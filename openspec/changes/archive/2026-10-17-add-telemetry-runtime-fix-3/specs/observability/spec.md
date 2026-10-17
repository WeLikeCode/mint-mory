# Spec Delta

## Purpose
MintMory's observability: OpenTelemetry traces and metrics from every entry point (CLI, REST API, MCP servers), safe and silent when no collector runs, distributed across HTTP, MCP and outbound LLM calls, with a local collector, Jaeger and Prometheus stack for development.

## ADDED Requirements

### Requirement: an injected exporter without the SDK says why telemetry is off — feedback FB-006
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: an injected exporter without the SDK says why telemetry is off
- **WHEN** init_telemetry() is called with a span_exporter or a metric_reader and the OpenTelemetry SDK is not installed (_sdk_available() returns False)
- **THEN** it returns False, installs no provider, and logs exactly one WARNING on the mintmory.telemetry logger that names the missing SDK and mintmory-core[otel]
