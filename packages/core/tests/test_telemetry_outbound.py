"""Outbound LLM and embedding calls carry the trace context (task 4.1).

Spec: observability › Outbound calls carry the trace context.

``gen_ai.chat`` is a CLIENT span with ``server.address``/``server.port``; every outbound
chat request and embedding request carries the W3C ``traceparent`` (and ``tracestate`` when the
span context has one) injected inside the wrapping span, so that span is the remote side's
parent. ``baggage`` is never forwarded, and with telemetry off no header is added.

Each test starts a real ``ThreadingHTTPServer`` daemon that records the request headers it
receives, then asserts the exported span and the header agree. The tests fail by assertion
against the current code (no header is injected and ``gen_ai.chat`` is not a CLIENT span).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.embedder import OllamaEmbedder, OpenAIEmbedder
from mintmory.core.llm import post_chat_completion

pytest.importorskip("opentelemetry.sdk")

_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
_PARENT_SPAN_ID = "00f067aa0ba902b7"
_CALLER_TRACEPARENT = f"00-{_TRACE_ID}-{_PARENT_SPAN_ID}-01"


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


@pytest.fixture
def embedding_server() -> Iterator[_RecordingServer]:
    """A local server answering the Ollama-compatible embeddings shape."""
    server = _RecordingServer({"data": [{"embedding": [0.25] * 8, "index": 0}]})
    try:
        yield server
    finally:
        server.shutdown()


def _in_memory_span_exporter() -> Any:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    return InMemorySpanExporter()


def _enable(exporter: Any) -> None:
    assert telemetry.init_telemetry(span_exporter=exporter) is True


def _finished_by_name(exporter: Any) -> dict[str, Any]:
    return {span.name: span for span in exporter.get_finished_spans()}


def _embed_span(exporter: Any, provider: str) -> Any:
    spans = [
        span
        for span in exporter.get_finished_spans()
        if span.name == "mintmory.embed"
        and dict(span.attributes or {}).get("mintmory.embed.provider") == provider
    ]
    assert len(spans) == 1, spans
    return spans[0]


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


class _StubEmbeddingItem:
    def __init__(self, embedding: list[float], index: int) -> None:
        self.embedding = embedding
        self.index = index


class _StubEmbeddingResponse:
    def __init__(self, data: list[_StubEmbeddingItem]) -> None:
        self.data = data


class _StubEmbeddings:
    def __init__(self) -> None:
        self.extra_headers: dict[str, str] | None = None

    def create(self, *, input: list[str], model: str, **kwargs: Any) -> _StubEmbeddingResponse:
        self.extra_headers = kwargs.get("extra_headers")
        items = [
            _StubEmbeddingItem([0.5] * OpenAIEmbedder._DIMENSIONS, index)
            for index, _text in enumerate(input)
        ]
        return _StubEmbeddingResponse(items)


class _StubOpenAIClient:
    def __init__(self) -> None:
        self.embeddings = _StubEmbeddings()


@pytest.mark.l4("C-83e1a4e6")
def test_chat_endpoint_receives_the_span_traceparent(chat_server: _RecordingServer) -> None:
    """The chat request carries the ``gen_ai.chat`` CLIENT span's ``traceparent``."""
    from opentelemetry.trace import SpanKind

    exporter = _in_memory_span_exporter()
    _enable(exporter)

    _chat_request(chat_server)

    span = _finished_by_name(exporter)["gen_ai.chat"]
    assert span.kind == SpanKind.CLIENT
    attributes = dict(span.attributes or {})
    assert attributes["server.address"] == "127.0.0.1"
    assert attributes["server.port"] == chat_server.port

    received = chat_server.headers
    assert received, "the server must have received the chat request"
    parts = _traceparent(received[0]).split("-")
    assert parts[1] == format(span.context.trace_id, "032x")
    assert parts[2] == format(span.context.span_id, "016x")


@pytest.mark.l4("C-9970c315")
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


@pytest.mark.l4("C-d1b2babd")
def test_embedding_endpoints_receive_the_embed_span_traceparent(
    embedding_server: _RecordingServer,
) -> None:
    """Both embedders inject their ``mintmory.embed`` span's ``traceparent``."""
    exporter = _in_memory_span_exporter()
    _enable(exporter)

    ollama = OllamaEmbedder(model="nomic-embed-text", dim=8, base_url=embedding_server.base_url)
    vector = ollama.embed("alpha")
    assert vector.shape == (8,)

    ollama_span = _embed_span(exporter, "ollama")
    ollama_headers = embedding_server.headers
    assert ollama_headers, "the Ollama embedder must have called the endpoint"
    parts = _traceparent(ollama_headers[0]).split("-")
    assert parts[2] == format(ollama_span.context.span_id, "016x")

    client = _StubOpenAIClient()
    openai = OpenAIEmbedder.__new__(OpenAIEmbedder)
    openai._client = client
    openai_vector = openai.embed("a")
    assert openai_vector.shape == (OpenAIEmbedder._DIMENSIONS,)

    openai_span = _embed_span(exporter, "openai")
    extra_headers = client.embeddings.extra_headers
    assert extra_headers is not None, "OpenAIEmbedder must pass extra_headers"
    assert _traceparent(extra_headers).split("-")[2] == format(openai_span.context.span_id, "016x")


@pytest.mark.l4("C-c2076c0f")
def test_no_traceparent_when_telemetry_is_off(chat_server: _RecordingServer) -> None:
    """With telemetry off no header is added; with it on the same request carries one."""
    telemetry.reset_telemetry()
    assert telemetry.inject_trace_headers({}) == {}

    _chat_request(chat_server)

    assert chat_server.headers, "the server must have received the chat request"
    assert "traceparent" not in chat_server.headers[0]

    exporter = _in_memory_span_exporter()
    _enable(exporter)
    with telemetry.span("caller"):
        _chat_request(chat_server)

    assert "traceparent" in chat_server.headers[1], chat_server.headers[1]
