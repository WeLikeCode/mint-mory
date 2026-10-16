# Tasks: telemetry runtime (OpenTelemetry, part 1 of 4)

No new dependencies (`uv.lock` resolves the `otel` extra to SDK and OTLP/HTTP exporter 1.42.1; CI installs it,
`ci.yml` runs `uv sync --frozen ... --extra otel`; SDK tests `pytest.importorskip("opentelemetry.sdk")`). Import `opentelemetry`
only inside `init_telemetry` and what it enables. Log via `logging.getLogger("mintmory.telemetry")` (`config.py` too),
never `structlog` (unconfigured, it prints to stdout, the MCP stdio stream). Each test first, failing.

## 1. Root `conftest.py`
- [x] 1.1 `os.environ.setdefault("MINTMORY_OTEL_ENABLED", "false")` beside the busy-timeout line; autouse reset fixture.
- [x] 1.2 Fixtures of the spec: `otlp_receiver` is a `ThreadingHTTPServer` in a daemon thread, shut down at teardown;
  `spans()` decodes with `trace_service_pb2.ExportTraceServiceRequest`, imported inside the method.

## 2. Settings (`config.py`, `OTelSettings`)
- [x] 2.1 `enabled: Literal["auto", "true", "false"] = "auto"`, `exporter: str = "otlp"`, `service_name: str | None = None`,
  `export_timeout_s: float = 3.0`; fallbacks as `field_validator(mode="before")`, no `gt=0`. `init_telemetry` is the
  only reader of `OTelSettings.enabled` on `staging`, so no caller breaks on the string.

## 3. Enablement and exporters (`telemetry.py`)
- [x] 3.1 Tests for "Telemetry enablement modes" (run "Auto with no collector stays off" in a `sys.executable -c`
  subprocess, since pytest already imported the SDK) and "Exporter selection..." (`capfd`).
- [x] 3.2 Helpers part 4 reuses: `_DEFAULT_ENDPOINT = "http://localhost:4318"`; `_sdk_available()`
  (`importlib.util.find_spec("opentelemetry.sdk") is not None`); `_endpoint_reachable(url, timeout=0.1)`
  (`socket.create_connection`, port 443 for `https` else 80 when absent, closed at once, False on `OSError` or
  `ValueError`); `_resolve_state(settings)` -> `off` | `sdk missing` | `export` | `no collector`; `_traces_endpoint()`
  (`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` as is, else `OTEL_EXPORTER_OTLP_ENDPOINT` or `_DEFAULT_ENDPOINT` plus
  `/v1/traces`). Replace the `structlog` call.
- [x] 3.3 With an endpoint variable set, build the OTLP exporters without `endpoint` (the SDK appends the path),
  else pass `_DEFAULT_ENDPOINT` plus `/v1/traces` or `/v1/metrics`. Console exporters with `out=sys.stderr`.

## 4. Never block, never flood, never raise
- [x] 4.1 Tests for "Export never blocks or floods...", both "fall back" requirements and "Telemetry init never raises".
- [x] 4.2 `timeout=settings.export_timeout_s` on both OTLP exporters unless a standard timeout variable is set
  (1.42.1's `BatchSpanProcessor` ignores `export_timeout_millis`); `export_timeout_millis` on the periodic reader.
- [x] 4.3 Guards keep `self._inner`. `_GuardedMetricExporter(MetricExporter)` calls `super().__init__(preferred_temporality=
  inner._preferred_temporality, preferred_aggregation=inner._preferred_aggregation)`; `export(metrics_data,
  timeout_millis=10_000, **kwargs)`, `shutdown(timeout_millis=30_000, **kwargs)`.
- [x] 4.4 Before building an OTLP exporter save the `opentelemetry.exporter.otlp.proto.http` logger level (if none is
  saved) and set CRITICAL (children inherit it; a filter on the parent would not reach them).
- [x] 4.5 `try/except Exception` around everything after the arguments are read; on failure call `_teardown(2.0)` (5.2)
  under the held lock, log, return False.

## 4b. Export scrubber
- [x] 4b.1 Test "A library's exception is scrubbed", plus a MintMory span through `telemetry.span`.
- [x] 4b.2 `_Scrubbing(SpanExporter)` outermost on every span exporter (OTLP behind the guard, console, injected);
  `export` rebuilds each span as `ReadableSpan(...)` with the same fields, `exception` events reduced to
  `exception.type` and an ERROR status without description.

## 5. Shutdown, error helper
- [x] 5.1 Tests for "Bounded flush on exit" and "One error-marking helper".
- [x] 5.2 `_teardown(timeout_s)`, called with the lock held: providers' `shutdown()` in `threading.Thread(name=
  "mintmory-telemetry-shutdown", daemon=True)`, `join(timeout_s)`; clear module state and `_instruments`;
  `_release_globals()` only if set; restore the logger level. `shutdown_telemetry` takes the one `threading.Lock`
  (not reentrant) and calls it. `_atexit_registered`: set after `atexit.register(shutdown_telemetry)` (via `import
  atexit`, so tests patch it) on a successful init; `reset_telemetry()` = `shutdown_telemetry(0.5)`,
  `atexit.unregister(shutdown_telemetry)`, flag False.
- [ ] 5.3 `mark_error`: return on `_NoopSpan`; else `set_status(Status(StatusCode.ERROR))` and
  `set_attribute("error.type", error_type)` inside `try/except Exception`.

## 6. Resource, sampling
- [ ] 6.1 Tests for "Resource identifies the process" and "Sampling...".
- [ ] 6.2 Explicit `Resource.create` attributes beat the environment, so compute them: parse `OTEL_RESOURCE_ATTRIBUTES`
  (`k=v`, values `urllib.parse.unquote`d); `_service_name(settings, default_service_name)` (part 4 reuses it);
  `service.version` from `importlib.metadata.version("mintmory-core")`, else `unknown`; `service.instance.id` =
  `uuid4().hex`; overlay the parsed keys, then the computed `service.name`. No `sampler` argument to `TracerProvider`.

## 7. Existing tests this change affects
- [ ] 7.1 `packages/api/tests/test_health_and_otel.py`: `test_telemetry_default_off_returns_false` (line 78) uses
  `OTelSettings(enabled="false")` (the new `auto` default would probe); drop the comment that CI lacks the SDK; the
  exporter-type test (lines 101-141) checks `captured[-1]._inner` and calls `telemetry.reset_telemetry()` instead of
  its `_reset()`. `OTelSettings(enabled=True, ...)` keeps working (normalised to `"true"`).
- [ ] 7.2 `packages/mcp/tests/test_telemetry_init.py` passes unchanged in its calls (`server.main()` still calls
  `init_telemetry(load_settings().otel)` until part 1b; its fake takes `settings`). In
  `test_main_telemetry_default_off_is_safe`, which deletes `MINTMORY_OTEL_ENABLED`, patch `telemetry._endpoint_reachable`
  to return False so `auto` never probes.

## 8. Test seam and global provider
- [ ] 8.1 Tests for "Telemetry test seam" and "Global providers and repeated init".
- [ ] 8.2 Module `_tracer_provider`/`_meter_provider` give `_tracer`/`_meter` and become global on success.
  `_release_globals()` resets the API globals as OpenTelemetry's test utilities do (`trace._TRACER_PROVIDER_SET_ONCE =
  Once()`, `trace._TRACER_PROVIDER = None`, same for `metrics._internal._METER_PROVIDER_SET_ONCE` / `_METER_PROVIDER`).
  Injected exporter via `SimpleSpanProcessor`; injected reader replaces the periodic one.

## 9. Checks
- [ ] 9.1 Update the `telemetry.py` docstring; `ruff check`, `ruff format --check`, `mypy packages`, full suite with
  coverage at or above 80%.
