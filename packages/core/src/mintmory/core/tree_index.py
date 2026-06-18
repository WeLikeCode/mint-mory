"""
Stat-only directory-tree walking + file-record rendering for recurrent indexing.

The walk NEVER opens a file — it uses ``os.stat`` only — so pointing it at a
cloud-backed (OneDrive Files-On-Demand) tree does not trigger downloads. Each
file becomes a deterministic *file-record*: its name, type, size, mtime, online-
only status, and the names of its folder neighbours (the "contextual information"
that a non-text file still carries). Full-text extraction is a separate, opt-in
step layered on top by the CLI (it is the only thing that reads bytes).

See openspec/changes/add-recurrent-tree-indexing/.
"""

from __future__ import annotations

import fnmatch
import os
import stat as stat_mod
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# Build artifacts — excluded only if the caller opts in via --exclude; kept here
# so callers (and tests) share one definition of "obviously not knowledge".
ARTIFACT_SUFFIXES: frozenset[str] = frozenset(
    {".dll", ".exe", ".pdb", ".jar", ".class", ".o", ".obj", ".bin", ".crc", ".lib", ".so"}
)

# Filenames that are never knowledge (macOS cruft). The custom-folder-icon file
# is literally "Icon" followed by a carriage return — built via chr(13) so no raw
# CR ends up in this source file.
_SKIP_NAMES: frozenset[str] = frozenset({".DS_Store", "Thumbs.db", "Icon", "Icon" + chr(13)})

_TYPE_LABELS: dict[str, str] = {
    ".pdf": "PDF document",
    ".doc": "Word document",
    ".docx": "Word document",
    ".xls": "Excel spreadsheet",
    ".xlsx": "Excel spreadsheet",
    ".ppt": "PowerPoint deck",
    ".pptx": "PowerPoint deck",
    ".txt": "text file",
    ".md": "Markdown file",
    ".html": "HTML page",
    ".htm": "HTML page",
    ".csv": "CSV table",
    ".json": "JSON file",
    ".xml": "XML file",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".gif": "image",
    ".svg": "vector image",
    ".psd": "Photoshop image",
    ".eps": "vector image",
    ".xd": "Adobe XD design",
    ".vsdx": "Visio diagram",
    ".dwg": "CAD drawing",
    ".mp4": "video",
    ".mov": "video",
    ".zip": "archive",
    ".rar": "archive",
}


@dataclass(frozen=True)
class FileEntry:
    """One file, captured from ``os.stat`` only (no content read)."""

    path: Path
    rel: str  # path relative to the walk root (POSIX-style)
    size: int
    mtime: float
    online_only: bool  # cloud placeholder: has size but no local data blocks

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()

    @property
    def name(self) -> str:
        return self.path.name


@dataclass(frozen=True)
class DirGroup:
    """All kept files in one directory — gives each entry its sibling context."""

    directory: Path
    rel_dir: str
    entries: list[FileEntry]


def _is_online_only(st: os.stat_result) -> bool:
    """A cloud placeholder reports a real size but zero allocated blocks."""
    return getattr(st, "st_blocks", 1) == 0 and st.st_size > 0


def _matches_any(name: str, rel: str, patterns: Sequence[str]) -> bool:
    """True if the filename OR its root-relative path matches any glob."""
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p) for p in patterns)


def iter_dir_groups(
    root: str | Path,
    *,
    include: Sequence[str] = ("*",),
    exclude: Sequence[str] = (),
    follow_symlinks: bool = False,
) -> Iterator[DirGroup]:
    """Yield one ``DirGroup`` per directory under ``root`` (stat-only).

    ``include``/``exclude`` are globs matched against both the bare filename and
    the root-relative path (so ``"Personal/**"`` excludes a whole subtree). Empty
    ``include`` means "everything". Excluded directories are pruned (not walked).
    """
    root_path = Path(root).expanduser()
    for dirpath, dirnames, filenames in os.walk(root_path, followlinks=follow_symlinks):
        rel_dir = os.path.relpath(dirpath, root_path)
        rel_dir = "" if rel_dir == "." else rel_dir

        # Prune excluded subdirectories in place so os.walk does not descend.
        kept: list[str] = []
        for dn in dirnames:
            dn_rel = f"{rel_dir}/{dn}" if rel_dir else dn
            excluded = exclude and (
                _matches_any(dn, dn_rel, exclude) or _matches_any(dn, f"{dn_rel}/", exclude)
            )
            if not excluded:
                kept.append(dn)
        dirnames[:] = kept

        entries: list[FileEntry] = []
        for fn in filenames:
            if fn in _SKIP_NAMES:
                continue
            f_rel = f"{rel_dir}/{fn}" if rel_dir else fn
            if include and not _matches_any(fn, f_rel, include):
                continue
            if exclude and _matches_any(fn, f_rel, exclude):
                continue
            fp = Path(dirpath) / fn
            try:
                st = fp.stat()
            except OSError:
                continue  # vanished mid-walk / permission — skip silently
            if not stat_mod.S_ISREG(st.st_mode):
                continue
            entries.append(
                FileEntry(
                    path=fp,
                    rel=f_rel,
                    size=st.st_size,
                    mtime=st.st_mtime,
                    online_only=_is_online_only(st),
                )
            )
        if entries:
            yield DirGroup(directory=Path(dirpath), rel_dir=rel_dir, entries=entries)


def human_size(n: int) -> str:
    """Human-readable byte count (e.g. 84 KB, 3.1 MB)."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def type_label(suffix: str) -> str:
    """Friendly type name for a suffix (e.g. '.docx' -> 'Word document')."""
    suffix = suffix.lower()
    if suffix in _TYPE_LABELS:
        return _TYPE_LABELS[suffix]
    return f"{suffix[1:].upper()} file" if suffix else "file"


def render_file_record(
    entry: FileEntry,
    group: DirGroup,
    root_label: str,
    *,
    max_siblings: int = 12,
) -> str:
    """Render the deterministic metadata + folder-context text for one file."""
    date = datetime.fromtimestamp(entry.mtime, tz=UTC).strftime("%Y-%m-%d")
    folder_parts = [p for p in Path(entry.rel).parent.parts if p not in (".", "")]
    location = " / ".join([root_label, *folder_parts])

    header = (
        f"File: {entry.name} "
        f"({type_label(entry.suffix)}, {human_size(entry.size)}, modified {date})"
    )
    lines = [header, f"Location: {location}"]
    siblings = sorted(e.name for e in group.entries if e.path != entry.path)
    if siblings:
        shown = ", ".join(siblings[:max_siblings])
        more = f" (+{len(siblings) - max_siblings} more)" if len(siblings) > max_siblings else ""
        lines.append(f"Alongside {len(siblings)} file(s) in this folder: {shown}{more}.")
    if entry.online_only:
        lines.append("Status: online-only (not downloaded).")
    return "\n".join(lines)
