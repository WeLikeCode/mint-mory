# Tasks: distributed traces across the boundaries (OpenTelemetry, part 3 of 4)

Requires `add-telemetry-runtime` (test seam: inject both exporter and reader; MintMory's provider is global;
`mark_error`; the scrubber) and `add-telemetry-heavy-path-spans` (`mintmory.embed` span). Do not add dependencies:
use `opentelemetry.trace`, `opentelemetry.propagate` (`extract`) and
`opentelemetry.trace.propagation.tracecontext.TraceContextTextMapPropagator` from `opentelemetry-api`, imported
lazily (only when telemetry is enabled). Tests use the in-memory exporter and reader with
`pytest.importorskip("opentelemetry.sdk")` and initialise telemetry themselves before `TestClient`/`fastmcp.Client`.
Write each test first and see it fail. The facts quoted below were checked against the installed packages (FastAPI
0.137.1, Starlette 1.3.1, anyio 4.13.0, FastMCP 3.4.2, mcp 1.27.2, OpenTelemetry 1.42.1).

## 1. Telemetry helpers (`packages/core/src/mintmory/core/telemetry.py`)
- [ ] 1.1 Tests for the helpers below, on and off, including `extract_context({"traceparent": "garbage"})` (an empty
  context, no exception) and `inject_trace_headers` with telemetry off (returns the dict unchanged).
- [ ] 1.2 `span()` keeps yielding the SDK span when enabled and `_NoopSpan` when not; add a no-op `update_name(name)` to
  `_NoopSpan`; failures use runtime's `telemetry.mark_error` (no status method on `_NoopSpan`). Add keyword-only
  `kind: str = "internal"` (`"internal"`, `"server"`, `"client"`, mapped to `SpanKind`) and `context: Any = None` to
  `span()`, passed to `start_as_current_span`. No existing caller passes attributes named `kind` or `context` (on
  `staging` the callers pass `step=` in `dreaming.py`, `gen_ai.*` and `prompt_chars` in `llm.py`, none to `traced()`).
  `inject_trace_headers(headers: dict[str, str]) -> dict[str, str]`: when enabled,
  `TraceContextTextMapPropagator().inject(headers)` (`traceparent`, `tracestate`; never `baggage`); always returns
  `headers`. `extract_context(carrier: Mapping[str, str]) -> Any`: `opentelemetry.propagate.extract(carrier)` when
  enabled, else `None`. Both inside `try/except Exception` (on error: headers unchanged, `None`). `_instrument(kind,
  factory_name, name, **options)` passes `options` to the factory on first creation (heavy-path already passes `unit`);
  add `record_histogram(name, value, *, unit, boundaries=None, **attrs)`, which creates the histogram through it with
  `unit` and `explicit_bucket_boundaries_advisory=boundaries` and records, a no-op when metrics are off.

## 2. HTTP server middleware (`packages/api/src/mintmory/api/telemetry_middleware.py`)
- [ ] 2.1 Tests in `packages/api/tests/test_telemetry_http.py` for every scenario of "HTTP server spans continue the
  caller's trace", "Excluded HTTP paths", "Unmatched and failing HTTP requests" and "HTTP server duration metric", with
  `TestClient(app)` inside a `with` block so the lifespan runs. Assert inside the block (the exporter and reader stay
  readable after a provider shutdown, so order does not matter, but this keeps the tests independent of
  `add-telemetry-entry-points`, whose lifespan calls `shutdown_telemetry()` on exit).
- [ ] 2.2 A pure ASGI middleware class (`__init__(self, app)`, `async __call__(self, scope, receive, send)`): pass
  non-`http` scopes, `/healthz`, `/readyz` and excluded paths straight through (`re.search` per item of
  `OTEL_PYTHON_EXCLUDED_URLS`, read from `os.environ` on each request, compiled patterns cached per variable value; a
  `re.error` item is skipped with one WARNING per distinct value; per-request reading is needed because Starlette builds
  the middleware stack once and tests set the variable after importing `app`). When telemetry is off, only call the
  app. Otherwise: decode the ASGI header pairs to a lower-case `dict[str, str]`, `ctx = telemetry.extract_context(...)`,
  open `telemetry.span(method, kind="server", context=ctx)`, wrap `send` to capture the status of
  `http.response.start`, `await self.app(...)`; then, when `scope.get("route")` is not None (FastAPI sets it after
  routing), `span.update_name(f"{method} {scope['route'].path}")` and set `http.route`; set `http.request.method` and
  `http.response.status_code`; never `url.path` or the query. On a 5xx, `mark_error(span, str(status))`; on an
  `Exception`, `mark_error(span, type(exc).__name__)`, status 500 if none was sent, re-raise; let
  `asyncio.CancelledError` pass unmarked. In a `finally`, `telemetry.record_histogram("http.server.request.duration",
  seconds, unit="s", boundaries=_HTTP_BUCKETS, **attrs)` with the spec's boundaries.
- [ ] 2.3 Register it in `app.py` with `app.add_middleware(TelemetryMiddleware)` after the CORS middleware. Store calls
  run in `anyio.to_thread.run_sync`, which copies the context into the worker thread (anyio 4.13.0), so core spans are
  children of the server span without extra code.

## 3. MCP tool calls (tests only)
- [ ] 3.1 Tests in `packages/mcp/tests/test_telemetry_mcp.py` for every scenario of "MCP tool calls are traced once".
  Use `fastmcp.Client(mcp)` (in-memory transport) inside `async with`; filter spans by `kind == SpanKind.SERVER`; for
  `_meta` call `client.session.call_tool("memory_stats", {}, meta={...})`. FastMCP 3.4.2 creates the SERVER span in
  `fastmcp/server/telemetry.py` (`server_span`, through the global tracer provider), reads `_meta` from the request
  context, and on an exception sets `error.type` and status ERROR; sync tools run on an anyio worker thread with the
  context copied, so `mintmory.search` is a descendant of the tool span. No MCP middleware.
- [ ] 3.2 If a test fails because the tool span is missing, check that runtime made MintMory's provider global
  (`trace.get_tracer_provider()` is the module's provider). Never add MintMory spans per tool call; if FastMCP's span
  or status is absent after that check, stop and report instead of adding one.

## 4. Outbound propagation
- [ ] 4.1 Tests for every scenario of "Outbound calls carry the trace context" with a `http.server` test server in a
  daemon thread returning a minimal chat-completion JSON (see `packages/core/tests/test_llm.py` for the shape the
  client parses) and recording request headers; the same for `OllamaEmbedder`. `openai` is not installed by the
  gates: build `OpenAIEmbedder.__new__(OpenAIEmbedder)` with `_client` a stub whose `embeddings.create(**kwargs)`
  records `kwargs["extra_headers"]` and returns an object with `.data[i].embedding`.
- [ ] 4.2 `llm.py` `post_chat_completion`: open `gen_ai.chat` with `kind="client"`, `server.address`/`server.port` from
  `urllib.parse.urlsplit` of the request URL (port default per scheme); add the injected headers to the existing
  `urllib.request.Request` inside the span, before `urlopen` (`for k, v in telemetry.inject_trace_headers({}).items():
  req.add_header(k, v)`).
- [ ] 4.3 `embedder.py`: inject the same way on `OllamaEmbedder`'s request and pass
  `extra_headers=telemetry.inject_trace_headers({})` to `self._client.embeddings.create(...)` in `OpenAIEmbedder`,
  inside the `mintmory.embed` span.

## 5. Checks
- [ ] 5.1 Add a "Distributed tracing" subsection to `docs/OBSERVABILITY.md` section 4 (what continues a trace:
  `traceparent` on HTTP requests, `_meta.traceparent` on MCP tool calls; what MintMory sends: `traceparent` and
  `tracestate`, never `baggage`, on LLM and embedding requests). Run `ruff check`, `ruff format --check`,
  `mypy packages` and the full test suite; coverage stays at or above 80%.
