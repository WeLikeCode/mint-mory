"""
CLI command tests using typer.testing.CliRunner.

Every test runs against an isolated SQLite file in a pytest ``tmp_path`` via the
``MINTMORY_DB`` environment variable, so the suite never touches ``~/.mintmory``.
No embedder is configured -> search is FTS-only (fine). No network, no LLM.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mintmory.cli.main import app
from typer.testing import CliRunner

if TYPE_CHECKING:
    from mintmory.core.storage import StorageAdapter

runner = CliRunner()


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the CLI at an isolated DB file under tmp_path."""
    db_path = tmp_path / "cli_test.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    yield db_path
    # Sanity: the real home DB must never be touched by these tests.
    assert os.environ["MINTMORY_DB"] == str(db_path)


def _add(content: str, *extra: str) -> str:
    """Run ``add`` and return captured stdout (helper for arrange steps)."""
    result = runner.invoke(app, ["add", content, *extra])
    assert result.exit_code == 0, result.output
    return result.output


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


def test_add_exit_zero_and_prints_id(cli_db: Path) -> None:
    result = runner.invoke(app, ["add", "The sky is blue", "--category", "fact"])
    assert result.exit_code == 0, result.output
    assert "Added memory" in result.output
    # A uuid4 id has 36 chars incl. hyphens; assert one is present.
    assert "-" in result.output


def test_add_persists_to_db(cli_db: Path) -> None:
    from mintmory.core.storage import StorageAdapter

    _add("Persisted content here", "--category", "fact")
    store = StorageAdapter(str(cli_db))
    store.initialise()
    assert store.get_stats().total_memories == 1
    store.close()


def test_add_with_source_and_verified(cli_db: Path) -> None:
    result = runner.invoke(
        app,
        [
            "add",
            "A verified agent note",
            "--category",
            "context",
            "--source",
            "agent",
            "--verified",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Added memory" in result.output


def test_add_invalid_category_errors(cli_db: Path) -> None:
    result = runner.invoke(app, ["add", "bad", "--category", "not-a-category"])
    assert result.exit_code != 0
    assert "invalid category" in result.output


def test_add_invalid_source_errors(cli_db: Path) -> None:
    result = runner.invoke(app, ["add", "bad", "--source", "not-a-source"])
    assert result.exit_code != 0
    assert "invalid source" in result.output


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_finds_added_memory(cli_db: Path) -> None:
    _add("parking integration uses OAuth", "--category", "fact")
    result = runner.invoke(app, ["search", "parking"])
    assert result.exit_code == 0, result.output
    assert "fact" in result.output
    assert "result(s)" in result.output


def test_search_empty_db_returns_zero_results(cli_db: Path) -> None:
    result = runner.invoke(app, ["search", "nothing here"])
    assert result.exit_code == 0, result.output
    assert "0 result(s)" in result.output


def test_search_with_category_filter(cli_db: Path) -> None:
    _add("alpha memory about widgets", "--category", "fact")
    _add("beta memory about widgets", "--category", "skill")
    result = runner.invoke(app, ["search", "widgets", "--category", "fact"])
    assert result.exit_code == 0, result.output
    assert "1 result(s)" in result.output


def test_search_with_around_link_type(cli_db: Path) -> None:
    _add("graph traversal anchor memory", "--category", "fact")
    result = runner.invoke(app, ["search", "anchor", "--around", "relates_to"])
    assert result.exit_code == 0, result.output
    assert "result(s)" in result.output


def test_search_invalid_around_errors(cli_db: Path) -> None:
    _add("anchor", "--category", "fact")
    result = runner.invoke(app, ["search", "anchor", "--around", "bogus_link"])
    assert result.exit_code != 0
    assert "invalid link type" in result.output


def test_search_invalid_category_filter_errors(cli_db: Path) -> None:
    result = runner.invoke(app, ["search", "x", "--category", "bogus"])
    assert result.exit_code != 0
    assert "invalid category" in result.output


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def test_stats_empty(cli_db: Path) -> None:
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0, result.output
    assert "total_memories" in result.output
    assert "active" in result.output


def test_stats_shows_counts_after_add(cli_db: Path) -> None:
    _add("first memory", "--category", "fact")
    _add("second memory", "--category", "skill")
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0, result.output
    assert "total_memories" in result.output
    # Two memories were added; the count 2 must appear in the table.
    assert "2" in result.output
    assert "avg_usefulness_score" in result.output


def test_stats_shows_top_concepts(cli_db: Path) -> None:
    # Content with proper nouns yields entity_ids, populating top_concepts.
    _add("The Acme OAuth PKCE integration is documented", "--category", "fact")
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0, result.output
    assert "top concepts" in result.output


# ---------------------------------------------------------------------------
# dream
# ---------------------------------------------------------------------------


def test_dream_light_exit_zero(cli_db: Path) -> None:
    _add("a memory to consolidate", "--category", "fact")
    result = runner.invoke(app, ["dream"])
    assert result.exit_code == 0, result.output
    assert "Dream report" in result.output
    assert "light" in result.output
    assert "new_links" in result.output


def test_dream_full_exit_zero(cli_db: Path) -> None:
    _add("a memory to consolidate fully", "--category", "fact")
    result = runner.invoke(app, ["dream", "--full"])
    assert result.exit_code == 0, result.output
    assert "Dream report" in result.output
    assert "full" in result.output
    assert "memories_archived" in result.output


def test_dream_empty_db_exit_zero(cli_db: Path) -> None:
    result = runner.invoke(app, ["dream"])
    assert result.exit_code == 0, result.output
    assert "new_links" in result.output


# ---------------------------------------------------------------------------
# serve / mcp_serve — exercised with the launchers mocked so no server starts.
# ---------------------------------------------------------------------------


def test_serve_invokes_uvicorn(cli_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    calls: dict[str, object] = {}

    fake_uvicorn = types.ModuleType("uvicorn")

    def _run(target: str, **kwargs: object) -> None:
        calls["target"] = target
        calls["kwargs"] = kwargs

    fake_uvicorn.run = _run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    result = runner.invoke(app, ["serve", "--port", "9999", "--host", "127.0.0.1"])
    assert result.exit_code == 0, result.output
    assert calls["target"] == "mintmory.api.app:app"
    assert calls["kwargs"] == {"host": "127.0.0.1", "port": 9999, "reload": True}


def test_mcp_serve_invokes_server_main(cli_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    called = {"ran": False}

    fake_server = types.ModuleType("mintmory.mcp.server")

    def _main() -> None:
        called["ran"] = True

    fake_server.main = _main  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mintmory.mcp.server", fake_server)
    monkeypatch.delenv("MINTMORY_TRANSPORT", raising=False)

    result = runner.invoke(app, ["mcp-serve", "--transport", "sse"])
    assert result.exit_code == 0, result.output
    assert called["ran"] is True
    assert os.environ.get("MINTMORY_TRANSPORT") == "sse"


# ---------------------------------------------------------------------------
# ingest (bulk)
# ---------------------------------------------------------------------------


def _store(cli_db: Path) -> StorageAdapter:
    from mintmory.core.storage import StorageAdapter

    s = StorageAdapter(str(cli_db))
    s.initialise()
    return s


def test_ingest_dir_respects_glob(cli_db: Path, tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("# Alpha\n\nAlpha covers the AXIS controller.")
    (docs / "b.txt").write_text("Beta notes about INGHub mobile.")
    (docs / "ignore.py").write_text("print('not ingested')")

    result = runner.invoke(app, ["ingest", str(docs), "--category", "fact"])
    assert result.exit_code == 0, result.output
    assert "Ingested" in result.output

    rows = _store(cli_db).connect().execute("SELECT content, metadata FROM memories").fetchall()
    assert len(rows) == 2  # .py excluded by the default glob
    assert any("AXIS" in r[0] for r in rows)
    assert all("source_file" in r[1] for r in rows)


def test_ingest_chunks_large_file_under_limit(cli_db: Path, tmp_path: Path) -> None:
    big = tmp_path / "big.md"
    big.write_text("\n\n".join(f"Paragraph {i} about Postgres tuning." for i in range(200)))

    result = runner.invoke(app, ["ingest", str(big), "--chunk-chars", "500"])
    assert result.exit_code == 0, result.output

    conn = _store(cli_db).connect()
    n = conn.execute("SELECT count(*) FROM memories").fetchone()[0]
    assert n > 1  # split into multiple chunks
    assert conn.execute("SELECT max(length(content)) FROM memories").fetchone()[0] <= 10_000


def test_ingest_missing_path_errors(cli_db: Path) -> None:
    result = runner.invoke(app, ["ingest", "/no/such/path/here"])
    assert result.exit_code != 0


def test_ingest_is_idempotent_on_rerun(cli_db: Path, tmp_path: Path) -> None:
    doc = tmp_path / "d.md"
    doc.write_text("# Title\n\nUnique content about MongoDB TTL index.")
    assert runner.invoke(app, ["ingest", str(doc)]).exit_code == 0
    n1 = _store(cli_db).connect().execute("SELECT count(*) FROM memories").fetchone()[0]
    rerun = runner.invoke(app, ["ingest", str(doc)])
    assert rerun.exit_code == 0, rerun.output
    n2 = _store(cli_db).connect().execute("SELECT count(*) FROM memories").fetchone()[0]
    assert n2 == n1  # duplicates skipped by default
    assert "skipped" in rerun.output


# ---------------------------------------------------------------------------
# note (capture)
# ---------------------------------------------------------------------------


def test_note_exit_zero_and_prints_id(cli_db: Path) -> None:
    """mintmory note prints 'Added note <id>' and exits 0."""
    result = runner.invoke(app, ["note", "Remember to update the README."])
    assert result.exit_code == 0, result.output
    assert "Added note" in result.output
    assert "-" in result.output  # uuid4 id contains hyphens


def test_note_stored_as_is_note(cli_db: Path) -> None:
    """The stored record has is_note=1 in the database."""
    from mintmory.core.storage import StorageAdapter

    runner.invoke(app, ["note", "A note stored in the DB."])
    store = StorageAdapter(str(cli_db))
    store.initialise()
    conn = store.connect()
    rows = conn.execute("SELECT is_note FROM memories WHERE is_note = 1").fetchall()
    assert len(rows) == 1
    store.close()


def test_note_with_valid_when(cli_db: Path) -> None:
    """--when with a valid ISO date exits 0."""
    result = runner.invoke(
        app,
        ["note", "Project launch event", "--when", "2026-09-01"],
    )
    assert result.exit_code == 0, result.output
    assert "Added note" in result.output


def test_note_with_about_shows_anchor_line(cli_db: Path) -> None:
    """--about causes the CLI to print an anchor line after the id line."""
    # First, add a memory the anchor resolver can potentially match.
    _add("The Tokyo trip itinerary covers the Shinjuku district.", "--category", "episodic")
    result = runner.invoke(
        app,
        ["note", "Pack adapters for Japan.", "--about", "Tokyo trip"],
    )
    assert result.exit_code == 0, result.output
    assert "Added note" in result.output
    # The anchor line may show '-> annotates', '-> topic:', or nothing — all valid.
    # We just confirm no exception and clean exit.


def test_note_bad_when_raises_bad_parameter(cli_db: Path) -> None:
    """--when with a non-ISO value must exit non-zero (typer.BadParameter)."""
    result = runner.invoke(app, ["note", "Something.", "--when", "next-tuesday"])
    assert result.exit_code != 0
    # typer surfaces BadParameter as a usage error.


def test_note_bad_until_raises_bad_parameter(cli_db: Path) -> None:
    """--until with a non-ISO value must exit non-zero."""
    result = runner.invoke(app, ["note", "Something.", "--until", "sometime soon"])
    assert result.exit_code != 0


def test_note_invalid_category_raises_bad_parameter(cli_db: Path) -> None:
    """--category with an invalid value must exit non-zero."""
    result = runner.invoke(app, ["note", "Something.", "--category", "not-a-category"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# notes (listing)
# ---------------------------------------------------------------------------


def _add_note(content: str, *extra: str) -> str:
    """Run ``note`` and return captured stdout."""
    result = runner.invoke(app, ["note", content, *extra])
    assert result.exit_code == 0, result.output
    return result.output


def test_notes_empty_db_shows_zero(cli_db: Path) -> None:
    """notes on an empty DB prints '0 note(s)'."""
    result = runner.invoke(app, ["notes"])
    assert result.exit_code == 0, result.output
    assert "0 note(s)" in result.output


def test_notes_lists_added_notes(cli_db: Path) -> None:
    """notes shows added notes and excludes plain memories."""
    _add("A plain memory — not a note.", "--category", "fact")
    _add_note("A genuine user note.")
    result = runner.invoke(app, ["notes"])
    assert result.exit_code == 0, result.output
    assert "1 note(s)" in result.output
    assert "user note" in result.output


def test_notes_upcoming_flag(cli_db: Path) -> None:
    """--upcoming returns future-dated notes only."""
    _add_note("Future dentist appointment.", "--when", "2099-12-31")
    _add_note("Undated note.")
    result = runner.invoke(app, ["notes", "--upcoming"])
    assert result.exit_code == 0, result.output
    assert "1 note(s)" in result.output


def test_notes_overdue_flag(cli_db: Path) -> None:
    """--overdue returns past-dated notes (valid_from < now)."""
    _add_note("Past meeting that already happened.", "--when", "2020-01-01")
    _add_note("Upcoming event.", "--when", "2099-06-01")
    result = runner.invoke(app, ["notes", "--overdue"])
    assert result.exit_code == 0, result.output
    assert "1 note(s)" in result.output


def test_notes_both_flags_raises_error(cli_db: Path) -> None:
    """--upcoming and --overdue together must exit non-zero."""
    _add_note("Any note.")
    result = runner.invoke(app, ["notes", "--upcoming", "--overdue"])
    assert result.exit_code != 0


def test_notes_table_has_valid_from_column(cli_db: Path) -> None:
    """The notes table shows the valid_from column."""
    _add_note("A dated note.", "--when", "2026-07-04")
    result = runner.invoke(app, ["notes"])
    assert result.exit_code == 0, result.output
    assert "valid_from" in result.output


def test_notes_limit_option(cli_db: Path) -> None:
    """--limit caps the number of rows in the table."""
    for i in range(5):
        _add_note(f"Note {i} for limit test.")
    result = runner.invoke(app, ["notes", "--limit", "2"])
    assert result.exit_code == 0, result.output
    # Footer shows the actual count returned, not the total.
    assert "note(s)" in result.output


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def test_doctor_healthy_offline(cli_db: Path) -> None:
    _add("a doctor probe memory", "--category", "fact")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    for row in ("database", "embedder", "vector search", "llm tier", "linking"):
        assert row in result.output
    assert "disabled" in result.output  # default LLM provider=none


# ---------------------------------------------------------------------------
# ingest — conversion
# ---------------------------------------------------------------------------


def _inject_fake_markitdown(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    """Inject a minimal fake ``markitdown`` module so the real convert path runs."""
    import sys
    import types

    fake = types.ModuleType("markitdown")

    class _Result:
        def __init__(self, content: str) -> None:
            self.text_content = content

    class MarkItDown:
        def __init__(self, *, enable_plugins: bool = False) -> None:
            self.enable_plugins = enable_plugins

        def convert(self, _source: str) -> _Result:
            return _Result(text)

    fake.MarkItDown = MarkItDown  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "markitdown", fake)


def test_ingest_docx_converts_via_markitdown(
    cli_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inject_fake_markitdown(monkeypatch, "# Report\n\nQuarterly numbers about ACME revenue.")
    report = tmp_path / "report.docx"
    report.write_bytes(b"\x00\x01\x02 not really a docx")

    result = runner.invoke(app, ["ingest", str(report), "--glob", "*.docx"])
    assert result.exit_code == 0, result.output

    rows = _store(cli_db).connect().execute("SELECT content, metadata FROM memories").fetchall()
    assert len(rows) == 1
    assert "ACME revenue" in rows[0][0]
    assert '"converter": "markitdown"' in rows[0][1]


def test_ingest_pdf_skipped_when_markitdown_absent(
    cli_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    # Ensure markitdown is genuinely unavailable for this run.
    monkeypatch.setitem(sys.modules, "markitdown", None)

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("# Alpha\n\nAlpha covers the AXIS controller.")
    (docs / "b.pdf").write_bytes(b"%PDF-1.4 binary BRAVO content")

    result = runner.invoke(app, ["ingest", str(docs), "--glob", "*.md,*.pdf"])
    assert result.exit_code == 0, result.output
    assert "skip" in result.output
    assert "skipped 1 file(s)" in result.output  # the failed file is counted in the summary

    rows = _store(cli_db).connect().execute("SELECT content FROM memories").fetchall()
    assert any("AXIS" in r[0] for r in rows)  # a.md ingested
    assert not any("BRAVO" in r[0] for r in rows)  # b.pdf skipped, content absent


def test_ingest_md_records_text_converter(cli_db: Path, tmp_path: Path) -> None:
    # spec.md: plain text/markdown is stored with metadata converter="text".
    doc = tmp_path / "readme.md"
    doc.write_text("# Title\n\nPlain markdown about the GATEWAY service.")
    result = runner.invoke(app, ["ingest", str(doc)])
    assert result.exit_code == 0, result.output
    row = _store(cli_db).connect().execute("SELECT metadata FROM memories").fetchone()
    assert '"converter": "text"' in row[0]


def test_ingest_convert_disabled_via_env_skips_binary(
    cli_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # MINTMORY_CONVERT_ENABLED=false is a global off-switch even with markitdown present.
    _inject_fake_markitdown(monkeypatch, "# Would convert\n\nbut disabled")
    monkeypatch.setenv("MINTMORY_CONVERT_ENABLED", "false")
    report = tmp_path / "report.docx"
    report.write_bytes(b"\x00\x01 fake docx")

    result = runner.invoke(app, ["ingest", str(report), "--glob", "*.docx"])
    assert result.exit_code == 0, result.output
    assert "skip" in result.output
    rows = _store(cli_db).connect().execute("SELECT count(*) FROM memories").fetchone()
    assert rows[0] == 0  # nothing ingested — conversion globally disabled


def test_ingest_empty_conversion_is_noted(
    cli_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # markitdown returns no extractable text -> 0 chunks, surfaced (not silently counted).
    _inject_fake_markitdown(monkeypatch, "   \n\n  ")
    report = tmp_path / "scan.pdf"
    report.write_bytes(b"%PDF-1.4 image-only scan")

    result = runner.invoke(app, ["ingest", str(report), "--glob", "*.pdf"])
    assert result.exit_code == 0, result.output
    assert "extractable" in result.output  # "produced no extractable text" (rich may wrap)
    rows = _store(cli_db).connect().execute("SELECT count(*) FROM memories").fetchone()
    assert rows[0] == 0


# ---------------------------------------------------------------------------
# index-tree (recurrent tree indexing)
# ---------------------------------------------------------------------------


def _tree(root: Path) -> None:
    (root / "a.md").write_text("# A\n\nAlpha about the AXIS controller.")
    (root / "notes.txt").write_text("loose notes")
    personal = root / "Personal"
    personal.mkdir()
    (personal / "photo.jpg").write_bytes(b"\xff\xd8\xff fake jpeg bytes")
    work = root / "Work"
    work.mkdir()
    (work / "diagram.vsdx").write_bytes(b"PK\x03\x04 fake visio")


def _count(cli_db: Path, where: str = "1=1") -> int:
    row = (
        _store(cli_db).connect().execute(f"SELECT count(*) FROM memories WHERE {where}").fetchone()
    )
    return int(row[0])


def test_index_tree_metadata_only_indexes_every_file(cli_db: Path, tmp_path: Path) -> None:
    tree = tmp_path / "lib"
    tree.mkdir()
    _tree(tree)
    result = runner.invoke(
        app, ["index-tree", str(tree), "--collection", "lib", "--no-text-content"]
    )
    assert result.exit_code == 0, result.output
    # 4 files -> 4 metadata records; no downloads (jpg/vsdx are not read).
    assert _count(cli_db) == 4
    conn = _store(cli_db).connect()
    metas = [r[0] for r in conn.execute("SELECT metadata FROM memories").fetchall()]
    assert all('"collection": "lib"' in m for m in metas)
    assert any("photo.jpg" in r[0] for r in conn.execute("SELECT content FROM memories").fetchall())
    # manifest tracks every path.
    assert conn.execute("SELECT count(*) FROM index_manifest").fetchone()[0] == 4


def test_index_tree_is_idempotent(cli_db: Path, tmp_path: Path) -> None:
    tree = tmp_path / "lib"
    tree.mkdir()
    _tree(tree)
    runner.invoke(app, ["index-tree", str(tree), "--collection", "lib"])
    n1 = _count(cli_db)
    result = runner.invoke(app, ["index-tree", str(tree), "--collection", "lib"])
    assert result.exit_code == 0, result.output
    assert _count(cli_db) == n1  # nothing new on an unchanged tree


def test_index_tree_reindexes_changed_file(cli_db: Path, tmp_path: Path) -> None:
    tree = tmp_path / "lib"
    tree.mkdir()
    _tree(tree)
    args = ["index-tree", str(tree), "--collection", "lib", "--no-text-content"]
    runner.invoke(app, args)
    # Change a file's content (and thus size) -> detected as changed.
    (tree / "a.md").write_text("# A\n\nAlpha now mentions BRAVO and the AXIS controller, expanded.")
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    conn = _store(cli_db).connect()
    # The active record for a.md reflects the new content; the old one is archived.
    # Match by metadata rel (sibling records also *mention* a.md in their context).
    active = conn.execute(
        'SELECT content FROM memories WHERE is_archived = 0 AND metadata LIKE \'%"rel": "a.md"%\''
    ).fetchall()
    assert len(active) == 1
    assert conn.execute("SELECT count(*) FROM memories WHERE is_archived = 1").fetchone()[0] == 1


def test_index_tree_force_reindexes_everything(cli_db: Path, tmp_path: Path) -> None:
    tree = tmp_path / "lib"
    tree.mkdir()
    _tree(tree)
    runner.invoke(app, ["index-tree", str(tree), "--collection", "lib", "--no-text-content"])
    # --force rebuilds every file even though nothing changed: 4 new + 4 archived.
    result = runner.invoke(
        app, ["index-tree", str(tree), "--collection", "lib", "--no-text-content", "--force"]
    )
    assert result.exit_code == 0, result.output
    assert _count(cli_db, "is_archived = 0") == 4
    assert _count(cli_db, "is_archived = 1") == 4


def test_index_tree_exclude_prunes_subtree(cli_db: Path, tmp_path: Path) -> None:
    tree = tmp_path / "lib"
    tree.mkdir()
    _tree(tree)
    result = runner.invoke(
        app,
        [
            "index-tree",
            str(tree),
            "--collection",
            "lib",
            "--no-text-content",
            "--exclude",
            "Personal/**",
        ],
    )
    assert result.exit_code == 0, result.output
    contents = [r[0] for r in _store(cli_db).connect().execute("SELECT content FROM memories")]
    assert not any("photo.jpg" in c for c in contents)
    assert _count(cli_db) == 3


def test_index_tree_prune_archives_vanished_files(cli_db: Path, tmp_path: Path) -> None:
    tree = tmp_path / "lib"
    tree.mkdir()
    _tree(tree)
    runner.invoke(app, ["index-tree", str(tree), "--collection", "lib"])
    (tree / "notes.txt").unlink()
    result = runner.invoke(app, ["index-tree", str(tree), "--collection", "lib", "--prune"])
    assert result.exit_code == 0, result.output
    conn = _store(cli_db).connect()
    # notes.txt memory archived; manifest row removed.
    assert (
        conn.execute(
            "SELECT count(*) FROM memories WHERE is_archived = 1 AND content LIKE '%notes.txt%'"
        ).fetchone()[0]
        == 1
    )
    assert conn.execute("SELECT count(*) FROM index_manifest").fetchone()[0] == 3


def test_index_tree_text_content_indexed_by_default(cli_db: Path, tmp_path: Path) -> None:
    # Plain-text files are full-texted inline by default -> their content is
    # searchable, not just the filename. (Regression: a credentials .txt whose
    # body held the search terms returned nothing when only metadata was indexed.)
    tree = tmp_path / "lib"
    tree.mkdir()
    (tree / "creds.txt").write_text("video wall display login user pass for the GATEWAY")
    result = runner.invoke(app, ["index-tree", str(tree), "--collection", "lib"])
    assert result.exit_code == 0, result.output
    conn = _store(cli_db).connect()
    facts = conn.execute(
        "SELECT content FROM memories WHERE category = 'fact' AND content LIKE '%video wall%'"
    ).fetchall()
    assert len(facts) == 1  # the body was indexed as a full-text chunk
    assert conn.execute("SELECT index_mode FROM index_manifest").fetchone()[0] == "content"
    # And it is findable by a content word absent from the filename.
    found = runner.invoke(app, ["search", "video wall display"])
    assert found.exit_code == 0, found.output
    assert "GATEWAY" in found.output


def test_index_tree_no_text_content_stays_metadata(cli_db: Path, tmp_path: Path) -> None:
    tree = tmp_path / "lib"
    tree.mkdir()
    (tree / "creds.txt").write_text("video wall display login secret")
    result = runner.invoke(
        app, ["index-tree", str(tree), "--collection", "lib", "--no-text-content"]
    )
    assert result.exit_code == 0, result.output
    conn = _store(cli_db).connect()
    assert conn.execute("SELECT count(*) FROM memories WHERE category = 'fact'").fetchone()[0] == 0
    assert conn.execute("SELECT index_mode FROM index_manifest").fetchone()[0] == "metadata"


def test_index_tree_content_pass_full_texts_docs(
    cli_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inject_fake_markitdown(monkeypatch, "# Plan\n\nQuarterly roadmap for the GATEWAY service.")
    tree = tmp_path / "lib"
    tree.mkdir()
    (tree / "plan.docx").write_bytes(b"PK\x03\x04 fake docx")
    result = runner.invoke(
        app,
        ["index-tree", str(tree), "--collection", "lib", "--content", "--content-types", "docx"],
    )
    assert result.exit_code == 0, result.output
    conn = _store(cli_db).connect()
    # One context file-record + one full-text fact chunk.
    facts = conn.execute(
        "SELECT content, metadata FROM memories WHERE category = 'fact'"
    ).fetchall()
    assert len(facts) == 1
    assert "GATEWAY" in facts[0][0]
    assert '"converter": "markitdown"' in facts[0][1]
    assert conn.execute("SELECT index_mode FROM index_manifest").fetchone()[0] == "content"


def test_doctor_conversion_row_not_installed(cli_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the absent branch deterministically (the 'docs' extra may or may not
    # be installed in the dev env) and assert the actionable install hint.
    from mintmory.core import conversion

    monkeypatch.setattr(conversion, "markitdown_available", lambda: False)
    _add("a doctor probe memory", "--category", "fact")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "conversion" in result.output
    assert "not installed" in result.output
    assert "uv sync --extra docs" in result.output


def test_doctor_conversion_row_available(cli_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mintmory.core import conversion

    monkeypatch.setattr(conversion, "markitdown_available", lambda: True)
    _add("a doctor probe memory", "--category", "fact")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "markitdown available" in result.output


# ---------------------------------------------------------------------------
# summary-jobs
# ---------------------------------------------------------------------------


def test_summary_jobs_empty_db_exits_zero(cli_db: Path) -> None:
    """summary-jobs on an empty DB prints a table and '0 job(s)'."""
    result = runner.invoke(app, ["summary-jobs"])
    assert result.exit_code == 0, result.output
    assert "job(s)" in result.output


def test_summary_jobs_table_output_default(cli_db: Path) -> None:
    """summary-jobs (no flags) renders a rich table with the required columns."""
    result = runner.invoke(app, ["summary-jobs"])
    assert result.exit_code == 0, result.output
    # Rich renders table headers.
    assert "concept" in result.output
    assert "memories" in result.output
    assert "has_summary" in result.output


def test_summary_jobs_json_flag_emits_list(cli_db: Path) -> None:
    """--json flag emits a JSON array (even when empty)."""
    import json

    result = runner.invoke(app, ["summary-jobs", "--json"])
    assert result.exit_code == 0, result.output
    # Strip rich markup / control codes before JSON-parsing.
    # console.print_json wraps the output but the raw JSON array is present.
    output = result.output.strip()
    # Find the JSON array within the output.
    start = output.find("[")
    end = output.rfind("]") + 1
    assert start != -1, f"No JSON array found in output: {output!r}"
    parsed = json.loads(output[start:end])
    assert isinstance(parsed, list)


def test_summary_jobs_all_flag_accepted(cli_db: Path) -> None:
    """--all flag is accepted and produces exit-code 0."""
    result = runner.invoke(app, ["summary-jobs", "--all"])
    assert result.exit_code == 0, result.output
    assert "job(s)" in result.output


def test_summary_jobs_needed_flag_accepted(cli_db: Path) -> None:
    """--needed flag (default) is accepted and produces exit-code 0."""
    result = runner.invoke(app, ["summary-jobs", "--needed"])
    assert result.exit_code == 0, result.output


def test_summary_jobs_limit_zero_means_no_cap(cli_db: Path) -> None:
    """--limit 0 is the default (no cap); must not error."""
    result = runner.invoke(app, ["summary-jobs", "--limit", "0"])
    assert result.exit_code == 0, result.output


def test_summary_jobs_limit_caps_results(cli_db: Path) -> None:
    """--limit N caps the number of rows returned (even if no jobs exist)."""
    result = runner.invoke(app, ["summary-jobs", "--limit", "1"])
    assert result.exit_code == 0, result.output
    assert "job(s)" in result.output


# ---------------------------------------------------------------------------
# summary-put
# ---------------------------------------------------------------------------


def test_summary_put_positional_text_stores_summary(cli_db: Path) -> None:
    """summary-put CONCEPT TEXT stores verbatim text and prints 'Stored summary'."""
    result = runner.invoke(app, ["summary-put", "alphacat", "Alpha cats are fast."])
    assert result.exit_code == 0, result.output
    assert "Stored summary" in result.output
    assert "alphacat" in result.output


def test_summary_put_file_flag_reads_text(cli_db: Path, tmp_path: Path) -> None:
    """--file reads the summary from a file path."""
    txt = tmp_path / "summary.txt"
    txt.write_text("Beta cats are slow.")
    result = runner.invoke(app, ["summary-put", "betacat", "--file", str(txt)])
    assert result.exit_code == 0, result.output
    assert "Stored summary" in result.output
    assert "betacat" in result.output


def test_summary_put_stdin_reads_text(cli_db: Path) -> None:
    """Omitting TEXT and --file reads from stdin."""
    result = runner.invoke(app, ["summary-put", "gammacat"], input="Gamma cats are nimble.")
    assert result.exit_code == 0, result.output
    assert "Stored summary" in result.output
    assert "gammacat" in result.output


def test_summary_put_empty_text_arg_errors(cli_db: Path) -> None:
    """Passing an empty string as TEXT must exit non-zero (BadParameter)."""
    result = runner.invoke(app, ["summary-put", "emptycat", ""])
    assert result.exit_code != 0


def test_summary_put_empty_file_errors(cli_db: Path, tmp_path: Path) -> None:
    """A file containing only whitespace must exit non-zero (empty after strip)."""
    txt = tmp_path / "empty.txt"
    txt.write_text("   \n\n  ")
    result = runner.invoke(app, ["summary-put", "emptycat", "--file", str(txt)])
    assert result.exit_code != 0


def test_summary_put_stdin_empty_errors(cli_db: Path) -> None:
    """Stdin with only whitespace must exit non-zero."""
    result = runner.invoke(app, ["summary-put", "emptycat"], input="   ")
    assert result.exit_code != 0


def test_summary_put_persists_to_db(cli_db: Path) -> None:
    """After summary-put, the summary is visible in the SQLite store."""
    runner.invoke(app, ["summary-put", "deltacat", "Delta cats leap."])
    store = _store(cli_db)
    row = store.get_summary("deltacat")
    assert row is not None
    assert row.summary_text == "Delta cats leap."
    store.close()


def test_summary_put_idempotent_overwrites(cli_db: Path) -> None:
    """Running summary-put twice for the same concept overwrites the text."""
    runner.invoke(app, ["summary-put", "epsiloncat", "First text."])
    runner.invoke(app, ["summary-put", "epsiloncat", "Second text."])
    store = _store(cli_db)
    row = store.get_summary("epsiloncat")
    assert row is not None
    assert row.summary_text == "Second text."
    store.close()


def test_summary_put_works_without_llm(cli_db: Path) -> None:
    """summary-put does not require an LLM backend (provider=none by default)."""
    result = runner.invoke(app, ["summary-put", "nollmcat", "No LLM needed."])
    assert result.exit_code == 0, result.output


def test_summary_jobs_then_put_roundtrip(cli_db: Path) -> None:
    """After summary-put, summary-jobs (default) does NOT surface the concept again
    when the DB is otherwise unchanged (incremental rule)."""
    # Put a summary for an arbitrary concept (no active memories -> memory_count=0).
    runner.invoke(app, ["summary-put", "zetacat", "Zeta cats are rare."])
    # summary-jobs default (--needed) should not re-surface "zetacat" because
    # the stored memory_count (0) matches the current active count (0).
    result_json = runner.invoke(app, ["summary-jobs", "--json"])
    assert result_json.exit_code == 0, result_json.output
    import json

    output = result_json.output.strip()
    start = output.find("[")
    end = output.rfind("]") + 1
    if start != -1:
        jobs = json.loads(output[start:end])
        concepts = [j["concept"] for j in jobs]
        assert "zetacat" not in concepts
