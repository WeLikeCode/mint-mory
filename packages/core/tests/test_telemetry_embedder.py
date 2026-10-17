"""``mintmory.embed`` spans and latency for the hashing and fake embedders (task 3.1).

Spec: observability › Embedding spans and latency.

Every public ``embed``/``embed_batch`` call records exactly one ``mintmory.embed`` span with the
provider, model, batch size and dimension, and one ``mintmory.embed.latency_ms`` point. A public
method that calls another (``FakeEmbedder.embed_batch`` calls ``embed``, and both hash embedders'
``embed`` calls ``embed_batch``) still records once: the re-entrancy guard keeps the outer call's
span. A failing embedder marks its span with ``mark_error``, records its point and re-raises.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.embedder import FakeEmbedder, HashingEmbedder

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


@pytest.mark.l4("C-53f9b64c")
def test_hashing_embed_batch_records_one_span_and_one_latency_point() -> None:
    """``HashingEmbedder().embed_batch(["a", "b"])`` records provider, batch size and dimension."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    _init(exporter, reader)
    embedder = HashingEmbedder()

    vectors = embedder.embed_batch(["a", "b"])

    assert len(vectors) == 2
    assert vectors[0].shape == (embedder.dimensions,)

    spans = _finished_by_name(exporter)
    assert set(spans) == {_EMBED_SPAN}, sorted(spans)
    attributes = dict(spans[_EMBED_SPAN].attributes or {})
    assert attributes["mintmory.embed.provider"] == "hashing"
    assert attributes["gen_ai.request.model"] == embedder.model_name
    assert attributes["mintmory.embed.batch_size"] == 2
    assert attributes["mintmory.embed.dim"] == embedder.dimensions

    metric = _metric(reader, _EMBED_LATENCY)
    assert metric is not None, "the embed latency histogram was not recorded"
    assert metric.unit == "ms"
    points = _points(reader, _EMBED_LATENCY)
    assert len(points) == 1, points
    point = points[0]
    assert point.count == 1
    point_attributes = dict(point.attributes)
    assert point_attributes["provider"] == "hashing"
    assert point_attributes["model"] == embedder.model_name


@pytest.mark.l4("C-53f9b64c")
def test_hashing_embed_records_one_span_with_batch_size_one() -> None:
    """A single ``embed`` call is one span with batch size 1, not one per inner batch call."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    _init(exporter, reader)
    embedder = HashingEmbedder(dim=64)

    vector = embedder.embed("only one")

    assert vector.shape == (64,)
    spans = _finished_by_name(exporter)
    assert set(spans) == {_EMBED_SPAN}, sorted(spans)
    attributes = dict(spans[_EMBED_SPAN].attributes or {})
    assert attributes["mintmory.embed.provider"] == "hashing"
    assert attributes["mintmory.embed.batch_size"] == 1
    assert attributes["mintmory.embed.dim"] == 64
    assert len(_points(reader, _EMBED_LATENCY)) == 1


@pytest.mark.l4("C-53f9b64c")
def test_fake_embed_batch_that_calls_embed_records_once() -> None:
    """``FakeEmbedder.embed_batch`` calls ``embed`` yet exports a single span for the batch."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    _init(exporter, reader)
    embedder = FakeEmbedder(dim=32)

    vectors = embedder.embed_batch(["alpha", "beta"])

    assert len(vectors) == 2
    spans = _finished_by_name(exporter)
    assert set(spans) == {_EMBED_SPAN}, sorted(spans)
    attributes = dict(spans[_EMBED_SPAN].attributes or {})
    assert attributes["mintmory.embed.provider"] == "fake"
    assert attributes["gen_ai.request.model"] == embedder.model_name
    assert attributes["mintmory.embed.batch_size"] == 2
    assert attributes["mintmory.embed.dim"] == 32
    assert len(_points(reader, _EMBED_LATENCY)) == 1


@pytest.mark.l4("C-53f9b64c")
def test_fake_embed_records_one_span_with_batch_size_one() -> None:
    """A single ``FakeEmbedder.embed`` call is also exactly one span and one point."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    _init(exporter, reader)
    embedder = FakeEmbedder()

    vector = embedder.embed("alpha")

    assert vector.shape == (embedder.dimensions,)
    spans = _finished_by_name(exporter)
    assert set(spans) == {_EMBED_SPAN}, sorted(spans)
    attributes = dict(spans[_EMBED_SPAN].attributes or {})
    assert attributes["mintmory.embed.provider"] == "fake"
    assert attributes["mintmory.embed.batch_size"] == 1
    assert attributes["mintmory.embed.dim"] == embedder.dimensions
    assert len(_points(reader, _EMBED_LATENCY)) == 1


@pytest.mark.l4("C-53f9b64c")
def test_a_failing_embed_batch_is_marked_and_re_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An embedder whose batch call raises exports one ERROR span and its latency point."""
    from opentelemetry.trace import StatusCode

    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    _init(exporter, reader)
    embedder = HashingEmbedder(dim=16)

    def _boom(text: str) -> list[str]:
        raise RuntimeError("embed-boom")

    monkeypatch.setattr(embedder, "_features", _boom)

    with pytest.raises(RuntimeError, match="embed-boom"):
        embedder.embed_batch(["alpha"])

    spans = _finished_by_name(exporter)
    assert set(spans) == {_EMBED_SPAN}, sorted(spans)
    failed = spans[_EMBED_SPAN]
    assert failed.status.status_code == StatusCode.ERROR
    attributes = dict(failed.attributes or {})
    assert attributes["error.type"] == "RuntimeError"
    assert attributes["mintmory.embed.provider"] == "hashing"

    points = _points(reader, _EMBED_LATENCY)
    assert len(points) == 1, points
    assert dict(points[0].attributes)["provider"] == "hashing"
