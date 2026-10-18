# Spec Delta

## Purpose
Regression scenarios for the observability capability, found by the verifier in add-telemetry-boundary-tracing.

## ADDED Requirements

### Requirement: Guard route.path and the status comparison in the middleware's finally — feedback FB-001
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: Guard route.path and the status comparison in the middleware's finally
- **WHEN** the matched route in scope["route"] has no path attribute, or the response status the app sent is not an int
- **THEN** the middleware still returns or raises exactly what the app did, and the request span is ended

### Requirement: Telemetry must not change what an LLM call raises: reading — feedback FB-002
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: Telemetry must not change what an LLM call raises: reading
- **WHEN** post_chat_completion is called with a base_url whose port is malformed (for example :abc or :99999)
- **THEN** it raises the same exception class as it did before telemetry was added (http.client.InvalidURL or urllib.error.URLError), not ValueError from reading the port
