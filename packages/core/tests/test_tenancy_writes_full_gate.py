"""Full-gate tests for task 5 — requirements 5.1 and 5.2.

R5.1: a database that has only the seeded ``global`` tenant keeps the existing
write/read contracts (default tenant, links, sessions, feedback, summaries and
the manifest) working unchanged.  R5.2: the configured lint, typecheck and test
gates exist and the lint/typecheck commands actually exit 0; pytest keeps the
80% coverage floor and the suite needs no external service.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import tomllib
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    MemoryCategory,
    MemoryRecord,
    MemorySummary,
    QueryResult,
    QuerySession,
    SearchRequest,
)

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


@pytest.mark.l4("C-59232fa4")
def test_global_only_database_keeps_existing_write_contracts(tmp_path: Path) -> None:
    store = SqliteBackend(tmp_path / "global-only.db")
    store.initialise()

    assert [tenant.id for tenant in store.list_tenants()] == ["global"]

    first = store.add_memory(MemoryRecord(content="the sky is blue", category=MemoryCategory.FACT))
    second = store.add_memory(MemoryRecord(content="the sea is deep", category=MemoryCategory.FACT))
    assert first.tenant_id == "global"
    assert second.tenant_id == "global"

    hits = store.search(SearchRequest(query="sky"))
    assert [memory.id for memory in hits.memories] == [first.id]

    store.add_link(
        ConceptLink(
            source_memory_id=first.id,
            target_memory_id=second.id,
            link_type=ConceptLinkType.RELATES_TO,
        )
    )
    links = store.get_links(first.id)
    assert [link.id for link in links]  # the default global link was stored
    assert links[0].tenant_id == "global"

    session = store.create_session(QuerySession(query_text="sky"))
    assert session.tenant_id == "global"
    store.record_query_results(
        [QueryResult(session_id=session.id, memory_id=first.id, relevance_score=1.0)]
    )
    assert store.get_session(session.id) is not None

    store.apply_feedback(first.id, useful=True, stale=False)
    updated = store.get_memory(first.id)
    assert updated is not None
    assert updated.usefulness_score > 0
    assert updated.tenant_id == "global"

    store.update_memory(first.id, content="the sky is clear")
    refreshed = store.get_memory(first.id)
    assert refreshed is not None
    assert refreshed.content == "the sky is clear"
    assert refreshed.tenant_id == "global"

    store.archive_memory(second.id)
    archived = store.get_memory(second.id)
    assert archived is not None
    assert archived.is_archived is True

    store.upsert_summary(
        MemorySummary(concept="sky", summary_text="the sky is clear", memory_count=1)
    )
    summary = store.get_summary("sky")
    assert summary is not None
    assert summary.summary_text == "the sky is clear"

    store.manifest_upsert(
        "/docs/weather.md",
        "docs",
        size=12,
        mtime=1.0,
        online_only=False,
        index_mode="metadata",
        memory_ids=[first.id],
    )
    entry = store.manifest_get("/docs/weather.md")
    assert entry is not None
    assert json.loads(entry["memory_ids"]) == [first.id]


@pytest.mark.l4("C-3e681376")
def test_tenancy_writes_gate_declares_required_commands_and_coverage_floor() -> None:
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


@pytest.mark.l4("C-3e681376")
def test_tenancy_writes_lint_and_typecheck_commands_pass() -> None:
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


@pytest.mark.l4("C-3e681376")
def test_tenancy_writes_suite_needs_no_external_service() -> None:
    gates = _gate_section()
    setup = _strings(gates.get("setup"), "gates.setup")
    assert setup == ["uv sync --frozen --extra cochange --extra otel --extra postgres"]

    postgres_tests = (ROOT / "packages" / "core" / "tests" / "test_pg_tenancy.py").read_text(
        encoding="utf-8"
    )
    assert 'PostgresBackend("postgresql://unused")' in postgres_tests
    assert "psycopg.connect" not in postgres_tests
