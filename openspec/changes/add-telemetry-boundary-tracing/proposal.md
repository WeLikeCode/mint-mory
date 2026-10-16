# Change: distributed traces across MintMory's boundaries: HTTP API, MCP tools, outbound LLM and embedding calls (OpenTelemetry, part 3 of 4)

## Why

The REST API (`api/app.py`) creates no server span and ignores an incoming `traceparent`, so a caller's trace stops at
MintMory. FastMCP 3.4.2 already traces each MCP tool call through the global OpenTelemetry API, but nothing pins that
with tests. The LLM client (`core/llm.py`) and the Ollama and OpenAI embedders send no `traceparent`, so a tracing LLM
gateway cannot join MintMory's trace, and `gen_ai.chat` is not a client span.

## What changes

- `telemetry.span()` gains keyword-only `kind`, `context`, `record_exception`, `set_status_on_exception`; header
  helpers and `record_histogram` are added.
- An ASGI middleware: one SERVER span per request, named by route template, continuing the caller's W3C context, with a
  defined outcome for every way a request ends, and the histogram `http.server.request.duration`; its own failures
  never change a response. Health endpoints are not traced.
- MCP: no MintMory code; tests pin the verified FastMCP 3.4.2 behaviour in both MCP servers.
- Outbound: `gen_ai.chat` becomes a CLIENT span with `server.address` and `server.port`; LLM and embedding requests carry
  `traceparent` (and `tracestate`, never `baggage`). Heavy-path's privacy requirement lists the attributes `gen_ai.chat`
  has before this unit; the two added here carry the endpoint's host and port, no content.

## Non-goals

`opentelemetry-instrumentation-*` packages (not in `uv.lock`), an MCP middleware, database client spans, recording
request or tool arguments.

## Impact

New `api/telemetry_middleware.py`; `app.py`, `llm.py`, `embedder.py`, `telemetry.py`; new API and MCP tests. Depends on
`add-telemetry-runtime` (seam, global provider, `mark_error`, scrubber) and `add-telemetry-heavy-path-spans`
(`mintmory.embed`), not on `add-telemetry-entry-points` (`design.md`).
