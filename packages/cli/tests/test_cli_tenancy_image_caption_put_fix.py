"""RED tests for fix unit 1.1 — global image-caption-put must exit 1.

C-5cf1ac32 (R6.10) and C-e0c27b16 (R5.1): a missing active image file-record is
reported as ``error: no active image file-record found ...`` on stderr with exit
code 1, in the selected tenant and in the global scope.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from mintmory.cli.main import app
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import MemoryCategory, MemoryRecord, MemorySource
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the CLI at an isolated DB file under tmp_path."""
    db_path = tmp_path / "cli_image_caption_put_fix.db"
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


def _seed_image(path: Path) -> str:
    store = _open(path)
    try:
        record = store.add_memory(
            record=MemoryRecord(
                content="x.png",
                category=MemoryCategory.CONTEXT,
                source=MemorySource.DOCUMENT,
                tenant_id="acme",
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


def _json_list(output: str) -> list[dict[str, Any]]:
    start = output.find("[")
    end = output.rfind("]") + 1
    assert start != -1 and end > start, output
    return cast(list[dict[str, Any]], json.loads(output[start:end]))


@pytest.mark.l4("C-5cf1ac32", "C-e0c27b16")
def test_image_caption_put_refuses_a_global_image_with_exit_one(cli_db: Path) -> None:
    _create_acme()
    image_id = _seed_image(cli_db)

    scoped_jobs = runner.invoke(app, ["--tenant", "acme", "image-jobs", "--json"])
    assert scoped_jobs.exit_code == 0, scoped_jobs.output
    assert image_id in scoped_jobs.output

    global_jobs = runner.invoke(app, ["image-jobs", "--json"])
    assert global_jobs.exit_code == 0, global_jobs.output
    assert image_id not in global_jobs.output

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
    assert global_put.exit_code == 1, global_put.output
    assert "no active image file-record found" in global_put.output

    store = _open(cli_db)
    try:
        assert store.get_annotating_descriptions(image_id, 10, tenant_id="global") == []
    finally:
        store.close()


@pytest.mark.l4("C-e0c27b16", "C-5cf1ac32")
@pytest.mark.parametrize("missing", ["no-such-image-id", "/tmp/no-such-image.png"])
def test_image_caption_put_without_an_active_record_exits_one(cli_db: Path, missing: str) -> None:
    _create_acme()

    result = runner.invoke(app, ["--tenant", "acme", "image-caption-put", missing, "a cat"])
    assert result.exit_code == 1, result.output
    assert "error: no active image file-record found" in result.stderr
