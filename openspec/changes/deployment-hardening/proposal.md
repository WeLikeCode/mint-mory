# Change: Deployment hardening — lock-pinned images, GHCR publish, oauth2-proxy SSO (MM-44)

## Why

Follow-ups to the MM-42/MM-43 Kubernetes deployment:

1. **Images aren't reproducible.** `uv.lock` is gitignored (not committed), so the
   Dockerfile resolves dependencies fresh at build time (MM-43 dropped `--frozen`
   because CI's checkout has no lock). Two builds of the same commit can differ, and
   there is no pinned supply chain.
2. **No published image.** CI only build-smokes the image; there's no registry to
   `helm install` from. Operators must build locally.
3. **Basic auth only.** MM-43's advanced tier gates the ingress with HTTP basic
   auth. For real user login, an OIDC/SSO option (oauth2-proxy) is wanted.

## What changes

- **Commit `uv.lock` → lock-pinned images.** Remove `uv.lock` from `.gitignore` and
  commit it; restore `COPY … uv.lock` + `uv sync --frozen` in the Dockerfile; switch
  CI to `uv sync --frozen --extra cochange --extra otel`. Builds become
  reproducible and supply-chain-pinned. (`--frozen` also fails CI fast if the lock
  drifts from `pyproject.toml`.)
- **GHCR image publishing.** A CI job publishes the **light** image to
  `ghcr.io/welikecode/mint-mory` on pushes to `main` (tags: `sha-<short sha>`, `main`,
  `latest`) and on release tags `vX.Y.Z` (image tag `X.Y.Z`, the chart's default
  `appVersion`; `latest` tracks only the default branch). Uses the built-in
  `GITHUB_TOKEN` with `packages: write` (no extra secret). The **full/torch** image
  is NOT auto-published (2 GB) — documented as build-on-demand. Publishing is
  additive; the existing `deploy-validate` build-smoke stays.
- **oauth2-proxy / OIDC SSO chart option.** The chart gains an `auth.mode`
  (`none` | `basic` | `oauth2proxy`, default `none`; `basic` = today's htpasswd).
  When `oauth2proxy`: render an oauth2-proxy Deployment + Service configured for a
  **bring-your-own OIDC** provider (issuer, client id, and a client-secret +
  cookie-secret Secret), and set the ingress-nginx external-auth annotations
  (`auth-url`, `auth-signin`) to route auth through it. Off by default; basic auth
  remains the lighter alternative. No application code changes (auth stays at the
  edge; MintMory is single-tenant — SSO gates access, it is not per-user tenancy).

## Remaining gap (review of 2026-10-15)

Sections 1–3 of `tasks.md` shipped in 317e0bf. Four things do not hold on `staging`:

1. **No image on release tags.** `.github/workflows/ci.yml` triggers on
   `push: branches: [main]` and `pull_request` only; with a `branches` filter and no
   `tags` filter GitHub never runs it for a tag push, so `publish-image` never runs
   for `v*` (`release.yml` runs on tags but publishes only to PyPI).
2. **Tag scheme does not match the chart.** With an empty `image.tag` the chart pulls
   `appVersion` (`0.1.0`), but the metadata step would publish the raw git tag
   (`v0.1.0`), so a default `helm install` of a release would not find its image.
   Fix: `type=semver,pattern={{version}}`, `flavor: latest=false`, and keep the
   Chart `appVersion` equal to the package version (`scripts/bump_version.py`).
3. **oauth2-proxy pods join the application Service.** The oauth2-proxy pods carry
   the application's selector labels (`app.kubernetes.io/name` + `instance`), and
   their container port is also named `http`, so the main Service (and the
   postgres-mode PDB) selects them and part of the app traffic lands on port 4180.
   Fix: the oauth2-proxy pods get `app.kubernetes.io/name: <chart name>-oauth2-proxy`;
   the application selectors are not changed (a Deployment selector is immutable,
   so changing the app's would break `helm upgrade` of every release). Changing the
   oauth2-proxy Deployment's selector means a release already running `oauth2proxy`
   mode must delete that one Deployment before upgrading (documented in the chart
   README).
4. **CI never renders `auth.mode=oauth2proxy`.** Task 4.1 asked for it; only the
   simple, advanced and postgres renders are validated.

Each fix has a pytest check that needs no `helm`, `docker` or network (the L4 gates
are ruff, mypy and pytest), plus a `helm template` check that is skipped when `helm`
is not installed.

## Impact

- Affected specs: **deployment** (ADDED: reproducible/pinned image, GHCR publish,
  oauth2-proxy auth mode).
- New/changed files: `.gitignore` (unignore uv.lock) + committed `uv.lock`;
  `Dockerfile` (restore `--frozen` + lock COPY); `.github/workflows/ci.yml` (frozen
  sync + a `publish-image` job); `deploy/helm/mintmory/` (values `auth.mode` +
  oauth2-proxy templates + schema + README/NOTES). No Python app code.
  The remaining gap adds: `ci.yml` (`tags: ["v*"]`, semver image tag,
  `latest=false`, an oauth2proxy render step), `templates/_helpers.tpl` +
  `templates/oauth2proxy-{deployment,service}.yaml` (own selector labels),
  `scripts/bump_version.py` (Chart `appVersion`), chart README, and the tests
  `tests/integration/test_deploy_hardening.py` + `tests/integration/test_bump_version.py`.
- Migrations: none. GHCR publish and oauth2-proxy are additive/off-by-default;
  committing the lock does not change runtime behaviour.
- Out of scope (separate epic): the Postgres/libsql HA storage backend — that is a
  storage-core re-architecture, designed separately (Fable/Opus), not implemented
  here.
