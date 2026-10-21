"""RED tests for task 2 — the multi-tenant Postgres fresh DDL.

They trace requirements 1.1–1.5 of ``schema_postgres.sql``: the ``tenants``
table and its seed row before ``memories``, the ``tenant_id`` column with its
foreign key on all six tables, the per-tenant keys, the absence of any
``tenant_id`` index from the fresh DDL, and the unchanged FTS / trigram
definitions.  The tests are text-only (no Postgres) and read the real schema
through the backend module that ships it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from mintmory.core import storage_postgres

SIX_TENANT_TABLES = (
    "memories",
    "concept_links",
    "memory_summaries",
    "index_manifest",
    "query_sessions",
    "query_results",
)

_TENANT_COLUMN = "tenant_id TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id)"

_CREATE_TABLE_RE = re.compile(
    r"^CREATE TABLE IF NOT EXISTS ([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE | re.IGNORECASE,
)
_CREATE_INDEX_RE = re.compile(
    r"^CREATE (?:UNIQUE )?INDEX\b.*?;",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)
_SEED_RE = re.compile(r"^INSERT INTO tenants\b.*?;", re.MULTILINE | re.DOTALL | re.IGNORECASE)


def _schema_sql() -> str:
    assert storage_postgres.__file__ is not None
    path = Path(storage_postgres.__file__).parent / "schema_postgres.sql"
    return path.read_text(encoding="utf-8")


def _normalise(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _create_table_blocks(sql: str) -> dict[str, str]:
    """Map every ``CREATE TABLE`` name to the text between its parentheses."""
    blocks: dict[str, str] = {}
    for match in _CREATE_TABLE_RE.finditer(sql):
        open_paren = sql.find("(", match.end())
        if open_paren == -1:
            continue
        depth = 0
        for index in range(open_paren, len(sql)):
            char = sql[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    blocks[match.group(1)] = sql[open_paren + 1 : index]
                    break
    return blocks


def _create_index_statements(sql: str) -> list[str]:
    return [match.group(0) for match in _CREATE_INDEX_RE.finditer(sql)]


def _assert_r1_contract(sql: str) -> None:
    table_matches = {match.group(1).lower(): match for match in _CREATE_TABLE_RE.finditer(sql)}
    blocks = _create_table_blocks(sql)
    normalised_blocks = {name.lower(): _normalise(body) for name, body in blocks.items()}

    # R1.1 — tenants DDL and seed precede memories.
    assert "tenants" in normalised_blocks
    assert "memories" in table_matches
    assert table_matches["tenants"].start() < table_matches["memories"].start()
    tenants = normalised_blocks["tenants"]
    assert "id TEXT PRIMARY KEY" in tenants
    assert "name TEXT NOT NULL DEFAULT ''" in tenants
    assert "is_active BOOLEAN NOT NULL DEFAULT TRUE" in tenants
    assert "created_at TIMESTAMP NOT NULL" in tenants
    assert "updated_at TIMESTAMP NOT NULL" in tenants

    seed_match = _SEED_RE.search(sql)
    assert seed_match is not None, "schema_postgres.sql does not seed the tenants table"
    seed = _normalise(seed_match.group(0))
    assert seed == (
        "INSERT INTO tenants (id, name, is_active, created_at, updated_at) "
        "VALUES ('global', 'Global (default) tenant', TRUE, '1970-01-01 00:00:00', "
        "'1970-01-01 00:00:00') ON CONFLICT (id) DO NOTHING;"
    )
    assert table_matches["tenants"].start() < seed_match.start() < table_matches["memories"].start()

    # R1.2 — every table carries the tenant column.
    for table in SIX_TENANT_TABLES:
        assert table in normalised_blocks, f"{table} block missing from schema_postgres.sql"
        assert _TENANT_COLUMN in normalised_blocks[table], table

    # R1.3 — per-tenant keys.
    assert (
        "CONSTRAINT concept_links_tenant_unique UNIQUE "
        "(tenant_id, source_memory_id, target_memory_id, link_type)"
        in normalised_blocks["concept_links"]
    )
    summaries = normalised_blocks["memory_summaries"]
    assert "concept TEXT NOT NULL" in summaries
    assert "CONSTRAINT memory_summaries_tenant_concept_key UNIQUE (tenant_id, concept)" in summaries
    manifest = normalised_blocks["index_manifest"]
    assert "path TEXT NOT NULL" in manifest
    assert "PRIMARY KEY (tenant_id, path)" in manifest

    # R1.4 — no tenant index in the fresh DDL, FTS / trigram untouched.
    index_statements = _create_index_statements(sql)
    assert index_statements
    for statement in index_statements:
        assert "tenant_id" not in statement.lower(), statement
    normalised_sql = _normalise(sql)
    assert (
        "content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
        in normalised_blocks["memories"]
    )
    assert (
        "CREATE INDEX IF NOT EXISTS idx_memories_fts ON memories USING GIN (content_tsv)"
        in normalised_sql
    )
    assert (
        "CREATE INDEX IF NOT EXISTS idx_memories_trgm "
        "ON memories USING GIN (content gin_trgm_ops)" in normalised_sql
    )


@pytest.mark.l4("C-68b825d2")
def test_pg_schema_creates_and_seeds_tenants_before_memories() -> None:
    sql = _schema_sql()
    blocks = _create_table_blocks(sql)

    assert "tenants" in blocks
    assert "memories" in blocks
    assert sql.index("CREATE TABLE IF NOT EXISTS tenants") < sql.index(
        "CREATE TABLE IF NOT EXISTS memories"
    )

    tenants = _normalise(blocks["tenants"])
    assert "id TEXT PRIMARY KEY" in tenants
    assert "name TEXT NOT NULL DEFAULT ''" in tenants
    assert "is_active BOOLEAN NOT NULL DEFAULT TRUE" in tenants
    assert "created_at TIMESTAMP NOT NULL" in tenants
    assert "updated_at TIMESTAMP NOT NULL" in tenants

    seed_match = _SEED_RE.search(sql)
    assert seed_match is not None
    assert _normalise(seed_match.group(0)) == (
        "INSERT INTO tenants (id, name, is_active, created_at, updated_at) "
        "VALUES ('global', 'Global (default) tenant', TRUE, '1970-01-01 00:00:00', "
        "'1970-01-01 00:00:00') ON CONFLICT (id) DO NOTHING;"
    )


@pytest.mark.l4("C-289a314a")
def test_pg_schema_six_tables_declare_tenant_id_reference() -> None:
    blocks = _create_table_blocks(_schema_sql())
    normalised = {name: _normalise(body) for name, body in blocks.items()}

    for table in SIX_TENANT_TABLES:
        assert table in normalised, f"{table} block missing from schema_postgres.sql"
        assert _TENANT_COLUMN in normalised[table], table


@pytest.mark.l4("C-7ab96287")
def test_pg_schema_tenant_keys_replace_global_keys() -> None:
    blocks = {name: _normalise(body) for name, body in _create_table_blocks(_schema_sql()).items()}

    assert (
        "CONSTRAINT concept_links_tenant_unique UNIQUE "
        "(tenant_id, source_memory_id, target_memory_id, link_type)" in blocks["concept_links"]
    )

    summaries = blocks["memory_summaries"]
    assert "concept TEXT NOT NULL" in summaries
    assert "CONSTRAINT memory_summaries_tenant_concept_key UNIQUE (tenant_id, concept)" in summaries

    manifest = blocks["index_manifest"]
    assert "path TEXT NOT NULL" in manifest
    assert "PRIMARY KEY (tenant_id, path)" in manifest


@pytest.mark.l4("C-d01718dd", "C-289a314a")
def test_pg_schema_declares_no_tenant_index_and_keeps_fts_and_trigram() -> None:
    sql = _schema_sql()
    normalised_sql = _normalise(sql)

    # Precondition: the fresh DDL does carry tenant columns, so the absence of
    # a tenant index below is meaningful (the indexes arrive with the in-place
    # migration for databases created before this unit).
    assert _TENANT_COLUMN in normalised_sql

    index_statements = _create_index_statements(sql)
    assert index_statements
    for statement in index_statements:
        assert "tenant_id" not in statement.lower(), statement

    memories = _normalise(_create_table_blocks(sql)["memories"])
    assert (
        "content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
        in memories
    )
    assert (
        "CREATE INDEX IF NOT EXISTS idx_memories_fts ON memories USING GIN (content_tsv)"
        in normalised_sql
    )
    assert (
        "CREATE INDEX IF NOT EXISTS idx_memories_trgm "
        "ON memories USING GIN (content gin_trgm_ops)" in normalised_sql
    )


@pytest.mark.l4("C-2623c583")
def test_pg_schema_parses_every_create_table_block() -> None:
    sql = _schema_sql()
    blocks = _create_table_blocks(sql)

    assert set(blocks) == {"tenants", *SIX_TENANT_TABLES}
    for table, body in blocks.items():
        assert body.strip(), table

    _assert_r1_contract(sql)
