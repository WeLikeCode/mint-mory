# Capability: observability (delta)

## Purpose

MintMory's observability: OpenTelemetry traces and metrics from every entry point (CLI, REST API, MCP servers), safe and silent when no collector runs, distributed across HTTP, MCP and outbound LLM calls, with a local collector, Jaeger and Prometheus stack for development.

## ADDED Requirements

### Requirement: Every entry point initialises telemetry once
The CLI SHALL initialise telemetry in a Typer callback with `telemetry.init_telemetry(default_service_name="mintmory-cli")` before any command except `serve` (uvicorn loads `mintmory.api.app:app`, whose lifespan initialises) and `mcp-serve` (it calls `mintmory.mcp.server.main()`). `mintmory-mcp` and `mintmory-history-mcp` SHALL call `init_telemetry(default_service_name="mintmory-mcp")` / `"mintmory-history-mcp"` in `main()` before the server runs, and the API lifespan `init_telemetry(settings.otel, default_service_name="mintmory-api")`. The CLI callback and both `main()` SHALL pass no settings and SHALL NOT call `load_settings()` for telemetry, and none of the entry points wraps the call: per `add-telemetry-runtime` ("Telemetry init never raises"), `init_telemetry` builds `OTelSettings()` itself, catches every init failure, logs `telemetry disabled: init failed (<class>)` and returns False, so telemetry can never stop a command or a server. A repeated init changes nothing (runtime).

#### Scenario: CLI command is traced
- **GIVEN** the root fixture `otlp_receiver`, `OTEL_EXPORTER_OTLP_ENDPOINT=otlp_receiver.endpoint`, `MINTMORY_OTEL_ENABLED=true`, and the `cli_db` fixture of `packages/cli/tests/test_cli.py` (`MINTMORY_DB` in a temp folder; the default hashing embedder, no network, no LLM)
- **WHEN** `mintmory add "hello"` runs through `CliRunner` (its store call is `@telemetry.traced("mintmory.add_memory")`) and the test then calls `telemetry.shutdown_telemetry()` (the `atexit` hook does not run inside `CliRunner`)
- **THEN** `otlp_receiver.spans()` contains `mintmory.add_memory` with `service.name=mintmory-cli`

#### Scenario: A telemetry failure does not stop a command
- **GIVEN** the `cli_db` fixture, `MINTMORY_OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_TIMEOUT=abc` (the OTLP exporter constructor raises `ValueError`)
- **WHEN** `mintmory add "hello"` runs through `CliRunner`
- **THEN** it exits 0 and prints the new memory id, and `mintmory.telemetry` logged one WARNING containing `telemetry disabled: init failed (ValueError)`

#### Scenario: An invalid unrelated setting does not break help
- **GIVEN** `MINTMORY_SUMMARY_CONCURRENCY=0` (`load_settings()` raises `ValidationError`)
- **WHEN** `mintmory add --help` runs through `CliRunner` (Click runs the group callback before the subcommand's `--help`)
- **THEN** it exits 0 and its output contains `Usage`

#### Scenario: serve and mcp-serve leave init to their servers
- **GIVEN** `mintmory.core.telemetry.init_telemetry` replaced by a recorder, `uvicorn.run` and `mintmory.mcp.server.main` patched to return at once
- **WHEN** `mintmory serve` and `mintmory mcp-serve` run through `CliRunner`
- **THEN** both exit 0 and the recorder saw no call

#### Scenario: Stdio MCP servers initialise telemetry
- **GIVEN** `init_telemetry` patched with a recorder in `mintmory.mcp.server` and in `mintmory.mcp.history_server`, each module's `mcp.run` patched, `sys.argv` set to the program name, `MINTMORY_HISTORY_DB` at a temp file (the history server's working-DB guard)
- **WHEN** each `main()` runs
- **THEN** each recorder saw exactly one call, before `run`, with no positional argument and `default_service_name` `mintmory-mcp` and `mintmory-history-mcp` respectively
