"""
Pure unit tests for mintmory.mcp.concise (MM-38).

No I/O, no DB, no FastMCP client — just dict-in / dict-out.
"""

from __future__ import annotations

import json

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

_FULL_RECORD: dict[str, object] = {
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

_FULL_RESPONSE: dict[str, object] = {
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

_FULL_ROW: dict[str, object] = {
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
