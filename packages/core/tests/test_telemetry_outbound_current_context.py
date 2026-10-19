"""Baggage is never forwarded even when the caller context is the current context (FB-003).

Spec: observability › Outbound calls carry the trace context.

The committed ``test_chat_forwards_tracestate_and_never_baggage`` passes the caller context as
``context=`` to the wrapping span, so that context's ``baggage`` never becomes *current*: the
assertion "no baggage header" holds for the wrong reason. Swapping the fixed W3C trace-context
propagator for the global (composite) propagator would therefore not fail any test.

These tests attach the extracted caller context (which carries ``baggage``) as the *current*
context, so the baggage is live when the chat request and ``inject_trace_headers`` run. The
server must still receive the caller's ``traceparent`` and ``tracestate`` and no ``baggage``
header.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.llm import post_chat_completion

pytest.importorskip("opentelemetry.sdk")

_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
_PARENT_SPAN_ID = "00f067aa0ba902b7"
_CALLER_TRACEPARENT = f"00-{_TRACE_ID}-{_PARENT_SPAN_ID}-01"
_BAGGAGE = "user=SENTINEL-BAG-current"


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default providers, so repeated inits stay meaningful."""
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


class _RecordingServer:
    """A local HTTP server that records the headers of every POST it answers."""

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self._headers: list[dict[str, str]] = []
        self._lock = threading.Lock()
        receiver = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                if length:
                    self.rfile.read(length)
                with receiver._lock:
                    receiver._headers.append({k.lower(): v for k, v in self.headers.items()})
                payload = json.dumps(receiver._response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def host(self) -> str:
        return str(self._server.server_address[0])

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def headers(self) -> list[dict[str, str]]:
        """The recorded request headers, one dict per POST, in arrival order."""
        with self._lock:
            return list(self._headers)

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)


@pytest.fixture
def chat_server() -> Iterator[_RecordingServer]:
    """A local server answering the OpenAI-compatible chat-completions shape."""
    server = _RecordingServer({"choices": [{"message": {"content": "hi"}}]})
    try:
        yield server
    finally:
        server.shutdown()


def _in_memory_span_exporter() -> Any:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    return InMemorySpanExporter()


def _enable(exporter: Any) -> None:
    assert telemetry.init_telemetry(span_exporter=exporter) is True


def _caller_context() -> Any:
    return telemetry.extract_context(
        {
            "traceparent": _CALLER_TRACEPARENT,
            "tracestate": "vendor=1",
            "baggage": _BAGGAGE,
        }
    )


def _chat_request(server: _RecordingServer) -> dict[str, Any]:
    return post_chat_completion(
        base_url=server.base_url,
        api_key=None,
        payload={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        timeout_s=5.0,
        system="test",
        model="m",
    )


def _traceparent(headers: dict[str, str]) -> str:
    value = headers.get("traceparent")
    assert value is not None, headers
    return value


def test_chat_never_forwards_baggage_from_the_current_context(
    chat_server: _RecordingServer,
) -> None:
    """With the caller context attached as current, the chat request sends no baggage."""
    from opentelemetry import context as otel_context

    exporter = _in_memory_span_exporter()
    _enable(exporter)
    caller_context = _caller_context()

    token = otel_context.attach(caller_context)
    try:
        with telemetry.span("caller"):
            _chat_request(chat_server)
    finally:
        otel_context.detach(token)

    received = chat_server.headers
    assert received, "the server must have received the chat request"
    headers = received[0]
    assert headers.get("tracestate") == "vendor=1", headers
    assert "baggage" not in headers, headers
    assert _traceparent(headers).split("-")[1] == _TRACE_ID
    assert _BAGGAGE not in json.dumps(headers)


def test_inject_trace_headers_never_forwards_baggage_from_the_current_context() -> None:
    """With the caller context attached as current, the helper adds no baggage header."""
    from opentelemetry import context as otel_context

    exporter = _in_memory_span_exporter()
    _enable(exporter)
    caller_context = _caller_context()

    token = otel_context.attach(caller_context)
    try:
        headers: dict[str, str] = {}
        with telemetry.span("local") as span:
            returned = telemetry.inject_trace_headers(headers)
            span_context = span.get_span_context()
    finally:
        otel_context.detach(token)

    assert returned is headers
    assert "traceparent" in headers, headers
    assert headers["traceparent"].split("-")[1] == _TRACE_ID
    assert format(span_context.trace_id, "032x") == _TRACE_ID
    assert headers.get("tracestate") == "vendor=1"
    assert "baggage" not in headers, headers
    assert _BAGGAGE not in json.dumps(headers)
