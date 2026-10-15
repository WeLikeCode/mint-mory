# Tasks: telemetry runtime (OpenTelemetry, part 1 of 4)

No new dependencies (the `otel` extra has `opentelemetry-sdk` and the OTLP/HTTP exporter, 1.42.1). Import
`opentelemetry` only inside `init_telemetry` and what it enables. Log via `logging.getLogger("mintmory.telemetry")`,
never `structlog` (unconfigured structlog prints to stdout, the MCP stdio stream). Each test first, failing.

## 1. Test isolation and helpers
- [ ] 1.1 Root `conftest.py`: add `os.environ.setdefault("MINTMORY_OTEL_ENABLED", "false")` beside the busy-timeout
  line, and an autouse fixture calling `telemetry.reset_telemetry()` before and after each test.
- [ ] 1.2 `packages/core/tests/otel_helpers.py`: `otlp_receiver()` (`ThreadingHTTPServer` on `127.0.0.1:0`, daemon
  thread, 200 to every POST, records `(path, body)`); `decode_spans(body)` via `ExportTraceServiceRequest`
  (`opentelemetry.proto.collector.trace.v1.trace_service_pb2`) giving `(name, resource attributes)`; `closed_port()`.

## 2. Settings (`config.py`, `OTelSettings`)
- [ ] 2.1 Tests, then: `enabled: Literal["auto", "true", "false"] = "auto"` with a `field_validator(mode="before")`
  normalising booleans and case and mapping any other value to `"auto"` with one WARNING; `exporter = "otlp"`; `service_name: str | None = None`;
  `export_timeout_s: float = Field(default=3.0, gt=0)`.

## 3. Enablement and exporters (`telemetry.py`)
- [ ] 3.1 Tests for the scenarios of "Telemetry enablement modes" (patch `telemetry._endpoint_reachable`; run "Auto with
  no collector stays off" in a `sys.executable -c` subprocess, since pytest already imported the SDK) and "Exporter
  selection and endpoint resolution" (`capfd`).
- [ ] 3.2 `_DEFAULT_ENDPOINT = "http://localhost:4318"`; `_endpoint_reachable(url, timeout=0.1)` (`socket.create_connection`
  to its host and port, closed at once, False on `OSError`); `_resolve_state(settings)` returning `off` (`false`, or
  `OTEL_SDK_DISABLED` in "true"/"1"), `sdk missing` (`importlib.util.find_spec("opentelemetry.sdk")` is None), `export`
  (`true`; or `auto` with `OTEL_EXPORTER_OTLP_ENDPOINT`/`_TRACES_ENDPOINT`/`_METRICS_ENDPOINT` set, no probe; or `auto`
  and the default endpoint reachable) or `no collector`. Also `_traces_endpoint()` (`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`
  as is, else `OTEL_EXPORTER_OTLP_ENDPOINT` or `_DEFAULT_ENDPOINT` plus `/v1/traces`). Part 4 reuses both. `sdk missing` with an endpoint variable set:
  one WARNING with `pip install 'mintmory-core[otel]'`. Replace the existing `structlog` call.
- [ ] 3.3 Per signal: `OTEL_TRACES_EXPORTER` / `OTEL_METRICS_EXPORTER` (`otlp`, `console`, `none`), else
  `settings.exporter`; a list uses its first known item; an unknown value falls back to `settings.exporter`, and an
  `OTEL_EXPORTER_OTLP_PROTOCOL` other than `http/protobuf` keeps HTTP/protobuf, each with one WARNING (the SDK already
  falls back for a bad sampler). With an endpoint variable set, build `OTLPSpanExporter`/`OTLPMetricExporter` without `endpoint`
  (the SDK reads it and appends `/v1/traces`, `/v1/metrics`); otherwise pass `_DEFAULT_ENDPOINT` plus that path.
  `ConsoleSpanExporter(out=sys.stderr)`, `ConsoleMetricExporter(out=sys.stderr)` (both default to stdout).

## 4. Never block, never flood
- [ ] 4.1 Tests for "Export never blocks or floods..." with `closed_port()`, `MINTMORY_OTEL_EXPORT_TIMEOUT_S=0.2`,
  `OTEL_BSP_SCHEDULE_DELAY=50`, `caplog` at DEBUG.
- [ ] 4.2 `timeout=settings.export_timeout_s` on both OTLP exporters unless an `OTEL_EXPORTER_OTLP[_TRACES|_METRICS]_TIMEOUT`
  is set (the real bound; 1.42.1's `BatchSpanProcessor` ignores `export_timeout_millis`);
  `export_timeout_millis=int(export_timeout_s * 1000)` on `PeriodicExportingMetricReader`.
- [ ] 4.3 Guards as subclasses holding `self._inner`: `_GuardedSpanExporter(SpanExporter)`; `_GuardedMetricExporter(MetricExporter)`
  calling `super().__init__(preferred_temporality=inner._preferred_temporality, preferred_aggregation=inner._preferred_aggregation)`
  with `export(metrics_data, timeout_millis=10_000, **kwargs)` and `shutdown(timeout_millis=30_000, **kwargs)`. A caught
  exception or a FAILURE result is a failed export: return FAILURE, log once per failure streak (WARNING if an endpoint
  variable is set, else DEBUG), INFO on recovery.
- [ ] 4.4 On creating an OTLP exporter, save and set `logging.getLogger("opentelemetry.exporter.otlp.proto.http")` to
  `CRITICAL` (children inherit it; a parent filter would not apply to them); `reset_telemetry()` restores it.

## 5. Bounded shutdown
- [ ] 5.1 Tests for "Bounded flush on exit" (`otlp_receiver()`, `closed_port()`).
- [ ] 5.2 `shutdown_telemetry(timeout_s=2.0)`: providers' `shutdown()` in a daemon thread, `join(timeout_s)`, then
  disabled. Providers built with `shutdown_on_exit=False`; `atexit.register(shutdown_telemetry)` once per process.
## 6. Resource, sampling
- [ ] 6.1 Tests for "Resource identifies the process" and "Sampling...".
- [ ] 6.2 Explicit `Resource.create` attributes beat the environment, so compute them: parse `OTEL_RESOURCE_ATTRIBUTES`
  (`k=v`, values `urllib.parse.unquote`d); `service.name` computed by the spec's order (the parsed value ranks second), in a helper
  `_service_name(settings, default_service_name)` that part 4 reuses; defaults `service.namespace`,
  `service.version` (`importlib.metadata.version("mintmory-core")`, else `unknown`), `service.instance.id`
  (`uuid4().hex`); overlay the parsed keys; finally put the computed `service.name` (which already honours the parsed one). No `sampler` argument to `TracerProvider`.

## 7. Existing tests this change breaks
- [ ] 7.1 `packages/api/tests/test_health_and_otel.py`: the test at line 78 uses `OTelSettings(enabled="false")`; drop
  its comment that CI lacks the SDK (the gate installs `otel`); the exporter-type test (lines 101-141) checks
  `captured[-1]._inner` (the guard wraps the exporter) and calls `telemetry.reset_telemetry()` instead of its `_reset()`.
  The entry points' own wiring and the MCP test are `add-telemetry-entry-points`.

## 8. Test seam and global provider
- [ ] 8.1 Test for "Re-initialisation in one process".
- [ ] 8.2 Signature `init_telemetry(settings=None, *, default_service_name="mintmory", span_exporter=None,
  metric_reader=None) -> bool`. Module `_tracer_provider`/`_meter_provider` give `_tracer`/`_meter` and become global on every successful init.
  `reset_telemetry()` resets the API globals as OpenTelemetry's test utilities do (`from opentelemetry.util._once import Once`;
  `trace._TRACER_PROVIDER_SET_ONCE = Once()`; `trace._TRACER_PROVIDER = None`; same with
  `metrics._internal._METER_PROVIDER_SET_ONCE` / `_METER_PROVIDER`), calls `shutdown_telemetry(0.5)` and clears module
  state. Injected `span_exporter` via `SimpleSpanProcessor`; injected `metric_reader` replaces the periodic one; injection
  enables telemetry even when `_resolve_state` says `off` (tests run with the conftest's `false`).

## 9. Checks
- [ ] 9.1 Update the `telemetry.py` docstring; `ruff check`, `ruff format --check`, `mypy packages`, full suite with
  coverage at or above 80%.
