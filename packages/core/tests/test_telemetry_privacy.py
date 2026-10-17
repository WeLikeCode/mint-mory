"""Telemetry carries no content: the sentinel walk over a real search, dream and failure.

Spec: observability › Telemetry carries no content.

A memory holding ``SENTINEL-CONTENT-7f3a`` is added, a search for ``SENTINEL-QUERY-91c2`` runs
and a light dream runs; a search whose ``_fts_scores`` raises a sentinel-carrying
``RuntimeError`` propagates. No exported span name, span or event attribute, status description
or metric attribute may contain a sentinel — the runtime's scrubber already drops exception
messages, and no span carries memory or query text. Each test also asserts the telemetry this
unit added (the ``mintmory.search.*`` phase span and the ``mintmory.search.latency_ms`` point)
really exists, so a no-op telemetry shim cannot make the privacy check pass vacuously.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.llm import build_dreaming_engine
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import SearchRequest

pytest.importorskip("opentelemetry.sdk")

_LATENCY = "mintmory.search.latency_ms"


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


def _points(reader: Any, name: str) -> list[Any]:
    data = reader.get_metrics_data()
    if data is None:
        return []
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == name:
                    return list(metric.data.data_points)
    return []


def _all_text(exporter: Any, reader: Any) -> str:
    """Every span name, span/event attribute, status description and metric attribute value."""
    lines: list[str] = []
    for span in exporter.get_finished_spans():
        lines.append(span.name)
        for key, value in dict(span.attributes or {}).items():
            lines.append(f"{key}={value}")
        for event in span.events:
            lines.append(event.name)
            for key, value in dict(event.attributes or {}).items():
                lines.append(f"{key}={value}")
        status = span.status
        if status is not None:
            lines.append(str(status.description or ""))
    for point in _points(reader, _LATENCY):
        for key, value in dict(point.attributes).items():
            lines.append(f"{key}={value}")
    return "\n".join(lines)


def _assert_no_sentinel(exporter: Any, reader: Any, sentinels: Sequence[str]) -> None:
    """Telemetry really recorded something, and no field anywhere carries a sentinel."""
    assert exporter.get_finished_spans(), "no spans were exported"
    blob = _all_text(exporter, reader)
    for sentinel in sentinels:
        assert sentinel not in blob, f"telemetry leaked {sentinel!r}"


@pytest.mark.l4("C-28481766")
def test_no_content_leaks_into_telemetry() -> None:
    """A memory, a query and a light dream leave no sentinel anywhere in the exported data."""
    store = StorageAdapter(":memory:")
    store.initialise()
    try:
        exporter = _in_memory_span_exporter()
        reader = _in_memory_metric_reader()
        assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True

        store.add_memory(content="a memory holding SENTINEL-CONTENT-7f3a", category="fact")
        store.search(SearchRequest(query="SENTINEL-QUERY-91c2"))
        build_dreaming_engine(store).run_light()

        names = {span.name for span in exporter.get_finished_spans()}
        assert "mintmory.add_memory" in names, sorted(names)
        assert "mintmory.search" in names, sorted(names)
        assert "mintmory.dream.light" in names, sorted(names)
        assert "mintmory.search.fts" in names, sorted(names)
        assert _points(reader, _LATENCY), "the search latency histogram is empty"

        _assert_no_sentinel(exporter, reader, ("SENTINEL-CONTENT-7f3a", "SENTINEL-QUERY-91c2"))
    finally:
        store.close()


@pytest.mark.l4("C-72a88eb9")
def test_a_failure_does_not_leak_its_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sentinel-carrying search failure keeps the type only; no field carries the message."""
    from opentelemetry.trace import StatusCode

    store = StorageAdapter(":memory:")
    store.initialise()
    try:
        exporter = _in_memory_span_exporter()
        reader = _in_memory_metric_reader()
        assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True
        store.add_memory(content="a memory", category="fact")

        def _boom(query: str, limit: int) -> dict[str, float]:
            raise RuntimeError("no such column: SENTINEL-QUERY-91c2")

        monkeypatch.setattr(store, "_fts_scores", _boom)

        with pytest.raises(RuntimeError, match="SENTINEL-QUERY-91c2"):
            store.search(SearchRequest(query="anything"))

        spans = {span.name: span for span in exporter.get_finished_spans()}
        fts = spans.get("mintmory.search.fts")
        assert fts is not None, sorted(spans)
        assert fts.status.status_code == StatusCode.ERROR
        assert dict(fts.attributes or {}).get("error.type") == "RuntimeError"
        assert _points(reader, _LATENCY), "the failing stage still records its latency point"

        _assert_no_sentinel(exporter, reader, ("SENTINEL-QUERY-91c2",))
    finally:
        store.close()
