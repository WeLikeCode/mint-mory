# Tasks: distributed traces across the boundaries (OpenTelemetry, part 3 of 4)

Requires `add-telemetry-runtime` (test seam; MintMory's provider is the global provider) and
`add-telemetry-heavy-path-spans` (`mintmory.embed` span). Do not add dependencies: use `opentelemetry.trace`,
`opentelemetry.propagate` (`extract`, `inject`) and `opentelemetry.context` from `opentelemetry-api`, imported lazily
(only when telemetry is enabled), like the rest of `telemetry.py`. Use the in-memory exporter and reader in tests,
with `pytest.importorskip("opentelemetry.sdk")`. Write each test first and see it fail. The facts quoted below were
checked against the installed packages (FastAPI 0.137.1, Starlette 1.3.1, anyio 4.13.0, FastMCP 3.4.2, mcp 1.27.2).

## 1. Telemetry helpers (`packages/core/src/mintmory/core/telemetry.py`)
- [ ] 1.1 Tests for the helpers below, on and off.
- [ ] 1.2 Add a keyword `kind: str = "internal"` (`"internal"`, `"server"`, `"client"`) and `context: Any = None` to
  `span()`, mapped to `SpanKind` and passed to `start_as_current_span`. Add `inject_trace_headers(headers: dict[str,
  str]) -> dict[str, str]`: when enabled, `opentelemetry.propagate.inject(headers)`; always returns `headers`. Add
  `extract_context(carrier: Mapping[str, str]) -> Any`: `opentelemetry.propagate.extract(carrier)` when enabled, else
  `None`. Let `_instrument` pass `explicit_bucket_boundaries_advisory` to `create_histogram` when given.

## 2. HTTP server middleware (`packages/api/src/mintmory/api/telemetry_middleware.py`)
- [ ] 2.1 Tests (in `packages/api/tests/test_telemetry_http.py`): every scenario of "HTTP server spans continue the
  caller's trace", "Excluded, unmatched and failing HTTP requests" and "HTTP server duration metric", with `fastapi.testclient.TestClient(app)` inside a `with`
  block so the lifespan runs, and one test for a route that raises (status ERROR, `error.type` set).
- [ ] 2.2 Write a pure ASGI middleware class (`__init__(self, app)`, `async __call__(self, scope, receive, send)`):
  pass non-`http` scopes and excluded paths straight through (`/healthz`, `/readyz`, or `re.search(regex, path)` for a
  comma-separated regex of `OTEL_PYTHON_EXCLUDED_URLS`, read from `os.environ` on each request, with the compiled
  patterns cached per variable value (an item `re.compile` rejects is skipped with one WARNING per distinct value,
  never an error for the request); because Starlette builds the middleware stack once and tests set the variable
  after importing the module-level `app`); otherwise extract the context from the request headers (decode the ASGI byte pairs
  to a lower-case `dict[str, str]`), open `telemetry.span(method, kind="server", context=ctx)`, wrap `send` to capture
  the status code from `http.response.start`, `await self.app(...)`, then, when `scope.get("route")` is not None
  (FastAPI sets it after routing; it is None for unmatched paths), rename the span with
  `span.update_name(f"{method} {scope['route'].path}")` and set `http.route`; set `http.request.method` and
  `http.response.status_code`; never set `url.path` or the query string; set status ERROR and `error.type` (the status
  code as a string, or the exception class name) for 5xx or an exception (re-raise it); record
  `http.server.request.duration` in seconds (`unit="s"`, the bucket boundaries in the spec). When telemetry is off the
  middleware only calls the app.
- [ ] 2.3 Register it in `app.py` with `app.add_middleware(TelemetryMiddleware)` after the CORS middleware. The store
  calls run in `anyio.to_thread.run_sync`, which copies the context into the worker thread (anyio 4.13.0), so core
  spans are children of the server span without extra code.

## 3. MCP tool calls (tests only)
- [ ] 3.1 Tests (in `packages/mcp/tests/test_telemetry_mcp.py`) for both scenarios of "MCP tool calls are traced
  once", plus a failing tool (status ERROR) and one `mintmory-history-mcp` tool. Use `fastmcp.Client(mcp)` (in-memory
  transport) inside `async with`; for the `_meta` scenario call `client.session.call_tool("memory_stats", {},
  meta={...})` (the MCP `ClientSession` accepts `meta=`). Notes for the implementer: FastMCP 3.4.2 creates the
  `tools/call <tool>` SERVER span itself through the global tracer provider and reads `_meta` from the request context
  (in middleware `context.message.meta` is always None, so do not add a middleware); `fastmcp.Client.call_tool(meta=)`
  overwrites `traceparent` with its own CLIENT span's when an SDK provider is global; sync tools run on an anyio worker
  thread with the context copied, so `mintmory.search` is a descendant of the tool span.
- [ ] 3.2 If a test fails because the tool span is missing, check that `add-telemetry-runtime` made MintMory's provider
  global on this init (`trace.get_tracer_provider()` is the module's provider); do not create MintMory spans per tool
  call.

## 4. Outbound propagation
- [ ] 4.1 Tests for both scenarios of "Outbound calls carry the trace context" with a `http.server` test server in a
  daemon thread that returns a minimal chat-completion JSON (look at the existing LLM tests in
  `packages/core/tests/test_llm.py` for the response shape the client parses) and records the request headers. Add the
  same check for `OllamaEmbedder` against a test server. `openai` is not installed by the gates, so test
  `OpenAIEmbedder` with `emb = OpenAIEmbedder.__new__(OpenAIEmbedder)` and `emb._client` set to a stub whose
  `embeddings.create(**kwargs)` records `kwargs["extra_headers"]` and returns an object with `.data[i].embedding`.
- [ ] 4.2 In `llm.py`, open `gen_ai.chat` with `kind="client"` and `server.address` / `server.port` from the request
  URL (`urllib.parse.urlsplit`), and add the injected headers to the `urllib.request.Request` inside the span (for
  example `for k, v in telemetry.inject_trace_headers({}).items(): req.add_header(k, v)`), before `urlopen`. The
  request object is built before the span today; add the headers after the span opens.
- [ ] 4.3 In `embedder.py`, inject the same way in `OllamaEmbedder` (on its `urllib.request.Request`) and pass
  `extra_headers=telemetry.inject_trace_headers({})` to `self._client.embeddings.create(...)` in `OpenAIEmbedder`,
  inside the `mintmory.embed` span.

## 5. Checks
- [ ] 5.1 Add a short "Distributed tracing" subsection to `docs/OBSERVABILITY.md` section 4 (what continues a trace:
  `traceparent` on HTTP requests, `_meta.traceparent` on MCP tool calls; what MintMory sends: `traceparent` on LLM and
  embedding requests). Run `ruff check`, `ruff format --check`, `mypy packages` and the full test suite; coverage stays
  at or above 80%.
