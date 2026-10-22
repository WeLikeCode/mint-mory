"""Tests for task 3 — Postgres ``list_memories`` is tenant-aware.

They trace requirement 3.1 (``list_memories(filter=None, *, tenant_id=None,
limit=None)`` runs the ``_SELECT_MEMORY`` query over non-archived rows with the
tenant predicate when concrete, applies ``_passes_filter`` in Python and then
the limit: ``None`` all, ``0`` none, negative ``ValueError``) and requirement
3.2 (the fake-pool story: the exact SQL and parameter for ``t1``, the ``None``
call without a tenant predicate, the negative-limit error before any statement,
and the filtered/limited rows of ``multi-tenancy-reads`` R4.2).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from mintmory.core.storage_postgres import PostgresBackend
from mintmory.core.types import MemoryFilter

from packages.core.tests.pg_fakes import FakeConnection, FakePool

_TENANT = "t1"


def _memory_row(
    memory_id: str,
    tenant_id: str,
    *,
    content: str,
    created_at: datetime,
    is_stale: bool = False,
    is_archived: bool = False,
    is_active: bool = True,
) -> dict[str, Any]:
    stamp = datetime(2026, 1, 1)
    return {
        "id": memory_id,
        "content": content,
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
        "is_stale": is_stale,
        "is_active": is_active,
        "is_archived": is_archived,
        "superseded_by": None,
        "flagged_for_review": False,
        "contradicts_ids": [],
        "is_note": False,
        "created_at": created_at,
        "updated_at": stamp,
        "last_accessed_at": None,
        "metadata": {},
        "tenant_id": tenant_id,
    }


def _backend(rows: list[dict[str, Any]]) -> tuple[PostgresBackend, FakeConnection]:
    conn = FakeConnection(responder=lambda _sql, _params: list(rows))
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)
    return backend, conn


def _statements(conn: FakeConnection) -> list[tuple[str, tuple[Any, ...]]]:
    return [
        (" ".join(sql.split()), () if params is None else tuple(params))
        for sql, params in conn.executed
    ]


# ---------------------------------------------------------------------------
# Requirement 3.1 / 3.2 — the exact SELECT and its tenant parameter
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-66dbed8a", "C-badf241c")
def test_pg_list_memories_builds_exact_tenant_scoped_select() -> None:
    row = _memory_row(
        "a1",
        _TENANT,
        content="t1 active fact",
        created_at=datetime(2026, 1, 1),
    )
    backend, conn = _backend([row])

    records = backend.list_memories(tenant_id=_TENANT)

    assert [mem.id for mem in records] == ["a1"]
    assert _statements(conn) == [
        (
            "SELECT id, content, category, entity_ids, confidence, source, verified, "
            "valid_from, valid_until, usefulness_score, staleness_score, "
            "reinforcement_count, retrieval_count, is_stale, is_active, is_archived, "
            "superseded_by, flagged_for_review, contradicts_ids, is_note, "
            "created_at, updated_at, last_accessed_at, metadata, tenant_id "
            "FROM memories WHERE is_archived = FALSE AND tenant_id = %s "
            "ORDER BY created_at, id",
            (_TENANT,),
        )
    ]

    conn.executed.clear()
    unscoped = backend.list_memories()

    assert [mem.id for mem in unscoped] == ["a1"]
    assert _statements(conn) == [
        (
            "SELECT id, content, category, entity_ids, confidence, source, verified, "
            "valid_from, valid_until, usefulness_score, staleness_score, "
            "reinforcement_count, retrieval_count, is_stale, is_active, is_archived, "
            "superseded_by, flagged_for_review, contradicts_ids, is_note, "
            "created_at, updated_at, last_accessed_at, metadata, tenant_id "
            "FROM memories WHERE is_archived = FALSE "
            "ORDER BY created_at, id",
            (),
        )
    ]


# ---------------------------------------------------------------------------
# Requirement 3.1 / 3.2 — the negative limit fails before touching the pool
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-66dbed8a", "C-badf241c")
def test_pg_list_memories_negative_limit_raises_before_any_statement() -> None:
    backend, conn = _backend([])

    with pytest.raises(ValueError, match="limit must be >= 0"):
        backend.list_memories(tenant_id=_TENANT, limit=-1)

    assert conn.executed == []


# ---------------------------------------------------------------------------
# Requirement 3.1 / 3.2 — _passes_filter runs before the limit (R4.2 rows)
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-66dbed8a", "C-badf241c")
def test_pg_list_memories_filters_then_limits_the_rows() -> None:
    t_active = _memory_row(
        "t-active",
        _TENANT,
        content="t1 active fact",
        created_at=datetime(2026, 1, 1),
    )
    t_stale = _memory_row(
        "t-stale",
        _TENANT,
        content="t1 stale fact",
        created_at=datetime(2026, 1, 2),
        is_stale=True,
    )
    t_archived = _memory_row(
        "t-archived",
        _TENANT,
        content="t1 archived fact",
        created_at=datetime(2026, 1, 3),
        is_archived=True,
    )
    t_inactive = _memory_row(
        "t-inactive",
        _TENANT,
        content="t1 inactive fact",
        created_at=datetime(2026, 1, 4),
        is_active=False,
    )
    g1 = _memory_row(
        "g1",
        "global",
        content="global active fact one",
        created_at=datetime(2026, 1, 5),
    )
    g2 = _memory_row(
        "g2",
        "global",
        content="global active fact two",
        created_at=datetime(2026, 1, 6),
    )

    def responder(_sql: str, params: Any) -> list[dict[str, Any]]:
        scoped_rows = [t_active, t_stale, t_archived, t_inactive]
        if params is not None and _TENANT in params:
            return list(scoped_rows)
        return [*scoped_rows, g1, g2]

    conn = FakeConnection(responder=responder)
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)

    scoped = backend.list_memories(tenant_id=_TENANT)
    assert [mem.id for mem in scoped] == ["t-active"]

    keep_stale = backend.list_memories(MemoryFilter(exclude_stale=False), tenant_id=_TENANT)
    assert [mem.id for mem in keep_stale] == ["t-active", "t-stale"]

    keep_stale_one = backend.list_memories(
        MemoryFilter(exclude_stale=False), tenant_id=_TENANT, limit=1
    )
    assert [mem.id for mem in keep_stale_one] == ["t-active"]

    assert backend.list_memories(tenant_id=_TENANT, limit=0) == []

    all_matching = backend.list_memories(tenant_id=_TENANT, limit=None)
    assert [mem.id for mem in all_matching] == ["t-active"]

    unscoped = backend.list_memories()
    assert [mem.id for mem in unscoped] == ["t-active", "g1", "g2"]

    unscoped_oldest = backend.list_memories(limit=1)
    assert [mem.id for mem in unscoped_oldest] == ["t-active"]
