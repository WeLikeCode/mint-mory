"""RED tests for task 4 — same-tenant references and id-only writes on Postgres.

They trace requirement 3.1 (``add_link``, ``record_query_results``,
``supersede_memory``, ``superseded_by`` on ``add_memory`` / ``update_memory``
and ``tenant_id`` in ``update_memory`` fields raise the same errors with the
same arguments as SQLite, keep the missing-row database errors, and let a
``global`` session reference any tenant), 3.2 (``tenant_id=None`` acts by id;
a concrete tenant that does not own the row raises ``KeyError``), 5.2 (each
reference rule raises with the stated arguments under a responder keyed on the
looked-up id, plus the archive example) and 5.7 (a rejected result batch writes
no row, and supersede names the first foreign id).  The fake pool of
``pg_fakes`` supplies the statements; no database is needed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest
from mintmory.core.storage_postgres import PostgresBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    CrossTenantLinkError,
    MemoryCategory,
    MemoryRecord,
    QueryResult,
    TenantImmutableError,
)
from psycopg.errors import ForeignKeyViolation

from packages.core.tests.pg_fakes import FakeConnection, FakeCursor, FakePool


def _backend(conn: FakeConnection) -> PostgresBackend:
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)
    return backend


def _memory_row(memory_id: str, tenant_id: str) -> dict[str, Any]:
    stamp = datetime(2026, 1, 1)
    return {
        "id": memory_id,
        "content": f"content {memory_id}",
        "category": "fact",
        "entity_ids": [],
        "confidence": 1.0,
        "source": "agent",
        "verified": False,
        "valid_from": None,
        "valid_until": None,
        "usefulness_score": 0.0,
        "staleness_score": 0.0,
        "reinforcement_count": 0,
        "retrieval_count": 0,
        "is_stale": False,
        "is_active": True,
        "is_archived": False,
        "superseded_by": None,
        "flagged_for_review": False,
        "contradicts_ids": [],
        "is_note": False,
        "created_at": stamp,
        "updated_at": stamp,
        "last_accessed_at": None,
        "metadata": {},
        "tenant_id": tenant_id,
    }


def _responder(
    memory_tenants: dict[str, str] | None = None,
    session_tenants: dict[str, str] | None = None,
    *,
    fail_on: str | None = None,
) -> Callable[[str, Any], list[Any]]:
    """Answer lookups by id, the write guard with an active tenant, and writes."""
    memories = memory_tenants or {}
    sessions = session_tenants or {}

    def responder(sql: str, params: Any) -> list[Any]:
        normalised = " ".join(sql.split())
        if normalised.startswith("SELECT is_active FROM tenants"):
            return [{"is_active": True}]
        if normalised.startswith("SELECT tenant_id FROM memories WHERE id = %s"):
            tenant = memories.get(str(params[0]))
            return [{"tenant_id": tenant}] if tenant is not None else []
        if normalised.startswith("SELECT tenant_id FROM query_sessions WHERE id = %s"):
            tenant = sessions.get(str(params[0]))
            return [{"tenant_id": tenant}] if tenant is not None else []
        if fail_on is not None and normalised.startswith(fail_on):
            raise ForeignKeyViolation("fake foreign key violation")
        if "FROM memories WHERE id = %s" in normalised:
            tenant = memories.get(str(params[0]))
            return [_memory_row(str(params[0]), tenant)] if tenant is not None else []
        if normalised.startswith("UPDATE memories SET") and "RETURNING id" in normalised:
            return [{"id": params["id"]}]
        return []

    return responder


class _ForeignKeyCursor(FakeCursor):
    """Cursor whose batch insert reports the foreign-key error psycopg would raise."""

    def executemany(self, sql: str, params_seq: Any) -> None:
        if self.connection is not None:
            for params in params_seq:
                self.connection.executed.append((sql, params))
        raise ForeignKeyViolation("fake foreign key violation")


class _ForeignKeyConnection(FakeConnection):
    """Connection whose ``executemany`` (the result batch) raises a foreign-key error."""

    def cursor(self, row_factory: Any = None) -> FakeCursor:
        return _ForeignKeyCursor(self, row_factory)


def _write_statements(conn: FakeConnection) -> list[str]:
    return [
        " ".join(sql.split())
        for sql, _params in conn.executed
        if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]


# ---------------------------------------------------------------------------
# Requirement 3.1 + 5.2 — add_link compares endpoints and the link tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-ce6c1aac", "C-8d3fb08f")
def test_pg_add_link_rejects_cross_tenant_endpoints() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1", "g1": "global"}))
    backend = _backend(conn)
    link = ConceptLink(
        source_memory_id="a1",
        target_memory_id="g1",
        link_type=ConceptLinkType.RELATES_TO,
        tenant_id="t1",
    )

    with pytest.raises(CrossTenantLinkError) as raised:
        backend.add_link(link)

    assert (
        raised.value.first_id,
        raised.value.first_tenant,
        raised.value.second_id,
        raised.value.second_tenant,
    ) == ("a1", "t1", "g1", "global")
    assert _write_statements(conn) == []


@pytest.mark.l4("C-ce6c1aac", "C-8d3fb08f")
def test_pg_add_link_requires_the_link_tenant_to_match_its_endpoints() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1", "a2": "t1"}))
    backend = _backend(conn)
    link = ConceptLink(
        source_memory_id="a1",
        target_memory_id="a2",
        link_type=ConceptLinkType.RELATES_TO,
        tenant_id="global",
    )

    with pytest.raises(CrossTenantLinkError) as raised:
        backend.add_link(link)

    assert (
        raised.value.first_id,
        raised.value.first_tenant,
        raised.value.second_id,
        raised.value.second_tenant,
    ) == ("a1", "t1", "a2", "global")
    assert _write_statements(conn) == []


@pytest.mark.l4("C-ce6c1aac")
def test_pg_add_link_missing_endpoint_keeps_the_foreign_key_error() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1"}, fail_on="INSERT INTO concept_links"))
    backend = _backend(conn)
    link = ConceptLink(
        source_memory_id="a1",
        target_memory_id="missing",
        link_type=ConceptLinkType.RELATES_TO,
        tenant_id="t1",
    )

    with pytest.raises(ForeignKeyViolation):
        backend.add_link(link)

    assert any(
        statement.startswith("INSERT INTO concept_links") for statement in _write_statements(conn)
    )


# ---------------------------------------------------------------------------
# Requirement 3.1 + 5.2 — record_query_results compares session and memory
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-ce6c1aac", "C-8d3fb08f")
def test_pg_record_query_results_rejects_a_cross_tenant_memory() -> None:
    conn = FakeConnection(responder=_responder({"g1": "global"}, {"s1": "t1"}))
    backend = _backend(conn)
    result = QueryResult(
        session_id="s1",
        memory_id="g1",
        relevance_score=1.0,
        tenant_id="t1",
    )

    with pytest.raises(CrossTenantLinkError) as raised:
        backend.record_query_results([result])

    assert (
        raised.value.first_id,
        raised.value.first_tenant,
        raised.value.second_id,
        raised.value.second_tenant,
    ) == ("s1", "t1", "g1", "global")
    assert _write_statements(conn) == []


@pytest.mark.l4("C-ce6c1aac", "C-8d3fb08f")
def test_pg_record_query_results_rejects_a_foreign_result_tenant() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1"}, {"s1": "t1"}))
    backend = _backend(conn)
    result = QueryResult(
        session_id="s1",
        memory_id="a1",
        relevance_score=1.0,
        tenant_id="global",
    )

    with pytest.raises(CrossTenantLinkError) as raised:
        backend.record_query_results([result])

    assert (
        raised.value.first_id,
        raised.value.first_tenant,
        raised.value.second_id,
        raised.value.second_tenant,
    ) == ("s1", "t1", "a1", "global")
    assert _write_statements(conn) == []


@pytest.mark.l4("C-ce6c1aac")
def test_pg_record_query_results_global_session_may_reference_any_tenant() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1"}, {"s1": "global"}))
    backend = _backend(conn)
    result = QueryResult(
        session_id="s1",
        memory_id="a1",
        relevance_score=1.0,
        tenant_id="global",
    )

    backend.record_query_results([result])

    assert any(
        statement.startswith("INSERT INTO query_results") for statement in _write_statements(conn)
    )
    assert conn.commits == 1


@pytest.mark.l4("C-ce6c1aac", "C-8d3fb08f", "C-3f98f2b5")
def test_pg_record_query_results_validates_the_batch_before_inserting() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1", "g1": "global"}, {"s1": "t1"}))
    backend = _backend(conn)
    valid = QueryResult(
        session_id="s1",
        memory_id="a1",
        relevance_score=1.0,
        tenant_id="t1",
    )
    invalid = QueryResult(
        session_id="s1",
        memory_id="g1",
        relevance_score=1.0,
        tenant_id="t1",
    )

    with pytest.raises(CrossTenantLinkError) as raised:
        backend.record_query_results([valid, invalid])

    assert (
        raised.value.first_id,
        raised.value.first_tenant,
        raised.value.second_id,
        raised.value.second_tenant,
    ) == ("s1", "t1", "g1", "global")
    assert _write_statements(conn) == []


@pytest.mark.l4("C-ce6c1aac")
def test_pg_record_query_results_missing_session_keeps_the_foreign_key_error() -> None:
    conn = _ForeignKeyConnection(responder=_responder({"a1": "t1"}))
    backend = _backend(conn)
    result = QueryResult(
        session_id="missing",
        memory_id="a1",
        relevance_score=1.0,
        tenant_id="t1",
    )

    with pytest.raises(ForeignKeyViolation):
        backend.record_query_results([result])

    assert any(
        statement.startswith("INSERT INTO query_results") for statement in _write_statements(conn)
    )


# ---------------------------------------------------------------------------
# Requirement 3.1 + 5.2 — supersede_memory and superseded_by comparisons
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-ce6c1aac", "C-8d3fb08f")
def test_pg_supersede_memory_rejects_a_cross_tenant_by_id() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1", "g1": "global"}))
    backend = _backend(conn)

    with pytest.raises(CrossTenantLinkError) as raised:
        backend.supersede_memory("a1", "g1")

    assert (
        raised.value.first_id,
        raised.value.first_tenant,
        raised.value.second_id,
        raised.value.second_tenant,
    ) == ("a1", "t1", "g1", "global")
    assert _write_statements(conn) == []


@pytest.mark.l4("C-ce6c1aac")
def test_pg_supersede_memory_missing_by_id_keeps_the_foreign_key_error() -> None:
    conn = FakeConnection(
        responder=_responder({"a1": "t1"}, fail_on="UPDATE memories SET superseded_by")
    )
    backend = _backend(conn)

    with pytest.raises(ForeignKeyViolation):
        backend.supersede_memory("a1", "missing")

    assert any(
        statement.startswith("UPDATE memories SET superseded_by")
        for statement in _write_statements(conn)
    )


@pytest.mark.l4("C-ce6c1aac", "C-8d3fb08f")
def test_pg_add_memory_superseded_by_requires_the_same_tenant() -> None:
    conn = FakeConnection(responder=_responder({"g1": "global"}))
    backend = _backend(conn)
    record = MemoryRecord(
        content="new tenant fact",
        category=MemoryCategory.FACT,
        tenant_id="t1",
        superseded_by="g1",
    )

    with pytest.raises(CrossTenantLinkError) as raised:
        backend.add_memory(record)

    assert (
        raised.value.first_id,
        raised.value.first_tenant,
        raised.value.second_id,
        raised.value.second_tenant,
    ) == (record.id, "t1", "g1", "global")
    assert _write_statements(conn) == []


@pytest.mark.l4("C-ce6c1aac")
def test_pg_add_memory_missing_superseded_by_keeps_the_foreign_key_error() -> None:
    conn = FakeConnection(responder=_responder({}, fail_on="INSERT INTO memories"))
    backend = _backend(conn)
    record = MemoryRecord(
        content="new tenant fact",
        category=MemoryCategory.FACT,
        tenant_id="t1",
        superseded_by="missing",
    )

    with pytest.raises(ForeignKeyViolation):
        backend.add_memory(record)

    assert any(
        statement.startswith("INSERT INTO memories") for statement in _write_statements(conn)
    )


@pytest.mark.l4("C-ce6c1aac", "C-8d3fb08f")
def test_pg_update_memory_superseded_by_requires_the_same_tenant() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1", "g1": "global"}))
    backend = _backend(conn)

    with pytest.raises(CrossTenantLinkError) as raised:
        backend.update_memory("a1", superseded_by="g1")

    assert (
        raised.value.first_id,
        raised.value.first_tenant,
        raised.value.second_id,
        raised.value.second_tenant,
    ) == ("a1", "t1", "g1", "global")
    assert _write_statements(conn) == []


@pytest.mark.l4("C-ce6c1aac")
def test_pg_update_memory_missing_superseded_by_keeps_the_foreign_key_error() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1"}, fail_on="UPDATE memories SET"))
    backend = _backend(conn)

    with pytest.raises(ForeignKeyViolation):
        backend.update_memory("a1", superseded_by="missing")

    assert any(statement.startswith("UPDATE memories SET") for statement in _write_statements(conn))


@pytest.mark.l4("C-ce6c1aac")
def test_pg_update_memory_keeps_tenant_id_immutable() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1"}))
    backend = _backend(conn)

    with pytest.raises(TenantImmutableError) as raised:
        backend.update_memory("a1", tenant_id="global")

    assert (
        raised.value.memory_id,
        raised.value.stored_tenant,
        raised.value.requested_tenant,
    ) == ("a1", "t1", "global")
    assert _write_statements(conn) == []

    with pytest.raises(KeyError) as missing:
        backend.update_memory("missing", tenant_id="global")
    assert missing.value.args[0] == "memory 'missing' not found"


# ---------------------------------------------------------------------------
# Requirement 3.2 + 5.2/5.7 — id-only writes and their KeyError
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-f3e0c70c")
def test_pg_archive_memory_without_tenant_acts_by_id() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1"}))
    backend = _backend(conn)

    backend.archive_memory("a1")

    assert any(
        statement.startswith("UPDATE memories SET is_archived")
        for statement in _write_statements(conn)
    )

    backend.archive_memory("missing")

    archived = [
        statement
        for statement in _write_statements(conn)
        if statement.startswith("UPDATE memories SET is_archived")
    ]
    assert len(archived) == 1, "a missing id stays a no-op, as on SQLite"


@pytest.mark.l4("C-f3e0c70c", "C-8d3fb08f")
def test_pg_archive_memory_foreign_tenant_raises_key_error() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1"}))
    backend = _backend(conn)

    with pytest.raises(KeyError) as raised:
        backend.archive_memory("a1", tenant_id="global")

    assert raised.value.args[0] == "memory 'a1' not found"
    assert _write_statements(conn) == []


@pytest.mark.l4("C-f3e0c70c")
def test_pg_supersede_memory_without_tenant_acts_by_id() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1", "a2": "t1"}))
    backend = _backend(conn)

    backend.supersede_memory("a1", "a2")

    assert any(
        statement.startswith("UPDATE memories SET superseded_by")
        for statement in _write_statements(conn)
    )


@pytest.mark.l4("C-f3e0c70c", "C-3f98f2b5")
def test_pg_supersede_memory_concrete_tenant_requires_both_rows() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1", "a2": "t1", "g1": "global"}))
    backend = _backend(conn)

    with pytest.raises(KeyError) as foreign_by_id:
        backend.supersede_memory("a1", "g1", tenant_id="t1")
    assert foreign_by_id.value.args[0] == "memory 'g1' not found"

    with pytest.raises(KeyError) as foreign_memory:
        backend.supersede_memory("a1", "a2", tenant_id="global")
    assert foreign_memory.value.args[0] == "memory 'a1' not found"

    assert _write_statements(conn) == []

    backend.supersede_memory("a1", "a2", tenant_id="t1")
    assert any(
        statement.startswith("UPDATE memories SET superseded_by")
        for statement in _write_statements(conn)
    )


@pytest.mark.l4("C-f3e0c70c")
def test_pg_apply_feedback_without_tenant_acts_by_id() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1"}))
    backend = _backend(conn)

    backend.apply_feedback("a1", useful=True, stale=False)

    assert any(statement.startswith("UPDATE memories SET") for statement in _write_statements(conn))
    assert conn.commits == 1

    with pytest.raises(KeyError) as missing:
        backend.apply_feedback("missing", useful=True, stale=False)
    assert missing.value.args[0] == "memory 'missing' not found"


@pytest.mark.l4("C-f3e0c70c")
def test_pg_apply_feedback_foreign_tenant_raises_key_error() -> None:
    conn = FakeConnection(responder=_responder({"a1": "t1"}))
    backend = _backend(conn)

    with pytest.raises(KeyError) as raised:
        backend.apply_feedback("a1", useful=True, stale=False, tenant_id="global")

    assert raised.value.args[0] == "memory 'a1' not found"
    assert _write_statements(conn) == []
