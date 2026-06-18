"""
Unit tests for ``mintmory.core.tree_index`` — the stat-only tree walker and
file-record renderer used by recurrent indexing. No network, no file content
reads beyond what the synthetic tmp tree contains.
"""

from __future__ import annotations

import types
from pathlib import Path

from mintmory.core.tree_index import (
    DirGroup,
    FileEntry,
    _is_online_only,
    human_size,
    iter_dir_groups,
    render_file_record,
    type_label,
)


def _make_tree(root: Path) -> None:
    (root / "a.md").write_text("# A\n\ndoc about AXIS")
    (root / "b.txt").write_text("notes")
    (root / "build.dll").write_bytes(b"\x00\x01binary")
    sub = root / "Personal"
    sub.mkdir()
    (sub / "secret.jpg").write_bytes(b"\xff\xd8\xff fake jpeg")
    work = root / "Work"
    work.mkdir()
    (work / "plan.docx").write_bytes(b"PK\x03\x04 fake")
    (work / "diagram.vsdx").write_bytes(b"PK\x03\x04 fake visio")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def test_human_size() -> None:
    assert human_size(0) == "0 B"
    assert human_size(512) == "512 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"


def test_type_label_known_and_unknown() -> None:
    assert type_label(".docx") == "Word document"
    assert type_label(".JPG") == "image"  # case-insensitive
    assert type_label(".xyz") == "XYZ file"
    assert type_label("") == "file"


def test_is_online_only_detects_placeholder() -> None:
    placeholder = types.SimpleNamespace(st_blocks=0, st_size=1000)
    local = types.SimpleNamespace(st_blocks=8, st_size=1000)
    empty = types.SimpleNamespace(st_blocks=0, st_size=0)
    assert _is_online_only(placeholder) is True  # type: ignore[arg-type]
    assert _is_online_only(local) is False  # type: ignore[arg-type]
    assert _is_online_only(empty) is False  # type: ignore[arg-type] # zero-byte not a placeholder


# ---------------------------------------------------------------------------
# iter_dir_groups
# ---------------------------------------------------------------------------
def test_iter_dir_groups_yields_all_files_by_default(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    groups = list(iter_dir_groups(tmp_path))
    names = {e.name for g in groups for e in g.entries}
    assert names == {"a.md", "b.txt", "build.dll", "secret.jpg", "plan.docx", "diagram.vsdx"}
    # Every entry has a rel path and a (real, local) stat.
    for g in groups:
        for e in g.entries:
            assert e.online_only is False  # real tmp files have data blocks
            assert e.size >= 0


def test_iter_dir_groups_include_filter(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    groups = list(iter_dir_groups(tmp_path, include=["*.docx", "*.md"]))
    names = {e.name for g in groups for e in g.entries}
    assert names == {"a.md", "plan.docx"}


def test_iter_dir_groups_exclude_folder_and_suffix(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    groups = list(iter_dir_groups(tmp_path, exclude=["Personal/**", "*.dll"]))
    names = {e.name for g in groups for e in g.entries}
    assert "secret.jpg" not in names  # whole Personal subtree pruned
    assert "build.dll" not in names  # suffix excluded
    assert {"a.md", "b.txt", "plan.docx", "diagram.vsdx"} <= names


def test_iter_dir_groups_skips_macos_cruft(tmp_path: Path) -> None:
    (tmp_path / ".DS_Store").write_bytes(b"x")
    (tmp_path / "real.txt").write_text("hi")
    names = {e.name for g in iter_dir_groups(tmp_path) for e in g.entries}
    assert names == {"real.txt"}


# ---------------------------------------------------------------------------
# render_file_record
# ---------------------------------------------------------------------------
def _entry(rel: str, *, online_only: bool = False, size: int = 84_000) -> FileEntry:
    return FileEntry(
        path=Path("/root") / rel, rel=rel, size=size, mtime=1_700_000_000.0, online_only=online_only
    )


def test_render_file_record_includes_type_location_and_siblings() -> None:
    e1 = _entry("Work/plan.docx")
    e2 = _entry("Work/logo.svg")
    e3 = _entry("Work/deck.pptx")
    group = DirGroup(directory=Path("/root/Work"), rel_dir="Work", entries=[e1, e2, e3])
    text = render_file_record(e1, group, "Acme")
    assert "plan.docx" in text
    assert "Word document" in text
    assert "82.0 KB" in text
    assert "Location: Acme / Work" in text
    assert "deck.pptx" in text and "logo.svg" in text  # siblings listed
    assert "modified 2023-11-14" in text  # mtime rendered as a date


def test_render_file_record_caps_siblings() -> None:
    entries = [_entry(f"D/f{i}.txt") for i in range(20)]
    group = DirGroup(directory=Path("/root/D"), rel_dir="D", entries=entries)
    text = render_file_record(entries[0], group, "Root", max_siblings=5)
    assert "Alongside 19 file(s)" in text
    assert "+14 more" in text


def test_render_file_record_flags_online_only() -> None:
    e = _entry("Work/big.pdf", online_only=True)
    group = DirGroup(directory=Path("/root/Work"), rel_dir="Work", entries=[e])
    text = render_file_record(e, group, "Root")
    assert "online-only" in text


def test_render_file_record_root_level_file_has_clean_location() -> None:
    e = _entry("top.md")
    group = DirGroup(directory=Path("/root"), rel_dir="", entries=[e])
    text = render_file_record(e, group, "Root")
    assert "Location: Root" in text  # no trailing ' / '
    assert "/ ." not in text
