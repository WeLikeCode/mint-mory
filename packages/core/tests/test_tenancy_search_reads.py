"""RED tests for task 3 — scoped search, traversal and anchoring.

They trace requirement 2.1 (the ``tenant_id = ?`` predicate goes into the SQL of
``_fts_scores``, ``_trigram_scores``, ``_vector_scores``, ``_load_memories`` and
each ``search_around`` hop, and those methods gain the trailing optional
``tenant_id`` parameter), 3.1 (``search`` binds the tenant into every phase and
the callables it hands to ``fuse_and_search``), 3.2 (``fuse_and_search`` gains
``tenant_id`` and ``record_session``, stamps the session tenant and drops
foreign rows as defense in depth), 3.3 (``record_session=False`` writes
nothing and returns ``session_id=""``), 3.4 (a search confined to an inactive
or missing tenant reads without writing), 3.5 (an unscoped search records a
``global`` session and bumps retrieval only for active tenants' rows), 3.6
(the search examples over the shared ``Alice`` corpus), 3.7 (a foreign anchor
contributes nothing for another tenant) and 3.8 (``anchor_candidates`` stays
side-effect free for every tenant).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from mintmory.core.hybrid_search import fuse_and_search
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    MemoryCategory,
    MemoryRecord,
    QuerySession,
    SearchAroundSpec,
    SearchRequest,
)


@dataclass
class Seed:
    store: SqliteBackend
    g1: MemoryRecord
    g2: MemoryRecord
    a1: MemoryRecord
    a2: MemoryRecord


def _memory(store: SqliteBackend, content: str, tenant_id: str) -> MemoryRecord:
    return store.add_memory(
        MemoryRecord(content=content, category=MemoryCategory.FACT, tenant_id=tenant_id)
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
def alice(tmp_path: Path) -> Seed:
    """Global and ``t1`` tenants; only g1 (global) and a1 (t1) mention Alice.

    g1→g2 is a ``global`` link and a1→a2 is a ``t1`` link, so the foreign anchor
    scenario of R3.7 has a same-tenant hop to follow next to a foreign one.
    """
    store = SqliteBackend(tmp_path / "mintmory.db")
    store.initialise()
    store.create_tenant("t1")

    g1 = _memory(store, "Alice uses Postgres", "global")
    g2 = _memory(store, "Bob uses MySQL", "global")
    a1 = _memory(store, "Alice uses SQLite", "t1")
    a2 = _memory(store, "Carol uses Redis", "t1")

    _relates(store, g1.id, g2.id, "global")
    _relates(store, a1.id, a2.id, "t1")

    store.create_session(QuerySession(query_text="global seed query"))
    store.create_session(QuerySession(query_text="t1 seed query", tenant_id="t1"))

    return Seed(store=store, g1=g1, g2=g2, a1=a1, a2=a2)


def _scalar(store: SqliteBackend, sql: str, *params: Any) -> int:
    row = store.connect().execute(sql, params).fetchone()
    assert row is not None
    return int(row[0])


def _session_count(store: SqliteBackend) -> int:
    return _scalar(store, "SELECT COUNT(*) FROM query_sessions")


def _result_count(store: SqliteBackend) -> int:
    return _scalar(store, "SELECT COUNT(*) FROM query_results")


def _retrieval(store: SqliteBackend, memory_id: str) -> int:
    return _scalar(store, "SELECT retrieval_count FROM memories WHERE id = ?", memory_id)


def _session_tenant(store: SqliteBackend, session_id: str) -> str:
    row = (
        store.connect()
        .execute("SELECT tenant_id FROM query_sessions WHERE id = ?", (session_id,))
        .fetchone()
    )
    assert row is not None
    return str(row["tenant_id"])


def set_trace(store: SqliteBackend, statements: list[str]) -> None:
    store.connect().set_trace_callback(statements.append)


def unset_trace(store: SqliteBackend) -> None:
    store.connect().set_trace_callback(None)


# ---------------------------------------------------------------------------
# Requirement 2.1 — the tenant predicate inside every candidate-phase SQL
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-51a6a3d3", "C-35f462ba")
def test_phase_scores_and_load_memories_are_tenant_scoped(alice: Seed) -> None:
    store = alice.store
    t1_only = {alice.a1.id}
    both = {alice.g1.id, alice.a1.id}

    for name, parameters in (
        ("_fts_scores", ["self", "query", "limit", "tenant_id"]),
        ("_trigram_scores", ["self", "query", "limit", "tenant_id"]),
        ("_vector_scores", ["self", "query", "query_embedding", "limit", "tenant_id"]),
        ("_load_memories", ["self", "ids", "tenant_id"]),
    ):
        signature = inspect.signature(getattr(SqliteBackend, name))
        assert list(signature.parameters) == parameters, f"SqliteBackend.{name}"
        assert signature.parameters["tenant_id"].default is None

    assert set(store._fts_scores("Alice", 50, tenant_id="t1")) == t1_only
    assert set(store._fts_scores("Alice", 50)) == both
    assert set(store._trigram_scores("Alice", 50, tenant_id="t1")) == t1_only
    assert set(store._trigram_scores("Alice", 50)) == both

    scoped_rows = store._load_memories([alice.g1.id, alice.a1.id], tenant_id="t1")
    assert [row.id for row in scoped_rows] == [alice.a1.id]
    unscoped_rows = store._load_memories([alice.g1.id, alice.a1.id])
    assert {row.id for row in unscoped_rows} == both


@pytest.mark.l4("C-51a6a3d3")
def test_vector_scores_sql_carries_tenant_predicate(monkeypatch: Any, tmp_path: Path) -> None:
    store = SqliteBackend(tmp_path / "mintmory.db")
    store.initialise()
    store.create_tenant("t1")
    monkeypatch.setattr(store, "vector_search_available", lambda: True)
    store.connect().create_function("vec_distance_cosine", 2, lambda a, b: 0.5)
    query_embedding = np.zeros(8, dtype=np.float32)

    scoped: list[str] = []
    set_trace(store, scoped)
    store._vector_scores("x", query_embedding, 50, tenant_id="t1")
    unset_trace(store)
    assert len(scoped) == 1
    assert "SELECT" in scoped[0].upper()
    assert "tenant_id = ?" in scoped[0]

    unscoped: list[str] = []
    set_trace(store, unscoped)
    store._vector_scores("x", query_embedding, 50)
    unset_trace(store)
    assert len(unscoped) == 1
    assert "tenant_id = ?" not in unscoped[0]


# ---------------------------------------------------------------------------
# Requirement 3.7 — a foreign anchor contributes nothing for another tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-1ee5de05", "C-51a6a3d3")
def test_search_around_with_foreign_anchor_returns_only_tenant_rows(alice: Seed) -> None:
    store = alice.store

    signature = inspect.signature(SqliteBackend.search_around)
    assert list(signature.parameters) == ["self", "anchor_ids", "spec", "tenant_id"]
    assert signature.parameters["tenant_id"].default is None

    scoped = store.search_around([alice.g1.id, alice.a1.id], SearchAroundSpec(), tenant_id="t1")
    assert scoped == [alice.a2.id]

    unscoped = store.search_around([alice.g1.id, alice.a1.id], SearchAroundSpec())
    assert set(unscoped) == {alice.g2.id, alice.a2.id}


# ---------------------------------------------------------------------------
# Requirements 3.1 + 3.6 — search scopes results, session and result rows
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-ff7699dc", "C-35f462ba")
def test_search_scopes_results_session_and_sql_over_shared_entity(alice: Seed) -> None:
    store = alice.store
    request = SearchRequest(query="Alice")

    signature = inspect.signature(SqliteBackend.search)
    assert list(signature.parameters) == [
        "self",
        "request",
        "query_embedding",
        "tenant_id",
    ]
    assert signature.parameters["tenant_id"].default is None
    assert signature.parameters["tenant_id"].kind is inspect.Parameter.KEYWORD_ONLY

    unscoped_stmts: list[str] = []
    set_trace(store, unscoped_stmts)
    unscoped = store.search(request)
    unset_trace(store)
    assert unscoped is not None
    assert sorted(mem.id for mem in unscoped.memories) == sorted([alice.g1.id, alice.a1.id])
    assert unscoped.total_found == 2
    assert _session_tenant(store, unscoped.session_id) == "global"
    unfiltered = [
        sql
        for sql in unscoped_stmts
        if ("memories" in sql or "concept_links" in sql) and "tenant_id =" in sql
    ]
    assert unfiltered == []
    assert (
        _scalar(
            store,
            "SELECT COUNT(*) FROM query_results WHERE session_id = ?",
            unscoped.session_id,
        )
        == 2
    )

    scoped_stmts: list[str] = []
    set_trace(store, scoped_stmts)
    scoped = store.search(request, tenant_id="t1")
    unset_trace(store)
    assert scoped is not None
    assert [mem.id for mem in scoped.memories] == [alice.a1.id]
    assert scoped.total_found == 1
    assert _session_tenant(store, scoped.session_id) == "t1"
    lacks_predicate = [
        sql
        for sql in scoped_stmts
        if ("memories" in sql or "concept_links" in sql) and "tenant_id" not in sql
    ]
    assert lacks_predicate == []
    assert (
        _scalar(
            store,
            "SELECT COUNT(*) FROM query_results WHERE session_id = ?",
            scoped.session_id,
        )
        == 1
    )


# ---------------------------------------------------------------------------
# Requirements 3.4 + 3.6 — inactive or missing tenant reads without writing
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-60cdc81b", "C-ff7699dc")
def test_search_confined_to_inactive_or_missing_tenant_writes_nothing(alice: Seed) -> None:
    store = alice.store
    store.set_tenant_active("t1", False)
    sessions0 = _session_count(store)
    results0 = _result_count(store)
    a1_r0 = _retrieval(store, alice.a1.id)

    inactive = store.search(SearchRequest(query="Alice"), tenant_id="t1")
    assert inactive is not None
    assert [mem.id for mem in inactive.memories] == [alice.a1.id]
    assert inactive.session_id == ""
    assert _session_count(store) == sessions0
    assert _result_count(store) == results0
    assert _retrieval(store, alice.a1.id) == a1_r0

    missing = store.search(SearchRequest(query="Alice"), tenant_id="nope")
    assert missing is not None
    assert missing.memories == []
    assert missing.session_id == ""
    assert _session_count(store) == sessions0
    assert _result_count(store) == results0
    assert _retrieval(store, alice.a1.id) == a1_r0


# ---------------------------------------------------------------------------
# Requirement 3.5 — the unscoped read-audit session bumps active tenants only
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-756ad7a3", "C-ff7699dc")
def test_unscoped_search_records_global_session_and_bumps_active_only(alice: Seed) -> None:
    store = alice.store
    store.set_tenant_active("t1", False)
    g1_r0 = _retrieval(store, alice.g1.id)
    a1_r0 = _retrieval(store, alice.a1.id)
    sessions0 = _session_count(store)

    unscoped = store.search(SearchRequest(query="Alice"))
    assert unscoped is not None
    assert {mem.id for mem in unscoped.memories} == {alice.g1.id, alice.a1.id}
    assert _session_tenant(store, unscoped.session_id) == "global"
    assert _session_count(store) == sessions0 + 1
    assert (
        _scalar(
            store,
            "SELECT COUNT(*) FROM query_results WHERE session_id = ?",
            unscoped.session_id,
        )
        == 2
    )
    assert _retrieval(store, alice.g1.id) == g1_r0 + 1
    assert _retrieval(store, alice.a1.id) == a1_r0

    scoped = store.search(SearchRequest(query="Alice"), tenant_id="t1")
    assert scoped is not None
    assert [mem.id for mem in scoped.memories] == [alice.a1.id]
    assert scoped.session_id == ""


# ---------------------------------------------------------------------------
# Requirement 3.2 — fuse_and_search stamps the tenant and drops foreign rows
# ---------------------------------------------------------------------------


def _fuse_callables(alice: Seed) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    """Fakes for the data-access callables plus the calls they recorded."""
    calls: dict[str, list[Any]] = {"created": [], "recorded": [], "bumped": []}

    def create_session(session: QuerySession) -> QuerySession:
        calls["created"].append(session)
        return session

    def record_results(results: list[Any]) -> None:
        calls["recorded"].append(results)

    def bump(ids: list[str], now: datetime) -> None:
        calls["bumped"].append(list(ids))

    def load(ids: list[str]) -> list[MemoryRecord]:
        keep = set(ids)
        return [mem for mem in (alice.a1, alice.g1) if mem.id in keep]

    return (
        {
            "create_session_fn": create_session,
            "record_query_results_fn": record_results,
            "bump_retrieval_fn": bump,
            "load_memories_fn": load,
        },
        calls,
    )


def _fuse_kwargs(alice: Seed) -> dict[str, Any]:
    callables, _ = _fuse_callables(alice)
    return {
        "request": SearchRequest(query="Alice"),
        "fts_scores": {alice.a1.id: 1.0, alice.g1.id: 0.5},
        "trigram_scores": {},
        "vector_scores": {},
        "vector_rrf_weight": 0.0,
        "search_around_fn": lambda anchors, spec: [],
        "get_annotating_notes_fn": lambda mid, cap: [],
        "note_bonus": 0.0,
        "auto_include_cap": 0,
        "now": datetime.now(UTC),
        **callables,
    }


@pytest.mark.l4("C-791d3b0d")
def test_fuse_and_search_stamps_tenant_and_drops_foreign_rows(alice: Seed) -> None:
    signature = inspect.signature(fuse_and_search)
    assert "tenant_id" in signature.parameters
    assert signature.parameters["tenant_id"].default is None
    assert "record_session" in signature.parameters
    assert signature.parameters["record_session"].default is True

    _, calls = _fuse_callables(alice)
    response = fuse_and_search(**_fuse_kwargs(alice), tenant_id="t1")
    assert response is not None
    assert [mem.id for mem in response.memories] == [alice.a1.id]
    assert calls["created"] and calls["created"][0].tenant_id == "t1"
    assert calls["recorded"]
    assert {result.memory_id for result in calls["recorded"][0]} == {alice.a1.id}
    assert calls["bumped"] == [[alice.a1.id]]


# ---------------------------------------------------------------------------
# Requirement 3.3 — record_session=False writes nothing, session_id ""
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-e72eb814")
def test_fuse_and_search_without_recording_returns_results_and_empty_session(
    alice: Seed,
) -> None:
    _, calls = _fuse_callables(alice)
    response = fuse_and_search(**_fuse_kwargs(alice), tenant_id="t1", record_session=False)
    assert response is not None
    assert [mem.id for mem in response.memories] == [alice.a1.id]
    assert response.session_id == ""
    assert calls["created"] == []
    assert calls["recorded"] == []
    assert calls["bumped"] == []


# ---------------------------------------------------------------------------
# Requirement 3.8 — anchor_candidates stays side-effect free for every tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-42824265", "C-51a6a3d3")
def test_anchor_candidates_is_tenant_scoped_without_side_effects(alice: Seed) -> None:
    store = alice.store
    sessions0 = _session_count(store)
    results0 = _result_count(store)
    g1_r0 = _retrieval(store, alice.g1.id)
    a1_r0 = _retrieval(store, alice.a1.id)

    signature = inspect.signature(SqliteBackend.anchor_candidates)
    assert list(signature.parameters) == ["self", "about", "limit", "tenant_id"]
    assert signature.parameters["limit"].default == 5
    assert signature.parameters["tenant_id"].default is None

    scoped = store.anchor_candidates("Alice", tenant_id="t1")
    assert [record.id for _, record in scoped] == [alice.a1.id]

    unscoped = store.anchor_candidates("Alice")
    assert {record.id for _, record in unscoped} == {alice.g1.id, alice.a1.id}

    assert _session_count(store) == sessions0
    assert _result_count(store) == results0
    assert _retrieval(store, alice.g1.id) == g1_r0
    assert _retrieval(store, alice.a1.id) == a1_r0
