# Capability: observability (delta)

## ADDED Requirements

### Requirement: Every entry point initialises telemetry once
The CLI SHALL initialise telemetry in a Typer callback before any command except `serve` (uvicorn loads `mintmory.api.app:app`, whose lifespan initialises) and `mcp-serve` (it calls `mintmory.mcp.server.main()`). The API lifespan, `mintmory-mcp` and `mintmory-history-mcp` SHALL each call `init_telemetry` once with their default service name. After a successful init, later calls SHALL change nothing and return True; a call returning False SHALL leave no state.

#### Scenario: CLI command is traced
- **GIVEN** a test OTLP receiver in `OTEL_EXPORTER_OTLP_ENDPOINT` and `MINTMORY_OTEL_ENABLED=true`
- **WHEN** `mintmory add` runs through the Typer test runner and telemetry shuts down
- **THEN** a `mintmory.add_memory` span with `service.name=mintmory-cli` reaches the receiver

#### Scenario: History MCP server initialises telemetry
- **WHEN** `mintmory-history-mcp`'s `main()` starts
- **THEN** `init_telemetry` was called once, before the server runs, with `default_service_name="mintmory-history-mcp"`
