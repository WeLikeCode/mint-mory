"""
Tests for MM-40: MCP resources + prompts.

Uses the FastMCP in-memory Client (same pattern as test_tools.py).
All assertions are behavioural — no direct import of private helpers except
build_schema() (which is part of the public helper surface).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastmcp import Client
from mintmory.core.history.ingest import write_session
from mintmory.core.history.models import SessionSummary
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import ConceptLinkType, MemoryCategory, MemorySource
from mintmory.mcp import server
from mintmory.mcp._schema import build_schema
from mintmory.mcp.history_server import mcp as history_mcp
from mintmory.mcp.server import mcp as main_mcp

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def mcp_client(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Client[Any]]:
    """In-memory client for the main MCP server."""
    db_file = tmp_path / "memories.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_file))
    server._store = None
    try:
        async with Client(main_mcp) as client:
            yield client
    finally:
        if server._store is not None:
            server._store.close()
        server._store = None


def _open_store(db_path: str) -> StorageAdapter:
    s = StorageAdapter(db_path)
    s.initialise()
    return s


def _make_session(session_id: str = "sess-001") -> SessionSummary:
    now = datetime.now(UTC).replace(tzinfo=None)
    ts = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return SessionSummary(
        session_id=session_id,
        agent="claude_code",
        repo="testrepo",
        repo_path="/home/user/testrepo",
        branch="main",
        ts_start=ts,
        ts_end=ts,
        turn_count=4,
        tools_used=["bash"],
        kind="feature",
        title="Test feature",
        summary_text="Implemented OAuth2 PKCE.",
        source_path="",
        distiller_version=1,
    )


@pytest.fixture
async def history_client(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client[Any]]:
    """In-memory client for the history MCP server, seeded with one session."""
    monkeypatch.delenv("MINTMORY_DB", raising=False)
    db_file = str(tmp_path / "agent-history.db")
    store = _open_store(db_file)
    write_session(store, _make_session("hist-sess-1"))
    store.close()
    monkeypatch.setenv("MINTMORY_HISTORY_DB", db_file)
    async with Client(history_mcp) as client:
        yield client


# ---------------------------------------------------------------------------
# Task 1: build_schema() unit tests
# ---------------------------------------------------------------------------


def test_build_schema_has_8_categories() -> None:
    schema = build_schema()
    assert len(schema["categories"]) == 8


def test_build_schema_has_12_link_types() -> None:
    schema = build_schema()
    assert len(schema["link_types"]) == 12


def test_build_schema_has_4_sources() -> None:
    schema = build_schema()
    assert len(schema["sources"]) == 4


def test_build_schema_all_categories_have_descriptions() -> None:
    schema = build_schema()
    for item in schema["categories"]:
        assert item["description"], f"Category {item['value']!r} has empty description"


def test_build_schema_all_link_types_have_descriptions() -> None:
    schema = build_schema()
    for item in schema["link_types"]:
        assert item["description"], f"Link type {item['value']!r} has empty description"


def test_build_schema_all_sources_covered() -> None:
    schema = build_schema()
    source_values = {s["value"] for s in schema["sources"]}
    enum_values = {e.value for e in MemorySource}
    assert source_values == enum_values


def test_build_schema_enum_coverage_categories() -> None:
    """Every MemoryCategory value appears in the schema."""
    schema = build_schema()
    schema_values = {item["value"] for item in schema["categories"]}
    enum_values = {e.value for e in MemoryCategory}
    assert schema_values == enum_values


def test_build_schema_enum_coverage_link_types() -> None:
    """Every ConceptLinkType value appears in the schema."""
    schema = build_schema()
    schema_values = {item["value"] for item in schema["link_types"]}
    enum_values = {e.value for e in ConceptLinkType}
    assert schema_values == enum_values


def test_build_schema_memory_record_fields_present() -> None:
    schema = build_schema()
    fields = schema["memory_record_fields"]
    assert isinstance(fields, list)
    assert len(fields) > 0
    for expected in ("id", "content", "category", "source", "confidence"):
        assert expected in fields, f"Expected field {expected!r} missing from memory_record_fields"


# ---------------------------------------------------------------------------
# Task 2: mintmory://schema resource
# ---------------------------------------------------------------------------


async def test_schema_resource_listed(mcp_client: Client[Any]) -> None:
    resources = await mcp_client.list_resources()
    uris = {str(r.uri) for r in resources}
    assert "mintmory://schema" in uris


async def test_schema_resource_returns_8_categories(mcp_client: Client[Any]) -> None:
    content = await mcp_client.read_resource("mintmory://schema")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    assert len(data["categories"]) == 8


async def test_schema_resource_returns_12_link_types(mcp_client: Client[Any]) -> None:
    content = await mcp_client.read_resource("mintmory://schema")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    assert len(data["link_types"]) == 12


async def test_schema_resource_all_descriptions_non_empty(mcp_client: Client[Any]) -> None:
    content = await mcp_client.read_resource("mintmory://schema")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    for item in data["categories"] + data["link_types"]:
        assert item["description"], f"Empty description for {item['value']!r}"


async def test_schema_resource_has_memory_record_fields(mcp_client: Client[Any]) -> None:
    content = await mcp_client.read_resource("mintmory://schema")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    fields = data["memory_record_fields"]
    assert isinstance(fields, list)
    assert "id" in fields
    assert "content" in fields
    assert "category" in fields


async def test_schema_resource_has_sources(mcp_client: Client[Any]) -> None:
    content = await mcp_client.read_resource("mintmory://schema")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    assert len(data["sources"]) == 4


# ---------------------------------------------------------------------------
# Task 2: mintmory://capabilities resource
# ---------------------------------------------------------------------------


async def test_capabilities_resource_listed(mcp_client: Client[Any]) -> None:
    resources = await mcp_client.list_resources()
    uris = {str(r.uri) for r in resources}
    assert "mintmory://capabilities" in uris


async def test_capabilities_resource_has_expected_keys(mcp_client: Client[Any]) -> None:
    content = await mcp_client.read_resource("mintmory://capabilities")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    for key in ("embedding_provider", "llm_provider", "llm_enabled", "vision_provider"):
        assert key in data, f"Missing key: {key!r}"


async def test_capabilities_no_api_key_in_output(mcp_client: Client[Any]) -> None:
    content = await mcp_client.read_resource("mintmory://capabilities")
    raw = content[0].text  # type: ignore[union-attr]
    assert "api_key" not in raw, "api_key must never appear in capabilities output"


async def test_capabilities_no_absolute_path_in_output(mcp_client: Client[Any]) -> None:
    content = await mcp_client.read_resource("mintmory://capabilities")
    raw = content[0].text  # type: ignore[union-attr]
    assert "/Users/" not in raw, "Absolute path leaked in capabilities"
    data = json.loads(raw)
    for v in data.values():
        if isinstance(v, str):
            assert not v.startswith("/"), f"Absolute path in capabilities value: {v!r}"


async def test_capabilities_llm_enabled_is_bool(mcp_client: Client[Any]) -> None:
    content = await mcp_client.read_resource("mintmory://capabilities")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    assert isinstance(data["llm_enabled"], bool)
    assert isinstance(data.get("dreaming_llm_steps"), bool)


# ---------------------------------------------------------------------------
# Task 3: Main-server prompts
# ---------------------------------------------------------------------------


async def test_prompts_listed_with_mintmory_prefix(mcp_client: Client[Any]) -> None:
    prompts = await mcp_client.list_prompts()
    names = {p.name for p in prompts}
    for expected in (
        "mintmory_recall_before_task",
        "mintmory_onboard",
        "mintmory_session_closeout",
        "mintmory_what_cochanged_with",
    ):
        assert expected in names, f"Prompt {expected!r} not listed"


async def test_recall_before_task_mentions_memory_search(mcp_client: Client[Any]) -> None:
    result = await mcp_client.get_prompt("mintmory_recall_before_task", {"intent": "find auth bug"})
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert "memory_search" in text, "recall prompt must mention memory_search"
    assert "session_feedback" in text, "recall prompt must mention session_feedback"
    assert "find auth bug" in text, "intent must appear in prompt text"


async def test_recall_before_task_with_link_types(mcp_client: Client[Any]) -> None:
    result = await mcp_client.get_prompt(
        "mintmory_recall_before_task",
        {"intent": "refactor login", "link_types": "relates_to,contradicts"},
    )
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert "relates_to" in text or "link_types" in text


async def test_onboard_mentions_schema(mcp_client: Client[Any]) -> None:
    result = await mcp_client.get_prompt("mintmory_onboard", {})
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert "mintmory://schema" in text, "onboard prompt must reference mintmory://schema"


async def test_onboard_parameterised_db_path(mcp_client: Client[Any]) -> None:
    result = await mcp_client.get_prompt(
        "mintmory_onboard", {"db_path": "/tmp/hermes.db", "llm_enabled": True}
    )
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert isinstance(text, str)


async def test_session_closeout_mentions_session_feedback(mcp_client: Client[Any]) -> None:
    result = await mcp_client.get_prompt(
        "mintmory_session_closeout",
        {"session_id": "abc-123", "useful_ids": "id1,id2", "stale_ids": "id3"},
    )
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert "session_feedback" in text
    assert "abc-123" in text, "session_id must appear in closeout text"


async def test_session_closeout_no_params(mcp_client: Client[Any]) -> None:
    result = await mcp_client.get_prompt("mintmory_session_closeout", {"session_id": "xyz"})
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert "session_feedback" in text


# ---------------------------------------------------------------------------
# Task 4: History server resource + prompt
# ---------------------------------------------------------------------------


async def test_history_sources_resource_listed(history_client: Client[Any]) -> None:
    resources = await history_client.list_resources()
    uris = {str(r.uri) for r in resources}
    assert "mintmory://history/sources" in uris


async def test_history_sources_has_by_collection(history_client: Client[Any]) -> None:
    content = await history_client.read_resource("mintmory://history/sources")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    assert "by_collection" in data
    assert isinstance(data["by_collection"], dict)


async def test_history_sources_has_date_range(history_client: Client[Any]) -> None:
    content = await history_client.read_resource("mintmory://history/sources")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    assert "earliest" in data
    assert "latest" in data


async def test_history_sources_no_per_session_content(history_client: Client[Any]) -> None:
    """The resource must not expose individual session summaries or transcripts."""
    content = await history_client.read_resource("mintmory://history/sources")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    assert "sessions" not in data
    assert "summaries" not in data
    assert "summary" not in data


async def test_history_sources_has_totals(history_client: Client[Any]) -> None:
    content = await history_client.read_resource("mintmory://history/sources")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    assert "total_sessions" in data
    assert "total_segments" in data
    assert data["total_sessions"] >= 1


async def test_changelog_prompt_listed(history_client: Client[Any]) -> None:
    prompts = await history_client.list_prompts()
    names = {p.name for p in prompts}
    assert "mintmory_changelog" in names


async def test_changelog_mentions_history_timeline(history_client: Client[Any]) -> None:
    result = await history_client.get_prompt(
        "mintmory_changelog", {"repo": "mintkey", "since": "30d", "kind": "fix"}
    )
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert "history_timeline" in text, "changelog prompt must mention history_timeline"
    assert "mintkey" in text, "repo param must appear in text"
    assert "30d" in text, "since param must appear in text"


async def test_changelog_no_write_words(history_client: Client[Any]) -> None:
    """Changelog prompt must not suggest any write/mutate action."""
    result = await history_client.get_prompt("mintmory_changelog", {})
    text = " ".join(m.content.text for m in result.messages).lower()  # type: ignore[union-attr]
    for forbidden in ("memory_add", "memory_archive", "memory_dream", "mutate", "write"):
        assert forbidden not in text, (
            f"changelog prompt must not mention {forbidden!r} (read-only server)"
        )


async def test_changelog_default_params(history_client: Client[Any]) -> None:
    """mintmory_changelog with no params must not error."""
    result = await history_client.get_prompt("mintmory_changelog", {})
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert "history_timeline" in text


# ---------------------------------------------------------------------------
# Manifest sanity — total new items <= 8
# ---------------------------------------------------------------------------


async def test_main_server_resource_count(mcp_client: Client[Any]) -> None:
    """Main server has exactly 2 new resources."""
    resources = await mcp_client.list_resources()
    uris = {str(r.uri) for r in resources}
    new_uris = {u for u in uris if u.startswith("mintmory://")}
    assert len(new_uris) == 2
    assert "mintmory://schema" in new_uris
    assert "mintmory://capabilities" in new_uris


async def test_main_server_prompt_count(mcp_client: Client[Any]) -> None:
    """Main server has exactly 4 mintmory_ prompts (3 from MM-40 + 1 from MM-41)."""
    prompts = await mcp_client.list_prompts()
    mintmory_prompts = [p for p in prompts if p.name.startswith("mintmory_")]
    assert len(mintmory_prompts) == 4


async def test_history_server_resource_count(history_client: Client[Any]) -> None:
    """History server has exactly 1 new resource."""
    resources = await history_client.list_resources()
    uris = {str(r.uri) for r in resources}
    new_uris = {u for u in uris if u.startswith("mintmory://")}
    assert len(new_uris) == 1
    assert "mintmory://history/sources" in new_uris


async def test_history_server_prompt_count(history_client: Client[Any]) -> None:
    """History server has exactly 1 new prompt."""
    prompts = await history_client.list_prompts()
    mintmory_prompts = [p for p in prompts if p.name.startswith("mintmory_")]
    assert len(mintmory_prompts) == 1


async def test_total_new_manifest_items_le_8(
    mcp_client: Client[Any], history_client: Client[Any]
) -> None:
    """Total new resources + prompts across both servers must be <= 8."""
    main_resources = [
        r for r in await mcp_client.list_resources() if str(r.uri).startswith("mintmory://")
    ]
    main_prompts = [p for p in await mcp_client.list_prompts() if p.name.startswith("mintmory_")]
    hist_resources = [
        r for r in await history_client.list_resources() if str(r.uri).startswith("mintmory://")
    ]
    hist_prompts = [
        p for p in await history_client.list_prompts() if p.name.startswith("mintmory_")
    ]
    total = len(main_resources) + len(main_prompts) + len(hist_resources) + len(hist_prompts)
    assert total <= 8, f"Too many manifest items: {total} > 8"
