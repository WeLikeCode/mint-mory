# MM-38 Optimize MCP Token Usage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in `verbosity="concise"` parameter to the four token-heavy MCP read tools, reducing token cost by ~90% while keeping `verbosity="full"` (the default) byte-identical to today.

**Architecture:** A new pure module `concise.py` holds all projection logic (no I/O, no model imports). The two MCP server files wire the parameter to that module — no changes to core types or query layer (CLI output unaffected). Docs get the relocated `memory_dream` LLM env-var prose and a note about `verbosity="concise"`.

**Tech Stack:** Python 3.12, FastMCP, Pydantic v2, pytest-asyncio, mypy --strict, ruff line-length 100, uv workspace.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| **Create** | `packages/mcp/src/mintmory/mcp/concise.py` | Pure projection helpers; no I/O |
| **Modify** | `packages/mcp/src/mintmory/mcp/server.py` | Wire `verbosity` param into `memory_search`, `memory_get`; trim `memory_dream` docstring; tighten `instructions` |
| **Modify** | `packages/mcp/src/mintmory/mcp/history_server.py` | Wire `verbosity` into `history_timeline`, `history_search`; tighten `instructions` |
| **Create** | `packages/mcp/tests/test_concise.py` | Pure unit tests for concise.py helpers |
| **Modify** | `packages/mcp/tests/test_tools.py` | Add verbosity regression tests for memory_search and memory_get |
| **Modify** | `packages/mcp/tests/test_history_mcp.py` | Add verbosity regression tests for history_timeline and history_search |
| **Modify** | `docs/agent-history-mcp.md` | Add `verbosity="concise"` option note; add relocated memory_dream LLM config prose |

---

## Task 1: Create `concise.py` — pure projection helpers

**Files:**
- Create: `packages/mcp/src/mintmory/mcp/concise.py`

- [ ] **Step 1: Write the file**

```python
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
            k: [n["id"] for n in v]
            for k, v in resp.get("notes_on_results", {}).items()
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
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync python -c "from mintmory.mcp.concise import concise_memory, concise_search_response, concise_history_row, concise_memory_get, _snip; print('ok')"
```

Expected: `ok`

---

## Task 2: Write pure unit tests for `concise.py`

**Files:**
- Create: `packages/mcp/tests/test_concise.py`
- Test: `packages/mcp/tests/test_concise.py`

- [ ] **Step 1: Write the test file**

```python
"""
Pure unit tests for mintmory.mcp.concise (MM-38).

No I/O, no DB, no FastMCP client — just dict-in / dict-out.
"""

from __future__ import annotations

import json

import pytest

from mintmory.mcp.concise import (
    SNIPPET_CHARS,
    _snip,
    concise_history_row,
    concise_memory,
    concise_memory_get,
    concise_search_response,
)

# ---------------------------------------------------------------------------
# _snip
# ---------------------------------------------------------------------------


def test_snip_short_unchanged() -> None:
    assert _snip("hello") == "hello"


def test_snip_exactly_n_unchanged() -> None:
    text = "x" * SNIPPET_CHARS
    assert _snip(text) == text
    assert "…" not in _snip(text)


def test_snip_longer_truncated_with_ellipsis() -> None:
    text = "a" * (SNIPPET_CHARS + 50)
    result = _snip(text)
    assert result.endswith("…")
    assert len(result) <= SNIPPET_CHARS + 1  # +1 for the ellipsis char


def test_snip_empty_string() -> None:
    assert _snip("") == ""


def test_snip_custom_n() -> None:
    result = _snip("hello world", n=5)
    assert result == "hello…"


def test_snip_trailing_whitespace_stripped_before_ellipsis() -> None:
    # Content that ends with spaces at the cut point should get rstripped
    text = "a" * 198 + "  " + "b" * 50
    result = _snip(text)
    # The result should not have trailing spaces before the ellipsis
    assert result.endswith("…")
    assert not result[:-1].endswith(" ")


# ---------------------------------------------------------------------------
# concise_memory
# ---------------------------------------------------------------------------

_FULL_RECORD: dict = {
    "id": "mem-001",
    "content": "Redis caches sessions.",
    "category": "fact",
    "entity_ids": ["redis"],
    "confidence": 0.9,
    "source": "agent",
    "verified": False,
    "valid_from": None,
    "valid_until": None,
    "usefulness_score": 3.5,
    "staleness_score": 0.1,
    "reinforcement_count": 2,
    "retrieval_count": 5,
    "is_stale": False,
    "is_active": True,
    "is_archived": False,
    "superseded_by": None,
    "flagged_for_review": False,
    "contradicts_ids": [],
    "is_note": False,
    "created_at": "2025-01-01T00:00:00",
    "updated_at": "2025-01-01T00:00:00",
    "last_accessed_at": None,
    "metadata": {"project": "mintkey"},
}

_EXPECTED_CONCISE_MEMORY_KEYS = {"id", "category", "snippet", "is_note"}
_FULL_ONLY_KEYS = {
    "usefulness_score",
    "staleness_score",
    "reinforcement_count",
    "retrieval_count",
    "metadata",
    "entity_ids",
    "content",
    "verified",
    "created_at",
    "updated_at",
}


def test_concise_memory_exact_fields() -> None:
    result = concise_memory(_FULL_RECORD)
    assert set(result.keys()) == _EXPECTED_CONCISE_MEMORY_KEYS


def test_concise_memory_dropped_fields_absent() -> None:
    result = concise_memory(_FULL_RECORD)
    for key in _FULL_ONLY_KEYS:
        assert key not in result, f"dropped key {key!r} still present"


def test_concise_memory_values_correct() -> None:
    result = concise_memory(_FULL_RECORD)
    assert result["id"] == "mem-001"
    assert result["category"] == "fact"
    assert result["is_note"] is False
    # short content → no ellipsis
    assert result["snippet"] == "Redis caches sessions."


def test_concise_memory_long_content_snippeted() -> None:
    long_record = dict(_FULL_RECORD, content="z" * 500)
    result = concise_memory(long_record)
    assert result["snippet"].endswith("…")
    assert len(result["snippet"]) <= SNIPPET_CHARS + 1


def test_concise_memory_is_note_flag_preserved() -> None:
    note_record = dict(_FULL_RECORD, is_note=True)
    result = concise_memory(note_record)
    assert result["is_note"] is True


# ---------------------------------------------------------------------------
# concise_memory_get
# ---------------------------------------------------------------------------

_EXPECTED_CONCISE_GET_KEYS = {"id", "category", "content"}


def test_concise_memory_get_exact_fields() -> None:
    result = concise_memory_get(_FULL_RECORD)
    assert set(result.keys()) == _EXPECTED_CONCISE_GET_KEYS


def test_concise_memory_get_dropped_fields_absent() -> None:
    result = concise_memory_get(_FULL_RECORD)
    for key in _FULL_ONLY_KEYS - {"content"}:
        assert key not in result, f"dropped key {key!r} still present"


def test_concise_memory_get_full_content_preserved() -> None:
    long_content = "y" * 1000
    record = dict(_FULL_RECORD, content=long_content)
    result = concise_memory_get(record)
    # concise_get keeps FULL content (unlike concise_memory which snippets)
    assert result["content"] == long_content
    assert "…" not in result["content"]


def test_concise_memory_get_values_correct() -> None:
    result = concise_memory_get(_FULL_RECORD)
    assert result["id"] == "mem-001"
    assert result["category"] == "fact"
    assert result["content"] == "Redis caches sessions."


# ---------------------------------------------------------------------------
# concise_search_response
# ---------------------------------------------------------------------------

_FULL_RESPONSE: dict = {
    "session_id": "sess-abc",
    "total_found": 2,
    "search_around_ids": ["mem-003"],
    "memories": [_FULL_RECORD, dict(_FULL_RECORD, id="mem-002", content="Another memory.")],
    "notes_on_results": {
        "mem-001": [dict(_FULL_RECORD, id="note-001", is_note=True)],
    },
}


def test_concise_search_response_envelope_preserved() -> None:
    result = concise_search_response(_FULL_RESPONSE)
    assert result["session_id"] == "sess-abc"
    assert result["total_found"] == 2
    assert result["search_around_ids"] == ["mem-003"]


def test_concise_search_response_memories_are_concise() -> None:
    result = concise_search_response(_FULL_RESPONSE)
    for mem in result["memories"]:
        assert set(mem.keys()) == _EXPECTED_CONCISE_MEMORY_KEYS


def test_concise_search_response_notes_reduced_to_ids() -> None:
    result = concise_search_response(_FULL_RESPONSE)
    # notes_on_results must be {str: list[str]} — ids only, NOT full records
    notes = result["notes_on_results"]
    assert isinstance(notes, dict)
    assert notes["mem-001"] == ["note-001"]
    # The value is a list of strings, not dicts
    for note_id in notes["mem-001"]:
        assert isinstance(note_id, str)


def test_concise_search_response_empty_notes_ok() -> None:
    resp_no_notes = dict(_FULL_RESPONSE, notes_on_results={})
    result = concise_search_response(resp_no_notes)
    assert result["notes_on_results"] == {}


def test_concise_search_response_missing_search_around_ids() -> None:
    resp = {k: v for k, v in _FULL_RESPONSE.items() if k != "search_around_ids"}
    result = concise_search_response(resp)
    assert result["search_around_ids"] == []


def test_concise_search_response_is_materially_smaller() -> None:
    full_json = json.dumps(_FULL_RESPONSE)
    concise_json = json.dumps(concise_search_response(_FULL_RESPONSE))
    assert len(concise_json) < len(full_json), (
        f"concise ({len(concise_json)}) not smaller than full ({len(full_json)})"
    )


# ---------------------------------------------------------------------------
# concise_history_row
# ---------------------------------------------------------------------------

_FULL_ROW: dict = {
    "date": "2025-06-01",
    "ts_start": "2025-06-01T10:00:00Z",
    "agent": "claude_code",
    "collection": "claude-code",
    "repo": "mintkey",
    "branch": "main",
    "kind": "fix",
    "title": "Fix auth bug",
    "summary": "Implemented PKCE flow and fixed the OAuth token refresh bug in auth.py",
    "session_id": "sess-xyz",
    "source_path": "/home/user/.claude/transcripts/sess-xyz.jsonl",
    "segment_index": 0,
    "segment_count": 1,
    "turn_lo": 0,
    "turn_hi": 8,
    "outcome": "success",
}

_EXPECTED_CONCISE_ROW_KEYS = {"date", "repo", "kind", "title", "snippet"}
_HISTORY_FULL_ONLY_KEYS = {
    "ts_start",
    "agent",
    "collection",
    "branch",
    "summary",
    "session_id",
    "source_path",
    "segment_index",
    "segment_count",
    "turn_lo",
    "turn_hi",
    "outcome",
}


def test_concise_history_row_exact_fields() -> None:
    result = concise_history_row(_FULL_ROW)
    assert set(result.keys()) == _EXPECTED_CONCISE_ROW_KEYS


def test_concise_history_row_dropped_fields_absent() -> None:
    result = concise_history_row(_FULL_ROW)
    for key in _HISTORY_FULL_ONLY_KEYS:
        assert key not in result, f"dropped key {key!r} still present"


def test_concise_history_row_values_correct() -> None:
    result = concise_history_row(_FULL_ROW)
    assert result["date"] == "2025-06-01"
    assert result["repo"] == "mintkey"
    assert result["kind"] == "fix"
    assert result["title"] == "Fix auth bug"
    # Short summary → no ellipsis
    assert "…" not in result["snippet"]


def test_concise_history_row_long_summary_snippeted() -> None:
    long_row = dict(_FULL_ROW, summary="w" * 500)
    result = concise_history_row(long_row)
    assert result["snippet"].endswith("…")
```

- [ ] **Step 2: Run the pure unit tests**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/test_concise.py -v
```

Expected: all tests pass.

---

## Task 3: Modify `server.py` — wire `verbosity` into `memory_search` and `memory_get`, trim `memory_dream` docstring and `instructions`

**Files:**
- Modify: `packages/mcp/src/mintmory/mcp/server.py:30-86,144-212,215-231`

- [ ] **Step 1: Add the `Literal` import and `concise` import**

In `server.py`, change the `from typing import Any` line to:

```python
from typing import Any, Literal
```

And add after the `from mintmory.core.types import (` block (after the closing `)`) a new import line:

```python
from mintmory.mcp.concise import concise_memory_get, concise_search_response
```

- [ ] **Step 2: Replace `memory_get` function body** (lines 144-152 currently)

Replace the entire `memory_get` function with:

```python
@mcp.tool()
def memory_get(
    memory_id: str,
    verbosity: Literal["full", "concise"] = "full",
) -> dict[str, Any] | None:
    """Retrieve a single memory by its ID. Returns None if not found.

    Pass verbosity="concise" for a compact {id, category, content} projection
    when you only need the body; use the default "full" for all fields.
    """
    store = _get_store()
    record = store.get_memory(memory_id)
    if record is None:
        return None
    result: dict[str, Any] = record.model_dump(mode="json")
    if verbosity == "concise":
        return concise_memory_get(result)
    return result
```

- [ ] **Step 3: Replace `memory_search` function signature and body** (lines 155-212 currently)

Replace the entire `memory_search` function with:

```python
@mcp.tool()
def memory_search(
    query: str,
    limit: int = 10,
    category: str | None = None,
    entity: str | None = None,
    search_around_link_types: list[str] | None = None,
    search_around_depth: int = 1,
    exclude_stale: bool = True,
    verbosity: Literal["full", "concise"] = "full",
) -> dict[str, Any]:
    """
    Search memories using hybrid FTS5 + vector similarity.

    Optionally traverses the concept graph (search_around) to find
    memories linked to the direct results via typed relationships.

    This implements the 'search in search OR scoped by relationships'
    requirement: results include both the direct matches AND memories
    reachable via the specified link types.

    Args:
        query: Natural language search query.
        limit: Max results to return (1–100).
        category: Filter by memory category.
        entity: Filter by entity appearing in entity_ids.
        search_around_link_types: Graph traversal link types, e.g.
            ['contradicts', 'relates_to']. Empty = all types.
        search_around_depth: How many hops to traverse (1–3).
        exclude_stale: Whether to exclude stale memories.
        verbosity: "full" (default) returns the complete SearchResponse with
            full MemoryRecord objects; "concise" returns a compact projection
            {id, category, snippet, is_note} per hit — use it for browsing/
            scanning; call memory_get with verbosity="full" when you need the body.

    Returns:
        SearchResponse dict with session_id, memories, total_found,
        and search_around_ids (IDs added via graph traversal).
    """
    store = _get_store()

    memory_filter = MemoryFilter(
        category=MemoryCategory(category) if category is not None else None,
        entity=entity,
        exclude_stale=exclude_stale,
    )

    search_around: SearchAroundSpec | None = None
    if search_around_link_types is not None:
        search_around = SearchAroundSpec(
            link_types=[ConceptLinkType(lt) for lt in search_around_link_types],
            depth=search_around_depth,
        )

    request = SearchRequest(
        query=query,
        limit=limit,
        filter=memory_filter,
        search_around=search_around,
    )
    response = store.search(request)
    result: dict[str, Any] = response.model_dump(mode="json")
    if verbosity == "concise":
        return concise_search_response(result)
    return result
```

- [ ] **Step 4: Replace `memory_dream` docstring** (trim the embedded env-var prose)

Replace the current `memory_dream` docstring:

```python
    """
    Run the dreaming consolidation process.

    Light: anomaly detection + concept linking + summary generation.
    Full: light + contradiction resolution + archival + rehabilitation.

    The summarizer + contradiction resolver are built from the configured LLM tier
    (MINTMORY_LLM_*; e.g. Ollama or a Portkey/OpenAI-compatible gateway). When
    MINTMORY_LLM_PROVIDER=none (the default), the summary-generation and
    contradiction-resolution steps are skipped (counts stay 0) and only the
    structural steps run. Linking + summary policy follow MINTMORY_LINK_* /
    MINTMORY_SUMMARY_*.

    Returns a DreamReport with counts of changes made.
    """
```

with:

```python
    """
    Run the dreaming consolidation process.

    Light: anomaly detection + concept linking + summary generation.
    Full: light + contradiction resolution + archival + rehabilitation.

    LLM-backed steps follow the configured tier; see docs/agent-history-mcp.md
    (LLM/config section). With MINTMORY_LLM_PROVIDER=none (default) only the
    structural steps run (summaries and contradiction resolution are skipped).

    Returns a DreamReport with counts of changes made.
    """
```

- [ ] **Step 5: Tighten the `instructions` block** (lines 63-86)

Replace the current `instructions=(...)` string in the `FastMCP(...)` call with this tighter version (keeps all routing guidance, drops repetitive prose, adds concise note):

```python
    instructions=(
        "MintMory: typed memory system for LLM agents (8 categories: fact, skill, "
        "preference, identity, context, episodic, temporal, relationship; "
        "12 ConceptLink types including annotates). "
        "BROWSING: use memory_search with verbosity=\"concise\" for id+snippet results "
        "when scanning many memories; switch to verbosity=\"full\" (default) only when "
        "you need complete body/metadata. "
        "GRAPH: use search_around to traverse the memory graph via typed relationships. "
        "FEEDBACK: call session_feedback after each query session to update usefulness scores. "
        "CONSOLIDATION: call memory_dream periodically to link concepts and resolve contradictions. "
        "NOTES: use memory_note for explicit user 'remember this' requests — exempt from "
        "auto-archival and win contradictions over inferred memories. "
        "SUMMARIES: call summary_jobs to get concepts needing synthesis, write each summary, "
        "send it back with summary_put — no separate LLM backend required. "
        "IMAGES: call image_jobs to get images needing a description, write a combined "
        "description, send it back with image_caption_put — no vision backend needed. "
        "If MINTMORY_VISION_PROVIDER=llm is configured, call vision_run to auto-caption instead."
    ),
```

- [ ] **Step 6: Verify server.py compiles and tools still register**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync python -c "from mintmory.mcp.server import mcp; print('tools:', len(mcp._tool_manager._tools)); print('ok')"
```

Expected: `tools: 16` (same count as before), `ok`.

---

## Task 4: Modify `history_server.py` — wire `verbosity` into `history_timeline` and `history_search`, tighten `instructions`

**Files:**
- Modify: `packages/mcp/src/mintmory/mcp/history_server.py:20-50,63-132`

- [ ] **Step 1: Add imports**

At the top of `history_server.py`, add `Literal` to the typing import and add the concise import. Change:

```python
from typing import Any
```

to:

```python
from typing import Any, Literal
```

And add after `from mintmory.core.history.ingest import DEFAULT_HISTORY_DB, _assert_not_working_db`:

```python
from mintmory.mcp.concise import concise_history_row
```

- [ ] **Step 2: Tighten the `instructions` block** (lines 38-50)

Replace the current `instructions=(...)` string in `FastMCP(...)` with:

```python
    instructions=(
        "READ-ONLY history of past coding sessions (Claude Code / Codex / Kiro). "
        "TIMELINE: use history_timeline for 'what changed/was fixed in the last N days/weeks/months' "
        "— returns newest-first session summaries. "
        "BROWSING: pass verbosity=\"concise\" for compact {date, repo, kind, title, snippet} rows "
        "when scanning many sessions; use the default verbosity=\"full\" for source_path back-links "
        "and all 15 fields. "
        "SEARCH: use history_search for topic recall across all indexed sessions. "
        "STATS: use history_stats to see session/segment counts and date range. "
        "No tool here writes, adds, archives, dreams, or otherwise mutates any store."
    ),
```

- [ ] **Step 3: Replace `history_timeline` function**

Replace the entire `history_timeline` function (lines 63-107) with:

```python
@mcp.tool()
def history_timeline(
    since: str = "90d",
    from_date: str | None = None,
    to_date: str | None = None,
    repo: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    group: bool = False,
    verbosity: Literal["full", "concise"] = "full",
) -> list[dict[str, Any]]:
    """Dated changelog of agent sessions in a time window (the 'what changed N ago' query).

    Returns newest-first session summaries from the agent-history index.
    Each full result is a dict with: date, ts_start, agent, collection, repo, branch,
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
        verbosity: "full" (default) returns all 15 fields including source_path and
            branch; "concise" returns a compact {date, repo, kind, title, snippet}
            projection for lightweight browsing/scanning.
    """
    # If both from_date and to_date are None but since has its default value,
    # pass since through as-is.  If the caller explicitly passes from_date or
    # to_date, suppress the default since so the pair works as from/to only.
    effective_since: str | None = since
    if from_date is not None or to_date is not None:
        effective_since = None

    rows = query.timeline(
        _db_path(),
        since=effective_since,
        from_iso=from_date,
        to_iso=to_date,
        repo=repo,
        kind=kind,
        limit=limit,
        group_by_session=group,
    )
    if verbosity == "concise":
        return [concise_history_row(r) for r in rows]
    return rows
```

- [ ] **Step 4: Replace `history_search` function**

Replace the entire `history_search` function (lines 110-132) with:

```python
@mcp.tool()
def history_search(
    query_text: str,
    repo: str | None = None,
    since: str | None = None,
    limit: int = 10,
    verbosity: Literal["full", "concise"] = "full",
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
        verbosity: "full" (default) returns the 15-field row shape (same as
            history_timeline); "concise" returns {date, repo, kind, title, snippet}
            for lightweight scanning.

    Returns:
        List of row dicts in search-rank order (same shape as history_timeline).
    """
    rows = query.search(_db_path(), query_text, repo=repo, since=since, limit=limit)
    if verbosity == "concise":
        return [concise_history_row(r) for r in rows]
    return rows
```

- [ ] **Step 5: Verify history server compiles**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync python -c "from mintmory.mcp.history_server import mcp; print('tools:', len(mcp._tool_manager._tools)); print('ok')"
```

Expected: `tools: 3`, `ok`.

---

## Task 5: Add MCP tool verbosity tests to `test_tools.py`

**Files:**
- Modify: `packages/mcp/tests/test_tools.py`

Add the following block at the end of `packages/mcp/tests/test_tools.py`, after the last existing test:

- [ ] **Step 1: Append the verbosity tests**

```python
# ---------------------------------------------------------------------------
# MM-38: verbosity parameter — memory_search and memory_get
# ---------------------------------------------------------------------------


async def test_memory_search_full_verbosity_default(mcp_client: Client[Any]) -> None:
    """Default (no verbosity) returns full shape — regression guard."""
    await mcp_client.call_tool(
        "memory_add",
        {"content": "OAuth2 PKCE is the recommended flow for SPAs.", "category": "skill"},
    )
    res = await mcp_client.call_tool("memory_search", {"query": "oauth pkce"})
    data = res.data
    assert data["session_id"]
    assert data["total_found"] >= 0
    # Full-only key must be present in every hit
    for mem in data["memories"]:
        assert "usefulness_score" in mem, "full verbosity must include usefulness_score"
        assert "content" in mem, "full verbosity must include content"
        assert "metadata" in mem, "full verbosity must include metadata"


async def test_memory_search_full_verbosity_explicit(mcp_client: Client[Any]) -> None:
    """verbosity='full' explicit returns the same full shape."""
    await mcp_client.call_tool(
        "memory_add",
        {"content": "Kubernetes uses etcd for state.", "category": "fact"},
    )
    res = await mcp_client.call_tool(
        "memory_search", {"query": "kubernetes", "verbosity": "full"}
    )
    data = res.data
    for mem in data["memories"]:
        assert "usefulness_score" in mem
        assert "content" in mem


async def test_memory_search_concise_verbosity(mcp_client: Client[Any]) -> None:
    """verbosity='concise' returns the lean shape with correct keys."""
    await mcp_client.call_tool(
        "memory_add",
        {"content": "Docker Compose orchestrates multi-container apps.", "category": "skill"},
    )
    res = await mcp_client.call_tool(
        "memory_search", {"query": "docker", "verbosity": "concise"}
    )
    data = res.data
    assert "session_id" in data
    assert "total_found" in data
    assert "search_around_ids" in data
    assert "notes_on_results" in data
    for mem in data["memories"]:
        assert set(mem.keys()) == {"id", "category", "snippet", "is_note"}, (
            f"unexpected keys in concise memory: {set(mem.keys())}"
        )
        # full-only keys must be absent
        assert "usefulness_score" not in mem
        assert "metadata" not in mem
        assert "content" not in mem


async def test_memory_search_concise_smaller_than_full(mcp_client: Client[Any]) -> None:
    """Concise serialized JSON must be materially smaller than full for a realistic record."""
    import json

    long_content = (
        "GraphQL is a query language for APIs and a runtime for fulfilling those queries "
        "with your existing data. " * 20
    )
    await mcp_client.call_tool(
        "memory_add", {"content": long_content, "category": "skill"}
    )
    full_res = await mcp_client.call_tool(
        "memory_search", {"query": "graphql", "verbosity": "full"}
    )
    concise_res = await mcp_client.call_tool(
        "memory_search", {"query": "graphql", "verbosity": "concise"}
    )
    full_size = len(json.dumps(full_res.data))
    concise_size = len(json.dumps(concise_res.data))
    assert concise_size < full_size, (
        f"concise ({concise_size} bytes) must be smaller than full ({full_size} bytes)"
    )


async def test_memory_get_full_verbosity_default(mcp_client: Client[Any]) -> None:
    """Default memory_get returns the full 30-field shape — regression guard."""
    added = await mcp_client.call_tool(
        "memory_add", {"content": "Postgres uses MVCC for concurrency.", "category": "fact"}
    )
    memory_id = added.data["id"]

    got = await mcp_client.call_tool("memory_get", {"memory_id": memory_id})
    data = got.data
    assert data is not None
    # Full-only keys must be present
    assert "usefulness_score" in data
    assert "staleness_score" in data
    assert "metadata" in data
    assert "entity_ids" in data
    assert "reinforcement_count" in data


async def test_memory_get_concise_verbosity(mcp_client: Client[Any]) -> None:
    """verbosity='concise' returns exactly {id, category, content}."""
    added = await mcp_client.call_tool(
        "memory_add", {"content": "Redis supports pub/sub messaging.", "category": "fact"}
    )
    memory_id = added.data["id"]

    got = await mcp_client.call_tool(
        "memory_get", {"memory_id": memory_id, "verbosity": "concise"}
    )
    data = got.data
    assert data is not None
    assert set(data.keys()) == {"id", "category", "content"}
    assert data["id"] == memory_id
    assert data["content"] == "Redis supports pub/sub messaging."
    # Full-only keys must be absent
    assert "usefulness_score" not in data
    assert "metadata" not in data


async def test_memory_get_missing_returns_none_in_concise(mcp_client: Client[Any]) -> None:
    """Missing id must return None even with verbosity='concise'."""
    got = await mcp_client.call_tool(
        "memory_get", {"memory_id": "does-not-exist", "verbosity": "concise"}
    )
    assert got.data is None
```

- [ ] **Step 2: Run the new server tool tests**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/test_tools.py -v -k "verbosity"
```

Expected: all verbosity tests pass.

---

## Task 6: Add verbosity tests to `test_history_mcp.py`

**Files:**
- Modify: `packages/mcp/tests/test_history_mcp.py`

Append the following block at the end of `packages/mcp/tests/test_history_mcp.py`:

- [ ] **Step 1: Append the history verbosity tests**

```python
# ---------------------------------------------------------------------------
# MM-38: verbosity parameter — history_timeline and history_search
# ---------------------------------------------------------------------------


async def test_history_timeline_full_verbosity_default(history_client: Client[Any]) -> None:
    """Default (no verbosity) returns the 15-field shape — regression guard."""
    res = await history_client.call_tool("history_timeline", {"since": "30d"})
    data = res.data
    assert isinstance(data, list)
    assert len(data) >= 1
    row = data[0]
    # Full-only keys must be present
    assert "branch" in row, "full verbosity must include branch"
    assert "ts_start" in row, "full verbosity must include ts_start"
    assert "summary" in row, "full verbosity must include summary"
    assert "segment_count" in row, "full verbosity must include segment_count"
    assert "source_path" in row, "full verbosity must include source_path"


async def test_history_timeline_full_verbosity_explicit(history_client: Client[Any]) -> None:
    """verbosity='full' explicit returns the same 15-field shape."""
    res = await history_client.call_tool(
        "history_timeline", {"since": "30d", "verbosity": "full"}
    )
    data = res.data
    assert len(data) >= 1
    assert "branch" in data[0]
    assert "summary" in data[0]


async def test_history_timeline_concise_verbosity(history_client: Client[Any]) -> None:
    """verbosity='concise' returns compact {date, repo, kind, title, snippet} rows."""
    res = await history_client.call_tool(
        "history_timeline", {"since": "30d", "verbosity": "concise"}
    )
    data = res.data
    assert isinstance(data, list)
    assert len(data) >= 1
    expected_keys = {"date", "repo", "kind", "title", "snippet"}
    for row in data:
        assert set(row.keys()) == expected_keys, (
            f"unexpected keys in concise row: {set(row.keys())}"
        )
        # Full-only keys must be absent
        assert "branch" not in row
        assert "ts_start" not in row
        assert "summary" not in row
        assert "segment_count" not in row


async def test_history_timeline_concise_smaller_than_full(history_client: Client[Any]) -> None:
    """Concise JSON must be materially smaller than full for a realistic record."""
    import json

    full_res = await history_client.call_tool(
        "history_timeline", {"since": "30d", "verbosity": "full"}
    )
    concise_res = await history_client.call_tool(
        "history_timeline", {"since": "30d", "verbosity": "concise"}
    )
    full_size = len(json.dumps(full_res.data))
    concise_size = len(json.dumps(concise_res.data))
    assert concise_size < full_size, (
        f"concise ({concise_size} bytes) must be smaller than full ({full_size} bytes)"
    )


async def test_history_search_full_verbosity_default(history_client: Client[Any]) -> None:
    """Default history_search returns the 15-field shape — regression guard."""
    res = await history_client.call_tool("history_search", {"query_text": "OAuth2"})
    data = res.data
    assert isinstance(data, list)
    for row in data:
        assert "branch" in row
        assert "summary" in row


async def test_history_search_concise_verbosity(history_client: Client[Any]) -> None:
    """verbosity='concise' returns compact rows for history_search."""
    res = await history_client.call_tool(
        "history_search", {"query_text": "OAuth2", "verbosity": "concise"}
    )
    data = res.data
    assert isinstance(data, list)
    expected_keys = {"date", "repo", "kind", "title", "snippet"}
    for row in data:
        assert set(row.keys()) == expected_keys
        assert "branch" not in row
        assert "summary" not in row
```

- [ ] **Step 2: Run the new history tool tests**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/test_history_mcp.py -v -k "verbosity"
```

Expected: all verbosity tests pass.

---

## Task 7: Update docs — add relocated `memory_dream` LLM config and `verbosity` note

**Files:**
- Modify: `docs/agent-history-mcp.md`

The `memory_dream` LLM env-var prose was removed from `server.py`'s docstring. It belongs in `docs/agent-history-mcp.md` (the canonical MCP reference doc) under a new section. Also add a `verbosity="concise"` usage note since that doc is where agents look for MCP options.

- [ ] **Step 1: Append a new section at the end of `docs/agent-history-mcp.md`**

Add this after the last `## Safety notes` section:

```markdown
---

## `verbosity="concise"` — lightweight browsing

All four token-heavy read tools accept an optional `verbosity` parameter:

| Tool | `verbosity="full"` (default) | `verbosity="concise"` |
|---|---|---|
| `memory_search` | Full `SearchResponse` (~25 fields/hit) | `{id, category, snippet, is_note}` per hit; `notes_on_results` → ids only |
| `memory_get` | All 30 fields | `{id, category, content}` |
| `history_timeline` | 15-field row | `{date, repo, kind, title, snippet}` |
| `history_search` | 15-field row | `{date, repo, kind, title, snippet}` |

Use `verbosity="concise"` for browse/scan passes; switch to `verbosity="full"` when
you need the body, metadata, scoring fields, or source_path back-links.

Example:

```python
# Scan recent sessions cheaply
history_timeline(since="30d", verbosity="concise")

# Then fetch full detail for one session
history_timeline(since="30d", session_id_filter="sess-xyz", verbosity="full")
```

Default is always `"full"` — existing clients are unaffected.

---

## LLM tier configuration for `memory_dream`

`memory_dream` runs structural steps (anomaly detection, concept linking) with any
configuration, but the summariser and contradiction-resolver are backed by the
configured LLM tier:

| Env var | Purpose | Example |
|---|---|---|
| `MINTMORY_LLM_PROVIDER` | `none` (default, skips LLM steps), `openai` (OpenAI-compatible) | `openai` |
| `MINTMORY_LLM_BASE_URL` | Base URL of the provider / gateway | `http://localhost:8789/v1` |
| `MINTMORY_LLM_API_KEY` | API key for the provider | `pk-hermes-...` |
| `MINTMORY_LLM_MODEL` | Model name to use | `MiniMax-M2.7` |
| `MINTMORY_LINK_*` | Concept-linking policy | see source |
| `MINTMORY_SUMMARY_*` | Summary generation policy | see source |

With `MINTMORY_LLM_PROVIDER=none` (the default), the summary-generation and
contradiction-resolution steps are skipped (`new_summaries=0`,
`contradictions_resolved=0`) and only structural steps run. No LLM backend is
required for the structural steps.

A Portkey gateway (self-hosted, `localhost:8789`) with a `pk-<name>-<org>` virtual
key is the recommended way to proxy cloud models (MiniMax-M2.5 / M2.7) to MintMory.
```

- [ ] **Step 2: Verify the file renders (no syntax errors)**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
python3 -c "
import pathlib
content = pathlib.Path('docs/agent-history-mcp.md').read_text()
assert 'verbosity' in content
assert 'MINTMORY_LLM_PROVIDER' in content
print('doc ok, length:', len(content))
"
```

Expected: prints `doc ok, length: <some number>`.

---

## Task 8: Run all CI gates and verify

- [ ] **Step 1: ruff check**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 2: ruff format**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync ruff format packages
```

Expected: `N files left unchanged.` or reformats cleanly.

- [ ] **Step 3: mypy --strict**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync mypy packages
```

Expected: `Success: no issues found in N source files`

If mypy fails on `mcp._tool_manager._tools` in the verification step (it's a private attr), remove that step — it's only a sanity smoke-test in the plan. The real mypy gate is this step.

- [ ] **Step 4: pytest full suite**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest -q
```

Expected: ≥ 80% coverage, all tests pass (0 failures). The new tests add ~50 cases.

- [ ] **Step 5: openspec validate**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
openspec validate optimize-mcp-token-usage --strict
```

Expected: `PASS` or equivalent success output. If `openspec` is not on PATH, run `uv run --no-sync openspec validate optimize-mcp-token-usage --strict`.

---

## Self-Review Checklist

### Spec coverage

| Spec requirement | Task covering it |
|---|---|
| `concise.py` with `_snip`, `concise_memory`, `concise_memory_get`, `concise_search_response`, `concise_history_row` | Task 1 |
| Full type annotations, mypy-clean | Task 1 + Task 8 step 3 |
| `test_concise.py` — exact field sets, snippet truncation, notes→ids, envelope preserved | Task 2 |
| `memory_search` gets `verbosity` param, default=full | Task 3 step 3 |
| `memory_get` gets `verbosity` param, None unchanged in both modes | Task 3 step 2 |
| `memory_dream` docstring trimmed, pointer to docs added | Task 3 step 4 |
| `instructions` block tightened ~40%, concise note added | Task 3 step 5 |
| `history_timeline` gets `verbosity` param | Task 4 step 3 |
| `history_search` gets `verbosity` param | Task 4 step 4 |
| `history_server.py` `instructions` tightened + concise note | Task 4 step 2 |
| Docs updated with relocated LLM env-var prose + verbosity table | Task 7 |
| `verbosity="full"` regression guard tests for all 4 tools | Tasks 5, 6 |
| `verbosity="concise"` shape tests for all 4 tools | Tasks 5, 6 |
| Concise JSON materially smaller than full (size assertion) | Tasks 5, 6 |
| Existing tests all green | Task 8 step 4 |
| `_shape_row` in query.py NOT modified | (never touched) |

### Placeholder scan
No TBDs, TODOs, or "similar to" references. All code blocks are complete.

### Type consistency
- `concise_memory(rec: dict[str, Any]) -> dict[str, Any]` — used in `concise_search_response`
- `concise_memory_get(rec: dict[str, Any]) -> dict[str, Any]` — used in `memory_get`
- `concise_search_response(resp: dict[str, Any]) -> dict[str, Any]` — used in `memory_search`
- `concise_history_row(row: dict[str, Any]) -> dict[str, Any]` — used in `history_timeline` and `history_search`
- Return types on all tool handlers stay `dict[str, Any]` / `list[dict[str, Any]]`

All consistent throughout Tasks 1–6.
