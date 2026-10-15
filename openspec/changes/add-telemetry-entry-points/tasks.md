# Tasks: entry points (OpenTelemetry, part 1b)

Requires `add-telemetry-runtime`. No new dependencies. Each test first, failing; reuse
`packages/core/tests/otel_helpers.py` (`otlp_receiver()`).

## 1. Entry points
- [ ] 1.1 Tests for "Every entry point initialises telemetry once": the CLI through `typer.testing.CliRunner` with
  `otlp_receiver()` in `OTEL_EXPORTER_OTLP_ENDPOINT` and `MINTMORY_OTEL_ENABLED=true` (the `mintmory add` scenario);
  `mintmory serve` and `mintmory mcp-serve` do not call the CLI's init (patch `uvicorn.run` and the MCP `main`); the
  history MCP `main()` with `init_telemetry` and the server `run` patched; the API lifespan calls `shutdown_telemetry`.
- [ ] 1.2 `cli/main.py`: `@app.callback()` that calls `init_telemetry(load_settings().otel,
  default_service_name="mintmory-cli")` unless `ctx.invoked_subcommand` is `serve` or `mcp-serve` (for
  `history backfill` it is `history`, which is traced).
- [ ] 1.3 `api/app.py` lifespan: `init_telemetry(settings.otel, default_service_name="mintmory-api")`; after `yield`,
  `shutdown_telemetry()` before closing the store. `mcp/server.py` `main()`: `default_service_name="mintmory-mcp"`.
  `history_server.py`: import `init_telemetry` at module level (so tests can patch it) and call it with
  `"mintmory-history-mcp"` in `main()` before the server runs.
- [ ] 1.4 `packages/mcp/tests/test_telemetry_init.py`: its fake `_fake_init_telemetry(settings=None)` becomes
  `(settings=None, **kwargs)` and the test also asserts `kwargs["default_service_name"] == "mintmory-mcp"`.

## 2. Checks
- [ ] 2.1 `ruff check`, `ruff format --check`, `mypy packages`, full suite with coverage at or above 80%.
