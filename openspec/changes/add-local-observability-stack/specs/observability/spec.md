# Capability: observability (delta)

## ADDED Requirements

### Requirement: Local observability stack
`deploy/observability/compose.yaml` SHALL run an OpenTelemetry Collector that receives OTLP on gRPC 4317 and HTTP 4318, Jaeger 2 that receives the collector's traces and serves its UI on 16686, and Prometheus that scrapes the collector's metrics and serves its UI on 9090. Images SHALL be pinned to exact versions. Published ports SHALL bind to `127.0.0.1` by default; ports, bind address and images SHALL be overridable by variables documented in `deploy/observability/.env.example`.

#### Scenario: Stack definition is pinned and configurable
- **WHEN** `deploy/observability/compose.yaml` is parsed as YAML
- **THEN** it defines the services `otel-collector`, `jaeger` and `prometheus`; every `image` has an exact version (no `latest`, no missing tag); every published port has the form `${VAR:-127.0.0.1}:${VAR:-<port>}:<port>`; and Jaeger's OTLP ports are not published

#### Scenario: Collector routes each signal
- **WHEN** `deploy/observability/otel-collector.yaml` is parsed
- **THEN** its `otlp` receiver enables gRPC on 4317 and HTTP on 4318, the traces pipeline exports to `jaeger:4317`, and the metrics pipeline exports to a `prometheus` exporter that `prometheus.yml` scrapes

#### Scenario: Compose accepts the file
- **GIVEN** the `docker` command is available (the test is skipped otherwise)
- **WHEN** `docker compose -f deploy/observability/compose.yaml config` runs
- **THEN** it exits with 0

### Requirement: MintMory API service in the local stack
`compose.yaml` SHALL define a service `mintmory-api` under the profile `api` that builds the repository's `Dockerfile`, publishes the API on `127.0.0.1:8080` by default, stores its database in a named volume, and sets `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` and `MINTMORY_OTEL_ENABLED=true`.

#### Scenario: API profile is wired to the collector
- **WHEN** the compose file is parsed
- **THEN** `mintmory-api` has `profiles: [api]`, a `build` context at the repository root, and the two environment variables above

### Requirement: Telemetry status in doctor
`mintmory doctor` SHALL print a `telemetry` row with the mode (`auto`, `true`, `false`), the state (`exporting`, `off`, `no collector`, or `SDK missing`), the trace endpoint, whether a TCP connection to it succeeds within 100 ms, and the service name. It SHALL NOT print header values or other secrets.

#### Scenario: Doctor without a collector
- **GIVEN** `MINTMORY_OTEL_ENABLED` is unset and nothing listens on the default endpoint
- **WHEN** `mintmory doctor` runs
- **THEN** the output has a `telemetry` row that says `auto` and `no collector` and names `http://localhost:4318`

#### Scenario: Doctor hides headers
- **GIVEN** `OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer SECRET-1234`
- **WHEN** `mintmory doctor` runs
- **THEN** the output does not contain `SECRET-1234`

### Requirement: Helm telemetry settings
The chart SHALL render `MINTMORY_OTEL_ENABLED: "false"` when `otel.enabled` is false. When it is true, the chart SHALL also render `OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG` and `OTEL_RESOURCE_ATTRIBUTES` from `otel.sampler`, `otel.samplerArg` and `otel.resourceAttributes` when they are set, and `values.schema.json` SHALL describe the three values.

#### Scenario: Disabled means disabled
- **WHEN** the configmap template is rendered with the default values
- **THEN** it contains `MINTMORY_OTEL_ENABLED: "false"`

### Requirement: Observability guide
`docs/OBSERVABILITY.md` section 4 SHALL describe the modes, every variable MintMory reads with its precedence, the local stack in three commands, how to find a slow phase in Jaeger and in Prometheus, and the production settings; `deploy/observability/README.md` SHALL give the quick start; `README.md` SHALL link to both.

#### Scenario: Guide names every variable
- **WHEN** the guide is read
- **THEN** it names `MINTMORY_OTEL_ENABLED`, `MINTMORY_OTEL_EXPORTER`, `MINTMORY_OTEL_EXPORT_TIMEOUT_S`, `MINTMORY_OTEL_SERVICE_NAME`, `OTEL_SDK_DISABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` and `OTEL_TRACES_SAMPLER`
