# Capability: observability (delta)

## Purpose

MintMory's observability: OpenTelemetry traces and metrics from every entry point (CLI, REST API, MCP servers), safe and silent when no collector runs, distributed across HTTP, MCP and outbound LLM calls, with a local collector, Jaeger and Prometheus stack for development.

## ADDED Requirements

### Requirement: Span options for boundary spans
`telemetry.span` SHALL have the signature `span(name, *, kind="internal", context=None, record_exception=True, set_status_on_exception=True, **attrs)` and pass `kind` (`"internal"`, `"server"`, `"client"`, mapped to `SpanKind`; any other value maps to INTERNAL), `context` and both flags to the tracer's `start_as_current_span`. The defaults are the SDK's, so existing callers (`dreaming.py`, `llm.py`, `traced`) keep their behaviour. With telemetry off it SHALL yield `_NoopSpan`, which gains a no-op `update_name(name)`.

#### Scenario: Options reach the span
- **GIVEN** telemetry initialised with an injected in-memory span exporter
- **WHEN** `with telemetry.span("a", kind="server"): pass` and `with telemetry.span("d", kind="bogus"): pass` run, then inside `pytest.raises(RuntimeError)` `with telemetry.span("b", record_exception=False, set_status_on_exception=False): raise RuntimeError("SENTINEL-12")` and the same with defaults as span `c`
- **THEN** `a` has kind SERVER and `d` kind INTERNAL; `b` has status UNSET and no event; `c` has status ERROR with an empty description (scrubbed) and one `exception` event whose only attribute is `exception.type=RuntimeError`; with telemetry not initialised, `with telemetry.span("a", kind="server", record_exception=False) as sp: sp.update_name("b")` raises nothing and `sp` is a `_NoopSpan`

### Requirement: HTTP server spans continue the caller's trace
Each API request, except excluded paths, SHALL run in a SERVER span named `<METHOD> <route template>` that continues the W3C context of the request headers (ASGI header bytes decoded as latin-1, names lower-cased), with `http.request.method`, `http.route` and `http.response.status_code`, and without `url.path`, `url.query` or any other raw path value. API scenarios run under `TestClient` with telemetry initialised with an in-memory span exporter and metric reader (setup in task 2.1).

#### Scenario: Incoming traceparent is continued
- **GIVEN** a memory created with `POST /memories` and the body `{"content": "Acme parking uses OAuth.", "category": "fact"}`
- **WHEN** `POST /memories/search` is sent with the body `{"query": "parking"}` and `traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
- **THEN** it answers 200, a SERVER span named `POST /memories/search` is exported with trace id `4bf92f3577b34da6a3ce929d0e0e4736` and parent span id `00f067aa0ba902b7`, and the `mintmory.search` span of that request is its descendant

#### Scenario: Route template, not the raw path, names the span
- **GIVEN** a memory created as above, its id `<id>` taken from the response
- **WHEN** `GET /memories/<id>?verbose=1` is called
- **THEN** the span is named `GET /memories/{memory_id}`, `http.route` is `/memories/{memory_id}`, it has no `url.path` or `url.query` attribute, and no attribute value contains `<id>`

### Requirement: How the middleware ends the server span
`TelemetryMiddleware` (`api/telemetry_middleware.py`, pure ASGI) SHALL be the outermost user middleware (the last `app.add_middleware` call, after `CORSMiddleware`) and, for a traced request, open `telemetry.span(<METHOD>, kind="server", context=telemetry.extract_context(headers), record_exception=False, set_status_on_exception=False)` around `await self.app(scope, receive, wrapped_send)`, where `wrapped_send` keeps the status of the first `http.response.start` message and forwards every message unchanged. When the app returns or raises:
- Name: when `scope.get("route")` is not None the span is renamed `<METHOD> <route.path>` and gets `http.route`; else it keeps `<METHOD>` and has no `http.route`. FastAPI 0.137.1 `APIRoute.matches` (`fastapi/routing.py`) sets `scope["route"]` on a full or partial match, so a method mismatch (405) has a route; a 404, and a CORS preflight answered by `CORSMiddleware`, have none.
- Status: `http.response.status_code` is the sent status; if none was sent and the app raised an `Exception`, 500 (Starlette's outer `ServerErrorMiddleware` sends it); if none was sent otherwise, the attribute is absent.
- Marking, with runtime's `telemetry.mark_error(span, error_type)`: an `Exception` marks with its class name and the same object is re-raised; else a sent status of 500 or more marks with the status as a string; `asyncio.CancelledError` (client gone) or another `BaseException` leaves the span unmarked and is re-raised.
- Metric: every traced request records one `http.server.request.duration` point with the span's `http.request.method`, `http.route` and `http.response.status_code`, absent ones omitted.

The "ASGI harness" of the scenarios: telemetry with an in-memory exporter and reader; `asyncio.run(TelemetryMiddleware(inner)(scope, receive, send))` with `scope = {"type": "http", "method": "GET", "path": "/x", "headers": []}`, `receive` returning `{"type": "http.request", "body": b"", "more_body": False}` and `send` appending each message to a list `sent`.

#### Scenario: No route, and a method mismatch
- **WHEN** `GET /no-such-path`, `DELETE /stats` and a preflight `OPTIONS /stats` (headers `Origin: http://x`, `Access-Control-Request-Method: GET`) are called
- **THEN** they answer 404, 405 and 200; spans `GET` (404, no `http.route`), `DELETE /stats` (`http.route=/stats`, 405) and `OPTIONS` (200, no `http.route`) are exported, all with status UNSET

#### Scenario: A route that raises before the response starts
- **GIVEN** a test route `GET /test-raise` added to the app that raises `RuntimeError("SENTINEL-55")`
- **WHEN** it is called with `TestClient(app, raise_server_exceptions=False)`
- **THEN** the answer is 500, its span `GET /test-raise` has status ERROR with an empty description, `error.type=RuntimeError`, `http.response.status_code` = 500 and no event, the duration histogram has a point with `http.response.status_code` = 500, and no exported span, event or status description contains `SENTINEL-55`

#### Scenario: An exception after the response started
- **GIVEN** the ASGI harness and `inner` that sends `{"type": "http.response.start", "status": 200, "headers": []}` and then raises `RuntimeError("SENTINEL-56")`
- **WHEN** the middleware is run inside `pytest.raises(RuntimeError)`
- **THEN** the raised object is the one `inner` raised, `sent` holds the start message, the span `GET` has status ERROR with an empty description, `error.type=RuntimeError`, `http.response.status_code` = 200 and no event, and the duration point has `http.response.status_code` = 200

#### Scenario: A 5xx answer without an exception
- **GIVEN** the ASGI harness and `inner` that sends a start message with status 503 and `{"type": "http.response.body", "body": b"x"}`
- **WHEN** the middleware is run
- **THEN** it returns None, `sent` holds both messages, and the span `GET` has status ERROR, `error.type` = `"503"` (a string) and `http.response.status_code` = 503

#### Scenario: A cancelled request, and no response at all
- **GIVEN** the ASGI harness and (a) `inner` raising `asyncio.CancelledError()` before sending anything, (b) `inner` returning without sending anything
- **WHEN** the middleware is run, (a) inside `pytest.raises(asyncio.CancelledError)`
- **THEN** in both, `sent` is empty, the span `GET` is exported with status UNSET, no `error.type`, no event and no `http.response.status_code`, and the duration point has `http.request.method=GET` and no other attribute; (b) returns None

### Requirement: Middleware telemetry never alters a request
Each telemetry step of the middleware (header decoding, `extract_context`, opening and closing the span, `update_name`, setting attributes, `mark_error`, `record_histogram`) SHALL run in its own `try/except Exception`, apart from the `try` around `await self.app(...)`. A failed step SHALL be dropped with one DEBUG record on `mintmory.telemetry` naming only the exception class; the app still gets the same `scope` and `receive`, its messages reach `send` unchanged and in order, and the middleware returns or raises what the app does. If the span cannot be opened, the request runs without span or point. `record_histogram` itself SHALL never raise. A missing or malformed `traceparent` SHALL start a new trace.

#### Scenario: A malformed traceparent starts a new trace
- **WHEN** `GET /stats` is sent with `traceparent: garbage`, and again with `traceparent: 00-00000000000000000000000000000000-0000000000000000-01`
- **THEN** both answer 200 and each SERVER span `GET /stats` has no parent and a trace id other than `4bf92f3577b34da6a3ce929d0e0e4736`; `telemetry.extract_context({"traceparent": "garbage"})` returns without raising

#### Scenario: A failing histogram record leaves the response unchanged
- **GIVEN** an empty store, the body `b0` of a `GET /stats` answer, then `opentelemetry.sdk.metrics._internal.instrument.Histogram.record` patched to raise `RuntimeError`
- **WHEN** `GET /stats` is sent again
- **THEN** it answers 200 with a body equal to `b0`, and the SERVER span `GET /stats` is still exported

#### Scenario: Failing span updates leave the response unchanged
- **GIVEN** the ASGI harness; `opentelemetry.sdk.trace.Span.set_attribute`, `.set_attributes`, `.update_name` and `telemetry.extract_context` patched to raise `RuntimeError`; `inner` sending a start message (status 201, headers `[(b"x-a", b"1")]`) and a body message `b"ok"`
- **WHEN** the middleware is run (each run with a new `sent`); again with an `inner` that sends the same two messages and then raises `ValueError("v")`; and with the first `inner` and `telemetry.span` patched to raise `RuntimeError`
- **THEN** the first and third runs return None with `sent` equal to the two messages in order, the second raises that `ValueError` object after them, the third adds no span to the exporter, and `mintmory.telemetry` has a DEBUG record containing `RuntimeError`

### Requirement: Excluded HTTP paths
`/healthz` and `/readyz` (exact path match) SHALL NOT be traced, nor a path in which `re.search` finds one of the comma-separated regexes of `OTEL_PYTHON_EXCLUDED_URLS` (the path only, no query string). Read on each request, the value SHALL be compiled by `telemetry_middleware._compile_excluded(value)` (a `functools.lru_cache` on the whole value): items stripped, empty items ignored, an item that is not a valid regex skipped with one WARNING on `mintmory.telemetry` containing it, logged at the value's first compile; a request never fails.

#### Scenario: Health probes are not traced
- **WHEN** `GET /healthz`, `GET /readyz` and `GET /healthz/x` are called
- **THEN** no span is exported for the first two, and `GET /healthz/x` (404) is traced as `GET`

#### Scenario: Excluded by the environment
- **GIVEN** the module-level `app` from `mintmory.api.app` and, set with `monkeypatch.setenv` after import, (a) `OTEL_PYTHON_EXCLUDED_URLS=^/stats$,/summaries`, (b) `OTEL_PYTHON_EXCLUDED_URLS=" , ^/stats$ ,"`
- **WHEN** `GET /stats`, `GET /summaries` and `GET /memories/<id>` of a created memory are called
- **THEN** `GET /stats` is not traced in (a) and (b), `GET /summaries` is not traced in (a) and is in (b), and the memory request is traced in both

#### Scenario: A bad exclusion pattern is skipped
- **GIVEN** `_compile_excluded.cache_clear()` and `OTEL_PYTHON_EXCLUDED_URLS=([,^/stats$`
- **WHEN** `GET /stats` and `GET /memories/<id>` of a created memory are called twice each
- **THEN** all four answer 200, `GET /stats` is not traced, the memory request is, and `mintmory.telemetry` logged exactly one WARNING, containing `([`

### Requirement: HTTP server duration metric
The API SHALL record each traced request in the histogram `http.server.request.duration` (unit `s`, explicit bucket boundaries 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5 and 10) with the attributes stated in "How the middleware ends the server span".

#### Scenario: Request duration recorded
- **WHEN** two `GET /stats` requests are sent
- **THEN** `InMemoryMetricReader.get_metrics_data()` has the metric `http.server.request.duration` with unit `s` and one point for `http.route=/stats`, `http.request.method=GET`, `http.response.status_code=200`, with `count` 2 and `explicit_bounds` `(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)`

### Requirement: MCP tool calls are traced once
Each MCP tool call in `mintmory-mcp` and `mintmory-history-mcp` SHALL be traced by FastMCP's native SERVER span; MintMory SHALL NOT add an MCP middleware or a second span per tool call, and no MintMory code depends on that span. Facts verified by running FastMCP 3.4.2 (pinned by `uv.lock`; CI runs `uv sync --frozen`) with an in-memory exporter:
- `FastMCP.call_tool` (`fastmcp/server/server.py`) runs the tool inside `server_span(f"tools/call {name}", ...)` (`fastmcp/server/telemetry.py`): tracer `fastmcp`, kind SERVER, attributes such as `mcp.method.name`, `gen_ai.tool.name` and `mcp.session.id`, never an argument value. The tracer is looked up per span (`opentelemetry.trace.get_tracer("fastmcp")`), so spans follow the current global provider, also after a reset and a new init.
- The parent is the `traceparent` / `tracestate` of the request's `_meta` unless a valid span is current. `fastmcp.Client.call_tool` opens its own CLIENT span of the same name and puts its `traceparent` into `_meta`, replacing a caller's; `client.session.call_tool(name, args, meta=...)` sends `_meta` as given, with no CLIENT span.
- A raising tool: `call_tool` re-raises the exception as `ToolError("Error calling tool '<name>': <message>")` (no masking, FastMCP's default); `server_span` sets `error.type=tool_error` and records an `exception` event; the SDK's `use_span` records a second and sets status ERROR with the message as description. Runtime's scrubber (outermost on every injected exporter) leaves `exception.type=fastmcp.exceptions.ToolError` as each event's only attribute and an empty description. `client.call_tool` raises `ToolError`; with `raise_on_error=False` it returns `is_error=True`.
- A sync tool runs on an anyio worker thread with the context copied, so its spans are children of the SERVER span.

If FastMCP differs from these facts, the tests fail and the unit fails; a MintMory span is never added in its place.

#### Scenario: The verified FastMCP version is installed
- **WHEN** the MCP telemetry test module runs
- **THEN** a test in it asserts `importlib.metadata.version("fastmcp") == "3.4.2"`, with a message that these facts were verified on 3.4.2 only

#### Scenario: Tool call is one span with core spans below it
- **GIVEN** telemetry initialised with an in-memory exporter and a memory added with `memory_add` (content `Acme parking uses OAuth.`, category `fact`)
- **WHEN** the client calls `memory_search` with the query `parking`
- **THEN** among exported spans of kind SERVER exactly one is named `tools/call memory_search`, and the `mintmory.search` span of that call is its descendant; a client of `mintmory-history-mcp` calling `history_stats` exports exactly one SERVER span `tools/call history_stats`

#### Scenario: A failing tool is marked
- **GIVEN** `mintmory.mcp.server._get_store` (the store accessor `memory_stats` calls) patched to raise `RuntimeError("SENTINEL-77")`
- **WHEN** the client calls `client.call_tool("memory_stats", {}, raise_on_error=False)`
- **THEN** the result has `is_error=True`; the SERVER span `tools/call memory_stats` has status ERROR with an empty description, `error.type=tool_error` and `exception` events whose only attribute is `exception.type=fastmcp.exceptions.ToolError`; and no exported span, event or status description contains `SENTINEL-77`

#### Scenario: Tool arguments never reach telemetry
- **WHEN** the client calls `memory_search` with the query `SENTINEL-ARG-4f` and `memory_note` with the text `SENTINEL-ARG-9a`
- **THEN** no exported span attribute, event or status description contains either sentinel

#### Scenario: Context in `_meta` is continued
- **WHEN** the client calls `client.session.call_tool("memory_stats", {}, meta={"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"})`
- **THEN** the `tools/call memory_stats` SERVER span has trace id `4bf92f3577b34da6a3ce929d0e0e4736` and parent span id `00f067aa0ba902b7`, and no CLIENT span is exported for that call

#### Scenario: Tool spans follow a new init
- **GIVEN** telemetry initialised with in-memory exporter A, one `memory_stats` call, then `telemetry.reset_telemetry()` and an init with in-memory exporter B
- **WHEN** a new client calls `memory_stats`
- **THEN** A holds exactly one SERVER span `tools/call memory_stats` and B holds exactly one

### Requirement: Outbound calls carry the trace context
`gen_ai.chat` SHALL be a CLIENT span with `server.address` (the URL host) and `server.port` (the URL port, else 443 for `https` and 80 for `http`); `mintmory.embed` stays INTERNAL. Every outbound LLM request (`llm.py`) and embedding request (`OllamaEmbedder`, `OpenAIEmbedder`) SHALL carry the W3C `traceparent` header, and `tracestate` when the span context has one, injected inside the span that wraps the request (`gen_ai.chat` or `mintmory.embed`), so that span is the remote side's parent. MintMory SHALL NOT forward `baggage` (the endpoints may be third-party). With telemetry off no header SHALL be added. The header helpers SHALL never raise. The chat request of the scenarios is `llm.post_chat_completion(base_url=f"http://127.0.0.1:{port}", api_key=None, payload={"model": "m", "messages": [{"role": "user", "content": "hi"}]}, timeout_s=5.0, system="test", model="m")` against a local `ThreadingHTTPServer` that records request headers and answers `/chat/completions` with the minimal JSON `packages/core/tests/test_llm.py` uses.

#### Scenario: LLM endpoint receives traceparent
- **GIVEN** telemetry initialised with an in-memory exporter and the test server on `127.0.0.1:<port>`
- **WHEN** the chat request is sent
- **THEN** the server received a `traceparent` whose trace id and parent span id are those of the exported `gen_ai.chat` span, and that span has kind CLIENT, `server.address=127.0.0.1` and `server.port=<port>`

#### Scenario: tracestate is forwarded, baggage is not
- **GIVEN** the same server, and a span opened with `telemetry.span("caller", context=telemetry.extract_context({"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01", "tracestate": "vendor=1", "baggage": "user=SENTINEL-BAG-3"}))`
- **WHEN** the chat request is sent inside that span
- **THEN** the server received `traceparent` with trace id `4bf92f3577b34da6a3ce929d0e0e4736`, `tracestate: vendor=1`, and no `baggage` header

#### Scenario: Embedding endpoints receive traceparent
- **GIVEN** telemetry initialised with an in-memory exporter, a local test HTTP server answering like Ollama's embedding endpoint, and `e = OpenAIEmbedder.__new__(OpenAIEmbedder)` with only `e._client` set to a stub whose `embeddings.create(**kwargs)` records `kwargs["extra_headers"]` and returns an object with `.data[0].embedding`
- **WHEN** `OllamaEmbedder` embeds one text against the server, and `e.embed("a")` runs
- **THEN** each received a `traceparent` whose parent span id is that of the `mintmory.embed` span exported for that call

#### Scenario: No header when telemetry is off
- **GIVEN** telemetry is not initialised
- **WHEN** the chat request is sent and `telemetry.inject_trace_headers({})` is called
- **THEN** the server received no `traceparent` header and the call returned `{}`
