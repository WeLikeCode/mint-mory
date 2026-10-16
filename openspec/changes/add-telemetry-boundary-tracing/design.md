# Design: boundary tracing

## Decisions

- **No dependency on `add-telemetry-entry-points`.** Checked against both folders and `staging`: (1) every test here
  initialises telemetry itself through runtime's seam (`init_telemetry(span_exporter=..., metric_reader=...)`) before
  `TestClient(app)` or `fastmcp.Client(mcp)`; the API lifespan on `staging` already calls `init_telemetry(settings.otel)`
  (`app.py`), which after runtime is a no-op that returns True, and after entry-points still is; (2) the MCP tests use
  the in-memory client and never call `main()`, the only code entry-points changes in the MCP servers; (3) the only
  file both units touch is `api/app.py`, entry-points in `lifespan` and this unit after the CORS `add_middleware`
  block, separate hunks; (4) the tests assert inside the `with TestClient(app)` block, so the `shutdown_telemetry()`
  that entry-points adds at lifespan exit cannot affect them. The plan keeps the two units unordered.
- **Outbound requests carry `traceparent` and `tracestate` only, never `baggage`.** LLM and embedding endpoints may be
  third-party (OpenAI, hosted gateways); baggage from an inbound caller could carry user data there, and MintMory
  itself sets none. A fixed `TraceContextTextMapPropagator` is used for outbound headers; inbound extraction keeps the
  global propagator (`OTEL_PROPAGATORS`), as runtime requires.
- **Error marking is runtime's `mark_error`** (one helper, also used by heavy-path's `search_phase`).
- **`asyncio.CancelledError` is not an error**: a client that goes away is not a server failure.
- **An exception after the response started keeps the sent status** on the span and duration point (the client saw
  it), and the span is still marked with `mark_error`.
- **`server.port` defaults to 443/80 by scheme** when the URL has none, matching runtime's `_endpoint_reachable`.
