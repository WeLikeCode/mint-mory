"""RED tests for task 3 — the in-place Postgres tenant migration.

They trace requirements 2.1–2.4: the pure migration plan, the catalog snapshot
adapter, the call from ``initialise()`` inside its advisory-locked transaction,
and the failure path that rolls the transaction back through
``TenantMigrationError``.  No Postgres is needed: catalog rows are the dicts a
``dict_row`` cursor returns, and the connection/pool are the fakes of
``pg_fakes``.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from mintmory.core.storage_postgres import (
    PostgresBackend,
    pg_catalog_snapshot,
    plan_pg_tenant_migration,
)
from mintmory.core.types import TenantMigrationError

from packages.core.tests.pg_fakes import FakeConnection, FakePool

TENANT_TABLES: tuple[str, ...] = (
    "memories",
    "concept_links",
    "memory_summaries",
    "index_manifest",
    "query_sessions",
    "query_results",
)

_OLD_LINK_UNIQUE = "concept_links_source_memory_id_target_memory_id_link_type_key"
_OLD_SUMMARY_UNIQUE = "memory_summaries_concept_key"
_OLD_MANIFEST_PK = "index_manifest_pkey"

ADD_COLUMN_STATEMENTS: list[str] = [
    f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'global' "
    "REFERENCES tenants(id)"
    for table in TENANT_TABLES
]
KEY_STATEMENTS: list[str] = [
    f'ALTER TABLE concept_links DROP CONSTRAINT "{_OLD_LINK_UNIQUE}"',
    "ALTER TABLE concept_links ADD CONSTRAINT concept_links_tenant_unique UNIQUE "
    "(tenant_id, source_memory_id, target_memory_id, link_type)",
    f'ALTER TABLE memory_summaries DROP CONSTRAINT "{_OLD_SUMMARY_UNIQUE}"',
    "ALTER TABLE memory_summaries ADD CONSTRAINT memory_summaries_tenant_concept_key "
    "UNIQUE (tenant_id, concept)",
    f'ALTER TABLE index_manifest DROP CONSTRAINT "{_OLD_MANIFEST_PK}"',
    "ALTER TABLE index_manifest ADD PRIMARY KEY (tenant_id, path)",
]
TENANT_INDEX_STATEMENTS: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_memories_tenant "
    "ON memories (tenant_id, is_active, is_archived)",
    "CREATE INDEX IF NOT EXISTS idx_links_tenant "
    "ON concept_links (tenant_id, source_memory_id, link_type)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_tenant "
    "ON query_sessions (tenant_id, concluded, created_at)",
]
FULL_PLAN: list[str] = [*ADD_COLUMN_STATEMENTS, *KEY_STATEMENTS, *TENANT_INDEX_STATEMENTS]

PRE_FEATURE_COLUMNS: dict[str, set[str]] = {
    "memories": {"id", "content", "category"},
    "concept_links": {"id", "source_memory_id", "target_memory_id", "link_type"},
    "memory_summaries": {"id", "concept", "summary_text"},
    "index_manifest": {"path", "collection"},
    "query_sessions": {"id", "query_text"},
    "query_results": {"session_id", "memory_id"},
}
MIGRATED_COLUMNS: dict[str, set[str]] = {
    table: {*columns, "tenant_id"} for table, columns in PRE_FEATURE_COLUMNS.items()
}
OLD_UNIQUES: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "concept_links": [(_OLD_LINK_UNIQUE, ("source_memory_id", "target_memory_id", "link_type"))],
    "memory_summaries": [(_OLD_SUMMARY_UNIQUE, ("concept",))],
}
OLD_PRIMARY_KEYS: dict[str, tuple[str, tuple[str, ...]]] = {
    "index_manifest": (_OLD_MANIFEST_PK, ("path",))
}
NEW_UNIQUES: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "concept_links": [
        (
            "concept_links_tenant_unique",
            ("tenant_id", "source_memory_id", "target_memory_id", "link_type"),
        )
    ],
    "memory_summaries": [("memory_summaries_tenant_concept_key", ("tenant_id", "concept"))],
}
NEW_PRIMARY_KEYS: dict[str, tuple[str, tuple[str, ...]]] = {
    "index_manifest": (_OLD_MANIFEST_PK, ("tenant_id", "path"))
}
TENANT_INDEXES: set[str] = {
    "idx_memories_tenant",
    "idx_links_tenant",
    "idx_sessions_tenant",
}

_PRE_COLUMN_ROWS: list[dict[str, Any]] = [
    {"table_name": table, "column_name": column}
    for table, columns in PRE_FEATURE_COLUMNS.items()
    for column in sorted(columns)
]
_PRE_CONSTRAINT_ROWS: list[dict[str, Any]] = [
    {
        "table_name": "concept_links",
        "conname": _OLD_LINK_UNIQUE,
        "contype": "u",
        "columns": ["source_memory_id", "target_memory_id", "link_type"],
    },
    {
        "table_name": "memory_summaries",
        "conname": _OLD_SUMMARY_UNIQUE,
        "contype": "u",
        "columns": ["concept"],
    },
    {
        "table_name": "index_manifest",
        "conname": _OLD_MANIFEST_PK,
        "contype": "p",
        "columns": ["path"],
    },
]
_PRE_INDEX_ROWS: list[dict[str, Any]] = [
    {"indexname": "idx_memories_fts"},
    {"indexname": "idx_memories_trgm"},
]


def _normalise(statement: str) -> str:
    return re.sub(r"\s+", " ", statement).strip().rstrip(";")


def _normalise_all(statements: list[str]) -> list[str]:
    return [_normalise(statement) for statement in statements]


def _catalog_responder(sql: str, params: Any) -> list[Any]:
    lowered = sql.lower()
    if "information_schema.columns" in lowered:
        return _PRE_COLUMN_ROWS
    if "pg_constraint" in lowered:
        return _PRE_CONSTRAINT_ROWS
    if "pg_indexes" in lowered:
        return _PRE_INDEX_ROWS
    return []


def _backend_with(conn: FakeConnection) -> PostgresBackend:
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)
    return backend


# ---------------------------------------------------------------------------
# Requirement 2.1 — the pure plan
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3b4448d0", "C-e1fe91f9")
def test_plan_pre_feature_snapshot_yields_fifteen_statements_in_order() -> None:
    statements = plan_pg_tenant_migration(PRE_FEATURE_COLUMNS, OLD_UNIQUES, OLD_PRIMARY_KEYS, set())

    assert _normalise_all(statements) == _normalise_all(FULL_PLAN)
    assert len(statements) == 15


@pytest.mark.l4("C-3b4448d0", "C-e1fe91f9")
def test_plan_migrated_snapshot_is_empty_and_old_keys_with_columns_are_partial() -> None:
    assert (
        plan_pg_tenant_migration(MIGRATED_COLUMNS, NEW_UNIQUES, NEW_PRIMARY_KEYS, TENANT_INDEXES)
        == []
    )

    partial = plan_pg_tenant_migration(MIGRATED_COLUMNS, OLD_UNIQUES, OLD_PRIMARY_KEYS, set())
    assert _normalise_all(partial) == _normalise_all([*KEY_STATEMENTS, *TENANT_INDEX_STATEMENTS])
    assert len(partial) == 9


@pytest.mark.l4("C-3b4448d0")
def test_plan_missing_key_entries_add_new_keys_without_dropping_anything() -> None:
    statements = plan_pg_tenant_migration(MIGRATED_COLUMNS, {}, {}, set())

    expected = [
        "ALTER TABLE concept_links ADD CONSTRAINT concept_links_tenant_unique UNIQUE "
        "(tenant_id, source_memory_id, target_memory_id, link_type)",
        "ALTER TABLE memory_summaries ADD CONSTRAINT memory_summaries_tenant_concept_key "
        "UNIQUE (tenant_id, concept)",
        "ALTER TABLE index_manifest ADD PRIMARY KEY (tenant_id, path)",
        *TENANT_INDEX_STATEMENTS,
    ]
    assert _normalise_all(statements) == _normalise_all(expected)
    assert not any("DROP CONSTRAINT" in statement for statement in statements)


# ---------------------------------------------------------------------------
# Requirement 2.2 — catalog snapshot and execution from the backend
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-38951bfc", "C-e1fe91f9")
def test_pg_catalog_snapshot_turns_dict_rows_into_plan_inputs() -> None:
    columns, uniques, primary_keys, indexes = pg_catalog_snapshot(
        _PRE_COLUMN_ROWS, _PRE_CONSTRAINT_ROWS, _PRE_INDEX_ROWS
    )

    assert columns == PRE_FEATURE_COLUMNS
    assert uniques == OLD_UNIQUES
    assert primary_keys == OLD_PRIMARY_KEYS
    assert indexes == {"idx_memories_fts", "idx_memories_trgm"}

    assert _normalise_all(plan_pg_tenant_migration(columns, uniques, primary_keys, indexes)) == (
        _normalise_all(FULL_PLAN)
    )


@pytest.mark.l4("C-38951bfc")
def test_ensure_tenant_columns_reads_the_catalog_and_executes_the_plan() -> None:
    conn = FakeConnection(responder=_catalog_responder)
    backend = _backend_with(conn)

    backend._ensure_tenant_columns(conn)

    executed = [sql for sql, _params in conn.executed]
    catalog_positions = [
        position
        for position, sql in enumerate(executed)
        if any(
            marker in sql.lower()
            for marker in ("information_schema.columns", "pg_constraint", "pg_indexes")
        )
    ]
    assert len(catalog_positions) == 3
    catalog_sql = [executed[position].lower() for position in catalog_positions]
    assert "information_schema.columns" in catalog_sql[0]
    assert "current_schema()" in catalog_sql[0]
    assert "pg_constraint" in catalog_sql[1]
    assert "contype in ('u', 'p')" in catalog_sql[1]
    assert "pg_indexes" in catalog_sql[2]
    assert "current_schema()" in catalog_sql[2]

    plan_start = max(catalog_positions) + 1
    plan_sql = _normalise_all(executed[plan_start : plan_start + len(FULL_PLAN)])
    assert plan_sql == _normalise_all(FULL_PLAN)


@pytest.mark.l4("C-38951bfc", "C-e1fe91f9")
def test_initialise_runs_ddl_catalog_and_plan_in_the_advisory_locked_transaction() -> None:
    conn = FakeConnection(responder=_catalog_responder)
    backend = _backend_with(conn)

    backend.initialise()

    executed = [sql for sql, _params in conn.executed]
    lock_position = next(
        position for position, sql in enumerate(executed) if "pg_advisory_xact_lock" in sql
    )
    assert "CREATE TABLE IF NOT EXISTS tenants" in executed[lock_position + 1]

    catalog_positions = [
        position
        for position, sql in enumerate(executed)
        if position > lock_position
        and any(
            marker in sql.lower()
            for marker in ("information_schema.columns", "pg_constraint", "pg_indexes")
        )
    ]
    assert len(catalog_positions) == 3
    assert catalog_positions[0] > lock_position + 1

    plan_start = max(catalog_positions) + 1
    plan_sql = _normalise_all(executed[plan_start : plan_start + len(FULL_PLAN)])
    assert plan_sql == _normalise_all(FULL_PLAN)
    assert conn.commits >= 1
    assert conn.rollbacks == 0


# ---------------------------------------------------------------------------
# Requirement 2.3 — failures inside the pool block roll back and fail closed
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-8b92f6fb")
def test_initialise_wraps_migration_failures_and_rolls_back() -> None:
    conn = FakeConnection(
        responder=_catalog_responder,
        fail_on=lambda sql: sql.startswith("ALTER TABLE"),
    )
    backend = _backend_with(conn)

    with pytest.raises(TenantMigrationError) as raised:
        backend.initialise()

    assert "fake failure" in str(raised.value)
    assert conn.rollbacks == 1
    # Only the extension probe commits before the advisory-locked transaction;
    # the failed migration must not commit after it.
    assert conn.commits == 1


@pytest.mark.l4("C-8b92f6fb")
def test_initialise_wraps_catalog_failures_but_propagates_lock_failures() -> None:
    def exploding_responder(sql: str, params: Any) -> list[Any]:
        if "information_schema.columns" in sql.lower():
            raise RuntimeError("catalog unavailable")
        return []

    catalog_conn = FakeConnection(responder=exploding_responder)
    catalog_backend = _backend_with(catalog_conn)

    with pytest.raises(TenantMigrationError) as raised:
        catalog_backend.initialise()
    assert "catalog unavailable" in str(raised.value)
    assert catalog_conn.rollbacks == 1

    lock_conn = FakeConnection(fail_on=lambda sql: "pg_advisory_xact_lock" in sql)
    lock_backend = _backend_with(lock_conn)

    with pytest.raises(RuntimeError) as lock_raised:
        lock_backend.initialise()
    assert not isinstance(lock_raised.value, TenantMigrationError)
    assert lock_conn.rollbacks == 1
