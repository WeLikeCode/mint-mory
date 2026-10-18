# Design: boundary tracing

## Decisions

- **No dependency on `add-telemetry-entry-points`**: every test here initialises telemetry through runtime's seam
  before `TestClient`/`fastmcp.Client` and asserts inside the `with` block, so the lifespan's `init_telemetry` (a no-op
  after that) and the `shutdown_telemetry()` entry-points adds at exit cannot affect it; the MCP tests never call
  `main()`; in `app.py` the two units edit separate hunks (`lifespan` vs after the CORS block).
- **Server span flags off**, through the `span()` options `add-telemetry-heavy-path-spans` delivers (its
  `command_span` needs the same flags and runs first, so `span()` changes there, once): in OpenTelemetry 1.42.1,
  `start_as_current_span` wraps the span in `use_span` (`opentelemetry/trace/__init__.py`), whose `except Exception`
  records the message and sets `Status(ERROR, "<Class>: <message>")`; `Span.set_status` keeps only an OK status, so
  that would replace `mark_error`'s.
- **`asyncio.CancelledError` is not an error** (the client went away). It is a `BaseException`, caught neither by
  `use_span` nor by the middleware's `except Exception`.
- **No status sent**: after an `Exception` the middleware records 500, which Starlette's outer `ServerErrorMiddleware`
  sends (run on the locked versions, the middleware saw no `http.response.start` for a raising route); otherwise the
  attribute is left out, not guessed, and the duration point is still recorded.
- **Exception after the response started**: the sent status stays (the client saw it); the span is still marked.
- **Outermost middleware** (registered after CORS): CORS preflights are traced as `OPTIONS` with no route.
- **A 405 keeps its route**: FastAPI 0.137.1 `APIRoute.matches` sets `scope["route"]` on a partial match (run:
  `DELETE /stats` arrived with route `/stats`); a template is bounded, so naming by it is safe.
- **Middleware telemetry failures are dropped at DEBUG** with the class name only: telemetry never changes what a
  client receives, and no header value or message reaches the logs.
- **MCP relies on FastMCP's span, verified by running FastMCP 3.4.2** with an SDK provider and an in-memory exporter
  (every fact in the spec). `uv.lock` pins it and CI syncs `--frozen`; a test asserts the version, so a later FastMCP
  fails the tests and its bump re-checks the facts. No MintMory code reads the span.
- **Outbound headers are `traceparent` and `tracestate` only** (a fixed `TraceContextTextMapPropagator`): endpoints may
  be third-party and inbound baggage could carry user data. Inbound extraction keeps the global propagator.
- **`server.port` defaults to 443/80 by scheme**, as runtime's `_endpoint_reachable`.
