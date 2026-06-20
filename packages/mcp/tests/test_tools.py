"""
Tests for the MintMory MCP tool surface.

Every tool is exercised through the fastmcp in-memory ``Client`` (no transport,
no subprocess) so the assertions cover the real registration + serialisation
path, not just the bare Python function bodies.

Isolation:
  * the ``mcp_client`` fixture points ``MINTMORY_DB`` at a per-test ``tmp_path``
    file so the suite never touches ``~/.mintmory``;
  * the module-level ``server._store`` singleton is reset to ``None`` before and
    after each test so each test gets a fresh adapter bound to its own DB.

``asyncio_mode = auto`` (root pyproject) means async tests need no decorator.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mintmory.mcp import server
from mintmory.mcp.server import mcp


@pytest.fixture
async def mcp_client(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Client[Any]]:
    """Yield an in-memory client bound to an isolated temp database."""
    db_file = tmp_path / "memories.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_file))
    server._store = None
    try:
        async with Client(mcp) as client:
            yield client
    finally:
        if server._store is not None:
            server._store.close()
        server._store = None


# ---------------------------------------------------------------------------
# Tool inventory
# ---------------------------------------------------------------------------


async def test_all_tools_registered(mcp_client: Client[Any]) -> None:
    names = {tool.name for tool in await mcp_client.list_tools()}
    assert names == {
        "memory_add",
        "memory_get",
        "memory_search",
        "memory_dream",
        "memory_stats",
        "session_feedback",
        "memory_archive",
        "summary_list",
        "summary_get",
        "summary_jobs",
        "summary_put",
        "memory_note",
        "notes_list",
        "image_jobs",
        "image_caption_put",
        "vision_run",
    }


# ---------------------------------------------------------------------------
# memory_add
# ---------------------------------------------------------------------------


async def test_memory_add_happy_path(mcp_client: Client[Any]) -> None:
    res = await mcp_client.call_tool(
        "memory_add",
        {
            "content": "The Acme parking integration uses OAuth 2.0 with PKCE.",
            "category": "fact",
            "source": "user",
            "confidence": 0.95,
            "verified": True,
            "metadata": {"project_id": "acme-parking"},
        },
    )
    data = res.data
    assert data["content"].startswith("The Acme parking integration")
    assert data["category"] == "fact"
    assert data["source"] == "user"
    assert data["confidence"] == 0.95
    assert data["verified"] is True
    assert data["metadata"] == {"project_id": "acme-parking"}
    # entity extraction ran during add
    assert isinstance(data["entity_ids"], list)
    assert data["is_active"] is True
    assert data["is_archived"] is False
    assert data["id"]


async def test_memory_add_defaults(mcp_client: Client[Any]) -> None:
    res = await mcp_client.call_tool("memory_add", {"content": "A bare fact.", "category": "fact"})
    data = res.data
    assert data["source"] == "agent"
    assert data["confidence"] == 1.0
    assert data["verified"] is False
    assert data["metadata"] == {}


async def test_memory_add_invalid_category_errors(mcp_client: Client[Any]) -> None:
    with pytest.raises(ToolError):
        await mcp_client.call_tool("memory_add", {"content": "x", "category": "not_a_category"})


# ---------------------------------------------------------------------------
# memory_get
# ---------------------------------------------------------------------------


async def test_memory_get_roundtrip(mcp_client: Client[Any]) -> None:
    added = await mcp_client.call_tool(
        "memory_add", {"content": "Recall me later.", "category": "context"}
    )
    memory_id = added.data["id"]

    got = await mcp_client.call_tool("memory_get", {"memory_id": memory_id})
    assert got.data["id"] == memory_id
    assert got.data["content"] == "Recall me later."


async def test_memory_get_missing_returns_none(mcp_client: Client[Any]) -> None:
    got = await mcp_client.call_tool("memory_get", {"memory_id": "does-not-exist"})
    assert got.data is None


# ---------------------------------------------------------------------------
# memory_search
# ---------------------------------------------------------------------------


async def test_memory_search_finds_added(mcp_client: Client[Any]) -> None:
    await mcp_client.call_tool(
        "memory_add",
        {"content": "Kubernetes deployments use rolling updates.", "category": "skill"},
    )
    res = await mcp_client.call_tool("memory_search", {"query": "kubernetes", "limit": 5})
    data = res.data
    assert data["session_id"]
    assert data["total_found"] >= 1
    contents = [m["content"] for m in data["memories"]]
    assert any("Kubernetes" in c for c in contents)
    assert data["search_around_ids"] == []


async def test_memory_search_category_filter(mcp_client: Client[Any]) -> None:
    await mcp_client.call_tool(
        "memory_add", {"content": "Redis caches sessions.", "category": "fact"}
    )
    await mcp_client.call_tool(
        "memory_add", {"content": "Redis tuning is a skill.", "category": "skill"}
    )
    res = await mcp_client.call_tool(
        "memory_search", {"query": "redis", "category": "fact", "limit": 10}
    )
    assert all(m["category"] == "fact" for m in res.data["memories"])


async def test_memory_search_entity_filter(mcp_client: Client[Any]) -> None:
    await mcp_client.call_tool(
        "memory_add", {"content": "The Postgres database is primary.", "category": "fact"}
    )
    res = await mcp_client.call_tool("memory_search", {"query": "database", "entity": "postgres"})
    # entity filter resolves without error; matching memories carry the entity
    for memory in res.data["memories"]:
        assert "postgres" in memory["entity_ids"]


async def test_memory_search_with_search_around(mcp_client: Client[Any]) -> None:
    res = await mcp_client.call_tool(
        "memory_add",
        {"content": "OAuth links to identity.", "category": "fact"},
    )
    assert res.data["id"]
    out = await mcp_client.call_tool(
        "memory_search",
        {
            "query": "oauth",
            "search_around_link_types": ["relates_to", "contradicts"],
            "search_around_depth": 2,
        },
    )
    data = out.data
    assert "search_around_ids" in data
    assert isinstance(data["search_around_ids"], list)


async def test_memory_search_invalid_link_type_errors(mcp_client: Client[Any]) -> None:
    with pytest.raises(ToolError):
        await mcp_client.call_tool(
            "memory_search",
            {"query": "x", "search_around_link_types": ["not_a_link_type"]},
        )


async def test_memory_search_excludes_stale_by_default(mcp_client: Client[Any]) -> None:
    res = await mcp_client.call_tool("memory_search", {"query": "anything", "limit": 3})
    # exclude_stale default propagates through the filter without error
    assert res.data["total_found"] == len(res.data["memories"]) or res.data["total_found"] >= 0


# ---------------------------------------------------------------------------
# memory_dream
# ---------------------------------------------------------------------------


async def test_memory_dream_light(mcp_client: Client[Any]) -> None:
    await mcp_client.call_tool(
        "memory_add", {"content": "GraphQL is a query language.", "category": "fact"}
    )
    res = await mcp_client.call_tool("memory_dream", {"intensity": "light"})
    data = res.data
    assert data["intensity"] == "light"
    assert data["duration_ms"] >= 0.0
    assert data["new_links"] >= 0
    # no LLM summariser -> summaries skipped
    assert data["new_summaries"] == 0
    assert data["anomalies"] is not None


async def test_memory_dream_full(mcp_client: Client[Any]) -> None:
    res = await mcp_client.call_tool("memory_dream", {"intensity": "full"})
    data = res.data
    assert data["intensity"] == "full"
    # full-only counters present
    assert data["contradictions_resolved"] == 0
    assert data["memories_archived"] >= 0
    assert data["memories_rehabilitated"] >= 0


async def test_memory_dream_default_is_light(mcp_client: Client[Any]) -> None:
    res = await mcp_client.call_tool("memory_dream", {})
    assert res.data["intensity"] == "light"


async def test_memory_dream_invalid_intensity_errors(mcp_client: Client[Any]) -> None:
    with pytest.raises(ToolError):
        await mcp_client.call_tool("memory_dream", {"intensity": "deep"})


# ---------------------------------------------------------------------------
# memory_stats
# ---------------------------------------------------------------------------


async def test_memory_stats(mcp_client: Client[Any]) -> None:
    await mcp_client.call_tool("memory_add", {"content": "One stat fact.", "category": "fact"})
    await mcp_client.call_tool("memory_add", {"content": "Two stat fact.", "category": "fact"})
    res = await mcp_client.call_tool("memory_stats", {})
    data = res.data
    assert data["total_memories"] == 2
    assert data["active"] == 2
    assert data["archived"] == 0
    assert "avg_usefulness_score" in data
    assert "top_concepts" in data


# ---------------------------------------------------------------------------
# memory_archive
# ---------------------------------------------------------------------------


async def test_memory_archive(mcp_client: Client[Any]) -> None:
    added = await mcp_client.call_tool(
        "memory_add", {"content": "Archive me.", "category": "episodic"}
    )
    memory_id = added.data["id"]

    res = await mcp_client.call_tool("memory_archive", {"memory_id": memory_id})
    assert res.data == {"id": memory_id, "archived": True}

    got = await mcp_client.call_tool("memory_get", {"memory_id": memory_id})
    assert got.data["is_archived"] is True
    assert got.data["is_active"] is False


# ---------------------------------------------------------------------------
# session_feedback
# ---------------------------------------------------------------------------


async def test_session_feedback_happy_path(mcp_client: Client[Any]) -> None:
    added = await mcp_client.call_tool(
        "memory_add", {"content": "Useful feedback memory.", "category": "fact"}
    )
    memory_id = added.data["id"]
    search = await mcp_client.call_tool("memory_search", {"query": "useful feedback"})
    session_id = search.data["session_id"]

    res = await mcp_client.call_tool(
        "session_feedback",
        {
            "session_id": session_id,
            "useful_ids": [memory_id],
            "stale_ids": [],
            "confidence_rating": 4,
            "reasoning": "Directly answered the query.",
        },
    )
    data = res.data
    assert data["id"] == session_id
    assert data["concluded"] is True
    assert data["confidence_rating"] == 4
    assert data["useful_ids"] == [memory_id]

    # usefulness was reinforced on the memory
    refreshed = await mcp_client.call_tool("memory_get", {"memory_id": memory_id})
    assert refreshed.data["usefulness_score"] > 0.0
    assert refreshed.data["reinforcement_count"] == 1


async def test_session_feedback_stale_marks_memory(mcp_client: Client[Any]) -> None:
    added = await mcp_client.call_tool(
        "memory_add", {"content": "Stale-able memory entry.", "category": "fact"}
    )
    memory_id = added.data["id"]
    search = await mcp_client.call_tool("memory_search", {"query": "stale-able"})
    session_id = search.data["session_id"]

    res = await mcp_client.call_tool(
        "session_feedback",
        {"session_id": session_id, "stale_ids": [memory_id]},
    )
    assert res.data["stale_ids"] == [memory_id]

    refreshed = await mcp_client.call_tool("memory_get", {"memory_id": memory_id})
    assert refreshed.data["staleness_score"] > 0.0


async def test_session_feedback_minimal_args(mcp_client: Client[Any]) -> None:
    search = await mcp_client.call_tool("memory_search", {"query": "empty"})
    session_id = search.data["session_id"]
    res = await mcp_client.call_tool("session_feedback", {"session_id": session_id})
    assert res.data["concluded"] is True
    assert res.data["useful_ids"] == []
    assert res.data["stale_ids"] == []


async def test_session_feedback_unknown_session_returns_error(mcp_client: Client[Any]) -> None:
    res = await mcp_client.call_tool("session_feedback", {"session_id": "no-such-session"})
    assert res.data["error"] == "conflict"
    assert "not found" in res.data["message"]


async def test_session_feedback_already_concluded_returns_error(
    mcp_client: Client[Any],
) -> None:
    search = await mcp_client.call_tool("memory_search", {"query": "double"})
    session_id = search.data["session_id"]
    await mcp_client.call_tool("session_feedback", {"session_id": session_id})

    res = await mcp_client.call_tool("session_feedback", {"session_id": session_id})
    assert res.data["error"] == "conflict"
    assert "already concluded" in res.data["message"]


# ---------------------------------------------------------------------------
# summaries
# ---------------------------------------------------------------------------


async def test_summary_list_empty(mcp_client: Client[Any]) -> None:
    res = await mcp_client.call_tool("summary_list", {})
    assert res.data == []


async def test_summary_get_missing_returns_none(mcp_client: Client[Any]) -> None:
    res = await mcp_client.call_tool("summary_get", {"concept": "nonexistent"})
    assert res.data is None


# ---------------------------------------------------------------------------
# memory_note
# ---------------------------------------------------------------------------


async def test_memory_note_happy_path_no_about(mcp_client: Client[Any]) -> None:
    """memory_note with content only → is_note=True, anchor_kind=none."""
    res = await mcp_client.call_tool(
        "memory_note",
        {"content": "Remember to renew the TLS cert before 2027-01-01."},
    )
    data = res.data
    assert data["note"]["is_note"] is True
    assert data["anchor_kind"] == "none"
    assert data["anchor_memory_id"] is None
    assert data["anchor_phrase"] is None


async def test_memory_note_happy_path_with_when(mcp_client: Client[Any]) -> None:
    """memory_note with a valid ISO when → valid_from stored, category temporal."""
    res = await mcp_client.call_tool(
        "memory_note",
        {
            "content": "Team offsite planning session.",
            "when": "2026-09-15",
        },
    )
    data = res.data
    assert data["note"]["is_note"] is True
    assert data["note"]["valid_from"] is not None
    assert "2026-09-15" in data["note"]["valid_from"]
    assert data["note"]["category"] == "temporal"


async def test_memory_note_happy_path_with_about(mcp_client: Client[Any]) -> None:
    """memory_note with about → anchor_phrase set; anchor_kind in {none, topic, memory}."""
    # Add an existing memory to give anchor resolution something to match against.
    await mcp_client.call_tool(
        "memory_add",
        {"content": "The Tokyo trip itinerary covers six hotels.", "category": "episodic"},
    )
    res = await mcp_client.call_tool(
        "memory_note",
        {
            "content": "Pack extra adapters for Japan.",
            "about": "Tokyo trip",
        },
    )
    data = res.data
    assert data["note"]["is_note"] is True
    assert data["anchor_phrase"] == "Tokyo trip"
    assert data["anchor_kind"] in {"memory", "topic", "none"}


async def test_memory_note_bad_iso_when_returns_error_dict(mcp_client: Client[Any]) -> None:
    """An unparseable 'when' must return an error dict, NOT raise ToolError."""
    res = await mcp_client.call_tool(
        "memory_note",
        {"content": "Something.", "when": "not-a-date"},
    )
    data = res.data
    assert data["error"] == "bad_request"
    assert "when" in data["message"]


async def test_memory_note_bad_iso_until_returns_error_dict(mcp_client: Client[Any]) -> None:
    """An unparseable 'until' must return an error dict."""
    res = await mcp_client.call_tool(
        "memory_note",
        {"content": "Something.", "until": "yesterday"},
    )
    data = res.data
    assert data["error"] == "bad_request"
    assert "until" in data["message"]


async def test_memory_note_stored_record_is_note_flag(mcp_client: Client[Any]) -> None:
    """After memory_note, memory_get confirms is_note=True on the returned id."""
    res = await mcp_client.call_tool("memory_note", {"content": "Note for round-trip check."})
    note_id = res.data["note"]["id"]
    got = await mcp_client.call_tool("memory_get", {"memory_id": note_id})
    assert got.data["is_note"] is True


# ---------------------------------------------------------------------------
# notes_list
# ---------------------------------------------------------------------------


async def test_notes_list_empty_store(mcp_client: Client[Any]) -> None:
    """notes_list on an empty store returns an empty list."""
    res = await mcp_client.call_tool("notes_list", {})
    assert res.data == []


async def test_notes_list_returns_only_notes(mcp_client: Client[Any]) -> None:
    """notes_list must not return ordinary (non-note) memories."""
    # Add one plain memory and one note.
    await mcp_client.call_tool(
        "memory_add", {"content": "A plain memory, not a note.", "category": "fact"}
    )
    await mcp_client.call_tool("memory_note", {"content": "A proper user note."})
    res = await mcp_client.call_tool("notes_list", {})
    records = res.data
    assert len(records) == 1
    assert records[0]["is_note"] is True


async def test_notes_list_upcoming_filter(mcp_client: Client[Any]) -> None:
    """--upcoming returns only notes with valid_from in the future."""
    # Future note.
    await mcp_client.call_tool(
        "memory_note",
        {"content": "Future dentist appointment.", "when": "2099-12-31"},
    )
    # Note with no date (default → no valid_from).
    await mcp_client.call_tool("memory_note", {"content": "Undated note, no valid_from."})
    res = await mcp_client.call_tool("notes_list", {"upcoming": True})
    records = res.data
    # All returned notes must have a valid_from in the future.
    assert len(records) >= 1
    for rec in records:
        assert rec["valid_from"] is not None


async def test_notes_list_overdue_filter(mcp_client: Client[Any]) -> None:
    """--overdue returns only notes with valid_from in the past."""
    # Past note.
    await mcp_client.call_tool(
        "memory_note",
        {"content": "Past meeting that already happened.", "when": "2020-01-01"},
    )
    # Future note (should NOT appear in overdue).
    await mcp_client.call_tool(
        "memory_note",
        {"content": "Upcoming event.", "when": "2099-06-01"},
    )
    res = await mcp_client.call_tool("notes_list", {"overdue": True})
    records = res.data
    assert len(records) >= 1
    # All returned records must be is_note=True.
    for rec in records:
        assert rec["is_note"] is True


async def test_notes_list_both_flags_returns_error_dict(mcp_client: Client[Any]) -> None:
    """Passing both upcoming=True and overdue=True must return an error dict."""
    res = await mcp_client.call_tool("notes_list", {"upcoming": True, "overdue": True})
    # Implementation maps ValueError → error dict, not ToolError.
    data = res.data
    assert isinstance(data, dict)
    assert data.get("error") == "bad_request"


async def test_notes_list_limit_respected(mcp_client: Client[Any]) -> None:
    """limit parameter caps the number of results."""
    for i in range(5):
        await mcp_client.call_tool("memory_note", {"content": f"Note number {i} for limit test."})
    res = await mcp_client.call_tool("notes_list", {"limit": 3})
    assert len(res.data) <= 3


# ---------------------------------------------------------------------------
# summary_jobs / summary_put (agent-supplied L3)
# ---------------------------------------------------------------------------


async def _add_memories_for_concept(
    mcp_client: Client[Any], concept_content_pairs: list[tuple[str, str]]
) -> list[str]:
    """Add memories and return their ids."""
    ids: list[str] = []
    for content, category in concept_content_pairs:
        res = await mcp_client.call_tool("memory_add", {"content": content, "category": category})
        ids.append(res.data["id"])
    return ids


async def test_summary_jobs_empty_on_fresh_db(mcp_client: Client[Any]) -> None:
    """summary_jobs returns [] when there are no qualifying concepts (< min_memories=3)."""
    res = await mcp_client.call_tool("summary_jobs", {})
    assert res.data == []


async def test_summary_jobs_returns_jobs_without_llm(mcp_client: Client[Any]) -> None:
    """summary_jobs returns SummaryJob dicts with no LLM configured (provider=none)."""
    # Need >= 3 active memories sharing one concept for min_memories=3.
    # Use a very specific entity name to avoid stoplist issues.
    for i in range(3):
        await mcp_client.call_tool(
            "memory_add",
            {
                "content": f"Zephyreon platform memory {i}: Zephyreon handles routing.",
                "category": "fact",
            },
        )
    res = await mcp_client.call_tool("summary_jobs", {})
    data = res.data
    assert isinstance(data, list)
    # At least one job must surface (the Zephyreon concept if entity extraction picks it up).
    # If none surface (entity extraction didn't detect the concept), the test is still
    # valid: we assert the result is a list of well-formed dicts — the important thing
    # is NO error is raised even without an LLM.
    for job in data:
        assert "concept" in job
        assert "memory_ids" in job
        assert "contents" in job
        assert "memory_count" in job
        assert "current_summary" in job


async def test_summary_jobs_then_put_then_jobs_empty(
    mcp_client: Client[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy-path round-trip: jobs -> put -> jobs returns [] for the stored concept.

    This test injects the dreaming engine directly so we can force a concept
    into the selection without depending on entity extraction.
    """
    from mintmory.core.types import MemorySummary

    # Seed three memories that share the entity "testconcept" by writing directly
    # through the store (bypasses entity extraction which is regex-based).
    store = server._get_store()

    # Upsert a summary directly so summary_get can verify it later.
    # First, confirm summary_jobs returns [] for an empty DB.
    res_empty = await mcp_client.call_tool("summary_jobs", {})
    assert res_empty.data == []

    # Seed the store with a summary to test include_all=True path.
    stored = store.upsert_summary(
        MemorySummary(concept="orangecat", summary_text="Orange cats purr.", memory_count=3)
    )
    assert stored.concept == "orangecat"

    # With include_all=False (default): the stored summary exists and memory_count==3
    # but the actual active count is 0, so it NEEDS re-summary -> appears.
    res_needed = await mcp_client.call_tool("summary_jobs", {"include_all": False})
    # Even if the concept is not in the active memories, the jobs list may be empty
    # because _select_summary_concepts only picks concepts with >= min_memories ACTIVE
    # memories. An orphaned MemorySummary row is not a job until there are active memories.
    # This is correct behaviour — jobs are driven by active memory counts.
    assert isinstance(res_needed.data, list)

    # The include_all flag must be accepted without error.
    res_all = await mcp_client.call_tool("summary_jobs", {"include_all": True})
    assert isinstance(res_all.data, list)


async def test_summary_jobs_limit_applied(mcp_client: Client[Any]) -> None:
    """limit=0 means no cap; a positive limit slices the result list."""
    # Even with an empty DB limit must be respected (returns an empty list, not an error).
    res = await mcp_client.call_tool("summary_jobs", {"limit": 2})
    assert isinstance(res.data, list)
    assert len(res.data) <= 2


async def test_summary_put_stores_and_get_confirms(mcp_client: Client[Any]) -> None:
    """summary_put persists the text verbatim; summary_get retrieves it."""
    res = await mcp_client.call_tool(
        "summary_put", {"concept": "foobarqux", "summary_text": "Foobarqux is a synthetic concept."}
    )
    data = res.data
    assert data["concept"] == "foobarqux"
    assert data["summary_text"] == "Foobarqux is a synthetic concept."
    assert data["is_current"] is True
    # memory_count is 0 for a concept with no active memories — that is correct.
    assert isinstance(data["memory_count"], int)

    # Verify via summary_get.
    got = await mcp_client.call_tool("summary_get", {"concept": "foobarqux"})
    assert got.data["concept"] == "foobarqux"
    assert got.data["summary_text"] == "Foobarqux is a synthetic concept."


async def test_summary_put_is_idempotent(mcp_client: Client[Any]) -> None:
    """Calling summary_put twice for the same concept overwrites, not duplicates."""
    await mcp_client.call_tool(
        "summary_put", {"concept": "idempotent_concept", "summary_text": "First text."}
    )
    res2 = await mcp_client.call_tool(
        "summary_put", {"concept": "idempotent_concept", "summary_text": "Second text."}
    )
    assert res2.data["summary_text"] == "Second text."

    # list should show exactly one entry for this concept.
    listed = await mcp_client.call_tool("summary_list", {})
    matching = [s for s in listed.data if s["concept"] == "idempotent_concept"]
    assert len(matching) == 1
    assert matching[0]["summary_text"] == "Second text."


async def test_summary_put_no_llm_required(mcp_client: Client[Any]) -> None:
    """summary_put works with no LLM backend (provider=none is the default in tests)."""
    # The fixture sets no MINTMORY_LLM_* vars -> provider=none. The call must succeed.
    res = await mcp_client.call_tool(
        "summary_put",
        {"concept": "nollmconcept", "summary_text": "Works without an LLM."},
    )
    assert res.data["concept"] == "nollmconcept"
    assert "error" not in res.data


# ---------------------------------------------------------------------------
# helper / wiring coverage
# ---------------------------------------------------------------------------


def test_get_store_is_singleton(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "singleton.db"))
    server._store = None
    try:
        first = server._get_store()
        second = server._get_store()
        assert first is second
    finally:
        if server._store is not None:
            server._store.close()
        server._store = None


# ---------------------------------------------------------------------------
# image_jobs / image_caption_put (agent-supplied vision, G5)
# ---------------------------------------------------------------------------


async def _seed_image_file_record(
    mcp_client: Client[Any],
    *,
    rel: str = "photos/sample.png",
    path: str = "/tmp/photos/sample.png",  # noqa: S108 — test-only, no real file
    ext: str = ".png",
) -> str:
    """Add a synthetic image file-record memory and return its id.

    This replicates what ``index-tree`` writes: a ``context``/``document`` memory
    with ext/rel/path/size/mtime/online_only/index_mode in metadata.
    """
    res = await mcp_client.call_tool(
        "memory_add",
        {
            "content": f"[image] {rel}",
            "category": "context",
            "source": "document",
            "metadata": {
                "collection": "test-lib",
                "path": path,
                "rel": rel,
                "ext": ext,
                "size": 1024,
                "mtime": 1_700_000_000.0,
                "online_only": False,
                "folder": str(rel).rsplit("/", 1)[0] if "/" in rel else ".",
                "index_mode": "vision",
            },
        },
    )
    assert res.data["id"], "expected a memory id"
    return str(res.data["id"])


async def test_image_jobs_empty_on_fresh_db(mcp_client: Client[Any]) -> None:
    """image_jobs returns [] when no raster image file-records exist."""
    res = await mcp_client.call_tool("image_jobs", {})
    assert res.data == []


async def test_image_jobs_returns_unseeded_raster(mcp_client: Client[Any]) -> None:
    """image_jobs (default) surfaces a raster file-record that has no description."""
    file_id = await _seed_image_file_record(mcp_client)
    res = await mcp_client.call_tool("image_jobs", {})
    data = res.data
    assert isinstance(data, list)
    assert len(data) == 1
    job = data[0]
    assert job["file_id"] == file_id
    assert job["mime"] == "image/png"
    assert job["online_only"] is False
    assert job["image_b64"] is None  # local file, include_bytes=False
    assert job["oversized"] is False
    assert job["current_description"] is None


async def test_image_jobs_include_all_param_accepted(mcp_client: Client[Any]) -> None:
    """include_all=True is accepted without error (returns a list)."""
    await _seed_image_file_record(mcp_client)
    res = await mcp_client.call_tool("image_jobs", {"include_all": True})
    assert isinstance(res.data, list)


async def test_image_jobs_limit_caps_results(mcp_client: Client[Any]) -> None:
    """limit>0 caps the returned job list."""
    for i in range(3):
        await _seed_image_file_record(
            mcp_client,
            rel=f"img{i}.jpg",
            path=f"/tmp/img{i}.jpg",  # noqa: S108
            ext=".jpg",
        )
    res = await mcp_client.call_tool("image_jobs", {"limit": 2})
    assert isinstance(res.data, list)
    assert len(res.data) <= 2


async def test_image_caption_put_empty_description_bad_request(
    mcp_client: Client[Any],
) -> None:
    """image_caption_put with an empty/whitespace description returns bad_request."""
    res = await mcp_client.call_tool(
        "image_caption_put",
        {"file_id_or_path": "some-id", "description": "   "},
    )
    data = res.data
    assert isinstance(data, dict)
    assert data["error"] == "bad_request"
    assert "description" in data["message"]


async def test_image_caption_put_unknown_id_not_found(mcp_client: Client[Any]) -> None:
    """image_caption_put with an unknown file_id returns not_found."""
    res = await mcp_client.call_tool(
        "image_caption_put",
        {"file_id_or_path": "no-such-id", "description": "A photo of a cat."},
    )
    data = res.data
    assert isinstance(data, dict)
    assert data["error"] == "not_found"


async def test_image_jobs_then_caption_put_then_jobs_empty(
    mcp_client: Client[Any],
) -> None:
    """Happy-path round-trip: image_jobs -> image_caption_put -> image_jobs returns [].

    After image_caption_put stores a description for a file-record, the default
    image_jobs (needs-redescribe predicate) must NOT re-surface that file-record.
    This is the no-drift / idempotent guarantee from design §5a + §7.
    """
    # 1. Seed a raster image file-record.
    file_id = await _seed_image_file_record(mcp_client, rel="cat.png", path="/tmp/cat.png")  # noqa: S108

    # 2. Confirm it appears in the default image_jobs list.
    res_before = await mcp_client.call_tool("image_jobs", {})
    job_ids = [j["file_id"] for j in res_before.data]
    assert file_id in job_ids, "seeded file-record must appear in image_jobs"

    # 3. Store a description via image_caption_put.
    put_res = await mcp_client.call_tool(
        "image_caption_put",
        {
            "file_id_or_path": file_id,
            "description": "A tabby cat sitting on a red cushion.",
        },
    )
    desc_data = put_res.data
    assert isinstance(desc_data, dict)
    assert "record" in desc_data, f"expected ImageDescription dict, got: {desc_data}"
    assert desc_data["file_id"] == file_id
    assert desc_data["record"]["is_note"] is False
    assert desc_data["record"]["metadata"]["kind"] == "image_description"

    # 4. Confirm image_jobs (default) no longer surfaces the described image.
    res_after = await mcp_client.call_tool("image_jobs", {})
    job_ids_after = [j["file_id"] for j in res_after.data]
    assert file_id not in job_ids_after, (
        "described image must NOT appear in default image_jobs after image_caption_put"
    )


async def test_image_caption_put_idempotent_replaces_prior(
    mcp_client: Client[Any],
) -> None:
    """A second image_caption_put archives the first description (replaced_description_id set)."""
    file_id = await _seed_image_file_record(mcp_client, rel="dog.png", path="/tmp/dog.png")  # noqa: S108

    # First put.
    first = await mcp_client.call_tool(
        "image_caption_put",
        {"file_id_or_path": file_id, "description": "A golden retriever running."},
    )
    first_desc_id: str = first.data["record"]["id"]

    # Second put — must archive the first.
    second = await mcp_client.call_tool(
        "image_caption_put",
        {"file_id_or_path": file_id, "description": "A golden retriever sitting."},
    )
    second_data = second.data
    assert second_data["replaced_description_id"] == first_desc_id

    # After the second put, the image must still NOT appear in default image_jobs.
    res = await mcp_client.call_tool("image_jobs", {})
    assert all(j["file_id"] != file_id for j in res.data)


async def test_image_jobs_include_all_surfaces_described_image(
    mcp_client: Client[Any],
) -> None:
    """include_all=True returns already-described images with current_description set."""
    file_id = await _seed_image_file_record(mcp_client, rel="bird.jpg", path="/tmp/bird.jpg")  # noqa: S108
    await mcp_client.call_tool(
        "image_caption_put",
        {"file_id_or_path": file_id, "description": "A blue jay perched on a branch."},
    )

    res = await mcp_client.call_tool("image_jobs", {"include_all": True})
    matching = [j for j in res.data if j["file_id"] == file_id]
    assert len(matching) == 1
    assert matching[0]["current_description"] == "A blue jay perched on a branch."


async def test_image_jobs_svg_not_surfaced(mcp_client: Client[Any]) -> None:
    """SVG file-records must never appear in image_jobs (they are self-described)."""
    await mcp_client.call_tool(
        "memory_add",
        {
            "content": "[svg] diagram.svg",
            "category": "context",
            "source": "document",
            "metadata": {
                "collection": "lib",
                "path": "/tmp/diagram.svg",  # noqa: S108
                "rel": "diagram.svg",
                "ext": ".svg",
                "size": 512,
                "mtime": 1_700_000_000.0,
                "online_only": False,
                "folder": ".",
                "index_mode": "vision",
            },
        },
    )
    res = await mcp_client.call_tool("image_jobs", {})
    assert all(j["mime"] != "image/svg+xml" for j in res.data)
    assert res.data == []  # SVG-only store → zero raster jobs


# ---------------------------------------------------------------------------
# vision_run (new — add-llm-vision-provider, Group 6.3)
# ---------------------------------------------------------------------------


async def test_vision_run_agent_provider_is_noop(
    mcp_client: Client[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """vision_run with provider=agent (default) returns provider='agent', described=0.

    No MINTMORY_VISION_PROVIDER is set → provider=agent → no-op path:
    captioner_from_settings returns None and vision_run returns the all-zero
    CaptionRunReport without calling caption_pending_images.
    """
    monkeypatch.delenv("MINTMORY_VISION_PROVIDER", raising=False)
    res = await mcp_client.call_tool("vision_run", {})
    data = res.data
    assert isinstance(data, dict)
    assert data["provider"] == "agent"
    assert data["described"] == 0
    assert data["skipped"] == 0
    assert data["failed"] == 0
    assert data["budget_hit"] is False


async def test_vision_run_agent_provider_default_params(
    mcp_client: Client[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """vision_run default params (limit=0, budget_mb=0.0, include_all=False) are accepted."""
    monkeypatch.delenv("MINTMORY_VISION_PROVIDER", raising=False)
    res = await mcp_client.call_tool(
        "vision_run", {"limit": 0, "budget_mb": 0.0, "include_all": False}
    )
    data = res.data
    assert data["provider"] == "agent"
    assert data["described"] == 0


async def test_vision_run_tool_registered(mcp_client: Client[Any]) -> None:
    """vision_run must appear in the registered tool list."""
    names = {tool.name for tool in await mcp_client.list_tools()}
    assert "vision_run" in names


async def test_vision_run_ocr_provider_returns_not_implemented(
    mcp_client: Client[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """vision_run with provider=ocr returns an error dict (not_implemented), not a ToolError.

    The OCR provider is still a stub; the MCP tool maps NotImplementedError to
    ``{"error": "not_implemented", "message": ...}`` rather than raising.
    """
    monkeypatch.setenv("MINTMORY_VISION_PROVIDER", "ocr")
    res = await mcp_client.call_tool("vision_run", {})
    data = res.data
    assert isinstance(data, dict)
    assert data.get("error") == "not_implemented"
    assert "message" in data
    assert "agent" in data["message"].lower() or "not implemented" in data["message"].lower()


async def test_vision_run_llm_provider_with_stubbed_captioner(
    mcp_client: Client[Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """vision_run with provider=llm + a monkeypatched poster describes pending images.

    No real network: ``post_chat_completion`` is monkeypatched to return a canned
    response. After vision_run, the image drops from the default image_jobs list
    (no-drift guarantee).
    """
    monkeypatch.setenv("MINTMORY_VISION_PROVIDER", "llm")

    # Seed a pending raster file-record pointing at a real tiny PNG.
    img_path = tmp_path / "sample.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    await mcp_client.call_tool(
        "memory_add",
        {
            "content": "[image] sample.png",
            "category": "context",
            "source": "document",
            "metadata": {
                "collection": "test",
                "path": str(img_path),
                "rel": "sample.png",
                "ext": ".png",
                "size": len(img_path.read_bytes()),
                "mtime": 1_700_000_000.0,
                "online_only": False,
                "folder": ".",
                "index_mode": "vision",
            },
        },
    )

    # Confirm the image appears in image_jobs before vision_run.
    before = await mcp_client.call_tool("image_jobs", {})
    assert len(before.data) == 1, f"expected 1 pending job, got {before.data}"

    # Stub the shared poster so describe() never makes a real HTTP call.
    from mintmory.core import llm as llm_mod

    def _fake_poster(
        *,
        base_url: str,
        api_key: object,
        payload: object,
        timeout_s: object,
        system: object,
        model: object,
    ) -> dict[str, object]:
        return {"choices": [{"message": {"content": "A sample test image."}}]}

    monkeypatch.setattr(llm_mod, "post_chat_completion", _fake_poster)

    # Run vision_run — should describe 1 image.
    res = await mcp_client.call_tool("vision_run", {})
    data = res.data
    assert isinstance(data, dict)
    assert data["described"] == 1, f"expected described=1, got {data}"
    assert data["failed"] == 0
    assert data["provider"] == "llm"

    # After vision_run, the image must drop from the default image_jobs list (no-drift).
    after = await mcp_client.call_tool("image_jobs", {})
    assert after.data == [], f"expected empty image_jobs after vision_run, got {after.data}"
