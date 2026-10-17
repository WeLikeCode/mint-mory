"""``set_attributes`` and the ``counts_added`` decorator (task 1.5).

Spec: observability › Memory counters, and the current-span attribute helper the CLI's
``index-tree`` count uses (observability › CLI commands are traced end to end).

``set_attributes(**attrs)`` writes its attributes on the span that is current when it is
called (the command span ``index-tree`` reports its ``mintmory.files.*`` counts on).
``counts_added(fn)`` wraps a function returning a memory record: after each call it records
``mintmory.memories.added`` with ``category=record.category.value`` and marks the wrapper
with ``__mintmory_counter__ = "mintmory.memories.added"`` so both backends' ``add_memory``
can be checked for the shared decorator. Both helpers are no-ops when telemetry is off.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
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


def _counter_values(reader: Any, name: str) -> dict[str, int]:
    """Each data point's ``category`` attribute mapped to the counter's aggregate value."""
    data = reader.get_metrics_data()
    assert data is not None, "no metrics were exported"
    values: dict[str, int] = {}
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name != name:
                    continue
                for point in metric.data.data_points:
                    category = dict(point.attributes).get("category")
                    values[str(category)] = int(point.value)
    return values


class _Category:
    def __init__(self, value: str) -> None:
        self.value = value


class _Record:
    def __init__(self, category: str) -> None:
        self.category = _Category(category)


def _make_add() -> Callable[[str], _Record]:
    """A stand-in for ``add_memory``: takes a category and returns a memory record."""

    def add(category: str) -> _Record:
        return _Record(category)

    return add


@pytest.mark.l4("C-e9540797")
def test_set_attributes_writes_on_the_current_span() -> None:
    """The attributes land on the active span, not on the no-op shim."""
    exporter = _in_memory_span_exporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True

    with telemetry.span("mintmory.cli.index-tree"):
        telemetry.set_attributes(**{"mintmory.files.scanned": 2, "mintmory.files.added": 2})

    span = _finished_by_name(exporter).get("mintmory.cli.index-tree")
    assert span is not None, "the command span was not exported"
    attributes = dict(span.attributes or {})
    assert attributes.get("mintmory.files.scanned") == 2
    assert attributes.get("mintmory.files.added") == 2


@pytest.mark.l4("C-910cf3ca")
def test_counts_added_records_each_category_and_marks_the_wrapper() -> None:
    """Two ``fact`` records and one ``skill`` record are counted per category."""
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(metric_reader=reader) is True

    wrapped = telemetry.counts_added(_make_add())
    assert wrapped is not None, "counts_added must return the wrapped callable"
    assert getattr(wrapped, "__mintmory_counter__", None) == "mintmory.memories.added"

    for _ in range(2):
        record = wrapped("fact")
        assert record is not None
        assert record.category.value == "fact"
    record = wrapped("skill")
    assert record is not None
    assert record.category.value == "skill"

    values = _counter_values(reader, "mintmory.memories.added")
    assert values == {"fact": 2, "skill": 1}


@pytest.mark.l4("C-910cf3ca")
def test_counts_added_works_with_telemetry_off() -> None:
    """The marker is set and the record still flows through when telemetry is disabled."""
    assert telemetry.is_enabled() is False

    wrapped = telemetry.counts_added(_make_add())
    assert wrapped is not None, "counts_added must return the wrapped callable"
    assert getattr(wrapped, "__mintmory_counter__", None) == "mintmory.memories.added"

    record = wrapped("fact")
    assert record is not None
    assert record.category.value == "fact"
