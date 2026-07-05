# Design: Deployment hardening (MM-44)

Additive infra/CI + chart options. No Python app code changes.

## 1. Lock-pinned images (commit `uv.lock`)

- `.gitignore`: remove the `uv.lock` line. `git add uv.lock` (the working-tree lock,
  ~600 KB) so it is in the repo and thus in every checkout / build context.
- `Dockerfile`: restore `COPY pyproject.toml uv.lock ./` and `uv sync --frozen
  --no-dev --extra otel [--extra local for full]`. `--frozen` fails if the lock is
  out of sync with `pyproject.toml` — a supply-chain guard.
- `.github/workflows/ci.yml` (`gates` job sync step): `uv sync --frozen --extra
  cochange --extra otel`. If the lock is stale, CI fails loudly (correct); regen with
  `uv lock` and commit.
- Rationale note in the Dockerfile comment updated (it currently says the repo
  gitignores the lock — reverse that).

## 2. GHCR publish (`publish-image` CI job)

New job in `ci.yml`, separate from `gates`/`deploy-validate`:
```yaml
publish-image:
  name: Publish light image to GHCR
  runs-on: ubuntu-latest
  needs: [gates, deploy-validate]        # only publish if validation + tests pass
  if: github.event_name == 'push'        # main pushes + tags, not PRs
  permissions: { contents: read, packages: write }
  steps:
    - uses: actions/checkout@v4
    - uses: docker/login-action@v3
      with: { registry: ghcr.io, username: ${{ github.actor }}, password: ${{ secrets.GITHUB_TOKEN }} }
    - uses: docker/metadata-action@v5
      id: meta
      with:
        images: ghcr.io/${{ github.repository }}      # ghcr.io/welikecode/mint-mory
        tags: |
          type=ref,event=branch                        # main
          type=sha,prefix=sha-                         # sha-<short>
          type=ref,event=tag                           # v0.1.0-beta.2
          type=raw,value=latest,enable={{is_default_branch}}
    - uses: docker/build-push-action@v6
      with:
        context: .
        build-args: VARIANT=light
        push: true
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}
        cache-from: type=gha
        cache-to: type=gha,mode=max
```
- Only the **light** variant is published (full/torch is 2 GB — documented as
  `docker build --build-arg VARIANT=full`, not in CI).
- `needs: [gates, deploy-validate]` → never publish a broken image.
- `if: push` → PRs validate but don't publish (avoids pushing from forks / on PRs).
- First push under the org creates the package via `GITHUB_TOKEN`; the package is
  linked to the repo. If the org restricts `GITHUB_TOKEN` package creation, the job
  errors clearly (documented in the README as a one-time org setting).
- The chart's `image.repository` default is updated to
  `ghcr.io/welikecode/mint-mory` so `helm install` pulls the published image
  (still overridable).

## 3. oauth2-proxy / OIDC SSO chart option

Values:
```yaml
auth:
  mode: none            # none | basic | oauth2proxy
  basic: { username: "", password: "", existingSecret: "" }   # mode=basic (== today)
  oauth2proxy:
    image: quay.io/oauth2-proxy/oauth2-proxy:v7.6.0
    provider: oidc
    oidcIssuerUrl: ""                 # e.g. https://accounts.google.com
    clientId: ""
    clientSecret: ""                  # -> Secret
    cookieSecret: ""                  # 32-byte base64; -> Secret (or chart-generated)
    emailDomains: ["*"]
    extraArgs: {}
```
`values.schema.json`: `auth.mode` enum `[none, basic, oauth2proxy]`.

Templates:
- `_helpers.tpl`: keep the htpasswd helper (basic); add oauth2-proxy name/labels.
- `ingress.yaml`: branch on `auth.mode`:
  - `basic` → existing `auth-type: basic` + `auth-secret` annotations (unchanged).
  - `oauth2proxy` → `nginx.ingress.kubernetes.io/auth-url:
    "http://<oauth2proxy-svc>.<ns>.svc.cluster.local:4180/oauth2/auth"` and
    `auth-signin: "https://$host/oauth2/start?rd=$escaped_request_uri"`, plus an
    ingress path `/oauth2` → the oauth2-proxy Service (so the login/callback flow is
    reachable on the same host).
  - `none` → no auth annotations.
- `oauth2proxy-deployment.yaml` + `oauth2proxy-service.yaml` (rendered only when
  `mode=oauth2proxy`): oauth2-proxy configured `--provider=oidc`,
  `--oidc-issuer-url`, `--client-id`, `--email-domain`, `--http-address=0.0.0.0:4180`,
  `--reverse-proxy=true`, `--upstream=static://200` (auth-only; ingress does the
  routing), `--cookie-secure`, secrets via env from a Secret.
- `oauth2proxy-secret.yaml`: `OAUTH2_PROXY_CLIENT_SECRET` + `OAUTH2_PROXY_COOKIE_SECRET`
  (cookie-secret chart-generated with `randAlphaNum 32 | b64enc` if unset).

Health note: kubelet probes hit the pod directly (not via ingress), so SSO does NOT
block `/healthz`/`/readyz` — unchanged from basic auth.

## 4. Validation (local + CI)

- `helm lint`; `helm template` for THREE modes (`auth.mode=none|basic|oauth2proxy`)
  → all render; oauth2proxy render shows the Deployment+Service+Secret + the
  `auth-url`/`auth-signin` ingress annotations + the `/oauth2` path. kubeconform each.
- `docker build --build-arg VARIANT=light` with `--frozen` (lock present) succeeds;
  container `/healthz` → 200.
- CI `gates` frozen sync green; `publish-image` job present, gated on push +
  needs-green (won't actually push on the validating PR/this branch unless it's a
  main push — it WILL run on the main push after commit; verify it succeeds or
  diagnose the GHCR permission).
- `openspec validate deployment-hardening --strict`.

## 5. Edge cases / risks
- **Stale lock** after committing: run `uv lock` if `--frozen` fails; the current
  working-tree lock built fine locally, so it should be in sync.
- **GHCR first-publish permission**: org may need "Allow GITHUB_TOKEN to create
  packages" (documented). If it fails, the fix is an org/repo setting, not code.
- **oauth2-proxy without a real OIDC provider**: renders fine (templating), but a
  live login needs the operator's issuer/client — documented; default `mode=none`.
- Do not enable oauth2proxy AND basic simultaneously (schema is a single `mode`).

## 6. Gates
Existing Python gates green (frozen). Plus `helm lint`/`template` (3 modes) +
kubeconform + `docker build` (light, frozen) + `openspec validate
deployment-hardening --strict`.
