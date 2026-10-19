# deployment Specification

## Purpose
TBD - created by archiving change add-api-health-and-otel. Update Purpose after archive.

## Requirements

### Requirement: API liveness and readiness endpoints
The REST API SHALL expose two unauthenticated health endpoints. `GET /healthz`
(liveness) SHALL return HTTP 200 when the process is serving and SHALL NOT touch the
database, so a slow or busy store cannot trigger a liveness failure. `GET /readyz`
(readiness) SHALL execute a cheap store check (a `SELECT 1`) and return HTTP 200 when
the store is openable, otherwise HTTP 503. Neither endpoint SHALL require
authentication (Kubernetes probes reach the pod directly), and neither SHALL expose
secrets or database contents.

#### Scenario: Liveness answers without the database
- **WHEN** a client calls `GET /healthz`
- **THEN** the API returns HTTP 200 without querying the database.

#### Scenario: Readiness reflects store health
- **GIVEN** an initialised store
- **WHEN** a client calls `GET /readyz`
- **THEN** the API returns HTTP 200; and when the store cannot answer a `SELECT 1`, `GET /readyz` returns HTTP 503.

### Requirement: Telemetry activation at API startup
The REST API SHALL initialise OpenTelemetry at startup by calling the telemetry
activator with the configured OTel settings and the default service name `mintmory-api`.
Activation SHALL follow the observability capability's enablement modes: it SHALL be a
no-op when telemetry is off (`MINTMORY_OTEL_ENABLED=false`, `OTEL_SDK_DISABLED=true`, the
SDK not installed, which logs one WARNING when `MINTMORY_OTEL_ENABLED=true` or `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` or `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` is set, or `auto` with no collector configured or answering), and
a failure inside activation SHALL leave telemetry off without stopping the API. When telemetry
is on, the API SHALL emit its spans and metrics through the configured exporter, and the
lifespan SHALL flush them with a bounded shutdown when the application stops.

#### Scenario: OTel stays off by default
- **GIVEN** `MINTMORY_OTEL_ENABLED` unset (`auto`), no OTLP endpoint variable, and `mintmory.core.telemetry._endpoint_reachable` patched to return False
- **WHEN** the API starts under `TestClient`
- **THEN** `telemetry.is_enabled()` is False and instrumentation remains a zero-cost shim.

#### Scenario: OTel activates when enabled
- **GIVEN** `MINTMORY_OTEL_ENABLED=true` (the `true` mode; a boolean true is normalised to it) and the OTel SDK is installed
- **WHEN** the API starts under `TestClient`
- **THEN** `telemetry.is_enabled()` is True, so the API's spans and metrics go through the configured exporter.

#### Scenario: Shutdown flushes with a bound
- **GIVEN** `mintmory.api.app.shutdown_telemetry` and the `close` of the store returned by a patched `mintmory.api.app.build_storage` both append to one call list
- **WHEN** the API starts and stops under `TestClient`
- **THEN** the list is `["shutdown_telemetry", "close"]`.

### Requirement: OTLP metric export
When the OTel exporter is configured as `otlp`, the telemetry layer SHALL export
metrics via an OTLP metric exporter (not only to the console), so that both traces
and metrics reach the configured OTLP endpoint. When the exporter is `console`,
metrics SHALL continue to use the console exporter.

#### Scenario: OTLP exports metrics as well as traces
- **GIVEN** telemetry is enabled with `exporter=otlp`
- **WHEN** the meter provider is built
- **THEN** metrics are read by an OTLP metric exporter (mirroring the OTLP span exporter), so `mintmory.llm.latency_ms`/`mintmory.llm.calls`/dream-duration metrics can reach the OTLP endpoint rather than only the console.

### Requirement: Container image for the REST API
The project SHALL provide a Dockerfile that builds a runnable image of the MintMory
REST API: it SHALL run as a non-root user, expose port 8080, default the store to a
`/data` volume via `MINTMORY_DB=/data/memories.db`, and start the API with a single
uvicorn worker and no auto-reload (the SQLite store is single-writer). The build
SHALL support a `VARIANT` argument selecting a light image (default; hashing embedder
+ OTel, no torch) or a full image (adds the local sentence-transformers extra).

#### Scenario: Light image runs the API
- **WHEN** the image is built with the default (light) variant and run
- **THEN** the container starts the REST API on port 8080 as a non-root user with the store under `/data`, and `GET /healthz` returns 200.

### Requirement: Helm chart deploys the API with SQLite-safe topology
The project SHALL provide a Helm chart that deploys the REST API. Because the store
is a single SQLite file, the chart SHALL deploy exactly one replica, SHALL use the
`Recreate` update strategy (never RollingUpdate), and SHALL mount a `ReadWriteOnce`
PersistentVolumeClaim at `/data`. The chart SHALL configure a liveness probe against
`/healthz` and a readiness probe against `/readyz`. The chart SHALL NOT render more
than one replica or a rolling update when `storage.backend` is `sqlite` (the default).

#### Scenario: The rendered Deployment is single-writer safe
- **WHEN** the chart is rendered with `storage.backend` set to `sqlite` (the default)
- **THEN** the Deployment has one replica, `strategy.type: Recreate`, a ReadWriteOnce PVC mounted at `/data`, `MINTMORY_DB=/data/memories.db`, and liveness/readiness probes on `/healthz` and `/readyz`.

### Requirement: Configuration and secrets separation
The chart SHALL pass non-secret settings (the `MINTMORY_*` and OpenTelemetry
environment) through a ConfigMap and SHALL place API keys
(`MINTMORY_LLM_API_KEY`/`MINTMORY_EMBED_API_KEY`/`MINTMORY_VISION_API_KEY`) in a
Secret rendered only when provided. With empty configuration the pod SHALL still run
(MintMory defaults to a fully offline configuration).

#### Scenario: Secrets are separated from config and optional
- **WHEN** the chart is rendered with no secrets set
- **THEN** no Secret with API keys is rendered, the ConfigMap carries only non-secret settings, and the Deployment is still valid.

### Requirement: Simple and advanced deployment tiers
The chart SHALL support a simple tier (Deployment + Service + PVC + probes; no
ingress, no auth, OpenTelemetry off) and an advanced tier that additionally enables
an Ingress with basic authentication via ingress-nginx annotations backed by an
htpasswd Secret (generated from values or an existing Secret), OpenTelemetry export
to a bring-your-own OTLP endpoint, and resource requests/limits. Enabling advanced
features SHALL be values-driven and default to off.

#### Scenario: Advanced tier adds ingress basic auth without app changes
- **GIVEN** the advanced values enable ingress and basic auth
- **WHEN** the chart is rendered
- **THEN** an Ingress is produced with ingress-nginx basic-auth annotations referencing an htpasswd Secret, an OTLP endpoint is set in the ConfigMap, and none of this requires any change to the application container.

### Requirement: Deployment artifacts are validated in CI
CI SHALL validate the deployment artifacts without a live cluster: `helm lint`,
`helm template` for both tiers, offline schema validation (kubeconform) of the
rendered manifests, and a build-smoke of the light container image (no registry
publish).

#### Scenario: CI catches broken manifests or Dockerfile
- **WHEN** CI runs the deploy-validation job
- **THEN** it fails if the chart does not lint, either tier does not render, the rendered manifests are not client-side valid, or the light image does not build.

### Requirement: Published container image
CI publishes the light image to `ghcr.io/<owner>/<repo>`, and a release tag `vX.Y.Z`
publishes the image tag `X.Y.Z` (the CI behaviour is in `design.md` section 2: it is
checked by the repository CI and by review, not by these scenarios). For that tag to be
the chart's default image tag, the chart's `appVersion` SHALL equal the package version,
and `scripts/bump_version.py` SHALL rewrite the double-quoted `appVersion` line of
`deploy/helm/mintmory/Chart.yaml` with the five package `pyproject.toml` files, through
`bump_chart_text(text: str, new_version: str) -> str` and
`main(argv: list[str] | None = None, root: Path | None = None) -> None`. A chart without
that line, or a version that is not `X.Y.Z`, SHALL fail the bump with nothing written.

#### Scenario: The chart's default tag tracks the release version
- **WHEN** the test compares `appVersion` from `deploy/helm/mintmory/Chart.yaml` with `project.version` from `packages/meta/pyproject.toml`
- **THEN** they are equal, and `scripts/bump_version.py X.Y.Z` rewrites the Chart `appVersion` to `"X.Y.Z"` (the chart's own `version:` line is left unchanged; see the next scenarios), so the tag that `release.yml` accepts (`vX.Y.Z` equal to the package version) always publishes the chart's default image tag.

#### Scenario: bump_version.py updates the chart through main()
- **GIVEN** a root with the five package `pyproject.toml` files at `version = "0.1.0"` and `deploy/helm/mintmory/Chart.yaml` containing `apiVersion: v2\nname: mintmory\nversion: 0.1.0\nappVersion: "0.1.0"\n`
- **WHEN** `main(["0.2.0"], root=<that root>)` runs (`main(argv=None, root=None)` defaults to `sys.argv[1:]` and the repository root)
- **THEN** Chart.yaml is `apiVersion: v2\nname: mintmory\nversion: 0.1.0\nappVersion: "0.2.0"\n`, the five pyprojects have `version = "0.2.0"`, and stdout contains the line `bumped deploy/helm/mintmory/Chart.yaml`.

#### Scenario: A Chart without a double-quoted appVersion fails the bump and writes nothing
- **GIVEN** the same root but Chart.yaml is `appVersion: 0.1.0\n` (or single-quoted, or has no `appVersion` line)
- **WHEN** `main(["0.2.0"], root=<that root>)` runs, or `bump_chart_text` is called on that text
- **THEN** `bump_chart_text` raises `ValueError("appVersion line not found")`, `main` exits via `SystemExit` with a message containing `appVersion`, and no file (pyproject or chart) has been modified.

#### Scenario: A bad version argument is rejected
- **WHEN** `main(["1.2"], root=<that root>)` runs
- **THEN** `SystemExit("usage: bump_version.py X.Y.Z")` is raised and no file is modified.

### Requirement: Selectable ingress authentication mode
The chart's `auth.mode` is `none` (default), `basic` or `oauth2proxy`; `none` and
`basic` are the simple and advanced tiers of the deployment spec's requirement "Simple
and advanced deployment tiers" and do not change here. In `oauth2proxy` mode the chart
SHALL deploy oauth2-proxy for a bring-your-own OIDC provider and SHALL route ingress auth
through it with ingress-nginx external-auth annotations, with no application code or
container change, the health probes still reachable, and application traffic kept on
the application pods.

#### Scenario: oauth2-proxy mode wires external auth without app changes
- **WHEN** the chart is rendered with `helm template` as release `t` twice: in mode `none` with only `--set ingress.enabled=true`, and in mode `oauth2proxy` with `--set auth.mode=oauth2proxy --set auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com --set auth.oauth2proxy.clientId=mintmory-ci --set auth.oauth2proxy.clientSecret=ci-placeholder --set ingress.enabled=true`
- **THEN** the `oauth2proxy` render has a Deployment, a Service and a Secret named `t-mintmory-oauth2-proxy` (the Secret holds the keys `client-secret` and `cookie-secret`); its Ingress `t-mintmory` has the annotation `nginx.ingress.kubernetes.io/auth-url` starting with `http://t-mintmory-oauth2-proxy.` and `nginx.ingress.kubernetes.io/auth-signin` containing `/oauth2/start`, and a path `/oauth2` whose backend is Service `t-mintmory-oauth2-proxy`; the containers of its Deployment `t-mintmory` equal those of the `none` render, and their liveness and readiness probes are `httpGet` on `/healthz` and `/readyz` (the kubelet calls the pod, not the ingress); and the selector of Service `t-mintmory` is NOT a subset of the pod-template labels of Deployment `t-mintmory-oauth2-proxy`, so no application request reaches oauth2-proxy.

### Requirement: oauth2-proxy pods have their own selector labels
In `auth.mode: oauth2proxy` the oauth2-proxy pods SHALL carry
`app.kubernetes.io/name: <chart name>-oauth2-proxy`, and the oauth2-proxy Deployment
and Service SHALL select on that label, so the application Service, Deployment and
PodDisruptionBudget selectors never match an oauth2-proxy pod and application
traffic never reaches oauth2-proxy. The application selectors SHALL NOT change.

#### Scenario: The rendered selectors are disjoint
- **WHEN** the chart is rendered with `helm template` as release `t` with `--set auth.mode=oauth2proxy --set auth.oauth2proxy.oidcIssuerUrl=https://issuer.example.com --set auth.oauth2proxy.clientId=mintmory-ci --set auth.oauth2proxy.clientSecret=ci-placeholder --set ingress.enabled=true`
- **THEN** Deployment `t-mintmory-oauth2-proxy` has pod-template labels `{app.kubernetes.io/name: mintmory-oauth2-proxy, app.kubernetes.io/instance: t, app.kubernetes.io/component: oauth2-proxy}` and the same `matchLabels`; the selector of Service `t-mintmory` is NOT a subset of those pod labels; the selector of Service `t-mintmory-oauth2-proxy` IS a subset of them and is NOT a subset of the pod labels of Deployment `t-mintmory`; and the application selectors are unchanged: Deployment `t-mintmory` still has `matchLabels` `{app.kubernetes.io/name: mintmory, app.kubernetes.io/instance: t}` and Service `t-mintmory` still has exactly that selector.

Facts the render relies on (read from the chart): the oauth2-proxy pod template carries only the helper labels (no `podLabels` are merged into it; `podLabels` apply to `deployment.yaml` only), and `values-postgres.yaml` renders the PDB `t-mintmory` with no further required values (CI already renders it that way).

#### Scenario: The postgres-mode PodDisruptionBudget does not cover oauth2-proxy
- **WHEN** the same render adds `-f deploy/helm/mintmory/values-postgres.yaml`
- **THEN** the `matchLabels` of PodDisruptionBudget `t-mintmory` are NOT a subset of the oauth2-proxy pod-template labels, and are still exactly `{app.kubernetes.io/name: mintmory, app.kubernetes.io/instance: t}`.

#### Scenario: The README documents the tag scheme and the upgrade step
- **WHEN** `tests/integration/test_deploy_hardening.py` reads `deploy/helm/mintmory/README.md`
- **THEN** the text contains each of the substrings `vX.Y.Z`, `X.Y.Z`, `latest`, `app.kubernetes.io/name`, `oauth2-proxy Deployment` and `helm upgrade`.
