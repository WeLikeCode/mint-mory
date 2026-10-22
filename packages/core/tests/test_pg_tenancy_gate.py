"""Full-gate tests for task 6 — requirements 6.1 and 6.2.

R6.1: the gates declared in ``.l4/config.yaml`` keep the 80% coverage floor and
their lint/typecheck commands exit 0, and the Postgres work is exercised on the
fake pool so no test needs Postgres, Docker or a network service.  R6.2: on a
real database the supplementary ``conformance-pg`` job runs ``initialise()``'s
catalog reads; a brand-new database gets exactly the three tenant indexes from
the plan, and a second start finds nothing left to migrate.
"""

from __future__ import annotations

import shlex
import subprocess
import tomllib
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from mintmory.core.storage_postgres import PostgresBackend

from packages.core.tests.pg_fakes import FakeConnection, FakePool

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / ".l4" / "config.yaml"
PYPROJECT_PATH = ROOT / "pyproject.toml"

TENANT_TABLES: tuple[str, ...] = (
    "memories",
    "concept_links",
    "memory_summaries",
    "index_manifest",
    "query_sessions",
    "query_results",
)

TENANT_INDEX_STATEMENTS: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_memories_tenant "
    "ON memories (tenant_id, is_active, is_archived)",
    "CREATE INDEX IF NOT EXISTS idx_links_tenant "
    "ON concept_links (tenant_id, source_memory_id, link_type)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_tenant "
    "ON query_sessions (tenant_id, concluded, created_at)",
)
TENANT_INDEX_NAMES: frozenset[str] = frozenset(
    {"idx_memories_tenant", "idx_links_tenant", "idx_sessions_tenant"}
)

_CONSTRAINT_ROWS: list[dict[str, Any]] = [
    {
        "table_name": "concept_links",
        "conname": "concept_links_tenant_unique",
        "contype": "u",
        "columns": ["tenant_id", "source_memory_id", "target_memory_id", "link_type"],
    },
    {
        "table_name": "memory_summaries",
        "conname": "memory_summaries_tenant_concept_key",
        "contype": "u",
        "columns": ["tenant_id", "concept"],
    },
    {
        "table_name": "index_manifest",
        "conname": "index_manifest_pkey",
        "contype": "p",
        "columns": ["tenant_id", "path"],
    },
]


class _CatalogState:
    """Answer the catalog reads as a fresh DDL database that may gain indexes."""

    def __init__(self, indexes: set[str] | None = None) -> None:
        self.indexes = set(indexes or ())

    def __call__(self, sql: str, params: Any) -> list[Any]:
        lowered = sql.lower()
        if "information_schema.columns" in lowered:
            return [{"table_name": table, "column_name": "tenant_id"} for table in TENANT_TABLES]
        if "pg_constraint" in lowered:
            return _CONSTRAINT_ROWS
        if "pg_indexes" in lowered:
            return [{"indexname": name} for name in sorted(self.indexes)]
        return []


def _gate_section() -> dict[str, Any]:
    loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    config = cast("dict[str, Any]", loaded)
    gates = config.get("gates")
    assert isinstance(gates, dict)
    return cast("dict[str, Any]", gates)


def _strings(value: object, name: str) -> list[str]:
    assert isinstance(value, list), f"{name} is not a list"
    items: list[str] = []
    for item in value:
        assert isinstance(item, str), f"{name} contains a non-string"
        items.append(item)
    return items


def _is_catalog_read(sql: str) -> bool:
    lowered = sql.lower()
    return any(
        marker in lowered
        for marker in ("information_schema.columns", "pg_constraint", "pg_indexes")
    )


def _statements_after_last_catalog_read(executed: list[tuple[str, Any]]) -> list[str]:
    positions = [
        position for position, (sql, _params) in enumerate(executed) if _is_catalog_read(sql)
    ]
    assert positions, "initialise() did not read the catalog"
    return [
        sql for sql, _params in executed[max(positions) + 1 :] if "pg_extension" not in sql.lower()
    ]


@pytest.mark.l4("C-85f83635")
def test_gate_config_declares_required_commands_and_coverage_floor() -> None:
    gates = _gate_section()
    lint = _strings(gates.get("lint"), "gates.lint")
    typecheck = _strings(gates.get("typecheck"), "gates.typecheck")

    assert any("ruff check" in command for command in lint)
    assert any("ruff format --check" in command for command in lint)
    assert any("mypy packages" in command for command in typecheck)

    test_gate = gates.get("test")
    assert isinstance(test_gate, dict)
    test_command = test_gate.get("command")
    assert isinstance(test_command, str)
    assert ".venv/bin/pytest" in test_command
    assert "--junitxml=.l4-out/junit.xml" in test_command

    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    addopts = pyproject["tool"]["pytest"]["ini_options"]["addopts"]
    assert isinstance(addopts, str)
    assert "--cov-fail-under=80" in addopts.split()


@pytest.mark.l4("C-85f83635")
def test_gate_lint_and_typecheck_commands_pass() -> None:
    gates = _gate_section()
    commands = _strings(gates.get("lint"), "gates.lint") + _strings(
        gates.get("typecheck"), "gates.typecheck"
    )
    assert commands

    for command in commands:
        completed = subprocess.run(
            shlex.split(command),
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, (
            f"{command} failed with exit {completed.returncode}\n"
            f"{completed.stdout}\n{completed.stderr}"
        )


@pytest.mark.l4("C-85f83635")
def test_postgres_gate_work_runs_on_the_fake_pool_without_a_live_service() -> None:
    catalog = _CatalogState(indexes=set(TENANT_INDEX_NAMES))
    conn = FakeConnection(responder=catalog)
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)

    backend.initialise()

    executed = [sql for sql, _params in conn.executed]
    assert any("CREATE TABLE IF NOT EXISTS tenants" in sql for sql in executed)
    assert any(sql.startswith("SELECT pg_advisory_xact_lock(") for sql in executed)
    assert conn.commits >= 1
    assert conn.rollbacks == 0


@pytest.mark.l4("C-40adad36")
def test_initialise_first_start_adds_tenant_indexes_and_later_start_finds_none() -> None:
    catalog = _CatalogState()
    conn = FakeConnection(responder=catalog)
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)

    backend.initialise()

    first = list(conn.executed)
    assert len([sql for sql, _params in first if _is_catalog_read(sql)]) == 3
    assert _statements_after_last_catalog_read(first) == list(TENANT_INDEX_STATEMENTS)

    catalog.indexes.update(TENANT_INDEX_NAMES)
    conn.executed.clear()

    backend.initialise()

    later = list(conn.executed)
    assert len([sql for sql, _params in later if _is_catalog_read(sql)]) == 3
    assert _statements_after_last_catalog_read(later) == []
