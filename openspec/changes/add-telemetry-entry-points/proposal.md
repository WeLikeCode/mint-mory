# Change: every MintMory entry point initialises and flushes telemetry (OpenTelemetry, part 1b)

## Why

`add-telemetry-runtime` makes telemetry safe to turn on, but on `staging` only the API lifespan and `mintmory-mcp` call
`init_telemetry`: the CLI (`ingest`, `index-tree`, `dream`, `history`) and `mintmory-history-mcp` emit nothing, every
entry point reports the same service name, and the API never flushes on shutdown.

## What changes

- The CLI initialises telemetry in a Typer callback (`mintmory-cli`), except `serve` and `mcp-serve`, which hand over to
  the API and MCP entry points.
- The API (`mintmory-api`), `mintmory-mcp` and `mintmory-history-mcp` pass their default service name; the API lifespan
  calls `shutdown_telemetry()` on stop.
- The `deployment` requirement "Telemetry activation at API startup" is modified: "OTel stays off by default" now
  means `auto` with no collector, and the API flushes with a bounded shutdown.

## Impact

`packages/cli/src/mintmory/cli/main.py`, `packages/api/src/mintmory/api/app.py`, `packages/mcp/src/mintmory/mcp/server.py`,
`history_server.py`, `packages/mcp/tests/test_telemetry_init.py`. Depends on `add-telemetry-runtime`
(`init_telemetry(..., default_service_name=...)`, `shutdown_telemetry`, the test seam).
