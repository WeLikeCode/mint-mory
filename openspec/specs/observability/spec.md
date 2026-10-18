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

### Requirement: HTTP server spans continue the caller's trace
Each API request, except excluded paths, SHALL run in a SERVER span named `<METHOD> <route template>` that continues the W3C context of the request headers (ASGI header bytes decoded as latin-1, names lower-cased), with `http.request.method`, `http.route` and `http.response.status_code`, and without `url.path`, `url.query` or any other raw path value. API scenarios run under `TestClient` with telemetry initialised with an in-memory span exporter and metric reader (setup in task 2.1).

#### Scenario: Incoming traceparent is continued
- **GIVEN** a memory created with `POST /memories` and the body `{"content": "Acme parking uses OAuth.", "category": "fact"}`
- **WHEN** `POST /memories/search` is sent with the body `{"query": "parking"}` and `traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
- **THEN** it answers 200, a SERVER span named `POST /memories/search` is exported with trace id `4bf92f3577b34da6a3ce929d0e0e4736` and parent span id `00f067aa0ba902b7`, and the `mintmory.search` span of that request is its descendant

#### Scenario: Route template, not the raw path, names the span
- **GIVEN** a memory created as above, its id `<id>` taken from the response
- **WHEN** `GET /memories/<id>?verbose=1` is called
- **THEN** the span is named `GET /memories/{memory_id}`, `http.route` is `/memories/{memory_id}`, it has no `url.path` or `url.query` attribute, and no attribute value contains `<id>`

### Requirement: How the middleware ends the server span
`TelemetryMiddleware` (`api/telemetry_middleware.py`, pure ASGI) SHALL be the outermost user middleware (the last `app.add_middleware` call, after `CORSMiddleware`) and, for a traced request, open `telemetry.span(<METHOD>, kind="server", context=telemetry.extract_context(headers), record_exception=False, set_status_on_exception=False)` around `await self.app(scope, receive, wrapped_send)`, where `wrapped_send` keeps the status of the first `http.response.start` message and forwards every message unchanged. These `span()` options and `_NoopSpan.update_name` are delivered by the prerequisite `add-telemetry-heavy-path-spans` (requirement "Span kind, parent context and exception options"); this unit does not change `span()`. When the app returns or raises:
- Name: when `scope.get("route")` is not None the span is renamed `<METHOD> <route.path>` and gets `http.route`; else it keeps `<METHOD>` and has no `http.route`. FastAPI 0.137.1 `APIRoute.matches` (`fastapi/routing.py`) sets `scope["route"]` on a full or partial match, so a method mismatch (405) has a route; a 404, and a CORS preflight answered by `CORSMiddleware`, have none.
- Status: `http.response.status_code` is the sent status; if none was sent and the app raised an `Exception`, 500 (Starlette's outer `ServerErrorMiddleware` sends it); if none was sent otherwise, the attribute is absent.
- Marking, with runtime's `telemetry.mark_error(span, error_type)`: an `Exception` marks with its class name and the same object is re-raised; else a sent status of 500 or more marks with the status as a string; `asyncio.CancelledError` (client gone) or another `BaseException` leaves the span unmarked and is re-raised.
- Metric: every traced request records one `http.server.request.duration` point with the span's `http.request.method`, `http.route` and `http.response.status_code`, absent ones omitted.

The "ASGI harness" of the scenarios: telemetry with an in-memory exporter and reader; `asyncio.run(TelemetryMiddleware(inner)(scope, receive, send))` with `scope = {"type": "http", "method": "GET", "path": "/x", "headers": []}`, `receive` returning `{"type": "http.request", "body": b"", "more_body": False}` and `send` appending each message to a list `sent`.

#### Scenario: No route, and a method mismatch
- **WHEN** `GET /no-such-path`, `DELETE /stats` and a preflight `OPTIONS /stats` (headers `Origin: http://x`, `Access-Control-Request-Method: GET`) are called
- **THEN** they answer 404, 405 and 200; spans `GET` (404, no `http.route`), `DELETE /stats` (`http.route=/stats`, 405) and `OPTIONS` (200, no `http.route`) are exported, all with status UNSET

#### Scenario: A route that raises before the response starts
- **GIVEN** a test route `GET /test-raise` added to the app that raises `RuntimeError("SENTINEL-55")`
- **WHEN** it is called with `TestClient(app, raise_server_exceptions=False)`
- **THEN** the answer is 500, its span `GET /test-raise` has status ERROR with an empty description, `error.type=RuntimeError`, `http.response.status_code` = 500 and no event, the duration histogram has a point with `http.response.status_code` = 500, and no exported span, event or status description contains `SENTINEL-55`

#### Scenario: An exception after the response started
- **GIVEN** the ASGI harness and `inner` that sends `{"type": "http.response.start", "status": 200, "headers": []}` and then raises `RuntimeError("SENTINEL-56")`
- **WHEN** the middleware is run inside `pytest.raises(RuntimeError)`
- **THEN** the raised object is the one `inner` raised, `sent` holds the start message, the span `GET` has status ERROR with an empty description, `error.type=RuntimeError`, `http.response.status_code` = 200 and no event, and the duration point has `http.response.status_code` = 200

#### Scenario: A 5xx answer without an exception
- **GIVEN** the ASGI harness and `inner` that sends a start message with status 503 and `{"type": "http.response.body", "body": b"x"}`
- **WHEN** the middleware is run
- **THEN** it returns None, `sent` holds both messages, and the span `GET` has status ERROR, `error.type` = `"503"` (a string) and `http.response.status_code` = 503

#### Scenario: A cancelled request, and no response at all
- **GIVEN** the ASGI harness and (a) `inner` raising `asyncio.CancelledError()` before sending anything, (b) `inner` returning without sending anything
- **WHEN** the middleware is run, (a) inside `pytest.raises(asyncio.CancelledError)`
- **THEN** in both, `sent` is empty, the span `GET` is exported with status UNSET, no `error.type`, no event and no `http.response.status_code`, and the duration point has `http.request.method=GET` and no other attribute; (b) returns None

### Requirement: Middleware telemetry never alters a request
Each telemetry step of the middleware (header decoding, `extract_context`, opening and closing the span, `update_name`, setting attributes, `mark_error`, `record_histogram`) SHALL run in its own `try/except Exception`, apart from the `try` around `await self.app(...)`. A failed step SHALL be dropped with one DEBUG record on `mintmory.telemetry` naming only the exception class; the app still gets the same `scope` and `receive`, its messages reach `send` unchanged and in order, and the middleware returns or raises what the app does. If the span cannot be opened, the request runs without span or point. `record_histogram` itself SHALL never raise. A missing or malformed `traceparent` SHALL start a new trace.

#### Scenario: A malformed traceparent starts a new trace
- **WHEN** `GET /stats` is sent with `traceparent: garbage`, and again with `traceparent: 00-00000000000000000000000000000000-0000000000000000-01`
- **THEN** both answer 200 and each SERVER span `GET /stats` has no parent and a trace id other than `4bf92f3577b34da6a3ce929d0e0e4736`; `telemetry.extract_context({"traceparent": "garbage"})` returns without raising

#### Scenario: A failing histogram record leaves the response unchanged
- **GIVEN** an empty store, the body `b0` of a `GET /stats` answer, then `opentelemetry.sdk.metrics._internal.instrument.Histogram.record` patched to raise `RuntimeError`
- **WHEN** `GET /stats` is sent again
- **THEN** it answers 200 with a body equal to `b0`, and the SERVER span `GET /stats` is still exported

#### Scenario: Failing span updates leave the response unchanged
- **GIVEN** the ASGI harness; `opentelemetry.sdk.trace.Span.set_attribute`, `.set_attributes`, `.update_name` and `telemetry.extract_context` patched to raise `RuntimeError`; `inner` sending a start message (status 201, headers `[(b"x-a", b"1")]`) and a body message `b"ok"`
- **WHEN** the middleware is run (each run with a new `sent`); again with an `inner` that sends the same two messages and then raises `ValueError("v")`; and with the first `inner` and `telemetry.span` patched to raise `RuntimeError`
- **THEN** the first and third runs return None with `sent` equal to the two messages in order, the second raises that `ValueError` object after them, the third adds no span to the exporter, and `mintmory.telemetry` has a DEBUG record containing `RuntimeError`

### Requirement: Excluded HTTP paths
`/healthz` and `/readyz` (exact path match) SHALL NOT be traced, nor a path in which `re.search` finds one of the comma-separated regexes of `OTEL_PYTHON_EXCLUDED_URLS` (the path only, no query string). Read on each request, the value SHALL be compiled by `telemetry_middleware._compile_excluded(value)` (a `functools.lru_cache` on the whole value): items stripped, empty items ignored, an item that is not a valid regex skipped with one WARNING on `mintmory.telemetry` containing it, logged at the value's first compile; a request never fails.

#### Scenario: Health probes are not traced
- **WHEN** `GET /healthz`, `GET /readyz` and `GET /healthz/x` are called
- **THEN** no span is exported for the first two, and `GET /healthz/x` (404) is traced as `GET`

#### Scenario: Excluded by the environment
- **GIVEN** the module-level `app` from `mintmory.api.app` and, set with `monkeypatch.setenv` after import, (a) `OTEL_PYTHON_EXCLUDED_URLS=^/stats$,/summaries`, (b) `OTEL_PYTHON_EXCLUDED_URLS=" , ^/stats$ ,"`
- **WHEN** `GET /stats`, `GET /summaries` and `GET /memories/<id>` of a created memory are called
- **THEN** `GET /stats` is not traced in (a) and (b), `GET /summaries` is not traced in (a) and is in (b), and the memory request is traced in both

#### Scenario: A bad exclusion pattern is skipped
- **GIVEN** `_compile_excluded.cache_clear()` and `OTEL_PYTHON_EXCLUDED_URLS=([,^/stats$`
- **WHEN** `GET /stats` and `GET /memories/<id>` of a created memory are called twice each
- **THEN** all four answer 200, `GET /stats` is not traced, the memory request is, and `mintmory.telemetry` logged exactly one WARNING, containing `([`

### Requirement: HTTP server duration metric
The API SHALL record each traced request in the histogram `http.server.request.duration` (unit `s`, explicit bucket boundaries 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5 and 10) with the attributes stated in "How the middleware ends the server span".

#### Scenario: Request duration recorded
- **WHEN** two `GET /stats` requests are sent
- **THEN** `InMemoryMetricReader.get_metrics_data()` has the metric `http.server.request.duration` with unit `s` and one point for `http.route=/stats`, `http.request.method=GET`, `http.response.status_code=200`, with `count` 2 and `explicit_bounds` `(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)`

### Requirement: MCP tool calls are traced once
Each MCP tool call in `mintmory-mcp` and `mintmory-history-mcp` SHALL be traced by FastMCP's native SERVER span; MintMory SHALL NOT add an MCP middleware or a second span per tool call, and no MintMory code depends on that span. Facts verified by running FastMCP 3.4.2 (pinned by `uv.lock`; CI runs `uv sync --frozen`) with an in-memory exporter:
- `FastMCP.call_tool` (`fastmcp/server/server.py`) runs the tool inside `server_span(f"tools/call {name}", ...)` (`fastmcp/server/telemetry.py`): tracer `fastmcp`, kind SERVER, attributes such as `mcp.method.name`, `gen_ai.tool.name` and `mcp.session.id`, never an argument value. The tracer is looked up per span (`opentelemetry.trace.get_tracer("fastmcp")`), so spans follow the current global provider, also after a reset and a new init.
- The parent is the `traceparent` / `tracestate` of the request's `_meta` unless a valid span is current. `fastmcp.Client.call_tool` opens its own CLIENT span of the same name and puts its `traceparent` into `_meta`, replacing a caller's; `client.session.call_tool(name, args, meta=...)` sends `_meta` as given, with no CLIENT span.
- A raising tool: `call_tool` re-raises the exception as `ToolError("Error calling tool '<name>': <message>")` (no masking, FastMCP's default); `server_span` sets `error.type=tool_error` and records an `exception` event; the SDK's `use_span` records a second and sets status ERROR with the message as description. Runtime's scrubber (outermost on every injected exporter) leaves `exception.type=fastmcp.exceptions.ToolError` as each event's only attribute and an empty description. `client.call_tool` raises `ToolError`; with `raise_on_error=False` it returns `is_error=True`.
- A sync tool runs on an anyio worker thread with the context copied, so its spans are children of the SERVER span.

If FastMCP differs from these facts, the tests fail and the unit fails; a MintMory span is never added in its place.

#### Scenario: The verified FastMCP version is installed
- **WHEN** the MCP telemetry test module runs
- **THEN** a test in it asserts `importlib.metadata.version("fastmcp") == "3.4.2"`, with a message that these facts were verified on 3.4.2 only

#### Scenario: Tool call is one span with core spans below it
- **GIVEN** telemetry initialised with an in-memory exporter and a memory added with `memory_add` (content `Acme parking uses OAuth.`, category `fact`)
- **WHEN** the client calls `memory_search` with the query `parking`
- **THEN** among exported spans of kind SERVER exactly one is named `tools/call memory_search`, and the `mintmory.search` span of that call is its descendant; a client of `mintmory-history-mcp` calling `history_stats` exports exactly one SERVER span `tools/call history_stats`

#### Scenario: A failing tool is marked
- **GIVEN** `mintmory.mcp.server._get_store` (the store accessor `memory_stats` calls) patched to raise `RuntimeError("SENTINEL-77")`
- **WHEN** the client calls `client.call_tool("memory_stats", {}, raise_on_error=False)`
- **THEN** the result has `is_error=True`; the SERVER span `tools/call memory_stats` has status ERROR with an empty description, `error.type=tool_error` and `exception` events whose only attribute is `exception.type=fastmcp.exceptions.ToolError`; and no exported span, event or status description contains `SENTINEL-77`

#### Scenario: Tool arguments never reach telemetry
- **WHEN** the client calls `memory_search` with the query `SENTINEL-ARG-4f` and `memory_note` with the text `SENTINEL-ARG-9a`
- **THEN** no exported span attribute, event or status description contains either sentinel

#### Scenario: Context in `_meta` is continued
- **WHEN** the client calls `client.session.call_tool("memory_stats", {}, meta={"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"})`
- **THEN** the `tools/call memory_stats` SERVER span has trace id `4bf92f3577b34da6a3ce929d0e0e4736` and parent span id `00f067aa0ba902b7`, and no CLIENT span is exported for that call

#### Scenario: Tool spans follow a new init
- **GIVEN** telemetry initialised with in-memory exporter A, one `memory_stats` call, then `telemetry.reset_telemetry()` and an init with in-memory exporter B
- **WHEN** a new client calls `memory_stats`
- **THEN** A holds exactly one SERVER span `tools/call memory_stats` and B holds exactly one

### Requirement: Outbound calls carry the trace context
`gen_ai.chat` SHALL be a CLIENT span with `server.address` (the URL host) and `server.port` (the URL port, else 443 for `https` and 80 for `http`); `mintmory.embed` stays INTERNAL. Every outbound LLM request (`llm.py`) and embedding request (`OllamaEmbedder`, `OpenAIEmbedder`) SHALL carry the W3C `traceparent` header, and `tracestate` when the span context has one, injected inside the span that wraps the request (`gen_ai.chat` or `mintmory.embed`), so that span is the remote side's parent. MintMory SHALL NOT forward `baggage` (the endpoints may be third-party). With telemetry off no header SHALL be added. The header helpers SHALL never raise. The chat request of the scenarios is `llm.post_chat_completion(base_url=f"http://127.0.0.1:{port}", api_key=None, payload={"model": "m", "messages": [{"role": "user", "content": "hi"}]}, timeout_s=5.0, system="test", model="m")` against a local `ThreadingHTTPServer` that records request headers and answers `/chat/completions` with the minimal JSON `packages/core/tests/test_llm.py` uses.

#### Scenario: LLM endpoint receives traceparent
- **GIVEN** telemetry initialised with an in-memory exporter and the test server on `127.0.0.1:<port>`
- **WHEN** the chat request is sent
- **THEN** the server received a `traceparent` whose trace id and parent span id are those of the exported `gen_ai.chat` span, and that span has kind CLIENT, `server.address=127.0.0.1` and `server.port=<port>`

#### Scenario: tracestate is forwarded, baggage is not
- **GIVEN** the same server, and a span opened with `telemetry.span("caller", context=telemetry.extract_context({"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01", "tracestate": "vendor=1", "baggage": "user=SENTINEL-BAG-3"}))`
- **WHEN** the chat request is sent inside that span
- **THEN** the server received `traceparent` with trace id `4bf92f3577b34da6a3ce929d0e0e4736`, `tracestate: vendor=1`, and no `baggage` header

#### Scenario: Embedding endpoints receive traceparent
- **GIVEN** telemetry initialised with an in-memory exporter, a local test HTTP server answering like Ollama's embedding endpoint, and `e = OpenAIEmbedder.__new__(OpenAIEmbedder)` with only `e._client` set to a stub whose `embeddings.create(**kwargs)` records `kwargs["extra_headers"]` and returns an object with `.data[0].embedding`
- **WHEN** `OllamaEmbedder` embeds one text against the server, and `e.embed("a")` runs
- **THEN** each received a `traceparent` whose parent span id is that of the `mintmory.embed` span exported for that call

#### Scenario: No header when telemetry is off
- **GIVEN** telemetry is not initialised
- **WHEN** the chat request is sent and `telemetry.inject_trace_headers({})` is called
- **THEN** the server received no `traceparent` header and the call returned `{}`
