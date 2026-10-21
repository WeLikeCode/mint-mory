"""Full-gate tests for task 6 — requirement 6.1.

R6.1: the gates declared in ``.l4/config.yaml`` keep the 80% coverage floor and
their lint/typecheck commands exit 0, and the Postgres write work is exercised
on the fake pool so no test needs Postgres, Docker or a network service.
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
from mintmory.core.types import MemoryCategory, MemoryRecord

from packages.core.tests.pg_fakes import FakeConnection, FakePool

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / ".l4" / "config.yaml"
PYPROJECT_PATH = ROOT / "pyproject.toml"


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


def _active(sql: str, params: Any) -> list[Any]:
    """The fake write guard: every tenant is active, every other query is empty."""
    if sql.lstrip().startswith("SELECT is_active FROM tenants"):
        return [{"is_active": True}]
    return []


@pytest.mark.l4("C-8b29b13f")
def test_writes_gate_config_declares_required_commands_and_coverage_floor() -> None:
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


@pytest.mark.l4("C-8b29b13f")
def test_writes_gate_lint_and_typecheck_commands_pass() -> None:
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


@pytest.mark.l4("C-8b29b13f")
def test_writes_gate_work_runs_on_the_fake_pool_without_a_live_service() -> None:
    conn = FakeConnection(responder=_active)
    pool = FakePool(conn)
    backend = PostgresBackend("postgresql://unused")
    backend._pool = pool
    record = MemoryRecord(
        content="a guarded Postgres write must run on the fake pool",
        category=MemoryCategory.FACT,
        tenant_id="t1",
    )

    backend.add_memory(record)

    assert pool.checkouts == 1
    executed = list(conn.executed)
    assert any(sql.lstrip().startswith("SELECT is_active FROM tenants") for sql, _ in executed)
    inserts = [
        (sql, params) for sql, params in executed if sql.lstrip().startswith("INSERT INTO memories")
    ]
    assert len(inserts) == 1
    assert "t1" in inserts[0][1]
    assert conn.commits == 1
    assert conn.rollbacks == 0
