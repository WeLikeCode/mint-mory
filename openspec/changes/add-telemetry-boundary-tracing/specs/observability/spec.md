# Capability: observability (delta)

## Purpose

MintMory's observability: OpenTelemetry traces and metrics from every entry point (CLI, REST API, MCP servers), safe and silent when no collector runs, distributed across HTTP, MCP and outbound LLM calls, with a local collector, Jaeger and Prometheus stack for development.

## ADDED Requirements

### Requirement: HTTP server spans continue the caller's trace
Each API request, except excluded paths, SHALL run in a SERVER span named `<METHOD> <route template>` (`<METHOD>` alone when no route matched) that continues the W3C context of the request headers, with `http.request.method`, `http.route` and `http.response.status_code`, and without the raw path. A 5xx response or an unhandled exception SHALL set status ERROR and `error.type`.

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

### Requirement: Excluded HTTP paths
`/healthz` and `/readyz` SHALL NOT be traced, nor a path for which `re.search` finds one of the comma-separated regexes of `OTEL_PYTHON_EXCLUDED_URLS` in the request path (no query string). The variable SHALL be read on each request; items are stripped, empty items ignored, and an item that is not a valid regex skipped with one WARNING per distinct value, never failing a request.

#### Scenario: Excluded by the environment
- **GIVEN** the module-level `app` from `mintmory.api.app` and, set with `monkeypatch.setenv` after import, `OTEL_PYTHON_EXCLUDED_URLS=^/stats$,/summaries`
- **WHEN** `GET /stats` and `GET /summaries` are called
- **THEN** no span is exported for them, and `GET /memories/<an existing id>` is still traced

#### Scenario: Empty items exclude nothing
- **GIVEN** `OTEL_PYTHON_EXCLUDED_URLS=" , ^/stats$ ,"`
- **WHEN** `GET /stats` and `GET /memories/<an existing id>` are called
- **THEN** `GET /stats` is not traced and the memory request is

#### Scenario: A bad exclusion pattern is skipped
- **GIVEN** `OTEL_PYTHON_EXCLUDED_URLS=([,^/stats$`
- **WHEN** `GET /stats` and `GET /memories/<an existing id>` are called twice each
- **THEN** both answer as without telemetry, `GET /stats` is not traced, the memory request is, and one WARNING names the bad pattern

### Requirement: Unmatched and failing HTTP requests
A request that matches no route SHALL be traced as `<METHOD>` alone. A 5xx response or an unhandled exception SHALL set status ERROR and `error.type` (the status code, or the exception class name); an unhandled exception records `http.response.status_code` = 500 on the span and the duration point. The runtime's scrubber removes exception messages at export.

#### Scenario: No route matched
- **WHEN** `GET /no-such-path` is called
- **THEN** a span named `GET` with `http.response.status_code` = 404 is exported and has no `http.route`

#### Scenario: A route that raises
- **GIVEN** a test route added to the app that raises `RuntimeError`
- **WHEN** it is called with `TestClient(app, raise_server_exceptions=False)`
- **THEN** its span has status ERROR, `error.type` = `RuntimeError` and `http.response.status_code` = 500, the duration histogram has a point with status 500, and no exported span, event or status description contains the exception's message

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

#### Scenario: A failing tool is marked
- **GIVEN** the store accessor the tool uses patched to raise `RuntimeError("SENTINEL-77")`
- **WHEN** the client calls `memory_stats`
- **THEN** the `tools/call memory_stats` span has status ERROR, and no exported span, event or status description contains `SENTINEL-77` (FastMCP's exception event keeps only `exception.type` after the runtime's scrubber)

#### Scenario: History MCP tool is traced
- **WHEN** a `fastmcp.Client` connected in memory to `mintmory-history-mcp` calls `history_stats`
- **THEN** one `tools/call history_stats` span with kind SERVER is exported

#### Scenario: Tool arguments never reach telemetry
- **WHEN** the client calls `memory_search` with the query `SENTINEL-ARG-4f` and `memory_note` with the text `SENTINEL-ARG-9a`
- **THEN** no exported span attribute, event or status description contains either sentinel (FastMCP 3.4.2 records the method, server, component, tool name and auth/session ids, never arguments)

#### Scenario: Context in `_meta` is continued
- **WHEN** the client sends the call through the MCP session, `client.session.call_tool("memory_stats", {}, meta={"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"})` (`fastmcp.Client.call_tool` would replace `traceparent` with its own span's)
- **THEN** the `tools/call memory_stats` span has trace id `4bf92f3577b34da6a3ce929d0e0e4736` and parent span id `00f067aa0ba902b7`

### Requirement: Outbound calls carry the trace context
`gen_ai.chat` SHALL be a CLIENT span with `server.address` and `server.port` of the endpoint. Every outbound LLM request (`llm.py`) and embedding request (`OllamaEmbedder`, `OpenAIEmbedder`) SHALL carry the W3C `traceparent` header (and `tracestate`, `baggage` when present), injected inside the span that wraps the request, `gen_ai.chat` or `mintmory.embed`, so that span is the remote side's parent. With telemetry off, no header SHALL be added.

#### Scenario: LLM endpoint receives traceparent
- **GIVEN** telemetry initialised with an in-memory exporter and a local test HTTP server that answers like an OpenAI-compatible `/chat/completions`
- **WHEN** MintMory's LLM client sends one chat request to it
- **THEN** the server received a `traceparent` header whose trace id and parent span id are those of the exported `gen_ai.chat` span, and that span has kind CLIENT

#### Scenario: Embedding endpoint receives traceparent
- **GIVEN** telemetry initialised with an in-memory exporter and a local test HTTP server that answers like Ollama's embedding endpoint
- **WHEN** `OllamaEmbedder` embeds one text against it
- **THEN** the server received a `traceparent` header whose parent span id is that of the exported `mintmory.embed` span

#### Scenario: No header when telemetry is off
- **GIVEN** telemetry is not initialised
- **WHEN** the same chat request is sent
- **THEN** the server received no `traceparent` header
