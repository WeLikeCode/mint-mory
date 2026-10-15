# Capability: deployment (delta)

## MODIFIED Requirements

### Requirement: Telemetry activation at API startup
The REST API SHALL initialise OpenTelemetry at startup by calling the telemetry
activator with the configured OTel settings and the default service name `mintmory-api`.
Activation SHALL follow the observability capability's enablement modes: it SHALL be a
no-op when telemetry is off (`MINTMORY_OTEL_ENABLED=false`, `OTEL_SDK_DISABLED=true`, the
SDK not installed, or `auto` with no collector configured or answering). When telemetry
is on, the API SHALL emit its spans and metrics through the configured exporter, and the
lifespan SHALL flush them with a bounded shutdown when the application stops.

#### Scenario: OTel stays off by default
- **GIVEN** `MINTMORY_OTEL_ENABLED` is `auto` (default), no OTLP endpoint variable is set and nothing answers on the default endpoint
- **WHEN** the API starts
- **THEN** telemetry activation is a no-op and instrumentation remains a zero-cost shim.

#### Scenario: OTel activates when enabled
- **GIVEN** `MINTMORY_OTEL_ENABLED` is true and the OTel SDK is installed
- **WHEN** the API starts
- **THEN** telemetry is active and the API's spans and metrics are emitted through the configured exporter.

#### Scenario: Shutdown flushes with a bound
- **GIVEN** telemetry is active
- **WHEN** the API stops
- **THEN** the lifespan calls `shutdown_telemetry()` before closing the store.
