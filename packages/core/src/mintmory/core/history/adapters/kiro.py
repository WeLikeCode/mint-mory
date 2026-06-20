"""
history/adapters/kiro.py — adapter for Kiro agentic IDE sessions.

Sessions live under:
  ~/Library/Application Support/Kiro/User/globalStorage/kiro.kiroagent/
    workspace-sessions/<b64url_workspace_path>/<uuid>.json

Each workspace dir has a sibling sessions.json:
  [ {sessionId, title, dateCreated, workspaceDirectory}, ... ]

The dir name is base64url-encoded workspace path with '==' padding;
urlsafe_b64decode decodes it to the workspace path. Trailing garbage
bytes from padding misalignment are stripped.

Session JSON has:
  {
    sessionId: str,
    workspacePath|workspaceDirectory: str,
    title: str,
    history: [
      {
        message: {
          role: str,           # 'user' | 'assistant'
          content: str | list  # str shorthand OR list of {type, text} blocks
        }
      }, ...
    ]
  }

Roles may also appear as 'sender' in the outer item dict.
Ignores *.vscdb files.
Fails soft per malformed session (skips, never aborts).
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Iterator

from mintmory.core.history.models import NormalizedTurn, SessionSummary
from mintmory.core.history.normalize import resolve_repo, to_utc_iso

_DEFAULT_ROOT = "~/Library/Application Support/Kiro/User/globalStorage/kiro.kiroagent"


def _decode_workspace_dir(dirname: str) -> str | None:
    """
    Decode a base64url-encoded workspace dir name to a filesystem path.

    Adds '==' padding before decoding to handle Kiro's unpadded names.
    Strips trailing non-printable/garbage bytes from padding misalignment.
    Returns None on decode failure.
    """
    try:
        decoded_bytes = base64.urlsafe_b64decode(dirname + "==")
        # Decode as UTF-8, ignoring errors
        decoded = decoded_bytes.decode("utf-8", errors="replace")
        # Strip trailing garbage: '?', null bytes, replacement chars
        while (
            decoded and decoded[-1] in ("?", "\x00", "�") or (decoded and ord(decoded[-1]) < 0x20)
        ):
            decoded = decoded[:-1]
        return decoded or None
    except Exception:  # noqa: BLE001
        return None


def _load_sessions_json(workspace_dir: str) -> dict[str, dict[str, str]]:
    """
    Load sessions.json from a workspace dir.

    Returns {sessionId: {title, dateCreated, ...}} dict.
    """
    sessions_path = os.path.join(workspace_dir, "sessions.json")
    result: dict[str, dict[str, str]] = {}
    if not os.path.isfile(sessions_path):
        return result
    try:
        with open(sessions_path, encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    sid = item.get("sessionId", "")
                    if sid:
                        result[sid] = item
        elif isinstance(data, dict):
            # Some versions may use dict form
            for sid, item in data.items():
                if isinstance(item, dict):
                    result[sid] = item
    except (OSError, json.JSONDecodeError):
        pass
    return result


def _extract_text(content: object) -> str:
    """Flatten Kiro content (str or list of blocks) to text."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type", "")
                if btype == "text" or btype == "":
                    text = str(block.get("text", block.get("content", ""))).strip()
                    if text:
                        parts.append(text)
            elif isinstance(block, str):
                parts.append(block.strip())
        return "\n".join(p for p in parts if p)
    return ""


def _parse_session_file(
    path: str,
    session_meta: dict[str, str] | None,
    workspace_path: str,
) -> tuple[SessionSummary, list[NormalizedTurn]] | None:
    """
    Parse one Kiro session JSON file.

    Returns (SessionSummary, turns) or None.
    Fails soft on malformed content.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    session_id = data.get("sessionId") or os.path.splitext(os.path.basename(path))[0]
    title = data.get("title", "")
    cwd = data.get("workspacePath") or data.get("workspaceDirectory") or workspace_path

    # Enrich from sessions.json metadata
    date_created: str | None = None
    if session_meta:
        if not title:
            title = session_meta.get("title", "")
        raw_date = session_meta.get("dateCreated", "")
        if raw_date:
            # dateCreated is epoch-ms in Kiro
            try:
                date_created = to_utc_iso(int(raw_date))
            except (ValueError, TypeError):
                date_created = to_utc_iso(raw_date)

    history = data.get("history", [])
    if not isinstance(history, list):
        return None

    turns: list[NormalizedTurn] = []

    for item in history:
        if not isinstance(item, dict):
            continue

        message = item.get("message", item)  # fallback: item itself has role
        if not isinstance(message, dict):
            continue

        role = message.get("role") or item.get("sender", "")
        if not role:
            continue

        content = message.get("content") or item.get("text", "")
        text = _extract_text(content)
        if not text:
            continue

        # Normalize role
        if role not in ("user", "assistant", "tool"):
            role = "assistant" if role in ("agent", "kiro") else role

        ts_iso = date_created  # Kiro items don't have per-turn timestamps
        seq = len(turns)
        turns.append(
            NormalizedTurn(
                seq=seq,
                ts=ts_iso,
                role=role,
                text=text,
            )
        )

    if not turns:
        return None

    repo_name, repo_path = resolve_repo(cwd)

    ts_start = date_created or "1970-01-01T00:00:00Z"
    ts_end = ts_start

    summary = SessionSummary(
        session_id=session_id,
        agent="kiro",
        repo=repo_name,
        repo_path=repo_path,
        branch="",
        ts_start=ts_start,
        ts_end=ts_end,
        turn_count=len(turns),
        tools_used=[],
        title=title,
        source_path=os.path.abspath(path),
        source_offset=0,
        model="",
    )
    return summary, turns


def iter_sessions(
    root: str | None = None,
) -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
    """
    Iterate over all Kiro sessions under *root*.

    root defaults to ~/Library/Application Support/Kiro/User/globalStorage/kiro.kiroagent.
    Walks workspace-sessions/<b64url>/<uuid>.json files.
    Decodes dir name to workspace path via urlsafe_b64decode.
    Reads sibling sessions.json for dates and titles.
    Ignores *.vscdb files.
    Fails soft per malformed session.
    """
    if root is None:
        root = _DEFAULT_ROOT
    root_expanded = os.path.expanduser(root)

    ws_sessions_dir = os.path.join(root_expanded, "workspace-sessions")
    if not os.path.isdir(ws_sessions_dir):
        return

    for ws_entry in os.scandir(ws_sessions_dir):
        if not ws_entry.is_dir():
            continue

        # Decode the dir name to workspace path
        workspace_path = _decode_workspace_dir(ws_entry.name) or ""

        # Load sessions.json for this workspace
        session_map = _load_sessions_json(ws_entry.path)

        # Walk session files
        try:
            entries = list(os.scandir(ws_entry.path))
        except OSError:
            continue

        for file_entry in entries:
            fname = file_entry.name
            # Skip non-session files
            if fname == "sessions.json":
                continue
            if fname.endswith(".vscdb"):
                continue
            if not fname.endswith(".json"):
                continue

            session_id_from_name = os.path.splitext(fname)[0]
            session_meta = session_map.get(session_id_from_name)

            try:
                result = _parse_session_file(
                    file_entry.path,
                    session_meta,
                    workspace_path,
                )
            except Exception:  # noqa: BLE001 — fail soft
                continue

            if result is not None:
                yield result
