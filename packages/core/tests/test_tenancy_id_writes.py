"""RED tests for task 4 — ``tenant_id`` on the id-only writes (requirement 3).

They trace requirement 3.1 (the SQLite and Protocol signatures gain a trailing
``tenant_id: str | None = None`` on ``archive_memory``, ``supersede_memory`` and
``apply_feedback``), 3.2 (``tenant_id=None`` acts on the stored row and keeps the
today's missing-row outcomes), 3.3 (a concrete ``tenant_id`` requires the row —
and for supersede both rows — in that tenant, otherwise ``KeyError`` naming the
first foreign id), 3.4 (these writes never change a stored tenant) and 3.5 (the
requirement's archive example).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from mintmory.core.ports import StorageBackend
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import MemoryCategory, MemoryRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _store(tmp_path: Path) -> SqliteBackend:
    backend = SqliteBackend(tmp_path / "mintmory.db")
    backend.initialise()
    return backend


def _create_tenant(store: SqliteBackend, tenant_id: str) -> None:
    store.create_tenant(tenant_id)


def _memory(store: SqliteBackend, content: str, tenant_id: str = "global") -> MemoryRecord:
    return store.add_memory(
        MemoryRecord(content=content, category=MemoryCategory.FACT, tenant_id=tenant_id)
    )


def _stored(store: SqliteBackend, memory_id: str) -> MemoryRecord:
    record = store.get_memory(memory_id)
    assert record is not None
    return record


def _assert_active(store: SqliteBackend, memory_id: str, expected: bool) -> None:
    assert _stored(store, memory_id).is_active is expected


# ---------------------------------------------------------------------------
# Requirement 3.1 — signatures on SQLite and the Protocol
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3810642f")
def test_id_only_write_signatures(tmp_path: Path) -> None:
    expected = {
        "archive_memory": ["self", "memory_id", "tenant_id"],
        "supersede_memory": ["self", "memory_id", "by_id", "tenant_id"],
        "apply_feedback": ["self", "memory_id", "useful", "stale", "tenant_id"],
    }
    for backend in (SqliteBackend, StorageBackend):
        for name, parameters in expected.items():
            signature = inspect.signature(getattr(backend, name))
            assert list(signature.parameters) == parameters
            assert signature.parameters["tenant_id"].default is None

    store = _store(tmp_path)
    with pytest.raises(KeyError):
        store.archive_memory("missing-memory", tenant_id="t1")


# ---------------------------------------------------------------------------
# Requirement 3.2 — tenant_id=None acts on the stored row
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-18bbe618", "C-a7082d94")
def test_none_acts_on_the_stored_row_and_keeps_missing_row_outcomes(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _create_tenant(store, "t1")
    a1 = _memory(store, "first t1 fact", "t1")
    a2 = _memory(store, "second t1 fact", "t1")
    g1 = _memory(store, "first global fact")
    g2 = _memory(store, "second global fact")

    store.archive_memory("missing-memory")
    store.supersede_memory("missing-memory", "also-missing")
    with pytest.raises(KeyError) as missing_feedback:
        store.apply_feedback("missing-memory", useful=True, stale=False)
    assert "missing-memory" in str(missing_feedback.value)

    store.archive_memory(a1.id)
    _assert_active(store, a1.id, False)

    store.supersede_memory(g1.id, g2.id)
    assert _stored(store, g1.id).superseded_by == g2.id

    store.apply_feedback(a2.id, useful=True, stale=False)
    assert _stored(store, a2.id).usefulness_score > 0

    with pytest.raises(KeyError):
        store.archive_memory(a2.id, tenant_id="global")
    _assert_active(store, a2.id, True)


# ---------------------------------------------------------------------------
# Requirement 3.3 — a concrete tenant_id requires the row in that tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-a7082d94")
def test_concrete_tenant_requires_the_row_in_that_tenant(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create_tenant(store, "t1")
    a1 = _memory(store, "first t1 fact", "t1")
    a2 = _memory(store, "second t1 fact", "t1")
    g1 = _memory(store, "first global fact")

    usefulness_before = _stored(store, a1.id).usefulness_score
    with pytest.raises(KeyError) as foreign_archive:
        store.archive_memory(a1.id, tenant_id="global")
    assert a1.id in str(foreign_archive.value)
    _assert_active(store, a1.id, True)

    with pytest.raises(KeyError) as foreign_feedback:
        store.apply_feedback(a1.id, useful=True, stale=False, tenant_id="global")
    assert a1.id in str(foreign_feedback.value)
    assert _stored(store, a1.id).usefulness_score == usefulness_before

    with pytest.raises(KeyError) as foreign_by_id:
        store.supersede_memory(a1.id, g1.id, tenant_id="t1")
    assert g1.id in str(foreign_by_id.value)
    _assert_active(store, a1.id, True)

    with pytest.raises(KeyError) as missing_by_id:
        store.supersede_memory(a1.id, "missing-by-id", tenant_id="t1")
    assert "missing-by-id" in str(missing_by_id.value)

    with pytest.raises(KeyError) as foreign_memory:
        store.supersede_memory(a1.id, a2.id, tenant_id="global")
    assert a1.id in str(foreign_memory.value)
    _assert_active(store, a1.id, True)

    store.archive_memory(a1.id, tenant_id="t1")
    _assert_active(store, a1.id, False)


# ---------------------------------------------------------------------------
# Requirement 3.4 — the writes never move a row to another tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-44a91f81")
def test_id_only_writes_never_change_the_stored_tenant(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create_tenant(store, "t1")
    a1 = _memory(store, "archive me", "t1")
    a2 = _memory(store, "give feedback to me", "t1")
    a3 = _memory(store, "supersede me", "t1")
    a4 = _memory(store, "replace with me", "t1")
    g1 = _memory(store, "global archive")
    g2 = _memory(store, "global supersede")
    g3 = _memory(store, "global replacement")

    store.archive_memory(a1.id, tenant_id="t1")
    assert _stored(store, a1.id).tenant_id == "t1"

    store.apply_feedback(a2.id, useful=True, stale=False, tenant_id="t1")
    assert _stored(store, a2.id).tenant_id == "t1"

    store.supersede_memory(a3.id, by_id=a4.id, tenant_id="t1")
    assert _stored(store, a3.id).tenant_id == "t1"
    assert _stored(store, a4.id).tenant_id == "t1"

    store.archive_memory(g1.id)
    assert _stored(store, g1.id).tenant_id == "global"

    store.supersede_memory(g2.id, by_id=g3.id)
    assert _stored(store, g2.id).tenant_id == "global"


# ---------------------------------------------------------------------------
# Requirement 3.5 — the requirement's archive example
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-24839466")
def test_archive_with_a_concrete_tenant_keeps_foreign_rows_active(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create_tenant(store, "t1")
    g1 = _memory(store, "global fact")
    a1 = _memory(store, "first t1 fact", "t1")

    assert g1.tenant_id == "global"
    with pytest.raises(KeyError):
        store.archive_memory(a1.id, tenant_id="global")
    _assert_active(store, a1.id, True)

    store.archive_memory(a1.id)
    _assert_active(store, a1.id, False)

    a1_again = _memory(store, "another t1 fact", "t1")
    store.archive_memory(a1_again.id, tenant_id="t1")
    _assert_active(store, a1_again.id, False)
