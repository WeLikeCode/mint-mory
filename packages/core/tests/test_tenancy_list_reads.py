"""RED tests for task 4 — the query-text-free list for the copy.

They trace requirement 4.1 (``list_memories`` with ``MemoryFilter`` semantics,
the tenant predicate and ``limit`` applied after filtering), 4.2 (the scoped /
unscoped examples: active, stale, archived and inactive rows) and 4.3
(``memory_exists_with_content`` is true only for an exact-content row of the
requested tenant).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import MemoryCategory, MemoryFilter, MemoryRecord


@dataclass
class Seed:
    store: SqliteBackend
    t_active: MemoryRecord
    t_stale: MemoryRecord
    t_archived: MemoryRecord
    t_inactive: MemoryRecord
    g1: MemoryRecord
    g2: MemoryRecord


def _memory(
    store: SqliteBackend,
    content: str,
    tenant_id: str,
    *,
    is_stale: bool = False,
    is_archived: bool = False,
    is_active: bool = True,
    created_at: datetime | None = None,
) -> MemoryRecord:
    record = MemoryRecord(
        content=content,
        category=MemoryCategory.FACT,
        entity_ids=["Alice"],
        tenant_id=tenant_id,
        is_stale=is_stale,
        is_archived=is_archived,
        is_active=is_active,
    )
    if created_at is not None:
        record.created_at = created_at
    return store.add_memory(record)


@pytest.fixture
def seed(tmp_path: Path) -> Seed:
    store = SqliteBackend(tmp_path / "mintmory.db")
    store.initialise()
    store.create_tenant("t1")

    t_active = _memory(store, "t1 active fact", "t1", created_at=datetime(2026, 1, 1))
    t_stale = _memory(store, "t1 stale fact", "t1", is_stale=True, created_at=datetime(2026, 1, 2))
    t_archived = _memory(
        store, "t1 archived fact", "t1", is_archived=True, created_at=datetime(2026, 1, 3)
    )
    t_inactive = _memory(
        store, "t1 inactive fact", "t1", is_active=False, created_at=datetime(2026, 1, 4)
    )
    g1 = _memory(store, "global active fact one", "global", created_at=datetime(2026, 1, 5))
    g2 = _memory(store, "global active fact two", "global", created_at=datetime(2026, 1, 6))

    return Seed(
        store=store,
        t_active=t_active,
        t_stale=t_stale,
        t_archived=t_archived,
        t_inactive=t_inactive,
        g1=g1,
        g2=g2,
    )


# ---------------------------------------------------------------------------
# Requirement 4.1 / 4.2 — the scoped and unscoped examples
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-d318e454", "C-12e05552")
def test_list_memories_is_tenant_scoped(seed: Seed) -> None:
    store = seed.store

    scoped = store.list_memories(tenant_id="t1")
    assert [mem.id for mem in scoped] == [seed.t_active.id]

    keep_stale = store.list_memories(MemoryFilter(exclude_stale=False), tenant_id="t1")
    assert [mem.id for mem in keep_stale] == [seed.t_active.id, seed.t_stale.id]

    unscoped = store.list_memories()
    assert {mem.id for mem in unscoped} == {
        seed.t_active.id,
        seed.g1.id,
        seed.g2.id,
    }

    assert store.list_memories(tenant_id="nope") == []


# ---------------------------------------------------------------------------
# Requirement 4.1 — limit semantics (None / 0 / negative / after filtering)
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-12e05552")
def test_list_memories_limit_semantics(seed: Seed) -> None:
    store = seed.store

    default_list = store.list_memories(tenant_id="t1", limit=None)
    assert [mem.id for mem in default_list] == [seed.t_active.id]

    assert store.list_memories(tenant_id="t1", limit=0) == []

    with pytest.raises(ValueError, match="limit must be >= 0"):
        store.list_memories(tenant_id="t1", limit=-1)

    stale_kept_one = store.list_memories(MemoryFilter(exclude_stale=False), tenant_id="t1", limit=1)
    assert [mem.id for mem in stale_kept_one] == [seed.t_active.id]

    unscoped_oldest = store.list_memories(limit=1)
    assert [mem.id for mem in unscoped_oldest] == [seed.t_active.id]


# ---------------------------------------------------------------------------
# Requirement 4.3 — exact-content dedup check confined to the tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-96f1f808")
def test_memory_exists_with_content_is_scoped_for_the_copy(seed: Seed) -> None:
    store = seed.store

    assert store.memory_exists_with_content("t1 active fact", tenant_id="t1") is True
    assert store.memory_exists_with_content("t1 stale fact", tenant_id="t1") is True

    foreign = store.memory_exists_with_content("global active fact one", tenant_id="t1")
    assert foreign is False
    assert (
        store.memory_exists_with_content("content never stored anywhere", tenant_id="t1") is False
    )
