"""Full-gate tests for task 5 — requirement 5.1.

R5.1: the gates declared in ``.l4/config.yaml`` (``ruff check``,
``ruff format --check``, ``mypy packages`` and ``pytest`` with the 80% coverage
floor) pass, and the tenant-scoped Postgres reads are exercised on the fake pool
so no test needs Postgres, Docker or a network service.
"""

from __future__ import annotations

import shlex
import subprocess
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from mintmory.core.storage_postgres import PostgresBackend

from packages.core.tests.pg_fakes import FakeConnection, FakePool

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / ".l4" / "config.yaml"
PYPROJECT_PATH = ROOT / "pyproject.toml"
TESTS = ROOT / "packages" / "core" / "tests"

READ_TEST_FILES: tuple[Path, ...] = (
    TESTS / "test_pg_tenancy_reads.py",
    TESTS / "test_pg_tenancy_search.py",
    TESTS / "test_pg_tenancy_list_reads.py",
    TESTS / "conformance" / "test_conformance_tenancy_reads.py",
)


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


@pytest.mark.l4("C-f4fb9aab")
def test_reads_full_gate_declares_required_commands_and_coverage_floor() -> None:
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
    coverage_tokens = [token for token in addopts.split() if token.startswith("--cov-fail-under=")]
    assert coverage_tokens, "the pytest addopts keep no coverage floor"
    assert int(coverage_tokens[0].split("=", 1)[1]) >= 80


@pytest.mark.l4("C-f4fb9aab")
def test_reads_full_gate_lint_and_typecheck_commands_pass() -> None:
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


@pytest.mark.l4("C-f4fb9aab")
def test_reads_full_gate_tenant_read_runs_on_the_fake_pool() -> None:
    def respond(sql: str, params: Any) -> list[Any]:
        if "FROM memories WHERE id = %s" in " ".join(sql.split()):
            return [_memory_row("a1", "t1")]
        return []

    conn = FakeConnection(responder=respond)
    pool = FakePool(conn)
    backend = PostgresBackend("postgresql://unused")
    backend._pool = pool

    memory = backend.get_memory("a1", tenant_id="t1")

    assert memory is not None
    assert memory.id == "a1"
    assert memory.content == "a1 mentions Alice"
    assert memory.tenant_id == "t1"

    statements = [(" ".join(sql.split()), tuple(params or ())) for sql, params in conn.executed]
    assert any("tenant_id = %s" in sql and params == ("a1", "t1") for sql, params in statements)
    assert pool.checkouts == 1
    assert conn.rollbacks == 0


@pytest.mark.l4("C-f4fb9aab")
def test_reads_full_gate_needs_no_external_service_and_adds_no_skips() -> None:
    gates = _gate_section()
    setup = _strings(gates.get("setup"), "gates.setup")
    assert setup == ["uv sync --frozen --extra cochange --extra otel --extra postgres"]

    for path in READ_TEST_FILES:
        assert path.is_file(), f"missing the unit's read test file: {path}"
        source = path.read_text(encoding="utf-8")
        assert "psycopg.connect" not in source, f"{path.name} opens a live Postgres connection"
        assert "pytest.skip(" not in source, f"{path.name} skips a read test"
        assert "pytest.mark.skip" not in source, f"{path.name} marks a read test skipped"
        assert "pytest.mark.xfail" not in source, f"{path.name} marks a read test xfail"
