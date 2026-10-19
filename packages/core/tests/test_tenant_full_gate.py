"""Full-gate tests for task 8 — requirement 8.1.

The deliverable of R8.1 is that the configured gates (``ruff check``,
``ruff format --check``, ``mypy packages`` and ``pytest`` with the 80% coverage
floor) pass.  These tests pin the gate configuration and execute the lint and
typecheck gates; the end-to-end round trip keeps the criterion discriminating
against a zero-value implementation of the tenancy surface.
"""

from __future__ import annotations

import shlex
import subprocess
import tomllib
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import MemoryCategory, MemoryRecord, MemorySummary

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


@pytest.mark.l4("C-d424e27b")
def test_full_gate_config_declares_every_required_gate() -> None:
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


@pytest.mark.l4("C-d424e27b")
def test_full_gate_lint_and_typecheck_commands_pass() -> None:
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


@pytest.mark.l4("C-d424e27b")
def test_full_gate_tenant_foundation_round_trips(tmp_path: Path) -> None:
    store = SqliteBackend(tmp_path / "gate.db")
    store.initialise()

    assert [tenant.id for tenant in store.list_tenants()] == ["global"]

    acme = store.create_tenant("acme", "Acme")
    assert acme.id == "acme"
    assert acme.name == "Acme"
    assert acme.is_active is True

    record = MemoryRecord(
        content="Alice works at Acme",
        category=MemoryCategory.FACT,
        tenant_id="acme",
    )
    store.add_memory(record)
    fetched = store.get_memory(record.id)
    assert fetched is not None
    assert fetched.content == "Alice works at Acme"
    assert fetched.tenant_id == "acme"

    store.upsert_summary(
        MemorySummary(
            concept="acme",
            summary_text="Acme summary",
            memory_count=1,
            tenant_id="acme",
        )
    )
    summary = store.get_summary("acme", "acme")
    assert summary is not None
    assert summary.summary_text == "Acme summary"
    assert store.get_summary("acme") is None

    store.manifest_upsert(
        "/a",
        "docs",
        size=1,
        mtime=1.0,
        online_only=False,
        index_mode="metadata",
        memory_ids=[record.id],
        tenant_id="acme",
    )
    entry = store.manifest_get("/a", tenant_id="acme")
    assert entry is not None
    assert entry["tenant_id"] == "acme"
    assert entry["collection"] == "docs"
    assert store.manifest_get("/a") is None
