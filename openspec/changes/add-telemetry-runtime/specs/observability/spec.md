# Capability: observability (delta)

## Purpose

MintMory's observability: OpenTelemetry traces and metrics from every entry point (CLI, REST API, MCP servers), safe and silent when no collector runs, distributed across HTTP, MCP and outbound LLM calls, with a local collector, Jaeger and Prometheus stack for development.

## ADDED Requirements

### Requirement: Telemetry enablement modes
`MINTMORY_OTEL_ENABLED` SHALL accept `auto` (default), `true`, `false`. `false`, or `OTEL_SDK_DISABLED=true` (any case), SHALL keep the no-op shim; `true` SHALL export when the SDK is installed; `auto` SHALL export only when the SDK is installed and `OTEL_EXPORTER_OTLP_ENDPOINT`, `_TRACES_ENDPOINT` or `_METRICS_ENDPOINT` is set or a TCP connection to the default endpoint succeeds within 100 ms, else stay no-op without importing `opentelemetry.sdk`. Without the SDK, init SHALL return False and log one WARNING on `mintmory.telemetry` containing `mintmory-core[otel]` when the mode is `true` or an endpoint variable is set, none otherwise.

#### Scenario: Auto with no collector stays off
- **GIVEN** no `MINTMORY_OTEL_ENABLED`, no endpoint variable, `telemetry._endpoint_reachable` patched to return False
- **WHEN** `init_telemetry` runs in a fresh Python process
- **THEN** it returns False and `opentelemetry.sdk` is not in `sys.modules`

#### Scenario: Auto turns on with a collector
- **GIVEN** no `MINTMORY_OTEL_ENABLED`, and either `_endpoint_reachable` patched to True or `OTEL_EXPORTER_OTLP_ENDPOINT` set
- **WHEN** `init_telemetry` runs
- **THEN** it returns True, and with the variable set `_endpoint_reachable` is not called

#### Scenario: Explicit off wins
- **GIVEN** `MINTMORY_OTEL_ENABLED=false`, or `OTEL_SDK_DISABLED=TRUE` with `MINTMORY_OTEL_ENABLED=true`
- **WHEN** `init_telemetry` runs without injection
- **THEN** it returns False

#### Scenario: SDK missing
- **GIVEN** `telemetry._sdk_available` patched to return False
- **WHEN** `init_telemetry` runs with (a) `MINTMORY_OTEL_ENABLED=true`, no endpoint variable; (b) `auto` and `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` set; (c) `auto`, no endpoint variable
- **THEN** each returns False; (a) and (b) log exactly one WARNING containing `mintmory-core[otel]`, (c) none

### Requirement: Exporter selection and endpoint resolution
The default exporter SHALL be OTLP over HTTP/protobuf to the endpoint of the standard `OTEL_EXPORTER_OTLP_*ENDPOINT` variables, default `http://localhost:4318`. `OTEL_TRACES_EXPORTER` and `OTEL_METRICS_EXPORTER` (`otlp`, `console`, `none`) SHALL override `MINTMORY_OTEL_EXPORTER` per signal. A signal set to `none` SHALL get no provider: `telemetry._tracer` (or `_meter`) stays None, `span()` yields the no-op span (or `add_count`/`record_value` do nothing), and that signal's global provider stays the API default. Both `none` without injection SHALL make `init_telemetry` return False with no state. Console exporters SHALL write to stderr only.

#### Scenario: Console output never reaches stdout
- **GIVEN** `MINTMORY_OTEL_ENABLED=true`, `MINTMORY_OTEL_EXPORTER=console`
- **WHEN** a span is created and telemetry is shut down
- **THEN** stdout is empty and the span is on stderr

#### Scenario: One signal switched off
- **GIVEN** `MINTMORY_OTEL_ENABLED=true` and (a) `OTEL_TRACES_EXPORTER=console`, `OTEL_METRICS_EXPORTER=none`, or (b) `OTEL_TRACES_EXPORTER=none`, `OTEL_METRICS_EXPORTER=console`
- **WHEN** `init_telemetry` runs
- **THEN** it returns True; in (a) `telemetry._meter` is None, `opentelemetry.metrics.get_meter_provider()` is not an SDK `MeterProvider` and `telemetry.record_value("x", 1.0)` raises nothing; in (b) `telemetry._tracer` is None, `telemetry.span("a")` yields a `_NoopSpan` and `opentelemetry.trace.get_tracer_provider()` is not an SDK `TracerProvider`

#### Scenario: Both signals off
- **GIVEN** `MINTMORY_OTEL_ENABLED=true`, `MINTMORY_OTEL_EXPORTER=none`
- **WHEN** `init_telemetry` runs
- **THEN** it returns False, `is_enabled()` is False, and no WARNING is logged

### Requirement: Export never blocks or floods when the collector is absent
Export SHALL run off the calling thread with bounded queues and time out after `MINTMORY_OTEL_EXPORT_TIMEOUT_S` (default 3 s) unless an `OTEL_EXPORTER_OTLP[_TRACES|_METRICS]_TIMEOUT` is set. A guard around each configured exporter SHALL turn an exception or FAILURE into a failed export that never raises, logged on `mintmory.telemetry` once per signal per failure streak as `telemetry: trace export failed` / `telemetry: metric export failed` (WARNING with an endpoint variable set, else DEBUG); the next success SHALL log INFO `telemetry: trace export recovered` (or `metric`). While telemetry runs, logger `opentelemetry.exporter.otlp.proto.http` SHALL be at CRITICAL.

#### Scenario: Export runs off the caller's thread
- **GIVEN** telemetry enabled with `OTEL_EXPORTER_OTLP_ENDPOINT` at `closed_port`, `MINTMORY_OTEL_EXPORT_TIMEOUT_S=0.2`, `_GuardedSpanExporter.export` wrapped to record `threading.get_ident()`
- **WHEN** the test thread creates 200 spans and calls `shutdown_telemetry()`
- **THEN** nothing raises, at least one export was recorded, none on the test thread

#### Scenario: Unreachable collector logs once
- **GIVEN** telemetry enabled, `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:<closed_port>`, `MINTMORY_OTEL_EXPORT_TIMEOUT_S=0.2`, `caplog` at DEBUG
- **WHEN** three times a span is created and `opentelemetry.trace.get_tracer_provider().force_flush()` runs (one failed export each)
- **THEN** exactly one WARNING on `mintmory.telemetry` contains `telemetry: trace export failed`, and no logger starting with `opentelemetry.exporter` logs WARNING or above

#### Scenario: Once per signal per streak
- **GIVEN** `OTEL_EXPORTER_OTLP_ENDPOINT` set; fake inner span and metric exporters whose `export` returns FAILURE, raises `ConnectionError`, returns SUCCESS, returns FAILURE
- **WHEN** `_GuardedSpanExporter(fake)` and `_GuardedMetricExporter(fake_metric)` each export four times
- **THEN** nothing raises, calls 1, 2, 4 return FAILURE, and per signal the `export failed` WARNING is logged twice (calls 1, 4) and the `export recovered` INFO once (call 3); without the endpoint variable the failures are DEBUG and no WARNING is logged

### Requirement: Invalid MintMory telemetry settings fall back
Constructing `OTelSettings` SHALL never raise for a bad `MINTMORY_OTEL_*` value: each SHALL log one WARNING on `mintmory.telemetry` naming the variable and fall back, `MINTMORY_OTEL_ENABLED` to `auto`, `MINTMORY_OTEL_EXPORTER` to `otlp`, a non-numeric or non-positive `MINTMORY_OTEL_EXPORT_TIMEOUT_S` to 3. Booleans and case SHALL be normalised (`True`, `"TRUE"` mean `true`).

#### Scenario: Bad MintMory values fall back
- **GIVEN** `MINTMORY_OTEL_ENABLED=maybe`, `MINTMORY_OTEL_EXPORTER=jaeger`, `MINTMORY_OTEL_EXPORT_TIMEOUT_S=abc`
- **WHEN** `OTelSettings()` is constructed once
- **THEN** nothing raises, `enabled == "auto"`, `exporter == "otlp"`, `export_timeout_s == 3.0`, with exactly three WARNINGs, one naming each variable

### Requirement: Invalid standard OpenTelemetry variables fall back
`init_telemetry` SHALL handle these without raising, each with one WARNING on `mintmory.telemetry` naming the variable: an unknown `OTEL_TRACES_EXPORTER` or `OTEL_METRICS_EXPORTER` falls back to the first known item of its list, else to `MINTMORY_OTEL_EXPORTER`; a protocol other than `http/protobuf` in `OTEL_EXPORTER_OTLP_PROTOCOL` or the per-signal `_TRACES_PROTOCOL` / `_METRICS_PROTOCOL` (which win) falls back to HTTP/protobuf. An unknown sampler falls back to the SDK default with the SDK's own WARNING; MintMory adds none. Values that make the SDK raise fall under "Telemetry init never raises".

#### Scenario: Bad standard values fall back
- **GIVEN** `OTEL_TRACES_EXPORTER=jaeger,console`, `OTEL_EXPORTER_OTLP_PROTOCOL=grpc`, `OTEL_TRACES_SAMPLER=nonsense`, `_endpoint_reachable` patched to True
- **WHEN** `init_telemetry` runs, a span is created and telemetry is shut down
- **THEN** nothing raises, the span is on stderr (console), `mintmory.telemetry` logs exactly two WARNINGs (naming `OTEL_TRACES_EXPORTER` and `OTEL_EXPORTER_OTLP_PROTOCOL`), and `opentelemetry.sdk.trace.sampling` one containing `Couldn't recognize sampler`

### Requirement: Telemetry init never raises
`init_telemetry` SHALL NOT raise. With `settings=None` it SHALL construct `OTelSettings()`, never `load_settings()`, so an invalid variable of another settings group cannot affect it. Any exception while importing the SDK or building exporters, processors, readers or providers (the OTLP exporters raise `ValueError` for `OTEL_EXPORTER_OTLP_TIMEOUT=abc` or `OTEL_EXPORTER_OTLP_COMPRESSION=zip`) SHALL be caught: init shuts down what it built, sets no global provider, keeps no state, logs one WARNING on `mintmory.telemetry` containing `telemetry disabled: init failed (<exception class name>)` without the message, and returns False. Callers need no guard.

#### Scenario: An exporter cannot be built
- **GIVEN** `MINTMORY_OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_TIMEOUT=abc`
- **WHEN** `init_telemetry()` runs
- **THEN** it returns False, `is_enabled()` is False, `opentelemetry.trace.get_tracer_provider()` is not an SDK `TracerProvider`, a WARNING contains `telemetry disabled: init failed (ValueError)`, no record contains `could not convert`, and a following `init_telemetry(span_exporter=InMemorySpanExporter())` returns True

#### Scenario: Another settings group is invalid
- **GIVEN** `MINTMORY_SUMMARY_CONCURRENCY=0` (`load_settings()` raises `ValidationError`)
- **WHEN** `init_telemetry(default_service_name="mintmory-cli", span_exporter=InMemorySpanExporter())` runs and a span is created
- **THEN** it returns True and the span carries `service.name=mintmory-cli`

### Requirement: Bounded flush on exit
`shutdown_telemetry(timeout_s=2.0)` SHALL be the one teardown: providers' `shutdown()` in a daemon thread named `mintmory-telemetry-shutdown` awaited at most `timeout_s`, then clear the module state, release the API's global providers and restore the `opentelemetry.exporter.otlp.proto.http` level init saved (saved only when none is). It SHALL be safe to repeat and without a prior init. `reset_telemetry()` SHALL be `shutdown_telemetry(timeout_s=0.5)`. Init and shutdown SHALL share one lock. The first successful init in a process SHALL register `shutdown_telemetry` with `atexit` once and build providers with `shutdown_on_exit=False`.

#### Scenario: Exit is bounded when export hangs
- **GIVEN** telemetry initialised with an injected span exporter whose `shutdown` waits on a `threading.Event` never set
- **WHEN** `shutdown_telemetry(timeout_s=0.2)` runs
- **THEN** it returns, `is_enabled()` is False, and `threading.enumerate()` holds a live daemon thread named `mintmory-telemetry-shutdown`

#### Scenario: Pending spans are delivered on exit
- **GIVEN** `MINTMORY_OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT=otlp_receiver.endpoint`
- **WHEN** a span `x` ends and `shutdown_telemetry()` runs at once
- **THEN** `otlp_receiver.requests` has a POST to `/v1/traces` and `otlp_receiver.spans()` contains `x`

#### Scenario: The exporter logger level is restored
- **GIVEN** `opentelemetry.exporter.otlp.proto.http` at NOTSET, `MINTMORY_OTEL_ENABLED=true`, `OTEL_EXPORTER_OTLP_ENDPOINT=otlp_receiver.endpoint`
- **WHEN** telemetry is initialised, shut down, initialised and shut down again
- **THEN** the level is CRITICAL while telemetry runs and NOTSET after each shutdown

#### Scenario: One atexit hook, none from the SDK
- **GIVEN** `atexit.register` patched to record its argument
- **WHEN** telemetry is initialised with an in-memory exporter and reader, reset, and initialised again
- **THEN** `shutdown_telemetry` was registered once, and `telemetry._tracer_provider._atexit_handler` and `telemetry._meter_provider._atexit_handler` are None

### Requirement: Resource identifies the process
`service.name` SHALL be, in order: `OTEL_SERVICE_NAME`, `service.name` in `OTEL_RESOURCE_ATTRIBUTES`, `MINTMORY_OTEL_SERVICE_NAME`, the entry point's default (`mintmory-api`, `mintmory-mcp`, `mintmory-history-mcp`, `mintmory-cli`). MintMory SHALL add `service.namespace=mintmory`, `service.version` (installed `mintmory-core`) and a random `service.instance.id`, which the same keys in `OTEL_RESOURCE_ATTRIBUTES` SHALL override.

#### Scenario: The caller's default name
- **GIVEN** no service-name variable
- **WHEN** `init_telemetry(default_service_name="mintmory-cli", span_exporter=...)` runs and a span is created
- **THEN** the span carries `service.name=mintmory-cli` and a non-empty `service.version`

#### Scenario: Standard variables win
- **GIVEN** (a) `OTEL_SERVICE_NAME=memo`, `MINTMORY_OTEL_SERVICE_NAME=other`, `OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=dev,service.namespace=team`; (b) no `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES=service.name=attrs`, `MINTMORY_OTEL_SERVICE_NAME=other`
- **WHEN** `init_telemetry(default_service_name="mintmory-cli", span_exporter=...)` runs
- **THEN** (a) spans carry `service.name=memo`, `deployment.environment.name=dev`, `service.namespace=team`; (b) `service.name=attrs`

### Requirement: Sampling and propagation follow the OpenTelemetry environment
The tracer provider SHALL take its sampler from `OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG` (default `parentbased_always_on`). MintMory SHALL NOT replace the API's global propagator, which reads `OTEL_PROPAGATORS` (default W3C `tracecontext`, `baggage`).

#### Scenario: Context propagates by default
- **WHEN** telemetry is initialised with an in-memory exporter and `opentelemetry.propagate.inject(carrier)` runs inside a span
- **THEN** `carrier["traceparent"]` names that span's trace and span ids

#### Scenario: Sampling switched off
- **GIVEN** telemetry enabled with `OTEL_TRACES_SAMPLER=always_off`
- **WHEN** spans are created
- **THEN** none is exported

### Requirement: Exported spans carry no exception message
Every span exporter, configured or injected, SHALL receive spans through a scrubber: in an `exception` event only `exception.type` is kept, and an ERROR status loses its description, for MintMory's spans and library spans (FastMCP's).

#### Scenario: A library's exception is scrubbed
- **GIVEN** telemetry initialised with an in-memory exporter
- **WHEN** a span from `opentelemetry.trace.get_tracer("x")` records `RuntimeError("SENTINEL-91c2")` and ends with status ERROR
- **THEN** the exported span has an `exception` event with `exception.type=RuntimeError`, and no attribute or status description contains the sentinel

### Requirement: One error-marking helper
`telemetry.mark_error(span, error_type: str) -> None` SHALL be the one way MintMory marks a span failed: on an SDK span it sets status ERROR without description and `error.type` = `error_type`; on `_NoopSpan` (telemetry off, or traces `none`) it does nothing; it SHALL never raise. `_NoopSpan` gets no status method. Parts 2 and 3 call it (`search_phase`, `command_span`, the HTTP middleware).

#### Scenario: Marking a span on and off
- **WHEN** `with telemetry.span("a") as sp: telemetry.mark_error(sp, "RuntimeError")` runs (a) with telemetry initialised with an in-memory exporter, (b) with telemetry not initialised
- **THEN** (a) span `a` is exported with status ERROR, an empty description and `error.type=RuntimeError`; (b) nothing raises and `sp` is a `_NoopSpan`

### Requirement: Telemetry test seam
`init_telemetry(settings=None, *, default_service_name="mintmory", span_exporter=None, metric_reader=None) -> bool` SHALL use an injected span exporter (through a synchronous processor) and metric reader instead of configured exporters, and injection SHALL enable telemetry when the SDK imports, even with `MINTMORY_OTEL_ENABLED=false` or `OTEL_SDK_DISABLED=true`. Injecting only one SHALL leave the other signal off (as `none`); injection never builds a configured exporter.

#### Scenario: Injection beats the suite's off default
- **GIVEN** `MINTMORY_OTEL_ENABLED=false` (the root `conftest.py` default)
- **WHEN** `init_telemetry(span_exporter=InMemorySpanExporter())` runs and a span is created
- **THEN** it returns True and the span is in that exporter

#### Scenario: Single injection builds no network exporter
- **GIVEN** `OTEL_EXPORTER_OTLP_ENDPOINT` set, the `OTLPSpanExporter` and `OTLPMetricExporter` classes patched to raise
- **WHEN** `init_telemetry(span_exporter=InMemorySpanExporter())` runs, then after a reset `init_telemetry(metric_reader=InMemoryMetricReader())`
- **THEN** both return True; the first leaves `telemetry._meter` None and exports its spans, the second leaves `telemetry._tracer` None and its `record_value` points reach the reader

### Requirement: Shared telemetry test fixtures
The root `conftest.py` SHALL give every package's tests `MINTMORY_OTEL_ENABLED=false` by default, an autouse `telemetry.reset_telemetry()` around each test, and fixtures used by name: `closed_port` (int, a `127.0.0.1` port nobody listens on) and `otlp_receiver` with `endpoint` (`http://127.0.0.1:<port>`), `requests` (`(path, body bytes)` per POST, each answered 200) and `spans()` (`(name, resource attributes dict)` per span posted to `/v1/traces`).

#### Scenario: A CLI-package test uses the receiver
- **GIVEN** a test in `packages/cli/tests` requesting `otlp_receiver`, with `MINTMORY_OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT=otlp_receiver.endpoint`
- **WHEN** it initialises telemetry, creates span `x` and calls `telemetry.shutdown_telemetry()`
- **THEN** `otlp_receiver.spans()` contains `x`, with no helper module imported

### Requirement: Global providers and repeated init
Each successful init SHALL make its providers the global ones, so library spans (FastMCP's) reach the same exporters. After a successful init, a later `init_telemetry` SHALL change nothing and return True; a call returning False SHALL leave no state.

#### Scenario: A second init changes nothing
- **GIVEN** telemetry initialised with an in-memory exporter
- **WHEN** `init_telemetry` is called again with other settings
- **THEN** it returns True and spans still go to the first exporter

#### Scenario: Re-initialisation after shutdown
- **GIVEN** telemetry initialised with one in-memory exporter, then shut down
- **WHEN** it is initialised with a second in-memory exporter and spans are created through `telemetry.span` and `opentelemetry.trace.get_tracer("x")`
- **THEN** the second init returns True and both spans are in the second exporter only
