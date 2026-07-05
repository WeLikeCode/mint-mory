# Capability: deployment (delta)

## ADDED Requirements

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
activator with the configured OTel settings. When `MINTMORY_OTEL_ENABLED` is false
or the optional OTel SDK is not installed, activation SHALL be a no-op with no change
to default behaviour. When enabled, the API SHALL emit the existing spans and metrics
through the configured exporter.

#### Scenario: OTel stays off by default
- **GIVEN** `MINTMORY_OTEL_ENABLED` is false (default)
- **WHEN** the API starts
- **THEN** telemetry activation is a no-op and instrumentation remains a zero-cost shim.

#### Scenario: OTel activates when enabled
- **GIVEN** `MINTMORY_OTEL_ENABLED` is true and the OTel SDK is installed
- **WHEN** the API starts
- **THEN** telemetry is active and the API's spans and metrics are emitted through the configured exporter.

### Requirement: OTLP metric export
When the OTel exporter is configured as `otlp`, the telemetry layer SHALL export
metrics via an OTLP metric exporter (not only to the console), so that both traces
and metrics reach the configured OTLP endpoint. When the exporter is `console`,
metrics SHALL continue to use the console exporter.

#### Scenario: OTLP exports metrics as well as traces
- **GIVEN** telemetry is enabled with `exporter=otlp`
- **WHEN** the meter provider is built
- **THEN** metrics are read by an OTLP metric exporter (mirroring the OTLP span exporter), so `mintmory.llm.latency_ms`/`mintmory.llm.calls`/dream-duration metrics can reach the OTLP endpoint rather than only the console.
