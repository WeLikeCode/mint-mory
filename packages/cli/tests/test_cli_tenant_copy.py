"""RED tests for task 5 — the CLI ``tenant copy`` command (R8.2, R9.10 CLI part).

The command is global-scope only: a named root ``--tenant`` refuses it before
touching the store; ``--id`` is repeatable and combines with the category or
entity filter as a union; the report is printed as a ``metric``/``value`` table
in ``CopyReport`` field order (``id_map`` omitted) or as exactly
``CopyReport.model_dump_json()`` with ``--json``. Selection and tenant errors
become ``error: <message>`` on stderr with exit 1.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mintmory.cli.main import app
from mintmory.core.storage import SqliteBackend
from mintmory.core.transfer import CopyReport
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    LinkSource,
    MemoryCategory,
    MemoryFilter,
    MemoryRecord,
    MemorySource,
)
from typer.testing import CliRunner

runner = CliRunner()

_COUNTERS = [
    "memories_copied",
    "memories_skipped_duplicate",
    "memories_skipped_not_found",
    "notes_copied",
    "notes_skipped_duplicate",
    "links_copied",
]


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the CLI at an isolated DB file under tmp_path."""
    db_path = tmp_path / "cli_copy.db"
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
    tenant: str = "acme",
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
    tenant: str = "acme",
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


def _seed_copy_source(path: Path) -> None:
    """R9.1-style source: acme with m1/m2, note n1 and two links; empty beta."""
    store = _open(path)
    try:
        store.create_tenant("acme")
        store.create_tenant("beta")
        _add(
            store,
            "m1",
            "Alice works at Acme",
            source=MemorySource.USER,
            entity_ids=["Alice", "Acme"],
            verified=True,
            confidence=0.8,
        )
        _add(store, "m2", "Bob works at Acme", entity_ids=["Bob", "Acme"])
        _add(
            store,
            "n1",
            "Alice prefers mornings",
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
            entity="Acme",
            strength=0.7,
            source=LinkSource.USER,
            verified=True,
        )
        _link(
            store,
            "n1",
            "m1",
            ConceptLinkType.ANNOTATES,
            entity="Alice",
            source=LinkSource.USER,
            verified=True,
        )
    finally:
        store.close()


def _beta_contents(path: Path) -> list[str]:
    store = _open(path)
    try:
        return [record.content for record in store.list_memories(tenant_id="beta")]
    finally:
        store.close()


def _report_json(output: str) -> dict[str, Any]:
    data = json.loads(output)
    assert isinstance(data, dict)
    return data


# ---------------------------------------------------------------------------
# R8.2 — the table, the repeatable --id and the field order
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2f599c95")
def test_tenant_copy_prints_a_metric_table_in_report_field_order(cli_db: Path) -> None:
    _seed_copy_source(cli_db)

    result = runner.invoke(app, ["tenant", "copy", "acme", "beta", "--id", "m1", "--id", "m2"])

    assert result.exit_code == 0, result.output
    output = result.output
    assert "metric" in output, output
    assert "value" in output, output

    positions = [output.index(name) for name in _COUNTERS]
    assert positions == sorted(positions), output
    assert "id_map" not in output, output

    values = {
        "memories_copied": 2,
        "memories_skipped_duplicate": 0,
        "memories_skipped_not_found": 0,
        "notes_copied": 1,
        "notes_skipped_duplicate": 0,
        "links_copied": 2,
    }
    for name in _COUNTERS:
        assert re.search(rf"{name}\s+{values[name]}\b", output), output

    assert sorted(_beta_contents(cli_db)) == [
        "Alice prefers mornings",
        "Alice works at Acme",
        "Bob works at Acme",
    ]


# ---------------------------------------------------------------------------
# R8.2 — --json emits exactly the report's model JSON
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2f599c95", "C-654ba513")
def test_tenant_copy_json_prints_exactly_the_report_model_json(cli_db: Path) -> None:
    _seed_copy_source(cli_db)

    result = runner.invoke(app, ["tenant", "copy", "acme", "beta", "--all-active", "--json"])

    assert result.exit_code == 0, result.output
    raw = result.output.strip()
    data = _report_json(raw)
    report = CopyReport(**data)

    assert raw == report.model_dump_json()
    assert report.source_tenant == "acme"
    assert report.dest_tenant == "beta"
    assert report.memories_copied == 2
    assert report.memories_skipped_duplicate == 0
    assert report.memories_skipped_not_found == 0
    assert report.notes_copied == 1
    assert report.notes_skipped_duplicate == 0
    assert report.links_copied == 2
    assert set(report.id_map) == {"m1", "m2", "n1"}


# ---------------------------------------------------------------------------
# R8.2 — filters are built only from --category / --entity and union with ids
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2f599c95")
def test_category_and_entity_filters_union_with_explicit_ids(cli_db: Path) -> None:
    store = _open(cli_db)
    try:
        store.create_tenant("acme")
        store.create_tenant("beta")
        store.create_tenant("gamma")
        _add(store, "f1", "Fact one")
        _add(store, "f2", "Fact two")
        _add(store, "c1", "Context one", category=MemoryCategory.CONTEXT)
        _add(store, "w1", "Widget fact", entity_ids=["Widget"])
    finally:
        store.close()

    union = runner.invoke(
        app,
        [
            "tenant",
            "copy",
            "acme",
            "beta",
            "--id",
            "c1",
            "--category",
            "fact",
            "--json",
        ],
    )
    assert union.exit_code == 0, union.output
    union_report = _report_json(union.output)
    assert union_report["memories_copied"] == 4
    assert sorted(_beta_contents(cli_db)) == [
        "Context one",
        "Fact one",
        "Fact two",
        "Widget fact",
    ]

    by_entity = runner.invoke(
        app, ["tenant", "copy", "acme", "gamma", "--entity", "Widget", "--json"]
    )
    assert by_entity.exit_code == 0, by_entity.output
    entity_report = _report_json(by_entity.output)
    assert entity_report["memories_copied"] == 1
    assert entity_report["notes_copied"] == 0
    assert list(entity_report["id_map"]) == ["w1"]


# ---------------------------------------------------------------------------
# R8.2 — --force repopulates duplicates
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2f599c95")
def test_force_flag_recopies_duplicate_content(cli_db: Path) -> None:
    _seed_copy_source(cli_db)
    command = ["tenant", "copy", "acme", "beta", "--id", "m1", "--id", "m2", "--json"]

    first = runner.invoke(app, command)
    assert first.exit_code == 0, first.output

    again = runner.invoke(app, command)
    assert again.exit_code == 0, again.output
    again_report = _report_json(again.output)
    assert again_report["memories_copied"] == 0
    assert again_report["memories_skipped_duplicate"] == 2
    assert again_report["notes_skipped_duplicate"] == 0

    forced = runner.invoke(app, [*command[:-1], "--force", "--json"])
    assert forced.exit_code == 0, forced.output
    forced_report = _report_json(forced.output)
    assert forced_report["memories_copied"] == 2
    assert forced_report["notes_copied"] == 1
    assert forced_report["memories_skipped_duplicate"] == 0


# ---------------------------------------------------------------------------
# R8.2 / R9.10 — global scope only, and the error paths
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2f599c95", "C-654ba513")
def test_named_root_tenant_refuses_copy_with_global_scope_message(cli_db: Path) -> None:
    _seed_copy_source(cli_db)

    result = runner.invoke(
        app, ["--tenant", "acme", "tenant", "copy", "acme", "beta", "--all-active"]
    )

    assert result.exit_code == 1, result.output
    assert result.stderr.strip() == (
        "error: tenant copy requires the global scope; this process is scoped to tenant 'acme'"
    )
    assert _beta_contents(cli_db) == []


@pytest.mark.l4("C-2f599c95", "C-654ba513")
def test_empty_selection_prints_a_selection_error_and_exits_one(cli_db: Path) -> None:
    _seed_copy_source(cli_db)

    result = runner.invoke(app, ["tenant", "copy", "acme", "beta"])

    assert result.exit_code == 1, result.output
    assert result.stderr.strip() == (
        "error: empty selection: pass memory_ids, filter or all_active=True"
    )
    assert _beta_contents(cli_db) == []


@pytest.mark.l4("C-2f599c95")
def test_tenant_error_prints_error_and_exits_one(cli_db: Path) -> None:
    _seed_copy_source(cli_db)

    result = runner.invoke(app, ["tenant", "copy", "acme", "ghost", "--id", "m1"])

    assert result.exit_code == 1, result.output
    assert result.stderr.strip() == "error: tenant 'ghost' not found"


# ---------------------------------------------------------------------------
# R8.2 — a copy into the destination is visible through the read filter
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2f599c95")
def test_copied_rows_are_visible_in_the_destination_tenant(cli_db: Path) -> None:
    _seed_copy_source(cli_db)

    result = runner.invoke(app, ["tenant", "copy", "acme", "beta", "--id", "m1", "--id", "m2"])
    assert result.exit_code == 0, result.output

    store = _open(cli_db)
    try:
        rows = store.list_memories(
            MemoryFilter(active_only=False, exclude_stale=False), tenant_id="beta"
        )
    finally:
        store.close()

    assert sorted(record.content for record in rows) == [
        "Alice prefers mornings",
        "Alice works at Acme",
        "Bob works at Acme",
    ]
    assert all(record.tenant_id == "beta" for record in rows)
