"""
history/adapters/codex.py — adapter for Codex (OpenAI Codex CLI) sessions.

Session data lives under ~/.codex/sessions/**/ as rollout-*.jsonl files.

Each rollout file has JSONL lines with {type, timestamp, payload}:
  - type='session_meta': payload has id, cwd, model_provider, cli_version
  - type='response_item': payload has role + content[] blocks
      content block types: 'input_text', 'output_text' (and possibly others)
  - type='event_msg': skip (task_started, input_request, etc.)

Additional enrichments:
  - ~/.codex/session_index.jsonl: maps id -> thread_name (title)
  - ~/.codex/external_agent_session_imports.json: skip imported_thread_ids

Skips: *.sqlite, codex-dev.db, *.db files.
Fails soft per malformed session (skips, never aborts the walk).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator

from mintmory.core.history.models import NormalizedTurn, SessionSummary
from mintmory.core.history.normalize import resolve_repo, to_utc_iso

_DEFAULT_ROOT = "~/.codex/sessions"
_SESSION_INDEX = "~/.codex/session_index.jsonl"
_IMPORTS_FILE = "~/.codex/external_agent_session_imports.json"


def _load_session_index(codex_root: str) -> dict[str, str]:
    """
    Load ~/.codex/session_index.jsonl -> {id: thread_name}.
    Returns empty dict if file not present or malformed.
    """
    index_path = os.path.join(os.path.dirname(codex_root), "session_index.jsonl")
    result: dict[str, str] = {}
    if not os.path.isfile(index_path):
        return result
    try:
        with open(index_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    sid = obj.get("id", "")
                    name = obj.get("thread_name", "")
                    if sid:
                        result[sid] = name
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return result


def _load_imported_ids(codex_root: str) -> set[str]:
    """
    Load ~/.codex/external_agent_session_imports.json and return the set of
    imported_thread_ids to skip — but ONLY for imports whose original
    ``source_path`` still exists on disk (i.e. will be indexed via that source's
    own adapter, e.g. Claude Code). If the source file is gone, Codex holds the
    only surviving copy, so we DON'T skip it (otherwise the session is lost).
    """
    imports_path = os.path.join(os.path.dirname(codex_root), "external_agent_session_imports.json")
    result: set[str] = set()
    if not os.path.isfile(imports_path):
        return result
    try:
        with open(imports_path, encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
        records = data.get("records", []) if isinstance(data, dict) else data
        if isinstance(records, list):
            for rec in records:
                tid = rec.get("imported_thread_id", "")
                source_path = rec.get("source_path", "")
                # Skip only if the original still exists (avoids double-count);
                # if it's missing, keep the Codex copy so the session survives.
                if tid and source_path and os.path.exists(source_path):
                    result.add(tid)
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return result


def _extract_text_from_content_blocks(content: list[object]) -> str:
    """Flatten Codex content blocks to plain text."""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype in ("input_text", "output_text"):
            text = str(block.get("text", "")).strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _parse_rollout_file(
    path: str,
    session_index: dict[str, str],
    imported_ids: set[str],
) -> tuple[SessionSummary, list[NormalizedTurn]] | None:
    """
    Parse one rollout-*.jsonl file.

    Returns (SessionSummary, turns) or None.
    Fails soft on malformed lines.
    """
    session_id: str | None = None
    cwd: str | None = None
    model: str = ""
    title: str = ""
    ts_list: list[str] = []
    turns: list[NormalizedTurn] = []

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
            continue

        if not isinstance(obj, dict):
            continue

        ltype = obj.get("type", "")
        raw_ts = obj.get("timestamp")
        ts_iso = to_utc_iso(raw_ts)
        payload = obj.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        if ltype == "session_meta":
            sid = payload.get("id", "")
            if sid:
                session_id = sid
                # Check import skip
                if session_id in imported_ids:
                    return None
                # Enrich title from index
                title = session_index.get(session_id, "")
            cwd = payload.get("cwd") or cwd
            # Prefer an actual model id; fall back to the provider name if absent.
            model = str(payload.get("model") or payload.get("model_provider", ""))
            # Record the session start timestamp from meta
            if ts_iso and ts_iso not in ts_list:
                ts_list.insert(0, ts_iso)

        elif ltype == "response_item":
            role = payload.get("role", "")
            content = payload.get("content", [])
            if not isinstance(content, list):
                continue

            # Normalize role: Codex uses 'developer', map to 'assistant'
            normalized_role = role
            if role in ("developer",):
                normalized_role = "assistant"
            elif role not in ("user", "assistant", "tool"):
                normalized_role = role  # preserve as-is

            text = _extract_text_from_content_blocks(content)
            if not text:
                continue

            seq = len(turns)
            if ts_iso and ts_iso not in ts_list:
                ts_list.append(ts_iso)

            turns.append(
                NormalizedTurn(
                    seq=seq,
                    ts=ts_iso,
                    role=normalized_role,
                    text=text,
                )
            )

        elif ltype == "event_msg":
            # Skip event messages (task_started, input_request, etc.)
            continue
        else:
            continue

    if not turns:
        return None

    if not session_id:
        # Derive from filename: rollout-<date>-<uuid>.jsonl
        basename = os.path.splitext(os.path.basename(path))[0]
        # Last UUID portion after the last '-' groups
        parts = basename.split("-")
        # rollout-YYYY-MM-DDT... schema: last 5 parts are the UUID
        session_id = "-".join(parts[-5:]) if len(parts) >= 5 else basename

    # Check import skip if session_meta wasn't found
    if session_id in imported_ids:
        return None

    repo_name, repo_path = resolve_repo(cwd)
    ts_start = ts_list[0] if ts_list else "1970-01-01T00:00:00Z"
    ts_end = ts_list[-1] if ts_list else ts_start

    summary = SessionSummary(
        session_id=session_id,
        agent="codex",
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
        model=model,
    )
    return summary, turns


def iter_sessions(
    root: str | None = None,
) -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
    """
    Iterate over all Codex sessions under *root*.

    root defaults to ~/.codex/sessions.
    Walks subdirectories for rollout-*.jsonl files.
    Enriches titles from session_index.jsonl.
    Skips imported sessions (external_agent_session_imports.json).
    Fails soft per malformed session.
    """
    if root is None:
        root = _DEFAULT_ROOT
    root_expanded = os.path.expanduser(root)

    if not os.path.isdir(root_expanded):
        return

    session_index = _load_session_index(root_expanded)
    imported_ids = _load_imported_ids(root_expanded)

    for dirpath, _dirnames, filenames in os.walk(root_expanded):
        for fname in filenames:
            # Skip db files
            if fname.endswith((".sqlite", ".db")):
                continue
            if not fname.endswith(".jsonl"):
                continue
            if not fname.startswith("rollout-"):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                result = _parse_rollout_file(fpath, session_index, imported_ids)
            except Exception:  # noqa: BLE001 — fail soft
                continue
            if result is not None:
                yield result
