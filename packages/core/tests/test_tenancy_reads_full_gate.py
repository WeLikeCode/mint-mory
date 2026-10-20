"""Full-gate tests for task 7 — requirements 6.1 and 6.2.

R6.1: every existing caller still passes no tenant, so the default reads keep
today's unscoped behaviour over all tenants and the rest of the existing suite
runs unchanged.  R6.2: the gates declared in ``.l4/config.yaml`` exist, keep the
80% coverage floor, and the lint/typecheck commands exit 0 without Postgres,
Docker or a network service.
"""

from __future__ import annotations

import inspect
import shlex
import subprocess
import tomllib
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from mintmory.core.ports import StorageBackend
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import MemoryCategory, MemoryRecord, SearchRequest

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / ".l4" / "config.yaml"
PYPROJECT_PATH = ROOT / "pyproject.toml"

READ_METHODS = (
    "get_memory",
    "search",
    "search_around",
    "get_links",
    "get_annotating_notes",
    "get_annotating_descriptions",
    "find_image_file_record",
    "anchor_candidates",
    "list_image_file_records",
    "list_notes",
    "list_summaries",
    "get_session",
    "get_stats",
    "memory_exists_with_content",
    "get_flagged_memories",
    "get_never_accessed_stale",
    "get_high_staleness_useful",
    "get_anomaly_high_staleness_useful_ids",
    "get_anomaly_never_accessed_ids",
    "get_anomaly_flagged_ids",
    "list_active_memory_ids",
    "get_stale_archivable_ids",
    "get_rehabilitable_rows",
    "get_existing_relates_to_pairs",
    "list_memories",
)


def _signature_problems() -> list[str]:
    """Callers that omit ``tenant_id`` must keep resolving to the unscoped read."""
    problems: list[str] = []
    for cls in (SqliteBackend, StorageBackend):
        for name in READ_METHODS:
            method = getattr(cls, name, None)
            if method is None:
                problems.append(f"{cls.__name__}.{name} is missing")
                continue
            parameters = inspect.signature(method).parameters
            if "tenant_id" not in parameters:
                problems.append(f"{cls.__name__}.{name} has no tenant_id")
            elif parameters["tenant_id"].default is not None:
                problems.append(f"{cls.__name__}.{name} does not default to None")
    return problems


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


@pytest.mark.l4("C-5ed1b587")
def test_tenancy_reads_gate_declares_every_required_command() -> None:
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


@pytest.mark.l4("C-5ed1b587")
def test_tenancy_reads_gate_commands_pass_without_external_services() -> None:
    gates = _gate_section()
    setup = _strings(gates.get("setup"), "gates.setup")
    assert setup == ["uv sync --frozen --extra cochange --extra otel --extra postgres"]

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

    postgres_tests = (ROOT / "packages" / "core" / "tests" / "test_pg_tenancy.py").read_text(
        encoding="utf-8"
    )
    assert 'PostgresBackend("postgresql://unused")' in postgres_tests
    assert "psycopg.connect" not in postgres_tests


@pytest.mark.l4("C-3028dfd4")
def test_existing_read_callers_can_keep_omitting_the_tenant() -> None:
    problems = _signature_problems()
    assert problems == [], (
        f"a caller that omits tenant_id no longer resolves to today's unscoped read: {problems}"
    )


@pytest.mark.l4("C-3028dfd4")
def test_existing_callers_without_a_tenant_keep_unscoped_reads(tmp_path: Path) -> None:
    assert _signature_problems() == []

    store = SqliteBackend(tmp_path / "gate.db")
    store.initialise()
    store.create_tenant("t1")

    g1 = store.add_memory(
        MemoryRecord(
            content="Alice uses Postgres",
            category=MemoryCategory.FACT,
            entity_ids=["Alice"],
        )
    )
    a1 = store.add_memory(
        MemoryRecord(
            content="Alice uses SQLite",
            category=MemoryCategory.FACT,
            tenant_id="t1",
            entity_ids=["Alice"],
        )
    )

    # A caller that passes no tenant sees both tenants' rows, as today.
    assert store.get_memory(g1.id) is not None
    assert store.get_memory(a1.id) is not None
    assert store.memory_exists_with_content("Alice uses Postgres") is True
    assert store.memory_exists_with_content("Alice uses SQLite") is True

    hits = store.search(SearchRequest(query="Alice"))
    assert {memory.id for memory in hits.memories} == {g1.id, a1.id}

    assert hasattr(store, "list_memories"), "the tenant-less list read is missing"
    listed = store.list_memories()
    assert {memory.id for memory in listed} == {g1.id, a1.id}

    stats = store.get_stats()
    assert stats.total_memories == 2
    assert stats.active == 2
