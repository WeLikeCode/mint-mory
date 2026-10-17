"""``search_phase`` and ``timed_phase``: the timing helper behind search spans (task 1.3).

Spec: observability › Search phase spans and latency, and observability › Span helpers without
work or with a failure.

``search_phase(name)`` is a context manager yielding an object with ``set_count(n)``. It opens
``mintmory.search.<name>`` when ``span`` is true, sets ``mintmory.result_count`` and records one
``mintmory.search.latency_ms`` histogram point (unit ``ms``, ``phase=name``) in a ``finally``. A
failing stage is marked with ``mark_error`` and re-raised; a metric failure stays inside
telemetry. ``timed_phase(name)`` is the same timing without a span.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry

pytest.importorskip("opentelemetry.sdk")


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


@pytest.mark.l4("C-f4b27f0d")
def test_search_phase_opens_a_span_and_records_a_latency_point() -> None:
    """The block's span carries the set count; the histogram carries ``phase`` and ``unit=ms``."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True

    with telemetry.search_phase("fts") as phase:
        assert phase is not None
        phase.set_count(3)

    spans = _finished_by_name(exporter)
    assert "mintmory.search.fts" in spans, sorted(spans)
    attributes = dict(spans["mintmory.search.fts"].attributes or {})
    assert attributes["mintmory.result_count"] == 3

    metric = _metric(reader, "mintmory.search.latency_ms")
    assert metric is not None, "the latency histogram was not recorded"
    assert metric.unit == "ms"
    points = _points(reader, "mintmory.search.latency_ms")
    assert len(points) == 1, points
    point = points[0]
    assert dict(point.attributes)["phase"] == "fts"
    assert point.count == 1
    assert point.sum >= 0


@pytest.mark.l4("C-c986421b")
def test_search_phase_records_zero_for_a_stage_with_nothing_to_do() -> None:
    """A stage that found nothing still has its span (count 0) and its latency point."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True

    with telemetry.search_phase("vector") as phase:
        assert phase is not None
        phase.set_count(0)

    spans = _finished_by_name(exporter)
    assert "mintmory.search.vector" in spans, sorted(spans)
    attributes = dict(spans["mintmory.search.vector"].attributes or {})
    assert attributes["mintmory.result_count"] == 0

    points = _points(reader, "mintmory.search.latency_ms")
    assert [dict(point.attributes).get("phase") for point in points] == ["vector"]


@pytest.mark.l4("C-20646f63")
def test_search_phase_marks_a_failing_stage_and_records_latency() -> None:
    """The exception propagates; the span is ERROR with ``error.type``; the point exists."""
    from opentelemetry.trace import StatusCode

    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True

    with (
        pytest.raises(RuntimeError, match="phase-boom"),
        telemetry.search_phase("fts") as phase,
    ):
        assert phase is not None
        phase.set_count(1)
        raise RuntimeError("phase-boom")

    spans = _finished_by_name(exporter)
    assert "mintmory.search.fts" in spans, sorted(spans)
    failed = spans["mintmory.search.fts"]
    assert failed.status.status_code == StatusCode.ERROR
    attributes = dict(failed.attributes or {})
    assert attributes["error.type"] == "RuntimeError"

    points = _points(reader, "mintmory.search.latency_ms")
    assert [dict(point.attributes).get("phase") for point in points] == ["fts"]


@pytest.mark.l4("C-0d312d3f")
def test_search_phase_swallows_a_metric_recording_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising ``record_value`` never escapes; the span still carries the real count."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True

    def _broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("metric-boom")

    monkeypatch.setattr(telemetry, "record_value", _broken)

    with telemetry.search_phase("substring") as phase:
        assert phase is not None
        phase.set_count(2)

    spans = _finished_by_name(exporter)
    assert "mintmory.search.substring" in spans, sorted(spans)
    attributes = dict(spans["mintmory.search.substring"].attributes or {})
    assert attributes["mintmory.result_count"] == 2


@pytest.mark.l4("C-43d72c8b")
def test_timed_phase_records_only_the_phase_point() -> None:
    """The decorator returns the answer, opens no span and records its ``graph`` point."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True

    decorator = telemetry.timed_phase("graph")
    assert decorator is not None

    def probe() -> str:
        return "graph-result"

    wrapped: Any = decorator(probe)
    assert wrapped is not None
    assert wrapped() == "graph-result"

    assert list(exporter.get_finished_spans()) == []
    points = _points(reader, "mintmory.search.latency_ms")
    assert [dict(point.attributes).get("phase") for point in points] == ["graph"]
    metric = _metric(reader, "mintmory.search.latency_ms")
    assert metric is not None
    assert metric.unit == "ms"


@pytest.mark.l4("C-f4b27f0d")
def test_search_phase_without_a_span_still_yields_a_count_setter() -> None:
    """With telemetry off the helper is a no-op but still yields an object the block can use."""
    assert telemetry.is_enabled() is False

    with telemetry.search_phase("fts", span=False) as phase:
        assert phase is not None
        phase.set_count(1)
