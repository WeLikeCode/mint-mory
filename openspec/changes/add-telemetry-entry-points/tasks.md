# Tasks: entry points (OpenTelemetry, part 1b)

Requires `add-telemetry-runtime` (`init_telemetry(settings=None, *, default_service_name=...)` that never raises,
`shutdown_telemetry`, the root `conftest.py` fixtures `otlp_receiver` and the autouse reset). No new dependencies. Each
test first, failing. Tests use `otlp_receiver` by fixture name (no helper import).

## 1. Entry points
- [x] 1.1 Tests in `packages/cli/tests/test_telemetry_cli.py` for the CLI scenarios of "Every entry point initialises
  telemetry once" (reuse the `cli_db` fixture pattern of `test_cli.py`: `monkeypatch.setenv("MINTMORY_DB", ...)`).
- [x] 1.2 `cli/main.py`: add `from mintmory.core import telemetry` at module level (tests patch
  `mintmory.core.telemetry.init_telemetry`) and an `@app.callback()` taking `ctx: typer.Context` (no docstring, so
  `mintmory --help` keeps the `Typer(help=...)` text) that calls `telemetry.init_telemetry(default_service_name="mintmory-cli")`
  unless `ctx.invoked_subcommand` is `serve` or `mcp-serve` (for `history backfill` it is `history`, traced). `app` has no
  callback today. Click calls it only when a subcommand is given (not for bare `mintmory` or `mintmory --help`), and
  also for `mintmory <cmd> --help`, where `auto` may probe once (100 ms).
- [x] 1.3 `api/app.py` lifespan: `init_telemetry(settings.otel, default_service_name="mintmory-api")`; import
  `shutdown_telemetry` beside `init_telemetry` at module level and call it after `yield`, before `_store.close()`.
- [ ] 1.4 `mcp/server.py` `main()`: replace `init_telemetry(load_settings().otel)` with
  `init_telemetry(default_service_name="mintmory-mcp")`. `history_server.py`: import `init_telemetry` at module level and
  call `init_telemetry(default_service_name="mintmory-history-mcp")` in `main()` after the `_assert_not_working_db`
  guard, before `mcp.run`. No `try/except` around any call (runtime's contract).
- [ ] 1.5 `packages/mcp/tests/test_telemetry_init.py`: `_fake_init_telemetry(settings=None)` becomes
  `(settings=None, **kwargs)`; assert `settings is None` and `kwargs["default_service_name"] == "mintmory-mcp"`. Add the
  history server test there. Keep runtime's `_endpoint_reachable` patch in `test_main_telemetry_default_off_is_safe`.
- [ ] 1.6 Deployment scenarios in `packages/api/tests/test_health_and_otel.py`. The file's other tests are unaffected:
  its `client` fixture never initialises telemetry (the conftest default is `false`), so the new
  `shutdown_telemetry()` at lifespan exit is a no-op there, and no test reads telemetry state after the lifespan ends;
  `test_routes.py` reads no telemetry state.

## 2. Checks
- [ ] 2.1 `ruff check`, `ruff format --check`, `mypy packages`, full suite with coverage at or above 80%.
