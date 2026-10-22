"""Integration gate for the CLI tenant selector (R6.13).

R6.3, R6.7, R6.8 and finally R6.4 run in that order against one real SQLite
file, after ``tenant create acme``. Deactivation is last because it makes the
tenant read-only for every later command.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from mintmory.cli.main import app
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import ConceptLink, ConceptLinkType
from typer.testing import CliRunner, Result

runner = CliRunner()

_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture
def tenancy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """One real SQLite file shared by every command of the sequence."""
    db_path = tmp_path / "tenancy_cli.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("MINTMORY_LINK_MIN_SHARED_ENTITIES", "1")
    monkeypatch.setenv("COLUMNS", "200")
    yield db_path


def _open(path: Path) -> SqliteBackend:
    store = SqliteBackend(str(path))
    store.initialise()
    return store


def _ok(*args: str) -> Result:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result


def _tenant_of(path: Path, memory_id: str) -> str:
    store = _open(path)
    try:
        record = store.get_memory(memory_id)
        assert record is not None
        return record.tenant_id
    finally:
        store.close()


def _created_id(output: str) -> str:
    match = _ID_RE.search(output)
    assert match is not None, output
    return match.group(0)


def _all_links(store: SqliteBackend, memory_ids: list[str]) -> list[ConceptLink]:
    by_id: dict[str, ConceptLink] = {}
    for memory_id in memory_ids:
        for link in store.get_links(memory_id):
            by_id[link.id] = link
    return list(by_id.values())


def _assert_no_cross_tenant_links(
    store: SqliteBackend, acme_ids: set[str], global_ids: set[str]
) -> list[ConceptLink]:
    records = {m.id: m for m in store.list_memories()}
    links = _all_links(store, list(records))
    for link in links:
        if link.source_memory_id in acme_ids:
            assert link.target_memory_id in acme_ids, link
            assert link.tenant_id == "acme", link
        else:
            assert link.source_memory_id in global_ids, link
            assert link.target_memory_id in global_ids, link
            assert link.tenant_id == "global", link
    return links


@pytest.mark.l4("C-74d42dd9", "C-769977e3")
def test_cli_tenancy_sequence_on_one_sqlite_file(tenancy_db: Path) -> None:
    created = _ok("tenant", "create", "acme")
    assert "created tenant 'acme'" in created.output

    # --- R6.3: add / search / stats ---------------------------------------
    acme_add = _ok("--tenant", "acme", "add", "Acme uses Postgres")
    global_add = _ok("add", "Global uses SQLite")
    acme_id = _created_id(acme_add.output)
    global_id = _created_id(global_add.output)
    assert _tenant_of(tenancy_db, acme_id) == "acme"
    assert _tenant_of(tenancy_db, global_id) == "global"

    scoped = _ok("--tenant", "acme", "search", "uses")
    assert "Acme uses Postgres" in scoped.output
    assert "Global uses SQLite" not in scoped.output
    assert "1 result(s)" in scoped.output

    unscoped = _ok("search", "uses")
    assert "Acme uses Postgres" in unscoped.output
    assert "Global uses SQLite" in unscoped.output
    assert "2 result(s)" in unscoped.output

    acme_stats = _ok("--tenant", "acme", "stats")
    assert re.search(r"total_memories[^\n]*\b1\b", acme_stats.output), acme_stats.output
    assert _ok("--tenant", "global", "stats").output == _ok("stats").output

    # --- R6.7: note / notes -----------------------------------------------
    global_anchor = _ok("add", "Initech HQ is in Austin")
    global_anchor_id = _created_id(global_anchor.output)
    carol = _ok("--tenant", "acme", "add", "Carol works at Initech")
    carol_id = _created_id(carol.output)

    note_result = _ok("--tenant", "acme", "note", "renew contract", "--about", "Initech")
    note_id = _created_id(note_result.output)
    assert carol_id in note_result.output

    store = _open(tenancy_db)
    try:
        note = store.get_memory(note_id)
        assert note is not None
        assert note.tenant_id == "acme"
        links = [
            link for link in store.get_links(note_id) if link.link_type == ConceptLinkType.ANNOTATES
        ]
        assert len(links) == 1
        assert links[0].target_memory_id == carol_id
        assert links[0].target_memory_id != global_anchor_id
    finally:
        store.close()

    scoped_notes = _ok("--tenant", "acme", "notes")
    assert "renew contract" in scoped_notes.output
    all_notes = _ok("notes")
    assert "renew contract" in all_notes.output

    # --- R6.8: dream ------------------------------------------------------
    dan = _ok("--tenant", "acme", "add", "Dan works at Initech")
    dan_id = _created_id(dan.output)
    alice = _ok("add", "Alice works at Acme")
    alice_id = _created_id(alice.output)
    bob = _ok("add", "Bob works at Acme")
    bob_id = _created_id(bob.output)

    missing_dream = runner.invoke(app, ["--tenant", "nope", "dream"])
    assert missing_dream.exit_code == 1, missing_dream.output
    assert "error: tenant 'nope' not found" in missing_dream.stderr

    _ok("--tenant", "acme", "dream")

    store = _open(tenancy_db)
    try:
        records = {m.id: m for m in store.list_memories()}
        acme_ids = {mid for mid, m in records.items() if m.tenant_id == "acme"}
        global_ids = {mid for mid, m in records.items() if m.tenant_id == "global"}
        assert {carol_id, dan_id} <= acme_ids
        assert {alice_id, bob_id} <= global_ids

        links = _assert_no_cross_tenant_links(store, acme_ids, global_ids)
        acme_pairs = {
            frozenset({link.source_memory_id, link.target_memory_id})
            for link in links
            if link.tenant_id == "acme"
        }
        assert frozenset({carol_id, dan_id}) in acme_pairs
    finally:
        store.close()

    _ok("dream")

    store = _open(tenancy_db)
    try:
        records = {m.id: m for m in store.list_memories()}
        acme_ids = {mid for mid, m in records.items() if m.tenant_id == "acme"}
        global_ids = {mid for mid, m in records.items() if m.tenant_id == "global"}
        links = _assert_no_cross_tenant_links(store, acme_ids, global_ids)
        global_pairs = {
            frozenset({link.source_memory_id, link.target_memory_id})
            for link in links
            if link.tenant_id == "global"
        }
        assert frozenset({alice_id, bob_id}) in global_pairs
    finally:
        store.close()

    # --- R6.4: missing and inactive tenants (deactivation last) ----------
    missing_add = runner.invoke(app, ["--tenant", "nope", "add", "x"])
    assert missing_add.exit_code == 1, missing_add.output
    assert "error: tenant 'nope' not found" in missing_add.stderr

    missing_search = _ok("--tenant", "nope", "search", "x")
    assert "0 result(s)" in missing_search.output

    store = _open(tenancy_db)
    try:
        assert all(m.content != "x" for m in store.list_memories())
        store.set_tenant_active("acme", False)
    finally:
        store.close()

    inactive_add = runner.invoke(app, ["--tenant", "acme", "add", "y"])
    assert inactive_add.exit_code == 1, inactive_add.output
    assert "is inactive" in inactive_add.stderr

    still_there = _ok("--tenant", "acme", "search", "uses")
    assert "Acme uses Postgres" in still_there.output

    store = _open(tenancy_db)
    try:
        assert all(m.content != "y" for m in store.list_memories())
    finally:
        store.close()
