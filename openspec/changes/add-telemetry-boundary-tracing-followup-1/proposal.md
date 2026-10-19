# Proposal: follow-up 1 for add-telemetry-boundary-tracing

## Why
Requested by CiprianSpot, 2026-10-18T18:32:24Z in FB-001 (behaviour, packages/api/src/mintmory/api/telemetry_middleware.py:126-146): Guard route.path and the status comparison in the middleware's finally block: they are read outside _safe, so either can raise, replace the app's outcome and leave the span open (review of PR #29; cannot happen on FastAPI 0.137.1, a guard against a later version).

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

Requested by CiprianSpot, 2026-10-18T18:32:25Z in FB-002 (behaviour, packages/core/src/mintmory/core/llm.py:107-110): Telemetry must not change what an LLM call raises: reading urlsplit(base_url).port for the span attributes raises ValueError before the request is made (review of PR #29).

        parsed = urllib.parse.urlsplit(base_url)
        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80

Requested by CiprianSpot, 2026-10-18T18:32:25Z in FB-003 (tests, packages/core/tests/test_telemetry_outbound.py:218-240): The 'baggage is never forwarded' half of the outbound criterion is not tested: with the global propagator in place of the fixed one the baggage tests still pass, because the caller context is passed as context= and its baggage never becomes current. Add a test: WHEN the extracted caller context, carrying baggage, is attached as the current context around the chat request (and around inject_trace_headers) THEN the server receives traceparent and tracestate and no baggage header.

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

Requested by CiprianSpot, 2026-10-18T18:32:26Z in FB-004 (tests, packages/mcp/tests/test_telemetry_mcp.py:237-260): test_tool_arguments_never_reach_telemetry never asserts that any span was exported, so it passes if export silently stops; assert the tool-call span exists before checking that no argument reached it.

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

Requested by CiprianSpot, 2026-10-18T18:32:26Z in FB-005 (tests): Weak or missing tests from the review of PR #29: (1) in packages/api/tests/test_telemetry_http_middleware.py the C-5fd2f50f test's final caplog assertion is already satisfied by _safe_drops_a_failure: assert the specific failure instead; (2) OpenAIEmbedder.embed_batch passing extra_headers has no test; (3) the 443/80 default-port branch of the LLM span attributes has no test; (4) removing the _enabled check from inject_trace_headers fails no test.

`add-telemetry-boundary-tracing` was merged, and a person asked for the changes above in its `feedback.md`. This change carries them out; each task names the finding it answers.

## What Changes
- F-3693beea: Feedback FB-001 (behaviour): Guard route.path and the status comparison in the middleware's finally
- F-23a0a190: Feedback FB-002 (behaviour): Telemetry must not change what an LLM call raises: reading
- F-d97951ca: Feedback FB-003 (tests): The 'baggage is never forwarded' half of the outbound criterion is not
- F-47d25d08: Feedback FB-004 (tests): test_tool_arguments_never_reach_telemetry never asserts that any span
- F-a0274ee1: Feedback FB-005 (tests): Weak or missing tests from the review of PR #29: (1) in

## Impact
The code and the tests of `add-telemetry-boundary-tracing`.
