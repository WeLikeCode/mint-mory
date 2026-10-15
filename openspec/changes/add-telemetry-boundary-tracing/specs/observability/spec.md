# Capability: observability (delta)

## ADDED Requirements

### Requirement: HTTP server spans continue the caller's trace
Each API request, except `/healthz`, `/readyz` and paths matched by `OTEL_PYTHON_EXCLUDED_URLS`, SHALL run in a SERVER span named `<METHOD> <route template>` (`<METHOD>` alone when no route matched) that continues the W3C context of the request headers, with `http.request.method`, `http.route` and `http.response.status_code`, and without the raw path. A 5xx response or an unhandled exception SHALL set status ERROR and `error.type`.

#### Scenario: Incoming traceparent is continued
- **GIVEN** telemetry initialised with an in-memory exporter and the API under `TestClient`
- **WHEN** `POST /memories/search` is sent with `traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
- **THEN** a SERVER span named `POST /memories/search` is exported with trace id `4bf92f3577b34da6a3ce929d0e0e4736` and parent span id `00f067aa0ba902b7`, and the `mintmory.search` span of that request is its descendant

#### Scenario: Route template, not the raw path, names the span
- **WHEN** `GET /memories/<an existing id>` is called
- **THEN** the span is named `GET /memories/{memory_id}`, `http.route` is `/memories/{memory_id}`, and no attribute value contains the id

#### Scenario: Health probes are not traced
- **WHEN** `GET /healthz` and `GET /readyz` are called
- **THEN** no span is exported for them

### Requirement: HTTP server duration metric
The API SHALL record each traced request in the histogram `http.server.request.duration` (unit `s`, bucket boundaries 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5 and 10) with the attributes `http.request.method`, `http.route` and `http.response.status_code`.

#### Scenario: Request duration recorded
- **GIVEN** telemetry initialised with an in-memory metric reader
- **WHEN** two `GET /stats` requests are sent
- **THEN** the histogram has a point for `http.route=/stats` with a count of 2

### Requirement: MCP tool calls are traced once
Each MCP tool call in `mintmory-mcp` and `mintmory-history-mcp` SHALL be traced by FastMCP's native SERVER span `tools/call <tool>` (scope `fastmcp`, with `mcp.method.name` and `gen_ai.tool.name`), which continues a W3C `traceparent` from the request's `_meta`. MintMory SHALL NOT create a second span per tool call. Spans created by the tool SHALL be its descendants; a failing tool's span SHALL have status ERROR.

#### Scenario: Tool call is one span with core spans below it
- **GIVEN** telemetry initialised with an in-memory exporter
- **WHEN** a `fastmcp.Client` connected in memory to `mintmory-mcp` calls `memory_search`
- **THEN** exactly one span named `tools/call memory_search` with kind SERVER is exported, and the `mintmory.search` span of that call is its descendant

#### Scenario: Context in `_meta` is continued
- **WHEN** the client sends the call through the MCP session, `client.session.call_tool("memory_stats", {}, meta={"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"})` (`fastmcp.Client.call_tool` would replace `traceparent` with its own span's)
- **THEN** the `tools/call memory_stats` span has trace id `4bf92f3577b34da6a3ce929d0e0e4736` and parent span id `00f067aa0ba902b7`

### Requirement: Outbound calls carry the trace context
`gen_ai.chat` SHALL be a CLIENT span with `server.address` and `server.port` of the endpoint. Every outbound LLM request (`llm.py`) and embedding request (`OllamaEmbedder`, `OpenAIEmbedder`) SHALL carry the W3C `traceparent` header, and `tracestate` and `baggage` when present, injected inside its client span, so the remote side's parent is that span. With telemetry off, no header SHALL be added.

#### Scenario: LLM endpoint receives traceparent
- **GIVEN** telemetry initialised with an in-memory exporter and a local test HTTP server that answers like an OpenAI-compatible `/chat/completions`
- **WHEN** MintMory's LLM client sends one chat request to it
- **THEN** the server received a `traceparent` header whose trace id and parent span id are those of the exported `gen_ai.chat` span, and that span has kind CLIENT

#### Scenario: No header when telemetry is off
- **GIVEN** telemetry is not initialised
- **WHEN** the same chat request is sent
- **THEN** the server received no `traceparent` header
