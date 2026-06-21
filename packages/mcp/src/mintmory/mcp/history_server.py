"""
MintMory History MCP Server — read-only agent-history index.

Exposes exactly three tools (NO write/mutate tools):
  history_timeline  — dated changelog of sessions in a time window
  history_search    — hybrid search across session summaries
  history_stats     — counts + date range of indexed sessions

Phase-2: rows include segment_index, segment_count, turn_lo, turn_hi, title,
outcome. history_stats returns total_sessions (distinct session_id) AND
total_segments (row count). timeline supports group_by_session.

The DB is resolved from MINTMORY_HISTORY_DB (or --db), defaulting to
~/.mintmory/agent-history.db.  At startup the Hermes guard is enforced so
a misconfigured path (pointing to the working store) fails fast.

Transport: stdio (default) or sse (--transport sse --port <N>).
"""

from __future__ import annotations

import os
from typing import Any

# FastMCP import — raises ImportError if mintmory-mcp not installed
try:
    from fastmcp import FastMCP
except ImportError as e:
    raise ImportError("fastmcp is not installed. Run: uv sync --package mintmory-mcp") from e

from mintmory.core.history import query
from mintmory.core.history.ingest import DEFAULT_HISTORY_DB, _assert_not_working_db

# ---------------------------------------------------------------------------
# Server initialisation
# ---------------------------------------------------------------------------

mcp: FastMCP[Any] = FastMCP(
    "mintmory-history",
    instructions=(
        "This server is READ-ONLY history of past coding sessions across "
        "Claude Code / Codex / Kiro. "
        "Use 'history_timeline' for 'what changed / was fixed in the last N days/weeks/months' "
        "queries — returns newest-first dated session summaries with source_path back-links. "
        "Use 'history_search' for topic recall across all indexed sessions. "
        "Use 'history_stats' to see counts of sessions/segments by source and kind, plus the "
        "earliest/latest session dates. "
        "No tool here writes, adds, archives, dreams, or otherwise mutates any store."
    ),
)


def _db_path() -> str:
    """Return the history DB path from MINTMORY_HISTORY_DB or the default."""
    return os.environ.get("MINTMORY_HISTORY_DB", os.path.expanduser(DEFAULT_HISTORY_DB))


# ---------------------------------------------------------------------------
# Tools — read-only
# ---------------------------------------------------------------------------


@mcp.tool()
def history_timeline(
    since: str = "90d",
    from_date: str | None = None,
    to_date: str | None = None,
    repo: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    group: bool = False,
) -> list[dict[str, Any]]:
    """Dated changelog of agent sessions in a time window (the 'what changed N ago' query).

    Returns newest-first session summaries from the agent-history index.
    Each result is a dict with: date, ts_start, agent, collection, repo, branch,
    kind, title, summary, session_id, source_path, segment_index, segment_count,
    turn_lo, turn_hi, outcome.

    Args:
        since: Relative window like '90d', '8w', '3m', '2y' (default '90d').
               Mutually exclusive with from_date/to_date.
        from_date: ISO start date/datetime (inclusive).  Use instead of since.
        to_date: ISO end date/datetime (inclusive).  Use instead of since.
        repo: Optional repo-name filter (exact match on metadata.repo).
        kind: Optional kind filter (fix/feature/refactor/…).
        limit: Max rows to return (default 50).
        group: When True, group segments by session (each session's segments
               in ascending segment_index order, groups newest-first).
    """
    # If both from_date and to_date are None but since has its default value,
    # pass since through as-is.  If the caller explicitly passes from_date or
    # to_date, suppress the default since so the pair works as from/to only.
    effective_since: str | None = since
    if from_date is not None or to_date is not None:
        effective_since = None

    return query.timeline(
        _db_path(),
        since=effective_since,
        from_iso=from_date,
        to_iso=to_date,
        repo=repo,
        kind=kind,
        limit=limit,
        group_by_session=group,
    )


@mcp.tool()
def history_search(
    query_text: str,
    repo: str | None = None,
    since: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Hybrid search across indexed agent session summaries.

    Searches the full-text + vector index for sessions matching query_text,
    filtered to only session_summary records.  Optionally constrained by
    repo and/or a recency window.

    Args:
        query_text: Natural-language search query.
        repo: Optional repo-name filter (exact match on metadata.repo).
        since: Optional recency window like '90d', '8w', '3m' (no from/to here).
        limit: Max results to return (default 10).

    Returns:
        List of row dicts in search-rank order (same shape as history_timeline).
    """
    return query.search(_db_path(), query_text, repo=repo, since=since, limit=limit)


@mcp.tool()
def history_stats() -> dict[str, Any]:
    """Counts of indexed sessions and segments by source (collection) and kind, plus date range.

    Read-only.  Returns a dict with:
      total_sessions: distinct session_id count (logical sessions)
      total_segments: total row count (one per segment per session)
      by_collection: {collection_name: count}
      by_kind: {kind: count}
      earliest: ISO date of the oldest segment (or null)
      latest: ISO date of the newest segment (or null)
    """
    import json as _json

    # Reuse the shared opener (Hermes guard + parent-dir creation) — single source of truth.
    store = query._open_history(_db_path())
    conn = store.connect()

    rows = conn.execute(
        "SELECT metadata, valid_from FROM memories "
        "WHERE is_archived = 0 "
        "  AND json_extract(metadata, '$.record_type') = 'session_summary' "
        "ORDER BY valid_from ASC"
    ).fetchall()

    by_collection: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    earliest: str | None = None
    latest: str | None = None
    session_ids: set[str] = set()

    for row in rows:
        meta: dict[str, Any] = _json.loads(row["metadata"] or "{}")
        coll = meta.get("collection", "unknown")
        knd = meta.get("kind", "unknown")
        by_collection[coll] = by_collection.get(coll, 0) + 1
        by_kind[knd] = by_kind.get(knd, 0) + 1
        vf = (row["valid_from"] or "")[:10] or None
        if vf:
            if earliest is None:
                earliest = vf
            latest = vf
        sid = meta.get("session_id", "")
        if sid:
            session_ids.add(sid)

    return {
        "total_sessions": len(session_ids),
        "total_segments": len(rows),
        "by_collection": by_collection,
        "by_kind": by_kind,
        "earliest": earliest,
        "latest": latest,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the mintmory-history MCP server.

    Enforces the Hermes guard on startup so a misconfigured DB path
    (pointing to the working store) fails fast before serving.
    """
    import argparse

    parser = argparse.ArgumentParser(description="MintMory History MCP Server (read-only)")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport to use (default: stdio)",
    )
    parser.add_argument("--port", type=int, default=8082, help="Port for SSE transport")
    parser.add_argument(
        "--db",
        default=None,
        help="Path to history SQLite DB (sets MINTMORY_HISTORY_DB)",
    )
    args = parser.parse_args()

    if args.db:
        os.environ["MINTMORY_HISTORY_DB"] = args.db

    # Guard: fail fast if the path resolves to the working store
    _assert_not_working_db(_db_path())

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse", port=args.port)


if __name__ == "__main__":
    main()
