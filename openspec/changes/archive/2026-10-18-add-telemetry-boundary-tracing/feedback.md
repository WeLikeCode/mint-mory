# Feedback — add-telemetry-boundary-tracing

<!-- l4:feedback v1
Ask for changes here while the unit's branch is open. The easy way is `l4 feedback add` (see `l4 feedback --help`).
An item is read only when its **Status** is `submitted`; `draft` items wait and `withdrawn` items are ignored.
Kinds: refactor · duplication · tests · config · behaviour (see docs/feedback.md).
Do not change item IDs. Commit and push to the l4/… branch: the harness takes submitted items at its next
verification round, turns them into a fix unit and checks that each one was addressed. -->

<!-- l4:feedback-index:start -->
| ID | Status | Kind | Where | Feedback |
|----|--------|------|-------|----------|
| FB-001 | submitted | behaviour | packages/api/src/mintmory/api/telemetry_middleware.py:126 | Guard route.path and the status comparison in the middleware's finally |
| FB-002 | submitted | behaviour | packages/core/src/mintmory/core/llm.py:107 | Telemetry must not change what an LLM call raises: reading |
| FB-003 | submitted | tests | packages/core/tests/test_telemetry_outbound.py:218 | The 'baggage is never forwarded' half of the outbound criterion is not |
| FB-004 | submitted | tests | packages/mcp/tests/test_telemetry_mcp.py:237 | test_tool_arguments_never_reach_telemetry never asserts that any span |
| FB-005 | submitted | tests |  | Weak or missing tests from the review of PR #29: (1) in |
<!-- l4:feedback-index:end -->

---

## FB-001: Guard route.path and the status comparison in the middleware's finally

- **Status:** submitted
- **Kind:** behaviour
- **Where:** `packages/api/src/mintmory/api/telemetry_middleware.py:126-146`
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-18T18:32:24Z

### Code
```python
        finally:
            route = scope.get("route")
            route_path = None if route is None else route.path
            if route_path is not None:
                _safe(span.update_name, f"{method} {route_path}")

            status = sent[0] if sent else None
            if status is None and error is not None:
                status = _INTERNAL_ERROR_STATUS

            attributes: dict[str, Any] = {_REQUEST_METHOD: method}
            if route_path is not None:
                attributes[_ROUTE] = route_path
            if status is not None:
                attributes[_RESPONSE_STATUS] = status
            _safe(span.set_attributes, attributes)

            if error is not None:
                _safe(telemetry.mark_error, span, type(error).__name__)
            elif status is not None and status >= _INTERNAL_ERROR_STATUS:
                _safe(telemetry.mark_error, span, str(status))
```

### Feedback
Guard route.path and the status comparison in the middleware's finally block: they are read outside _safe, so either can raise, replace the app's outcome and leave the span open (review of PR #29; cannot happen on FastAPI 0.137.1, a guard against a later version).

### When / Then
- **When:** the matched route in scope["route"] has no path attribute, or the response status the app sent is not an int
- **Then:** the middleware still returns or raises exactly what the app did, and the request span is ended

### Outcome
<!-- written by the harness -->

---

## FB-002: Telemetry must not change what an LLM call raises: reading

- **Status:** submitted
- **Kind:** behaviour
- **Where:** `packages/core/src/mintmory/core/llm.py:107-110`
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-18T18:32:25Z

### Code
```python
    parsed = urllib.parse.urlsplit(base_url)
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
```

### Feedback
Telemetry must not change what an LLM call raises: reading urlsplit(base_url).port for the span attributes raises ValueError before the request is made (review of PR #29).

### When / Then
- **When:** post_chat_completion is called with a base_url whose port is malformed (for example :abc or :99999)
- **Then:** it raises the same exception class as it did before telemetry was added (http.client.InvalidURL or urllib.error.URLError), not ValueError from reading the port

### Outcome
<!-- written by the harness -->

---

## FB-003: The 'baggage is never forwarded' half of the outbound criterion is not

- **Status:** submitted
- **Kind:** tests
- **Where:** `packages/core/tests/test_telemetry_outbound.py:218-240`
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-18T18:32:25Z

### Code
```python
def test_chat_forwards_tracestate_and_never_baggage(chat_server: _RecordingServer) -> None:
    """A caller's ``tracestate`` is forwarded; its ``baggage`` never leaves MintMory."""
    exporter = _in_memory_span_exporter()
    _enable(exporter)
    caller_context = telemetry.extract_context(
        {
            "traceparent": _CALLER_TRACEPARENT,
            "tracestate": "vendor=1",
            "baggage": "user=SENTINEL-BAG-3",
        }
    )

    with telemetry.span("caller", context=caller_context):
        _chat_request(chat_server)

    received = chat_server.headers
    assert received, "the server must have received the chat request"
    headers = received[0]
    assert headers.get("tracestate") == "vendor=1", headers
    assert "baggage" not in headers, headers
    assert _traceparent(headers).split("-")[1] == _TRACE_ID
```

### Feedback
The 'baggage is never forwarded' half of the outbound criterion is not tested: with the global propagator in place of the fixed one the baggage tests still pass, because the caller context is passed as context= and its baggage never becomes current. Add a test: WHEN the extracted caller context, carrying baggage, is attached as the current context around the chat request (and around inject_trace_headers) THEN the server receives traceparent and tracestate and no baggage header.

### Outcome
<!-- written by the harness -->

---

## FB-004: test_tool_arguments_never_reach_telemetry never asserts that any span

- **Status:** submitted
- **Kind:** tests
- **Where:** `packages/mcp/tests/test_telemetry_mcp.py:237-260`
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-18T18:32:26Z

### Code
```python
async def test_tool_arguments_never_reach_telemetry(
    mcp_client: tuple[Client[Any], Any],
) -> None:
    """Neither the search query nor the note text appears anywhere in the exported spans."""
    client, exporter = mcp_client

    res = await client.call_tool("memory_search", {"query": "SENTINEL-ARG-4f"})
    assert res.is_error is False
    assert res.data["session_id"], "the search must have produced a session"
    note = await client.call_tool("memory_note", {"content": "SENTINEL-ARG-9a"})
    assert note.is_error is False
    assert note.data["note"]["is_note"] is True

    exported = _telemetry_text(exporter)
    assert "SENTINEL-ARG-4f" not in exported
    assert "SENTINEL-ARG-9a" not in exported


# ---------------------------------------------------------------------------
# Context in _meta is continued
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-da502b68")
```

### Feedback
test_tool_arguments_never_reach_telemetry never asserts that any span was exported, so it passes if export silently stops; assert the tool-call span exists before checking that no argument reached it.

### Outcome
<!-- written by the harness -->

---

## FB-005: Weak or missing tests from the review of PR #29: (1) in

- **Status:** submitted
- **Kind:** tests
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-18T18:32:26Z

### Feedback
Weak or missing tests from the review of PR #29: (1) in packages/api/tests/test_telemetry_http_middleware.py the C-5fd2f50f test's final caplog assertion is already satisfied by _safe_drops_a_failure: assert the specific failure instead; (2) OpenAIEmbedder.embed_batch passing extra_headers has no test; (3) the 443/80 default-port branch of the LLM span attributes has no test; (4) removing the _enabled check from inject_trace_headers fails no test.

### Outcome
<!-- written by the harness -->
