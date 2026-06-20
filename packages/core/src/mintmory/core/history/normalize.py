"""
history/normalize.py — sessionizer helpers for time and repo resolution.

to_utc_iso(): coerce timestamps to ISO-8601 UTC 'Z' strings.
resolve_repo(): walk up a cwd path to find the git root, worktree-aware.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime


def to_utc_iso(ts: str | int | float | None) -> str | None:
    """
    Coerce epoch seconds/ms or an ISO string to ISO-8601 UTC 'Z'; None -> None.

    - int/float < 1e10 treated as epoch seconds; >= 1e10 as epoch milliseconds.
    - ISO string: parsed, converted to UTC, reformatted with 'Z' suffix.
    - Returns None on any parse failure (not on None input — that returns None).
    """
    if ts is None:
        return None

    if isinstance(ts, (int, float)):
        # Heuristic: epoch ms vs seconds (ms > year 2001 threshold)
        epoch_s = ts / 1000.0 if ts >= 1e10 else float(ts)
        try:
            dt = datetime.fromtimestamp(epoch_s, tz=UTC)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OSError, OverflowError, ValueError):
            return None

    # String path: try ISO parsing
    text = str(ts).strip()
    if not text:
        return None

    # Normalise trailing Z to +00:00 for fromisoformat
    normalized = text
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        # Try a few more formats (date-only or space-separated)
        candidate = normalized.split("+")[0] if len(normalized) <= 10 else normalized
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(candidate, fmt)
                break
            except ValueError:
                continue
        else:
            return None

    # Attach UTC if naive; convert if aware
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_repo(cwd: str | None) -> tuple[str, str]:
    """
    Return (repo_name, repo_path).

    Walk up ``cwd`` looking for a '.git' entry:
    - '.git' directory → git root is that directory's parent; repo_name = basename.
    - '.git' FILE (worktree) → read it to find 'gitdir: <real_gitdir>'; climb back
      to find the main worktree root (strip '/.git/worktrees/<name>' suffix if
      present); repo_name = basename of that root.

    Fallback: repo_name = basename(cwd) if cwd is non-empty, else 'unknown';
              repo_path = cwd or ''.
    """
    if not cwd:
        return ("unknown", "")

    cwd_abs = os.path.abspath(cwd)
    current = cwd_abs

    while True:
        git_candidate = os.path.join(current, ".git")

        if os.path.isdir(git_candidate):
            # Normal git repo: git root == current
            return (os.path.basename(current), current)

        if os.path.isfile(git_candidate):
            # Worktree: .git file contains "gitdir: <path>"
            try:
                with open(git_candidate) as fh:  # noqa: PTH123
                    content = fh.read().strip()
            except OSError:
                break
            match = re.match(r"gitdir:\s*(.+)", content)
            if match:
                real_gitdir = os.path.normpath(os.path.join(current, match.group(1).strip()))
                # Strip /.git/worktrees/<name> to get the main worktree root
                # Pattern: <root>/.git/worktrees/<worktree-name>
                parts = real_gitdir.replace("\\", "/").split("/")
                try:
                    git_idx = next(i for i in range(len(parts) - 1, -1, -1) if parts[i] == ".git")
                    main_root = "/".join(parts[:git_idx])
                    if main_root:
                        return (os.path.basename(main_root), main_root)
                except StopIteration:
                    pass
            # Fallback: use current as root
            return (os.path.basename(current), current)

        parent = os.path.dirname(current)
        if parent == current:
            # Reached filesystem root without finding .git
            break
        current = parent

    # Fallback
    repo_name = os.path.basename(cwd_abs) or "unknown"
    return (repo_name, cwd_abs)
