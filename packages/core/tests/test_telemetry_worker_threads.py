"""Worker threads keep the trace (task 5.1).

Spec: observability › Worker threads keep the trace.

``backfill``/``sync`` fan session preparation out to a ``ThreadPoolExecutor`` and the
dreaming engine fans its summary calls out to another. A thread-pool worker starts with an
empty context, so without ``run_in_context`` every span opened there begins a fresh trace.
This is the integration counterpart of the ``run_in_context`` unit test: the fake
distiller's and summarizer's spans must land in the caller's trace (``root-a`` / ``root-b``),
and the backfill/sync reports must still be error-free.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.config import SummarySettings
from mintmory.core.dreaming import DreamingEngine
from mintmory.core.history.ingest import backfill, sync
from mintmory.core.history.models import NormalizedTurn, SessionSummary
from mintmory.core.storage import StorageAdapter

pytest.importorskip("opentelemetry.sdk")


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default providers, tolerating repeated inits."""
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


def _in_memory_exporter() -> Any:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    return InMemorySpanExporter()


def _trace_id(span: Any) -> str:
    return format(span.context.trace_id, "032x")


def _sessions() -> list[tuple[SessionSummary, list[NormalizedTurn]]]:
    """Four short sessions (one segment each), like the stub adapter of the ingest suite."""
    sessions: list[tuple[SessionSummary, list[NormalizedTurn]]] = []
    for index in range(4):
        summary = SessionSummary(
            session_id=f"worker-{index}",
            agent="claude_code",
            repo="myproject",
            repo_path="/home/user/myproject",
            branch="main",
            ts_start=f"2025-03-0{index + 1}T10:00:00Z",
            ts_end=f"2025-03-0{index + 1}T10:30:00Z",
            turn_count=2,
            tools_used=["bash"],
            kind="investigation",
            title="",
            summary_text="",
            source_path="",
            distiller_version=1,
        )
        turns = [
            NormalizedTurn(seq=0, ts="2025-03-01T10:00:00Z", role="user", text=f"task {index}"),
            NormalizedTurn(seq=1, ts="2025-03-01T10:01:00Z", role="assistant", text="done"),
        ]
        sessions.append((summary, turns))
    return sessions


@pytest.mark.l4("C-711e3d68")
def test_worker_threads_keep_the_caller_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backfill, sync and the dream summaries all stay in the caller's trace."""
    import mintmory.core.history.ingest as ingest_mod

    exporter = _in_memory_exporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True

    def _iter_sessions() -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
        yield from _sessions()

    monkeypatch.setattr(
        ingest_mod,
        "_load_adapter",
        lambda name: _iter_sessions if name == "stub" else None,
    )

    def _fake_distiller(
        seg_sum: SessionSummary,
        seg_turns: list[NormalizedTurn],
        prev_context: str = "",
    ) -> tuple[SessionSummary, str]:
        with telemetry.span("fake.distill"):
            pass
        return dataclasses.replace(seg_sum, summary_text="distilled", distiller_version=2), ""

    with telemetry.span("root-a") as root_a:
        root_a_trace = _trace_id(root_a)
        backfill_report = backfill(
            db_path=str(tmp_path / "backfill.db"),
            sources=["stub"],
            distiller=_fake_distiller,
            max_concurrency=4,
        )
        sync_report = sync(
            db_path=str(tmp_path / "sync.db"),
            sources=["stub"],
            distiller=_fake_distiller,
            max_concurrency=4,
        )

    store = StorageAdapter(":memory:", embedder=None)
    store.initialise()
    for content in (
        'a note about "alpha-x"',
        'another "alpha-x" note',
        'a note about "beta-y"',
        'another "beta-y" note',
    ):
        store.add_memory(content=content, category="fact")

    def _fake_summarizer(concept: str, contents: list[str]) -> str:
        with telemetry.span("fake.summarize"):
            pass
        return f"summary of {concept} with {len(contents)} memories"

    with telemetry.span("root-b") as root_b:
        root_b_trace = _trace_id(root_b)
        engine = DreamingEngine(
            store,
            summarizer=_fake_summarizer,
            summary_settings=SummarySettings(concurrency=2, min_memories=2),
        )
        engine.run_full()

    assert backfill_report.errors == 0
    assert sync_report.errors == 0

    spans = exporter.get_finished_spans()
    distill_ids = {_trace_id(span) for span in spans if span.name == "fake.distill"}
    summarize_ids = {_trace_id(span) for span in spans if span.name == "fake.summarize"}
    assert len(distill_ids) >= 1
    assert distill_ids == {root_a_trace}
    assert len(summarize_ids) >= 1
    assert summarize_ids == {root_b_trace}
