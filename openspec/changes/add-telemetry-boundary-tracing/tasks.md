# Tasks: distributed traces across the boundaries (OpenTelemetry, part 3 of 4)

Requires `add-telemetry-runtime` and `add-telemetry-heavy-path-spans` (`mintmory.embed`; `span()`'s `kind`, `context`,
`record_exception`, `set_status_on_exception` and `_NoopSpan.update_name`, used here, not changed). No new dependency,
no `uv.lock` change; import `opentelemetry` lazily. Tests: `pytest.importorskip("opentelemetry.sdk")`, in-memory
exporter and reader injected before `TestClient`/`fastmcp.Client`, `asyncio_mode = "auto"`. Each test first, failing.

## 1. Telemetry helpers (`core/telemetry.py`)
- [x] 1.1 Tests for the header helpers on and off (`extract_context` of `garbage` returns, `inject_trace_headers` off
  returns the dict unchanged).
- [ ] 1.2 `inject_trace_headers(headers)`: `TraceContextTextMapPropagator().inject(headers)` when enabled, returns
  `headers`. `extract_context(carrier)`: `opentelemetry.propagate.extract(carrier)` when enabled, else `None`. Both in
  `try/except Exception`.
- [ ] 1.3 `_instrument(kind, factory_name, name, **options)` passes `options` to the factory on first creation
  (heavy-path's `unit` included). `record_histogram(name, value, *, unit, boundaries=None, **attrs)`: through it with
  `unit` and `explicit_bucket_boundaries_advisory=boundaries`, `None` attributes dropped, no-op when metrics are off,
  body in `try/except Exception`.

## 2. HTTP middleware (`api/telemetry_middleware.py`)
- [ ] 2.1 `packages/api/tests/test_telemetry_http.py`, every scenario of the five HTTP requirements. API setup copies
  the `client` fixture of `packages/api/tests/test_routes.py` (`MINTMORY_DB` in `tmp_path`, `app_module._store` reset,
  `TestClient(app_module.app)` in `with`), telemetry initialised first; assert inside the block. `/test-raise` via
  `app_module.app.add_api_route`, removed from `app.router.routes` at teardown.
- [ ] 2.2 Call helpers as `telemetry.<name>` so tests can patch them. Pass through: non-`http` scope, telemetry off,
  `/healthz`, `/readyz`, excluded paths. `_safe(step, *args)` runs one step in `try/except Exception`, logging DEBUG
  `telemetry: http middleware step failed (<class>)`. Headers decoded with `latin-1`; the span entered with
  `contextlib.ExitStack.enter_context` (failure: `return await self.app(...)`); `time.perf_counter()` around
  `await self.app(scope, receive, wrapped_send)`; `except Exception as exc` keeps `exc` and re-raises; the `finally`
  applies, each through `_safe`, the name, attributes, `mark_error`, `record_histogram(..., unit="s",
  boundaries=_HTTP_BUCKETS)` and `stack.close()`.
- [ ] 2.3 `app.add_middleware(TelemetryMiddleware)` after the CORS block. Store calls run in
  `anyio.to_thread.run_sync`, which copies the context (anyio 4.13.0), so core spans are children of the server span.

## 3. MCP (tests only)
- [ ] 3.1 `packages/mcp/tests/test_telemetry_mcp.py`, every scenario of "MCP tool calls are traced once". Clients as the
  `mcp_client` fixture of `test_tools.py` and the `history_client` fixture of `test_history_mcp.py`, copied.
- [ ] 3.2 No MCP code, no span per tool call. A failing MCP test means runtime's provider is not global
  (`trace.get_tracer_provider()` is not `telemetry._tracer_provider`), the scrubber is not outermost, or FastMCP differs
  from the spec; the tests then stay failing and the unit is not done.

## 4. Outbound
- [ ] 4.1 Tests with a `ThreadingHTTPServer` daemon recording headers (chat JSON as in `core/tests/test_llm.py`; an
  Ollama-like embedding answer). `OpenAIEmbedder.__new__` with only `_client` set: `model_name` and `dimensions` are
  class-level properties.
- [ ] 4.2 `post_chat_completion`: `gen_ai.chat` with `kind="client"`, `server.address`/`server.port` from
  `urllib.parse.urlsplit`; `req.add_header(k, v)` for each injected header inside the span, before `urlopen`.
- [ ] 4.3 `OllamaEmbedder` injects the same way; `OpenAIEmbedder` passes `extra_headers=telemetry.inject_trace_headers({})`
  to `embeddings.create`, inside `mintmory.embed`.

## 5. Checks
- [ ] 5.1 `docs/OBSERVABILITY.md` section 4 gets "Distributed tracing" (what continues a trace, what MintMory sends).
  `ruff check`, `ruff format --check`, `mypy packages`, full suite, coverage at or above 80%.
