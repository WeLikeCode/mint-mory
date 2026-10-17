"""Search phase spans and latency on the real search entry points (task 2.1).

Spec: observability › Search phase spans and latency, and observability › Span helpers
without work or with a failure.

Both storage backends run their ``search`` through the shared ``collect_scores`` path, which
opens ``mintmory.search.fts``/``.substring``/``.vector``/``.fusion`` child spans under
``mintmory.search`` and records the ``mintmory.search.latency_ms`` histogram by ``phase``
(``fts``, ``substring``, ``vector``, ``fusion``, ``graph``, ``total``). A stage with nothing to
do still records its span with ``mintmory.result_count=0``; a failing stage is marked with
``mark_error`` and re-raised, its point recorded; a metric failure never escapes. Note
anchoring uses the same score methods but must not count as search.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    LinkSource,
    MemoryCategory,
    MemoryRecord,
    SearchAroundSpec,
    SearchRequest,
)

pytest.importorskip("opentelemetry.sdk")

_LATENCY = "mintmory.search.latency_ms"
_PHASE_SPANS = ("fts", "substring", "vector", "fusion")


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


@pytest.fixture()
def store() -> Iterator[StorageAdapter]:
    """A fresh in-memory SQLite store (no embedder, so the vector stage is empty)."""
    adapter = StorageAdapter(":memory:")
    adapter.initialise()
    yield adapter
    adapter.close()


def _in_memory_span_exporter() -> Any:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    return InMemorySpanExporter()


def _in_memory_metric_reader() -> Any:
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    return InMemoryMetricReader()


def _finished_by_name(exporter: Any) -> dict[str, Any]:
    return {span.name: span for span in exporter.get_finished_spans()}


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


def _phases(reader: Any) -> list[str]:
    return [str(dict(point.attributes).get("phase")) for point in _points(reader, _LATENCY)]


def _add(store: StorageAdapter, content: str) -> str:
    return store.add_memory(content=content, category="fact").id


def _assert_phase_children(exporter: Any, reader: Any) -> None:
    """The four phase spans hang off ``mintmory.search`` and all five latency points exist."""
    spans = _finished_by_name(exporter)
    search_span = spans.get("mintmory.search")
    assert search_span is not None, sorted(spans)
    for phase in _PHASE_SPANS:
        name = f"mintmory.search.{phase}"
        assert name in spans, sorted(spans)
        parent = spans[name].parent
        assert parent is not None, name
        assert parent.span_id == search_span.context.span_id, phase
    assert set(_phases(reader)) == {"fts", "substring", "vector", "fusion", "total"}


@pytest.mark.l4("C-f4b27f0d")
def test_search_records_the_four_phase_spans_and_latency(store: StorageAdapter) -> None:
    """A real search records the four child phase spans and the five latency points."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True
    _add(store, "parking garage integration notes")
    _add(store, "coffee machine is broken in the kitchen")
    _add(store, "parking permit renewal reminder")

    response = store.search(SearchRequest(query="parking garage"))

    assert response.total_found >= 1
    _assert_phase_children(exporter, reader)


@pytest.mark.l4("C-43d72c8b")
def test_search_around_alone_records_only_its_graph_point(store: StorageAdapter) -> None:
    """``search_around`` runs no score stage: only the ``graph`` point, no phase span."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True
    anchor = _add(store, "anchor node")
    neighbour = _add(store, "neighbour node")
    store.add_link(
        ConceptLink(
            source_memory_id=anchor,
            target_memory_id=neighbour,
            link_type=ConceptLinkType.RELATES_TO,
            strength=0.8,
            source=LinkSource.USER,
        )
    )

    result = store.search_around([anchor], SearchAroundSpec(depth=1))

    assert neighbour in result
    assert _phases(reader) == ["graph"]
    names = set(_finished_by_name(exporter))
    for phase in _PHASE_SPANS:
        assert f"mintmory.search.{phase}" not in names, sorted(names)


@pytest.mark.l4("C-c91ee0e7")
def test_postgres_search_uses_the_shared_phase_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pool-less ``PostgresBackend`` with patched data access still records the phases."""
    from mintmory.core.storage_postgres import PostgresBackend

    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True
    backend = PostgresBackend(dsn="postgresql://localhost:5432/mintmory")
    memory = MemoryRecord(id="mem-1", content="parking garage", category=MemoryCategory.FACT)

    monkeypatch.setattr(backend, "_fts_scores", lambda query, limit: {memory.id: 1.0})
    monkeypatch.setattr(backend, "_trigram_scores", lambda query, limit: {})
    monkeypatch.setattr(backend, "_vector_scores", lambda query, embedding, limit: {})
    monkeypatch.setattr(backend, "_load_memories", lambda ids: [memory] if ids else [])
    monkeypatch.setattr(backend, "_bump_retrieval", lambda ids, now: None)
    monkeypatch.setattr(backend, "create_session", lambda session: session)
    monkeypatch.setattr(backend, "record_query_results", lambda results: None)
    monkeypatch.setattr(backend, "get_annotating_notes", lambda memory_id, cap: [])
    monkeypatch.setattr(backend, "search_around", lambda anchor_ids, spec: [])

    response = backend.search(SearchRequest(query="parking garage"))

    assert response.total_found == 1
    _assert_phase_children(exporter, reader)


@pytest.mark.l4("C-c986421b")
def test_stage_with_nothing_to_do_records_a_zero_count(store: StorageAdapter) -> None:
    """With no embedder the vector stage is empty, but its span still carries count 0."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True
    _add(store, "database indexing strategies")

    store.search(SearchRequest(query="database indexing"))

    spans = _finished_by_name(exporter)
    assert "mintmory.search.vector" in spans, sorted(spans)
    attributes = dict(spans["mintmory.search.vector"].attributes or {})
    assert attributes["mintmory.result_count"] == 0
    assert "vector" in _phases(reader)


@pytest.mark.l4("C-20646f63")
def test_failing_stage_is_marked_and_still_timed(
    store: StorageAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same exception propagates; the fts span is ERROR with ``error.type`` and a point."""
    from opentelemetry.trace import StatusCode

    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True
    _add(store, "a memory")

    def _boom(query: str, limit: int) -> dict[str, float]:
        raise RuntimeError("no such column: SENTINEL-QUERY-91c2")

    monkeypatch.setattr(store, "_fts_scores", _boom)

    with pytest.raises(RuntimeError, match="SENTINEL-QUERY-91c2"):
        store.search(SearchRequest(query="anything"))

    spans = _finished_by_name(exporter)
    assert "mintmory.search.fts" in spans, sorted(spans)
    failed = spans["mintmory.search.fts"]
    assert failed.status.status_code == StatusCode.ERROR
    assert dict(failed.attributes or {})["error.type"] == "RuntimeError"
    assert "fts" in _phases(reader)


@pytest.mark.l4("C-0d312d3f")
def test_a_metric_failure_stays_inside_telemetry(
    store: StorageAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raising ``record_value`` never escapes an embedder call or a search."""
    from mintmory.core.embedder import HashingEmbedder

    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True
    _add(store, "a memory about metrics")

    def _broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("metric-boom")

    monkeypatch.setattr(telemetry, "record_value", _broken)

    vector = HashingEmbedder().embed("a")
    assert vector.shape == (512,)

    response = store.search(SearchRequest(query="metrics"))

    assert response.total_found >= 1
    spans = _finished_by_name(exporter)
    assert "mintmory.search.fts" in spans, sorted(spans)
    attributes = dict(spans["mintmory.search.fts"].attributes or {})
    assert attributes["mintmory.result_count"] >= 1


@pytest.mark.l4("C-f4b27f0d")
def test_note_anchoring_records_no_search_phase(store: StorageAdapter) -> None:
    """A note anchored to a memory reuses the score methods without recording a phase."""
    from mintmory.core.notes import create_note

    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True
    _add(store, "parking garage gate opens at eight")

    store.search(SearchRequest(query="parking garage"))
    assert "mintmory.search.fts" in _finished_by_name(exporter)

    exporter.clear()
    create_note(store, "remember the parking garage gate code", about="parking garage gate")

    names = set(_finished_by_name(exporter))
    for phase in _PHASE_SPANS:
        assert f"mintmory.search.{phase}" not in names, sorted(names)
