"""RED tests for task 2 — tenant-scoped dreaming helper reads.

They trace requirement 1.1: the ten dreaming helpers gain a trailing
``tenant_id: str | None = None`` on ``SqliteBackend`` and the
``StorageBackend`` Protocol, with ``None``/concrete/unknown-tenant semantics.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from mintmory.core.ports import StorageBackend
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import ConceptLink, ConceptLinkType, MemoryCategory, MemoryRecord


@dataclass
class DreamSeed:
    store: SqliteBackend
    g_flagged: MemoryRecord
    g_never_stale: MemoryRecord
    g_high: MemoryRecord
    g_stale_archivable: MemoryRecord
    g_rehab: MemoryRecord
    g_note_stale: MemoryRecord
    g_never_id: MemoryRecord
    g_retrieved_old: MemoryRecord
    g_archived: MemoryRecord
    g_rel_a: MemoryRecord
    g_rel_b: MemoryRecord
    g_rel_c: MemoryRecord
    a_flagged: MemoryRecord
    a_never_stale: MemoryRecord
    a_high: MemoryRecord
    a_stale_archivable: MemoryRecord
    a_rehab: MemoryRecord
    a_note_stale: MemoryRecord
    a_never_id: MemoryRecord
    a_retrieved_old: MemoryRecord
    a_archived: MemoryRecord
    a_rel_a: MemoryRecord
    a_rel_b: MemoryRecord
    a_rel_c: MemoryRecord
    g_active_ids: set[str]
    a_active_ids: set[str]


def _memory(store: SqliteBackend, content: str, tenant_id: str, **fields: Any) -> MemoryRecord:
    return store.add_memory(
        MemoryRecord(
            content=content,
            category=MemoryCategory.FACT,
            tenant_id=tenant_id,
            **fields,
        )
    )


def _relates(store: SqliteBackend, source: str, target: str, tenant_id: str) -> None:
    store.add_link(
        ConceptLink(
            source_memory_id=source,
            target_memory_id=target,
            link_type=ConceptLinkType.RELATES_TO,
            tenant_id=tenant_id,
        )
    )


@pytest.fixture
def seed(tmp_path: Path) -> DreamSeed:
    store = SqliteBackend(tmp_path / "mintmory.db")
    store.initialise()
    store.create_tenant("t1")

    old = datetime(1999, 12, 31)
    recent = datetime(2026, 1, 1)

    g_flagged = _memory(store, "global flagged", "global", flagged_for_review=True)
    g_never_stale = _memory(store, "global never accessed stale", "global", staleness_score=4.0)
    g_high = _memory(
        store,
        "global high staleness useful",
        "global",
        staleness_score=6.0,
        usefulness_score=4.0,
        last_accessed_at=recent,
    )
    g_stale_archivable = _memory(
        store,
        "global stale archivable",
        "global",
        is_stale=True,
        staleness_score=9.0,
        usefulness_score=1.0,
        last_accessed_at=old,
    )
    g_rehab = _memory(
        store,
        "global rehabilitable",
        "global",
        is_stale=True,
        staleness_score=1.0,
        usefulness_score=9.0,
        last_accessed_at=recent,
    )
    g_note_stale = _memory(
        store,
        "global stale note",
        "global",
        is_note=True,
        is_stale=True,
        staleness_score=9.0,
        usefulness_score=9.0,
    )
    g_never_id = _memory(store, "global never retrieved", "global", created_at=old)
    g_retrieved_old = _memory(
        store, "global retrieved long ago", "global", retrieval_count=1, created_at=old
    )
    g_archived = _memory(store, "global archived", "global", is_archived=True)
    g_rel_a = _memory(store, "global relation a", "global")
    g_rel_b = _memory(store, "global relation b", "global")
    g_rel_c = _memory(store, "global relation c", "global")

    a_flagged = _memory(store, "t1 flagged", "t1", flagged_for_review=True)
    a_never_stale = _memory(store, "t1 never accessed stale", "t1", staleness_score=4.0)
    a_high = _memory(
        store,
        "t1 high staleness useful",
        "t1",
        staleness_score=6.0,
        usefulness_score=4.0,
        last_accessed_at=recent,
    )
    a_stale_archivable = _memory(
        store,
        "t1 stale archivable",
        "t1",
        is_stale=True,
        staleness_score=9.0,
        usefulness_score=1.0,
        last_accessed_at=old,
    )
    a_rehab = _memory(
        store,
        "t1 rehabilitable",
        "t1",
        is_stale=True,
        staleness_score=1.0,
        usefulness_score=9.0,
        last_accessed_at=recent,
    )
    a_note_stale = _memory(
        store,
        "t1 stale note",
        "t1",
        is_note=True,
        is_stale=True,
        staleness_score=9.0,
        usefulness_score=9.0,
    )
    a_never_id = _memory(store, "t1 never retrieved", "t1", created_at=old)
    a_retrieved_old = _memory(
        store, "t1 retrieved long ago", "t1", retrieval_count=1, created_at=old
    )
    a_archived = _memory(store, "t1 archived", "t1", is_archived=True)
    a_rel_a = _memory(store, "t1 relation a", "t1")
    a_rel_b = _memory(store, "t1 relation b", "t1")
    a_rel_c = _memory(store, "t1 relation c", "t1")

    _relates(store, g_rel_a.id, g_rel_b.id, "global")
    store.add_link(
        ConceptLink(
            source_memory_id=g_rel_a.id,
            target_memory_id=g_rel_c.id,
            link_type=ConceptLinkType.CONTRADICTS,
            tenant_id="global",
        )
    )
    _relates(store, a_rel_a.id, a_rel_b.id, "t1")
    store.add_link(
        ConceptLink(
            source_memory_id=a_rel_a.id,
            target_memory_id=a_rel_c.id,
            link_type=ConceptLinkType.CONTRADICTS,
            tenant_id="t1",
        )
    )

    g_all = [
        g_flagged,
        g_never_stale,
        g_high,
        g_stale_archivable,
        g_rehab,
        g_note_stale,
        g_never_id,
        g_retrieved_old,
        g_archived,
        g_rel_a,
        g_rel_b,
        g_rel_c,
    ]
    a_all = [
        a_flagged,
        a_never_stale,
        a_high,
        a_stale_archivable,
        a_rehab,
        a_note_stale,
        a_never_id,
        a_retrieved_old,
        a_archived,
        a_rel_a,
        a_rel_b,
        a_rel_c,
    ]

    return DreamSeed(
        store=store,
        g_flagged=g_flagged,
        g_never_stale=g_never_stale,
        g_high=g_high,
        g_stale_archivable=g_stale_archivable,
        g_rehab=g_rehab,
        g_note_stale=g_note_stale,
        g_never_id=g_never_id,
        g_retrieved_old=g_retrieved_old,
        g_archived=g_archived,
        g_rel_a=g_rel_a,
        g_rel_b=g_rel_b,
        g_rel_c=g_rel_c,
        a_flagged=a_flagged,
        a_never_stale=a_never_stale,
        a_high=a_high,
        a_stale_archivable=a_stale_archivable,
        a_rehab=a_rehab,
        a_note_stale=a_note_stale,
        a_never_id=a_never_id,
        a_retrieved_old=a_retrieved_old,
        a_archived=a_archived,
        a_rel_a=a_rel_a,
        a_rel_b=a_rel_b,
        a_rel_c=a_rel_c,
        g_active_ids={record.id for record in g_all if not record.is_archived},
        a_active_ids={record.id for record in a_all if not record.is_archived},
    )


def _ids(records: list[MemoryRecord]) -> set[str]:
    return {record.id for record in records}


@pytest.mark.l4("C-91dbbaaa")
def test_dreaming_read_signatures_declare_trailing_tenant_id() -> None:
    expected = {
        "get_flagged_memories": ["self", "tenant_id"],
        "get_never_accessed_stale": ["self", "days_old", "min_staleness", "tenant_id"],
        "get_high_staleness_useful": ["self", "min_staleness", "min_usefulness", "tenant_id"],
        "get_anomaly_high_staleness_useful_ids": [
            "self",
            "min_staleness",
            "min_usefulness",
            "tenant_id",
        ],
        "get_anomaly_never_accessed_ids": ["self", "cutoff_iso", "tenant_id"],
        "get_anomaly_flagged_ids": ["self", "tenant_id"],
        "list_active_memory_ids": ["self", "ordered", "tenant_id"],
        "get_stale_archivable_ids": ["self", "min_staleness", "cutoff_iso", "tenant_id"],
        "get_rehabilitable_rows": ["self", "cutoff_iso", "tenant_id"],
        "get_existing_relates_to_pairs": ["self", "tenant_id"],
    }
    for cls in (SqliteBackend, StorageBackend):
        for name, parameters in expected.items():
            signature = inspect.signature(getattr(cls, name))
            assert list(signature.parameters) == parameters, f"{cls.__name__}.{name}"
            assert signature.parameters["tenant_id"].default is None

    active = inspect.signature(SqliteBackend.list_active_memory_ids).parameters
    assert active["ordered"].kind is inspect.Parameter.KEYWORD_ONLY
    assert active["tenant_id"].kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.l4("C-91dbbaaa")
def test_get_flagged_memories_is_tenant_scoped(seed: DreamSeed) -> None:
    store = seed.store

    assert _ids(store.get_flagged_memories(tenant_id="t1")) == {seed.a_flagged.id}
    assert _ids(store.get_flagged_memories(tenant_id=None)) == {
        seed.g_flagged.id,
        seed.a_flagged.id,
    }
    assert store.get_flagged_memories(tenant_id="nope") == []


@pytest.mark.l4("C-91dbbaaa")
def test_get_never_accessed_stale_is_tenant_scoped(seed: DreamSeed) -> None:
    store = seed.store

    assert _ids(store.get_never_accessed_stale(tenant_id="t1")) == {seed.a_never_stale.id}
    assert _ids(store.get_never_accessed_stale(tenant_id=None)) == {
        seed.g_never_stale.id,
        seed.a_never_stale.id,
    }
    assert store.get_never_accessed_stale(tenant_id="nope") == []


@pytest.mark.l4("C-91dbbaaa")
def test_get_high_staleness_useful_is_tenant_scoped(seed: DreamSeed) -> None:
    store = seed.store

    assert _ids(store.get_high_staleness_useful(tenant_id="t1")) == {seed.a_high.id}
    assert _ids(store.get_high_staleness_useful(tenant_id=None)) == {
        seed.g_high.id,
        seed.a_high.id,
    }
    assert store.get_high_staleness_useful(tenant_id="nope") == []


@pytest.mark.l4("C-91dbbaaa")
def test_get_anomaly_high_staleness_useful_ids_is_tenant_scoped(seed: DreamSeed) -> None:
    store = seed.store

    assert store.get_anomaly_high_staleness_useful_ids(5.0, 3.0, tenant_id="t1") == [seed.a_high.id]
    assert set(store.get_anomaly_high_staleness_useful_ids(5.0, 3.0, tenant_id=None)) == {
        seed.g_high.id,
        seed.a_high.id,
    }
    assert store.get_anomaly_high_staleness_useful_ids(5.0, 3.0, tenant_id="nope") == []


@pytest.mark.l4("C-91dbbaaa")
def test_get_anomaly_never_accessed_ids_is_tenant_scoped(seed: DreamSeed) -> None:
    store = seed.store

    assert store.get_anomaly_never_accessed_ids("2000-01-01T00:00:00", tenant_id="t1") == [
        seed.a_never_id.id
    ]
    assert set(store.get_anomaly_never_accessed_ids("2000-01-01T00:00:00", tenant_id=None)) == {
        seed.g_never_id.id,
        seed.a_never_id.id,
    }
    assert store.get_anomaly_never_accessed_ids("2000-01-01T00:00:00", tenant_id="nope") == []


@pytest.mark.l4("C-91dbbaaa")
def test_get_anomaly_flagged_ids_is_tenant_scoped(seed: DreamSeed) -> None:
    store = seed.store

    assert store.get_anomaly_flagged_ids(tenant_id="t1") == [seed.a_flagged.id]
    assert set(store.get_anomaly_flagged_ids(tenant_id=None)) == {
        seed.g_flagged.id,
        seed.a_flagged.id,
    }
    assert store.get_anomaly_flagged_ids(tenant_id="nope") == []


@pytest.mark.l4("C-91dbbaaa")
def test_list_active_memory_ids_is_tenant_scoped(seed: DreamSeed) -> None:
    store = seed.store

    assert set(store.list_active_memory_ids(tenant_id="t1")) == seed.a_active_ids
    assert set(store.list_active_memory_ids(tenant_id=None)) == (
        seed.g_active_ids | seed.a_active_ids
    )
    assert store.list_active_memory_ids(tenant_id="nope") == []
    assert store.list_active_memory_ids(ordered=True, tenant_id="t1") == sorted(seed.a_active_ids)


@pytest.mark.l4("C-91dbbaaa")
def test_get_stale_archivable_ids_is_tenant_scoped(seed: DreamSeed) -> None:
    store = seed.store

    assert store.get_stale_archivable_ids(5.0, "2000-01-01T00:00:00", tenant_id="t1") == [
        seed.a_stale_archivable.id
    ]
    assert set(store.get_stale_archivable_ids(5.0, "2000-01-01T00:00:00", tenant_id=None)) == {
        seed.g_stale_archivable.id,
        seed.a_stale_archivable.id,
    }
    assert store.get_stale_archivable_ids(5.0, "2000-01-01T00:00:00", tenant_id="nope") == []


@pytest.mark.l4("C-91dbbaaa")
def test_get_rehabilitable_rows_is_tenant_scoped(seed: DreamSeed) -> None:
    store = seed.store

    assert store.get_rehabilitable_rows("2025-01-01T00:00:00", tenant_id="t1") == [
        (seed.a_rehab.id, 1.0)
    ]
    assert set(store.get_rehabilitable_rows("2025-01-01T00:00:00", tenant_id=None)) == {
        (seed.g_rehab.id, 1.0),
        (seed.a_rehab.id, 1.0),
    }
    assert store.get_rehabilitable_rows("2025-01-01T00:00:00", tenant_id="nope") == []


@pytest.mark.l4("C-91dbbaaa")
def test_get_existing_relates_to_pairs_is_tenant_scoped(seed: DreamSeed) -> None:
    store = seed.store

    assert store.get_existing_relates_to_pairs(tenant_id="t1") == {
        frozenset({seed.a_rel_a.id, seed.a_rel_b.id})
    }
    assert store.get_existing_relates_to_pairs(tenant_id=None) == {
        frozenset({seed.g_rel_a.id, seed.g_rel_b.id}),
        frozenset({seed.a_rel_a.id, seed.a_rel_b.id}),
    }
    assert store.get_existing_relates_to_pairs(tenant_id="nope") == set()
