# Capability: observability (delta)

## ADDED Requirements

### Requirement: Telemetry enablement modes
`MINTMORY_OTEL_ENABLED` SHALL accept `auto` (default), `true` and `false`. `false`, or `OTEL_SDK_DISABLED=true`, SHALL keep the no-op shim. `true` SHALL export when the SDK is installed. `auto` SHALL export only when the SDK is installed and an OTLP endpoint variable is set or a TCP connection to the default endpoint succeeds within 100 ms; otherwise it SHALL stay no-op without importing `opentelemetry.sdk`.

#### Scenario: Auto with no collector stays off
- **GIVEN** no `MINTMORY_OTEL_ENABLED`, no `OTEL_EXPORTER_OTLP_*ENDPOINT`, and `telemetry._endpoint_reachable` patched to return False
- **WHEN** `init_telemetry` runs in a fresh Python process
- **THEN** it returns False and `opentelemetry.sdk` is not in `sys.modules`

#### Scenario: Auto turns on with a collector
- **GIVEN** no `MINTMORY_OTEL_ENABLED`, and either `_endpoint_reachable` patched to return True, or `OTEL_EXPORTER_OTLP_ENDPOINT` set
- **WHEN** `init_telemetry` runs
- **THEN** it returns True, and with the endpoint variable set `_endpoint_reachable` is not called

#### Scenario: Explicit off wins
- **GIVEN** `MINTMORY_OTEL_ENABLED=false`, or `OTEL_SDK_DISABLED=true` with `MINTMORY_OTEL_ENABLED=true`
- **WHEN** `init_telemetry` runs without an injected exporter or reader
- **THEN** it returns False

#### Scenario: Endpoint configured but SDK missing
- **GIVEN** any of `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` set and `opentelemetry.sdk` not importable
- **WHEN** `init_telemetry` runs
- **THEN** it returns False and logs one WARNING naming the `otel` extra

### Requirement: Exporter selection and endpoint resolution
The default exporter SHALL be OTLP over HTTP/protobuf to the endpoint named by the standard `OTEL_EXPORTER_OTLP_*ENDPOINT` variables, default `http://localhost:4318`. `OTEL_TRACES_EXPORTER` and `OTEL_METRICS_EXPORTER` (`otlp`, `console`, `none`) SHALL override `MINTMORY_OTEL_EXPORTER` per signal. Console exporters SHALL write to stderr only.

#### Scenario: Console output never reaches stdout
- **GIVEN** `MINTMORY_OTEL_ENABLED=true`, `MINTMORY_OTEL_EXPORTER=console`
- **WHEN** a span is created and telemetry is shut down
- **THEN** stdout is empty and the span is on stderr

#### Scenario: Metrics can be switched off alone
- **GIVEN** telemetry enabled with `OTEL_METRICS_EXPORTER=none`
- **WHEN** `init_telemetry` runs
- **THEN** spans are exported and no metric reader or exporter exists

### Requirement: Export never blocks or floods when the collector is absent
Export SHALL run off the calling thread with bounded queues and time out after `MINTMORY_OTEL_EXPORT_TIMEOUT_S` (default 3 s) unless a standard `OTEL_EXPORTER_OTLP_*TIMEOUT` is set. Failures SHALL be logged at most once per signal until an export succeeds again (WARNING when an endpoint was configured, DEBUG for the implicit default) and SHALL never raise into application code.

#### Scenario: Unreachable collector does not slow the caller
- **GIVEN** telemetry enabled with the endpoint at a closed local port
- **WHEN** application code creates 200 spans
- **THEN** that takes under 0.5 s and raises nothing

#### Scenario: Unreachable collector logs once
- **GIVEN** telemetry enabled with `OTEL_EXPORTER_OTLP_ENDPOINT` at a closed local port
- **WHEN** three export cycles fail
- **THEN** `mintmory.telemetry` logs exactly one WARNING about trace export and no `opentelemetry` logger emits WARNING or above

### Requirement: Invalid MintMory telemetry settings fall back
Loading settings SHALL never raise for a bad `MINTMORY_OTEL_*` value: each bad value SHALL log one WARNING and fall back, an unknown `MINTMORY_OTEL_ENABLED` to `auto`, an unknown `MINTMORY_OTEL_EXPORTER` to `otlp`, and a non-numeric or non-positive `MINTMORY_OTEL_EXPORT_TIMEOUT_S` to 3.

#### Scenario: Bad MintMory values fall back
- **GIVEN** `MINTMORY_OTEL_ENABLED=maybe`, `MINTMORY_OTEL_EXPORTER=jaeger` and `MINTMORY_OTEL_EXPORT_TIMEOUT_S=abc`
- **WHEN** settings load
- **THEN** nothing raises, the mode is `auto`, the exporter setting is `otlp`, the timeout is 3, and three WARNINGs are logged

### Requirement: Invalid standard OpenTelemetry variables fall back
`init_telemetry` SHALL never raise for a bad standard variable: an unknown `OTEL_TRACES_EXPORTER` or `OTEL_METRICS_EXPORTER` SHALL fall back to the first known item of its comma-separated list, else to `MINTMORY_OTEL_EXPORTER`; an `OTEL_EXPORTER_OTLP_PROTOCOL` other than `http/protobuf` to HTTP/protobuf; an unknown sampler or argument to the SDK's own fallback; each with one WARNING.

#### Scenario: Bad standard values fall back
- **GIVEN** `OTEL_TRACES_EXPORTER=jaeger,console`, `OTEL_EXPORTER_OTLP_PROTOCOL=grpc` and `OTEL_TRACES_SAMPLER=nonsense`, with `_endpoint_reachable` patched to True
- **WHEN** `init_telemetry` runs
- **THEN** nothing raises, traces go to the console exporter over stderr, and one WARNING per bad value is logged

### Requirement: Bounded flush on exit
`shutdown_telemetry(timeout_s=2.0)` SHALL flush and shut the providers down, return within `timeout_s` + 0.5 s whatever the collector state, be safe to repeat, and leave the module as `reset_telemetry()` does, so a later `init_telemetry` initialises again. `init_telemetry` SHALL register it with `atexit` and create the providers with `shutdown_on_exit=False`.

#### Scenario: Exit is fast without a collector
- **GIVEN** telemetry enabled with the endpoint at a closed local port and spans pending
- **WHEN** `shutdown_telemetry(timeout_s=1.0)` runs
- **THEN** it returns within 1.5 s

#### Scenario: Init after shutdown works
- **WHEN** telemetry is initialised with an in-memory exporter, shut down, then initialised with a second in-memory exporter and a span is created
- **THEN** the second init returns True and the span is in the second exporter

#### Scenario: Pending spans are delivered on exit
- **GIVEN** telemetry enabled with the endpoint at a test HTTP receiver answering 200
- **WHEN** a span ends and `shutdown_telemetry()` runs at once
- **THEN** the receiver got a POST to `/v1/traces` containing that span

### Requirement: Resource identifies the process
`service.name` SHALL be, in order: `OTEL_SERVICE_NAME`, `service.name` in `OTEL_RESOURCE_ATTRIBUTES`, `MINTMORY_OTEL_SERVICE_NAME`, the entry point's default (`mintmory-api`, `mintmory-mcp`, `mintmory-history-mcp`, `mintmory-cli`). MintMory SHALL add `service.namespace=mintmory`, `service.version` (installed `mintmory-core`) and a random `service.instance.id`, which the same keys in `OTEL_RESOURCE_ATTRIBUTES` SHALL override.

#### Scenario: The caller's default name
- **GIVEN** no service-name variable
- **WHEN** `init_telemetry(default_service_name="mintmory-cli", span_exporter=...)` runs and a span is created
- **THEN** the span carries `service.name=mintmory-cli` and a non-empty `service.version`

#### Scenario: Standard variables win
- **GIVEN** `OTEL_SERVICE_NAME=memo`, `MINTMORY_OTEL_SERVICE_NAME=other`, `OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=dev,service.namespace=team`
- **WHEN** `init_telemetry(default_service_name="mintmory-cli", span_exporter=...)` runs
- **THEN** spans carry `service.name=memo`, `deployment.environment.name=dev`, `service.namespace=team`

#### Scenario: Resource attributes beat the MintMory name
- **GIVEN** no `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES=service.name=attrs` and `MINTMORY_OTEL_SERVICE_NAME=other`
- **WHEN** `init_telemetry(default_service_name="mintmory-cli", span_exporter=...)` runs
- **THEN** spans carry `service.name=attrs`

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
Every exporter, configured or injected, SHALL receive spans through a scrubber: in an `exception` event only `exception.type` is kept (`exception.message` and `exception.stacktrace` are dropped), and an ERROR status loses its description. This holds for MintMory's spans and for spans a library creates (FastMCP's).

#### Scenario: A library's exception is scrubbed
- **GIVEN** telemetry initialised with an in-memory exporter
- **WHEN** a span from `opentelemetry.trace.get_tracer("x")` records `RuntimeError("SENTINEL-91c2")` and ends with status ERROR
- **THEN** the exported span has an `exception` event with `exception.type=RuntimeError`, no attribute or status description contains the sentinel

### Requirement: Telemetry test seam
`init_telemetry(settings=None, *, default_service_name="mintmory", span_exporter=None, metric_reader=None)` SHALL use an injected span exporter (through a synchronous processor) and metric reader instead of the configured exporters. Injection SHALL enable telemetry when the SDK imports, even with `MINTMORY_OTEL_ENABLED=false` or `OTEL_SDK_DISABLED=true`. `reset_telemetry()` SHALL clear all telemetry state.

#### Scenario: Injection beats the suite's off default
- **GIVEN** `MINTMORY_OTEL_ENABLED=false` (the root `conftest.py` default)
- **WHEN** `init_telemetry(span_exporter=InMemorySpanExporter())` runs and a span is created
- **THEN** it returns True and the span is in that exporter

### Requirement: Global providers and repeated init
Each successful init SHALL make its providers the global ones, so library spans (FastMCP's) reach the same exporters. After a successful init, a later `init_telemetry` SHALL change nothing and return True; a call returning False SHALL leave no state.

#### Scenario: A second init changes nothing
- **GIVEN** telemetry initialised with an in-memory exporter
- **WHEN** `init_telemetry` is called again with other settings
- **THEN** it returns True and spans still go to the first exporter

#### Scenario: Re-initialisation in one process
- **GIVEN** telemetry initialised with one in-memory exporter, then reset
- **WHEN** it is initialised with a second in-memory exporter and spans are created through `telemetry.span` and `opentelemetry.trace.get_tracer("x")`
- **THEN** both spans are in the second exporter only
