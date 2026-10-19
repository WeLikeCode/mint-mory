"""``OpenAIEmbedder.embed_batch`` forwards headers; ``inject_trace_headers`` obeys the off switch.

Spec: observability › Outbound calls carry the trace context.

FB-005 items 2 and 4: the batch embedding path had no test that it passes ``extra_headers`` to
the OpenAI client, and removing the ``_enabled`` check from ``inject_trace_headers`` failed no
test. The first test drives ``OpenAIEmbedder.embed_batch`` with a stub client and asserts the
caller's current ``traceparent`` reached ``extra_headers``. The second leaves a valid span in the
current context, switches telemetry off and asserts the helper still returns the carrier
untouched, so a helper that ignores the switch fails by assertion.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.embedder import OpenAIEmbedder

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


def _in_memory_span_exporter() -> Any:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    return InMemorySpanExporter()


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
        self.inputs: list[str] | None = None

    def create(self, *, input: list[str], model: str, **kwargs: Any) -> _StubEmbeddingResponse:
        self.extra_headers = kwargs.get("extra_headers")
        self.inputs = input
        return _StubEmbeddingResponse(
            [
                _StubEmbeddingItem([0.5] * OpenAIEmbedder._DIMENSIONS, index)
                for index, _text in enumerate(input)
            ]
        )


class _StubOpenAIClient:
    def __init__(self) -> None:
        self.embeddings = _StubEmbeddings()


def _openai_embedder() -> tuple[OpenAIEmbedder, _StubOpenAIClient]:
    client = _StubOpenAIClient()
    embedder = OpenAIEmbedder.__new__(OpenAIEmbedder)
    embedder._client = client
    return embedder, client


def test_openai_embed_batch_passes_the_current_traceparent_as_extra_headers() -> None:
    """``embed_batch`` sends the embedding span's ``traceparent`` in ``extra_headers``."""
    exporter = _in_memory_span_exporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True
    embedder, client = _openai_embedder()

    vectors = embedder.embed_batch(["alpha", "beta"])

    assert len(vectors) == 2
    assert client.embeddings.inputs == ["alpha", "beta"]
    extra_headers = client.embeddings.extra_headers
    assert extra_headers is not None, "embed_batch must pass extra_headers"
    traceparent = extra_headers.get("traceparent")
    assert traceparent is not None, extra_headers

    spans = [span for span in exporter.get_finished_spans() if span.name == "mintmory.embed"]
    assert len(spans) == 1, [span.name for span in exporter.get_finished_spans()]
    assert traceparent.split("-")[2] == format(spans[0].context.span_id, "016x")


def test_inject_trace_headers_leaves_the_carrier_untouched_when_telemetry_is_off() -> None:
    """With a valid span current but telemetry off, the helper still adds no header."""
    from opentelemetry import context as otel_context

    exporter = _in_memory_span_exporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True

    headers: dict[str, str] = {"x-custom": "keep"}
    with telemetry.span("caller"):
        captured = otel_context.get_current()

    telemetry.reset_telemetry()
    assert telemetry.is_enabled() is False

    token = otel_context.attach(captured)
    try:
        returned = telemetry.inject_trace_headers(headers)
    finally:
        otel_context.detach(token)

    assert returned is headers
    assert headers == {"x-custom": "keep"}
    assert "traceparent" not in headers, headers
