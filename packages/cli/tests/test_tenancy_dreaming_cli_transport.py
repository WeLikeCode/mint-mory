"""RED tests for task 3 — CLI dreaming and summary commands on a multi-tenant DB.

They trace requirement 3.1 (``dream`` runs every tenant through ``run_dream``),
3.2 (the command still renders a ``DreamReport`` table, the per-tenant total),
3.3 (``DreamFailedError`` becomes ``error: <message>`` on stderr with exit 1)
and 4.1 (``summary-jobs`` / ``summary-put`` stay on the global tenant).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mintmory.cli.main import app
from mintmory.core.dreaming import DreamingEngine
from mintmory.core.ports import StorageBackend
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import ConceptLink, DreamReport, MemoryCategory, MemoryRecord
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db_path = tmp_path / "cli_tenancy.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    yield db_path


def _open(path: Path) -> StorageBackend:
    store = StorageAdapter(str(path))
    store.initialise()
    return store


def _add(
    store: StorageBackend,
    memory_id: str,
    content: str,
    tenant_id: str,
    **fields: Any,
) -> MemoryRecord:
    return store.add_memory(
        MemoryRecord(
            id=memory_id,
            content=content,
            category=MemoryCategory.FACT,
            tenant_id=tenant_id,
            **fields,
        )
    )


def _seed_two_tenants(path: Path) -> None:
    store = _open(path)
    try:
        store.create_tenant("t1")
        _add(store, "g1", "Alice works at Acme in Berlin", "global")
        _add(store, "g2", "Bob works at Acme in Berlin", "global")
        _add(store, "a1", "Alice works at Acme in Berlin", "t1")
        _add(store, "a2", "Carol works at Acme in Berlin", "t1")
        _add(store, "a3", "Dan works at Acme in Berlin", "t1")
    finally:
        store.close()


def _seed_summary_tenants(path: Path) -> None:
    store = _open(path)
    try:
        store.create_tenant("t1")
        for index in range(3):
            _add(
                store,
                f"g{index}",
                f"Global {index} fact",
                "global",
                entity_ids=["globalconcept"],
            )
            _add(
                store,
                f"a{index}",
                f"Tenant {index} fact",
                "t1",
                entity_ids=["tenantconcept"],
            )
    finally:
        store.close()


def _all_links(store: StorageBackend, memory_ids: list[str]) -> list[ConceptLink]:
    by_id: dict[str, ConceptLink] = {}
    for memory_id in memory_ids:
        for link in store.get_links(memory_id):
            by_id[link.id] = link
    return list(by_id.values())


@pytest.mark.l4("C-7881686c", "C-d9c39ea3")
def test_dream_runs_each_tenant_without_cross_tenant_links(cli_db: Path) -> None:
    _seed_two_tenants(cli_db)

    result = runner.invoke(app, ["dream"])

    assert result.exit_code == 0, result.output
    assert "Dream report" in result.output
    assert re.search(r"new_links[^\n]*\b4\b", result.output), result.output

    store = _open(cli_db)
    try:
        grouped: dict[str, set[frozenset[str]]] = defaultdict(set)
        for link in _all_links(store, ["g1", "g2", "a1", "a2", "a3"]):
            grouped[link.tenant_id].add(frozenset({link.source_memory_id, link.target_memory_id}))
    finally:
        store.close()

    assert grouped == {
        "global": {frozenset({"g1", "g2"})},
        "t1": {
            frozenset({"a1", "a2"}),
            frozenset({"a1", "a3"}),
            frozenset({"a2", "a3"}),
        },
    }


@pytest.mark.l4("C-63860dbc")
def test_dream_failure_reports_error_on_stderr(
    cli_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: DreamingEngine) -> DreamReport:
        raise RuntimeError("boom")

    monkeypatch.setattr(DreamingEngine, "run_light", boom)
    monkeypatch.setattr(DreamingEngine, "run_full", boom)

    result = runner.invoke(app, ["dream"])

    assert result.exit_code == 1
    assert "error: dreaming failed for tenant(s): global (RuntimeError: boom)" in result.stderr


@pytest.mark.l4("C-a0213e6c")
def test_summary_commands_stay_on_the_global_tenant(cli_db: Path) -> None:
    _seed_summary_tenants(cli_db)

    jobs_result = runner.invoke(app, ["summary-jobs", "--json"])
    assert jobs_result.exit_code == 0, jobs_result.output
    output = jobs_result.output
    start = output.find("[")
    end = output.rfind("]") + 1
    assert start != -1, output
    jobs = json.loads(output[start:end])
    assert [job["concept"] for job in jobs] == ["globalconcept"]

    put_result = runner.invoke(app, ["summary-put", "tenantconcept", "Global only."])
    assert put_result.exit_code == 0, put_result.output
    assert "0 memories" in put_result.output

    store = _open(cli_db)
    try:
        assert store.get_summary("tenantconcept", "global") is not None
        assert store.get_summary("tenantconcept", "t1") is None
    finally:
        store.close()
