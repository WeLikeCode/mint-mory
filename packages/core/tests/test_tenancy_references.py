"""RED tests for task 3 — same-tenant references (requirement 2).

They trace requirement 2.1 (``add_link`` compares the stored tenants of both
endpoints and the link's own tenant; a missing endpoint keeps the foreign-key
``IntegrityError`` and runs no tenant check), 2.2 (``record_query_results``
compares each result with its session and memory, lets a ``global`` session
reference any tenant and validates the whole batch before the first insert),
2.3 (``supersede_memory`` rejects a cross-tenant ``by_id`` and keeps the FK
error for a missing one), 2.4 (``add_memory``/``update_memory`` with
``superseded_by`` require the target in the same tenant), 2.5 (``update_memory``
never moves a row to another tenant and keeps ``KeyError`` for a missing row),
2.6 (soft references are not checked by storage) and 2.7 (every example of the
requirement).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    CrossTenantLinkError,
    MemoryCategory,
    MemoryRecord,
    QueryResult,
    QuerySession,
    TenantImmutableError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raised(call: Callable[[], object]) -> BaseException | None:
    """Run ``call`` and return whatever it raised (``None`` when it succeeded)."""
    try:
        call()
    except BaseException as exc:
        return exc
    return None


def _assert_cross_tenant(
    exc: BaseException | None,
    first_id: str,
    first_tenant: str,
    second_id: str,
    second_tenant: str,
) -> None:
    assert isinstance(exc, CrossTenantLinkError), f"expected CrossTenantLinkError, got {exc!r}"
    assert (exc.first_id, exc.first_tenant, exc.second_id, exc.second_tenant) == (
        first_id,
        first_tenant,
        second_id,
        second_tenant,
    )


def _assert_immutable(
    exc: BaseException | None,
    memory_id: str,
    stored_tenant: str,
    requested_tenant: str,
) -> None:
    assert isinstance(exc, TenantImmutableError), f"expected TenantImmutableError, got {exc!r}"
    assert (exc.memory_id, exc.stored_tenant, exc.requested_tenant) == (
        memory_id,
        stored_tenant,
        requested_tenant,
    )


def _create_tenant(store: SqliteBackend, tenant_id: str) -> None:
    store.create_tenant(tenant_id)


def _memory(store: SqliteBackend, content: str, tenant_id: str = "global") -> MemoryRecord:
    return store.add_memory(
        MemoryRecord(content=content, category=MemoryCategory.FACT, tenant_id=tenant_id)
    )


def _session(store: SqliteBackend, tenant_id: str) -> QuerySession:
    session = QuerySession(query_text="who is Alice?", tenant_id=tenant_id)
    store.create_session(session)
    return session


def _link_count(store: SqliteBackend) -> int:
    row = store.connect().execute("SELECT COUNT(*) FROM concept_links").fetchone()
    assert row is not None
    return int(row[0])


def _result_count(store: SqliteBackend, session_id: str) -> int:
    row = (
        store.connect()
        .execute("SELECT COUNT(*) FROM query_results WHERE session_id = ?", (session_id,))
        .fetchone()
    )
    assert row is not None
    return int(row[0])


def _stored_tenant(store: SqliteBackend, memory_id: str) -> str:
    row = (
        store.connect()
        .execute("SELECT tenant_id FROM memories WHERE id = ?", (memory_id,))
        .fetchone()
    )
    assert row is not None
    return str(row["tenant_id"])


# ---------------------------------------------------------------------------
# Requirement 2.1 + 2.7 — add_link compares endpoint and link tenants
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-4389e90a", "C-86e4552e")
def test_add_link_cross_tenant_endpoints(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    g1 = _memory(store, "global memory")
    a1 = _memory(store, "tenant memory", "t1")

    # A missing endpoint keeps the FK error and must suppress the tenant check.
    missing = _raised(
        lambda: store.add_link(
            ConceptLink(
                source_memory_id=a1.id,
                target_memory_id="missing-memory",
                link_type=ConceptLinkType.RELATES_TO,
                tenant_id="global",
            )
        )
    )
    assert isinstance(missing, sqlite3.IntegrityError)
    assert _link_count(store) == 0

    forward = _raised(
        lambda: store.add_link(
            ConceptLink(
                source_memory_id=g1.id,
                target_memory_id=a1.id,
                link_type=ConceptLinkType.RELATES_TO,
            )
        )
    )
    _assert_cross_tenant(forward, g1.id, "global", a1.id, "t1")
    assert _link_count(store) == 0

    reverse = _raised(
        lambda: store.add_link(
            ConceptLink(
                source_memory_id=a1.id,
                target_memory_id=g1.id,
                link_type=ConceptLinkType.RELATES_TO,
                tenant_id="t1",
            )
        )
    )
    _assert_cross_tenant(reverse, a1.id, "t1", g1.id, "global")
    assert _link_count(store) == 0


@pytest.mark.l4("C-4389e90a", "C-86e4552e")
def test_add_link_link_tenant_must_match_its_endpoints(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    a1 = _memory(store, "first tenant memory", "t1")
    a2 = _memory(store, "second tenant memory", "t1")

    store.add_link(
        ConceptLink(
            source_memory_id=a1.id,
            target_memory_id=a2.id,
            link_type=ConceptLinkType.RELATES_TO,
            tenant_id="t1",
        )
    )
    assert _link_count(store) == 1

    mismatch = _raised(
        lambda: store.add_link(
            ConceptLink(
                source_memory_id=a1.id,
                target_memory_id=a2.id,
                link_type=ConceptLinkType.RELATES_TO,
            )
        )
    )
    _assert_cross_tenant(mismatch, a1.id, "t1", a2.id, "global")
    assert _link_count(store) == 1


# ---------------------------------------------------------------------------
# Requirement 2.2 + 2.7 — record_query_results session/memory rules
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-056266db", "C-86e4552e")
def test_record_query_results_cross_tenant_rules(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    g1 = _memory(store, "global memory")
    a1 = _memory(store, "tenant memory", "t1")
    global_session = _session(store, "global")
    tenant_session = _session(store, "t1")

    # A global session may reference a tenant's memory (read-audit record).
    allowed = QueryResult(
        session_id=global_session.id,
        memory_id=a1.id,
        relevance_score=1.0,
    )
    assert _raised(lambda: store.record_query_results([allowed])) is None
    assert _result_count(store, global_session.id) == 1

    # A t1 session recording a global memory under the result tenant t1.
    first_clause = _raised(
        lambda: store.record_query_results(
            [
                QueryResult(
                    session_id=tenant_session.id,
                    memory_id=g1.id,
                    relevance_score=1.0,
                    tenant_id="t1",
                )
            ]
        )
    )
    _assert_cross_tenant(first_clause, tenant_session.id, "t1", g1.id, "global")

    # Same result with the default (global) result tenant: first clause.
    default_tenant = _raised(
        lambda: store.record_query_results(
            [
                QueryResult(
                    session_id=tenant_session.id,
                    memory_id=g1.id,
                    relevance_score=1.0,
                )
            ]
        )
    )
    _assert_cross_tenant(default_tenant, tenant_session.id, "t1", g1.id, "global")

    # A t1 session recording a t1 memory but with the default result tenant.
    default_result_tenant = _raised(
        lambda: store.record_query_results(
            [
                QueryResult(
                    session_id=tenant_session.id,
                    memory_id=a1.id,
                    relevance_score=1.0,
                )
            ]
        )
    )
    _assert_cross_tenant(default_result_tenant, tenant_session.id, "t1", a1.id, "global")
    assert _result_count(store, tenant_session.id) == 0


@pytest.mark.l4("C-056266db")
def test_record_query_results_validates_the_batch_before_inserting(
    store: SqliteBackend,
) -> None:
    _create_tenant(store, "t1")
    g1 = _memory(store, "global memory")
    a1 = _memory(store, "first tenant memory", "t1")
    a2 = _memory(store, "second tenant memory", "t1")
    tenant_session = _session(store, "t1")

    # A missing session or memory keeps the FK error and runs no tenant check.
    missing_session = _raised(
        lambda: store.record_query_results(
            [
                QueryResult(
                    session_id="missing-session",
                    memory_id=a1.id,
                    relevance_score=1.0,
                    tenant_id="global",
                )
            ]
        )
    )
    assert isinstance(missing_session, sqlite3.IntegrityError)
    assert _result_count(store, tenant_session.id) == 0

    missing_memory = _raised(
        lambda: store.record_query_results(
            [
                QueryResult(
                    session_id=tenant_session.id,
                    memory_id="missing-memory",
                    relevance_score=1.0,
                    tenant_id="global",
                )
            ]
        )
    )
    assert isinstance(missing_memory, sqlite3.IntegrityError)
    assert _result_count(store, tenant_session.id) == 0

    # The whole batch is validated before the first INSERT, not row by row.
    valid = QueryResult(
        session_id=tenant_session.id,
        memory_id=a1.id,
        relevance_score=1.0,
        tenant_id="t1",
    )
    invalid = QueryResult(
        session_id=tenant_session.id,
        memory_id=g1.id,
        relevance_score=1.0,
        tenant_id="t1",
    )
    batch = _raised(lambda: store.record_query_results([valid, invalid]))
    _assert_cross_tenant(batch, tenant_session.id, "t1", g1.id, "global")
    assert _result_count(store, tenant_session.id) == 0

    # The same batch with the second result pointing at another t1 memory is
    # valid, which proves the zero above came from the rejected batch.
    assert (
        _raised(
            lambda: store.record_query_results(
                [
                    valid,
                    QueryResult(
                        session_id=tenant_session.id,
                        memory_id=a2.id,
                        relevance_score=0.5,
                        tenant_id="t1",
                    ),
                ]
            )
        )
        is None
    )
    assert _result_count(store, tenant_session.id) == 2


# ---------------------------------------------------------------------------
# Requirement 2.3 + 2.7 — supersede_memory
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-4789c501", "C-86e4552e")
def test_supersede_memory_requires_the_same_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    a1 = _memory(store, "tenant memory", "t1")
    g1 = _memory(store, "global memory")

    # A missing by_id keeps today's FK behaviour.
    missing = _raised(lambda: store.supersede_memory(a1.id, "missing-memory"))
    assert isinstance(missing, sqlite3.IntegrityError)
    untouched = store.get_memory(a1.id)
    assert untouched is not None
    assert untouched.is_active is True
    assert untouched.superseded_by is None

    cross = _raised(lambda: store.supersede_memory(a1.id, g1.id))
    _assert_cross_tenant(cross, a1.id, "t1", g1.id, "global")
    stored = store.get_memory(a1.id)
    assert stored is not None
    assert stored.is_active is True
    assert stored.is_archived is False
    assert stored.superseded_by is None


# ---------------------------------------------------------------------------
# Requirement 2.4 + 2.7 — superseded_by on add_memory / update_memory
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-24b01ee5")
def test_add_memory_superseded_by_requires_the_same_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    g1 = _memory(store, "global memory")

    # A missing target keeps the FK error and writes nothing.
    missing_record = MemoryRecord(
        content="new tenant memory",
        category=MemoryCategory.FACT,
        superseded_by="missing-memory",
    )
    missing = _raised(lambda: store.add_memory(missing_record))
    assert isinstance(missing, sqlite3.IntegrityError)
    assert store.get_memory(missing_record.id) is None

    record = MemoryRecord(
        content="new tenant memory",
        category=MemoryCategory.FACT,
        tenant_id="t1",
        superseded_by=g1.id,
    )
    cross = _raised(lambda: store.add_memory(record))
    _assert_cross_tenant(cross, record.id, "t1", g1.id, "global")
    assert store.get_memory(record.id) is None


@pytest.mark.l4("C-24b01ee5", "C-86e4552e")
def test_update_memory_superseded_by_requires_the_same_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    a1 = _memory(store, "tenant memory", "t1")
    g1 = _memory(store, "global memory")

    # A missing target keeps the FK error and leaves the row untouched.
    missing = _raised(lambda: store.update_memory(a1.id, superseded_by="missing-memory"))
    assert isinstance(missing, sqlite3.IntegrityError)
    untouched = store.get_memory(a1.id)
    assert untouched is not None
    assert untouched.superseded_by is None

    cross = _raised(lambda: store.update_memory(a1.id, superseded_by=g1.id))
    _assert_cross_tenant(cross, a1.id, "t1", g1.id, "global")
    stored = store.get_memory(a1.id)
    assert stored is not None
    assert stored.superseded_by is None


# ---------------------------------------------------------------------------
# Requirement 2.5 + 2.7 — tenant_id is immutable through update_memory
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-bcdf64ef", "C-86e4552e")
def test_update_memory_rejects_a_tenant_change(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    a1 = _memory(store, "tenant memory", "t1")

    # A missing row still fails with KeyError before any tenant comparison.
    missing = _raised(lambda: store.update_memory("missing-memory", tenant_id="global"))
    assert isinstance(missing, KeyError)
    assert missing.args[0] == "memory 'missing-memory' not found"

    # The stored tenant itself is accepted and the column never moves.
    same = store.update_memory(a1.id, tenant_id="t1", content="same tenant update")
    assert same.tenant_id == "t1"
    assert _stored_tenant(store, a1.id) == "t1"

    cross = _raised(lambda: store.update_memory(a1.id, tenant_id="global"))
    _assert_immutable(cross, a1.id, "t1", "global")
    assert _stored_tenant(store, a1.id) == "t1"

    # An invalid id is compared as an opaque string, not validated.
    invalid = _raised(lambda: store.update_memory(a1.id, tenant_id="Not Valid!"))
    _assert_immutable(invalid, a1.id, "t1", "Not Valid!")
    assert _stored_tenant(store, a1.id) == "t1"


# ---------------------------------------------------------------------------
# Requirement 2.6 — soft references are left to their consumers
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-561f5d0e")
def test_soft_references_are_not_checked_by_storage(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    g1 = _memory(store, "global memory")
    a1 = _memory(store, "tenant memory", "t1")

    soft = MemoryRecord(
        content="tenant memory with soft references",
        category=MemoryCategory.FACT,
        tenant_id="t1",
        entity_ids=[g1.id],
        contradicts_ids=[g1.id],
        metadata={"related": g1.id},
    )
    store.add_memory(soft)

    updated = store.update_memory(
        a1.id,
        entity_ids=[g1.id],
        contradicts_ids=[g1.id],
        metadata={"related": g1.id},
    )
    assert updated.entity_ids == [g1.id]
    assert updated.contradicts_ids == [g1.id]
    assert updated.metadata == {"related": g1.id}

    session = QuerySession(
        query_text="soft references",
        tenant_id="t1",
        useful_ids=[g1.id],
        stale_ids=[g1.id],
    )
    store.create_session(session)
    store.update_session_feedback(session.id, 5, "reason", [g1.id], [g1.id])
    fetched = store.get_session(session.id)
    assert fetched is not None
    assert fetched.useful_ids == [g1.id]
    assert fetched.stale_ids == [g1.id]

    # A hard reference is still checked, which contrasts with the soft ones.
    hard = _raised(lambda: store.update_memory(a1.id, superseded_by=g1.id))
    _assert_cross_tenant(hard, a1.id, "t1", g1.id, "global")


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> SqliteBackend:
    backend = SqliteBackend(tmp_path / "mintmory.db")
    backend.initialise()
    return backend
