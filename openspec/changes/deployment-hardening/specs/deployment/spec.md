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
CI SHALL publish the light image to `ghcr.io/<owner>/<repo>` on pushes to the
default branch and on release tags `v*`, using the built-in `GITHUB_TOKEN`. A release
tag `vX.Y.Z` SHALL publish the image tag `X.Y.Z`, the chart's default image tag
(`appVersion`). `latest` SHALL track only the default branch. Pull requests SHALL
build the image but SHALL NOT publish. The full (torch) variant SHALL NOT be
auto-published.

#### Scenario: A default-branch push publishes branch, sha and latest
- **WHEN** a commit is pushed to `main`
- **THEN** the `publish-image` job runs after `gates` and `deploy-validate` succeed and pushes the light image tagged `main`, `sha-<short sha>` and `latest`.

#### Scenario: A release tag publishes the chart's default image tag
- **GIVEN** `deploy/helm/mintmory/Chart.yaml` has `appVersion: "0.1.0"` and `packages/meta/pyproject.toml` has `version = "0.1.0"`
- **WHEN** the tag `v0.1.0` is pushed
- **THEN** `.github/workflows/ci.yml` runs (its `on.push.tags` includes `"v*"`), `publish-image` runs and pushes `ghcr.io/welikecode/mint-mory:0.1.0`, and that push does NOT tag the image `latest`.

#### Scenario: A pull request never publishes
- **WHEN** CI runs for a `pull_request` event
- **THEN** `deploy-validate` builds the light image and `publish-image` is skipped (its `if` is `github.event_name == 'push'`).

#### Scenario: The workflow is checked without helm, docker or network
- **WHEN** `tests/integration/test_deploy_hardening.py` loads `.github/workflows/ci.yml` with `yaml.safe_load` (PyYAML reads the key `on` as the boolean `True`, so the test reads `wf.get("on", wf.get(True))`)
- **THEN** `on.push.branches` is `["main"]`, `on.push.tags` contains `"v*"`, `pull_request` is still a trigger, `jobs.publish-image.needs` contains `gates` and `deploy-validate`, its `if` is `github.event_name == 'push'`, and the `docker/metadata-action` step's `with.tags` lines include `type=ref,event=branch`, `type=sha,prefix=sha-`, `type=semver,pattern={{version}}` and `type=raw,value=latest,enable={{is_default_branch}}`, do NOT include `type=ref,event=tag`, and its `with.flavor` contains `latest=false`.

#### Scenario: The chart's default tag tracks the release version
- **WHEN** the test compares `appVersion` from `deploy/helm/mintmory/Chart.yaml` with `project.version` from `packages/meta/pyproject.toml`
- **THEN** they are equal, and `scripts/bump_version.py X.Y.Z` rewrites the Chart `appVersion` to `"X.Y.Z"` (the chart's own `version:` line is left unchanged), so the tag that `release.yml` accepts (`vX.Y.Z` equal to the package version) always publishes the chart's default image tag.

### Requirement: Selectable ingress authentication mode
The chart SHALL support `auth.mode` values `none` (default), `basic` and
`oauth2proxy`. `basic` gates the ingress with HTTP basic auth backed by an htpasswd
Secret. `oauth2proxy` deploys oauth2-proxy for a bring-your-own OIDC provider and
routes ingress auth through it with ingress-nginx external-auth annotations. No mode
SHALL require an application code change, and health probes SHALL stay reachable.

#### Scenario: oauth2-proxy mode wires external auth without app changes
- **GIVEN** `auth.mode: oauth2proxy` with an OIDC issuer and client
- **WHEN** the chart is rendered
- **THEN** an oauth2-proxy Deployment + Service + Secret are produced (the OIDC client secret and cookie secret live only in that Secret), the Ingress carries `auth-url`/`auth-signin` external-auth annotations pointing at oauth2-proxy plus an `/oauth2` path, no application container changes, and `/healthz`/`/readyz` remain reachable by the kubelet (probes hit the pod directly, not the ingress).

#### Scenario: Default is unauthenticated and basic still works
- **WHEN** the chart is rendered with the default `auth.mode: none`
- **THEN** no auth is configured; and with `auth.mode: basic` the ingress gets HTTP basic-auth annotations backed by an htpasswd Secret.

### Requirement: oauth2-proxy pods have their own selector labels
In `auth.mode: oauth2proxy` the oauth2-proxy pods SHALL carry
`app.kubernetes.io/name: <chart name>-oauth2-proxy`, and the oauth2-proxy Deployment
and Service SHALL select on that label, so the application Service, Deployment and
PodDisruptionBudget selectors never match an oauth2-proxy pod and application
traffic never reaches oauth2-proxy. The application selectors SHALL NOT change.

#### Scenario: The rendered selectors are disjoint
- **GIVEN** `helm` is on PATH (the test is skipped with `pytest.mark.skipif(shutil.which("helm") is None, ...)` otherwise)
- **WHEN** the chart is rendered as release `t` with `--set auth.mode=oauth2proxy --set auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com --set auth.oauth2proxy.clientId=mintmory-ci --set auth.oauth2proxy.clientSecret=ci-placeholder --set ingress.enabled=true`
- **THEN** Deployment `t-mintmory-oauth2-proxy` has pod-template labels `{app.kubernetes.io/name: mintmory-oauth2-proxy, app.kubernetes.io/instance: t, app.kubernetes.io/component: oauth2-proxy}` and the same `matchLabels`; the selector of Service `t-mintmory` is NOT a subset of those pod labels; the selector of Service `t-mintmory-oauth2-proxy` IS a subset of them and is NOT a subset of the pod labels of Deployment `t-mintmory`; and Deployment `t-mintmory` still has `matchLabels` `{app.kubernetes.io/name: mintmory, app.kubernetes.io/instance: t}`.

#### Scenario: The postgres-mode PodDisruptionBudget does not cover oauth2-proxy
- **GIVEN** `helm` is on PATH
- **WHEN** the same render adds `-f deploy/helm/mintmory/values-postgres.yaml`
- **THEN** the `matchLabels` of PodDisruptionBudget `t-mintmory` are NOT a subset of the oauth2-proxy pod-template labels.

#### Scenario: The template wiring is checked without helm
- **WHEN** `tests/integration/test_deploy_hardening.py` reads the chart templates as text
- **THEN** `templates/_helpers.tpl` defines `mintmory.oauth2ProxySelectorLabels` whose body contains `app.kubernetes.io/name: {{ printf "%s-oauth2-proxy" (include "mintmory.name" .)`, `app.kubernetes.io/instance: {{ .Release.Name }}` and `app.kubernetes.io/component: oauth2-proxy`; `templates/oauth2proxy-deployment.yaml` contains `include "mintmory.oauth2ProxySelectorLabels"` exactly 2 times and `include "mintmory.selectorLabels"` 0 times; `templates/oauth2proxy-service.yaml` contains `include "mintmory.oauth2ProxySelectorLabels"` exactly 1 time and `include "mintmory.selectorLabels"` 0 times.

#### Scenario: The application selectors are unchanged
- **WHEN** the same test reads `_helpers.tpl`, `deployment.yaml`, `service.yaml` and `pdb.yaml`
- **THEN** the body of the `mintmory.selectorLabels` define is still exactly the two lines `app.kubernetes.io/name: {{ include "mintmory.name" . }}` and `app.kubernetes.io/instance: {{ .Release.Name }}`, and each of `deployment.yaml`, `service.yaml` and `pdb.yaml` still contains `include "mintmory.selectorLabels"`.

### Requirement: CI validates the oauth2proxy auth render
The CI `deploy-validate` job SHALL render the chart with `auth.mode=oauth2proxy`
(placeholder OIDC values, ingress enabled) and validate the output with kubeconform,
as it already does for the simple, advanced and postgres renders, so a broken
oauth2proxy template fails CI.

#### Scenario: The oauth2proxy render is validated in CI
- **WHEN** CI runs the `deploy-validate` job
- **THEN** a step runs `helm template t deploy/helm/mintmory --set auth.mode=oauth2proxy --set auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com --set auth.oauth2proxy.clientId=mintmory-ci --set auth.oauth2proxy.clientSecret=ci-placeholder --set ingress.enabled=true` piped into `kubeconform -strict -summary -kubernetes-version 1.29.0 -`, and the job fails if any rendered resource is invalid.

#### Scenario: The CI step is checked without helm
- **WHEN** `tests/integration/test_deploy_hardening.py` loads `.github/workflows/ci.yml` with `yaml.safe_load`
- **THEN** some step of `jobs.deploy-validate.steps` has a `run` string containing all of `auth.mode=oauth2proxy`, `auth.oauth2proxy.oidcIssuerUrl=`, `auth.oauth2proxy.clientId=`, `auth.oauth2proxy.clientSecret=`, `ingress.enabled=true` and `kubeconform -strict`.
