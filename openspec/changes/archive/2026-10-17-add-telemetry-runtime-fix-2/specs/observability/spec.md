# Spec Delta

## Purpose
MintMory's observability: OpenTelemetry traces and metrics from every entry point (CLI, REST API, MCP servers), safe and silent when no collector runs, distributed across HTTP, MCP and outbound LLM calls, with a local collector, Jaeger and Prometheus stack for development.

## ADDED Requirements

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
