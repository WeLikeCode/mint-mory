"""
Concise projection helpers for MCP tool responses (MM-38).

Pure functions — no I/O, no model imports.  Each helper takes an already-
serialised dict (from model.model_dump(mode="json") or _shape_row) and returns
a smaller dict with only the fields an agent needs for browsing/scanning.

Use verbosity="full" (default) in every tool when you need the complete body or
metadata; verbosity="concise" for lightweight passes.
"""

from __future__ import annotations

from typing import Any

SNIPPET_CHARS = 200


def _snip(text: str, n: int = SNIPPET_CHARS) -> str:
    """Truncate *text* to *n* chars, appending '…' when truncated."""
    return text if len(text) <= n else text[:n].rstrip() + "…"


def concise_memory(rec: dict[str, Any]) -> dict[str, Any]:
    """Project a full MemoryRecord dict to {id, category, snippet, is_note}."""
    return {
        "id": rec["id"],
        "category": rec["category"],
        "snippet": _snip(rec.get("content", "")),
        "is_note": rec.get("is_note", False),
    }


def concise_memory_get(rec: dict[str, Any]) -> dict[str, Any]:
    """Project a full MemoryRecord dict to {id, category, content}.

    For single-memory fetches the caller *wants* the full content, so we keep
    it — we just drop the scoring/state machinery.
    """
    return {
        "id": rec["id"],
        "category": rec["category"],
        "content": rec.get("content", ""),
    }


def concise_search_response(resp: dict[str, Any]) -> dict[str, Any]:
    """Project a full SearchResponse dict to the concise envelope + lean hits."""
    return {
        "session_id": resp["session_id"],
        "total_found": resp["total_found"],
        "search_around_ids": resp.get("search_around_ids", []),
        "memories": [concise_memory(m) for m in resp["memories"]],
        # notes_on_results: ids only (no nested full records)
        "notes_on_results": {
            k: [n["id"] for n in v] for k, v in resp.get("notes_on_results", {}).items()
        },
    }


def concise_history_row(row: dict[str, Any]) -> dict[str, Any]:
    """Project a full _shape_row dict to {date, repo, kind, title, snippet}."""
    return {
        "date": row["date"],
        "repo": row["repo"],
        "kind": row["kind"],
        "title": row["title"],
        "snippet": _snip(row["summary"]),
    }
