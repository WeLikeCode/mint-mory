"""RED tests for task 2 — the multi-tenant SQLite schema (``schema.sql``).

They trace requirements 2.1–2.5: the ``tenants`` table and its seed row, the
``tenant_id`` column on all six tables, per-tenant uniqueness, the absence of
any ``tenant_id`` index from ``schema.sql`` itself, and the unchanged FTS5 /
trigram triggers.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from mintmory.core.storage import StorageAdapter

SIX_TENANT_TABLES = (
    "memories",
    "concept_links",
    "memory_summaries",
    "index_manifest",
    "query_sessions",
    "query_results",
)


@pytest.fixture()
def store() -> StorageAdapter:
    adapter = StorageAdapter(":memory:")
    adapter.initialise()
    return adapter


@pytest.fixture()
def schema_sql() -> str:
    path = Path(__file__).parent.parent / "src" / "mintmory" / "core" / "schema.sql"
    return path.read_text()


def _unique_index_columns(conn: sqlite3.Connection, table: str) -> set[tuple[str, ...]]:
    result: set[tuple[str, ...]] = set()
    for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if not index["unique"]:
            continue
        columns = tuple(
            row["name"] for row in conn.execute(f"PRAGMA index_info({index['name']})").fetchall()
        )
        result.add(columns)
    return result


# ---------------------------------------------------------------------------
# Requirement 2.1 — the tenants table and its seed
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-b3eb1490")
def test_fresh_schema_creates_and_seeds_tenants(store: StorageAdapter) -> None:
    conn = store.connect()
    info = {row["name"]: row for row in conn.execute("PRAGMA table_info(tenants)").fetchall()}
    assert set(info) == {"id", "name", "is_active", "created_at", "updated_at"}
    assert info["id"]["pk"] == 1
    assert info["name"]["notnull"] == 1
    assert info["name"]["dflt_value"] == "''"
    assert info["is_active"]["notnull"] == 1
    assert info["is_active"]["dflt_value"] == "1"
    assert info["created_at"]["notnull"] == 1
    assert info["updated_at"]["notnull"] == 1

    rows = conn.execute(
        "SELECT id, name, is_active, created_at, updated_at FROM tenants"
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert (
        row["id"],
        row["name"],
        row["is_active"],
        row["created_at"],
        row["updated_at"],
    ) == (
        "global",
        "Global (default) tenant",
        1,
        "1970-01-01T00:00:00",
        "1970-01-01T00:00:00",
    )


@pytest.mark.l4("C-b3eb1490")
def test_tenants_table_is_created_before_memories_and_reseed_is_idempotent(
    store: StorageAdapter, schema_sql: str
) -> None:
    assert "CREATE TABLE IF NOT EXISTS tenants" in schema_sql
    assert "CREATE TABLE IF NOT EXISTS memories" in schema_sql
    tenants_at = schema_sql.index("CREATE TABLE IF NOT EXISTS tenants")
    memories_at = schema_sql.index("CREATE TABLE IF NOT EXISTS memories")
    assert tenants_at < memories_at
    assert "INSERT OR IGNORE INTO tenants" in schema_sql
    store.initialise()
    rows = store.connect().execute("SELECT id, COUNT(*) AS c FROM tenants GROUP BY id").fetchall()
    assert [(row["id"], row["c"]) for row in rows] == [("global", 1)]


# ---------------------------------------------------------------------------
# Requirement 2.2 — tenant_id as the last column of all six tables
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-90e130ca")
def test_six_tables_have_tenant_id_as_last_column(store: StorageAdapter) -> None:
    conn = store.connect()
    for table in SIX_TENANT_TABLES:
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        assert info, table
        last = info[-1]
        assert last["name"] == "tenant_id", table
        assert last["notnull"] == 1, table
        assert last["dflt_value"] == "'global'", table
        foreign_keys = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        assert any(fk["table"] == "tenants" and fk["from"] == "tenant_id" for fk in foreign_keys), (
            table
        )


# ---------------------------------------------------------------------------
# Requirement 2.3 — per-tenant uniqueness
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-b6f54c67")
def test_concept_links_uniqueness_is_per_tenant(store: StorageAdapter) -> None:
    conn = store.connect()
    unique = _unique_index_columns(conn, "concept_links")
    assert ("tenant_id", "source_memory_id", "target_memory_id", "link_type") in unique
    assert ("source_memory_id", "target_memory_id", "link_type") not in unique


@pytest.mark.l4("C-b6f54c67")
def test_memory_summaries_unique_per_tenant_concept(store: StorageAdapter) -> None:
    conn = store.connect()
    unique = _unique_index_columns(conn, "memory_summaries")
    assert ("tenant_id", "concept") in unique
    assert ("concept",) not in unique
    info = {row["name"]: row for row in conn.execute("PRAGMA table_info(memory_summaries)")}
    assert info["concept"]["notnull"] == 1


@pytest.mark.l4("C-b6f54c67")
def test_index_manifest_primary_key_is_tenant_and_path(store: StorageAdapter) -> None:
    conn = store.connect()
    info = conn.execute("PRAGMA table_info(index_manifest)").fetchall()
    primary = {row["name"]: row["pk"] for row in info if row["pk"]}
    assert primary == {"tenant_id": 1, "path": 2}
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='index_manifest'"
    ).fetchone()["sql"]
    assert "'metadata'" in sql
    assert "'content'" in sql
    assert "'vision'" in sql


# ---------------------------------------------------------------------------
# Requirement 2.4 — schema.sql creates no index over tenant_id
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-d0373dab")
def test_schema_sql_declares_no_index_over_tenant_id(tmp_path: Path, schema_sql: str) -> None:
    pre_feature = (Path(__file__).parent / "fixtures" / "pre_tenancy_schema.sql").read_text()
    index_statements = [
        statement for statement in schema_sql.split(";") if "CREATE INDEX" in statement
    ]
    assert index_statements
    offenders = [statement for statement in index_statements if "tenant_id" in statement]
    assert offenders == []

    db_path = tmp_path / "pre_feature.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(pre_feature)
        conn.commit()
        conn.executescript(schema_sql)
        conn.commit()
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert "tenants" in tables


# ---------------------------------------------------------------------------
# Requirement 2.5 — FTS5 and trigram triggers stay unchanged
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-c842fbe1")
def test_fts_and_trigram_triggers_stay_unchanged(store: StorageAdapter, schema_sql: str) -> None:
    assert "CREATE TABLE IF NOT EXISTS tenants" in schema_sql
    for name in (
        "memories_fts_insert",
        "memories_fts_update",
        "memories_fts_delete",
    ):
        assert f"CREATE TRIGGER IF NOT EXISTS {name}" in schema_sql, name
    conn = store.connect()
    triggers = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
    }
    assert {
        "memories_fts_insert",
        "memories_fts_update",
        "memories_fts_delete",
    } <= triggers
    assert {
        "memories_trigram_insert",
        "memories_trigram_update",
        "memories_trigram_delete",
    } <= triggers

    store.add_memory(content="tenant trigger probe", category="fact")
    fts_hits = conn.execute(
        "SELECT COUNT(*) AS c FROM memories_fts WHERE memories_fts MATCH 'probe'"
    ).fetchone()["c"]
    assert fts_hits >= 1
    trigram_hits = conn.execute(
        "SELECT COUNT(*) AS c FROM memories_trigram WHERE content LIKE '%probe%'"
    ).fetchone()["c"]
    assert trigram_hits >= 1
