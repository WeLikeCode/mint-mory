"""
history/query.py — shared read-only query surface for the agent-history index.

Provides resolve_window, timeline, and search.  These are the single source of
truth consumed by both the ``mintmory history timeline/search`` CLI commands
and the ``mintmory-history-mcp`` server — results are therefore identical
across both surfaces.

All times are naive-UTC to match the storage layer's valid_from column.

Phase-2 changes:
- _shape_row adds segment_index, segment_count, turn_lo, turn_hi, title, outcome.
- timeline ORDER BY valid_from DESC, session_id ASC, segment_index ASC (tiebreak).
- timeline(..., group_by_session=False): when True, group rows by session_id.
- search ranks segments individually; shape is unchanged otherwise.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from mintmory.core.history.ingest import _assert_not_working_db
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import MemoryFilter, SearchRequest

DEFAULT_WINDOW_DAYS = 90

# Multipliers matching the CLI _parse_since grammar exactly:
#   d → 1 day, w → 7 days, m → 30 days, y → 365 days
_UNIT_DAYS: dict[str, int] = {"d": 1, "w": 7, "m": 30, "y": 365}


# ---------------------------------------------------------------------------
# Window resolver
# ---------------------------------------------------------------------------


def resolve_window(
    *,
    since: str | None,
    from_iso: str | None,
    to_iso: str | None,
    now: datetime,
) -> tuple[datetime, datetime]:
    """Return (start, end) as naive-UTC datetimes.

    Rules:
    - ``since`` ('75d' / '8w' / '3m' / '2y') is mutually exclusive with
      ``from_iso`` / ``to_iso``.  Providing both raises ``ValueError``.
    - ``since`` → (now - delta, now).
    - ``from_iso`` / ``to_iso`` → (parse(from_iso) or datetime.min,
      parse(to_iso) or now).
    - Neither → (now - DEFAULT_WINDOW_DAYS days, now).

    Grammar for ``since``: <N><unit> where unit ∈ {d, w, m, y}.
    Multipliers: d=1 day, w=7 days, m=30 days, y=365 days.
    """
    if since is not None and (from_iso is not None or to_iso is not None):
        raise ValueError(
            "--since and --from/--to are mutually exclusive; provide one or the other."
        )

    if since is not None:
        m = re.fullmatch(r"(\d+)([dwmy])", since.strip())
        if not m:
            raise ValueError(
                f"Invalid since value {since!r}; expected e.g. '75d', '8w', '3m', '2y'."
            )
        n = int(m.group(1))
        unit = m.group(2)
        delta = timedelta(days=n * _UNIT_DAYS[unit])
        return now - delta, now

    if from_iso is not None or to_iso is not None:
        start = datetime.fromisoformat(from_iso) if from_iso else datetime.min
        end = datetime.fromisoformat(to_iso) if to_iso else now
        # Strip timezone info to keep naive-UTC consistent with storage
        if start.tzinfo is not None:
            start = start.replace(tzinfo=None)
        if end.tzinfo is not None:
            end = end.replace(tzinfo=None)
        return start, end

    # Default: last 90 days
    return now - timedelta(days=DEFAULT_WINDOW_DAYS), now


# ---------------------------------------------------------------------------
# DB opener (enforces Hermes guard)
# ---------------------------------------------------------------------------


def _open_history(db_path: str) -> StorageAdapter:
    """Expand db_path, enforce the Hermes guard, open + return a StorageAdapter.

    Callers treat the returned adapter as read-only; this function never writes.
    Raises HermesGuardError if db_path resolves to the working store.
    """
    expanded = os.path.expanduser(db_path)
    _assert_not_working_db(expanded)
    # Create the parent dir (matches the old CLI helper) so a first-run query on a
    # machine without ~/.mintmory/ shows an empty timeline instead of crashing.
    parent = os.path.dirname(os.path.abspath(expanded))
    if parent:
        os.makedirs(parent, exist_ok=True)
    store = StorageAdapter(expanded)
    store.initialise()
    return store


# ---------------------------------------------------------------------------
# Row shaper
# ---------------------------------------------------------------------------


def _shape_row(content: str, meta: dict[str, Any], valid_from: str | None) -> dict[str, Any]:
    """Convert a raw DB row into the standard row-dict shape.

    Phase-2: adds segment_index, segment_count, turn_lo, turn_hi, title, outcome.
    """
    date_str = (valid_from or "")[:10]
    return {
        "date": date_str,
        "ts_start": meta.get("ts_start", ""),
        "agent": meta.get("agent", ""),
        "collection": meta.get("collection", ""),
        "repo": meta.get("repo", ""),
        "branch": meta.get("branch", ""),
        "kind": meta.get("kind", ""),
        "title": meta.get("title", ""),
        "summary": content,
        "session_id": meta.get("session_id", ""),
        "source_path": meta.get("source_path", ""),
        # Phase-2 segment fields
        "segment_index": meta.get("segment_index", 0),
        "segment_count": meta.get("segment_count", 1),
        "turn_lo": meta.get("turn_lo", 0),
        "turn_hi": meta.get("turn_hi", 0),
        "outcome": meta.get("outcome", ""),
    }


# ---------------------------------------------------------------------------
# timeline
# ---------------------------------------------------------------------------


def timeline(
    db_path: str,
    *,
    since: str | None = None,
    from_iso: str | None = None,
    to_iso: str | None = None,
    repo: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    now: datetime | None = None,
    group_by_session: bool = False,
) -> list[dict[str, Any]]:
    """Return session summaries whose valid_from falls in the resolved window.

    Results are newest-first (with segment tiebreak), filtered by ``repo`` and/or
    ``kind`` when supplied. Each element is a dict with: date, ts_start, agent,
    collection, repo, branch, kind, title, summary (=content), session_id,
    source_path, segment_index, segment_count, turn_lo, turn_hi, outcome.

    Phase-2 ORDER BY: valid_from DESC, session_id ASC, segment_index ASC — the
    tiebreak is REQUIRED so segments within the same second stay in author order.

    When group_by_session=True: rows are grouped by session_id (each group in
    ascending segment_index order), groups ordered by newest valid_from.

    Query: is_archived=0 AND metadata.record_type='session_summary'
           AND valid_from in [start, end]
           (+ optional metadata.repo / metadata.kind)
           ORDER BY valid_from DESC, session_id ASC, segment_index ASC
           LIMIT ?.
    """
    if now is None:
        now = datetime.now(UTC).replace(tzinfo=None)

    start, end = resolve_window(since=since, from_iso=from_iso, to_iso=to_iso, now=now)
    store = _open_history(db_path)
    conn = store.connect()

    # Push repo/kind filters INTO the SQL WHERE so LIMIT applies AFTER filtering.
    # (Filtering in Python after a SQL LIMIT silently truncated --repo/--kind to
    # whatever survived the global newest-N cut — i.e. the filter "didn't work".)
    where = [
        "is_archived = 0",
        "json_extract(metadata, '$.record_type') = 'session_summary'",
        "valid_from >= ?",
        "valid_from <= ?",
    ]
    params: list[Any] = [start.isoformat(), end.isoformat()]
    if repo is not None:
        where.append("json_extract(metadata, '$.repo') = ?")
        params.append(repo)
    if kind is not None:
        where.append("json_extract(metadata, '$.kind') = ?")
        params.append(kind)
    params.append(limit)

    rows = conn.execute(
        "SELECT content, metadata, valid_from FROM memories "
        "WHERE " + " AND ".join(where) + " "
        "ORDER BY valid_from DESC, "
        "         json_extract(metadata, '$.session_id') ASC, "
        "         CAST(json_extract(metadata, '$.segment_index') AS INTEGER) ASC "
        "LIMIT ?",
        params,
    ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        meta: dict[str, Any] = json.loads(row["metadata"] or "{}")
        result.append(_shape_row(row["content"], meta, row["valid_from"]))

    if group_by_session:
        result = _group_rows_by_session(result)

    return result


def _group_rows_by_session(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group flat rows by session_id, preserving newest-first group order.

    Each group is in ascending segment_index order.  Groups are ordered by the
    newest valid_from seen within that session (i.e. the order the session's
    first segment appeared in the incoming newest-first list).
    """
    seen_order: list[str] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        sid = row["session_id"]
        if sid not in groups:
            seen_order.append(sid)
            groups[sid] = []
        groups[sid].append(row)

    out: list[dict[str, Any]] = []
    for sid in seen_order:
        group = sorted(groups[sid], key=lambda r: r.get("segment_index", 0))
        out.extend(group)
    return out


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def search(
    db_path: str,
    query: str,
    *,
    repo: str | None = None,
    since: str | None = None,
    limit: int = 10,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Hybrid search (StorageAdapter.search) over session summaries only.

    Optionally constrained to ``repo`` and/or ``valid_from >= (now - since)``.
    Returns the same row-dict shape as timeline(), in search-rank order.

    Phase-2: rows now include segment_index, segment_count, turn_lo, turn_hi, outcome.
    """
    if now is None:
        now = datetime.now(UTC).replace(tzinfo=None)

    window_start: datetime | None = None
    if since is not None:
        window_start, _ = resolve_window(since=since, from_iso=None, to_iso=None, now=now)

    # repo/since are post-filters (the hybrid ranker has no metadata predicate), so
    # over-fetch candidates before applying them — otherwise a repo with few top-ranked
    # hits gets truncated to nothing by the limit*3 cut (the --repo "doesn't work" bug).
    # SearchRequest.limit is capped at 100 by the schema, so over-fetch up to that.
    overfetch = max(limit * 3, 100) if (repo is not None or since is not None) else limit * 3
    overfetch = min(overfetch, 100)
    store = _open_history(db_path)
    response = store.search(
        SearchRequest(
            query=query,
            limit=overfetch,
            filter=MemoryFilter(active_only=True),
        )
    )

    results: list[dict[str, Any]] = []
    for mem in response.memories:
        raw_meta = mem.metadata
        if isinstance(raw_meta, str):
            meta: dict[str, Any] = json.loads(raw_meta)
        else:
            meta = raw_meta or {}

        if meta.get("record_type") != "session_summary":
            continue
        if repo is not None and meta.get("repo", "") != repo:
            continue
        if (
            window_start is not None
            and mem.valid_from is not None
            and mem.valid_from < window_start
        ):
            continue

        valid_from_str = mem.valid_from.isoformat() if mem.valid_from else None
        results.append(_shape_row(mem.content, meta, valid_from_str))
        if len(results) >= limit:
            break

    return results
