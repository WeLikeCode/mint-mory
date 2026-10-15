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

### Requirement: Invalid telemetry configuration never stops MintMory
Loading settings and `init_telemetry` SHALL never raise for a bad telemetry value; each bad value SHALL log one WARNING and fall back: an unknown `MINTMORY_OTEL_ENABLED` to `auto`; an unknown `OTEL_TRACES_EXPORTER` or `OTEL_METRICS_EXPORTER` to the first known item of its comma-separated list, else `MINTMORY_OTEL_EXPORTER`; an `OTEL_EXPORTER_OTLP_PROTOCOL` other than `http/protobuf` to HTTP/protobuf; an unknown sampler or argument to the SDK's own fallback.

#### Scenario: Bad values fall back
- **GIVEN** `MINTMORY_OTEL_ENABLED=maybe`, `OTEL_TRACES_EXPORTER=jaeger,console`, `OTEL_EXPORTER_OTLP_PROTOCOL=grpc` and `OTEL_TRACES_SAMPLER=nonsense`
- **WHEN** settings load and `init_telemetry` runs with `_endpoint_reachable` patched to True
- **THEN** nothing raises, the mode is `auto`, traces go to the console exporter over stderr, and one WARNING per bad value is logged

### Requirement: Bounded flush on exit
`shutdown_telemetry(timeout_s=2.0)` SHALL flush and shut the providers down, return within `timeout_s` + 0.5 s whatever the collector state, and be safe to repeat. `init_telemetry` SHALL register it with `atexit` and create the providers with `shutdown_on_exit=False`. The API lifespan SHALL call it on stop.

#### Scenario: Exit is fast without a collector
- **GIVEN** telemetry enabled with the endpoint at a closed local port and spans pending
- **WHEN** `shutdown_telemetry(timeout_s=1.0)` runs
- **THEN** it returns within 1.5 s

#### Scenario: Pending spans are delivered on exit
- **GIVEN** telemetry enabled with the endpoint at a test HTTP receiver answering 200
- **WHEN** a span ends and `shutdown_telemetry()` runs at once
- **THEN** the receiver got a POST to `/v1/traces` containing that span

### Requirement: Resource identifies the process
`service.name` SHALL be, in order: `OTEL_SERVICE_NAME`, `service.name` in `OTEL_RESOURCE_ATTRIBUTES`, `MINTMORY_OTEL_SERVICE_NAME`, the entry point's default (`mintmory-api`, `mintmory-mcp`, `mintmory-history-mcp`, `mintmory-cli`). MintMory SHALL add `service.namespace=mintmory`, `service.version` (installed `mintmory-core`) and a random `service.instance.id`, which the same keys in `OTEL_RESOURCE_ATTRIBUTES` SHALL override.

#### Scenario: Entry point default name
- **GIVEN** no service-name variable
- **WHEN** the CLI initialises telemetry
- **THEN** spans carry `service.name=mintmory-cli` and a non-empty `service.version`

#### Scenario: Standard variables win
- **GIVEN** `OTEL_SERVICE_NAME=memo`, `MINTMORY_OTEL_SERVICE_NAME=other`, `OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=dev,service.namespace=team`
- **WHEN** any entry point initialises telemetry
- **THEN** spans carry `service.name=memo`, `deployment.environment.name=dev`, `service.namespace=team`

#### Scenario: Resource attributes beat the MintMory name
- **GIVEN** no `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES=service.name=attrs` and `MINTMORY_OTEL_SERVICE_NAME=other`
- **WHEN** any entry point initialises telemetry
- **THEN** spans carry `service.name=attrs`

### Requirement: Sampling and propagation follow the OpenTelemetry environment
The tracer provider SHALL take its sampler from `OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG` (default `parentbased_always_on`) and the process SHALL use the propagators of `OTEL_PROPAGATORS` (default W3C `tracecontext`, `baggage`).

#### Scenario: Sampling switched off
- **GIVEN** telemetry enabled with `OTEL_TRACES_SAMPLER=always_off`
- **WHEN** spans are created
- **THEN** none is exported

### Requirement: Telemetry test seam and global provider
`init_telemetry(settings=None, *, default_service_name="mintmory", span_exporter=None, metric_reader=None)` SHALL use an injected span exporter (synchronous processor) and metric reader instead of the configured exporters. Injection SHALL enable telemetry when the SDK imports, even with `MINTMORY_OTEL_ENABLED=false` or `OTEL_SDK_DISABLED=true`. Each successful init SHALL make its providers global, so library spans (FastMCP's) reach the same exporters. `reset_telemetry()` SHALL clear all of this.

#### Scenario: Injection beats the suite's off default
- **GIVEN** `MINTMORY_OTEL_ENABLED=false` (the root `conftest.py` default)
- **WHEN** `init_telemetry(span_exporter=InMemorySpanExporter())` runs and a span is created
- **THEN** it returns True and the span is in that exporter

#### Scenario: Re-initialisation in one process
- **GIVEN** telemetry initialised with one in-memory exporter, then reset
- **WHEN** it is initialised with a second in-memory exporter and spans are created through `telemetry.span` and `opentelemetry.trace.get_tracer("x")`
- **THEN** both spans are in the second exporter only
