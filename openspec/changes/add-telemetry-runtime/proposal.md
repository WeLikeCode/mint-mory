# Change: a telemetry runtime that is on when a collector is there and never blocks MintMory (OpenTelemetry, part 1 of 4)

## Why

MintMory already has an OpenTelemetry seam (`packages/core/src/mintmory/core/telemetry.py`). It is
initialised by the API lifespan (`packages/api/src/mintmory/api/app.py`, `init_telemetry(settings.otel)`)
and by `mintmory-mcp` (`packages/mcp/src/mintmory/mcp/server.py`, `main()`). Spans exist for
`mintmory.add_memory`, `mintmory.search`, `mintmory.search_around`, the dream run and its steps, and
`gen_ai.chat`; metrics exist for LLM calls and dream durations. Measured on `staging`, the runtime has
these gaps:

1. **The CLI never initialises telemetry.** Nothing in `packages/cli` calls `init_telemetry`, so
   `mintmory ingest`, `index-tree`, `dream`, `history backfill` and `history sync` (the slow paths) emit
   nothing. `mintmory-history-mcp` (`packages/mcp/src/mintmory/mcp/history_server.py`) does not either.
2. **The console exporter corrupts the MCP stdio stream.** opentelemetry-sdk 1.42.1's
   `ConsoleSpanExporter` writes to `sys.stdout` by default (`opentelemetry/sdk/trace/export/__init__.py`,
   line 330). The default `MINTMORY_OTEL_EXPORTER` is `console`, so `MINTMORY_OTEL_ENABLED=true` makes
   `mintmory-mcp --transport stdio` write spans into its JSON-RPC stream. The module docstring says stderr.
3. **No collector means log noise and slow exits.** The OTLP/HTTP exporter retries a refused connection
   for up to 10 s (1 s, 2 s, 4 s back-off), logs a WARNING per retry and an ERROR per batch, every 5 s.
   The SDK's own `atexit` shutdown waits for that export, so a short CLI command can hang on exit.
4. **Off unless a flag is set.** A person who starts a collector on the standard local port sees nothing
   until they also set `MINTMORY_OTEL_ENABLED=true`.
5. **Thin resource.** Only `service.name` is set, and `MINTMORY_OTEL_SERVICE_NAME` (default `mintmory`)
   overrides the standard `OTEL_SERVICE_NAME`. Every entry point reports the same name.
6. **Tests cannot capture spans.** The global tracer provider can be set once per process and there is no
   way to inject an in-memory exporter, so span shape and parenting are untested.

## What changes

- `MINTMORY_OTEL_ENABLED` accepts `auto` (the new default), `true` and `false`. `auto` exports only when the
  SDK is installed and a collector is configured or answers on the default endpoint; otherwise MintMory runs
  the existing no-op shim and does not import the SDK. `OTEL_SDK_DISABLED=true` always wins.
- The default exporter becomes OTLP over HTTP/protobuf, to the endpoint the standard `OTEL_EXPORTER_OTLP_*`
  variables name (default `http://localhost:4318`). `OTEL_TRACES_EXPORTER` and `OTEL_METRICS_EXPORTER`
  (`otlp`, `console`, `none`) choose per signal. Console exporters write to stderr.
- Export runs in background threads with bounded queues and a short timeout (`MINTMORY_OTEL_EXPORT_TIMEOUT_S`,
  default 3 s). Export failures are logged once per signal until an export succeeds again.
- `shutdown_telemetry(timeout_s=2.0)` flushes with a hard time bound; `init_telemetry` registers it with
  `atexit`, and the SDK's own exit hooks are switched off.
- The resource carries `service.name` (standard precedence, then a per-entry-point default),
  `service.namespace`, `service.version` and `service.instance.id`, merged with `OTEL_RESOURCE_ATTRIBUTES`.
- Sampling and propagation follow the standard environment (`OTEL_TRACES_SAMPLER`, `OTEL_PROPAGATORS`).
- Every entry point initialises once: the CLI (a Typer callback), the API, `mintmory-mcp` and
  `mintmory-history-mcp`.
- MintMory's providers become the global OpenTelemetry providers on each successful init, so spans that libraries
  create through the global API (FastMCP 3.4.2 creates one per MCP tool call) go to the same exporters.
- A test seam: `init_telemetry(..., span_exporter=..., metric_reader=...)` and `reset_telemetry()`; the repository's
  `conftest.py` keeps the existing suite at `MINTMORY_OTEL_ENABLED=false`.
- The `deployment` capability's "Telemetry activation at API startup" requirement is modified: its scenario "OTel
  stays off by default" now means `auto` with no collector configured or answering, and the bounded shutdown is
  added.

## Non-goals

OTLP log export, the gRPC protocol, database-driver spans, new third-party dependencies (everything here uses
the packages already in the `otel` extra), and new spans or metrics (parts 2 and 3).

## Impact

- Specs: ADDED `observability` requirements; MODIFIED `deployment` "Telemetry activation at API startup".
- Code: `packages/core/src/mintmory/core/telemetry.py`, `packages/core/src/mintmory/core/config.py`
  (`OTelSettings`), `packages/cli/src/mintmory/cli/main.py` (callback), `packages/api/src/mintmory/api/app.py`
  (lifespan shutdown), `packages/mcp/src/mintmory/mcp/server.py` and `history_server.py` (`main`).
- Behaviour: with no collector and no configuration nothing changes. With a collector on `localhost:4318`,
  MintMory now exports without extra configuration.
- Tests: existing tests that assume "off by default" keep passing, because nothing listens on the default port
  in tests; the new tests point the probe at a local listener instead.
