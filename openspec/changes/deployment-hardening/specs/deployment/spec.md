# Capability: deployment (delta)

## ADDED Requirements

### Requirement: Reproducible lock-pinned container image
The dependency lockfile (`uv.lock`) SHALL be committed to the repository, and the
container image build SHALL install dependencies from it with a frozen sync
(`uv sync --frozen`) so that image builds are reproducible and supply-chain-pinned.
CI SHALL likewise sync frozen, so a lockfile that has drifted from `pyproject.toml`
fails the build rather than silently resolving new versions.

#### Scenario: A drifted lockfile fails the build
- **GIVEN** `uv.lock` is committed and the Dockerfile/CI use `uv sync --frozen`
- **WHEN** an image is built or CI runs
- **THEN** dependencies install from the committed lock, and if the lock is out of sync with `pyproject.toml` the build/CI fails rather than resolving unpinned versions.

### Requirement: Published container image
CI SHALL publish the light container image to the GitHub Container Registry
(`ghcr.io/<owner>/<repo>`) on pushes to the default branch and on release tags,
tagged by branch, short commit sha, git tag, and `latest` on the default branch,
authenticating with the built-in token (no extra registry secret). Pull requests
SHALL validate the image build but SHALL NOT publish. The full (torch) variant SHALL
NOT be auto-published.

#### Scenario: Main and tags publish, PRs do not
- **WHEN** a push lands on the default branch or a tag
- **THEN** the light image is pushed to GHCR with branch/sha/tag/latest tags after validation and tests pass; and a pull request builds the image for validation but publishes nothing.

### Requirement: Selectable ingress authentication mode
The chart SHALL support an authentication mode with values `none`, `basic`, and
`oauth2proxy` (default `none`). `basic` SHALL gate the ingress with HTTP basic auth
backed by an htpasswd Secret (as before). `oauth2proxy` SHALL deploy an oauth2-proxy
configured for a bring-your-own OIDC provider and route ingress authentication
through it via ingress-nginx external-auth annotations, with the OIDC client secret
and cookie secret held in a Secret. Enabling either auth mode SHALL require no
application code change, and health probes SHALL remain reachable (probes hit the pod
directly, not the ingress).

#### Scenario: oauth2-proxy mode wires external auth without app changes
- **GIVEN** `auth.mode: oauth2proxy` with an OIDC issuer and client
- **WHEN** the chart is rendered
- **THEN** an oauth2-proxy Deployment + Service + Secret are produced, the Ingress carries `auth-url`/`auth-signin` external-auth annotations pointing at oauth2-proxy plus an `/oauth2` path, no application container changes, and `/healthz`/`/readyz` remain reachable by the kubelet.

#### Scenario: Default is unauthenticated and basic still works
- **WHEN** the chart is rendered with the default `auth.mode: none`
- **THEN** no auth is configured; and with `auth.mode: basic` the ingress gets HTTP basic-auth annotations backed by an htpasswd Secret.
