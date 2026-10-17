# observability Specification

## Purpose
MintMory's observability: OpenTelemetry traces and metrics from every entry point (CLI, REST API, MCP servers), safe and silent when no collector runs, distributed across HTTP, MCP and outbound LLM calls, with a local collector, Jaeger and Prometheus stack for development.

## Requirements

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
`init_telemetry` SHALL NOT raise. With `settings=None` it SHALL construct `OTelSettings()`, never `load_settings()`, so an invalid variable of another settings group cannot affect it. Any exception while importing the SDK or building exporters, processors, readers or providers (the OTLP exporters raise `ValueError` for `OTEL_EXPORTER_OTLP_TIMEOUT=abc` or `OTEL_EXPORTER_OTLP_COMPRESSION=zip`) SHALL be caught: init runs `shutdown_telemetry`'s teardown on what it built under the lock it already holds (not taken again), so no global provider, no state and the saved logger level restored, logs one WARNING on `mintmory.telemetry` containing `telemetry disabled: init failed (<exception class name>)` without the message, and returns False. Callers need no guard.

#### Scenario: An exporter cannot be built
- **GIVEN** `MINTMORY_OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_TIMEOUT=abc`
- **WHEN** `init_telemetry()` runs
- **THEN** it returns False, `is_enabled()` is False, `opentelemetry.trace.get_tracer_provider()` is not an SDK `TracerProvider`, a WARNING contains `telemetry disabled: init failed (ValueError)`, no record contains `could not convert`, the `opentelemetry.exporter.otlp.proto.http` level is the one before init, and a following `init_telemetry(span_exporter=InMemorySpanExporter())` returns True

#### Scenario: Another settings group is invalid
- **GIVEN** `MINTMORY_SUMMARY_CONCURRENCY=0` (`load_settings()` raises `ValidationError`)
- **WHEN** `init_telemetry(default_service_name="mintmory-cli", span_exporter=InMemorySpanExporter())` runs and a span is created
- **THEN** it returns True and the span carries `service.name=mintmory-cli`

### Requirement: Bounded flush on exit
`shutdown_telemetry(timeout_s=2.0)` SHALL be the one teardown: providers' `shutdown()` in a daemon thread named `mintmory-telemetry-shutdown` awaited at most `timeout_s`, then clear the module state (`_tracer`, `_meter`, the providers, the `_instruments` cache), release the API's global providers and restore the `opentelemetry.exporter.otlp.proto.http` level init saved (saved only when none is). It SHALL be safe to repeat and without a prior init. Init and shutdown SHALL share one lock. Providers SHALL be built with `shutdown_on_exit=False`. A successful init while the module flag `_atexit_registered` is False SHALL call `atexit.register(shutdown_telemetry)` (looked up on the `atexit` module at call time) and set the flag; `shutdown_telemetry` keeps it, so a process registers once however often it re-initialises. `reset_telemetry()` SHALL be `shutdown_telemetry(timeout_s=0.5)`, then `atexit.unregister(shutdown_telemetry)` and `_atexit_registered = False`, so each test starts unregistered.

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
- **GIVEN** `monkeypatch.setattr("atexit.register", calls.append)` with `calls = []`, and `_atexit_registered` False (the autouse reset)
- **WHEN** telemetry is initialised with an in-memory exporter and reader, initialised again, shut down with `shutdown_telemetry()` and initialised again
- **THEN** `calls == [telemetry.shutdown_telemetry]`, `_atexit_registered` is True, `telemetry._tracer_provider._atexit_handler` and `telemetry._meter_provider._atexit_handler` are None; after `reset_telemetry()` the flag is False and one more init makes `len(calls) == 2`; with the same GIVEN, an init returning False (`MINTMORY_OTEL_ENABLED=true`, `MINTMORY_OTEL_EXPORTER=none`) leaves `calls` empty and the flag False

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

### Requirement: _sdk_available must catch ImportError and ValueError from — feedback FB-001
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: _sdk_available must catch ImportError and ValueError from
- **WHEN** init_telemetry() runs and the opentelemetry package is not installed (importlib.util.find_spec raises ModuleNotFoundError for opentelemetry.sdk)
- **THEN** it returns False without raising; in auto mode it logs nothing, in true mode it logs one WARNING that names mintmory-core[otel]

### Requirement: _build_meter_provider must wrap the configured metric exporter with — feedback FB-002
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: _build_meter_provider must wrap the configured metric exporter with
- **WHEN** a metric export fails because the configured OTLP collector is unreachable (endpoint on a closed port, three force_flush calls)
- **THEN** exactly one WARNING 'telemetry: metric export failed' is logged per failure streak on the mintmory.telemetry logger

### Requirement: init_telemetry: one set of providers when two threads init at once — feedback FB-003
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: init_telemetry: one set of providers when two threads init at once
- **WHEN** two threads call init_telemetry at the same time (for example behind a threading.Barrier, each with its own span_exporter)
- **THEN** exactly one set of providers is built and installed as the global ones, the other call returns the same result without building, and shutdown_telemetry flushes and shuts down that one set

### Requirement: MINTMORY_OTEL_ENABLED keeps the boolean spellings it accepted before — feedback FB-004
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: MINTMORY_OTEL_ENABLED keeps the boolean spellings it accepted before
- **WHEN** MINTMORY_OTEL_ENABLED is 1, yes, on, 0, no or off (any case)
- **THEN** the mode is true for 1, yes and on and false for 0, no and off, with no WARNING; auto, true and false (any case) keep their meaning; any other value still falls back to auto with a WARNING

### Requirement: an injected exporter without the SDK says why telemetry is off — feedback FB-006
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: an injected exporter without the SDK says why telemetry is off
- **WHEN** init_telemetry() is called with a span_exporter or a metric_reader and the OpenTelemetry SDK is not installed (_sdk_available() returns False)
- **THEN** it returns False, installs no provider, and logs exactly one WARNING on the mintmory.telemetry logger that names the missing SDK and mintmory-core[otel]

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

### Requirement: Span kind, parent context and exception options
`telemetry.span` SHALL have the signature `span(name, *, kind="internal", context=None, record_exception=True, set_status_on_exception=True, **attrs)` and pass `kind` (`"internal"`, `"server"`, `"client"`, mapped to `SpanKind`; any other value maps to INTERNAL), `context` and both flags to the tracer's `start_as_current_span`. The defaults are the SDK's, so existing callers (`dreaming.py`, `llm.py`, `traced`) keep their behaviour. With telemetry off it SHALL yield `_NoopSpan`, which gains a no-op `update_name(name)`. This unit's `command_span` uses the two flags; `add-telemetry-boundary-tracing`, which depends on this unit, uses all four options and `update_name` for its server and client spans and does not change `span()`.

#### Scenario: Options reach the span
- **GIVEN** telemetry initialised with an injected in-memory span exporter
- **WHEN** `with telemetry.span("a", kind="server"): pass` and `with telemetry.span("d", kind="bogus"): pass` run, then inside `pytest.raises(RuntimeError)` `with telemetry.span("b", record_exception=False, set_status_on_exception=False): raise RuntimeError("SENTINEL-12")` and the same with defaults as span `c`
- **THEN** `a` has kind SERVER and `d` kind INTERNAL; `b` has status UNSET and no event; `c` has status ERROR with an empty description (scrubbed) and one `exception` event whose only attribute is `exception.type=RuntimeError`; with telemetry not initialised, `with telemetry.span("a", kind="server", record_exception=False) as sp: sp.update_name("b")` raises nothing and `sp` is a `_NoopSpan`

### Requirement: Search phase spans and latency
Each search SHALL record child spans `mintmory.search.fts`, `.substring`, `.vector` and `.fusion` under `mintmory.search`, each with `mintmory.result_count`, and the histogram `mintmory.search.latency_ms` (unit `ms`) with `phase` = `fts`, `substring`, `vector`, `fusion`, `graph` (every search-around) or `total`. This SHALL live in code shared by both storage backends (`hybrid_search.py` and `telemetry.py`). Note anchoring SHALL NOT record search phases.

#### Scenario: A search shows its phases
- **GIVEN** telemetry with an injected in-memory span exporter and metric reader, and a SQLite store with three memories
- **WHEN** a search runs
- **THEN** the four phase spans have the `mintmory.search` span as parent, and latency points exist for `fts`, `substring`, `vector`, `fusion` and `total`

#### Scenario: Search-around alone records only its graph point
- **WHEN** `search_around` is called directly (it runs no score stage)
- **THEN** one `phase=graph` point is recorded and no `mintmory.search.fts`, `.substring`, `.vector` or `.fusion` span

#### Scenario: The Postgres backend uses the shared path
- **GIVEN** a `PostgresBackend` built without a database (its pool is created lazily) whose data-access methods are patched
- **WHEN** its `search` runs with telemetry on
- **THEN** the same four phase spans and the `total` point are recorded

### Requirement: Span helpers without work or with a failure
A search stage with nothing to do (no query embedding, substring search off, no match) SHALL still record its span with `mintmory.result_count` = 0. When the code wrapped by any span helper of this change raises (`search_phase`, the embed decorator, `mintmory.convert`, `mintmory.vision.caption`, `command_span`), the helper SHALL mark its span with `telemetry.mark_error(span, <exception class name>)` from `add-telemetry-runtime`, still record its metric point if it has one, and re-raise the exception unchanged. Recording a metric point or attribute SHALL never raise into the caller.

#### Scenario: A stage with nothing to do
- **WHEN** a search runs without a query embedding
- **THEN** the `mintmory.search.vector` span has `mintmory.result_count` = 0

#### Scenario: A failing stage
- **GIVEN** `_fts_scores` patched to raise `RuntimeError`
- **WHEN** a search runs
- **THEN** the same `RuntimeError` propagates, the `mintmory.search.fts` span has status ERROR and `error.type=RuntimeError`, and a `phase=fts` point is recorded

#### Scenario: A metric failure stays inside telemetry
- **GIVEN** telemetry on and `telemetry.record_value` patched to raise `RuntimeError`
- **WHEN** `HashingEmbedder().embed("a")` and a search run
- **THEN** both return their normal results

### Requirement: Embedding spans and latency
Every public `embed` or `embed_batch` call of an embedder in `embedder.py` SHALL record one `mintmory.embed` span (kind INTERNAL) with `mintmory.embed.provider` (the `create_embedder` name: `hashing`, `local`, `ollama`, `openai`, `fake`), `gen_ai.request.model` (the embedder's `model_name`, omitted when empty), `mintmory.embed.batch_size` and `mintmory.embed.dim`, and one `mintmory.embed.latency_ms` point (unit `ms`, attributes `provider` and `model`, `model` omitted when empty). A public method calling another (`FakeEmbedder.embed_batch` calls `embed`) SHALL record once.

#### Scenario: Hashing embedder is traced
- **WHEN** `HashingEmbedder().embed_batch(["a", "b"])` runs with telemetry on
- **THEN** one `mintmory.embed` span with `mintmory.embed.provider=hashing`, `mintmory.embed.batch_size` = 2 and `mintmory.embed.dim` = the embedder's dimension, and one latency point exist

#### Scenario: Network embedders name their model
- **WHEN** `OllamaEmbedder` embeds one text against a local test HTTP server, and an `OpenAIEmbedder` built with `OpenAIEmbedder.__new__` and a stub client embeds one text
- **THEN** each records one `mintmory.embed` span with `mintmory.embed.provider` (`ollama`, `openai`), `gen_ai.request.model` and `mintmory.embed.dim`, and `LocalEmbedder.embed` and `.embed_batch` carry the same decorator (`__wrapped__`)

### Requirement: CLI commands are traced end to end
`add`, `search`, `ingest`, `index-tree`, `dream`, `history backfill` and `history sync` SHALL each run inside a root span `mintmory.cli.<command>` (spaces become dots), marked with `mark_error` when the command raises or exits non-zero, never for exit code 0. `telemetry.command_span(name)` SHALL open that span with `record_exception=False, set_status_on_exception=False` and mark it only through `mark_error`: `typer.Exit` is a `RuntimeError` subclass (Typer 0.26.7), so the SDK default would mark an exit with code 0 as ERROR. `index-tree` SHALL set `mintmory.files.scanned`, `.added`, `.updated`, `.unchanged` and `.failed` from the counters `index_tree` already keeps (`scanned`, `added`, `updated`, `unchanged`, `failed`).

#### Scenario: Command spans and counts
- **GIVEN** telemetry with an in-memory exporter and a folder with two text files
- **WHEN** `mintmory index-tree <folder>`, `mintmory search hello` and `mintmory dream` run through the Typer test runner
- **THEN** `mintmory.cli.index-tree` (with `mintmory.files.scanned` = 2 and `mintmory.files.added` = 2), `mintmory.cli.search` and `mintmory.cli.dream` spans are exported, none with status ERROR; and `mintmory history sync` over an empty session folder (the fixtures of `packages/cli/tests/test_history_cli.py`) exports a `mintmory.cli.history.sync` span

#### Scenario: A failing command is marked
- **WHEN** `mintmory ingest` runs on a path that does not exist (Typer does not validate it: the body finds no files and raises `typer.Exit(code=1)`)
- **THEN** the `mintmory.cli.ingest` span has status ERROR and `error.type=Exit`

#### Scenario: Exit code 0 is not an error
- **GIVEN** telemetry with an in-memory exporter, a function decorated with `telemetry.command_span("probe-ok")` raising `typer.Exit(code=0)` and one decorated with `telemetry.command_span("probe-fail")` raising `typer.Exit(code=1)`
- **WHEN** each is called inside `pytest.raises(typer.Exit)`
- **THEN** span `mintmory.cli.probe-ok` has status UNSET and no event; `mintmory.cli.probe-fail` has status ERROR, `error.type=Exit` and no event

### Requirement: Indexing and conversion phases are traced
Under `mintmory.cli.index-tree`, `index-tree` SHALL record `mintmory.index_tree.scan` around the walk over the roots (including the per-file co-change embeddings), `mintmory.index_tree.prune` around the `--prune` pass, and `mintmory.index_tree.cochange` around the post-walk co-change block, which runs only when co-change is on and at least two files were added or updated (`if run_cochange and len(changed_docs) >= 2:`); that span SHALL carry `mintmory.outcome=ok` and `mintmory.cochange.changesets` (the count `apply_changesets` returns), or `mintmory.outcome=unavailable` when `CoChangeUnavailable` is caught (no ERROR). Inside the walk it SHALL record one `mintmory.convert` span per binary conversion (the `extract_markdown` call when `want_binary` is true; the plain-text pass, `text_eligible` without `want_binary`, records none) and one `mintmory.vision.caption` span around each `captioner.describe(...)` call of the raster branch, which runs only when `vision.captioner_from_settings` returns a captioner (`MINTMORY_VISION_PROVIDER=llm`); SVG text and rasters queued for the agent record none. `ingest` SHALL record one `mintmory.convert` span per `extract_markdown` call. Both span kinds carry `mintmory.file.suffix`, `mintmory.file.size_bytes` and `mintmory.outcome` (`ok`, or `failed` on the `ConversionError` / `VisionError` the commands catch and count).

#### Scenario: index-tree phases
- **GIVEN** telemetry with an in-memory exporter and a folder with three text files written at once
- **WHEN** `mintmory index-tree --prune --cochange <folder>` runs
- **THEN** `mintmory.cli.index-tree` has the children `mintmory.index_tree.scan`, `.prune` and `.cochange`, the last with `mintmory.outcome=ok` (three files in one folder and time block take the connected-components fallback, since `cochange_fallback_max_n` defaults to 8, so scikit-learn is not needed), and no `mintmory.convert` span exists

#### Scenario: No co-change span without co-change work
- **WHEN** `mintmory index-tree --cochange` runs over a folder with one text file, and `--no-cochange` over three
- **THEN** neither run exports a `mintmory.index_tree.cochange` span

#### Scenario: Conversion spans
- **GIVEN** `mintmory.core.conversion.extract_markdown` patched to return `ExtractResult(text="converted", method="markitdown", path=...)`
- **WHEN** `mintmory ingest report.pdf` runs, and `mintmory index-tree --content --content-types pdf <folder with report.pdf>`
- **THEN** one `mintmory.convert` span (`mintmory.file.suffix=.pdf`, `mintmory.outcome=ok`) is a child of `mintmory.cli.ingest`, and one is a descendant of the content run's `mintmory.index_tree.scan`

#### Scenario: Inline caption span
- **GIVEN** `MINTMORY_VISION_PROVIDER=llm`, `mintmory.core.llm.post_chat_completion` patched to return `{"choices": [{"message": {"content": "A caption."}}]}` (as `test_index_tree_vision_llm_mode_captions_raster_inline` in `packages/cli/tests/test_cli.py` does), and a folder with `photo.png` (`b"\x89PNG\r\n\x1a\n" + b"\x00" * 16`)
- **WHEN** `mintmory index-tree <folder> --no-text-content --vision` runs, then the same over a fresh database with `MINTMORY_VISION_PROVIDER` unset
- **THEN** the first run prints `images-described` and exports one `mintmory.vision.caption` span (`mintmory.file.suffix=.png`, `mintmory.outcome=ok`) under `mintmory.index_tree.scan`; the second prints `images-queued` and exports none

### Requirement: Worker threads keep the trace
Work handed to thread pools in a traced operation (session preparation in history `backfill` and `sync`, the dream's concurrent summaries) SHALL run in a fresh copy of the caller's context per task.

#### Scenario: Threads stay in the trace
- **GIVEN** telemetry with an in-memory exporter
- **WHEN** inside a test span `root-a`, `backfill(..., max_concurrency=4)` runs, and then `sync(..., max_concurrency=4)` into a second, empty history database, each over four sessions (the stub adapter of `test_backfill_concurrent_no_data_loss` in `packages/core/tests/test_history_ingest.py`) with a fake distiller that opens span `fake.distill`; and inside a test span `root-b`, `DreamingEngine(store, summarizer=fake, summary_settings=SummarySettings(concurrency=2, min_memories=2)).run_full()` runs over four memories (two quoting `"alpha-x"`, two quoting `"beta-y"`, so at least two concepts), the fake summarizer opening span `fake.summarize`
- **THEN** every `fake.distill` span has the trace id of `root-a`, every `fake.summarize` span that of `root-b`, and the backfill and sync reports have `errors == 0`

### Requirement: Memory counters
Adding a memory SHALL increment `mintmory.memories.added` with `category` (the `MemoryCategory` value, e.g. `fact`), through one decorator shared by both backends' `add_memory`.

#### Scenario: Counter by category
- **WHEN** two `fact` memories and one `skill` memory are added to a SQLite store with telemetry on
- **THEN** the counter reports 2 for `category=fact` and 1 for `category=skill`, and `PostgresBackend.add_memory` carries the same decorator

### Requirement: Telemetry carries no content
Span names, span and event attributes, status descriptions and metric attributes SHALL NOT contain memory text, note text, query text, prompts, completions, file contents, concept names or header values. A failed span carries status ERROR and `error.type` only; exception messages are removed at export by the runtime's scrubber. On `staging` the existing spans already comply and stay as they are: `gen_ai.chat` carries `gen_ai.system`, `gen_ai.request.model`, `prompt_chars`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `latency_ms`, `ok`; `mintmory.dream.light` / `.full` carry counts (`new_links`, `new_summaries`, `contradictions_resolved`, `archived`, `rehabilitated`); `mintmory.dream.step` carries `step` and `count`; metrics `mintmory.llm.latency_ms`, `mintmory.llm.calls` (`model`, `ok`) and `mintmory.dream.duration_ms` (`intensity`).

#### Scenario: No content leaks into telemetry
- **WHEN** a memory with text `SENTINEL-CONTENT-7f3a` is added, a search for `SENTINEL-QUERY-91c2` runs and `build_dreaming_engine(store).run_light()` runs, with telemetry on
- **THEN** no exported span, event or metric attribute value contains either sentinel

#### Scenario: Notes, LLM calls, concept names, headers and indexed files leak nothing
- **GIVEN** telemetry on; a local test HTTP server answering `POST /v1/chat/completions` with `{"choices": [{"message": {"content": "SENTINEL-OUT-2b"}}]}`; a SQLite store with three memories each containing `"zq-concept-41"` (quoted, so the entity extractor yields the concept `zq-concept-41`) and `SENTINEL-DREAM-8e`
- **WHEN** `notes.create_note(store, "SENTINEL-NOTE-5d")` runs, `build_dreaming_engine(store, LLMSettings(provider="ollama", base_url=<server>/v1, model="m", api_key="SENTINEL-KEY-6e")).run_full()` runs (the summary prompt holds the concept name and `SENTINEL-DREAM-8e`, the `Authorization` header the key), and `mintmory index-tree` indexes a text file containing `SENTINEL-FILE-3c`
- **THEN** the server received at least one chat request, and no exported span name, span or event attribute, status description or metric attribute contains `zq-concept-41`, `SENTINEL-NOTE-5d`, `SENTINEL-DREAM-8e`, `SENTINEL-OUT-2b`, `SENTINEL-KEY-6e` or `SENTINEL-FILE-3c`

#### Scenario: A failure does not leak its message
- **GIVEN** `_fts_scores` patched to raise `RuntimeError("no such column: SENTINEL-QUERY-91c2")`
- **WHEN** a search runs with telemetry on and the error propagates
- **THEN** the `mintmory.search.fts` span has status ERROR and `error.type=RuntimeError`, and no exported span (including `mintmory.search`), event or status description contains the sentinel

### Requirement: Rejected hold: the diff is longer than 120000 characters: the judge saw only the start — finding H-e0757174
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: Rejected hold: the diff is longer than 120000 characters: the judge saw only the start
- **WHEN** the meter, a counter's add, a histogram's record or a span's set_attribute raises inside a telemetry helper (counts_added, add_count, record_value, the span attributes of embed_span and file_span)
- **THEN** the error stays inside telem
