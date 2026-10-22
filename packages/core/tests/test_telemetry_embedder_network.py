"""``mintmory.embed`` spans and latency for the network/cached embedders (task 3.2).

Spec: observability › Embedding spans and latency › Network embedders name their model.

``OllamaEmbedder`` and ``OpenAIEmbedder`` each record one ``mintmory.embed`` span with their
``mintmory.embed.provider``, ``gen_ai.request.model`` and ``mintmory.embed.dim``, plus one
``mintmory.embed.latency_ms`` point. ``LocalEmbedder.embed`` and ``.embed_batch`` carry the same
shared decorator (their ``__wrapped__``), even though the local model itself cannot be loaded here.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.embedder import LocalEmbedder, OllamaEmbedder, OpenAIEmbedder

pytest.importorskip("opentelemetry.sdk")

_EMBED_SPAN = "mintmory.embed"
_EMBED_LATENCY = "mintmory.embed.latency_ms"


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


class _EmbeddingServer:
    """A local OpenAI-compatible ``/v1/embeddings`` endpoint recording each request body."""

    def __init__(self, dimension: int) -> None:
        self._dimension = dimension
        self._requests: list[bytes] = []
        self._lock = threading.Lock()
        receiver = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                with receiver._lock:
                    receiver._requests.append(body)
                payload = json.dumps(
                    {"data": [{"embedding": [0.25] * receiver._dimension, "index": 0}]}
                ).encode("utf-8")
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
    def base_url(self) -> str:
        """``http://127.0.0.1:<port>/v1`` — the Ollama embedder appends ``/embeddings``."""
        host = str(self._server.server_address[0])
        port = self._server.server_address[1]
        return f"http://{host}:{port}/v1"

    @property
    def requests(self) -> list[bytes]:
        """The JSON bodies of every embeddings POST received."""
        with self._lock:
            return list(self._requests)

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)


@pytest.fixture
def embedding_server() -> Iterator[_EmbeddingServer]:
    """A local ``ThreadingHTTPServer`` answering embeddings requests in a daemon thread."""
    server = _EmbeddingServer(dimension=8)
    try:
        yield server
    finally:
        server.shutdown()


def _in_memory_span_exporter() -> Any:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    return InMemorySpanExporter()


def _in_memory_metric_reader() -> Any:
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    return InMemoryMetricReader()


def _finished_by_name(exporter: Any) -> dict[str, Any]:
    return {span.name: span for span in exporter.get_finished_spans()}


def _metric(reader: Any, name: str) -> Any:
    data = reader.get_metrics_data()
    assert data is not None, "no metrics were exported"
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == name:
                    return metric
    return None


def _points(reader: Any, name: str) -> list[Any]:
    metric = _metric(reader, name)
    if metric is None:
        return []
    return list(metric.data.data_points)


def _init(exporter: Any, reader: Any) -> None:
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True


class _StubEmbeddingItem:
    def __init__(self, embedding: list[float], index: int) -> None:
        self.embedding = embedding
        self.index = index


class _StubEmbeddingResponse:
    def __init__(self, data: list[_StubEmbeddingItem]) -> None:
        self.data = data


class _StubEmbeddings:
    def create(self, *, input: list[str], model: str, **kwargs: Any) -> _StubEmbeddingResponse:
        items = [
            _StubEmbeddingItem([0.5] * OpenAIEmbedder._DIMENSIONS, index)
            for index, _text in enumerate(input)
        ]
        return _StubEmbeddingResponse(items)


class _StubOpenAIClient:
    def __init__(self) -> None:
        self.embeddings = _StubEmbeddings()


@pytest.mark.l4("C-755ec9f3")
def test_ollama_embed_names_provider_and_model(embedding_server: _EmbeddingServer) -> None:
    """``OllamaEmbedder`` against a local server records provider, model, dimension and a point."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    _init(exporter, reader)
    embedder = OllamaEmbedder(model="nomic-embed-text", dim=8, base_url=embedding_server.base_url)

    vector = embedder.embed("alpha")

    assert vector.shape == (8,)
    assert embedding_server.requests, "the embedder must call the embeddings endpoint"

    spans = _finished_by_name(exporter)
    assert set(spans) == {_EMBED_SPAN}, sorted(spans)
    attributes = dict(spans[_EMBED_SPAN].attributes or {})
    assert attributes["mintmory.embed.provider"] == "ollama"
    assert attributes["gen_ai.request.model"] == embedder.model_name
    assert attributes["mintmory.embed.dim"] == embedder.dimensions

    metric = _metric(reader, _EMBED_LATENCY)
    assert metric is not None, "the embed latency histogram was not recorded"
    assert metric.unit == "ms"
    points = _points(reader, _EMBED_LATENCY)
    assert len(points) == 1, points
    point_attributes = dict(points[0].attributes)
    assert point_attributes["provider"] == "ollama"
    assert point_attributes["model"] == embedder.model_name


@pytest.mark.l4("C-755ec9f3")
def test_openai_embed_names_provider_and_model() -> None:
    """``OpenAIEmbedder`` with a stub client records provider, model, dimension and a point."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    _init(exporter, reader)
    embedder = OpenAIEmbedder.__new__(OpenAIEmbedder)
    embedder._client = _StubOpenAIClient()

    vector = embedder.embed("alpha")

    assert vector.shape == (OpenAIEmbedder._DIMENSIONS,)

    spans = _finished_by_name(exporter)
    assert set(spans) == {_EMBED_SPAN}, sorted(spans)
    attributes = dict(spans[_EMBED_SPAN].attributes or {})
    assert attributes["mintmory.embed.provider"] == "openai"
    assert attributes["gen_ai.request.model"] == embedder.model_name
    assert attributes["mintmory.embed.dim"] == embedder.dimensions

    points = _points(reader, _EMBED_LATENCY)
    assert len(points) == 1, points
    assert dict(points[0].attributes)["provider"] == "openai"


@pytest.mark.l4("C-755ec9f3")
def test_local_embedder_methods_carry_the_shared_decorator() -> None:
    """``LocalEmbedder.embed`` and ``.embed_batch`` are wrapped by the shared embed decorator."""
    embed_wrapped = getattr(LocalEmbedder.embed, "__wrapped__", None)
    batch_wrapped = getattr(LocalEmbedder.embed_batch, "__wrapped__", None)
    assert embed_wrapped is not None, "LocalEmbedder.embed must carry the shared decorator"
    assert batch_wrapped is not None, "LocalEmbedder.embed_batch must carry the shared decorator"
    assert embed_wrapped.__name__ == "embed"
    assert batch_wrapped.__name__ == "embed_batch"
    assert embed_wrapped is not batch_wrapped
