"""Integration gate for cross-tenant copy (R9.1, R9.11, R10.1).

The acceptance fixture of R9.1 is copied through the real CLI into a second
tenant (R9.11); a tenant-scoped dream then runs inside the destination only and
must neither touch a source row nor create a link that joins the two tenants.
The final check pins the configured ``.l4/config.yaml`` gates (coverage floor,
lint/typecheck) and proves the copy flow needs no Postgres, Docker or network.
"""

from __future__ import annotations

import json
import shlex
import sqlite3
import subprocess
import tomllib
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from mintmory.cli.main import app
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    LinkSource,
    MemoryCategory,
    MemoryFilter,
    MemoryRecord,
    MemorySource,
    MemorySummary,
)
from typer.testing import CliRunner

runner = CliRunner()

ROOT = Path(__file__).resolve().parents[2]

_COUNTERS = (
    "memories_copied",
    "memories_skipped_duplicate",
    "memories_skipped_not_found",
    "notes_copied",
    "notes_skipped_duplicate",
    "links_copied",
)


@pytest.fixture
def copy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """One real SQLite file shared by the CLI commands of the sequence."""
    db_path = tmp_path / "tenancy_copy.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("COLUMNS", "200")
    yield db_path


def _open(path: Path) -> SqliteBackend:
    store = SqliteBackend(str(path))
    store.initialise()
    return store


def _add(
    store: SqliteBackend,
    memory_id: str,
    content: str,
    tenant: str,
    **fields: Any,
) -> MemoryRecord:
    if "category" not in fields:
        fields["category"] = MemoryCategory.FACT
    return store.add_memory(
        record=MemoryRecord(id=memory_id, content=content, tenant_id=tenant, **fields)
    )


def _link(
    store: SqliteBackend,
    source_id: str,
    target_id: str,
    link_type: ConceptLinkType,
    tenant: str,
    **fields: Any,
) -> ConceptLink:
    return store.add_link(
        ConceptLink(
            source_memory_id=source_id,
            target_memory_id=target_id,
            link_type=link_type,
            tenant_id=tenant,
            **fields,
        )
    )


def _seed_r9_1(path: Path) -> None:
    """Build the R9.1 acceptance fixture: acme, empty beta and global g1."""
    store = _open(path)
    try:
        store.create_tenant("acme")
        store.create_tenant("beta")
        _add(
            store,
            "m1",
            "Alice works at Acme",
            "acme",
            source=MemorySource.USER,
            entity_ids=["Alice", "Acme"],
            verified=True,
            confidence=0.8,
            valid_from=datetime(2026, 1, 1),
            valid_until=datetime(2027, 1, 1),
            usefulness_score=4.0,
            staleness_score=2.0,
            reinforcement_count=3,
            retrieval_count=5,
            contradicts_ids=["m2"],
            flagged_for_review=True,
            last_accessed_at=datetime(2026, 6, 1),
            metadata={"project": "x"},
        )
        _add(store, "m2", "Bob works at Acme", "acme", entity_ids=["Bob", "Acme"])
        _add(store, "m3", "Archived Acme fact", "acme", is_archived=True)
        _add(
            store,
            "n1",
            "Alice prefers mornings",
            "acme",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            is_note=True,
            metadata={"anchor_memory_id": "m1"},
        )
        _link(
            store,
            "m1",
            "m2",
            ConceptLinkType.RELATES_TO,
            "acme",
            entity="Acme",
            strength=0.7,
            source=LinkSource.USER,
        )
        _link(
            store,
            "n1",
            "m1",
            ConceptLinkType.ANNOTATES,
            "acme",
            entity="Alice",
            source=LinkSource.USER,
        )
        _add(store, "g1", "Global fact", "global")
        store.upsert_summary(
            MemorySummary(
                concept="acme",
                summary_text="Acme summary",
                memory_count=2,
                tenant_id="acme",
            )
        )
    finally:
        store.close()


def _rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _acme_snapshot(store: SqliteBackend) -> dict[str, list[dict[str, Any]]]:
    """Every acme memory, link and summary row, in a deterministic order."""
    conn = store.connect()
    return {
        table: _rows(
            conn,
            f"SELECT * FROM {table} WHERE tenant_id = ? ORDER BY id",
            ("acme",),
        )
        for table in ("memories", "concept_links", "memory_summaries")
    }


def _cross_tenant_links(store: SqliteBackend) -> list[tuple[str, str, str]]:
    """Links that join an acme record and a beta record, with their link id."""
    conn = store.connect()
    tenants = {
        row["id"]: row["tenant_id"] for row in conn.execute("SELECT id, tenant_id FROM memories")
    }
    crossings: list[tuple[str, str, str]] = []
    for row in conn.execute("SELECT id, source_memory_id, target_memory_id FROM concept_links"):
        source_tenant = tenants.get(row["source_memory_id"])
        target_tenant = tenants.get(row["target_memory_id"])
        if {source_tenant, target_tenant} == {"acme", "beta"}:
            crossings.append((row["id"], str(source_tenant), str(target_tenant)))
    return crossings


def _gate_section() -> dict[str, Any]:
    loaded = yaml.safe_load((ROOT / ".l4" / "config.yaml").read_text(encoding="utf-8"))
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


@pytest.mark.l4("C-fd8b39a5", "C-86c2ff91")
def test_r9_1_seed_is_copied_by_the_cli_then_beta_dream_stays_inside_beta(
    copy_db: Path,
) -> None:
    _seed_r9_1(copy_db)

    store = _open(copy_db)
    try:
        before = _acme_snapshot(store)

        m1 = store.get_memory("m1", tenant_id="acme")
        assert m1 is not None
        assert m1.content == "Alice works at Acme"
        assert m1.category is MemoryCategory.FACT
        assert m1.usefulness_score == pytest.approx(4.0)
        assert m1.staleness_score == pytest.approx(2.0)
        assert m1.reinforcement_count == 3
        assert m1.retrieval_count == 5
        assert m1.valid_from == datetime(2026, 1, 1)
        assert m1.valid_until == datetime(2027, 1, 1)
        assert m1.contradicts_ids == ["m2"]
        assert m1.flagged_for_review is True
        assert m1.last_accessed_at == datetime(2026, 6, 1)
        assert m1.verified is True
        assert m1.confidence == pytest.approx(0.8)
        assert m1.metadata == {"project": "x"}

        assert store.get_memory("m2", tenant_id="acme") is not None
        assert store.get_memory("m3", tenant_id="acme") is not None
        m3 = store.get_memory("m3", tenant_id="acme")
        assert m3 is not None and m3.is_archived is True

        n1 = store.get_memory("n1", tenant_id="acme")
        assert n1 is not None
        assert n1.content == "Alice prefers mornings"
        assert n1.is_note is True
        assert n1.metadata == {"anchor_memory_id": "m1"}

        links = store.get_links("m1", tenant_id="acme")
        by_type = {link.link_type: link for link in links}
        assert by_type[ConceptLinkType.RELATES_TO].target_memory_id == "m2"
        assert by_type[ConceptLinkType.RELATES_TO].strength == pytest.approx(0.7)
        assert by_type[ConceptLinkType.ANNOTATES].source_memory_id == "n1"

        assert store.get_summary("acme", tenant_id="acme") is not None
        assert store.list_memories(MemoryFilter(active_only=False), tenant_id="beta") == []
        assert store.get_memory("g1", tenant_id="global") is not None
    finally:
        store.close()

    copied = runner.invoke(
        app, ["tenant", "copy", "acme", "beta", "--id", "m1", "--id", "m2", "--json"]
    )
    assert copied.exit_code == 0, copied.output
    report = json.loads(copied.output)
    assert report["source_tenant"] == "acme"
    assert report["dest_tenant"] == "beta"
    assert report["memories_copied"] == 2
    assert report["notes_copied"] == 1
    assert report["links_copied"] == 2
    assert set(report["id_map"]) == {"m1", "m2", "n1"}

    dreamed = runner.invoke(app, ["--tenant", "beta", "dream"])
    assert dreamed.exit_code == 0, dreamed.output

    store = _open(copy_db)
    try:
        assert _acme_snapshot(store) == before
        assert _cross_tenant_links(store) == []
        beta_contents = sorted(
            record.content
            for record in store.list_memories(
                MemoryFilter(active_only=False, exclude_stale=False), tenant_id="beta"
            )
        )
        assert beta_contents == [
            "Alice prefers mornings",
            "Alice works at Acme",
            "Bob works at Acme",
        ]
    finally:
        store.close()


@pytest.mark.l4("C-00790979")
def test_configured_gates_pass_and_the_copy_flow_needs_no_external_service(
    copy_db: Path,
) -> None:
    gates = _gate_section()

    test_gate = gates.get("test")
    assert isinstance(test_gate, dict)
    test_command = test_gate.get("command")
    assert isinstance(test_command, str)
    assert ".venv/bin/pytest" in test_command
    assert "--junitxml=.l4-out/junit.xml" in test_command

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    ini_options = pyproject["tool"]["pytest"]["ini_options"]
    addopts = ini_options["addopts"]
    assert isinstance(addopts, str)
    assert "--cov-fail-under=80" in addopts.split()
    testpaths = ini_options["testpaths"]
    assert isinstance(testpaths, list)
    assert "tests/integration" in testpaths

    commands = _strings(gates.get("lint"), "gates.lint") + _strings(
        gates.get("typecheck"), "gates.typecheck"
    )
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

    store = _open(copy_db)
    try:
        store.create_tenant("acme")
        store.create_tenant("beta")
        _add(store, "s1", "Only source fact", "acme")
    finally:
        store.close()

    copied = runner.invoke(app, ["tenant", "copy", "acme", "beta", "--all-active", "--json"])
    assert copied.exit_code == 0, copied.output
    report = json.loads(copied.output)
    for counter in _COUNTERS:
        assert counter in report
    assert report["memories_copied"] == 1

    store = _open(copy_db)
    try:
        beta_contents = [record.content for record in store.list_memories(tenant_id="beta")]
    finally:
        store.close()
    assert beta_contents == ["Only source fact"]
