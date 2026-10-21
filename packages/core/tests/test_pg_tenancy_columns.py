"""RED tests for task 4 — Postgres column parity and per-tenant keys.

They trace requirements 3.1–3.5 with the fake connection/pool of
``pg_fakes``: the Postgres statements read and write ``tenant_id``, the
per-tenant conflict targets and keyed lookups are in place, the global-only
guard still covers every write/keyed method, and ``_truncate_all`` clears the
non-global tenant rows after truncating the six tables.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pytest
from mintmory.core.ports import ManifestEntry
from mintmory.core.storage_postgres import _SELECT_MEMORY, PostgresBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    LinkSource,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
    MemorySummary,
    QueryResult,
    QuerySession,
    TenancyNotSupportedError,
)

from packages.core.tests.pg_fakes import FakeConnection, FakePool

_NOW = datetime(2024, 1, 1)
_TENANT = "acme"


def _normalise(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _backend(conn: FakeConnection) -> PostgresBackend:
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)
    return backend


def _find_statement(conn: FakeConnection, marker: str) -> tuple[str, Any]:
    for sql, params in conn.executed:
        if marker in _normalise(sql):
            return _normalise(sql), params
    raise AssertionError(f"no executed statement contains {marker!r}: {conn.executed!r}")


def _insert_columns(sql: str) -> list[str]:
    match = re.search(
        r"INSERT INTO \w+\s*\((.*?)\)\s*VALUES",
        _normalise(sql),
        re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, sql
    return [column.strip() for column in match.group(1).split(",")]


def _summary_responder(sql: str, params: Any) -> list[Any]:
    if "FROM memory_summaries" in _normalise(sql):
        return [_summary_row("global")]
    return []


def _memory_row(tenant_id: str) -> dict[str, Any]:
    return {
        "id": "m1",
        "content": "Alice works at Acme",
        "category": MemoryCategory.FACT.value,
        "entity_ids": ["Alice"],
        "confidence": 1.0,
        "source": MemorySource.AGENT.value,
        "verified": False,
        "valid_from": _NOW,
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
        "created_at": _NOW,
        "updated_at": _NOW,
        "last_accessed_at": None,
        "metadata": {},
        "tenant_id": tenant_id,
    }


def _link_row(tenant_id: str) -> dict[str, Any]:
    return {
        "id": "l1",
        "source_memory_id": "m1",
        "target_memory_id": "m2",
        "link_type": ConceptLinkType.RELATES_TO.value,
        "entity": "Alice",
        "strength": 0.5,
        "confidence": 0.5,
        "source": LinkSource.DREAMING.value,
        "verified": False,
        "created_at": _NOW,
        "updated_at": _NOW,
        "tenant_id": tenant_id,
    }


def _summary_row(tenant_id: str) -> dict[str, Any]:
    return {
        "id": "sum1",
        "concept": "acme",
        "summary_text": "Acme summary",
        "memory_count": 1,
        "is_current": True,
        "generated_at": _NOW,
        "tenant_id": tenant_id,
    }


def _session_row(tenant_id: str) -> dict[str, Any]:
    return {
        "id": "s1",
        "query_text": "who works at Acme?",
        "created_at": _NOW,
        "confidence_rating": 4,
        "reasoning": "found it",
        "useful_ids": ["m1"],
        "stale_ids": [],
        "concluded": True,
        "tenant_id": tenant_id,
    }


def _manifest_row(tenant_id: str) -> dict[str, Any]:
    return {
        "path": "/a",
        "collection": "default",
        "size": 1,
        "mtime": 0.0,
        "content_hash": "hash",
        "index_mode": "content",
        "memory_ids": '["m1"]',
        "online_only": 0,
        "last_seen": "2024-01-01 00:00:00",
        "tenant_id": tenant_id,
    }


# ---------------------------------------------------------------------------
# Requirement 3.1 — every record statement carries tenant_id
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-73647c35")
def test_select_memory_ends_with_tenant_id() -> None:
    assert _normalise(_SELECT_MEMORY).endswith("tenant_id")


@pytest.mark.l4("C-73647c35", "C-9a6d3abf")
def test_add_memory_insert_includes_tenant_id() -> None:
    conn = FakeConnection()
    backend = _backend(conn)
    record = MemoryRecord(content="Alice works at Acme", category=MemoryCategory.FACT)

    backend.add_memory(record)

    sql, params = _find_statement(conn, "INSERT INTO memories")
    assert "tenant_id" in _insert_columns(sql)
    assert "global" in params


@pytest.mark.l4("C-73647c35", "C-9a6d3abf")
def test_add_link_insert_includes_tenant_id() -> None:
    conn = FakeConnection()
    backend = _backend(conn)
    link = ConceptLink(
        source_memory_id="m1",
        target_memory_id="m2",
        link_type=ConceptLinkType.RELATES_TO,
    )

    backend.add_link(link)

    sql, params = _find_statement(conn, "INSERT INTO concept_links")
    assert "tenant_id" in _insert_columns(sql)
    assert "global" in params


@pytest.mark.l4("C-73647c35", "C-9a6d3abf")
def test_create_session_insert_includes_tenant_id() -> None:
    conn = FakeConnection()
    backend = _backend(conn)
    session = QuerySession(query_text="who works at Acme?")

    backend.create_session(session)

    sql, params = _find_statement(conn, "INSERT INTO query_sessions")
    assert "tenant_id" in _insert_columns(sql)
    assert "global" in params


@pytest.mark.l4("C-73647c35", "C-9a6d3abf")
def test_record_query_results_insert_includes_tenant_id() -> None:
    conn = FakeConnection()
    backend = _backend(conn)
    result = QueryResult(session_id="s1", memory_id="m1", relevance_score=1.0)

    backend.record_query_results([result])

    sql, params = _find_statement(conn, "INSERT INTO query_results")
    assert "tenant_id" in _insert_columns(sql)
    assert "global" in params


@pytest.mark.l4("C-73647c35", "C-9a6d3abf")
def test_upsert_summary_insert_includes_tenant_id() -> None:
    conn = FakeConnection(responder=_summary_responder)
    backend = _backend(conn)
    summary = MemorySummary(concept="acme", summary_text="Acme summary", memory_count=1)

    backend.upsert_summary(summary)

    sql, params = _find_statement(conn, "INSERT INTO memory_summaries")
    assert "tenant_id" in _insert_columns(sql)
    assert "global" in params


@pytest.mark.l4("C-73647c35", "C-9a6d3abf")
def test_manifest_upsert_insert_includes_tenant_id() -> None:
    conn = FakeConnection()
    backend = _backend(conn)

    backend.manifest_upsert(
        "/a",
        "default",
        size=1,
        mtime=0.0,
        online_only=False,
        index_mode="content",
        memory_ids=[],
    )

    sql, params = _find_statement(conn, "INSERT INTO index_manifest")
    assert "tenant_id" in _insert_columns(sql)
    assert "global" in params


# ---------------------------------------------------------------------------
# Requirement 3.1 — mappers return the stored tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-73647c35", "C-9a6d3abf")
def test_row_to_memory_returns_the_stored_tenant() -> None:
    backend = _backend(FakeConnection())

    assert backend._row_to_memory(_memory_row("global")).tenant_id == "global"
    assert backend._row_to_memory(_memory_row(_TENANT)).tenant_id == _TENANT


@pytest.mark.l4("C-73647c35", "C-9a6d3abf")
def test_row_to_link_returns_the_stored_tenant() -> None:
    backend = _backend(FakeConnection())

    assert backend._row_to_link(_link_row("global")).tenant_id == "global"
    assert backend._row_to_link(_link_row(_TENANT)).tenant_id == _TENANT


@pytest.mark.l4("C-73647c35")
def test_get_session_returns_the_stored_tenant() -> None:
    conn = FakeConnection(responder=lambda sql, params: [_session_row(_TENANT)])
    backend = _backend(conn)

    session = backend.get_session("s1")

    assert session is not None
    assert session.tenant_id == _TENANT


@pytest.mark.l4("C-73647c35")
def test_get_summary_returns_the_stored_tenant() -> None:
    conn = FakeConnection(responder=lambda sql, params: [_summary_row(_TENANT)])
    backend = _backend(conn)

    summary = backend.get_summary("acme")

    assert summary is not None
    assert summary.tenant_id == _TENANT


@pytest.mark.l4("C-73647c35")
def test_manifest_get_returns_the_stored_tenant() -> None:
    conn = FakeConnection(responder=lambda sql, params: [_manifest_row(_TENANT)])
    backend = _backend(conn)

    entry: ManifestEntry | None = backend.manifest_get("/a")

    assert entry is not None
    assert entry["tenant_id"] == _TENANT


# ---------------------------------------------------------------------------
# Requirement 3.2 — per-tenant conflict targets and keyed tenant predicates
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-faabc87f", "C-9a6d3abf")
def test_add_link_conflict_target_is_per_tenant() -> None:
    conn = FakeConnection()
    backend = _backend(conn)

    backend.add_link(
        ConceptLink(
            source_memory_id="m1",
            target_memory_id="m2",
            link_type=ConceptLinkType.RELATES_TO,
        )
    )

    sql, _params = _find_statement(conn, "INSERT INTO concept_links")
    assert (
        "ON CONFLICT (tenant_id, source_memory_id, target_memory_id, link_type) DO NOTHING" in sql
    )


@pytest.mark.l4("C-faabc87f", "C-9a6d3abf")
def test_upsert_summary_conflict_target_is_per_tenant() -> None:
    conn = FakeConnection(responder=_summary_responder)
    backend = _backend(conn)

    backend.upsert_summary(
        MemorySummary(concept="acme", summary_text="Acme summary", memory_count=1)
    )

    sql, _params = _find_statement(conn, "INSERT INTO memory_summaries")
    assert "ON CONFLICT (tenant_id, concept) DO UPDATE" in sql


@pytest.mark.l4("C-faabc87f", "C-9a6d3abf")
def test_manifest_upsert_conflict_target_is_per_tenant() -> None:
    conn = FakeConnection()
    backend = _backend(conn)

    backend.manifest_upsert(
        "/a",
        "default",
        size=1,
        mtime=0.0,
        online_only=False,
        index_mode="content",
        memory_ids=[],
    )

    sql, _params = _find_statement(conn, "INSERT INTO index_manifest")
    assert "ON CONFLICT (tenant_id, path) DO UPDATE" in sql


@pytest.mark.l4("C-faabc87f", "C-9a6d3abf")
def test_get_summary_looks_up_by_concept_and_tenant() -> None:
    conn = FakeConnection()
    backend = _backend(conn)

    backend.get_summary("acme")

    sql, params = _find_statement(conn, "FROM memory_summaries")
    assert "WHERE concept = %s AND tenant_id = %s" in sql
    assert params == ("acme", "global")


@pytest.mark.l4("C-faabc87f", "C-9a6d3abf")
def test_manifest_get_looks_up_by_path_and_tenant() -> None:
    conn = FakeConnection()
    backend = _backend(conn)

    backend.manifest_get("/a")

    sql, params = _find_statement(conn, "FROM index_manifest")
    assert "WHERE path = %s AND tenant_id = %s" in sql
    assert params == ("/a", "global")


@pytest.mark.l4("C-faabc87f", "C-9a6d3abf")
def test_manifest_paths_filters_by_collection_and_tenant() -> None:
    conn = FakeConnection()
    backend = _backend(conn)

    backend.manifest_paths("default")

    sql, params = _find_statement(conn, "FROM index_manifest")
    assert "WHERE collection = %s AND tenant_id = %s" in sql
    assert params == ("default", "global")


@pytest.mark.l4("C-faabc87f", "C-9a6d3abf")
def test_manifest_delete_filters_by_path_and_tenant() -> None:
    conn = FakeConnection()
    backend = _backend(conn)

    backend.manifest_delete("/a")

    sql, params = _find_statement(conn, "DELETE FROM index_manifest")
    assert "WHERE path = %s AND tenant_id = %s" in sql
    assert params == ("/a", "global")


# ---------------------------------------------------------------------------
# Requirement 3.3 — the global-only guard still covers writes and keyed methods
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-d4a710f6", "C-73647c35")
def test_guards_stay_on_record_writes_and_keyed_methods_before_pool_access() -> None:
    conn = FakeConnection(responder=_summary_responder)
    backend = _backend(conn)

    with pytest.raises(TenancyNotSupportedError):
        backend.add_memory(
            MemoryRecord(
                content="Alice works at Acme",
                category=MemoryCategory.FACT,
                tenant_id=_TENANT,
            )
        )
    with pytest.raises(TenancyNotSupportedError):
        backend.add_link(
            ConceptLink(
                source_memory_id="m1",
                target_memory_id="m2",
                link_type=ConceptLinkType.RELATES_TO,
                tenant_id=_TENANT,
            )
        )
    with pytest.raises(TenancyNotSupportedError):
        backend.create_session(QuerySession(query_text="q", tenant_id=_TENANT))
    with pytest.raises(TenancyNotSupportedError):
        backend.record_query_results(
            [
                QueryResult(
                    session_id="s1",
                    memory_id="m1",
                    relevance_score=1.0,
                    tenant_id=_TENANT,
                )
            ]
        )
    with pytest.raises(TenancyNotSupportedError):
        backend.upsert_summary(
            MemorySummary(
                concept="acme",
                summary_text="Acme summary",
                memory_count=1,
                tenant_id=_TENANT,
            )
        )
    with pytest.raises(TenancyNotSupportedError):
        backend.get_summary("acme", tenant_id=_TENANT)
    with pytest.raises(TenancyNotSupportedError):
        backend.manifest_get("/a", tenant_id=_TENANT)
    with pytest.raises(TenancyNotSupportedError):
        backend.manifest_upsert(
            "/a",
            "default",
            size=1,
            mtime=0.0,
            online_only=False,
            index_mode="content",
            memory_ids=[],
            tenant_id=_TENANT,
        )
    with pytest.raises(TenancyNotSupportedError):
        backend.manifest_paths("default", tenant_id=_TENANT)
    with pytest.raises(TenancyNotSupportedError):
        backend.manifest_delete("/a", tenant_id=_TENANT)

    assert conn.executed == []

    backend.add_memory(MemoryRecord(content="Alice works at Acme", category=MemoryCategory.FACT))
    sql, _params = _find_statement(conn, "INSERT INTO memories")
    assert "tenant_id" in _insert_columns(sql)


# ---------------------------------------------------------------------------
# Requirement 3.4 — _truncate_all also clears non-global tenants
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-536811bb")
def test_truncate_all_deletes_non_global_tenants_after_the_truncate() -> None:
    conn = FakeConnection()
    backend = _backend(conn)

    backend._truncate_all()

    assert len(conn.executed) == 2
    assert _normalise(conn.executed[0][0]) == (
        "TRUNCATE memories, concept_links, index_manifest, query_sessions, "
        "query_results, memory_summaries RESTART IDENTITY CASCADE"
    )
    assert _normalise(conn.executed[1][0]) == "DELETE FROM tenants WHERE id <> 'global'"
    assert conn.commits == 1
