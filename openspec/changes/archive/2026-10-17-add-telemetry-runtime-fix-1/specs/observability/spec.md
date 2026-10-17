# Spec Delta

## Purpose
MintMory's observability: OpenTelemetry traces and metrics from every entry point (CLI, REST API, MCP servers), safe and silent when no collector runs, distributed across HTTP, MCP and outbound LLM calls, with a local collector, Jaeger and Prometheus stack for development.

## ADDED Requirements

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
