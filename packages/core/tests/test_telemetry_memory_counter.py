"""``add_memory`` records ``mintmory.memories.added`` through the shared decorator (task 5.3).

Spec: observability › Memory counters. Both storage backends' ``add_memory`` carry
``telemetry.counts_added``, so every insert records the counter with its ``category``. The
helper's own on/off behaviour is pinned in ``test_telemetry_set_attributes_counter.py`` (task
1.5); this file checks it is wired onto the real store and onto ``PostgresBackend``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.storage import StorageAdapter

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


@pytest.fixture()
def store() -> Iterator[StorageAdapter]:
    """A fresh in-memory SQLite store (no embedder, so inserts stay cheap)."""
    adapter = StorageAdapter(":memory:")
    adapter.initialise()
    yield adapter
    adapter.close()


def _in_memory_metric_reader() -> Any:
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    return InMemoryMetricReader()


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


@pytest.mark.l4("C-910cf3ca")
def test_sqlite_add_memory_counts_each_category(store: StorageAdapter) -> None:
    """Two ``fact`` inserts and one ``skill`` insert record the counter by category."""
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(metric_reader=reader) is True

    facts = [
        store.add_memory(content="the sky is blue", category="fact"),
        store.add_memory(content="water boils at 100 celsius", category="fact"),
    ]
    skill = store.add_memory(content="how to tie a bowline knot", category="skill")

    assert [record.category.value for record in facts] == ["fact", "fact"]
    assert skill.category.value == "skill"

    assert _counter_values(reader, "mintmory.memories.added") == {"fact": 2, "skill": 1}


@pytest.mark.l4("C-910cf3ca")
def test_both_backends_add_memory_carry_the_shared_decorator() -> None:
    """``counts_added`` marks both ``add_memory`` methods, as the helper's marker shows."""
    from mintmory.core.storage import SqliteBackend
    from mintmory.core.storage_postgres import PostgresBackend

    for backend in (SqliteBackend, PostgresBackend):
        marker = getattr(backend.add_memory, "__mintmory_counter__", None)
        assert marker == "mintmory.memories.added", backend.__name__
