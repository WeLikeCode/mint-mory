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

See `specs/`: enablement modes (`auto` default), OTLP/HTTP by default with per-signal standard variables and console
on stderr, non-blocking export with failures logged once, a bounded `atexit` shutdown, the resource and sampler from
the standard environment, one init per entry point with MintMory's providers made global (FastMCP's tool spans then
reach the same exporters), a test seam, and the root `conftest.py` pinning the existing suite to
`MINTMORY_OTEL_ENABLED=false`. The `deployment` requirement "Telemetry activation at API startup" is modified
accordingly.

## Non-goals

OTLP logs, gRPC, database-driver spans, new dependencies, new spans or metrics (parts 2 and 3).

## Impact

`telemetry.py`, `config.py` (`OTelSettings`), the CLI callback, `api/app.py`, `mcp/server.py`, `history_server.py`,
the root `conftest.py`, and the existing telemetry tests named in the tasks. With no collector and no configuration
the shim stays a no-op, as today (only the default values of `enabled` and `exporter` change); with a collector on `localhost:4318`, MintMory exports without configuration.
