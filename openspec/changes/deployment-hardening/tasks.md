# Tasks: Deployment hardening (MM-44)

## 1. Lock-pinned images
- [ ] Remove `uv.lock` from `.gitignore` (the orchestrator commits `uv.lock`).
- [ ] Dockerfile: restore `COPY pyproject.toml uv.lock ./` + `uv sync --frozen
  --no-dev --extra otel` (light) / `+ --extra local` (full); update the comment.
- [ ] CI `gates` sync: `uv sync --frozen --extra cochange --extra otel`.
- [ ] Verify `docker build --build-arg VARIANT=light` (frozen) builds + `/healthz`
  200; if `--frozen` fails, `uv lock` and note it.

## 2. GHCR publish
- [ ] `ci.yml`: `publish-image` job — needs [gates, deploy-validate], `if:
  github.event_name == 'push'`, `permissions: packages: write`; docker/login-action
  (ghcr, github.actor/GITHUB_TOKEN) + metadata-action (branch/sha/tag/latest tags) +
  build-push-action (VARIANT=light, push, gha cache). Light only; no full/torch.
- [ ] Chart `image.repository` default → `ghcr.io/welikecode/mint-mory`.
- [ ] README: GHCR pull usage + the one-time org "allow GITHUB_TOKEN packages" note.

## 3. oauth2-proxy / OIDC SSO
- [ ] values: `auth.mode` (none|basic|oauth2proxy, default none) + `auth.basic`
  (== current basicAuth) + `auth.oauth2proxy` (image/provider/issuer/clientId/
  clientSecret/cookieSecret/emailDomains/extraArgs). values.schema.json enum.
  Migrate the existing `ingress.basicAuth.*` to `auth.basic.*` (keep advanced example
  working) OR keep both wired — pick one and keep it consistent.
- [ ] templates: ingress.yaml branches on auth.mode (basic annotations |
  oauth2-proxy auth-url/auth-signin + `/oauth2` path | none);
  oauth2proxy-deployment.yaml + oauth2proxy-service.yaml + oauth2proxy-secret.yaml
  (client-secret + generated cookie-secret), rendered only when mode=oauth2proxy.
- [ ] README/NOTES: the three auth modes; SSO needs a BYO OIDC provider.

## 4. Validation
- [ ] `helm lint`; `helm template` for auth.mode none/basic/oauth2proxy all render;
  kubeconform each; oauth2proxy render shows Deployment+Service+Secret + auth-url/
  auth-signin annotations + `/oauth2` path.
- [ ] `docker build --build-arg VARIANT=light` (frozen) + `/healthz` 200.
- [ ] Existing Python gates green (frozen sync).
- [ ] `openspec validate deployment-hardening --strict`.
