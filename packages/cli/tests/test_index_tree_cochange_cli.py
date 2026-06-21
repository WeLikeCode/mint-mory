"""
End-to-end CLI tests for MM-33: `index-tree` recency + co-change and the `docs`
sub-app. These drive the real Typer commands via CliRunner against an isolated
SQLite DB, then assert on persisted state (parsing rich tables is fragile).

Covers spec scenarios not reached by the direct-call integration tests:
recency stamped through the real walk, two distinct edit bursts via
`index-tree --cochange`, CLI-level idempotency, the honesty label of
`docs changed-with`, and graceful degradation when scikit-learn is absent.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mintmory.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

# Two bursts: folder_a edited around T0, folder_b edited ~50000s later.
_T0 = 1_700_000_000.0
_BURST = {
    "folder_a/f1.txt": _T0,
    "folder_a/f2.txt": _T0 + 60.0,
    "folder_b/f3.txt": _T0 + 50_000.0,
    "folder_b/f4.txt": _T0 + 50_060.0,
}


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Isolate the CLI on a tmp DB + a wide console so output isn't truncated."""
    db_path = tmp_path / "docs_test.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("COLUMNS", "200")
    yield db_path


def _make_tree(root: Path) -> None:
    """Create the two-burst document tree with explicit mtimes."""
    for rel, mtime in _BURST.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(f"Distinct content for {rel} about topic {rel.split('/')[0]}.\n")
        os.utime(fp, (mtime, mtime))


def _store(db_path: Path) -> Any:
    from mintmory.core.storage import StorageAdapter

    s = StorageAdapter(str(db_path))
    s.initialise()
    return s


def _doc_meta(store: Any, abs_path: str) -> dict[str, Any]:
    """Return the metadata dict of the active document memory for a path."""
    conn = store.connect()
    row = conn.execute(
        "SELECT metadata FROM memories "
        "WHERE source = 'document' AND is_archived = 0 "
        "AND json_extract(metadata, '$.path') = ? ORDER BY rowid DESC",
        (abs_path,),
    ).fetchone()
    assert row is not None, f"no document memory for {abs_path}"
    meta: dict[str, Any] = json.loads(row["metadata"] or "{}")
    return meta


# ---------------------------------------------------------------------------
# Recency through the real walk (no sklearn needed)
# ---------------------------------------------------------------------------


def test_index_tree_stamps_valid_from_from_mtime(cli_db: Path, tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    _make_tree(root)

    result = runner.invoke(app, ["index-tree", str(root), "--no-cochange"])
    assert result.exit_code == 0, result.output

    store = _store(cli_db)
    # Every document carries valid_from + the fs_mtime trust tier.
    for rel in _BURST:
        meta = _doc_meta(store, str(root / rel))
        assert meta["modified_source"] == "fs_mtime"
    # documents_timeline orders newest-first: folder_b (later mtime) before folder_a.
    from mintmory.core.cochange import documents_timeline

    rows = documents_timeline(store, limit=10)
    assert len(rows) == 4
    assert rows[0]["path"].endswith("f4.txt")
    assert rows[-1]["path"].endswith("f1.txt")


def test_docs_timeline_cli_runs(cli_db: Path, tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    _make_tree(root)
    assert runner.invoke(app, ["index-tree", str(root), "--no-cochange"]).exit_code == 0

    result = runner.invoke(app, ["docs", "timeline"])
    assert result.exit_code == 0, result.output
    assert "document(s)" in result.output


# ---------------------------------------------------------------------------
# Co-change via the real CLI (sklearn-gated)
# ---------------------------------------------------------------------------

sklearn = pytest.importorskip("sklearn", reason="scikit-learn not installed")


def test_index_tree_cochange_separates_two_bursts(cli_db: Path, tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    _make_tree(root)

    result = runner.invoke(app, ["index-tree", str(root), "--cochange"])
    assert result.exit_code == 0, result.output

    store = _store(cli_db)
    cs = {rel: _doc_meta(store, str(root / rel)).get("changeset_id") for rel in _BURST}
    # All four were assigned to a change-set.
    assert all(cs[r] is not None for r in _BURST), cs
    # Same-burst files share a change-set; cross-burst files do not.
    assert cs["folder_a/f1.txt"] == cs["folder_a/f2.txt"]
    assert cs["folder_b/f3.txt"] == cs["folder_b/f4.txt"]
    assert cs["folder_a/f1.txt"] != cs["folder_b/f3.txt"]


def test_docs_changed_with_shows_peer_and_honesty_label(cli_db: Path, tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    _make_tree(root)
    assert runner.invoke(app, ["index-tree", str(root), "--cochange"]).exit_code == 0

    f1 = str(root / "folder_a/f1.txt")
    result = runner.invoke(app, ["docs", "changed-with", f1])
    assert result.exit_code == 0, result.output
    # Honesty label is always printed.
    assert "not a version-controlled commit" in result.output
    # The same-folder peer (f2) is listed; the other burst (f3/f4) is not.
    assert "f2.txt" in result.output
    assert "f3.txt" not in result.output


def test_index_tree_cochange_idempotent_rerun(cli_db: Path, tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    _make_tree(root)

    first = runner.invoke(app, ["index-tree", str(root), "--cochange"])
    assert first.exit_code == 0, first.output

    store = _store(cli_db)
    # Snapshot edge counts after the first run.
    conn = store.connect()
    edges_before = conn.execute("SELECT COUNT(*) AS c FROM concept_links").fetchone()["c"]
    docs_before = conn.execute(
        "SELECT COUNT(*) AS c FROM memories WHERE source='document' AND is_archived=0"
    ).fetchone()["c"]

    # Re-run with no file changes: nothing changed -> co-change pass skipped.
    second = runner.invoke(app, ["index-tree", str(root), "--cochange"])
    assert second.exit_code == 0, second.output

    store2 = _store(cli_db)
    conn2 = store2.connect()
    edges_after = conn2.execute("SELECT COUNT(*) AS c FROM concept_links").fetchone()["c"]
    docs_after = conn2.execute(
        "SELECT COUNT(*) AS c FROM memories WHERE source='document' AND is_archived=0"
    ).fetchone()["c"]
    # No duplicate documents and no duplicate co-change edges.
    assert docs_after == docs_before
    assert edges_after == edges_before


# ---------------------------------------------------------------------------
# Graceful degradation when scikit-learn is unavailable (no importorskip:
# we simulate absence by shadowing sklearn.cluster in sys.modules)
# ---------------------------------------------------------------------------


def test_index_tree_cochange_degrades_without_sklearn(
    cli_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "corpus"
    _make_tree(root)

    # Make `from sklearn.cluster import HDBSCAN` raise ImportError inside
    # cluster_changesets, exercising the CoChangeUnavailable -> hint path.
    monkeypatch.setitem(sys.modules, "sklearn.cluster", None)
    # MM-34 F: the connected-components fallback never requires sklearn.
    # Disable the fallback (set max_n=1) so the HDBSCAN path is taken,
    # which then raises CoChangeUnavailable when sklearn is absent.
    # Set fallback_max_n=2 (minimum allowed) so 4 docs > 2 forces the HDBSCAN path.
    monkeypatch.setenv("MINTMORY_DOC_COCHANGE_FALLBACK_MAX_N", "2")

    result = runner.invoke(app, ["index-tree", str(root), "--cochange"])
    assert result.exit_code == 0, result.output
    assert "co-change skipped" in result.output

    # Recency still applied even though co-change was skipped.
    store = _store(cli_db)
    meta = _doc_meta(store, str(root / "folder_a/f1.txt"))
    assert meta["modified_source"] == "fs_mtime"
    assert "changeset_id" not in meta


# ---------------------------------------------------------------------------
# MM-34 new tests
# ---------------------------------------------------------------------------


def test_image_files_excluded_from_cochange_but_indexed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Image files are still indexed (file-record exists) but have no changeset_id."""
    db_path = tmp_path / "img_test.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("COLUMNS", "200")

    root = tmp_path / "corpus"
    root.mkdir()

    t0 = 1_700_000_000.0
    md_files = ["a.md", "b.md", "c.md"]
    img_files = ["img1.jpg", "img2.jpg"]
    for name in md_files:
        fp = root / name
        fp.write_text(f"Markdown content for {name} — distinct enough\n")
        os.utime(fp, (t0, t0))
    for name in img_files:
        fp = root / name
        fp.write_bytes(b"\xff\xd8\xff" + name.encode())  # minimal JPEG header
        os.utime(fp, (t0 + 10, t0 + 10))

    result = runner.invoke(
        app,
        ["index-tree", str(root), "--cochange", "--collection", "test-mm34"],
    )
    assert result.exit_code == 0, result.output

    store = _store(db_path)
    conn = store.connect()

    # Images must be indexed (file-record exists)
    for name in img_files:
        abs_path = str(root / name)
        row = conn.execute(
            "SELECT metadata FROM memories WHERE source='document' AND is_archived=0 "
            "AND json_extract(metadata, '$.path') = ?",
            (abs_path,),
        ).fetchone()
        assert row is not None, f"image {name} was not indexed"
        meta: dict[str, Any] = json.loads(row["metadata"] or "{}")
        assert "changeset_id" not in meta, f"image {name} should not have changeset_id"


def test_body_chunk_recency_and_record_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Body-text chunks get valid_from, modified_source='fs_mtime', record_role='chunk'."""
    db_path = tmp_path / "chunk_test.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("COLUMNS", "200")

    root = tmp_path / "corpus"
    root.mkdir()
    doc = root / "doc.md"
    doc.write_text("First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n")
    t = 1_700_000_000.0
    os.utime(doc, (t, t))

    result = runner.invoke(
        app,
        [
            "index-tree",
            str(root),
            "--no-cochange",
            "--collection",
            "test-chunk-recency",
            "--text-content",
            "--text-max-kb",
            "2048",
        ],
    )
    assert result.exit_code == 0, result.output

    store = _store(db_path)
    conn = store.connect()
    abs_path = str(doc)

    # File-record must have record_role="file"
    file_row = conn.execute(
        "SELECT metadata, valid_from FROM memories WHERE source='document' AND is_archived=0 "
        "AND json_extract(metadata, '$.path') = ? ORDER BY rowid DESC LIMIT 1",
        (abs_path,),
    ).fetchone()
    assert file_row is not None, "file-record not found"
    file_meta: dict[str, Any] = json.loads(file_row["metadata"] or "{}")
    assert file_meta.get("record_role") == "file", f"expected record_role=file, got {file_meta}"
    assert file_row["valid_from"] is not None, "file-record missing valid_from"

    # Body chunks must have record_role="chunk", modified_source="fs_mtime", valid_from set
    chunk_rows = conn.execute(
        "SELECT metadata, valid_from FROM memories WHERE source='document' AND is_archived=0 "
        "AND json_extract(metadata, '$.source_file') = ?",
        (abs_path,),
    ).fetchall()
    assert len(chunk_rows) >= 1, "no body chunks found"
    for row in chunk_rows:
        meta: dict[str, Any] = json.loads(row["metadata"] or "{}")
        assert meta.get("record_role") == "chunk", f"expected record_role=chunk, got {meta}"
        assert meta.get("modified_source") == "fs_mtime", f"expected fs_mtime, got {meta}"
        assert row["valid_from"] is not None, "chunk missing valid_from"


def test_cold_run_tags_cold_full_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """First (cold) run tags change-sets with changeset_kind='cold_full_index'."""
    db_path = tmp_path / "cold_test.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("COLUMNS", "200")

    root = tmp_path / "corpus"
    _make_tree(root)

    result = runner.invoke(
        app,
        ["index-tree", str(root), "--cochange", "--collection", "test-cold-kind"],
    )
    assert result.exit_code == 0, result.output

    store = _store(db_path)
    conn = store.connect()
    # All members that have a changeset_id should carry changeset_kind=cold_full_index
    rows = conn.execute(
        "SELECT metadata FROM memories WHERE source='document' AND is_archived=0 "
        "AND json_extract(metadata, '$.changeset_id') IS NOT NULL"
    ).fetchall()
    assert len(rows) >= 2, "expected at least 2 changeset members"
    for row in rows:
        meta: dict[str, Any] = json.loads(row["metadata"] or "{}")
        assert meta.get("changeset_kind") == "cold_full_index", (
            f"expected cold_full_index, got {meta.get('changeset_kind')!r} in {meta}"
        )


def test_incremental_run_tags_incremental(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Second run (after cold) tags change-sets with changeset_kind='incremental'."""
    db_path = tmp_path / "incr_test.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("COLUMNS", "200")

    root = tmp_path / "corpus"
    _make_tree(root)

    # First run (cold)
    r1 = runner.invoke(
        app,
        ["index-tree", str(root), "--cochange", "--collection", "test-incr-kind"],
    )
    assert r1.exit_code == 0, r1.output

    # Touch two files in a new time burst so they qualify as changed
    t_new = 1_700_000_000.0 + 100_000.0
    for name in ["folder_a/f1.txt", "folder_a/f2.txt"]:
        fp = root / name
        os.utime(fp, (t_new, t_new))

    # Second run (incremental — collection already has manifest rows)
    r2 = runner.invoke(
        app,
        ["index-tree", str(root), "--cochange", "--collection", "test-incr-kind"],
    )
    assert r2.exit_code == 0, r2.output

    store = _store(db_path)
    conn = store.connect()
    # Active changeset members should now carry 'incremental' (the second-run changeset)
    rows = conn.execute(
        "SELECT metadata FROM memories WHERE source='document' AND is_archived=0 "
        "AND json_extract(metadata, '$.changeset_kind') = 'incremental'"
    ).fetchall()
    assert len(rows) >= 2, "expected at least 2 incremental changeset members"


def test_docs_changed_with_shows_kind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """'docs changed-with' output contains the kind column."""
    db_path = tmp_path / "kind_cw_test.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("COLUMNS", "200")

    root = tmp_path / "corpus"
    _make_tree(root)

    r1 = runner.invoke(
        app,
        ["index-tree", str(root), "--cochange", "--collection", "test-cw-kind"],
    )
    assert r1.exit_code == 0, r1.output

    f1 = str(root / "folder_a/f1.txt")
    result = runner.invoke(app, ["docs", "changed-with", f1])
    assert result.exit_code == 0, result.output
    # The kind column header and value should appear
    assert "kind" in result.output
    # cold_full_index or incremental should appear
    assert "cold_full_index" in result.output or "incremental" in result.output


def test_summary_table_shows_cochange_kind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """index-tree --cochange summary table includes the 'cochange_kind' row."""
    db_path = tmp_path / "summary_kind_test.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("COLUMNS", "200")

    root = tmp_path / "corpus"
    _make_tree(root)

    result = runner.invoke(
        app,
        ["index-tree", str(root), "--cochange", "--collection", "test-summary-kind"],
    )
    assert result.exit_code == 0, result.output
    assert "cochange_kind" in result.output
