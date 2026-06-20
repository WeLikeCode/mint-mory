"""
history/adapters/claude_code.py — adapter for Claude Code sessions.

Parses ~/.claude/projects/<project>/<uuid>.jsonl files.

Each JSONL file is one session. Lines have a 'type' field:
  - 'user' / 'assistant': chat turns
  - others: metadata, attachments, file snapshots (skipped for turns)

message.content may be a string OR a list of blocks:
  - {type: 'text', text: str}         -> role text turn
  - {type: 'tool_use', name: str}     -> role='tool' turn
  - {type: 'tool_result', ...}        -> role='tool' turn (result)
  - {type: 'thinking', ...}           -> skip

Lines where isSidechain=True are always skipped.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

from mintmory.core.history.models import NormalizedTurn, SessionSummary
from mintmory.core.history.normalize import resolve_repo, to_utc_iso

_DEFAULT_ROOT = "~/.claude/projects"


def _extract_text_from_content(content: Any) -> str:
    """Flatten message.content (str or list of blocks) to plain text."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype == "text":
            parts.append(str(block.get("text", "")))
        elif btype == "tool_result":
            # content inside tool_result can be str or list
            inner = block.get("content", "")
            parts.append(_extract_text_from_content(inner))
    return "\n".join(p for p in parts if p)


def _parse_session_file(
    path: str,
) -> tuple[SessionSummary, list[NormalizedTurn]] | None:
    """
    Parse one <uuid>.jsonl session file.

    Returns (SessionSummary, turns) or None if the file yields no turns.
    Fails soft on malformed lines (skips them, never aborts).
    """
    session_id: str | None = None
    cwd: str | None = None
    git_branch: str = ""
    model: str = ""
    ts_list: list[str] = []
    turns: list[NormalizedTurn] = []
    tools_seen: list[str] = []

    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return None

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue  # fail soft

        if not isinstance(obj, dict):
            continue

        # Skip sidechain lines
        if obj.get("isSidechain"):
            continue

        ltype = obj.get("type", "")

        # Harvest session-level fields from any line
        if session_id is None and obj.get("sessionId"):
            session_id = obj["sessionId"]
        if cwd is None and obj.get("cwd"):
            cwd = obj["cwd"]
        if not git_branch and obj.get("gitBranch"):
            git_branch = obj["gitBranch"]

        if ltype not in ("user", "assistant"):
            continue

        # Harvest timestamp
        raw_ts = obj.get("timestamp")
        ts_iso = to_utc_iso(raw_ts)
        if ts_iso:
            ts_list.append(ts_iso)

        message = obj.get("message")
        if not isinstance(message, dict):
            continue

        # Harvest model from assistant messages
        if ltype == "assistant" and not model:
            model = str(message.get("model", ""))

        content = message.get("content", "")
        seq = len(turns)

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "text":
                    text = str(block.get("text", "")).strip()
                    if text:
                        role = "user" if ltype == "user" else "assistant"
                        turns.append(
                            NormalizedTurn(
                                seq=seq,
                                ts=ts_iso,
                                role=role,
                                text=text,
                            )
                        )
                        seq += 1
                elif btype == "tool_use":
                    tool_name = str(block.get("name", ""))
                    if tool_name and tool_name not in tools_seen:
                        tools_seen.append(tool_name)
                    turns.append(
                        NormalizedTurn(
                            seq=seq,
                            ts=ts_iso,
                            role="tool",
                            text=f"tool_use:{tool_name}",
                            tool_name=tool_name or None,
                        )
                    )
                    seq += 1
                elif btype == "tool_result":
                    inner_content = block.get("content", "")
                    text = _extract_text_from_content(inner_content).strip()
                    turns.append(
                        NormalizedTurn(
                            seq=seq,
                            ts=ts_iso,
                            role="tool",
                            text=text or "(tool result)",
                            tool_name=None,
                        )
                    )
                    seq += 1
                # skip 'thinking' and unknown block types
        else:
            # content is a string
            text = str(content).strip() if content else ""
            if text:
                role = "user" if ltype == "user" else "assistant"
                turns.append(
                    NormalizedTurn(
                        seq=seq,
                        ts=ts_iso,
                        role=role,
                        text=text,
                    )
                )

    if not session_id:
        # Fall back to filename UUID
        session_id = os.path.splitext(os.path.basename(path))[0]

    if not turns:
        return None

    repo_name, repo_path = resolve_repo(cwd)
    ts_start = ts_list[0] if ts_list else "1970-01-01T00:00:00Z"
    ts_end = ts_list[-1] if ts_list else ts_start

    summary = SessionSummary(
        session_id=session_id,
        agent="claude_code",
        repo=repo_name,
        repo_path=repo_path,
        branch=git_branch,
        ts_start=ts_start,
        ts_end=ts_end,
        turn_count=len(turns),
        tools_used=tools_seen,
        source_path=os.path.abspath(path),
        source_offset=0,
        model=model,
    )
    return summary, turns


def iter_sessions(
    root: str | None = None,
) -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
    """
    Iterate over all Claude Code sessions under *root*.

    root defaults to ~/.claude/projects.
    Each <uuid>.jsonl file is one session.
    Fails soft per malformed session (skips, never aborts the walk).
    """
    if root is None:
        root = _DEFAULT_ROOT
    root_expanded = os.path.expanduser(root)

    if not os.path.isdir(root_expanded):
        return

    for project_entry in os.scandir(root_expanded):
        if not project_entry.is_dir():
            continue
        try:
            project_entries = list(os.scandir(project_entry.path))
        except OSError:
            continue
        for file_entry in project_entries:
            if not file_entry.name.endswith(".jsonl"):
                continue
            try:
                result = _parse_session_file(file_entry.path)
            except Exception:  # noqa: BLE001 — fail soft
                continue
            if result is not None:
                yield result
