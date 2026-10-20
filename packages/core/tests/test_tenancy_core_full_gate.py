"""Full-gate tests for task 6 — requirement 7.1.

R7.1: a database that has only the seeded ``global`` tenant keeps the existing
core contracts (notes, document timeline and the default dreaming engine) and
every existing caller can keep omitting the tenant.  The gates declared in
``.l4/config.yaml`` exist, keep the 80% coverage floor, and the lint/typecheck
commands exit 0 without Postgres, Docker or a network service.
"""

from __future__ import annotations

import inspect
import json
import shlex
import sqlite3
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from mintmory.core import cochange, llm, notes, session, vision
from mintmory.core.dreaming import DreamingEngine
from mintmory.core.storage import SqliteBackend

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / ".l4" / "config.yaml"
PYPROJECT_PATH = ROOT / "pyproject.toml"
_SCHEMA = ROOT / "packages" / "core" / "src" / "mintmory" / "core" / "schema.sql"
_TS = "2026-01-01T00:00:00"

TENANT_DEFAULTS: tuple[tuple[Callable[..., object], object], ...] = (
    (notes.create_note, "global"),
    (notes.notes_list, None),
    (session.apply_feedback, None),
    (cochange.changed_with, None),
    (cochange.documents_timeline, None),
    (vision.image_jobs, "global"),
    (vision.image_caption_put, "global"),
    (vision.caption_pending_images, "global"),
    (llm.build_dreaming_engine, None),
    (DreamingEngine.__init__, None),
)


def _tenant_signature_problems() -> list[str]:
    """Existing callers that omit ``tenant_id`` must still pick today's scope."""
    problems: list[str] = []
    for func, expected_default in TENANT_DEFAULTS:
        name = f"{func.__module__}.{getattr(func, '__qualname__', func)}"
        parameters = inspect.signature(func).parameters
        if "tenant_id" not in parameters:
            problems.append(f"{name} has no keyword-only tenant_id")
            continue
        parameter = parameters["tenant_id"]
        if parameter.kind is not inspect.Parameter.KEYWORD_ONLY:
            problems.append(f"{name}.tenant_id is not keyword-only")
        if parameter.default != expected_default:
            problems.append(
                f"{name}.tenant_id defaults to {parameter.default!r}, expected {expected_default!r}"
            )
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


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def _write(path: Path, sql: str, params: tuple[Any, ...] = ()) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _seed_global_database(path: Path) -> None:
    _init_db(path)
    _write(
        path,
        "INSERT OR IGNORE INTO tenants (id, name, is_active, created_at, updated_at) "
        "VALUES (?, ?, 1, ?, ?)",
        ("global", "global", _TS, _TS),
    )
    _write(
        path,
        "INSERT INTO memories (id, content, category, source, entity_ids, tenant_id, "
        "metadata, is_note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "n1",
            "book hotel",
            "episodic",
            "user",
            json.dumps(["tokyo"]),
            "global",
            json.dumps({"anchor": "Tokyo trip"}),
            1,
            _TS,
            _TS,
        ),
    )
    _write(
        path,
        "INSERT INTO memories (id, content, category, source, entity_ids, tenant_id, "
        "metadata, is_note, valid_from, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "d1",
            "Tokyo trip plan",
            "fact",
            "document",
            json.dumps(["tokyo"]),
            "global",
            json.dumps({"path": "/docs/tokyo.md", "rel": "tokyo.md", "collection": "docs"}),
            0,
            "2026-01-02T00:00:00",
            _TS,
            _TS,
        ),
    )


@pytest.mark.l4("C-61a564ed")
def test_existing_callers_can_keep_omitting_the_tenant() -> None:
    problems = _tenant_signature_problems()
    assert problems == [], (
        f"an existing caller that omits tenant_id no longer resolves to today's scope: {problems}"
    )


@pytest.mark.l4("C-61a564ed")
def test_global_only_database_keeps_existing_default_core_reads(tmp_path: Path) -> None:
    database = tmp_path / "global-only.db"
    _seed_global_database(database)
    store = SqliteBackend(database)

    assert [tenant.id for tenant in store.list_tenants()] == ["global"]

    listed = notes.notes_list(store)
    assert [note.id for note in listed] == ["n1"]
    assert listed[0].tenant_id == "global"

    timeline = cochange.documents_timeline(store)
    assert [entry["path"] for entry in timeline] == ["/docs/tokyo.md"]
    assert timeline[0]["collection"] == "docs"


@pytest.mark.l4("C-61a564ed")
def test_tenancy_core_gate_declares_required_commands_and_coverage_floor() -> None:
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


@pytest.mark.l4("C-61a564ed")
def test_tenancy_core_gate_commands_pass_without_external_services() -> None:
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
