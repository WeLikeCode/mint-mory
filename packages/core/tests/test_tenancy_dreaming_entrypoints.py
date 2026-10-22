"""RED tests for task 2 — per-tenant dreaming entry points (requirement 2).

They trace requirement 2.1 (the ``dreaming.py`` entry-point surface), 2.2
(``dream_all_tenants`` iterates active tenants and records failures), 2.3
(``DreamAllReport.total``), 2.4 (``DreamFailedError``), 2.5 (``run_dream``),
2.6 (one-tenant parity with the legacy engine) and 2.7 (multi-tenant iteration,
``skipped_inactive`` and failures).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from mintmory.core import dreaming
from mintmory.core.dreaming import DreamingEngine
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    AnomalyReport,
    DreamIntensity,
    DreamReport,
    MemoryCategory,
    MemoryRecord,
    TenantInactiveError,
    TenantNotFoundError,
)
from pydantic import BaseModel


def _summarizer(concept: str, contents: list[str]) -> str:
    return f"{concept}:{len(contents)}"


def _store(path: Path) -> SqliteBackend:
    store = SqliteBackend(path)
    store.initialise()
    return store


def _memory(
    store: SqliteBackend,
    content: str,
    tenant_id: str = "global",
    **fields: Any,
) -> MemoryRecord:
    return store.add_memory(
        MemoryRecord(
            content=content,
            category=MemoryCategory.FACT,
            tenant_id=tenant_id,
            **fields,
        )
    )


class _FakeEngine(DreamingEngine):
    """A ``DreamingEngine`` whose steps return fixed reports (or fail)."""

    def __init__(self, adapter: SqliteBackend, tenant_id: str, *, fail: bool = False) -> None:
        super().__init__(adapter, tenant_id=tenant_id)
        self.fail = fail
        self.light_calls = 0
        self.full_calls = 0

    def _maybe_fail(self) -> None:
        if self.fail:
            self.adapter.add_memory(
                MemoryRecord(
                    id=f"before-{self.tenant_id}",
                    content=f"{self.tenant_id} partial write",
                    category=MemoryCategory.FACT,
                    tenant_id=self._wt(),
                )
            )
            raise RuntimeError("boom")

    def run_light(self) -> DreamReport:
        self.light_calls += 1
        self._maybe_fail()
        return DreamReport(intensity=DreamIntensity.LIGHT, duration_ms=1.0, new_links=1)

    def run_full(self) -> DreamReport:
        self.full_calls += 1
        self._maybe_fail()
        return DreamReport(
            intensity=DreamIntensity.FULL,
            duration_ms=1.0,
            new_links=2,
            new_summaries=1,
            contradictions_resolved=3,
            memories_archived=4,
            memories_rehabilitated=5,
        )


def _factory(engines: dict[str, _FakeEngine]) -> Callable[[str], DreamingEngine]:
    def build(tenant_id: str) -> DreamingEngine:
        return engines[tenant_id]

    return build


_P_IDS = ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]


def _seed_parity_db(path: Path) -> SqliteBackend:
    """R2.6 seed: p1..p3 acme memories, p4/p5 a note conflict, p6/p7 states."""
    store = _store(path)
    now = datetime.utcnow()
    _memory(store, "Alice works at Acme", id="p1")
    _memory(store, "Bob works at Acme", id="p2")
    _memory(store, "Carol works at Acme", id="p3")
    _memory(
        store,
        "Acme is closed on Fridays",
        id="p4",
        is_note=True,
        flagged_for_review=True,
        contradicts_ids=["p5"],
    )
    _memory(store, "Acme opens on Fridays", id="p5")
    _memory(
        store,
        "Old memo",
        id="p6",
        is_stale=True,
        staleness_score=9.5,
        last_accessed_at=None,
    )
    _memory(
        store,
        "Useful tip",
        id="p7",
        is_stale=True,
        usefulness_score=6.0,
        staleness_score=4.0,
        last_accessed_at=now - timedelta(days=1),
    )
    return store


def _link_snapshot(store: SqliteBackend) -> set[tuple[str, str, str, float]]:
    rows = (
        store.connect()
        .execute(
            "SELECT source_memory_id, target_memory_id, link_type, strength FROM concept_links"
        )
        .fetchall()
    )
    return {
        (row["source_memory_id"], row["target_memory_id"], row["link_type"], row["strength"])
        for row in rows
    }


def _summary_snapshot(store: SqliteBackend) -> set[tuple[str, str, int]]:
    rows = (
        store.connect()
        .execute("SELECT concept, summary_text, memory_count FROM memory_summaries")
        .fetchall()
    )
    return {(row["concept"], row["summary_text"], row["memory_count"]) for row in rows}


def _state_snapshot(
    store: SqliteBackend, memory_ids: list[str]
) -> dict[str, tuple[bool, bool, bool, float, bool, str | None]]:
    snapshot: dict[str, tuple[bool, bool, bool, float, bool, str | None]] = {}
    for memory_id in memory_ids:
        record = store.get_memory(memory_id)
        assert record is not None
        snapshot[memory_id] = (
            record.is_active,
            record.is_archived,
            record.is_stale,
            record.staleness_score,
            record.flagged_for_review,
            record.superseded_by,
        )
    return snapshot


# ---------------------------------------------------------------------------
# Requirement 2.1 — the entry-point surface
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-443639c5")
def test_dreaming_module_defines_the_per_tenant_entry_point_surface() -> None:
    for name in (
        "EngineFactory",
        "DreamAllReport",
        "DreamFailedError",
        "dream_all_tenants",
        "run_dream",
    ):
        assert hasattr(dreaming, name), f"mintmory.core.dreaming does not define {name}"

    report_cls = getattr(dreaming, "DreamAllReport", None)
    assert isinstance(report_cls, type)
    assert issubclass(report_cls, BaseModel)
    error_cls = getattr(dreaming, "DreamFailedError", None)
    assert isinstance(error_cls, type)
    assert issubclass(error_cls, RuntimeError)
    assert callable(getattr(dreaming, "dream_all_tenants", None))
    assert callable(getattr(dreaming, "run_dream", None))


# ---------------------------------------------------------------------------
# Requirement 2.3 — DreamAllReport.total()
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-6d7b9d0d")
def test_total_sums_metrics_and_concatenates_anomalies_in_tenant_order() -> None:
    report_cls = getattr(dreaming, "DreamAllReport", None)
    if report_cls is None:
        pytest.fail("DreamAllReport is not defined in mintmory.core.dreaming")

    per_tenant = {
        "t2": DreamReport(
            intensity=DreamIntensity.FULL,
            duration_ms=2.5,
            new_links=2,
            new_summaries=1,
            contradictions_resolved=4,
            memories_archived=6,
            memories_rehabilitated=8,
            anomalies=AnomalyReport(
                high_staleness_useful=["t2-h"],
                never_accessed=["t2-n"],
                contradictions=["t2-c"],
            ),
        ),
        "t1": DreamReport(
            intensity=DreamIntensity.FULL,
            duration_ms=1.5,
            new_links=3,
            new_summaries=5,
            contradictions_resolved=7,
            memories_archived=9,
            memories_rehabilitated=11,
            anomalies=AnomalyReport(
                high_staleness_useful=["t1-h"],
                never_accessed=["t1-n"],
                contradictions=["t1-c"],
            ),
        ),
    }
    report = report_cls(
        intensity=DreamIntensity.FULL,
        per_tenant=per_tenant,
        skipped_inactive=["t9"],
        failed={"t8": "RuntimeError: boom"},
    )

    total = report.total()

    assert isinstance(total, DreamReport)
    assert total.intensity == DreamIntensity.FULL
    assert total.duration_ms == pytest.approx(4.0)
    assert total.new_links == 5
    assert total.new_summaries == 6
    assert total.contradictions_resolved == 11
    assert total.memories_archived == 15
    assert total.memories_rehabilitated == 19
    assert total.anomalies is not None
    assert total.anomalies.high_staleness_useful == ["t1-h", "t2-h"]
    assert total.anomalies.never_accessed == ["t1-n", "t2-n"]
    assert total.anomalies.contradictions == ["t1-c", "t2-c"]

    empty = report_cls(intensity=DreamIntensity.LIGHT, per_tenant={}).total()
    assert isinstance(empty, DreamReport)
    assert empty.intensity == DreamIntensity.LIGHT
    assert empty.duration_ms == 0.0
    assert empty.new_links == 0
    assert empty.new_summaries == 0
    assert empty.contradictions_resolved == 0
    assert empty.memories_archived == 0
    assert empty.memories_rehabilitated == 0
    assert empty.anomalies == AnomalyReport()


# ---------------------------------------------------------------------------
# Requirement 2.4 — DreamFailedError
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-bb56329e")
def test_dream_failed_error_message_sorts_tenants_and_keeps_failed() -> None:
    error_cls = getattr(dreaming, "DreamFailedError", None)
    if error_cls is None:
        pytest.fail("DreamFailedError is not defined in mintmory.core.dreaming")

    failed = {"t2": "ValueError: bad", "t1": "RuntimeError: boom"}
    error = error_cls(failed)

    assert isinstance(error, RuntimeError)
    assert (
        str(error) == "dreaming failed for tenant(s): t1 (RuntimeError: boom), t2 (ValueError: bad)"
    )
    assert getattr(error, "failed", None) == failed


# ---------------------------------------------------------------------------
# Requirement 2.2 / 2.7 — dream_all_tenants
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-61979b79", "C-dc6f014f")
def test_dream_all_tenants_runs_active_tenants_with_their_intensity(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    store.create_tenant("t2")
    store.set_tenant_active("t2", False)
    dream_all = getattr(dreaming, "dream_all_tenants", None)
    if dream_all is None:
        pytest.fail("dream_all_tenants is not defined in mintmory.core.dreaming")

    engines = {name: _FakeEngine(store, name) for name in ("global", "t1")}
    seen: list[str] = []

    def factory(tenant_id: str) -> DreamingEngine:
        seen.append(tenant_id)
        return engines[tenant_id]

    report = dream_all(store, intensity=DreamIntensity.FULL, engine_factory=factory)

    report_cls = getattr(dreaming, "DreamAllReport", None)
    assert isinstance(report_cls, type)
    assert isinstance(report, report_cls)
    checked = cast("Any", report)
    assert list(checked.per_tenant) == ["global", "t1"]
    assert checked.skipped_inactive == ["t2"]
    assert checked.failed == {}
    assert seen == ["global", "t1"]
    assert engines["global"].full_calls == 1
    assert engines["t1"].full_calls == 1
    assert engines["global"].light_calls == 0
    assert engines["t1"].light_calls == 0

    light_engines = {name: _FakeEngine(store, name) for name in ("global", "t1")}
    light_report = dream_all(
        store,
        intensity=DreamIntensity.LIGHT,
        engine_factory=_factory(light_engines),
    )
    assert list(light_report.per_tenant) == ["global", "t1"]
    assert light_engines["global"].light_calls == 1
    assert light_engines["t1"].light_calls == 1
    assert light_engines["global"].full_calls == 0
    assert light_engines["t1"].full_calls == 0


@pytest.mark.l4("C-61979b79")
def test_dream_all_tenants_records_a_run_failure_and_continues(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    dream_all = getattr(dreaming, "dream_all_tenants", None)
    if dream_all is None:
        pytest.fail("dream_all_tenants is not defined in mintmory.core.dreaming")

    engines = {
        "global": _FakeEngine(store, "global"),
        "t1": _FakeEngine(store, "t1", fail=True),
    }

    report = dream_all(
        store,
        intensity=DreamIntensity.LIGHT,
        engine_factory=_factory(engines),
    )

    assert list(report.per_tenant) == ["global"]
    assert report.skipped_inactive == []
    assert report.failed == {"t1": "RuntimeError: boom"}
    assert engines["t1"].light_calls == 1
    assert engines["global"].light_calls == 1

    partial = store.get_memory("before-t1", tenant_id="t1")
    assert partial is not None
    assert partial.content == "t1 partial write"


@pytest.mark.l4("C-dc6f014f")
def test_dream_all_tenants_records_a_factory_failure_and_run_dream_raises(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    store.create_tenant("t2")
    store.set_tenant_active("t2", False)
    dream_all = getattr(dreaming, "dream_all_tenants", None)
    if dream_all is None:
        pytest.fail("dream_all_tenants is not defined in mintmory.core.dreaming")

    global_engine = _FakeEngine(store, "global")

    def factory(tenant_id: str) -> DreamingEngine:
        if tenant_id == "t1":
            raise RuntimeError("boom")
        return global_engine

    report = dream_all(store, intensity=DreamIntensity.LIGHT, engine_factory=factory)

    assert list(report.per_tenant) == ["global"]
    assert report.skipped_inactive == ["t2"]
    assert report.failed == {"t1": "RuntimeError: boom"}
    assert global_engine.light_calls == 1

    run_dream = getattr(dreaming, "run_dream", None)
    if run_dream is None:
        pytest.fail("run_dream is not defined in mintmory.core.dreaming")
    error_cls = dreaming.DreamFailedError
    with pytest.raises(error_cls) as exc_info:
        run_dream(
            store,
            intensity=DreamIntensity.LIGHT,
            tenant_id=None,
            engine_factory=factory,
        )
    assert getattr(exc_info.value, "failed", None) == {"t1": "RuntimeError: boom"}
    assert str(exc_info.value) == "dreaming failed for tenant(s): t1 (RuntimeError: boom)"


# ---------------------------------------------------------------------------
# Requirement 2.5 — run_dream
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-ac42fe75")
def test_run_dream_concrete_tenant_validates_before_running(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    store.create_tenant("t2")
    store.set_tenant_active("t2", False)
    run_dream = getattr(dreaming, "run_dream", None)
    if run_dream is None:
        pytest.fail("run_dream is not defined in mintmory.core.dreaming")

    engines = {"t1": _FakeEngine(store, "t1")}
    seen: list[str] = []

    def factory(tenant_id: str) -> DreamingEngine:
        seen.append(tenant_id)
        return engines[tenant_id]

    with pytest.raises(TenantNotFoundError):
        run_dream(
            store,
            intensity=DreamIntensity.LIGHT,
            tenant_id="unknown",
            engine_factory=factory,
        )
    assert seen == []

    with pytest.raises(TenantInactiveError):
        run_dream(
            store,
            intensity=DreamIntensity.LIGHT,
            tenant_id="t2",
            engine_factory=factory,
        )
    assert seen == []

    report = run_dream(
        store,
        intensity=DreamIntensity.FULL,
        tenant_id="t1",
        engine_factory=factory,
    )
    assert isinstance(report, DreamReport)
    assert report.intensity == DreamIntensity.FULL
    assert report.new_links == 2
    assert report.new_summaries == 1
    assert seen == ["t1"]


@pytest.mark.l4("C-ac42fe75")
def test_run_dream_without_a_tenant_returns_the_total(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    run_dream = getattr(dreaming, "run_dream", None)
    if run_dream is None:
        pytest.fail("run_dream is not defined in mintmory.core.dreaming")

    engines = {name: _FakeEngine(store, name) for name in ("global", "t1")}
    report = run_dream(
        store,
        intensity=DreamIntensity.LIGHT,
        tenant_id=None,
        engine_factory=_factory(engines),
    )

    assert isinstance(report, DreamReport)
    assert report.intensity == DreamIntensity.LIGHT
    assert report.new_links == 2
    assert report.duration_ms == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Requirement 2.6 — one-tenant parity with the legacy engine
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-d95fbef7")
def test_one_tenant_run_dream_parity_with_the_legacy_engine(tmp_path: Path) -> None:
    legacy = _seed_parity_db(tmp_path / "legacy.db")
    tenant = _seed_parity_db(tmp_path / "tenant.db")

    legacy_report = DreamingEngine(legacy, summarizer=_summarizer).run_full()

    run_dream = getattr(dreaming, "run_dream", None)
    if run_dream is None:
        pytest.fail("run_dream is not defined in mintmory.core.dreaming")
    tenant_report = run_dream(
        tenant,
        intensity=DreamIntensity.FULL,
        tenant_id=None,
        engine_factory=lambda name: DreamingEngine(tenant, summarizer=_summarizer, tenant_id=name),
    )

    assert isinstance(tenant_report, DreamReport)
    assert legacy_report.new_links > 0
    assert legacy_report.new_summaries > 0
    assert tenant_report.new_links == legacy_report.new_links
    assert tenant_report.new_summaries == legacy_report.new_summaries
    assert tenant_report.contradictions_resolved == 1
    assert tenant_report.memories_archived == 1
    assert tenant_report.memories_rehabilitated == 1

    assert _link_snapshot(tenant) == _link_snapshot(legacy)
    assert _summary_snapshot(tenant) == _summary_snapshot(legacy)
    assert _state_snapshot(tenant, _P_IDS) == _state_snapshot(legacy, _P_IDS)
    assert tenant_report.model_dump(exclude={"duration_ms"}) == legacy_report.model_dump(
        exclude={"duration_ms"}
    )
