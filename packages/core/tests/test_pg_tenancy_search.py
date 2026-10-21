"""RED tests for task 2 — Postgres search runs the pipeline with the tenant.

They trace requirement 2.1 (``search`` passes the tenant to its three phases
and to the ``load_memories_fn``, ``search_around_fn`` and
``get_annotating_notes_fn`` callables, looks the tenant up for a concrete id
only, and gives ``fuse_and_search`` the ``tenant_id`` and
``record_session = tenant_id is None or (t is not None and t.is_active)`` it
does on SQLite) and 2.2 (the fake-pool story over ``SearchRequest(query=
"Alice")``: an active ``t1`` records a session stamped with ``t1``, an
inactive or unknown tenant records nothing and still runs the reads).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import numpy as np
import pytest
from mintmory.core.embedder import HashingEmbedder
from mintmory.core.storage_postgres import PostgresBackend
from mintmory.core.types import SearchAroundSpec, SearchRequest

from packages.core.tests.pg_fakes import FakeConnection, FakePool

_TENANT = "t1"
_POOL = 50  # max(SearchRequest().limit * 5, 50)


def _memory_row(memory_id: str, tenant_id: str) -> dict[str, Any]:
    stamp = datetime(2026, 1, 1)
    return {
        "id": memory_id,
        "content": f"{memory_id} mentions Alice",
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


def _tenant_row(is_active: bool) -> dict[str, Any]:
    stamp = datetime(2026, 1, 1)
    return {
        "id": _TENANT,
        "name": "",
        "is_active": is_active,
        "created_at": stamp,
        "updated_at": stamp,
    }


def _search_responder(
    tenant_state: str, stored_tenant: str = _TENANT
) -> Callable[[str, Any], list[Any]]:
    """Answer the search story: FTS candidate ``a1``, most other statements empty.

    ``tenant_state``: "active" (directory row with ``is_active`` true), "inactive"
    (directory row with ``is_active`` false) or "none" (no directory row).
    ``stored_tenant`` answers the stored-tenant lookups of ``record_query_results``.
    """

    def respond(sql: str, params: Any) -> list[Any]:
        normalised = " ".join(sql.split())
        if "ts_rank(content_tsv" in normalised:
            return [("a1", 0.5)]
        if ("word_similarity(" in normalised) or ("embedding <=> %s" in normalised):
            return []
        if normalised.startswith("SELECT id, content"):
            return [_memory_row("a1", _TENANT)]
        if normalised.startswith("SELECT m.id, m.content"):
            return []
        if normalised.startswith("SELECT source_memory_id, target_memory_id"):
            return []
        if normalised.startswith("SELECT id, name, is_active"):
            if tenant_state == "none":
                return []
            return [_tenant_row(tenant_state == "active")]
        if normalised.startswith("SELECT is_active FROM tenants"):
            return [{"is_active": True}]
        if normalised.startswith("SELECT tenant_id FROM"):
            return [{"tenant_id": stored_tenant}]
        return []

    return respond


def _backend(
    tenant_state: str, stored_tenant: str = _TENANT
) -> tuple[PostgresBackend, FakeConnection]:
    conn = FakeConnection(responder=_search_responder(tenant_state, stored_tenant))
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)
    return backend, conn


def _statements(conn: FakeConnection) -> list[tuple[str, tuple[Any, ...]]]:
    return [
        (" ".join(sql.split()), () if params is None else tuple(params))
        for sql, params in conn.executed
    ]


def _no_writes(statements: list[tuple[str, tuple[Any, ...]]], label: str) -> None:
    prefixes = (
        "INSERT INTO query_sessions",
        "INSERT INTO query_results",
        "UPDATE query_results",
        "UPDATE memories SET retrieval_count",
    )
    assert not any(sql.lstrip().startswith(prefixes) for sql, _params in statements), (
        f"{label} wrote a session, a result or a retrieval counter"
    )


def _session_inserts(statements: list[tuple[str, tuple[Any, ...]]]) -> list[tuple[Any, ...]]:
    return [
        params
        for sql, params in statements
        if sql.lstrip().startswith("INSERT INTO query_sessions")
    ]


# ---------------------------------------------------------------------------
# Requirement 2.1 — the tenant reaches every phase and callable
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-f2076555")
def test_pg_search_passes_tenant_to_phases_and_callables() -> None:
    backend, conn = _backend("active")
    backend._trgm_available = True
    backend.embedder = HashingEmbedder(dim=8)
    backend._vec_available = True
    embedding = np.zeros(8, dtype=np.float32)
    request = SearchRequest(query="Alice", search_around=SearchAroundSpec())

    response = backend.search(request, embedding, tenant_id=_TENANT)

    statements = _statements(conn)
    fts = [(sql, params) for sql, params in statements if "ts_rank(content_tsv" in sql]
    assert fts
    for sql, params in fts:
        assert "AND tenant_id = %s ORDER BY rank DESC LIMIT %s" in sql, sql
        assert params == ("alice:*", "alice:*", _TENANT, _POOL), params
    trigram = [(sql, params) for sql, params in statements if "word_similarity(" in sql]
    assert trigram
    for sql, params in trigram:
        assert ") AND tenant_id = %s" in sql, sql
        assert params == ("alice", "alice", "alice", "alice", _TENANT, _POOL), params
    vector = [(sql, params) for sql, params in statements if "embedding <=> %s" in sql]
    assert vector
    for sql, params in vector:
        assert "AND vector_dims(embedding) = %s AND tenant_id = %s ORDER BY" in sql, sql
        np.testing.assert_array_equal(params[0], embedding)
        assert params[1:] == (8, _TENANT, _POOL), params
    loads = [(sql, params) for sql, params in statements if sql.startswith("SELECT id, content")]
    assert loads
    for sql, params in loads:
        assert "WHERE id IN (%s) AND tenant_id = %s" in sql, sql
        assert params == ("a1", _TENANT), params
    arounds = [
        (sql, params)
        for sql, params in statements
        if sql.startswith("SELECT source_memory_id, target_memory_id")
    ]
    assert arounds
    for sql, params in arounds:
        assert "FROM concept_links" in sql and "AND tenant_id = %s" in sql, sql
        assert params == (0.0, "a1", "a1", _TENANT), params
    notes = [
        (sql, params) for sql, params in statements if sql.startswith("SELECT m.id, m.content")
    ]
    assert notes
    for sql, params in notes:
        assert "AND m.tenant_id = %s" in sql, sql
        cap = backend._resolve_auto_include_cap()
        assert params == ("a1", "annotates", _TENANT, cap), params

    assert [mem.id for mem in response.memories] == ["a1"]
    sessions = _session_inserts(statements)
    assert sessions
    assert _TENANT in sessions[-1], sessions[-1]
    assert response.session_id == sessions[-1][0]


@pytest.mark.l4("C-f2076555")
def test_pg_search_without_tenant_records_a_global_unscoped_session() -> None:
    backend, conn = _backend("active", "global")

    response = backend.search(SearchRequest(query="Alice"))

    statements = _statements(conn)
    sessions = _session_inserts(statements)
    assert sessions
    assert "global" in sessions[-1], sessions[-1]
    assert response.session_id == sessions[-1][0]
    assert response.session_id != ""
    for sql, _params in statements:
        assert "tenant_id =" not in sql, sql


# ---------------------------------------------------------------------------
# Requirement 2.2 — an active tenant records, a dead tenant writes nothing
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-eeb31841")
def test_pg_search_active_tenant_records_session_and_results() -> None:
    backend, conn = _backend("active")

    response = backend.search(SearchRequest(query="Alice"), tenant_id=_TENANT)

    statements = _statements(conn)
    assert any("ts_rank(content_tsv" in sql for sql, _params in statements)
    assert any(sql.startswith("SELECT id, content") for sql, _params in statements)
    assert any(sql.lstrip().startswith("INSERT INTO query_results") for sql, _params in statements)
    assert any(
        sql.lstrip().startswith("UPDATE memories SET retrieval_count")
        for sql, _params in statements
    )
    sessions = _session_inserts(statements)
    assert len(sessions) == 1, sessions
    inserted = sessions[0]
    assert _TENANT in inserted, inserted
    assert "Alice" in inserted, inserted
    assert inserted[0] != "", inserted
    assert [mem.id for mem in response.memories] == ["a1"]
    assert response.session_id == inserted[0]


@pytest.mark.l4("C-eeb31841", "C-f2076555")
def test_pg_search_inactive_tenant_returns_results_without_recording() -> None:
    backend, conn = _backend("inactive")

    response = backend.search(SearchRequest(query="Alice"), tenant_id=_TENANT)

    statements = _statements(conn)
    assert any("ts_rank(content_tsv" in sql for sql, _params in statements)
    loads = [(sql, params) for sql, params in statements if sql.startswith("SELECT id, content")]
    assert loads
    for sql, params in loads:
        assert "tenant_id = %s" in sql, sql
        assert params == ("a1", _TENANT), params
    _no_writes(statements, "an inactive tenant")
    assert [mem.id for mem in response.memories] == ["a1"]
    assert response.session_id == ""


@pytest.mark.l4("C-eeb31841")
def test_pg_search_unknown_tenant_records_nothing() -> None:
    backend, conn = _backend("none")

    response = backend.search(SearchRequest(query="Alice"), tenant_id="nope")

    statements = _statements(conn)
    _no_writes(statements, "an unknown tenant")
    assert response.session_id == ""
    assert response.memories == []
