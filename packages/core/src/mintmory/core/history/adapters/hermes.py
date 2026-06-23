"""
history/adapters/hermes.py — adapter for Hermes agentic sessions.

Sessions live at ~/.hermes/sessions/session_<YYYYMMDD>_<HHMMSS>_<hash>.json.
Each file is a single JSON object (not JSONL):
  {
    "session_id": str,
    "model": str,
    "base_url": str,
    "platform": str,
    "session_start": ISO8601,
    "last_updated": ISO8601,
    "system_prompt": str,
    "tools": [{"type": str, "function": {"name": str, ...}}, ...],
    "message_count": int,
    "messages": [{"role": "user"|"assistant"|"tool", "content": str|dict|list,
                  "tool_calls": [...], "tool_call_id": str, ...}, ...]
  }

Interactive-only: files whose basename begins with "session_cron_" are skipped.
Files not matching session_*.json (e.g. request_dump_*.json, *.jsonl) are also
skipped — only basenames starting with "session_" and ending with ".json" are
parsed.

Fails soft per malformed session (skips, never aborts the walk).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

from mintmory.core.history.models import NormalizedTurn, SessionSummary

_DEFAULT_ROOT = "~/.hermes/sessions"

_VALID_ROLES: frozenset[str] = frozenset({"user", "assistant", "tool"})


def _content_text(content: Any) -> str:
    """Flatten message content (str | dict | list | None) to plain text.

    - str  → returned as-is
    - dict or list → json.dumps with sort_keys=True for determinism
    - None or other → empty string
    """
    if isinstance(content, str):
        return content
    if isinstance(content, (dict, list)):
        return json.dumps(content, sort_keys=True, ensure_ascii=False)
    return ""


def _extract_tool_name(msg: dict[str, Any]) -> str | None:
    """Best-effort extraction of a tool name from an assistant or tool message.

    For assistant messages, checks tool_calls[0].function.name.
    For tool messages, checks the content dict's 'name'/'tool' key.
    Returns None if no name can be determined.
    """
    role = msg.get("role", "")
    if role == "assistant":
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            first = tool_calls[0]
            if isinstance(first, dict):
                fn = first.get("function", {})
                if isinstance(fn, dict) and fn.get("name"):
                    return str(fn["name"])
    content = msg.get("content")
    if isinstance(content, dict):
        for key in ("name", "tool"):
            if content.get(key):
                return str(content[key])
    return None


def _parse_session(
    path: str,
) -> tuple[SessionSummary, list[NormalizedTurn]] | None:
    """Parse one Hermes session_*.json file.

    Returns (SessionSummary, turns) or None if:
      - file is not readable or contains invalid JSON
      - top-level value is not a dict
      - messages list is absent or empty
      - no usable turns after flattening
    Never raises — always fails soft.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            obj = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(obj, dict):
        return None

    raw_messages = obj.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        return None

    # --- Build turns ---
    turns: list[NormalizedTurn] = []
    tools_seen: list[str] = []

    for _i, msg in enumerate(raw_messages):
        if not isinstance(msg, dict):
            continue

        raw_role = msg.get("role", "")
        role = raw_role if raw_role in _VALID_ROLES else "tool"

        content = msg.get("content")
        text = _content_text(content).strip()
        if not text:
            continue

        tool_name = _extract_tool_name(msg)
        if tool_name and tool_name not in tools_seen:
            tools_seen.append(tool_name)

        turns.append(
            NormalizedTurn(
                seq=len(turns),
                ts=None,  # Hermes messages carry no per-turn timestamp
                role=role,
                text=text,
                tool_name=tool_name,
            )
        )

    if not turns:
        return None

    # --- tools_used: merge per-message tool names with top-level tools list ---
    top_tools = obj.get("tools")
    if isinstance(top_tools, list):
        for t in top_tools:
            if isinstance(t, dict):
                fn = t.get("function", {})
                if isinstance(fn, dict):
                    name = fn.get("name", "")
                    if name and name not in tools_seen:
                        tools_seen.append(name)
    tools_used = sorted(set(tools_seen))

    # --- Session metadata ---
    session_id = obj.get("session_id") or os.path.splitext(os.path.basename(path))[0]
    ts_start = obj.get("session_start") or "1970-01-01T00:00:00Z"
    ts_end = obj.get("last_updated") or ts_start

    summary = SessionSummary(
        session_id=str(session_id),
        agent="hermes",
        repo="hermes",
        repo_path="",
        branch="",
        ts_start=str(ts_start),
        ts_end=str(ts_end),
        turn_count=len(turns),
        tools_used=tools_used,
        source_path=os.path.abspath(path),
        source_offset=0,
        model=str(obj.get("model", "")),
    )
    return summary, turns


def iter_sessions(
    root: str | None = None,
) -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
    """Iterate over interactive Hermes sessions under *root*.

    root defaults to ~/.hermes/sessions.
    Reads session_*.json files; skips session_cron_* (background routines).
    Fails soft per malformed session (skips, never aborts the walk).
    """
    if root is None:
        root = _DEFAULT_ROOT
    root_expanded = os.path.expanduser(root)

    if not os.path.isdir(root_expanded):
        return

    try:
        entries = list(os.scandir(root_expanded))
    except OSError:
        return

    for entry in entries:
        name = entry.name
        # Only parse session_*.json files (not request_dump_*, not *.jsonl)
        if not name.startswith("session_") or not name.endswith(".json"):
            continue
        # Exclude background cron sessions
        if name.startswith("session_cron_"):
            continue
        try:
            result = _parse_session(entry.path)
        except Exception:  # noqa: BLE001 — fail soft
            continue
        if result is not None:
            yield result
