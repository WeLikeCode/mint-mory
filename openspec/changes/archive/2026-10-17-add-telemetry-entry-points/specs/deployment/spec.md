# Capability: deployment (delta)

## MODIFIED Requirements

### Requirement: Telemetry activation at API startup
The REST API SHALL initialise OpenTelemetry at startup by calling the telemetry
activator with the configured OTel settings and the default service name `mintmory-api`.
Activation SHALL follow the observability capability's enablement modes: it SHALL be a
no-op when telemetry is off (`MINTMORY_OTEL_ENABLED=false`, `OTEL_SDK_DISABLED=true`, the
SDK not installed, which logs one WARNING when `MINTMORY_OTEL_ENABLED=true` or `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` or `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` is set, or `auto` with no collector configured or answering), and
a failure inside activation SHALL leave telemetry off without stopping the API. When telemetry
is on, the API SHALL emit its spans and metrics through the configured exporter, and the
lifespan SHALL flush them with a bounded shutdown when the application stops.

#### Scenario: OTel stays off by default
- **GIVEN** `MINTMORY_OTEL_ENABLED` unset (`auto`), no OTLP endpoint variable, and `mintmory.core.telemetry._endpoint_reachable` patched to return False
- **WHEN** the API starts under `TestClient`
- **THEN** `telemetry.is_enabled()` is False and instrumentation remains a zero-cost shim.

#### Scenario: OTel activates when enabled
- **GIVEN** `MINTMORY_OTEL_ENABLED=true` (the `true` mode; a boolean true is normalised to it) and the OTel SDK is installed
- **WHEN** the API starts under `TestClient`
- **THEN** `telemetry.is_enabled()` is True, so the API's spans and metrics go through the configured exporter.

#### Scenario: Shutdown flushes with a bound
- **GIVEN** `mintmory.api.app.shutdown_telemetry` and the `close` of the store returned by a patched `mintmory.api.app.build_storage` both append to one call list
- **WHEN** the API starts and stops under `TestClient`
- **THEN** the list is `["shutdown_telemetry", "close"]`.
