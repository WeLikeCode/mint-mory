# Capability: deployment (delta)

## ADDED Requirements

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
than one replica or a rolling update under any values.

#### Scenario: The rendered Deployment is single-writer safe
- **WHEN** the chart is rendered with any values
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
`helm template` for both tiers, a client-side `kubectl apply --dry-run` of the
rendered manifests, and a build-smoke of the light container image (no registry
publish).

#### Scenario: CI catches broken manifests or Dockerfile
- **WHEN** CI runs the deploy-validation job
- **THEN** it fails if the chart does not lint, either tier does not render, the rendered manifests are not client-side valid, or the light image does not build.
