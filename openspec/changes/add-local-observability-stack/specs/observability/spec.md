# Capability: observability (delta)

## Purpose

MintMory's observability: OpenTelemetry traces and metrics from every entry point (CLI, REST API, MCP servers), safe and silent when no collector runs, distributed across HTTP, MCP and outbound LLM calls, with a local collector, Jaeger and Prometheus stack for development.

## ADDED Requirements

### Requirement: Local observability stack
`deploy/observability/compose.yaml` SHALL run an OpenTelemetry Collector that receives OTLP on gRPC 4317 and HTTP 4318, Jaeger 2 that receives the collector's traces and serves its UI on 16686, and Prometheus that scrapes the collector's metrics and serves its UI on 9090. Images SHALL be pinned to exact versions. Published ports SHALL bind to `127.0.0.1` by default; ports, bind address and images SHALL be overridable by variables documented in `deploy/observability/.env.example`.

#### Scenario: Stack definition is pinned and configurable
- **WHEN** `deploy/observability/compose.yaml` is parsed as YAML
- **THEN** it defines the services `otel-collector`, `jaeger` and `prometheus`; every `image`, after resolving `${VAR:-default}` to its default, has a tag that is neither missing nor `latest`; every published port has the form `${VAR:-127.0.0.1}:${VAR:-<port>}:<port>`; and Jaeger's OTLP ports are not published

#### Scenario: Collector routes each signal
- **WHEN** `deploy/observability/otel-collector.yaml` is parsed
- **THEN** its `otlp` receiver enables gRPC on 4317 and HTTP on 4318, the traces pipeline exports to `jaeger:4317`, and the metrics pipeline exports to a `prometheus` exporter that `prometheus.yml` scrapes

#### Scenario: The environment example documents every variable
- **WHEN** `compose.yaml` and `.env.example` are read
- **THEN** every `MINTMORY_OBS_*` name used in `compose.yaml` appears in `.env.example` as `NAME=<the same default as in compose.yaml>`, and `.env.example` contains `# OTEL_TRACES_SAMPLER=`

#### Scenario: Compose accepts the file
- **GIVEN** the `docker` command is available (the test is skipped otherwise)
- **WHEN** `docker compose -f deploy/observability/compose.yaml config` runs
- **THEN** it exits with 0

### Requirement: MintMory API service in the local stack
`compose.yaml` SHALL define a service `mintmory-api` under the profile `api` that builds the repository's `Dockerfile` (which already installs the `otel` extra in both variants, runs uvicorn on `0.0.0.0:8080` and declares `VOLUME /data` with `MINTMORY_DB=/data/memories.db`), publishes the API on `127.0.0.1:8080` by default, mounts a named volume at `/data`, and sets `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` and `MINTMORY_OTEL_ENABLED=true`.

#### Scenario: API profile is wired to the collector
- **WHEN** the compose file is parsed
- **THEN** `mintmory-api` has `profiles: [api]`, a `build` context at the repository root, a named volume mounted at `/data`, port `${MINTMORY_OBS_BIND:-127.0.0.1}:${MINTMORY_OBS_API_PORT:-8080}:8080`, no `command` override, and the two environment variables above; and every `Dockerfile` line whose command starts with `uv sync` contains `--extra otel` (on `staging` exactly two such lines)

### Requirement: Telemetry status in doctor
`mintmory doctor` SHALL add one row whose check is `telemetry` and whose status is `mode=<auto|true|false>, state=<state>, endpoint=<endpoint>, reachable=<yes|no|invalid>, service=<name>`. `state` maps `add-telemetry-runtime`'s `_resolve_state` values `export`, `off`, `no collector`, `sdk missing` to `exporting`, `off`, `no collector`, `SDK missing`; `endpoint` is runtime's `_traces_endpoint()`; `service` is runtime's `_service_name(settings, "mintmory-cli")`. `reachable` SHALL be `invalid` when the endpoint has no host or its port is not a valid number (`urllib.parse.urlsplit(...).port` raises `ValueError`), else `yes`/`no` from runtime's `_endpoint_reachable` (100 ms; port 443/80 by scheme when absent). Building the row SHALL never raise and never change doctor's exit code: on any exception the status is `status unavailable (<exception class name>)`. It SHALL NOT print header values or other secrets.

#### Scenario: Doctor without a collector
- **GIVEN** the `cli_db` fixture, `MINTMORY_OTEL_ENABLED` unset, and `telemetry._endpoint_reachable` patched to return False
- **WHEN** `mintmory doctor` runs
- **THEN** it exits 0 and the `telemetry` row contains `mode=auto, state=no collector, endpoint=http://localhost:4318/v1/traces, reachable=no, service=mintmory-cli`

#### Scenario: Doctor with an endpoint it cannot parse
- **GIVEN** the `cli_db` fixture and `OTEL_EXPORTER_OTLP_ENDPOINT` set to (a) `not a url`, (b) `http://localhost:99999`
- **WHEN** `mintmory doctor` runs
- **THEN** it exits 0 and the `telemetry` row contains `reachable=invalid`

#### Scenario: Doctor survives a failing status
- **GIVEN** the `cli_db` fixture and `mintmory.core.telemetry.status` patched to raise `RuntimeError`
- **WHEN** `mintmory doctor` runs
- **THEN** it exits 0 and the `telemetry` row contains `status unavailable (RuntimeError)`

#### Scenario: Doctor shows SDK missing and hides headers
- **GIVEN** the `cli_db` fixture, `MINTMORY_OTEL_ENABLED=true`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318`, `OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer SECRET-1234`, `_endpoint_reachable` patched to True
- **WHEN** `mintmory doctor` runs, then again with `telemetry._sdk_available` patched to False
- **THEN** the first row contains `state=exporting` and `reachable=yes`, the second `state=SDK missing`, and neither output contains `SECRET-1234`

### Requirement: Helm telemetry settings
`values.yaml` SHALL keep `otel.enabled: false` as the default and add `otel.sampler: ""`, `otel.samplerArg: ""` and `otel.resourceAttributes: ""`; `values.schema.json` SHALL declare the three as `string` inside the `otel` object, which keeps `additionalProperties: false`. The chart SHALL render `MINTMORY_OTEL_ENABLED: "false"` when `otel.enabled` is false, and when it is true also `OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG` and `OTEL_RESOURCE_ATTRIBUTES` from the three values, each only when it is a non-empty string.

#### Scenario: Sampler values are rendered
- **WHEN** the configmap template, `values.yaml` and `values.schema.json` are read
- **THEN** inside the `otel.enabled` branch the template renders each of the three variables under an `if` on its value; `values.yaml` has the three keys with `""`; the schema declares them as `string` and `otel.additionalProperties` is false

#### Scenario: Rendered with helm
- **GIVEN** `helm` is on PATH (the test is skipped otherwise)
- **WHEN** `helm template` runs with the defaults, and with `--set otel.enabled=true --set-string otel.sampler=parentbased_traceidratio,otel.samplerArg=0.1`
- **THEN** the first output contains `MINTMORY_OTEL_ENABLED: "false"` and no `OTEL_TRACES_SAMPLER`; the second contains `OTEL_TRACES_SAMPLER: "parentbased_traceidratio"` and `OTEL_TRACES_SAMPLER_ARG: "0.1"` and no `OTEL_RESOURCE_ATTRIBUTES`

#### Scenario: Disabled means disabled
- **WHEN** the configmap template text is read
- **THEN** an `else` branch of `.Values.otel.enabled` contains `MINTMORY_OTEL_ENABLED: "false"`

### Requirement: Observability guide
`docs/OBSERVABILITY.md` section 4 SHALL describe the modes, every variable MintMory reads with its precedence, the local stack in three commands, how to find a slow phase in Jaeger and in Prometheus, and the production settings; `deploy/observability/README.md` SHALL give the quick start; `README.md` SHALL link to both.

#### Scenario: Guide names every variable
- **WHEN** `docs/OBSERVABILITY.md` section 4 (from `## 4.` to `## 5.`) is read
- **THEN** it names `MINTMORY_OTEL_ENABLED`, `MINTMORY_OTEL_EXPORTER`, `MINTMORY_OTEL_EXPORT_TIMEOUT_S`, `MINTMORY_OTEL_SERVICE_NAME`, `OTEL_SDK_DISABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_EXPORTER_OTLP_TIMEOUT`, `OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG`, `OTEL_PROPAGATORS` and `OTEL_PYTHON_EXCLUDED_URLS`

#### Scenario: Guide has its parts and links
- **WHEN** the guide, `deploy/observability/README.md` and `README.md` are read
- **THEN** section 4 has the headings `Modes`, `Variables`, `Local stack`, `Finding a slow phase` and `Production`, and still the headings `4.3 Spans to emit`, `4.4 Metrics to emit` and `Distributed tracing` of parts 2 and 3; the guide and the stack README contain `docker compose -f deploy/observability/compose.yaml up -d`; the guide contains `mintmory_search_latency_ms_bucket`; and `README.md` links to `docs/OBSERVABILITY.md` and `deploy/observability/README.md`
