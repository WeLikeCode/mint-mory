# Capability: observability (delta)

## Purpose

MintMory's observability: OpenTelemetry traces and metrics from every entry point (CLI, REST API, MCP servers), safe and silent when no collector runs, distributed across HTTP, MCP and outbound LLM calls, with a local collector, Jaeger and Prometheus stack for development.

## ADDED Requirements

### Requirement: HTTP server spans continue the caller's trace
Each API request, except excluded paths, SHALL run in a SERVER span named `<METHOD> <route template>` that continues the W3C context of the request headers, with `http.request.method`, `http.route` and `http.response.status_code`, and without `url.path`, `url.query` or any other raw path value. A missing or malformed `traceparent` SHALL start a new trace and never fail the request. Failures are marked as stated in "Unmatched and failing HTTP requests".

#### Scenario: Incoming traceparent is continued
- **GIVEN** telemetry initialised with an injected in-memory span exporter and metric reader, and the API under `TestClient`
- **WHEN** `POST /memories/search` is sent with `traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
- **THEN** a SERVER span named `POST /memories/search` is exported with trace id `4bf92f3577b34da6a3ce929d0e0e4736` and parent span id `00f067aa0ba902b7`, and the `mintmory.search` span of that request is its descendant

#### Scenario: A malformed traceparent starts a new trace
- **WHEN** `GET /stats` is sent with `traceparent: garbage`
- **THEN** it answers 200 and its SERVER span has no parent and a trace id other than `4bf92f3577b34da6a3ce929d0e0e4736`

#### Scenario: Route template, not the raw path, names the span
- **WHEN** `GET /memories/<an existing id>?verbose=1` is called
- **THEN** the span is named `GET /memories/{memory_id}`, `http.route` is `/memories/{memory_id}`, it has no `url.path` or `url.query` attribute, and no attribute value contains the id

### Requirement: Excluded HTTP paths
`/healthz` and `/readyz` (exact path match) SHALL NOT be traced, nor a path in which `re.search` finds one of the comma-separated regexes of `OTEL_PYTHON_EXCLUDED_URLS` (the path only, no query string). The variable SHALL be read on each request; items are stripped, empty items ignored, and an item that is not a valid regex skipped with one WARNING on `mintmory.telemetry` per distinct value, never failing a request.

#### Scenario: Health probes are not traced
- **WHEN** `GET /healthz`, `GET /readyz` and `GET /healthz/x` are called
- **THEN** no span is exported for the first two, and `GET /healthz/x` (404) is traced as `GET`

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
- **THEN** both answer as without telemetry, `GET /stats` is not traced, the memory request is, and `mintmory.telemetry` logged exactly one WARNING, containing `([`

### Requirement: Unmatched and failing HTTP requests
A request that matches no route SHALL be traced as `<METHOD>` alone. A 5xx response or an unhandled exception SHALL mark the span with `telemetry.mark_error(span, error_type)` from `add-telemetry-runtime`, with `error_type` the status code as a string or the exception class name. An exception before the response started records `http.response.status_code` = 500 on the span and the duration point; after it started, the sent status is kept. `asyncio.CancelledError` (client gone) SHALL end the span unmarked and propagate. The runtime's scrubber removes exception messages at export.

#### Scenario: No route matched
- **WHEN** `GET /no-such-path` is called
- **THEN** a span named `GET` with `http.response.status_code` = 404 is exported and has no `http.route`

#### Scenario: A route that raises
- **GIVEN** a test route added to the app that raises `RuntimeError("SENTINEL-55")`
- **WHEN** it is called with `TestClient(app, raise_server_exceptions=False)`
- **THEN** its span has status ERROR, `error.type=RuntimeError` and `http.response.status_code` = 500, the duration histogram has a point with status 500, and no exported span, event or status description contains `SENTINEL-55`

### Requirement: HTTP server duration metric
The API SHALL record each traced request in the histogram `http.server.request.duration` (unit `s`, explicit bucket boundaries 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5 and 10) with the attributes `http.request.method`, `http.route` (absent when no route matched) and `http.response.status_code`.

#### Scenario: Request duration recorded
- **GIVEN** telemetry initialised with an injected in-memory span exporter and metric reader
- **WHEN** two `GET /stats` requests are sent
- **THEN** `InMemoryMetricReader.get_metrics_data()` has the metric `http.server.request.duration` with unit `s` and one point for `http.route=/stats`, `http.request.method=GET`, `http.response.status_code=200`, with `count` 2 and `explicit_bounds` `(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)`

### Requirement: MCP tool calls are traced once
Each MCP tool call in `mintmory-mcp` and `mintmory-history-mcp` SHALL be traced by FastMCP's native SERVER span `tools/call <tool>` (FastMCP 3.4.2 `fastmcp/server/telemetry.py` `server_span`: scope `fastmcp`, `mcp.method.name`, `gen_ai.tool.name`; on an exception it sets `error.type` and status ERROR), which continues a W3C `traceparent` from the request's `_meta`. MintMory SHALL NOT create a second span per tool call. Spans created by the tool SHALL be its descendants.

#### Scenario: Tool call is one span with core spans below it
- **GIVEN** telemetry initialised with an in-memory exporter
- **WHEN** a `fastmcp.Client` connected in memory to `mintmory-mcp` calls `memory_search`
- **THEN** among exported spans of kind SERVER exactly one is named `tools/call memory_search` (the in-memory client adds its own CLIENT span of that name), and the `mintmory.search` span of that call is its descendant

#### Scenario: A failing tool is marked
- **GIVEN** `mintmory.mcp.server._get_store` (the store accessor `memory_stats` calls) patched to raise `RuntimeError("SENTINEL-77")`
- **WHEN** the client calls `memory_stats`
- **THEN** the SERVER span `tools/call memory_stats` has status ERROR, and no exported span, event or status description contains `SENTINEL-77`

#### Scenario: History MCP tool is traced
- **WHEN** a `fastmcp.Client` connected in memory to `mintmory-history-mcp` calls `history_stats`
- **THEN** one `tools/call history_stats` span with kind SERVER is exported

#### Scenario: Tool arguments never reach telemetry
- **WHEN** the client calls `memory_search` with the query `SENTINEL-ARG-4f` and `memory_note` with the text `SENTINEL-ARG-9a`
- **THEN** no exported span attribute, event or status description contains either sentinel (FastMCP 3.4.2 records the method, server, component, tool name and auth/session ids, never arguments)

#### Scenario: Context in `_meta` is continued
- **WHEN** the client sends the call through the MCP session, `client.session.call_tool("memory_stats", {}, meta={"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"})` (`fastmcp.Client.call_tool` would replace `traceparent` with its own span's)
- **THEN** the `tools/call memory_stats` SERVER span has trace id `4bf92f3577b34da6a3ce929d0e0e4736` and parent span id `00f067aa0ba902b7`

### Requirement: Outbound calls carry the trace context
`gen_ai.chat` SHALL be a CLIENT span with `server.address` (the URL host) and `server.port` (the URL port, else 443 for `https` and 80 for `http`); `mintmory.embed` stays INTERNAL. Every outbound LLM request (`llm.py`) and embedding request (`OllamaEmbedder`, `OpenAIEmbedder`) SHALL carry the W3C `traceparent` header, and `tracestate` when the span context has one, injected inside the span that wraps the request (`gen_ai.chat` or `mintmory.embed`), so that span is the remote side's parent. MintMory SHALL NOT forward `baggage` to these endpoints, which may be third-party providers. With telemetry off no header SHALL be added. The header helpers SHALL never raise.

#### Scenario: LLM endpoint receives traceparent
- **GIVEN** telemetry initialised with an in-memory exporter and a local test HTTP server on `127.0.0.1:<port>` that answers like an OpenAI-compatible `/chat/completions`
- **WHEN** MintMory's LLM client sends one chat request to it
- **THEN** the server received a `traceparent` whose trace id and parent span id are those of the exported `gen_ai.chat` span, and that span has kind CLIENT, `server.address=127.0.0.1` and `server.port=<port>`

#### Scenario: tracestate is forwarded, baggage is not
- **GIVEN** the same server, and a span opened with `telemetry.span("caller", context=telemetry.extract_context({"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01", "tracestate": "vendor=1", "baggage": "user=SENTINEL-BAG-3"}))`
- **WHEN** the LLM client sends one chat request inside that span
- **THEN** the server received `traceparent` with trace id `4bf92f3577b34da6a3ce929d0e0e4736`, `tracestate: vendor=1`, and no `baggage` header

#### Scenario: Embedding endpoints receive traceparent
- **GIVEN** telemetry initialised with an in-memory exporter, a local test HTTP server answering like Ollama's embedding endpoint, and an `OpenAIEmbedder` built with `OpenAIEmbedder.__new__` whose `_client` is a stub recording the `extra_headers` keyword of `embeddings.create`
- **WHEN** `OllamaEmbedder` embeds one text against the server, and the `OpenAIEmbedder` embeds one text
- **THEN** each received a `traceparent` whose parent span id is that of the `mintmory.embed` span exported for that call

#### Scenario: No header when telemetry is off
- **GIVEN** telemetry is not initialised
- **WHEN** the same chat request is sent and `telemetry.inject_trace_headers({})` is called
- **THEN** the server received no `traceparent` header and the call returned `{}`
