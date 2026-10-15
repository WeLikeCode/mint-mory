# Capability: observability (delta)

## ADDED Requirements

### Requirement: Telemetry enablement modes
`MINTMORY_OTEL_ENABLED` SHALL accept `auto` (default), `true` and `false`. `false`, or `OTEL_SDK_DISABLED=true`, SHALL keep the no-op shim. `true` SHALL export when the SDK is installed. `auto` SHALL export only when the SDK is installed and either an OTLP endpoint variable is set or a TCP connection to the default endpoint's host and port succeeds within 100 ms; otherwise it SHALL stay no-op and SHALL NOT import `opentelemetry.sdk`.

#### Scenario: Auto with no collector stays off
- **GIVEN** `MINTMORY_OTEL_ENABLED` is unset, no `OTEL_EXPORTER_OTLP_*ENDPOINT` variable is set, and nothing listens on the default endpoint
- **WHEN** `init_telemetry` runs in a fresh Python process
- **THEN** it returns False, `is_enabled()` is False, and `opentelemetry.sdk` is not in `sys.modules`

#### Scenario: Auto with a listening collector turns on
- **GIVEN** `MINTMORY_OTEL_ENABLED` is unset and the endpoint probe reports the default endpoint reachable (tests patch `telemetry._endpoint_reachable`)
- **WHEN** `init_telemetry` runs
- **THEN** it returns True

#### Scenario: Auto with a configured endpoint turns on without probing
- **GIVEN** `OTEL_EXPORTER_OTLP_ENDPOINT` is set
- **WHEN** `init_telemetry` runs with the SDK installed
- **THEN** it returns True and `telemetry._endpoint_reachable` is not called

#### Scenario: Explicit off wins
- **GIVEN** `MINTMORY_OTEL_ENABLED=false`, or `OTEL_SDK_DISABLED=true` together with `MINTMORY_OTEL_ENABLED=true`
- **WHEN** `init_telemetry` runs
- **THEN** it returns False

#### Scenario: Endpoint configured but SDK missing
- **GIVEN** `OTEL_EXPORTER_OTLP_ENDPOINT` is set and `opentelemetry.sdk` cannot be imported
- **WHEN** `init_telemetry` runs
- **THEN** it returns False and logs exactly one WARNING that names the `otel` extra

### Requirement: Exporter selection and endpoint resolution
The default exporter SHALL be OTLP over HTTP/protobuf. Its endpoint SHALL follow the standard variables (`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` or `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` over `OTEL_EXPORTER_OTLP_ENDPOINT`), default `http://localhost:4318`. `OTEL_TRACES_EXPORTER` and `OTEL_METRICS_EXPORTER` (`otlp`, `console`, `none`) SHALL override `MINTMORY_OTEL_EXPORTER` per signal. Console exporters SHALL write to stderr only.

#### Scenario: Console output never reaches stdout
- **GIVEN** `MINTMORY_OTEL_ENABLED=true` and `MINTMORY_OTEL_EXPORTER=console`
- **WHEN** a span is created and telemetry is shut down
- **THEN** nothing is written to stdout and the span appears on stderr

#### Scenario: Metrics can be switched off alone
- **GIVEN** telemetry is enabled with `OTEL_METRICS_EXPORTER=none`
- **WHEN** `init_telemetry` runs
- **THEN** spans are exported and no metric reader or metric exporter is created

### Requirement: Export never blocks or floods when the collector is absent
Span and metric export SHALL run off the calling thread with bounded queues. Each export SHALL time out after `MINTMORY_OTEL_EXPORT_TIMEOUT_S` (default 3 seconds) unless a standard `OTEL_EXPORTER_OTLP_*TIMEOUT` variable is set. Export failures SHALL be logged at most once per signal until an export succeeds again, at WARNING when the endpoint was configured and at DEBUG for the implicit default, and SHALL never raise into application code.

#### Scenario: Unreachable collector does not slow the caller
- **GIVEN** telemetry is enabled with the endpoint at a closed local port
- **WHEN** application code creates 200 spans
- **THEN** creating them takes less than 0.5 seconds in total and raises nothing

#### Scenario: Unreachable collector logs once
- **GIVEN** telemetry is enabled with `OTEL_EXPORTER_OTLP_ENDPOINT` at a closed local port
- **WHEN** three export cycles fail
- **THEN** exactly one WARNING about the trace export is logged by `mintmory.telemetry` and no `opentelemetry` logger emits a record at WARNING or above

### Requirement: Bounded flush on exit
`shutdown_telemetry(timeout_s=2.0)` SHALL flush pending telemetry and shut the providers down, return within `timeout_s` plus 0.5 seconds whatever the collector state, and be safe to call more than once. `init_telemetry` SHALL register it with `atexit` and create the SDK providers with `shutdown_on_exit=False`. The API lifespan SHALL call it when the application stops.

#### Scenario: Exit is fast without a collector
- **GIVEN** telemetry is enabled with the endpoint at a closed local port and spans are pending
- **WHEN** `shutdown_telemetry(timeout_s=1.0)` is called
- **THEN** it returns within 1.5 seconds

#### Scenario: Pending spans are delivered on exit
- **GIVEN** telemetry is enabled with the endpoint at a local test HTTP receiver that answers 200
- **WHEN** a span ends and `shutdown_telemetry()` is called at once
- **THEN** the receiver has received a POST to `/v1/traces` that contains that span

### Requirement: Resource identifies the process
`service.name` SHALL be, in order: `OTEL_SERVICE_NAME`, `service.name` in `OTEL_RESOURCE_ATTRIBUTES`, `MINTMORY_OTEL_SERVICE_NAME`, then the entry point's default (`mintmory-api`, `mintmory-mcp`, `mintmory-history-mcp`, `mintmory-cli`). MintMory SHALL add `service.namespace` = `mintmory`, `service.version` = the installed `mintmory-core` version and a random `service.instance.id`; other keys of `OTEL_RESOURCE_ATTRIBUTES` SHALL override these defaults.

#### Scenario: Entry point default name
- **GIVEN** no service-name variable is set
- **WHEN** the CLI initialises telemetry
- **THEN** exported spans carry `service.name` = `mintmory-cli` and a non-empty `service.version`

#### Scenario: Standard variables win
- **GIVEN** `OTEL_SERVICE_NAME=memo`, `MINTMORY_OTEL_SERVICE_NAME=other` and `OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=dev,service.namespace=team`
- **WHEN** any entry point initialises telemetry
- **THEN** exported spans carry `service.name` = `memo`, `deployment.environment.name` = `dev` and `service.namespace` = `team`

### Requirement: Sampling and propagation follow the OpenTelemetry environment
The tracer provider SHALL use the SDK's sampler from `OTEL_TRACES_SAMPLER` and `OTEL_TRACES_SAMPLER_ARG`, defaulting to `parentbased_always_on`, and the process SHALL use the propagators named by `OTEL_PROPAGATORS`, defaulting to W3C `tracecontext` and `baggage`.

#### Scenario: Sampling switched off
- **GIVEN** telemetry is enabled with `OTEL_TRACES_SAMPLER=always_off`
- **WHEN** spans are created
- **THEN** none is exported

### Requirement: Every entry point initialises telemetry once
The CLI SHALL initialise telemetry in a Typer callback before any command except `serve` and `mcp-serve`, which hand over to the API and MCP entry points. The API lifespan, `mintmory-mcp` and `mintmory-history-mcp` SHALL each call `init_telemetry` once with their default service name. After a successful init, a later `init_telemetry` call SHALL change nothing and return True; a call that returns False SHALL leave no state behind.

#### Scenario: CLI command is traced
- **GIVEN** a test OTLP receiver configured through `OTEL_EXPORTER_OTLP_ENDPOINT` and `MINTMORY_OTEL_ENABLED=true`
- **WHEN** `mintmory add` runs through the Typer test runner and telemetry is shut down
- **THEN** a `mintmory.add_memory` span with `service.name` = `mintmory-cli` reaches the receiver

#### Scenario: History MCP server initialises telemetry
- **WHEN** `mintmory-history-mcp`'s `main()` starts the server
- **THEN** `init_telemetry` was called once, before the server runs, with `default_service_name="mintmory-history-mcp"`

### Requirement: Telemetry test seam and global provider
`init_telemetry(settings=None, *, default_service_name="mintmory", span_exporter=None, metric_reader=None)` SHALL use an injected span exporter (through a synchronous span processor) and metric reader instead of the configured exporters, and enable telemetry when either is given and the SDK imports, whatever `settings.enabled` says. Each successful init SHALL make its providers the global ones, so library spans (FastMCP's) reach the same exporters. `reset_telemetry()` SHALL clear all of this.

#### Scenario: Re-initialisation in one process
- **GIVEN** telemetry was initialised with one in-memory exporter and then reset
- **WHEN** it is initialised again with a second in-memory exporter and a span is created through `telemetry.span` and another through `opentelemetry.trace.get_tracer("x")`
- **THEN** both spans are in the second exporter only
