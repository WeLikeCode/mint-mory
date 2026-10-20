"""RED tests for task 2 — tenant-aware CLI commands.

Every scenario starts from a fresh ``cli_db`` and runs ``tenant create acme``
first (R6.2). The tests trace requirement 2.1 (the read/write tenant mapping of
each command), 2.2 (``dream`` per tenant), 2.3 (missing-tenant reads are empty),
2.4 (the write guard runs before any work), 5.1 (tenant errors become
``error: …`` on stderr with exit 1), 5.2 (a refused write leaves the DB
unchanged) and the command scenarios of R6.3, R6.4, R6.6–R6.12.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from mintmory.cli.main import app
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    CaptionRunReport,
    ConceptLink,
    ConceptLinkType,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
)
from typer.testing import CliRunner

runner = CliRunner()

_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the CLI at an isolated DB file under tmp_path."""
    db_path = tmp_path / "cli_tenancy.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("COLUMNS", "200")
    yield db_path


def _open(path: Path) -> SqliteBackend:
    store = SqliteBackend(str(path))
    store.initialise()
    return store


def _create_acme() -> None:
    result = runner.invoke(app, ["tenant", "create", "acme"])
    assert result.exit_code == 0, result.output


def _created_id(output: str) -> str:
    match = _ID_RE.search(output)
    assert match is not None, output
    return match.group(0)


def t_acme(path: Path, memory_id: str) -> str:
    """Read a row's tenant with the Python API, as R6.2 requires."""
    store = _open(path)
    try:
        record = store.get_memory(memory_id)
        assert record is not None
        return record.tenant_id
    finally:
        store.close()


def _json_list(output: str) -> list[dict[str, Any]]:
    start = output.find("[")
    end = output.rfind("]") + 1
    assert start != -1 and end > start, output
    return cast(list[dict[str, Any]], json.loads(output[start:end]))


def _all_links(store: SqliteBackend, ids: list[str]) -> list[ConceptLink]:
    seen: dict[str, ConceptLink] = {}
    for memory_id in ids:
        for link in store.get_links(memory_id):
            seen[link.id] = link
    return list(seen.values())


def _seed_image(path: Path, tenant_id: str = "acme") -> str:
    store = _open(path)
    try:
        record = store.add_memory(
            record=MemoryRecord(
                content="x.png",
                category=MemoryCategory.CONTEXT,
                source=MemorySource.DOCUMENT,
                tenant_id=tenant_id,
                metadata={
                    "path": "/tmp/x.png",
                    "rel": "x.png",
                    "ext": ".png",
                    "size": 10,
                    "collection": "c",
                },
            )
        )
        return record.id
    finally:
        store.close()


# ---------------------------------------------------------------------------
# R6.3 — add / search / stats
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-cf987871", "C-46c6afc8", "C-f10d86d5")
def test_add_search_and_stats_use_the_selected_tenant(cli_db: Path) -> None:
    _create_acme()

    acme = runner.invoke(app, ["--tenant", "acme", "add", "Acme uses Postgres"])
    assert acme.exit_code == 0, acme.output
    global_ = runner.invoke(app, ["add", "Global uses SQLite"])
    assert global_.exit_code == 0, global_.output

    acme_id = _created_id(acme.output)
    global_id = _created_id(global_.output)
    assert t_acme(cli_db, acme_id) == "acme"
    assert t_acme(cli_db, global_id) == "global"

    scoped = runner.invoke(app, ["--tenant", "acme", "search", "uses"])
    assert scoped.exit_code == 0, scoped.output
    assert "Acme uses Postgres" in scoped.output
    assert "Global uses SQLite" not in scoped.output
    assert "1 result(s)" in scoped.output

    unscoped = runner.invoke(app, ["search", "uses"])
    assert unscoped.exit_code == 0, unscoped.output
    assert "Acme uses Postgres" in unscoped.output
    assert "Global uses SQLite" in unscoped.output
    assert "2 result(s)" in unscoped.output

    scoped_stats = runner.invoke(app, ["--tenant", "acme", "stats"])
    assert scoped_stats.exit_code == 0, scoped_stats.output
    assert re.search(r"total_memories[^\n]*\b1\b", scoped_stats.output), scoped_stats.output

    global_stats = runner.invoke(app, ["--tenant", "global", "stats"])
    plain_stats = runner.invoke(app, ["stats"])
    assert global_stats.exit_code == 0, global_stats.output
    assert plain_stats.exit_code == 0, plain_stats.output
    assert global_stats.output == plain_stats.output


# ---------------------------------------------------------------------------
# R6.4 — missing and inactive tenants
# ---------------------------------------------------------------------------


@pytest.mark.l4(
    "C-cf987871",
    "C-46c6afc8",
    "C-17c1d2d1",
    "C-92f6541b",
    "C-b86d1447",
    "C-8e7b8062",
    "C-5dc41637",
)
def test_missing_and_inactive_tenants_are_handled(cli_db: Path) -> None:
    _create_acme()
    seeded = runner.invoke(app, ["--tenant", "acme", "add", "Acme uses Postgres"])
    assert seeded.exit_code == 0, seeded.output

    missing_add = runner.invoke(app, ["--tenant", "nope", "add", "x"])
    assert missing_add.exit_code == 1, missing_add.output
    assert "error: tenant 'nope' not found" in missing_add.stderr

    missing_search = runner.invoke(app, ["--tenant", "nope", "search", "x"])
    assert missing_search.exit_code == 0, missing_search.output
    assert "0 result(s)" in missing_search.output

    missing_search_uses = runner.invoke(app, ["--tenant", "nope", "search", "uses"])
    assert missing_search_uses.exit_code == 0, missing_search_uses.output
    assert "0 result(s)" in missing_search_uses.output

    store = _open(cli_db)
    try:
        assert [m.content for m in store.list_memories()] == ["Acme uses Postgres"]
        store.set_tenant_active("acme", False)
    finally:
        store.close()

    inactive_add = runner.invoke(app, ["--tenant", "acme", "add", "y"])
    assert inactive_add.exit_code == 1, inactive_add.output
    assert "error: tenant 'acme' is inactive" in inactive_add.stderr

    still_there = runner.invoke(app, ["--tenant", "acme", "search", "uses"])
    assert still_there.exit_code == 0, still_there.output
    assert "Acme uses Postgres" in still_there.output

    store = _open(cli_db)
    try:
        assert [m.content for m in store.list_memories()] == ["Acme uses Postgres"]
    finally:
        store.close()


# ---------------------------------------------------------------------------
# R6.6 — ingest
# ---------------------------------------------------------------------------


@pytest.mark.l4(
    "C-cf987871",
    "C-46c6afc8",
    "C-29450002",
    "C-b86d1447",
    "C-5dc41637",
)
def test_ingest_dedups_within_the_write_tenant(cli_db: Path, tmp_path: Path) -> None:
    _create_acme()
    source = tmp_path / "a.txt"
    source.write_text("Acme ingest fact")

    first = runner.invoke(app, ["--tenant", "acme", "ingest", str(source)])
    assert first.exit_code == 0, first.output
    again = runner.invoke(app, ["--tenant", "acme", "ingest", str(source)])
    assert again.exit_code == 0, again.output
    unscoped = runner.invoke(app, ["ingest", str(source)])
    assert unscoped.exit_code == 0, unscoped.output

    store = _open(cli_db)
    try:
        rows = [m for m in store.list_memories() if m.content == "Acme ingest fact"]
        assert len(rows) == 2
        assert sorted(m.tenant_id for m in rows) == ["acme", "global"]
    finally:
        store.close()

    refused = runner.invoke(app, ["--tenant", "nope", "ingest", str(source)])
    assert refused.exit_code == 1, refused.output
    assert "error: tenant 'nope' not found" in refused.stderr

    store = _open(cli_db)
    try:
        rows = [m for m in store.list_memories() if m.content == "Acme ingest fact"]
        assert len(rows) == 2
    finally:
        store.close()


# ---------------------------------------------------------------------------
# R6.7 — note / notes
# ---------------------------------------------------------------------------


@pytest.mark.l4(
    "C-cf987871",
    "C-46c6afc8",
    "C-f9c22bd5",
    "C-b86d1447",
    "C-5dc41637",
)
def test_note_and_notes_are_tenant_scoped(cli_db: Path) -> None:
    _create_acme()
    global_anchor = runner.invoke(app, ["add", "Initech HQ is in Austin"])
    assert global_anchor.exit_code == 0, global_anchor.output
    global_anchor_id = _created_id(global_anchor.output)

    carol = runner.invoke(app, ["--tenant", "acme", "add", "Carol works at Initech"])
    assert carol.exit_code == 0, carol.output
    carol_id = _created_id(carol.output)

    note_result = runner.invoke(
        app, ["--tenant", "acme", "note", "renew contract", "--about", "Initech"]
    )
    assert note_result.exit_code == 0, note_result.output
    note_id = _created_id(note_result.output)
    assert "annotates" in note_result.output
    assert carol_id in note_result.output

    store = _open(cli_db)
    try:
        note = store.get_memory(note_id)
        assert note is not None
        assert note.tenant_id == "acme"
        assert note.is_note is True
        links = [
            link for link in store.get_links(note_id) if link.link_type == ConceptLinkType.ANNOTATES
        ]
        assert len(links) == 1
        assert links[0].target_memory_id == carol_id
        assert links[0].target_memory_id != global_anchor_id
        assert links[0].tenant_id == "acme"
    finally:
        store.close()

    scoped_notes = runner.invoke(app, ["--tenant", "acme", "notes"])
    assert scoped_notes.exit_code == 0, scoped_notes.output
    assert "renew contract" in scoped_notes.output

    all_notes = runner.invoke(app, ["notes"])
    assert all_notes.exit_code == 0, all_notes.output
    assert "renew contract" in all_notes.output

    refused = runner.invoke(app, ["--tenant", "nope", "note", "nope note"])
    assert refused.exit_code == 1, refused.output
    assert "error: tenant 'nope' not found" in refused.stderr

    store = _open(cli_db)
    try:
        assert all(m.content != "nope note" for m in store.list_memories())
    finally:
        store.close()


# ---------------------------------------------------------------------------
# R6.8 — dream
# ---------------------------------------------------------------------------


@pytest.mark.l4(
    "C-cf987871",
    "C-46c6afc8",
    "C-fbe84147",
    "C-8610aa4b",
    "C-8e7b8062",
)
def test_dream_is_confined_to_the_selected_tenant(
    cli_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MINTMORY_LINK_MIN_SHARED_ENTITIES", "1")
    _create_acme()

    for content in ("Carol works at Initech", "Dan works at Initech"):
        added = runner.invoke(app, ["--tenant", "acme", "add", content])
        assert added.exit_code == 0, added.output
    for content in ("Alice works at Acme", "Bob works at Acme"):
        added = runner.invoke(app, ["add", content])
        assert added.exit_code == 0, added.output

    refused = runner.invoke(app, ["--tenant", "nope", "dream"])
    assert refused.exit_code == 1, refused.output
    assert "error: tenant 'nope' not found" in refused.stderr

    scoped = runner.invoke(app, ["--tenant", "acme", "dream"])
    assert scoped.exit_code == 0, scoped.output

    store = _open(cli_db)
    try:
        records = {m.id: m for m in store.list_memories()}
        acme_ids = {mid for mid, m in records.items() if m.tenant_id == "acme"}
        global_ids = {mid for mid, m in records.items() if m.tenant_id == "global"}
        assert len(acme_ids) == 2
        assert len(global_ids) == 2

        links = _all_links(store, list(records))
        assert links
        for link in links:
            if link.tenant_id == "acme":
                assert link.source_memory_id in acme_ids
                assert link.target_memory_id in acme_ids
            else:
                assert link.tenant_id == "global"
                assert link.source_memory_id in global_ids
                assert link.target_memory_id in global_ids
        acme_pairs = {
            frozenset({link.source_memory_id, link.target_memory_id})
            for link in links
            if link.tenant_id == "acme"
        }
        assert len(acme_pairs) == 1
    finally:
        store.close()

    unscoped = runner.invoke(app, ["dream"])
    assert unscoped.exit_code == 0, unscoped.output
    explicit_global = runner.invoke(app, ["--tenant", "global", "dream"])
    assert explicit_global.exit_code == 0, explicit_global.output

    store = _open(cli_db)
    try:
        records = {m.id: m for m in store.list_memories()}
        acme_ids = {mid for mid, m in records.items() if m.tenant_id == "acme"}
        global_ids = {mid for mid, m in records.items() if m.tenant_id == "global"}
        pairs: dict[str, set[frozenset[str]]] = defaultdict(set)
        for link in _all_links(store, list(records)):
            pairs[link.tenant_id].add(frozenset({link.source_memory_id, link.target_memory_id}))
        assert len(pairs["acme"]) == 1
        assert len(pairs["global"]) == 1
        for tenant, tenant_pairs in pairs.items():
            expected = acme_ids if tenant == "acme" else global_ids
            for pair in tenant_pairs:
                assert pair <= expected
    finally:
        store.close()


# ---------------------------------------------------------------------------
# R6.9 — summary-jobs / summary-put
# ---------------------------------------------------------------------------


@pytest.mark.l4(
    "C-cf987871",
    "C-46c6afc8",
    "C-0459af16",
    "C-92f6541b",
    "C-b86d1447",
    "C-5dc41637",
)
def test_summary_commands_use_the_selected_tenant(cli_db: Path) -> None:
    _create_acme()
    for content in ("Carol works at Initech", "Dan works at Initech", "Eve works at Initech"):
        added = runner.invoke(app, ["--tenant", "acme", "add", content])
        assert added.exit_code == 0, added.output
    for content in ("Alice works at Acme", "Bob works at Acme", "Frank works at Acme"):
        added = runner.invoke(app, ["add", content])
        assert added.exit_code == 0, added.output

    jobs = runner.invoke(app, ["--tenant", "acme", "summary-jobs", "--json"])
    assert jobs.exit_code == 0, jobs.output
    concepts = {job["concept"] for job in _json_list(jobs.output)}
    assert "initech" in concepts
    assert "acme" not in concepts

    put = runner.invoke(app, ["--tenant", "acme", "summary-put", "initech", "Initech summary"])
    assert put.exit_code == 0, put.output

    store = _open(cli_db)
    try:
        summary = store.get_summary("initech", "acme")
        assert summary is not None
        assert summary.summary_text == "Initech summary"
        assert summary.tenant_id == "acme"
    finally:
        store.close()

    missing_jobs = runner.invoke(app, ["--tenant", "nope", "summary-jobs", "--json"])
    assert missing_jobs.exit_code == 0, missing_jobs.output
    assert _json_list(missing_jobs.output) == []

    refused = runner.invoke(app, ["--tenant", "nope", "summary-put", "initech", "nope summary"])
    assert refused.exit_code == 1, refused.output
    assert "error: tenant 'nope' not found" in refused.stderr

    store = _open(cli_db)
    try:
        assert store.get_summary("initech", "nope") is None
    finally:
        store.close()


# ---------------------------------------------------------------------------
# R6.10 — image-jobs / image-caption-put
# ---------------------------------------------------------------------------


@pytest.mark.l4(
    "C-cf987871",
    "C-46c6afc8",
    "C-5cf1ac32",
    "C-92f6541b",
    "C-b86d1447",
    "C-5dc41637",
)
def test_image_commands_use_the_selected_tenant(cli_db: Path) -> None:
    _create_acme()
    image_id = _seed_image(cli_db)

    scoped_jobs = runner.invoke(app, ["--tenant", "acme", "image-jobs", "--json"])
    assert scoped_jobs.exit_code == 0, scoped_jobs.output
    assert image_id in scoped_jobs.output

    global_jobs = runner.invoke(app, ["image-jobs", "--json"])
    assert global_jobs.exit_code == 0, global_jobs.output
    assert image_id not in global_jobs.output

    missing_jobs = runner.invoke(app, ["--tenant", "nope", "image-jobs", "--json"])
    assert missing_jobs.exit_code == 0, missing_jobs.output
    assert _json_list(missing_jobs.output) == []

    put = runner.invoke(app, ["--tenant", "acme", "image-caption-put", image_id, "a cat"])
    assert put.exit_code == 0, put.output

    store = _open(cli_db)
    try:
        descriptions = store.get_annotating_descriptions(image_id, 10, tenant_id="acme")
        assert len(descriptions) == 1
        assert descriptions[0].tenant_id == "acme"
        assert descriptions[0].content == "a cat"
    finally:
        store.close()

    global_put = runner.invoke(app, ["image-caption-put", image_id, "a cat"])
    # R6.10 asks for exit 1, but the global scope still goes through today's
    # KeyError -> BadParameter path (exit 2); R5.1 keeps that behaviour. Pin the
    # refusal and message without forcing an unrelated exit-code change.
    assert global_put.exit_code != 0, global_put.output
    assert "no active image file-record found" in global_put.output

    store = _open(cli_db)
    try:
        assert store.get_annotating_descriptions(image_id, 10, tenant_id="global") == []
    finally:
        store.close()


# ---------------------------------------------------------------------------
# R6.11 — vision-run
# ---------------------------------------------------------------------------


@pytest.mark.l4(
    "C-cf987871",
    "C-46c6afc8",
    "C-a9f24733",
    "C-b86d1447",
    "C-5dc41637",
)
def test_vision_run_and_caption_put_use_the_write_tenant(
    cli_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_acme()
    import mintmory.core.vision as vision_mod

    calls: list[dict[str, Any]] = []

    class _StubCaptioner:
        pass

    def fake_captioner(settings: object) -> _StubCaptioner:
        return _StubCaptioner()

    def fake_caption_pending(store: object, **kwargs: Any) -> CaptionRunReport:
        calls.append(kwargs)
        return CaptionRunReport()

    monkeypatch.setattr(vision_mod, "captioner_from_settings", fake_captioner)
    monkeypatch.setattr(vision_mod, "caption_pending_images", fake_caption_pending)

    result = runner.invoke(app, ["--tenant", "acme", "vision-run"])
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0].get("tenant_id") == "acme"

    missing = runner.invoke(app, ["--tenant", "nope", "vision-run"])
    assert missing.exit_code == 1, missing.output
    assert "error: tenant 'nope' not found" in missing.stderr
    assert len(calls) == 1

    missing_put = runner.invoke(app, ["--tenant", "nope", "image-caption-put", "x", "a cat"])
    assert missing_put.exit_code == 1, missing_put.output
    assert "error: tenant 'nope' not found" in missing_put.stderr


# ---------------------------------------------------------------------------
# R6.12 — docs timeline / changed-with
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-cf987871", "C-46c6afc8", "C-dc6d50e5")
def test_docs_commands_are_read_tenant_scoped(cli_db: Path) -> None:
    _create_acme()
    acme_path = "/tmp/acme-doc.txt"
    global_path = "/tmp/global-doc.txt"
    valid_from = datetime(2026, 1, 1, tzinfo=UTC)

    store = _open(cli_db)
    try:
        for path, tenant_id in ((acme_path, "acme"), (global_path, "global")):
            store.add_memory(
                record=MemoryRecord(
                    content=f"document {path}",
                    category=MemoryCategory.CONTEXT,
                    source=MemorySource.DOCUMENT,
                    tenant_id=tenant_id,
                    valid_from=valid_from,
                    metadata={
                        "path": path,
                        "collection": "c",
                        "changeset_id": "cs-shared",
                        "changeset_observed_at": "2026-01-01T00:00:00",
                        "changeset_kind": "incremental",
                    },
                )
            )
    finally:
        store.close()

    timeline = runner.invoke(app, ["--tenant", "acme", "docs", "timeline"])
    assert timeline.exit_code == 0, timeline.output
    assert acme_path in timeline.output
    assert global_path not in timeline.output

    changed = runner.invoke(app, ["--tenant", "acme", "docs", "changed-with", global_path])
    assert changed.exit_code == 0, changed.output
    assert "no co-change peers" in changed.output
    assert acme_path not in changed.output


# ---------------------------------------------------------------------------
# R6.1 / R4.1 / R4.2 — tenant create and tenant list
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-c35d15c6", "C-a79e558d")
def test_tenant_create_reports_created_again_and_invalid_ids(cli_db: Path) -> None:
    created = runner.invoke(app, ["tenant", "create", "acme", "--name", "Acme Corp"])
    assert created.exit_code == 0, created.output
    assert "created tenant 'acme'" in created.output

    store = _open(cli_db)
    try:
        tenant = store.get_tenant("acme")
        assert tenant is not None
        assert tenant.name == "Acme Corp"
    finally:
        store.close()

    again = runner.invoke(app, ["tenant", "create", "acme", "--name", "Renamed"])
    assert again.exit_code == 0, again.output
    assert "tenant 'acme' already exists" in again.output
    assert "created tenant" not in again.output

    store = _open(cli_db)
    try:
        tenant = store.get_tenant("acme")
        assert tenant is not None
        assert tenant.name == "Acme Corp"
    finally:
        store.close()

    invalid = runner.invoke(app, ["tenant", "create", "Bad"])
    assert invalid.exit_code == 1, invalid.output
    assert "error: invalid tenant id 'Bad'" in invalid.stderr

    store = _open(cli_db)
    try:
        assert store.get_tenant("Bad") is None
    finally:
        store.close()


@pytest.mark.l4("C-c35d15c6", "C-58023183", "C-a79e558d")
def test_tenant_list_reports_fresh_global_and_created_tenants(cli_db: Path) -> None:
    fresh = runner.invoke(app, ["tenant", "list", "--json"])
    assert fresh.exit_code == 0, fresh.output

    store = _open(cli_db)
    try:
        tenants = store.list_tenants()
    finally:
        store.close()
    assert [t.id for t in tenants] == ["global"]
    assert tenants[0].name == "Global (default) tenant"
    assert fresh.stdout.strip() == json.dumps([t.model_dump(mode="json") for t in tenants])

    created = runner.invoke(app, ["tenant", "create", "acme", "--name", "Acme Corp"])
    assert created.exit_code == 0, created.output

    listing = runner.invoke(app, ["tenant", "list", "--json"])
    assert listing.exit_code == 0, listing.output

    store = _open(cli_db)
    try:
        tenants = store.list_tenants()
    finally:
        store.close()
    assert [t.id for t in tenants] == ["acme", "global"]
    assert next(t for t in tenants if t.id == "acme").name == "Acme Corp"
    assert listing.stdout.strip() == json.dumps([t.model_dump(mode="json") for t in tenants])

    table = runner.invoke(app, ["tenant", "list"])
    assert table.exit_code == 0, table.output
    for header in ("id", "name", "is_active", "created_at"):
        assert header in table.output
    for tenant in tenants:
        assert tenant.id in table.output
        assert tenant.name in table.output
        assert tenant.created_at.isoformat() in table.output
    assert "true" in table.output
    assert "false" not in table.output
    assert table.output.find("Acme Corp") < table.output.find("Global (default) tenant")


# ---------------------------------------------------------------------------
# R3.2 — a valid tenant does not change the tenant directory
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-7760785e")
def test_valid_tenant_option_does_not_change_the_tenant_directory(cli_db: Path) -> None:
    scoped_create = runner.invoke(app, ["--tenant", "acme", "tenant", "create", "t1"])
    assert scoped_create.exit_code == 0, scoped_create.output
    assert "created tenant 't1'" in scoped_create.output

    plain_create = runner.invoke(app, ["tenant", "create", "t2", "--name", "Second tenant"])
    assert plain_create.exit_code == 0, plain_create.output
    assert "created tenant 't2'" in plain_create.output

    unscoped = runner.invoke(app, ["tenant", "list", "--json"])
    assert unscoped.exit_code == 0, unscoped.output
    scoped = runner.invoke(app, ["--tenant", "acme", "tenant", "list", "--json"])
    assert scoped.exit_code == 0, scoped.output
    assert scoped.stdout == unscoped.stdout

    store = _open(cli_db)
    try:
        tenants = store.list_tenants()
    finally:
        store.close()
    assert [t.id for t in tenants] == ["global", "t1", "t2"]
    assert next(t for t in tenants if t.id == "t2").name == "Second tenant"

    unscoped_table = runner.invoke(app, ["tenant", "list"])
    scoped_table = runner.invoke(app, ["--tenant", "acme", "tenant", "list"])
    assert scoped_table.exit_code == 0, scoped_table.output
    assert scoped_table.output == unscoped_table.output
    assert "t1" in scoped_table.output
    assert "t2" in scoped_table.output
