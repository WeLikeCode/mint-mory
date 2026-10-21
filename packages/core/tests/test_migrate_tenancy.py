"""RED tests for task 5 — the SQLite→Postgres migration carries tenants.

They trace requirements 4.1–4.6 without a database: the table metadata and
insert helpers are asserted directly, dry-run reports come from a real
tenant-aware SQLite file, and the pre-checks are exercised on a pre-tenancy
fixture and on a source whose row points at a ghost tenant.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import mintmory.core.migrate as migrate
import pytest
from mintmory.core.embedder import HashingEmbedder
from mintmory.core.migrate import (
    _insert_concept_links_batch,
    _insert_index_manifest_batch,
    _insert_memories_batch,
    _insert_memory_summaries_batch,
    _insert_query_results_batch,
    _insert_query_sessions_batch,
    _insert_tenants_batch,
    _pg_truncate_all,
    _source_checksum,
    migrate_sqlite_to_postgres,
)
from mintmory.core.storage import SqliteBackend

from packages.core.tests.pg_fakes import FakeConnection

_TENANT_COLUMNS = ("id", "name", "is_active", "created_at", "updated_at")
_SIX_TABLES = (
    "memories",
    "concept_links",
    "memory_summaries",
    "index_manifest",
    "query_sessions",
    "query_results",
)


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _insert_columns(sql: str) -> list[str]:
    match = re.search(
        r"INSERT INTO \w+\s*\((.*?)\)\s*VALUES",
        _norm(sql),
        re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, sql
    return [column.strip() for column in match.group(1).split(",")]


def _tenant_row(tenant_id: str, name: str) -> dict[str, Any]:
    return {
        "id": tenant_id,
        "name": name,
        "is_active": 1 if tenant_id != "acme" else 0,
        "created_at": "1970-01-01T00:00:00",
        "updated_at": "1970-01-01T00:00:00",
    }


def _memory_row(tenant_id: str) -> dict[str, Any]:
    return {
        "id": "m1",
        "content": "Alice works at Acme",
        "category": "fact",
        "entity_ids": "[]",
        "embedding": None,
        "confidence": 1.0,
        "source": "agent",
        "verified": 1,
        "valid_from": None,
        "valid_until": None,
        "usefulness_score": 0.0,
        "staleness_score": 0.0,
        "reinforcement_count": 0,
        "retrieval_count": 0,
        "is_stale": 0,
        "is_active": 1,
        "is_archived": 0,
        "superseded_by": None,
        "flagged_for_review": 0,
        "contradicts_ids": "[]",
        "is_note": 0,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
        "last_accessed_at": None,
        "metadata": "{}",
        "tenant_id": tenant_id,
    }


def _link_row(tenant_id: str) -> dict[str, Any]:
    return {
        "id": "l1",
        "source_memory_id": "m1",
        "target_memory_id": "m2",
        "link_type": "relates_to",
        "entity": "Alice",
        "strength": 0.5,
        "confidence": 0.5,
        "source": "dreaming",
        "verified": 0,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
        "tenant_id": tenant_id,
    }


def _summary_row(tenant_id: str) -> dict[str, Any]:
    return {
        "id": "sum1",
        "concept": "acme",
        "summary_text": "Acme summary",
        "memory_count": 1,
        "is_current": 1,
        "generated_at": "2024-01-01T00:00:00",
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
        "memory_ids": "[]",
        "online_only": 0,
        "last_seen": "2024-01-01T00:00:00",
        "tenant_id": tenant_id,
    }


def _session_row(tenant_id: str) -> dict[str, Any]:
    return {
        "id": "s1",
        "query_text": "who works at Acme?",
        "created_at": "2024-01-01T00:00:00",
        "confidence_rating": 4,
        "reasoning": "found it",
        "useful_ids": "[]",
        "stale_ids": "[]",
        "concluded": 0,
        "tenant_id": tenant_id,
    }


def _result_row(tenant_id: str) -> dict[str, Any]:
    return {
        "session_id": "s1",
        "memory_id": "m1",
        "relevance_score": 1.0,
        "was_accessed": 1,
        "was_useful": 1,
        "was_stale": 0,
        "tenant_id": tenant_id,
    }


def _build_tenant_aware_source(tmp_path: Path) -> tuple[str, str]:
    path = str(tmp_path / "memories.db")
    store = SqliteBackend(path, embedder=HashingEmbedder(dim=8))
    store.initialise()
    store.create_tenant("acme", "Acme")
    memory = store.add_memory(content="Acme tenant memory", category="fact", tenant_id="acme")
    store.close()
    return path, memory.id


# ---------------------------------------------------------------------------
# Requirement 4.1 — table metadata for the tenant directory
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-457d193a")
def test_tenants_table_metadata_is_complete() -> None:
    assert getattr(migrate, "_TENANTS_COLS", None) == _TENANT_COLUMNS
    assert getattr(migrate, "_TABLE_COLS", {}).get("tenants") == _TENANT_COLUMNS
    assert getattr(migrate, "_TABLE_PK", {}).get("tenants") == ["id"]
    assert getattr(migrate, "_CHECKSUM_EXCLUDED", {}).get("tenants") == set()
    assert getattr(migrate, "_BOOL_COLS", {}).get("tenants") == {"is_active"}
    assert getattr(migrate, "_DATETIME_COLS", {}).get("tenants") == {"created_at", "updated_at"}
    assert getattr(migrate, "_JSONB_COLS", {}).get("tenants") == set()


@pytest.mark.l4("C-457d193a")
def test_fk_order_starts_with_tenants() -> None:
    order = getattr(migrate, "_FK_ORDER", None)
    assert order is not None
    assert order[0] == "tenants"
    assert set(order[1:]) == set(_SIX_TABLES)


@pytest.mark.l4("C-457d193a")
def test_index_manifest_primary_key_is_per_tenant() -> None:
    assert getattr(migrate, "_TABLE_PK", {}).get("index_manifest") == ["tenant_id", "path"]


# ---------------------------------------------------------------------------
# Requirement 4.2 — tenant_id on the six source tuples and insert helpers
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2eb283b3")
def test_six_source_column_tuples_end_with_tenant_id() -> None:
    names = (
        "_MEMORIES_COLS",
        "_CONCEPT_LINKS_COLS",
        "_MEMORY_SUMMARIES_COLS",
        "_INDEX_MANIFEST_COLS",
        "_QUERY_SESSIONS_COLS",
        "_QUERY_RESULTS_COLS",
    )
    for name in names:
        columns = getattr(migrate, name, None)
        assert columns is not None, name
        assert columns[-1] == "tenant_id", name


@pytest.mark.l4("C-2eb283b3")
def test_insert_memories_batch_carries_tenant_id() -> None:
    conn = FakeConnection()

    assert _insert_memories_batch(conn, [_memory_row("acme")]) == 1

    sql, params = conn.executed[0]
    assert _insert_columns(sql)[-1] == "tenant_id"
    assert params[-1] == "acme"


@pytest.mark.l4("C-2eb283b3")
def test_insert_memory_summaries_batch_carries_tenant_id() -> None:
    conn = FakeConnection()

    assert _insert_memory_summaries_batch(conn, [_summary_row("acme")]) == 1

    sql, params = conn.executed[0]
    assert _insert_columns(sql)[-1] == "tenant_id"
    assert params[-1] == "acme"


@pytest.mark.l4("C-2eb283b3")
def test_insert_query_sessions_batch_carries_tenant_id() -> None:
    conn = FakeConnection()

    assert _insert_query_sessions_batch(conn, [_session_row("acme")]) == 1

    sql, params = conn.executed[0]
    assert _insert_columns(sql)[-1] == "tenant_id"
    assert params[-1] == "acme"


@pytest.mark.l4("C-2eb283b3")
def test_insert_query_results_batch_carries_tenant_id() -> None:
    conn = FakeConnection()

    assert _insert_query_results_batch(conn, [_result_row("acme")]) == 1

    sql, params = conn.executed[0]
    assert _insert_columns(sql)[-1] == "tenant_id"
    assert params[-1] == "acme"


@pytest.mark.l4("C-2eb283b3", "C-56611860")
def test_insert_concept_links_batch_carries_tenant_id_and_per_tenant_conflict() -> None:
    conn = FakeConnection()

    assert _insert_concept_links_batch(conn, [_link_row("acme")]) == 1

    sql, params = conn.executed[0]
    normalised = _norm(sql)
    assert _insert_columns(normalised)[-1] == "tenant_id"
    assert params[-1] == "acme"
    assert (
        "ON CONFLICT (tenant_id, source_memory_id, target_memory_id, link_type) DO NOTHING"
        in normalised
    )


@pytest.mark.l4("C-2eb283b3", "C-56611860")
def test_insert_index_manifest_batch_carries_tenant_id_and_per_tenant_conflict() -> None:
    conn = FakeConnection()

    assert _insert_index_manifest_batch(conn, [_manifest_row("acme")]) == 1

    sql, params = conn.executed[0]
    normalised = _norm(sql)
    assert _insert_columns(normalised)[-1] == "tenant_id"
    assert params[-1] == "acme"
    assert "ON CONFLICT (tenant_id, path) DO NOTHING" in normalised


# ---------------------------------------------------------------------------
# Requirement 4.3 — tenants insert helper and truncate
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-d39187cd")
def test_insert_tenants_batch_sql_and_params() -> None:
    conn = FakeConnection()
    rows = [_tenant_row("global", "Global"), _tenant_row("acme", "Acme")]

    assert _insert_tenants_batch(conn, rows) == 2

    assert len(conn.executed) == 2
    sql = _norm(conn.executed[0][0])
    assert sql == (
        "INSERT INTO tenants (id, name, is_active, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING"
    )
    first = conn.executed[0][1]
    second = conn.executed[1][1]
    assert first[0] == "global"
    assert first[1] == "Global"
    assert bool(first[2]) is True
    assert second[0] == "acme"
    assert second[1] == "Acme"
    assert bool(second[2]) is False


@pytest.mark.l4("C-d39187cd")
def test_insert_tenants_batch_dry_run_or_no_rows_writes_nothing() -> None:
    conn = FakeConnection()

    assert _insert_tenants_batch(conn, [_tenant_row("global", "Global")], dry_run=True) == 1
    assert conn.executed == []
    assert _insert_tenants_batch(conn, []) == 0
    assert conn.executed == []


@pytest.mark.l4("C-d39187cd")
def test_tenants_registered_in_table_insert_fn() -> None:
    insert_fn = migrate._TABLE_INSERT_FN.get("tenants")
    assert insert_fn is not None

    conn = FakeConnection()
    assert insert_fn(conn, [_tenant_row("global", "Global")]) == 1
    assert "INSERT INTO tenants" in _norm(conn.executed[0][0])


@pytest.mark.l4("C-d39187cd")
def test_pg_truncate_all_clears_tenants_too() -> None:
    conn = FakeConnection()

    _pg_truncate_all(conn)

    assert _norm(conn.executed[0][0]) == (
        "TRUNCATE memories, concept_links, index_manifest, query_sessions, "
        "query_results, memory_summaries, tenants RESTART IDENTITY CASCADE"
    )
    assert conn.commits == 1


# ---------------------------------------------------------------------------
# Requirement 4.4 — the source pre-checks (also in dry-run)
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-455cf2dc", "C-56611860")
def test_pre_tenancy_source_raises_before_dry_run(tmp_path: Path) -> None:
    path = str(tmp_path / "old.db")
    fixture = Path(__file__).parent / "fixtures" / "pre_tenancy_schema.sql"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(fixture.read_text())
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError) as excinfo:
        migrate_sqlite_to_postgres(path, "postgresql://unused", dry_run=True)

    assert str(excinfo.value) == (
        "source database predates multi-tenancy: open it once with this MintMory "
        "version (any command) to migrate it, then retry"
    )


@pytest.mark.l4("C-455cf2dc", "C-56611860")
def test_source_with_unknown_tenant_raises_before_dry_run(tmp_path: Path) -> None:
    path, memory_id = _build_tenant_aware_source(tmp_path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("UPDATE memories SET tenant_id = 'ghost' WHERE id = ?", (memory_id,))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError) as excinfo:
        migrate_sqlite_to_postgres(path, "postgresql://unused", dry_run=True)

    assert str(excinfo.value) == "source table 'memories' references unknown tenant(s): ['ghost']"


# ---------------------------------------------------------------------------
# Requirement 4.5 — tenant_id is part of the checksum
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-fec13454", "C-457d193a", "C-56611860")
def test_checksums_include_tenant_id() -> None:
    assert getattr(migrate, "_CHECKSUM_EXCLUDED", {}).get("tenants") == set()

    global_row = _tenant_row("global", "Global")
    acme_row = _tenant_row("acme", "Acme")
    assert global_row.keys() == acme_row.keys()
    assert _source_checksum([global_row], "tenants") != _source_checksum([acme_row], "tenants")


# ---------------------------------------------------------------------------
# Requirement 4.6 — dry-run report lists tenants first with its row count
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-56611860")
def test_dry_run_lists_tenants_first_with_its_row_count(tmp_path: Path) -> None:
    path, _memory_id = _build_tenant_aware_source(tmp_path)

    report = migrate_sqlite_to_postgres(path, "postgresql://unused", dry_run=True)

    assert report.dry_run is True
    assert report.tables[0].table == "tenants"
    assert report.tables[0].src_count == 2
