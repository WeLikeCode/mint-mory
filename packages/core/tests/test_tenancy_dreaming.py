"""RED tests for task 1 — the tenant-scoped ``DreamingEngine`` (requirement 1).

They trace requirement 1.1 (``__init__`` stores ``tenant_id``), 1.2 (every step
read and write is confined to the engine's tenant), 1.3 (a foreign
``contradicts_ids`` entry resolves to ``None`` and is skipped), 1.4
(``collect_summary_jobs`` / ``apply_summary`` use the engine's tenant), 1.5
(``tenant_id=None`` keeps today's unscoped engine), 1.6
(``build_dreaming_engine`` / ``build_conflict_resolver`` forward ``tenant_id``),
1.7 (Scenario A: linking and summaries) and 1.8 (Scenario B: cross-tenant
resolution is skipped).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from mintmory.core.config import LinkSettings, LLMProvider, LLMSettings
from mintmory.core.dreaming import DreamingEngine
from mintmory.core.llm import build_conflict_resolver, build_dreaming_engine
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    BatchResolutionAction,
    ConceptLink,
    CrossTenantLinkError,
    DreamReport,
    MemoryCategory,
    MemoryRecord,
    MemorySummary,
    TenantImmutableError,
)


def _summarizer(concept: str, contents: list[str]) -> str:
    return f"{concept}:{len(contents)}"


_READ_METHODS = (
    "list_active_memory_ids",
    "get_memory",
    "get_existing_relates_to_pairs",
    "get_anomaly_high_staleness_useful_ids",
    "get_anomaly_never_accessed_ids",
    "get_anomaly_flagged_ids",
    "get_flagged_memories",
    "get_stale_archivable_ids",
    "get_rehabilitable_rows",
    "get_summary",
)

_WRITE_METHODS = (
    "add_link",
    "upsert_summary",
    "update_memory",
    "archive_memory",
    "supersede_memory",
    "add_memory",
)


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


def _links(store: SqliteBackend) -> list[ConceptLink]:
    rows = store.connect().execute("SELECT * FROM concept_links").fetchall()
    return [store._row_to_link(row) for row in rows]


class _RecordingStore(SqliteBackend):
    """``SqliteBackend`` that records the ``tenant_id`` each engine call passes.

    Only calls whose immediate caller lives in ``mintmory.core.dreaming`` are
    recorded, so storage-internal lookups (for example ``update_memory``'s own
    by-id ``get_memory``) do not pollute the observation.
    """

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self.engine_calls: dict[str, list[str | None]] = defaultdict(list)

    def _record(self, method: str, tenant_id: str | None) -> None:
        if sys._getframe(2).f_globals.get("__name__") == "mintmory.core.dreaming":
            self.engine_calls[method].append(tenant_id)

    def list_active_memory_ids(
        self, *, ordered: bool = False, tenant_id: str | None = None
    ) -> list[str]:
        self._record("list_active_memory_ids", tenant_id)
        return super().list_active_memory_ids(ordered=ordered, tenant_id=tenant_id)

    def get_memory(self, memory_id: str, tenant_id: str | None = None) -> MemoryRecord | None:
        self._record("get_memory", tenant_id)
        return super().get_memory(memory_id, tenant_id)

    def get_existing_relates_to_pairs(self, tenant_id: str | None = None) -> set[frozenset[str]]:
        self._record("get_existing_relates_to_pairs", tenant_id)
        return super().get_existing_relates_to_pairs(tenant_id)

    def get_anomaly_high_staleness_useful_ids(
        self, min_staleness: float, min_usefulness: float, tenant_id: str | None = None
    ) -> list[str]:
        self._record("get_anomaly_high_staleness_useful_ids", tenant_id)
        return super().get_anomaly_high_staleness_useful_ids(
            min_staleness, min_usefulness, tenant_id
        )

    def get_anomaly_never_accessed_ids(
        self, cutoff_iso: str, tenant_id: str | None = None
    ) -> list[str]:
        self._record("get_anomaly_never_accessed_ids", tenant_id)
        return super().get_anomaly_never_accessed_ids(cutoff_iso, tenant_id)

    def get_anomaly_flagged_ids(self, tenant_id: str | None = None) -> list[str]:
        self._record("get_anomaly_flagged_ids", tenant_id)
        return super().get_anomaly_flagged_ids(tenant_id)

    def get_flagged_memories(self, tenant_id: str | None = None) -> list[MemoryRecord]:
        self._record("get_flagged_memories", tenant_id)
        return super().get_flagged_memories(tenant_id)

    def get_stale_archivable_ids(
        self, min_staleness: float, cutoff_iso: str, tenant_id: str | None = None
    ) -> list[str]:
        self._record("get_stale_archivable_ids", tenant_id)
        return super().get_stale_archivable_ids(min_staleness, cutoff_iso, tenant_id)

    def get_rehabilitable_rows(
        self, cutoff_iso: str, tenant_id: str | None = None
    ) -> list[tuple[str, float]]:
        self._record("get_rehabilitable_rows", tenant_id)
        return super().get_rehabilitable_rows(cutoff_iso, tenant_id)

    def get_summary(self, concept: str, tenant_id: str = "global") -> MemorySummary | None:
        self._record("get_summary", tenant_id)
        return super().get_summary(concept, tenant_id)

    def add_link(self, link: ConceptLink) -> ConceptLink:
        self._record("add_link", link.tenant_id)
        return super().add_link(link)

    def upsert_summary(self, summary: MemorySummary) -> MemorySummary:
        self._record("upsert_summary", summary.tenant_id)
        return super().upsert_summary(summary)

    def update_memory(self, memory_id: str, **fields: object) -> MemoryRecord:
        tenant_id = fields.get("tenant_id")
        self._record("update_memory", tenant_id if isinstance(tenant_id, str) else None)
        return super().update_memory(memory_id, **fields)

    def archive_memory(self, memory_id: str, tenant_id: str | None = None) -> None:
        self._record("archive_memory", tenant_id)
        super().archive_memory(memory_id, tenant_id)

    def supersede_memory(self, memory_id: str, by_id: str, tenant_id: str | None = None) -> None:
        self._record("supersede_memory", tenant_id)
        super().supersede_memory(memory_id, by_id, tenant_id)

    def add_memory(self, record: MemoryRecord | None = None, **fields: Any) -> MemoryRecord:
        tenant_id = record.tenant_id if record is not None else fields.get("tenant_id")
        self._record("add_memory", tenant_id if isinstance(tenant_id, str) else None)
        return super().add_memory(record, **fields)


# ---------------------------------------------------------------------------
# Requirement 1.1 — the constructor stores tenant_id
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-49f64902")
def test_engine_stores_its_tenant(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    _memory(store, "Alice works at Acme", "global")

    engine = DreamingEngine(store, tenant_id="t1")

    assert getattr(engine, "tenant_id", None) == "t1"
    assert engine.adapter is store


# ---------------------------------------------------------------------------
# Requirement 1.2 — every step read and write is confined to the tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-8b56effb")
def test_engine_confines_every_read_and_write_to_its_tenant(tmp_path: Path) -> None:
    store = _RecordingStore(tmp_path / "mintmory.db")
    store.initialise()
    store.create_tenant("t1")

    recent = datetime.utcnow() - timedelta(days=1)
    _memory(store, "Alice works at Acme", "t1")
    _memory(store, "Carol works at Acme", "t1")
    _memory(store, "Dan works at Acme", "t1")
    a9 = _memory(store, "Acme opens on Fridays", "t1")
    _memory(
        store,
        "Acme is closed on Fridays",
        "t1",
        is_note=True,
        flagged_for_review=True,
        contradicts_ids=[a9.id],
    )
    _memory(store, "Old memo", "t1", is_stale=True, staleness_score=9.5)
    _memory(
        store,
        "Useful tip",
        "t1",
        is_stale=True,
        usefulness_score=6.0,
        staleness_score=4.0,
        last_accessed_at=recent,
    )
    f2 = _memory(store, "Legacy fact", "t1")
    _memory(
        store,
        "New fact",
        "t1",
        flagged_for_review=True,
        contradicts_ids=[f2.id],
    )
    global_memory = _memory(store, "Alice works at Acme", "global")
    store.engine_calls.clear()

    def resolver(_: MemoryRecord) -> list[BatchResolutionAction]:
        return [BatchResolutionAction(action="ADD", reason="brand new fact")]

    engine = DreamingEngine(
        store,
        summarizer=_summarizer,
        conflict_resolver=resolver,
        link_settings=LinkSettings(
            min_shared_entities=1,
            max_per_node=0,
            idf_weighted_strength=False,
            stoplist_csv="",
        ),
        tenant_id="t1",
    )
    assert getattr(engine, "tenant_id", None) == "t1"

    report = engine.run_full()
    assert isinstance(report, DreamReport)

    for method in _READ_METHODS:
        assert store.engine_calls[method], f"{method} was never called"
        assert set(store.engine_calls[method]) == {"t1"}, (
            method,
            store.engine_calls[method],
        )
    for method in _WRITE_METHODS:
        assert store.engine_calls[method], f"{method} was never called"
        assert set(store.engine_calls[method]) == {"t1"}, (
            method,
            store.engine_calls[method],
        )

    with pytest.raises(TenantImmutableError):
        store.update_memory(global_memory.id, tenant_id="t1")
    assert store.get_memory(global_memory.id) is not None


# ---------------------------------------------------------------------------
# Requirement 1.4 — summary job/apply paths use the engine's tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-180a8a6f")
def test_summary_jobs_and_apply_summary_use_the_engine_tenant(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    for name in ("Alice", "Carol", "Dan"):
        _memory(store, f"{name} works at Acme", "global")
    t1_memories = [
        _memory(store, f"{name} works at Acme", "t1") for name in ("Alice", "Carol", "Dan")
    ]

    engine = DreamingEngine(store, summarizer=_summarizer, tenant_id="t1")
    assert getattr(engine, "tenant_id", None) == "t1"

    jobs = engine.collect_summary_jobs()
    assert isinstance(jobs, list)
    assert [job.concept for job in jobs] == ["acme"]
    assert set(jobs[0].memory_ids) == {memory.id for memory in t1_memories}
    assert set(jobs[0].contents) == {memory.content for memory in t1_memories}

    summary = engine.apply_summary("acme", "tenant t1 summary")
    assert isinstance(summary, MemorySummary)
    assert summary.tenant_id == "t1"
    assert summary.memory_count == 3
    assert store.get_summary("acme", "global") is None


# ---------------------------------------------------------------------------
# Requirement 1.5 — tenant_id=None keeps today's engine
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-8bf5b256")
def test_legacy_engine_stores_none_and_stamps_global_writes(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    for name in ("Alice", "Carol", "Dan"):
        _memory(store, f"{name} works at Acme", "global")

    engine = DreamingEngine(
        store,
        summarizer=_summarizer,
        link_settings=LinkSettings(min_shared_entities=1),
    )
    assert getattr(engine, "tenant_id", "MISSING") is None

    report = engine.run_light()
    assert isinstance(report, DreamReport)
    assert report.new_links >= 1
    assert report.new_summaries == 1
    links = _links(store)
    assert links
    assert {link.tenant_id for link in links} == {"global"}
    summary = store.get_summary("acme", "global")
    assert summary is not None
    assert summary.summary_text == "acme:3"


@pytest.mark.l4("C-8bf5b256")
def test_legacy_engine_may_attempt_a_cross_tenant_link_and_add_link_refuses(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    for name in ("Alice", "Carol", "Dan"):
        _memory(store, f"{name} works at Acme", "global")
    _memory(store, "Alice works at Acme", "t1")

    engine = DreamingEngine(store, link_settings=LinkSettings(min_shared_entities=1))
    assert getattr(engine, "tenant_id", "MISSING") is None

    with pytest.raises(CrossTenantLinkError):
        engine.run_light()


# ---------------------------------------------------------------------------
# Requirement 1.6 — builders forward tenant_id
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-86ecfcef")
def test_build_dreaming_engine_passes_tenant_to_the_engine(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")

    engine = build_dreaming_engine(store, LLMSettings(provider=LLMProvider.NONE), tenant_id="t1")

    assert engine is not None
    assert getattr(engine, "tenant_id", None) == "t1"


@pytest.mark.l4("C-86ecfcef")
def test_build_conflict_resolver_lookups_are_tenant_scoped(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    global_conflict = _memory(store, "Acme opens on Fridays", "global")
    record = _memory(
        store,
        "Acme is closed on Fridays",
        "t1",
        flagged_for_review=True,
        contradicts_ids=[global_conflict.id],
    )

    resolver = build_conflict_resolver(
        LLMSettings(provider=LLMProvider.OLLAMA), store, tenant_id="t1"
    )

    assert resolver is not None
    assert resolver(record) == [BatchResolutionAction(action="NONE", reason="no live conflicts")]


# ---------------------------------------------------------------------------
# Requirement 1.7 — Scenario A: linking and summaries
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-1db051ad")
def test_scenario_a_linking_and_summaries_stay_inside_the_tenant(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    g1 = _memory(store, "Alice works at Acme", "global")
    g2 = _memory(store, "Bob works at Acme", "global")
    a1 = _memory(store, "Alice works at Acme", "t1")
    a2 = _memory(store, "Carol works at Acme", "t1")
    a3 = _memory(store, "Dan works at Acme", "t1")

    engine = DreamingEngine(
        store,
        summarizer=_summarizer,
        link_settings=LinkSettings(min_shared_entities=1),
        tenant_id="t1",
    )
    assert getattr(engine, "tenant_id", None) == "t1"

    first = engine.run_light()
    assert isinstance(first, DreamReport)
    assert first.new_links == 3
    assert first.new_summaries == 1

    links = _links(store)
    assert len(links) == 3
    assert {frozenset({link.source_memory_id, link.target_memory_id}) for link in links} == {
        frozenset({a1.id, a2.id}),
        frozenset({a1.id, a3.id}),
        frozenset({a2.id, a3.id}),
    }
    assert {link.link_type.value for link in links} == {"relates_to"}
    assert {link.tenant_id for link in links} == {"t1"}
    assert all(g1.id not in {link.source_memory_id, link.target_memory_id} for link in links)
    assert all(g2.id not in {link.source_memory_id, link.target_memory_id} for link in links)

    summary = store.get_summary("acme", "t1")
    assert summary is not None
    assert summary.concept == "acme"
    assert summary.summary_text == "acme:3"
    assert summary.tenant_id == "t1"
    assert store.get_summary("acme", "global") is None

    second = engine.run_light()
    assert second.new_links == 0
    assert second.new_summaries == 0


# ---------------------------------------------------------------------------
# Requirement 1.3 / 1.8 — Scenario B: cross-tenant resolution is skipped
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-cd24da0d", "C-3b1be517")
def test_scenario_b_cross_tenant_contradiction_is_skipped(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    g9 = _memory(store, "Acme opens on Fridays", "global")
    a9 = _memory(store, "Acme opens on Fridays", "t1")
    n1 = _memory(
        store,
        "Acme is closed on Fridays",
        "t1",
        is_note=True,
        flagged_for_review=True,
        contradicts_ids=[g9.id, a9.id],
    )

    assert store.get_memory(g9.id, tenant_id="t1") is None

    engine = DreamingEngine(store, tenant_id="t1")
    assert getattr(engine, "tenant_id", None) == "t1"

    report = engine.run_full()
    assert isinstance(report, DreamReport)
    assert report.contradictions_resolved == 1

    superseded = store.get_memory(a9.id, tenant_id="t1")
    assert superseded is not None
    assert superseded.superseded_by == n1.id
    assert superseded.is_archived is True

    untouched = store.get_memory(g9.id)
    assert untouched is not None
    assert untouched.superseded_by is None
    assert untouched.is_active is True
    assert untouched.is_archived is False
