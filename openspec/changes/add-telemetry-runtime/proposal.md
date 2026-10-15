# Change: a telemetry runtime that is on when a collector is there and never blocks MintMory (OpenTelemetry, part 1 of 4)

## Why

`packages/core/src/mintmory/core/telemetry.py` is initialised by the API lifespan and `mintmory-mcp`; spans exist
for add, search, search-around, dream and `gen_ai.chat`. Gaps on `staging`:

1. The CLI and `mintmory-history-mcp` never call `init_telemetry`, so the slow paths emit nothing.
2. The default exporter is `console`, and opentelemetry-sdk 1.42.1's console exporters write to stdout: enabling
   telemetry writes spans into the `mintmory-mcp` stdio JSON-RPC stream.
3. With no collector the OTLP exporter retries for 10 s, logs a WARNING per retry and an ERROR per batch, and the
   SDK's exit hook waits 7-8 s per provider, so short CLI commands hang on exit.
4. It is off unless `MINTMORY_OTEL_ENABLED=true`, even when a collector runs on the standard port.
5. The resource has only `service.name`, and `MINTMORY_OTEL_SERVICE_NAME` overrides the standard `OTEL_SERVICE_NAME`.
6. Tests cannot capture spans (no in-memory seam; the global provider is set once per process).

## What changes

- `MINTMORY_OTEL_ENABLED` = `auto` (new default) | `true` | `false`. `auto` exports only when the SDK is installed and
  an OTLP endpoint is configured or answers on `localhost:4318`; otherwise the no-op shim runs and the SDK is not
  imported. `OTEL_SDK_DISABLED=true` always wins.
- Default exporter OTLP/HTTP to the standard `OTEL_EXPORTER_OTLP_*` endpoint; `OTEL_TRACES_EXPORTER` /
  `OTEL_METRICS_EXPORTER` per signal; console exporters on stderr.
- Background export with a 3 s timeout (`MINTMORY_OTEL_EXPORT_TIMEOUT_S`), failures logged once per streak, a bounded
  `shutdown_telemetry()` registered with `atexit`.
- Resource: standard `service.name` precedence, then a per-entry-point default; `service.namespace`,
  `service.version`, `service.instance.id`; `OTEL_RESOURCE_ATTRIBUTES` merged. Sampler and propagators from the
  standard environment.
- Every entry point initialises once. MintMory's providers become the global ones, so FastMCP's own tool-call spans
  reach the same exporters.
- Test seam (`span_exporter=`, `metric_reader=`, `reset_telemetry()`); the root `conftest.py` keeps the existing
  suite at `MINTMORY_OTEL_ENABLED=false`.
- `deployment` "Telemetry activation at API startup" is modified: "OTel stays off by default" now means `auto` with no
  collector, and the API flushes with a bounded shutdown.

## Non-goals

OTLP logs, gRPC, database-driver spans, new dependencies, new spans or metrics (parts 2 and 3).

## Impact

`telemetry.py`, `config.py` (`OTelSettings`), the CLI callback, `api/app.py`, `mcp/server.py`, `history_server.py`,
the root `conftest.py`, and the existing telemetry tests named in the tasks. With no collector and no configuration
nothing changes; with a collector on `localhost:4318`, MintMory exports without configuration.
