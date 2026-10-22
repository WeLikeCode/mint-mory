# Spec Delta

## Purpose
MintMory's observability: OpenTelemetry traces and metrics from every entry point (CLI, REST API, MCP servers), safe and silent when no collector runs, distributed across HTTP, MCP and outbound LLM calls, with a local collector, Jaeger and Prometheus stack for development.

## ADDED Requirements

### Requirement: Rejected hold: the diff is longer than 120000 characters: the judge saw only the start — finding H-e0757174
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: Rejected hold: the diff is longer than 120000 characters: the judge saw only the start
- **WHEN** the meter, a counter's add, a histogram's record or a span's set_attribute raises inside a telemetry helper (counts_added, add_count, record_value, the span attributes of embed_span and file_span)
- **THEN** the error stays inside telem
