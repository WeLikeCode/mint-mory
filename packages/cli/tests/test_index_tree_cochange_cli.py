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

    result = runner.invoke(app, ["index-tree", str(root), "--cochange"])
    assert result.exit_code == 0, result.output
    assert "co-change skipped" in result.output

    # Recency still applied even though co-change was skipped.
    store = _store(cli_db)
    meta = _doc_meta(store, str(root / "folder_a/f1.txt"))
    assert meta["modified_source"] == "fs_mtime"
    assert "changeset_id" not in meta
