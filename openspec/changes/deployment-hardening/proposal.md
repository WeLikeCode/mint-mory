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
  `ghcr.io/welikecode/mint-mory` on pushes to `main` (tags: `sha-<sha>`, `main`) and
  on git tags (the version tag, e.g. `v0.1.0-beta.2`; `latest` tracks only the default branch). Uses the built-in
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

## Impact

- Affected specs: **deployment** (ADDED: reproducible/pinned image, GHCR publish,
  oauth2-proxy auth mode).
- New/changed files: `.gitignore` (unignore uv.lock) + committed `uv.lock`;
  `Dockerfile` (restore `--frozen` + lock COPY); `.github/workflows/ci.yml` (frozen
  sync + a `publish-image` job); `deploy/helm/mintmory/` (values `auth.mode` +
  oauth2-proxy templates + schema + README/NOTES). No Python app code.
- Migrations: none. GHCR publish and oauth2-proxy are additive/off-by-default;
  committing the lock does not change runtime behaviour.
- Out of scope (separate epic): the Postgres/libsql HA storage backend — that is a
  storage-core re-architecture, designed separately (Fable/Opus), not implemented
  here.
