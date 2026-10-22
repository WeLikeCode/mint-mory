"""Full-gate acceptance for the CLI tenant selector (R7.1).

The unit's final check is the configured gate itself: the pytest run keeps the
80% coverage floor, the CLI package and the integration suite stay in
``testpaths``, and the tenant workflows the unit added keep working against a
real SQLite file with no Postgres, Docker or network service.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from mintmory.cli.main import app
from mintmory.core.storage import SqliteBackend
from typer.testing import CliRunner

runner = CliRunner()

_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture
def gate_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the CLI at an isolated SQLite file under tmp_path."""
    db_path = tmp_path / "cli_tenancy_gate.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("COLUMNS", "200")
    yield db_path


def _open(path: Path) -> SqliteBackend:
    store = SqliteBackend(str(path))
    store.initialise()
    return store


def _created_id(output: str) -> str:
    match = _ID_RE.search(output)
    assert match is not None, output
    return match.group(0)


def _tenant_of(path: Path, memory_id: str) -> str:
    store = _open(path)
    try:
        record = store.get_memory(memory_id)
        assert record is not None
        return record.tenant_id
    finally:
        store.close()


def _gate_configuration() -> dict[str, Any]:
    """Read the coverage floor and test paths from the configured gate."""
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    return cast(dict[str, Any], pyproject["tool"]["pytest"]["ini_options"])


@pytest.mark.l4("C-88762101")
def test_gate_full_cli_tenancy_flow_and_coverage_floor(gate_db: Path, tmp_path: Path) -> None:
    """The gate keeps its coverage floor and the tenant workflows still run end to end."""
    config = Path(".l4/config.yaml").read_text(encoding="utf-8")
    assert ".venv/bin/pytest" in config

    ini_options = _gate_configuration()
    addopts = str(ini_options["addopts"])
    coverage_floor = re.search(r"--cov-fail-under=(\d+)", addopts)
    assert coverage_floor is not None, addopts
    assert int(coverage_floor.group(1)) >= 80, addopts

    testpaths = cast(list[str], ini_options["testpaths"])
    assert "packages/cli/tests" in testpaths
    assert "tests/integration" in testpaths

    created = runner.invoke(app, ["tenant", "create", "acme", "--name", "Acme Corp"])
    assert created.exit_code == 0, created.output
    assert "created tenant 'acme'" in created.output

    listing = runner.invoke(app, ["tenant", "list", "--json"])
    assert listing.exit_code == 0, listing.output
    tenants = cast(list[dict[str, Any]], json.loads(listing.stdout))
    assert [tenant["id"] for tenant in tenants] == ["acme", "global"]
    assert next(tenant for tenant in tenants if tenant["id"] == "acme")["name"] == "Acme Corp"

    acme = runner.invoke(app, ["--tenant", "acme", "add", "Acme uses Postgres"])
    assert acme.exit_code == 0, acme.output
    global_ = runner.invoke(app, ["add", "Global uses SQLite"])
    assert global_.exit_code == 0, global_.output
    assert _tenant_of(gate_db, _created_id(acme.output)) == "acme"
    assert _tenant_of(gate_db, _created_id(global_.output)) == "global"

    scoped = runner.invoke(app, ["--tenant", "acme", "search", "uses"])
    assert scoped.exit_code == 0, scoped.output
    assert "Acme uses Postgres" in scoped.output
    assert "Global uses SQLite" not in scoped.output
    assert "1 result(s)" in scoped.output

    unscoped = runner.invoke(app, ["search", "uses"])
    assert unscoped.exit_code == 0, unscoped.output
    assert "Acme uses Postgres" in unscoped.output
    assert "Global uses SQLite" in unscoped.output

    scoped_stats = runner.invoke(app, ["--tenant", "acme", "stats"])
    assert scoped_stats.exit_code == 0, scoped_stats.output
    assert re.search(r"total_memories[^\n]*\b1\b", scoped_stats.output), scoped_stats.output

    missing_write = runner.invoke(app, ["--tenant", "nope", "add", "x"])
    assert missing_write.exit_code == 1, missing_write.output
    assert "error: tenant 'nope' not found" in missing_write.stderr

    missing_read = runner.invoke(app, ["--tenant", "nope", "search", "x"])
    assert missing_read.exit_code == 0, missing_read.output
    assert "0 result(s)" in missing_read.output

    refusal = runner.invoke(app, ["--tenant", "acme", "index-tree", str(tmp_path)])
    assert refusal.exit_code == 1, refusal.output
    assert "does not support --tenant" in refusal.stderr

    invalid = runner.invoke(app, ["--tenant", "Bad", "stats"])
    assert invalid.exit_code == 1, invalid.output
    assert "invalid tenant id 'Bad'" in invalid.stderr
