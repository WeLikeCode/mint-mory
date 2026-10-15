# Tasks: local Jaeger stack, doctor check and guide (OpenTelemetry, part 4 of 4)

Requires `add-telemetry-runtime`. No new Python dependencies. The gates have no Docker and no Helm, so every check
below is a pytest test that parses files (`yaml` is available; use `pytest.importorskip("yaml")`), plus tests that
run `docker` or `helm` only when `shutil.which(...)` finds them (skipped otherwise). Put the file tests in
`packages/core/tests/test_observability_stack.py` (or the package where the deploy tests already live, if any).
Write each test first and see it fail.

## 1. Collector, Jaeger and Prometheus (`deploy/observability/`)
- [ ] 1.1 Tests for every scenario of "Local observability stack" and "MintMory API service in the local stack".
- [ ] 1.2 `otel-collector.yaml`, exactly this content (validated with `otelcol-contrib validate` on
  `otel/opentelemetry-collector-contrib:0.162.0`):

  ```yaml
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318
  processors:
    memory_limiter:
      check_interval: 1s
      limit_mib: 256
    batch: {}
  exporters:
    otlp/jaeger:
      endpoint: jaeger:4317
      tls:
        insecure: true
    prometheus:
      endpoint: 0.0.0.0:8889
      add_metric_suffixes: false
      resource_to_telemetry_conversion:
        enabled: true
  service:
    pipelines:
      traces:
        receivers: [otlp]
        processors: [memory_limiter, batch]
        exporters: [otlp/jaeger]
      metrics:
        receivers: [otlp]
        processors: [memory_limiter, batch]
        exporters: [prometheus]
  ```
- [ ] 1.3 `prometheus.yml`: `scrape_interval: 15s`, one job `otel-collector` with target `otel-collector:8889`.
- [ ] 1.4 `compose.yaml` (Compose specification, no top-level `version`):
  - `otel-collector`: image `${MINTMORY_OBS_COLLECTOR_IMAGE:-otel/opentelemetry-collector-contrib:0.162.0}`, command
    `--config=/etc/otelcol-contrib/config.yaml`, the config mounted read-only there, ports
    `${MINTMORY_OBS_BIND:-127.0.0.1}:${MINTMORY_OBS_OTLP_GRPC_PORT:-4317}:4317` and the same for HTTP 4318,
    `depends_on: [jaeger]`.
  - `jaeger`: image `${MINTMORY_OBS_JAEGER_IMAGE:-jaegertracing/jaeger:2.22.0}` (its default configuration is the
    all-in-one with in-memory storage and OTLP receivers), port `${MINTMORY_OBS_BIND:-127.0.0.1}:${MINTMORY_OBS_JAEGER_UI_PORT:-16686}:16686`
    only.
  - `prometheus`: image `${MINTMORY_OBS_PROMETHEUS_IMAGE:-prom/prometheus:v3.15.0}`, `prometheus.yml` mounted read-only
    at `/etc/prometheus/prometheus.yml`, port `${MINTMORY_OBS_BIND:-127.0.0.1}:${MINTMORY_OBS_PROMETHEUS_PORT:-9090}:9090`.
  - `mintmory-api` with `profiles: [api]`: `build: {context: ../.., dockerfile: Dockerfile}`, port
    `${MINTMORY_OBS_BIND:-127.0.0.1}:${MINTMORY_OBS_API_PORT:-8080}:8080`, a named volume for the database (look at the
    `Dockerfile` for the data path and the command), environment `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`,
    `MINTMORY_OTEL_ENABLED=true`, `OTEL_SERVICE_NAME=mintmory-api`, `depends_on: [otel-collector]`.
- [ ] 1.5 `.env.example`: every `MINTMORY_OBS_*` variable above with its default and one comment line each, plus the
  MintMory-side variables a developer may want (`OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG`,
  `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_METRICS_EXPORTER`), all commented out.
- [ ] 1.6 `README.md` in `deploy/observability/`: the quick start (`docker compose -f deploy/observability/compose.yaml up -d`,
  run any `mintmory` command or start `mintmory-mcp`, open `http://localhost:16686` and pick the service
  `mintmory-cli` or `mintmory-mcp`; Prometheus at `http://localhost:9090` with the query
  `histogram_quantile(0.95, sum by (le, phase) (rate(mintmory_search_latency_ms_bucket[5m])))`, which needs a
  long-running process such as the API or an MCP server: a one-shot CLI command exports once, under its own
  `service.instance.id`), the `api` profile
  (`--profile api up -d --build`), changing ports with a `.env` file, and stopping (`down`, `down -v`).

## 2. Doctor (`packages/cli/src/mintmory/cli/main.py`, `telemetry.py`)
- [ ] 2.1 Tests for both scenarios of "Telemetry status in doctor". Make "nothing listens" certain by patching
  `telemetry._endpoint_reachable` to return False (do not change `_DEFAULT_ENDPOINT`: the row must still name
  `http://localhost:4318`), remove `MINTMORY_OTEL_ENABLED` with `monkeypatch.delenv` (the root `conftest.py` sets it to
  `false`), and set `monkeypatch.setenv("COLUMNS", "200")` so Rich does not wrap the table in `CliRunner`'s 80 columns.
- [ ] 2.2 Add `telemetry.status(settings, default_service_name="mintmory-cli") -> dict[str, str]` returning `mode`,
  `state` (part 1's `_resolve_state`; `export` is shown as `exporting`), `endpoint` (part 1's `_traces_endpoint()`),
  `reachable` (`yes`/`no`, `_endpoint_reachable`) and `service_name` (part 1's `_service_name(settings,
  default_service_name)`), without initialising anything. Add a `telemetry` row to the `doctor`
  table built from it. Never read or print `OTEL_EXPORTER_OTLP_HEADERS`.

## 3. Helm (`deploy/helm/mintmory/`)
- [ ] 3.1 Tests: the configmap template text renders `MINTMORY_OTEL_ENABLED: "false"` in an `else` branch of
  `.Values.otel.enabled`, and references `.Values.otel.sampler`, `.Values.otel.samplerArg`,
  `.Values.otel.resourceAttributes`; `values.schema.json` declares them as strings. If `helm` is on PATH, also run
  `helm template` with defaults and with `--set otel.enabled=true --set-string
  otel.sampler=parentbased_traceidratio,otel.samplerArg=0.1` and assert the rendered values. (`--set` turns
  `samplerArg=1` into a number, which a string schema rejects; the guide uses `--set-string` too.)
- [ ] 3.2 Change `templates/configmap.yaml`, `values.yaml` (with comments) and `values.schema.json` accordingly. Keep
  the existing `otel.endpoint` and `otel.serviceName` behaviour.

## 4. Guide
- [ ] 4.1 Tests "Guide names every variable" and "Guide has its parts and links" (read the files and assert each name,
  heading, command and link).
- [ ] 4.2 Rewrite `docs/OBSERVABILITY.md` section 4.5 (and the summary at the top of section 4) as the user guide in the
  spec, under the headings `Modes`, `Variables`, `Local stack`, `Finding a slow phase` and `Production`: a table of the
  variables with default and precedence; modes (`auto` exports when a collector is configured or
  answers on `localhost:4318`, `true`, `false`); the local stack; "finding a bottleneck" (Jaeger: search service and
  operation, sort by duration, open the slowest trace, read the `mintmory.search.*` and `gen_ai.chat` children;
  Prometheus: the phase query above); production (Helm values, sampling ratio, `OTEL_EXPORTER_OTLP_HEADERS` for an
  authenticated collector, kept in a Secret). Add a short "Observability" pointer in `README.md`.

## 5. Checks
- [ ] 5.1 Run `ruff check`, `ruff format --check`, `mypy packages` and the full test suite; coverage stays at or above
  80%.
