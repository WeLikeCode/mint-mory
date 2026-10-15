# Change: distributed traces across MintMory's boundaries: HTTP API, MCP tools, outbound LLM and embedding calls (OpenTelemetry, part 3 of 4)

## Why

A trace is only "distributed" if it crosses process boundaries. Today it does not:

- The REST API (`packages/api/src/mintmory/api/app.py`) creates no server span and ignores an incoming W3C
  `traceparent` header, so a caller's trace stops at MintMory and each core span starts a new trace.
- MCP tool calls: FastMCP 3.4.2 already creates a SERVER span `tools/call <tool>` per tool call and continues a
  `traceparent` passed in the request's `_meta` (`fastmcp/server/server.py`), through the global OpenTelemetry API.
  Part 1 makes MintMory's provider the global one, so these spans start to be exported; nothing pins this behaviour
  with tests yet, and nothing documents it.
- Outbound calls carry no trace context: the LLM client (`packages/core/src/mintmory/core/llm.py`, `urllib`), the
  Ollama embedder (`urllib`) and the OpenAI embedder (`openai` SDK) send no `traceparent`, so an LLM gateway or proxy
  that traces cannot join MintMory's trace. The `gen_ai.chat` span is not marked as a client span.

## What changes

- A small ASGI middleware in the API: one SERVER span per request named `<METHOD> <route template>`, continuing the
  caller's W3C context, with the stable HTTP semantic-convention attributes (no raw path: paths such as
  `/summaries/{concept}` carry content), status ERROR on 5xx, and the histogram `http.server.request.duration`
  (seconds, with buckets suited to an API). Health endpoints are not traced. No new dependency: this is ~80 lines over
  `opentelemetry-api`, which the `otel` extra already installs.
- MCP: MintMory relies on FastMCP's native tool-call span and does not add its own; tests pin that one span per tool
  call is exported, that core spans are its descendants, and that `_meta.traceparent` is continued, in both MCP
  servers.
- Outbound: `gen_ai.chat` becomes a CLIENT span with `server.address` and `server.port`, and every outbound LLM and
  embedding HTTP request carries `traceparent` (and `tracestate`, `baggage` when present) injected inside the client
  span.

## Non-goals

The official `opentelemetry-instrumentation-*` packages (not in `uv.lock`; the middleware covers MintMory's needs
with no new dependency); a MintMory-specific MCP middleware (FastMCP's span already covers it); client spans for
database drivers; recording request or tool arguments.

## Impact

- Code: new `packages/api/src/mintmory/api/telemetry_middleware.py`; `app.py`, `llm.py`, `embedder.py`, and
  `telemetry.py` (a span `kind` argument and header helpers); new MCP tests.
- Depends on `add-telemetry-runtime` (test seam, global provider) and `add-telemetry-heavy-path-spans` (the
  `mintmory.embed` span inside which embedding requests inject their headers).
