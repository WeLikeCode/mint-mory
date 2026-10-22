"""RED tests for task 3 — migrating an existing SQLite database to tenancy.

They trace requirements 3.1–3.8: the migration is wired into ``initialise()``,
its plan is ordered (columns, rebuilds, indexes), it runs under one
``BEGIN IMMEDIATE`` and re-computes the plan inside the lock, failures roll
back and fail closed, a second start is a no-op, and a pre-feature database
migrates its rows and matches a fresh database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import TenantMigrationError

SIX_TENANT_TABLES: tuple[str, ...] = (
    "memories",
    "concept_links",
    "memory_summaries",
    "index_manifest",
    "query_sessions",
    "query_results",
)
REBUILT_TABLES: tuple[str, ...] = ("concept_links", "memory_summaries", "index_manifest")
TENANT_INDEXES: tuple[str, ...] = (
    "idx_memories_tenant",
    "idx_links_tenant",
    "idx_sessions_tenant",
)
TENANT_INDEX_TARGETS: dict[str, str] = {
    "idx_memories_tenant": "memories(tenant_id, is_active, is_archived)",
    "idx_links_tenant": "concept_links(tenant_id, source_memory_id, link_type)",
    "idx_sessions_tenant": "query_sessions(tenant_id, concluded, created_at)",
}
PRE_TENANCY_SCHEMA: Path = Path(__file__).parent / "fixtures" / "pre_tenancy_schema.sql"
SCHEMA_SQL: Path = Path(__file__).parent.parent / "src" / "mintmory" / "core" / "schema.sql"

SEED_SQL = """
INSERT INTO memories (id, content, category, created_at, updated_at) VALUES
    ('m1', 'Alice works at Acme', 'fact', '2026-01-01T00:00:00', '2026-01-01T00:00:00'),
    ('m2', 'Bob works at Acme', 'fact', '2026-01-01T00:00:00', '2026-01-01T00:00:00');

INSERT INTO concept_links
    (id, source_memory_id, target_memory_id, link_type, created_at, updated_at)
VALUES
    ('l1', 'm1', 'm2', 'relates_to', '2026-01-01T00:00:00', '2026-01-01T00:00:00');

INSERT INTO memory_summaries (id, concept, summary_text, generated_at)
VALUES ('s1', 'acme', 'Acme summary', '2026-01-01T00:00:00');

INSERT INTO index_manifest (path, collection, size, mtime, last_seen)
VALUES ('/a', 'collection', 10, 1.0, '2026-01-01T00:00:00');

INSERT INTO query_sessions (id, query_text, created_at)
VALUES ('q1', 'who works at Acme?', '2026-01-01T00:00:00');

INSERT INTO query_results (session_id, memory_id)
VALUES ('q1', 'm1');
"""


def _create_pre_tenancy_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(PRE_TENANCY_SCHEMA.read_text())
        conn.executescript(SEED_SQL)
        conn.commit()
    finally:
        conn.close()


def _pragma_int(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute(f"PRAGMA {name}").fetchone()
    assert row is not None
    return int(row[0])


def _table_info(conn: sqlite3.Connection, table: str) -> list[tuple[Any, ...]]:
    return [
        (row["cid"], row["name"], row["type"], row["notnull"], row["dflt_value"], row["pk"])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    ]


def _column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _index_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    }


def _unique_index_columns(conn: sqlite3.Connection, table: str) -> set[tuple[str, ...]]:
    result: set[tuple[str, ...]] = set()
    for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if not index["unique"]:
            continue
        columns = tuple(
            str(row["name"])
            for row in conn.execute(f"PRAGMA index_info({index['name']})").fetchall()
        )
        result.add(columns)
    return result


def _foreign_keys(conn: sqlite3.Connection, table: str) -> list[tuple[Any, ...]]:
    return sorted(
        (
            row["id"],
            row["seq"],
            row["table"],
            row["from"],
            row["to"],
            row["on_update"],
            row["on_delete"],
            row["match"],
        )
        for row in conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    )


def _schema_snapshot(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    return sorted(
        (str(row["type"]), str(row["name"]), str(row["sql"] or ""))
        for row in conn.execute("SELECT type, name, sql FROM sqlite_master").fetchall()
    )


def _row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in SIX_TENANT_TABLES:
        row = conn.execute(f"SELECT count(*) AS c FROM {table}").fetchone()
        assert row is not None
        counts[table] = int(row["c"])
    return counts


# ---------------------------------------------------------------------------
# Requirement 3.1 — initialise() runs the tenant migration
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-879ba6ee")
def test_initialise_runs_tenant_migration_after_index_mode_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    real_vision = SqliteBackend._ensure_index_mode_vision

    def record_vision(self: SqliteBackend, conn: sqlite3.Connection) -> None:
        calls.append("vision")
        real_vision(self, conn)

    def record_tenants(self: SqliteBackend, conn: sqlite3.Connection) -> None:
        calls.append("tenants")

    monkeypatch.setattr(SqliteBackend, "_ensure_index_mode_vision", record_vision)
    monkeypatch.setattr(SqliteBackend, "_ensure_tenant_columns", record_tenants)

    SqliteBackend(":memory:").initialise()

    assert calls == ["vision", "tenants"]


# ---------------------------------------------------------------------------
# Requirement 3.2 — the migration plan
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-e80f6d60")
def test_plan_right_after_schema_on_a_new_file_is_the_three_tenant_indexes(
    tmp_path: Path,
) -> None:
    backend = SqliteBackend(tmp_path / "fresh.db")
    conn = backend.connect()
    conn.executescript(SCHEMA_SQL.read_text())
    conn.commit()

    statements = backend._tenant_migration_statements(conn)

    assert len(statements) == 3
    normalized = [" ".join(statement.split()).rstrip(";") for statement in statements]
    for name, target in TENANT_INDEX_TARGETS.items():
        assert any(
            statement.startswith(f"CREATE INDEX IF NOT EXISTS {name}") and target in statement
            for statement in normalized
        ), statements
    assert all(statement.upper().startswith("CREATE INDEX") for statement in normalized)

    backend.initialise()
    assert backend._tenant_migration_statements(conn) == []


@pytest.mark.l4("C-e80f6d60")
def test_plan_adds_columns_before_rebuilds_before_indexes(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    _create_pre_tenancy_db(path)
    backend = SqliteBackend(path)
    conn = backend.connect()

    statements = backend._tenant_migration_statements(conn)
    normalized = [" ".join(statement.split()) for statement in statements]

    alter_positions = [
        index for index, statement in enumerate(normalized) if "ADD COLUMN tenant_id" in statement
    ]
    assert len(alter_positions) == 6
    altered_tables = {
        statement.split("ALTER TABLE", 1)[1].split()[0].strip('"')
        for statement in normalized
        if "ADD COLUMN tenant_id" in statement
    }
    assert altered_tables == set(SIX_TENANT_TABLES)

    create_positions = [
        index
        for index, statement in enumerate(normalized)
        if "CREATE TABLE" in statement and "__tenant_new" in statement
    ]
    assert len(create_positions) == len(REBUILT_TABLES)
    rebuilt_tables = {
        statement.split("CREATE TABLE", 1)[1].split()[0].split("__tenant_new")[0].strip('"')
        for statement in normalized
        if "CREATE TABLE" in statement and "__tenant_new" in statement
    }
    assert rebuilt_tables == set(REBUILT_TABLES)
    assert max(alter_positions) < min(create_positions)

    tenant_index_positions = [
        index
        for index, statement in enumerate(normalized)
        if any(
            statement.upper().startswith(f"CREATE INDEX IF NOT EXISTS {name.upper()}")
            for name in TENANT_INDEXES
        )
    ]
    assert tenant_index_positions == [len(statements) - 3, len(statements) - 2, len(statements) - 1]


# ---------------------------------------------------------------------------
# Requirement 3.3 — plan without a lock, re-computed inside BEGIN IMMEDIATE
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-557d75d1")
def test_ensure_tenant_columns_returns_on_an_empty_plan_without_a_transaction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = SqliteBackend(tmp_path / "empty-plan.db")
    backend.initialise()
    conn = backend.connect()
    calls: list[int] = []

    def empty_plan(self: SqliteBackend, inner: sqlite3.Connection) -> list[str]:
        calls.append(1)
        return []

    monkeypatch.setattr(SqliteBackend, "_tenant_migration_statements", empty_plan)
    backend._ensure_tenant_columns(conn)

    assert calls == [1]
    assert not conn.in_transaction


@pytest.mark.l4("C-557d75d1")
def test_ensure_tenant_columns_recomputes_the_plan_inside_the_transaction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = SqliteBackend(tmp_path / "recompute.db")
    conn = backend.connect()
    plans = [
        ["CREATE TABLE first_plan_marker (value TEXT)"],
        ["CREATE TABLE second_plan_marker (value TEXT)"],
    ]
    calls: list[int] = []
    observed: list[tuple[bool, int]] = []

    def plan(self: SqliteBackend, inner: sqlite3.Connection) -> list[str]:
        calls.append(1)
        observed.append((inner.in_transaction, _pragma_int(inner, "foreign_keys")))
        return plans[len(calls) - 1]

    monkeypatch.setattr(SqliteBackend, "_tenant_migration_statements", plan)
    backend._ensure_tenant_columns(conn)

    assert len(calls) == 2
    assert observed[0] == (False, 1)
    assert observed[1] == (True, 0)
    tables = {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    assert "second_plan_marker" in tables
    assert "first_plan_marker" not in tables
    assert _pragma_int(conn, "foreign_keys") == 1
    assert not conn.in_transaction


@pytest.mark.l4("C-557d75d1")
def test_ensure_tenant_columns_executes_nothing_when_the_second_plan_is_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = SqliteBackend(tmp_path / "empty-second.db")
    conn = backend.connect()
    plans = [["CREATE TABLE stale_plan_marker (value TEXT)"], []]
    calls: list[int] = []

    def plan(self: SqliteBackend, inner: sqlite3.Connection) -> list[str]:
        calls.append(1)
        return plans[len(calls) - 1]

    monkeypatch.setattr(SqliteBackend, "_tenant_migration_statements", plan)
    backend._ensure_tenant_columns(conn)

    assert len(calls) == 2
    tables = {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    assert "stale_plan_marker" not in tables
    assert _pragma_int(conn, "foreign_keys") == 1
    assert not conn.in_transaction


# ---------------------------------------------------------------------------
# Requirements 3.4 and 3.7 — fail closed and roll back
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-44253807", "C-c9473b02")
def test_failed_migration_rolls_back_and_raises_tenant_migration_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "legacy.db"
    _create_pre_tenancy_db(path)
    backend = SqliteBackend(path)
    conn = backend.connect()
    counts_before = _row_counts(conn)
    memory_info_before = _table_info(conn, "memories")
    real = SqliteBackend._tenant_migration_statements

    def broken(self: SqliteBackend, inner: sqlite3.Connection) -> list[str]:
        statements = real(self, inner)
        return statements[:1] + ["ALTER TABLE no_such_table ADD COLUMN x TEXT"] + statements[1:]

    monkeypatch.setattr(SqliteBackend, "_tenant_migration_statements", broken)

    with pytest.raises(TenantMigrationError):
        backend.initialise()

    after = backend.connect()
    assert _row_counts(after) == counts_before
    assert _table_info(after, "memories") == memory_info_before
    assert "tenant_id" not in _column_names(after, "memories")
    assert _pragma_int(after, "foreign_keys") == 1


# ---------------------------------------------------------------------------
# Requirement 3.5 — a second start is a no-op
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-00ad76d3", "C-e80f6d60")
def test_second_initialise_returns_an_empty_plan_and_changes_no_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.db"
    _create_pre_tenancy_db(path)
    backend = SqliteBackend(path)
    conn = backend.connect()

    before_plan = backend._tenant_migration_statements(conn)
    assert before_plan
    assert "tenant_id" not in _column_names(conn, "memories")

    backend.initialise()
    assert backend._tenant_migration_statements(conn) == []
    schema_after_first = _schema_snapshot(conn)
    counts_after_first = _row_counts(conn)

    backend.initialise()
    assert _schema_snapshot(conn) == schema_after_first
    assert _row_counts(conn) == counts_after_first


# ---------------------------------------------------------------------------
# Requirement 3.6 — a pre-feature database migrates and matches a fresh one
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2710c07f", "C-00ad76d3")
def test_pre_tenancy_database_migrates_rows_and_matches_a_fresh_database(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "legacy.db"
    _create_pre_tenancy_db(legacy_path)
    backend = SqliteBackend(legacy_path)
    counts_before = _row_counts(backend.connect())

    backend.initialise()
    conn = backend.connect()

    for table in SIX_TENANT_TABLES:
        columns = _column_names(conn, table)
        assert "tenant_id" in columns, table
        assert columns[-1] == "tenant_id", table
    assert _row_counts(conn) == counts_before

    memory = backend.get_memory("m1")
    assert memory is not None
    assert memory.tenant_id == "global"

    links = backend.get_links("m1")
    assert len(links) == 1
    assert links[0].tenant_id == "global"

    summary = backend.get_summary("acme")
    assert summary is not None
    assert summary.tenant_id == "global"

    manifest = backend.manifest_get("/a")
    assert manifest is not None
    assert manifest["tenant_id"] == "global"

    session = backend.get_session("q1")
    assert session is not None
    assert session.tenant_id == "global"

    assert set(TENANT_INDEXES).issubset(_index_names(conn))

    fresh = SqliteBackend(tmp_path / "fresh.db")
    fresh.initialise()
    fresh_conn = fresh.connect()

    for table in SIX_TENANT_TABLES:
        assert _table_info(conn, table) == _table_info(fresh_conn, table), table
    for table in REBUILT_TABLES:
        assert _unique_index_columns(conn, table) == _unique_index_columns(fresh_conn, table), table
        assert _foreign_keys(conn, table) == _foreign_keys(fresh_conn, table), table

    assert not any(row[2] == "tenants" for row in _foreign_keys(conn, "memories"))


# ---------------------------------------------------------------------------
# Requirement 3.8 — a concurrent start never replays a stale plan
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-b58c85ff")
def test_concurrent_start_recomputes_the_plan_inside_the_transaction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "legacy.db"
    _create_pre_tenancy_db(path)

    backend_a = SqliteBackend(path)
    backend_b = SqliteBackend(path)
    stale_plan = backend_b._tenant_migration_statements(backend_b.connect())
    assert stale_plan
    counts_before = _row_counts(backend_a.connect())
    backend_a.initialise()

    real = SqliteBackend._tenant_migration_statements
    calls: list[int] = []

    def stale_then_real(self: SqliteBackend, conn: sqlite3.Connection) -> list[str]:
        calls.append(1)
        if len(calls) == 1:
            return list(stale_plan)
        return real(self, conn)

    monkeypatch.setattr(SqliteBackend, "_tenant_migration_statements", stale_then_real)
    backend_b.initialise()

    assert len(calls) >= 2
    conn_b = backend_b.connect()
    for table in SIX_TENANT_TABLES:
        assert "tenant_id" in _column_names(conn_b, table), table
    assert _row_counts(conn_b) == counts_before
    assert backend_b._tenant_migration_statements(conn_b) == []
