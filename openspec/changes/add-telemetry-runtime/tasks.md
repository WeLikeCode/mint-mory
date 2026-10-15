# Tasks: telemetry runtime (OpenTelemetry, part 1 of 4)

Use only the packages already in the `otel` extra (`opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`,
both 1.42.1 in `uv.lock`). Do not add dependencies. Keep the zero-import rule: `opentelemetry` is imported only
inside `init_telemetry` and the functions it enables. Log through `logging.getLogger("mintmory.telemetry")`
(standard library), never `structlog`: MintMory does not configure structlog, whose default logger prints to stdout,
which is the MCP stdio protocol stream. Write each test first and see it fail. The facts quoted below were checked
against the installed packages.

## 1. Test isolation and helpers
- [ ] 1.1 In the repository-root `conftest.py`, next to the existing
  `os.environ.setdefault("MINTMORY_SQLITE_BUSY_TIMEOUT_MS", "100")`, add
  `os.environ.setdefault("MINTMORY_OTEL_ENABLED", "false")` (so the existing suite never probes `localhost:4318` or
  exports to a developer's local collector) and an autouse fixture that calls `telemetry.reset_telemetry()` before
  and after each test. Tests of `auto` mode use `monkeypatch.delenv("MINTMORY_OTEL_ENABLED")`.
- [ ] 1.2 Add `packages/core/tests/otel_helpers.py` with: a context manager `otlp_receiver()` that starts a
  `http.server.ThreadingHTTPServer` on `127.0.0.1:0` in a daemon thread, answers every POST with 200 and an empty
  body, and records `(path, body_bytes)`; `decode_spans(body)` that parses the body with
  `opentelemetry.proto.collector.trace.v1.trace_service_pb2.ExportTraceServiceRequest` and returns a list of
  `(span name, resource attributes dict)`; and `closed_port()` that binds a socket to `127.0.0.1:0`, reads the port
  and closes it. Tests that need the SDK use `pytest.importorskip("opentelemetry.sdk")`.

## 2. Settings (`packages/core/src/mintmory/core/config.py`, `OTelSettings`)
- [ ] 2.1 Tests: `enabled` accepts `auto`, `true`, `false` (any case, and booleans) and defaults to `auto`; `exporter`
  defaults to `otlp`; `service_name` defaults to `None`; `export_timeout_s` defaults to 3.0 and must be > 0.
- [ ] 2.2 Change `enabled` to `Literal["auto", "true", "false"]` with a `field_validator(mode="before")` that maps
  booleans and any case to those strings; `exporter` default `"otlp"`; `service_name: str | None = None`; add
  `export_timeout_s: float = Field(default=3.0, gt=0)`.

## 3. Enablement and exporters (`packages/core/src/mintmory/core/telemetry.py`)
- [ ] 3.1 Tests for every scenario of "Telemetry enablement modes" and "Exporter selection and endpoint resolution".
  Patch `telemetry._endpoint_reachable` to return True or False for the probe cases. Test "Auto with no collector
  stays off" in a subprocess (`subprocess.run([sys.executable, "-c", ...])` with `MINTMORY_OTEL_ENABLED` removed from
  the environment and `_endpoint_reachable` patched inside the script), because pytest has already imported the SDK
  in-process. Use `capfd` for the stdout/stderr scenario.
- [ ] 3.2 Add `_DEFAULT_ENDPOINT = "http://localhost:4318"`, `_endpoint_reachable(url: str, timeout: float = 0.1) ->
  bool` (`socket.create_connection((host, port), timeout)` on the URL's host and port, closed at once; False on any
  `OSError`), and `_resolve_state(settings) -> str` returning `"off"`, `"export"`, `"no collector"` or
  `"sdk missing"`: `false` or `OTEL_SDK_DISABLED` in ("true", "1") -> `off`; otherwise the SDK must import
  (`importlib.util.find_spec("opentelemetry.sdk")`, which does not import it) or the state is `sdk missing`; `true`
  -> `export`; `auto` -> `export` when any of `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`,
  `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` is set (no probe), else `export` when
  `_endpoint_reachable(_DEFAULT_ENDPOINT)` is True, else `no collector`. Part 4 reuses this function. When the state
  is `sdk missing` and an endpoint variable is set, log one WARNING with the hint `pip install 'mintmory-core[otel]'`;
  otherwise log at DEBUG. Replace the existing `structlog` call in `init_telemetry`.
- [ ] 3.3 Per signal, read `OTEL_TRACES_EXPORTER` / `OTEL_METRICS_EXPORTER` (`otlp`, `console`, `none`), falling back to
  `settings.exporter`. Create `OTLPSpanExporter(...)` / `OTLPMetricExporter(...)` without an endpoint argument when an
  endpoint variable is set (the SDK reads the standard variables and appends `/v1/traces` and `/v1/metrics`; a
  per-signal variable is used as is); otherwise pass `endpoint=_DEFAULT_ENDPOINT + "/v1/traces"` (and
  `/v1/metrics`). Create `ConsoleSpanExporter(out=sys.stderr)` and `ConsoleMetricExporter(out=sys.stderr)` (both
  default to stdout). `none` creates nothing for that signal.

## 4. Never block, never flood
- [ ] 4.1 Tests for "Export never blocks or floods when the collector is absent", with `closed_port()`,
  `MINTMORY_OTEL_EXPORT_TIMEOUT_S=0.2` (a failed export then ends at once, without retrying for seconds), a small
  `OTEL_BSP_SCHEDULE_DELAY` (for example 50 ms) and `caplog` at DEBUG.
- [ ] 4.2 Pass `timeout=settings.export_timeout_s` to both OTLP exporters unless `OTEL_EXPORTER_OTLP_TIMEOUT`,
  `OTEL_EXPORTER_OTLP_TRACES_TIMEOUT` or `OTEL_EXPORTER_OTLP_METRICS_TIMEOUT` is set. This `timeout=` is the real
  bound: in 1.42.1 `BatchSpanProcessor` stores `export_timeout_millis` but does not use it. Also pass
  `export_timeout_millis=int(settings.export_timeout_s * 1000)` to `PeriodicExportingMetricReader`.
- [ ] 4.3 Wrap each OTLP exporter in a guard that is a real subclass:
  - `_GuardedSpanExporter(SpanExporter)` with `export(self, spans)`, `force_flush(self, timeout_millis=30000)` and
    `shutdown(self)` delegating to the inner exporter;
  - `_GuardedMetricExporter(MetricExporter)` whose `__init__` calls
    `super().__init__(preferred_temporality=inner._preferred_temporality,
    preferred_aggregation=inner._preferred_aggregation)` (the reader reads these two as dict attributes), with
    `export(self, metrics_data, timeout_millis=10_000, **kwargs)`, `force_flush(self, timeout_millis=10_000)` and
    `shutdown(self, timeout_millis=30_000, **kwargs)` (the reader passes `timeout=`).
  Each guard catches every exception from the inner `export` and returns FAILURE; an exception or a FAILURE result
  counts as a failed export. Log one record per failure streak (WARNING when an endpoint variable is set, else DEBUG),
  and one INFO when an export succeeds after a failure. Keep the inner exporter as `self._inner`.
- [ ] 4.4 When an OTLP exporter is created, remember the level of
  `logging.getLogger("opentelemetry.exporter.otlp.proto.http")` and set it to `logging.CRITICAL`; its child loggers
  (`...trace_exporter`, `...metric_exporter`), which log the SDK's retry and failure messages, inherit it. (A
  `logging.Filter` on a parent logger does not apply to records of its children, so a filter does not work.)
  `reset_telemetry()` restores the level.

## 5. Bounded shutdown
- [ ] 5.1 Tests for "Bounded flush on exit" (both scenarios), using `otlp_receiver()` and `closed_port()`.
- [ ] 5.2 Add `shutdown_telemetry(timeout_s: float = 2.0) -> None`: if not enabled return; run
  `tracer_provider.shutdown()` and `meter_provider.shutdown()` in a daemon `threading.Thread` and `join(timeout_s)`;
  mark the module disabled either way. Create `TracerProvider(..., shutdown_on_exit=False)` and
  `MeterProvider(..., shutdown_on_exit=False)` (without this the SDK's own exit hook waits 7 to 8 seconds per provider
  when no collector answers); register `shutdown_telemetry` with `atexit` once per process.
- [ ] 5.3 In `packages/api/src/mintmory/api/app.py` `lifespan`, call `shutdown_telemetry()` after `yield`, before
  closing the store.

## 6. Resource, sampling, propagation
- [ ] 6.1 Tests for "Resource identifies the process" and "Sampling and propagation follow the OpenTelemetry
  environment".
- [ ] 6.2 An explicit attribute passed to `Resource.create` beats both `OTEL_SERVICE_NAME` and
  `OTEL_RESOURCE_ATTRIBUTES`, so compute the attributes in Python: parse `OTEL_RESOURCE_ATTRIBUTES` (comma-separated
  `key=value`, values percent-decoded with `urllib.parse.unquote`); `service.name` = `OTEL_SERVICE_NAME`, else the
  parsed `service.name`, else `settings.service_name`, else `default_service_name`; start from the defaults
  `service.namespace` = `mintmory`, `service.version` = `importlib.metadata.version("mintmory-core")` (`"unknown"`
  when not installed), `service.instance.id` = `uuid.uuid4().hex`; overlay the parsed attributes; set `service.name`;
  pass the result to `Resource.create`. Construct `TracerProvider` without a `sampler` argument (it reads
  `OTEL_TRACES_SAMPLER` and `OTEL_TRACES_SAMPLER_ARG`); do not override the global propagator.

## 7. Entry points
- [ ] 7.1 Tests for "Every entry point initialises telemetry once": the CLI through `typer.testing.CliRunner` with
  `otlp_receiver()` and `MINTMORY_OTEL_ENABLED=true`; the history MCP `main()` with `init_telemetry` and the server
  `run` monkeypatched, like `packages/mcp/tests/test_telemetry_init.py`.
- [ ] 7.2 Update the existing tests that the new signature and defaults break, without weakening what they check:
  - `packages/mcp/tests/test_telemetry_init.py`: the fake `_fake_init_telemetry(settings=None)` becomes
    `(settings=None, **kwargs)` and the test asserts `kwargs["default_service_name"] == "mintmory-mcp"`.
  - `packages/api/tests/test_health_and_otel.py`: the test at line 78 uses `OTelSettings(enabled="false")` (the
    default is now `auto`); the comment saying the SDK is not installed in CI is wrong (the gate installs the `otel`
    extra) and goes; the exporter-type test (lines 101-141) unwraps the guard (`captured[-1]._inner`) and replaces its
    manual `_reset()` with `telemetry.reset_telemetry()`.
- [ ] 7.3 Signature: `init_telemetry(settings=None, *, default_service_name="mintmory", span_exporter=None,
  metric_reader=None) -> bool`. CLI: add `@app.callback()` in `packages/cli/src/mintmory/cli/main.py` that calls
  `init_telemetry(load_settings().otel, default_service_name="mintmory-cli")` unless `ctx.invoked_subcommand` is
  `serve` or `mcp-serve` (for `history backfill` it is `history`, which is traced). API:
  `default_service_name="mintmory-api"`. MCP: `"mintmory-mcp"` in `server.py` `main()`; in `history_server.py` import
  `init_telemetry` at module level (so tests can patch it) and call it with `"mintmory-history-mcp"` in `main()` before
  the server runs.

## 8. Test seam and global provider
- [ ] 8.1 Test for "Re-initialisation in one process".
- [ ] 8.2 Keep module-level `_tracer_provider` and `_meter_provider`; get `_tracer` and `_meter` from them. On every
  successful init, make them the global providers. The API refuses a second `set_tracer_provider`, so
  `reset_telemetry()` (test use) also resets the API globals, as OpenTelemetry's own test utilities do:
  `from opentelemetry.util._once import Once`; `trace._TRACER_PROVIDER_SET_ONCE = Once()`;
  `trace._TRACER_PROVIDER = None`; `metrics._internal._METER_PROVIDER_SET_ONCE = Once()`;
  `metrics._internal._METER_PROVIDER = None`. An injected `span_exporter` is added through `SimpleSpanProcessor`; an
  injected `metric_reader` replaces the periodic reader; either one enables telemetry when the SDK imports, whatever
  `settings.enabled` says. `reset_telemetry()` calls `shutdown_telemetry(0.5)` and clears `_enabled`, `_tracer`,
  `_meter`, `_instruments`, the providers and the `atexit` flag's effect on state (registration itself stays). A call
  of `init_telemetry` that returns False leaves no state behind; after a successful init, later calls return True and
  change nothing.

## 9. Documentation and checks
- [ ] 9.1 Update the module docstring of `telemetry.py` (modes, stderr, bounded shutdown, global provider) and the
  `OTelSettings` comments. Run `ruff check`, `ruff format --check`, `mypy packages` and the full test suite; coverage
  stays at or above 80%.
