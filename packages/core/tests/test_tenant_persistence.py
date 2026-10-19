"""RED tests for task 4 — persist ``tenant_id`` on every row (``storage.py``).

They trace requirement 4.1 (``_MEMORY_COLUMNS``/``_memory_row_values``/
``_row_to_memory`` carry ``tenant_id`` and ``update_memory`` never writes it),
4.2 (links, sessions and query results persist and return the model's
``tenant_id``, plus the memory round trip), 4.6 (with only the reserved tenant
the default ``global`` behaviour is unchanged) and 4.7 (every write in these
tests names a tenant that exists in the directory; no transport is involved).
"""

from __future__ import annotations

import pytest
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    MemoryCategory,
    MemoryRecord,
    QueryResult,
    QuerySession,
    TenantImmutableError,
)


@pytest.fixture()
def store() -> StorageAdapter:
    adapter = StorageAdapter(":memory:")
    adapter.initialise()
    return adapter


def _seed_tenant(store: StorageAdapter, tenant_id: str) -> None:
    """Create the directory row the foreign keys target (R4.7: no ghost tenants)."""
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO tenants (id, name, is_active, created_at, updated_at) "
            "VALUES (?, ?, 1, '2026-01-01T00:00:00', '2026-01-01T00:00:00')",
            (tenant_id, tenant_id),
        )


def _stored_tenant(store: StorageAdapter, table: str, key: str, value: str) -> str:
    row = (
        store.connect()
        .execute(f"SELECT tenant_id FROM {table} WHERE {key} = ?", (value,))
        .fetchone()
    )
    assert row is not None
    return str(row["tenant_id"])


# ---------------------------------------------------------------------------
# Requirement 4.1 + 4.2 — memory column, row values and row mapper in lockstep
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-970f835b", "C-5939ff59", "C-877680dc", "C-03910be6")
def test_memory_tenant_id_persists_and_round_trips(store: StorageAdapter) -> None:
    _seed_tenant(store, "t1")
    record = MemoryRecord(
        content="Alice works at Acme",
        category=MemoryCategory.FACT,
        tenant_id="t1",
    )
    store.add_memory(record)

    fetched = store.get_memory(record.id)
    assert fetched is not None
    assert fetched.tenant_id == "t1"
    assert _stored_tenant(store, "memories", "id", record.id) == "t1"

    default = store.add_memory(content="Bob works at Acme", category=MemoryCategory.FACT)
    default_fetched = store.get_memory(default.id)
    assert default_fetched is not None
    assert default_fetched.tenant_id == "global"
    assert _stored_tenant(store, "memories", "id", default.id) == "global"


@pytest.mark.l4("C-970f835b")
def test_update_memory_does_not_write_tenant_id(store: StorageAdapter) -> None:
    _seed_tenant(store, "t1")
    _seed_tenant(store, "t2")
    record = store.add_memory(
        MemoryRecord(
            content="Alice works at Acme",
            category=MemoryCategory.FACT,
            tenant_id="t1",
        )
    )

    updated = store.update_memory(record.id, content="Alice works at Globex")

    with pytest.raises(TenantImmutableError):
        store.update_memory(record.id, tenant_id="t2")

    assert updated.tenant_id == "t1"
    fetched = store.get_memory(record.id)
    assert fetched is not None
    assert fetched.content == "Alice works at Globex"
    assert fetched.tenant_id == "t1"
    assert _stored_tenant(store, "memories", "id", record.id) == "t1"


# ---------------------------------------------------------------------------
# Requirement 4.2 — links, sessions and query results persist their tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-5939ff59")
def test_link_tenant_id_persists_and_round_trips(store: StorageAdapter) -> None:
    _seed_tenant(store, "t1")
    first = store.add_memory(
        MemoryRecord(content="Alice", category=MemoryCategory.FACT, tenant_id="t1")
    )
    second = store.add_memory(
        MemoryRecord(content="Acme", category=MemoryCategory.FACT, tenant_id="t1")
    )
    link = ConceptLink(
        source_memory_id=first.id,
        target_memory_id=second.id,
        link_type=ConceptLinkType.RELATES_TO,
        tenant_id="t1",
    )
    store.add_link(link)

    links = store.get_links(first.id)
    assert len(links) == 1
    assert links[0].tenant_id == "t1"
    assert _stored_tenant(store, "concept_links", "id", link.id) == "t1"


@pytest.mark.l4("C-5939ff59")
def test_session_and_query_result_tenant_id_persist(store: StorageAdapter) -> None:
    _seed_tenant(store, "t1")
    memory = store.add_memory(
        MemoryRecord(content="Alice works at Acme", category=MemoryCategory.FACT, tenant_id="t1")
    )

    session = QuerySession(query_text="who works at Acme", tenant_id="t1")
    store.create_session(session)
    fetched_session = store.get_session(session.id)
    assert fetched_session is not None
    assert fetched_session.tenant_id == "t1"
    assert _stored_tenant(store, "query_sessions", "id", session.id) == "t1"

    result = QueryResult(
        session_id=session.id,
        memory_id=memory.id,
        relevance_score=0.9,
        tenant_id="t1",
    )
    store.record_query_results([result])
    assert _stored_tenant(store, "query_results", "session_id", session.id) == "t1"


@pytest.mark.l4("C-03910be6")
def test_tenant_writes_target_an_existing_directory_row(store: StorageAdapter) -> None:
    _seed_tenant(store, "t1")
    record = store.add_memory(
        MemoryRecord(content="Alice works at Acme", category=MemoryCategory.FACT, tenant_id="t1")
    )
    rows = (
        store.connect()
        .execute(
            "SELECT t.id AS id FROM tenants AS t JOIN memories AS m "
            "ON m.tenant_id = t.id WHERE m.id = ?",
            (record.id,),
        )
        .fetchall()
    )
    assert [row["id"] for row in rows] == ["t1"]
