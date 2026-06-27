"""
Tests for MM-41: docs_changed_with, docs_timeline tools + mintmory_what_cochanged_with prompt.

Uses the FastMCP in-memory Client pattern (same as test_resources_prompts.py).
Fixture setup inserts document memories + applies changesets directly via the
store (no real file-system, no sklearn required for the MCP-layer tests).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastmcp import Client
from mintmory.mcp import server
from mintmory.mcp.server import mcp

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def mcp_client(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Client[Any]]:
    """In-memory MCP client bound to an isolated temp DB."""
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


def _add_doc_memory(
    store: Any,
    *,
    path: str,
    collection: str = "test",
    mtime: float,
    changeset_id: str | None = None,
    changeset_kind: str = "",
    changeset_observed_at: str = "",
) -> Any:
    """Insert a source='document' memory with the given metadata."""
    vf = datetime.fromtimestamp(mtime, tz=UTC).replace(tzinfo=None)
    meta: dict[str, Any] = {
        "path": path,
        "rel": path.lstrip("/"),
        "collection": collection,
        "mtime": mtime,
        "modified_source": "fs_mtime",
    }
    if changeset_id is not None:
        meta["changeset_id"] = changeset_id
        meta["changeset_kind"] = changeset_kind
        meta["changeset_observed_at"] = changeset_observed_at
    return store.add_memory(
        content=f"[doc] {path}",
        category="context",
        source="document",
        valid_from=vf,
        metadata=meta,
    )


def _add_concept_link(
    store: Any,
    *,
    entity: str,
    source_memory_id: str,
    target_memory_id: str,
    strength: float,
) -> None:
    """Insert a relates_to concept_link for the co-change edge."""
    from mintmory.core.types import ConceptLink, ConceptLinkType, LinkSource

    link = ConceptLink(
        source_memory_id=source_memory_id,
        target_memory_id=target_memory_id,
        link_type=ConceptLinkType.RELATES_TO,
        entity=entity,
        strength=strength,
        source=LinkSource.INFERENCE,
    )
    store.add_link(link)


def _seed_cochange_pair(
    store: Any,
    *,
    path_a: str = "/repo/a.py",
    path_b: str = "/repo/b.py",
    changeset_id: str = "cs-test-001",
    strength: float = 0.85,
) -> tuple[Any, Any]:
    """Insert two docs in the same changeset + the edge between them."""
    now_ts = 1_700_000_000.0
    rec_a = _add_doc_memory(
        store,
        path=path_a,
        mtime=now_ts,
        changeset_id=changeset_id,
        changeset_kind="cold_full_index",
        changeset_observed_at="2024-11-14T22:13:20",
    )
    rec_b = _add_doc_memory(
        store,
        path=path_b,
        mtime=now_ts + 60,
        changeset_id=changeset_id,
        changeset_kind="cold_full_index",
        changeset_observed_at="2024-11-14T22:13:20",
    )
    entity_tag = f"changeset:{changeset_id}"
    _add_concept_link(
        store,
        entity=entity_tag,
        source_memory_id=rec_a.id,
        target_memory_id=rec_b.id,
        strength=strength,
    )
    return rec_a, rec_b


# ---------------------------------------------------------------------------
# docs_changed_with
# ---------------------------------------------------------------------------


async def test_docs_changed_with_registered(mcp_client: Client[Any]) -> None:
    """docs_changed_with must appear in the tool list."""
    names = {t.name for t in await mcp_client.list_tools()}
    assert "docs_changed_with" in names


async def test_docs_changed_with_returns_peers(mcp_client: Client[Any]) -> None:
    """For an indexed file in a changeset, returns the peer with path/strength/observed_at/kind."""
    store = server._get_store()
    _seed_cochange_pair(store, path_a="/repo/a.py", path_b="/repo/b.py")

    res = await mcp_client.call_tool("docs_changed_with", {"path": "/repo/a.py"})
    peers = res.data
    assert isinstance(peers, list)
    assert len(peers) == 1
    peer = peers[0]
    assert peer["path"] == "/repo/b.py"
    assert isinstance(peer["strength"], float)
    assert peer["strength"] == pytest.approx(0.85)
    assert peer["observed_at"] == "2024-11-14T22:13:20"
    assert peer["kind"] == "cold_full_index"


async def test_docs_changed_with_unknown_path_returns_empty(mcp_client: Client[Any]) -> None:
    """Unknown/unindexed path must return an empty list, not an error."""
    res = await mcp_client.call_tool("docs_changed_with", {"path": "/not/indexed.py"})
    assert res.data == []


async def test_docs_changed_with_no_changeset_returns_empty(mcp_client: Client[Any]) -> None:
    """A document memory WITHOUT a changeset_id returns [] (not in any change-set)."""
    store = server._get_store()
    _add_doc_memory(store, path="/solo/file.py", mtime=1_700_000_000.0)
    res = await mcp_client.call_tool("docs_changed_with", {"path": "/solo/file.py"})
    assert res.data == []


async def test_docs_changed_with_non_document_memory_never_returned(
    mcp_client: Client[Any],
) -> None:
    """A non-document (source=agent) memory is never returned, even if it has a changeset_id."""
    store = server._get_store()
    # Insert an agent memory with a path (should be invisible to changed_with,
    # which filters source='document')
    store.add_memory(
        content="agent note",
        category="fact",
        source="agent",
        metadata={
            "path": "/agent/note.py",
            "changeset_id": "cs-agent-fake",
        },
    )
    # Insert a real document peer in the same changeset (but different path)
    _add_doc_memory(
        store,
        path="/doc/real.py",
        mtime=1_700_000_000.0,
        changeset_id="cs-agent-fake",
    )
    # Query from the agent memory's path — source='document' filter means it's not found
    res = await mcp_client.call_tool("docs_changed_with", {"path": "/agent/note.py"})
    assert res.data == []


async def test_docs_changed_with_kind_may_be_empty_for_legacy(
    mcp_client: Client[Any],
) -> None:
    """kind="" is valid for legacy rows; the tool must not crash or omit the key."""
    store = server._get_store()
    now_ts = 1_700_000_000.0
    cs_id = "cs-legacy-001"
    entity_tag = f"changeset:{cs_id}"
    rec_a = _add_doc_memory(
        store,
        path="/legacy/a.py",
        mtime=now_ts,
        changeset_id=cs_id,
        changeset_kind="",  # legacy: no kind
        changeset_observed_at="2024-01-01T00:00:00",
    )
    rec_b = _add_doc_memory(
        store,
        path="/legacy/b.py",
        mtime=now_ts + 30,
        changeset_id=cs_id,
        changeset_kind="",
        changeset_observed_at="2024-01-01T00:00:00",
    )
    from mintmory.core.types import ConceptLink, ConceptLinkType, LinkSource

    store.add_link(
        ConceptLink(
            source_memory_id=rec_a.id,
            target_memory_id=rec_b.id,
            link_type=ConceptLinkType.RELATES_TO,
            entity=entity_tag,
            strength=0.7,
            source=LinkSource.INFERENCE,
        )
    )
    res = await mcp_client.call_tool("docs_changed_with", {"path": "/legacy/a.py"})
    assert len(res.data) == 1
    assert res.data[0]["kind"] == ""  # empty string, not missing


# ---------------------------------------------------------------------------
# docs_timeline
# ---------------------------------------------------------------------------


async def test_docs_timeline_registered(mcp_client: Client[Any]) -> None:
    """docs_timeline must appear in the tool list."""
    names = {t.name for t in await mcp_client.list_tools()}
    assert "docs_timeline" in names


async def test_docs_timeline_empty_on_fresh_db(mcp_client: Client[Any]) -> None:
    """Empty store returns an empty list."""
    res = await mcp_client.call_tool("docs_timeline", {})
    assert res.data == []


async def test_docs_timeline_newest_first(mcp_client: Client[Any]) -> None:
    """Documents are returned newest-first by valid_from."""
    store = server._get_store()
    _add_doc_memory(store, path="/old.py", mtime=1_000_000.0, collection="lib")
    _add_doc_memory(store, path="/new.py", mtime=2_000_000.0, collection="lib")
    _add_doc_memory(store, path="/mid.py", mtime=1_500_000.0, collection="lib")

    res = await mcp_client.call_tool("docs_timeline", {})
    data = res.data
    assert isinstance(data, list)
    assert len(data) == 3
    paths = [r["path"] for r in data]
    assert paths == ["/new.py", "/mid.py", "/old.py"]


async def test_docs_timeline_collection_filter(mcp_client: Client[Any]) -> None:
    """collection= filter returns only documents in that collection."""
    store = server._get_store()
    _add_doc_memory(store, path="/src/a.py", mtime=1_000_000.0, collection="alpha")
    _add_doc_memory(store, path="/src/b.py", mtime=1_100_000.0, collection="beta")
    _add_doc_memory(store, path="/src/c.py", mtime=1_200_000.0, collection="alpha")

    res = await mcp_client.call_tool("docs_timeline", {"collection": "alpha"})
    data = res.data
    assert isinstance(data, list)
    assert len(data) == 2
    for row in data:
        assert row["collection"] == "alpha"


async def test_docs_timeline_source_document_only(mcp_client: Client[Any]) -> None:
    """Only source='document' records appear; agent/user memories are excluded."""
    store = server._get_store()
    _add_doc_memory(store, path="/doc.py", mtime=1_000_000.0, collection="lib")
    # Insert a non-document memory (agent source)
    store.add_memory(
        content="agent knowledge",
        category="fact",
        source="agent",
        metadata={"path": "/agent.py", "collection": "lib"},
    )

    res = await mcp_client.call_tool("docs_timeline", {})
    data = res.data
    # Only the document memory should appear
    assert len(data) == 1
    assert data[0]["path"] == "/doc.py"


async def test_docs_timeline_limit_respected(mcp_client: Client[Any]) -> None:
    """limit parameter caps the returned rows."""
    store = server._get_store()
    for i in range(10):
        _add_doc_memory(store, path=f"/file{i:02d}.py", mtime=1_000_000.0 + i * 1000)

    res = await mcp_client.call_tool("docs_timeline", {"limit": 3})
    data = res.data
    assert isinstance(data, list)
    assert len(data) == 3


async def test_docs_timeline_limit_clamped_to_200(mcp_client: Client[Any]) -> None:
    """limit > 200 is HARD-CAPPED to 200 rows even when more documents exist."""
    store = server._get_store()
    # Insert 205 docs (> the 200 cap) so truncation is actually observable.
    for i in range(205):
        _add_doc_memory(store, path=f"/clamp{i:03d}.py", mtime=1_000_000.0 + i)

    # Request an absurd limit — must clamp to exactly 200, not return all 205, not error.
    res = await mcp_client.call_tool("docs_timeline", {"limit": 999999})
    data = res.data
    assert isinstance(data, list)
    assert len(data) == 200, f"cap not enforced: got {len(data)} rows"

    # A small explicit limit is still honoured (below the cap).
    res2 = await mcp_client.call_tool("docs_timeline", {"limit": 3})
    assert isinstance(res2.data, list)
    assert len(res2.data) == 3


async def test_docs_timeline_malformed_since_returns_error_dict(
    mcp_client: Client[Any],
) -> None:
    """A malformed `since` value must return an error dict, NOT raise ToolError."""
    res = await mcp_client.call_tool("docs_timeline", {"since": "bogus"})
    data = res.data
    assert isinstance(data, dict), f"Expected error dict, got {type(data)}: {data}"
    assert data.get("error") == "bad_request"
    assert "detail" in data


async def test_docs_timeline_malformed_from_date_returns_error_dict(
    mcp_client: Client[Any],
) -> None:
    """A malformed from_date must return an error dict."""
    res = await mcp_client.call_tool("docs_timeline", {"from_date": "not-a-date"})
    data = res.data
    assert isinstance(data, dict)
    assert data.get("error") == "bad_request"


async def test_docs_timeline_result_has_required_keys(mcp_client: Client[Any]) -> None:
    """Each row has date, collection, path, title, valid_from keys."""
    store = server._get_store()
    _add_doc_memory(store, path="/check.py", mtime=1_700_000_000.0, collection="lib")

    res = await mcp_client.call_tool("docs_timeline", {})
    data = res.data
    assert len(data) == 1
    row = data[0]
    for key in ("date", "collection", "path", "title", "valid_from"):
        assert key in row, f"Missing key {key!r} in row {row}"


# ---------------------------------------------------------------------------
# mintmory_what_cochanged_with prompt
# ---------------------------------------------------------------------------


async def test_what_cochanged_with_listed(mcp_client: Client[Any]) -> None:
    """mintmory_what_cochanged_with must appear in the prompt list with mintmory_ prefix."""
    prompts = await mcp_client.list_prompts()
    names = {p.name for p in prompts}
    assert "mintmory_what_cochanged_with" in names


async def test_what_cochanged_with_references_docs_changed_with(
    mcp_client: Client[Any],
) -> None:
    """Prompt text must reference docs_changed_with."""
    result = await mcp_client.get_prompt("mintmory_what_cochanged_with", {"path": "/some/file.py"})
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert "docs_changed_with" in text, "Prompt must reference docs_changed_with"


async def test_what_cochanged_with_path_in_text(mcp_client: Client[Any]) -> None:
    """The supplied path must appear in the returned guidance."""
    test_path = "/src/feature/auth.py"
    result = await mcp_client.get_prompt("mintmory_what_cochanged_with", {"path": test_path})
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert test_path in text, f"Path {test_path!r} must appear in prompt text"


async def test_what_cochanged_with_honesty_caveat(mcp_client: Client[Any]) -> None:
    """Prompt must include the not-a-commit honesty caveat."""
    result = await mcp_client.get_prompt("mintmory_what_cochanged_with", {"path": "/repo/file.py"})
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    # The spec requires the caveat that this is observed co-change, not a commit
    assert "commit" in text.lower() or "version" in text.lower(), (
        "Prompt must carry the not-a-version-controlled-commit caveat"
    )
    assert "observed" in text.lower(), "Prompt must state this is OBSERVED co-change"


async def test_what_cochanged_with_index_tree_hint(mcp_client: Client[Any]) -> None:
    """Prompt must hint to run index-tree when empty."""
    result = await mcp_client.get_prompt("mintmory_what_cochanged_with", {"path": "/repo/file.py"})
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert "index-tree" in text, "Prompt must hint to run index-tree --cochange when empty"


async def test_what_cochanged_with_no_mutating_suggestions(
    mcp_client: Client[Any],
) -> None:
    """Prompt must not suggest write or mutate operations."""
    result = await mcp_client.get_prompt("mintmory_what_cochanged_with", {"path": "/repo/file.py"})
    text = " ".join(m.content.text for m in result.messages).lower()  # type: ignore[union-attr]
    for forbidden in ("memory_add", "memory_archive", "memory_dream", "mutate"):
        assert forbidden not in text, f"Prompt must not mention {forbidden!r}"


async def test_what_cochanged_with_mentions_docs_timeline(
    mcp_client: Client[Any],
) -> None:
    """Prompt should reference docs_timeline for recency."""
    result = await mcp_client.get_prompt("mintmory_what_cochanged_with", {"path": "/repo/file.py"})
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert "docs_timeline" in text, "Prompt must mention docs_timeline for recency"


# ---------------------------------------------------------------------------
# Manifest count: main server now has 4 mintmory_ prompts
# ---------------------------------------------------------------------------


async def test_main_server_prompt_count_after_mm41(mcp_client: Client[Any]) -> None:
    """Main server must have exactly 4 mintmory_ prompts after MM-41."""
    prompts = await mcp_client.list_prompts()
    mintmory_prompts = [p for p in prompts if p.name.startswith("mintmory_")]
    assert len(mintmory_prompts) == 4, (
        f"Expected 4 mintmory_ prompts, got {len(mintmory_prompts)}: "
        f"{[p.name for p in mintmory_prompts]}"
    )
