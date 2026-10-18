# Tasks: local Jaeger stack, doctor check and guide (OpenTelemetry, part 4 of 4)

Requires `add-telemetry-runtime`. No new Python dependencies. The gates have no Docker and no Helm, so every check
below is a pytest test that parses files (`yaml` is available; use `pytest.importorskip("yaml")`), plus tests that
run `docker` or `helm` only when `shutil.which(...)` finds them (skipped otherwise). No deploy tests exist on
`staging`; put the file tests in `tests/integration/test_observability_stack.py` (in `testpaths`; the repository root
is `Path(__file__).resolve().parents[2]`, as `tests/integration/test_bump_version.py` does) and the doctor tests in
`packages/cli/tests/test_cli.py`. Write each test first and see it fail. The image tags below were current when the
change was written; the gates cannot pull them, so only the `docker` test (skipped without Docker) checks them.

## 1. Collector, Jaeger and Prometheus (`deploy/observability/`)
- [x] 1.1 Tests for every scenario of "Local observability stack" and "MintMory API service in the local stack".
  Resolve `${VAR:-default}` with `re.fullmatch(r"\$\{[A-Z_]+:-(.+)\}", image)` before checking the tag (the part
  after the last `:` that follows the last `/`). For the `Dockerfile` check, strip each line and its `RUN`/`&&`/`;`
  prefixes; on `staging` lines 46 and 48 are the only `uv sync` commands (line 20 is a comment) and both carry
  `--extra otel`, so the test passes without touching the `Dockerfile`.
- [x] 1.2 `otel-collector.yaml`, exactly this content (validated with `otelcol-contrib validate` on
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
- [x] 1.3 `prometheus.yml`: `scrape_interval: 15s`, one job `otel-collector` with target `otel-collector:8889`.
- [x] 1.4 `compose.yaml` (Compose specification, no top-level `version`):
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
    `${MINTMORY_OBS_BIND:-127.0.0.1}:${MINTMORY_OBS_API_PORT:-8080}:8080`, the top-level named volume `mintmory-data`
    mounted at `/data` (the `Dockerfile` sets `MINTMORY_DB=/data/memories.db`, `VOLUME ["/data"]`, `USER app`, and its
    `CMD` runs uvicorn on `0.0.0.0:8080`; no `command` override), environment `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`,
    `MINTMORY_OTEL_ENABLED=true`, `OTEL_SERVICE_NAME=mintmory-api`, `depends_on: [otel-collector]`.
- [x] 1.5 `.env.example`: every `MINTMORY_OBS_*` variable above as an active `NAME=<compose default>` line under one
  comment line, plus the MintMory-side variables a developer may want as commented lines (`# OTEL_TRACES_SAMPLER=`,
  `# OTEL_TRACES_SAMPLER_ARG=`, `# OTEL_RESOURCE_ATTRIBUTES=`, `# OTEL_METRICS_EXPORTER=`).
- [x] 1.6 `README.md` in `deploy/observability/`: the quick start (`docker compose -f deploy/observability/compose.yaml up -d`,
  run any `mintmory` command or start `mintmory-mcp`, open `http://localhost:16686` and pick the service
  `mintmory-cli` or `mintmory-mcp`; Prometheus at `http://localhost:9090` with the query
  `histogram_quantile(0.95, sum by (le, phase) (rate(mintmory_search_latency_ms_bucket[5m])))`, which needs a
  long-running process such as the API or an MCP server: a one-shot CLI command exports once, under its own
  `service.instance.id`), the `api` profile
  (`--profile api up -d --build`), changing ports with a `.env` file, and stopping (`down`, `down -v`).

## 2. Doctor (`packages/cli/src/mintmory/cli/main.py`, `telemetry.py`)
- [x] 2.1 Tests for every scenario of "Telemetry status in doctor" (`cli_db` fixture of `test_cli.py`). Patch
  `telemetry._endpoint_reachable` (do not change `_DEFAULT_ENDPOINT`: the row must still name `http://localhost:4318`),
  remove `MINTMORY_OTEL_ENABLED` with `monkeypatch.delenv` where the scenario says unset (the root `conftest.py` sets
  `false`), and set `monkeypatch.setenv("COLUMNS", "200")` so Rich does not wrap the table.
- [x] 2.2 `telemetry.status(settings, default_service_name="mintmory-cli") -> dict[str, str]` with keys `mode`, `state`,
  `endpoint`, `reachable`, `service`, built from runtime's helpers (`add-telemetry-runtime` tasks 3.2 and 6.2):
  `_resolve_state(settings)` (`off` | `sdk missing` | `export` | `no collector`, mapped per the spec),
  `_traces_endpoint()` (`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` as is, else `OTEL_EXPORTER_OTLP_ENDPOINT` or
  `http://localhost:4318` plus `/v1/traces`), `_endpoint_reachable(url)` and `_service_name(settings,
  default_service_name)`. `endpoint` and `reachable`: inside `try/except ValueError`,
  `parts = urlsplit(_traces_endpoint())` and read `parts.port`; invalid (`ValueError`, or `parts.hostname` is None) gives `endpoint="<invalid>"`, `reachable="invalid"`;
  else `endpoint = urlunsplit((parts.scheme, parts.netloc.rpartition("@")[2], parts.path, "", ""))` (userinfo, query
  and fragment dropped; not rebuilt from `.hostname`, which lower-cases and drops IPv6 brackets) and `reachable` from
  `_endpoint_reachable(endpoint)`. The raw value is never returned. It initialises nothing and never reads
  `OTEL_EXPORTER_OTLP_HEADERS`.
- [x] 2.3 In `doctor`, after the `conversion` row: `table.add_row("telemetry", text)` where `text` is
  `", ".join(f"{k}={v}" for k, v in status(...).items())`, inside `try/except Exception as exc` giving
  `f"status unavailable ({type(exc).__name__})"`. The row never touches `healthy` (exit code unchanged).

## 3. Helm (`deploy/helm/mintmory/`)
- [x] 3.1 Tests for every scenario of "Helm telemetry settings" (template text; `values.yaml` and `values.schema.json`
  parsed). In the `helm template` test use `--set-string` (`--set` turns `samplerArg=0.1` into a number, which the
  string schema rejects; the guide uses `--set-string` too).
- [x] 3.2 `templates/configmap.yaml`: inside `{{- if .Values.otel.enabled }}` add `{{- if .Values.otel.sampler }}
  OTEL_TRACES_SAMPLER: {{ .Values.otel.sampler | quote }}{{- end }}` and the same for the other two; add `{{- else }}
  MINTMORY_OTEL_ENABLED: "false"`. `values.yaml`: the three keys with `""` and a comment each. `values.schema.json`:
  three `{"type": "string"}` properties under `otel`. Keep `otel.endpoint` and `otel.serviceName` as they are.

## 4. Guide
- [x] 4.1 Tests "Guide names every variable" and "Guide has its parts and links" (read the files and assert each name,
  heading, command and link).
- [x] 4.2 In `docs/OBSERVABILITY.md` section 4, replace the body of `4.5 Exporters & local viewing` with the guide,
  under `####` headings `Modes`, `Variables`, `Local stack`, `Finding a slow phase` and `Production`, and update the
  first bullet of `4.1 Principles` ("Off by default") to the `auto` mode. Keep `4.2`-`4.4`, `4.6` and the
  "Distributed tracing" subsection that parts 2 and 3 write; edit nothing else in section 4. The guide: a table of the
  variables with default and precedence; modes (`auto` exports when a collector is configured or
  answers on `localhost:4318`, `true`, `false`); the local stack; "finding a bottleneck" (Jaeger: search service and
  operation, sort by duration, open the slowest trace, read the `mintmory.search.*` and `gen_ai.chat` children;
  Prometheus: the phase query above); production (Helm values, sampling ratio, `OTEL_EXPORTER_OTLP_HEADERS` for an
  authenticated collector, kept in a Secret). Add a short "Observability" pointer in `README.md`.

## 5. Checks
- [ ] 5.1 Run `ruff check`, `ruff format --check`, `mypy packages` and the full test suite; coverage stays at or above
  80%.
