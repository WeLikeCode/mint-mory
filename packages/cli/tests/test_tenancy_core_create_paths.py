"""RED tests for task 4 — the create paths that stay on the global tenant (5.7).

``index-tree`` (manifest + file records) and CLI ``ingest`` write ``global``
records in this release, even when another tenant already exists. The test
builds its schema and reads its results with raw SQL: the already-implemented
path is confirmed by a zero-value run that zeroes every public storage method.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from mintmory.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

_SCHEMA = Path(__file__).resolve().parents[2] / "core" / "src" / "mintmory" / "core" / "schema.sql"
_TS = "2026-01-01T00:00:00"


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT OR IGNORE INTO tenants (id, name, is_active, created_at, updated_at) "
        "VALUES (?, ?, 1, ?, ?)",
        ("t1", "t1", _TS, _TS),
    )
    conn.commit()
    conn.close()


def _rows(path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


@pytest.mark.l4("C-af9d319a")
def test_index_tree_and_cli_ingest_write_global_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    _init_db(db_path)

    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "note.txt").write_text("Alpha tree content.")

    indexed = runner.invoke(
        app,
        [
            "index-tree",
            str(tree),
            "--collection",
            "lib",
            "--no-text-content",
            "--no-cochange",
        ],
    )
    assert indexed.exit_code == 0, indexed.output

    created = _rows(db_path, "SELECT content, tenant_id, metadata FROM memories")
    assert created != []
    assert {row["tenant_id"] for row in created} == {"global"}
    file_records = [row for row in created if json.loads(row["metadata"]).get("rel") == "note.txt"]
    assert len(file_records) == 1
    assert "note.txt" in file_records[0]["content"]

    manifest = _rows(db_path, "SELECT path, tenant_id FROM index_manifest")
    assert manifest != []
    assert {row["tenant_id"] for row in manifest} == {"global"}
    assert {row["path"] for row in manifest} == {str(tree / "note.txt")}

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "memo.txt").write_text("Ingested memo content unique.")

    ingested = runner.invoke(app, ["ingest", str(docs / "memo.txt")])
    assert ingested.exit_code == 0, ingested.output

    chunks = _rows(
        db_path,
        "SELECT content, tenant_id FROM memories WHERE content = ?",
        ("Ingested memo content unique.",),
    )
    assert len(chunks) == 1
    assert chunks[0]["tenant_id"] == "global"
    assert {row["tenant_id"] for row in _rows(db_path, "SELECT tenant_id FROM memories")} == {
        "global"
    }
