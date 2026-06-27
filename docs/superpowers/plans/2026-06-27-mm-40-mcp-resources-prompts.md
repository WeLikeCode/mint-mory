# MM-40: MCP Resources + Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MCP resources (`mintmory://schema`, `mintmory://capabilities`, `mintmory://history/sources`) and prompts (`mintmory_recall_before_task`, `mintmory_onboard`, `mintmory_session_closeout`, `mintmory_changelog`) to the two existing MCP servers, additive-only, with full test coverage and all CI gates green.

**Architecture:** A new `packages/mcp/src/mintmory/mcp/_schema.py` module holds the curated description map and `build_schema()`. Resources and prompts are added as decorated functions directly after the existing `@mcp.tool()` blocks in `server.py` and `history_server.py`. The `history_stats` aggregation body is extracted into `_aggregate_stats()` so both the tool and the new resource call it.

**Tech Stack:** Python 3.12, FastMCP 3.4.2 (`@mcp.resource`, `@mcp.prompt`), pytest-asyncio (in-memory `Client`), ruff (line-length=100), mypy --strict.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `packages/mcp/src/mintmory/mcp/_schema.py` | **Create** | Curated description map + `build_schema()` |
| `packages/mcp/src/mintmory/mcp/server.py` | **Modify** | Add 2 resources + 3 prompts (additive) |
| `packages/mcp/src/mintmory/mcp/history_server.py` | **Modify** | Extract `_aggregate_stats()`, add 1 resource + 1 prompt (additive) |
| `packages/mcp/tests/test_resources_prompts.py` | **Create** | All new tests |
| `docs/agent-history-mcp.md` | **Modify** | Add "Resources & Prompts" section |

---

## Task 1: Create `_schema.py` with curated description map and `build_schema()`

**Files:**
- Create: `packages/mcp/src/mintmory/mcp/_schema.py`

- [ ] **Step 1.1: Write the failing test for `build_schema()`**

Create `packages/mcp/tests/test_resources_prompts.py` with this opening block:

```python
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
from mintmory.core.types import ConceptLinkType, MemoryCategory, MemoryRecord, MemorySource
from mintmory.mcp._schema import build_schema
from mintmory.mcp import server, history_server
from mintmory.mcp.server import mcp as main_mcp
from mintmory.mcp.history_server import mcp as history_mcp
from mintmory.core.history.ingest import write_session
from mintmory.core.history.models import SessionSummary
from mintmory.core.storage import StorageAdapter


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
    # Spot-check a few expected fields
    for expected in ("id", "content", "category", "source", "confidence"):
        assert expected in fields, f"Expected field {expected!r} missing from memory_record_fields"
```

- [ ] **Step 1.2: Run the test to confirm it fails (import error expected)**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/test_resources_prompts.py::test_build_schema_has_8_categories -x -q 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'mintmory.mcp._schema'`

- [ ] **Step 1.3: Create `_schema.py`**

Create `packages/mcp/src/mintmory/mcp/_schema.py`:

```python
"""
Schema helper for the mintmory://schema MCP resource (MM-40).

Provides a curated one-line description per MemoryCategory / ConceptLinkType /
MemorySource value. Names are always iterated from the live enums; descriptions
are kept in the CATEGORY_DESCRIPTIONS / LINK_TYPE_DESCRIPTIONS / SOURCE_DESCRIPTIONS
maps below. A coverage guard raises KeyError immediately if a new enum value is
added without a corresponding description (caught by the unit-test suite before CI).
"""

from __future__ import annotations

from mintmory.core.types import ConceptLinkType, MemoryCategory, MemoryRecord, MemorySource

# ---------------------------------------------------------------------------
# Curated description maps — copied from inline comments in core/types.py
# ---------------------------------------------------------------------------

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "identity": "Persistent facts about the user/agent",
    "preference": "Stated or inferred preferences",
    "skill": "How to do something; procedures, tools, recipes",
    "context": "Current working context, active project state",
    "fact": "World-state facts, configuration values, URLs",
    "episodic": "Something that happened in a specific session",
    "temporal": "Time-bounded fact with explicit validity window",
    "relationship": "A typed link between two entities (stored as ConceptLink)",
}

LINK_TYPE_DESCRIPTIONS: dict[str, str] = {
    "relates_to": "General connection, no specific direction (symmetric)",
    "contradicts": "Cannot both be true (symmetric)",
    "refines": "B adds specificity to A; inverse: generalizes",
    "supersedes": "B replaces A completely; inverse: precedes",
    "enables": "A made B possible; inverse: enabled_by",
    "depends_on": "A requires B; inverse: supports",
    "similar_to": "A is like B (symmetric)",
    "part_of": "A is contained in B; inverse: contains",
    "uses": "A actively uses B; inverse: used_by",
    "before": "A occurred before B (temporal); inverse: after",
    "valid_until": "A is true until time T (encoded in target metadata)",
    "annotates": "A (a note) annotates B (the item it is about); inverse: annotated_by",
}

SOURCE_DESCRIPTIONS: dict[str, str] = {
    "user": "Explicitly provided by the human user",
    "agent": "Inferred or generated by the AI agent",
    "document": "Extracted from an indexed document or file",
    "inference": "Derived by the system during processing",
}


# ---------------------------------------------------------------------------
# Schema builder
# ---------------------------------------------------------------------------


def build_schema() -> dict[str, object]:
    """Build the mintmory://schema resource payload.

    Iterates the live enums for names and looks up the curated descriptions.
    Raises KeyError if any enum value is missing a description (coverage guard).
    """
    categories: list[dict[str, str]] = []
    for member in MemoryCategory:
        desc = CATEGORY_DESCRIPTIONS[member.value]  # KeyError = missing description
        categories.append({"value": member.value, "description": desc})

    link_types: list[dict[str, str]] = []
    for member in ConceptLinkType:
        desc = LINK_TYPE_DESCRIPTIONS[member.value]  # KeyError = missing description
        link_types.append({"value": member.value, "description": desc})

    sources: list[dict[str, str]] = []
    for member in MemorySource:
        desc = SOURCE_DESCRIPTIONS[member.value]  # KeyError = missing description
        sources.append({"value": member.value, "description": desc})

    memory_record_fields: list[str] = list(MemoryRecord.model_fields)

    return {
        "categories": categories,
        "link_types": link_types,
        "sources": sources,
        "memory_record_fields": memory_record_fields,
    }
```

- [ ] **Step 1.4: Run the schema unit tests**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/test_resources_prompts.py -k "build_schema" -v 2>&1 | tail -20
```

Expected: All `test_build_schema_*` tests pass.

---

## Task 2: Add `mintmory://schema` and `mintmory://capabilities` resources to `server.py`

**Files:**
- Modify: `packages/mcp/src/mintmory/mcp/server.py`
- Modify: `packages/mcp/tests/test_resources_prompts.py` (append new tests)

- [ ] **Step 2.1: Append resource tests to `test_resources_prompts.py`**

Append these tests to `packages/mcp/tests/test_resources_prompts.py`:

```python
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
    # No absolute path should appear — no '/Users/', no leading '/'
    assert "/Users/" not in raw, "Absolute path leaked in capabilities"
    # Check no value starts with '/' by scanning strings in the parsed dict
    data = json.loads(raw)
    for v in data.values():
        if isinstance(v, str):
            assert not v.startswith("/"), f"Absolute path in capabilities value: {v!r}"


async def test_capabilities_llm_enabled_is_bool(mcp_client: Client[Any]) -> None:
    content = await mcp_client.read_resource("mintmory://capabilities")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    assert isinstance(data["llm_enabled"], bool)
    assert isinstance(data.get("dreaming_llm_steps"), bool)
```

- [ ] **Step 2.2: Run the resource tests to confirm they fail**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/test_resources_prompts.py -k "schema_resource or capabilities_resource" -x -q 2>&1 | tail -10
```

Expected: Failures because the resources do not yet exist.

- [ ] **Step 2.3: Add resources to `server.py`**

In `packages/mcp/src/mintmory/mcp/server.py`, find the `from mintmory.mcp.concise import ...` import line and add:

```python
from mintmory.mcp._schema import build_schema
```

Then, after the `_get_store()` function (around line 98, after the closing `return _store`), add a blank line and these two resource handlers — before the `# Tools` section comment:

```python
# ---------------------------------------------------------------------------
# Resources — read-on-demand structured data (MM-40)
# ---------------------------------------------------------------------------


@mcp.resource("mintmory://schema")
def mintmory_schema() -> dict[str, object]:
    """Memory taxonomy: all MemoryCategory / ConceptLinkType / MemorySource values
    with one-line descriptions, plus the MemoryRecord field list. Zero PII."""
    return build_schema()


@mcp.resource("mintmory://capabilities")
def mintmory_capabilities() -> dict[str, object]:
    """Active configuration summary (providers, flags). Never includes api_key or
    absolute DB paths. Returns a safe minimal dict on settings-load failure."""
    try:
        settings = load_settings()
        from mintmory.core.config import LLMProvider  # noqa: PLC0415

        llm_enabled = settings.llm.provider is not LLMProvider.NONE
        return {
            "embedding_provider": settings.embed.provider.value,
            "llm_provider": settings.llm.provider.value,
            "llm_enabled": llm_enabled,
            "llm_model": settings.llm.model,
            "vision_provider": settings.vision.provider.value,
            "dreaming_llm_steps": llm_enabled,
        }
    except Exception:  # noqa: BLE001
        return {"error": "settings unavailable"}
```

- [ ] **Step 2.4: Run the resource tests again**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/test_resources_prompts.py -k "schema_resource or capabilities" -v 2>&1 | tail -20
```

Expected: All resource tests pass.

---

## Task 3: Add three prompts to `server.py`

**Files:**
- Modify: `packages/mcp/src/mintmory/mcp/server.py`
- Modify: `packages/mcp/tests/test_resources_prompts.py` (append prompt tests)

- [ ] **Step 3.1: Append prompt tests for the main server**

Append to `packages/mcp/tests/test_resources_prompts.py`:

```python
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
    ):
        assert expected in names, f"Prompt {expected!r} not listed"


async def test_recall_before_task_mentions_memory_search(mcp_client: Client[Any]) -> None:
    result = await mcp_client.get_prompt(
        "mintmory_recall_before_task", {"intent": "find auth bug"}
    )
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
    # llm_enabled=True should be reflected; db_path is accepted without error
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
```

- [ ] **Step 3.2: Run prompt tests to confirm failure**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/test_resources_prompts.py -k "prompt" -x -q 2>&1 | tail -10
```

Expected: Failures (prompts not yet registered).

- [ ] **Step 3.3: Add prompts to `server.py`**

After the resources block (after `mintmory_capabilities` function), add:

```python
# ---------------------------------------------------------------------------
# Prompts — pre-authored agent-policy templates (MM-40)
# ---------------------------------------------------------------------------


@mcp.prompt()
def mintmory_recall_before_task(intent: str, link_types: str = "") -> str:
    """Guidance to search memory before acting on a task, then close the loop.

    Args:
        intent: What you are about to work on (used as the search query).
        link_types: Optional comma-separated ConceptLinkType values for graph
            traversal, e.g. "relates_to,contradicts". Leave empty for no graph hop.
    """
    lt_clause = ""
    if link_types.strip():
        lt_clause = (
            f', search_around_link_types={link_types.strip().split(",")!r}'
        )
    return (
        f"Before acting on: {intent!r}\n\n"
        "1. RECALL FIRST — call memory_search:\n"
        f'   memory_search(query="{intent}"{lt_clause})\n'
        "   KEEP the returned session_id — you will need it in step 3.\n\n"
        "2. ACT — use the retrieved memories to inform your work.\n\n"
        "3. CLOSE THE LOOP — after finishing, call session_feedback:\n"
        "   session_feedback(\n"
        "       session_id=<session_id from step 1>,\n"
        "       useful_ids=[<ids of memories that helped>],\n"
        "       stale_ids=[<ids of memories that were wrong or outdated>],\n"
        "       confidence_rating=1..5,\n"
        "       reasoning='<one sentence explanation>',\n"
        "   )\n"
        "   This self-assessment lets MintMory improve without human intervention.\n\n"
        "Source policy: hermes-onboarding.md §STEP 5 (recall→feedback discipline)."
    )


@mcp.prompt()
def mintmory_onboard(db_path: str = "", llm_enabled: bool = False) -> str:
    """MintMory onboarding policy (Part 1). Renders the adoption checklist as a prompt.

    Args:
        db_path: Optional path to the MintMory database (shown in the YAML snippet).
        llm_enabled: When True, includes LLM-tier configuration guidance.
    """
    db_line = f"MINTMORY_DB: {db_path}" if db_path else "MINTMORY_DB: ~/.mintmory/memories.db"
    llm_section = ""
    if llm_enabled:
        llm_section = (
            "\n      MINTMORY_LLM_PROVIDER: openai\n"
            "      MINTMORY_LLM_BASE_URL: http://localhost:8789/v1\n"
            "      MINTMORY_LLM_MODEL: MiniMax-M2.7"
        )
    return (
        "## MintMory Onboarding — adopt this memory policy\n\n"
        "MintMory is a local, typed, graph-linked memory system. Taxonomy reference:\n"
        "  mintmory://schema  (read with your MCP client to see all 8 categories +\n"
        "                      12 link types with descriptions)\n\n"
        "### Register the MCP server\n\n"
        "Add this block to your MCP configuration (command: uv run mintmory-mcp):\n\n"
        "    mintmory:\n"
        "      command: uv\n"
        "      args: [run, --project, /path/to/MintMory, mintmory-mcp]\n"
        "      enabled: true\n"
        "      env:\n"
        f"        {db_line}\n"
        "        MINTMORY_EMBED_PROVIDER: hashing"
        f"{llm_section}\n\n"
        "### Memory policy — apply every task\n\n"
        "  • RECALL FIRST: memory_search(query=<intent>) before acting.\n"
        "    Pass search_around_link_types=['relates_to'] for related items.\n"
        "    KEEP the returned session_id.\n\n"
        "  • WRITE durable knowledge: memory_add(content, category) where category\n"
        "    is one of: identity | preference | skill | context | fact |\n"
        "    episodic | temporal | relationship. One idea per memory.\n\n"
        "  • CLOSE THE LOOP: session_feedback(session_id, useful_ids=[...],\n"
        "    stale_ids=[...], confidence_rating=1..5). MintMory self-improves.\n\n"
        "  • CONSOLIDATE: memory_dream(intensity='full') when idle, to build\n"
        "    links + summaries and resolve contradictions.\n\n"
        "  • NOTES: use memory_note only when the user EXPLICITLY asks you to\n"
        "    remember something ('remember that...', 'note that...').\n\n"
        "  • BULK LOAD: mintmory ingest <paths...> --category <cat>\n"
        "    (chunks + dedups automatically; never script add-per-file).\n\n"
        "### Health check\n\n"
        "  mintmory doctor   # exit 0 = healthy\n\n"
        "Source policy: hermes-onboarding.md Part 1."
    )


@mcp.prompt()
def mintmory_session_closeout(
    session_id: str, useful_ids: str = "", stale_ids: str = ""
) -> str:
    """Guidance to submit session feedback and close the memory feedback loop.

    Args:
        session_id: The QuerySession id returned by memory_search.
        useful_ids: Comma-separated memory ids the agent found helpful.
        stale_ids: Comma-separated memory ids the agent found stale or incorrect.
    """
    useful_list = [i.strip() for i in useful_ids.split(",") if i.strip()]
    stale_list = [i.strip() for i in stale_ids.split(",") if i.strip()]
    return (
        "## Close the memory feedback loop\n\n"
        f"Session id: {session_id}\n\n"
        "Call session_feedback to record your passive self-assessment:\n\n"
        "    session_feedback(\n"
        f"        session_id={session_id!r},\n"
        f"        useful_ids={useful_list!r},\n"
        f"        stale_ids={stale_list!r},\n"
        "        confidence_rating=1..5,   # your overall confidence\n"
        "        reasoning='<one sentence>',\n"
        "    )\n\n"
        "This updates usefulness/staleness scores so MintMory self-improves.\n"
        "If you found no relevant memories, submit with empty lists — still call it.\n"
        "A session can only receive feedback once (returns conflict error if repeated)."
    )
```

- [ ] **Step 3.4: Run the prompt tests**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/test_resources_prompts.py -k "prompt or recall or onboard or closeout" -v 2>&1 | tail -25
```

Expected: All prompt tests pass.

---

## Task 4: Refactor `history_server.py` and add history resource + prompt

**Files:**
- Modify: `packages/mcp/src/mintmory/mcp/history_server.py`
- Modify: `packages/mcp/tests/test_resources_prompts.py` (append history tests)

- [ ] **Step 4.1: Append history server tests**

Append to `packages/mcp/tests/test_resources_prompts.py`:

```python
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
    # Must NOT have a 'sessions' or 'summaries' key with per-session text
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
# Task 5: Manifest sanity — total new items <= 8
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
    """Main server has exactly 3 new prompts."""
    prompts = await mcp_client.list_prompts()
    mintmory_prompts = [p for p in prompts if p.name.startswith("mintmory_")]
    assert len(mintmory_prompts) == 3


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
        r
        for r in await history_client.list_resources()
        if str(r.uri).startswith("mintmory://")
    ]
    hist_prompts = [
        p for p in await history_client.list_prompts() if p.name.startswith("mintmory_")
    ]
    total = len(main_resources) + len(main_prompts) + len(hist_resources) + len(hist_prompts)
    assert total <= 8, f"Too many manifest items: {total} > 8"
```

- [ ] **Step 4.2: Run the history tests to confirm they fail**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/test_resources_prompts.py -k "history_sources or changelog" -x -q 2>&1 | tail -10
```

Expected: Failures.

- [ ] **Step 4.3: Refactor `history_server.py` — extract `_aggregate_stats()` and add resource + prompt**

In `packages/mcp/src/mintmory/mcp/history_server.py`:

1. Add the `_aggregate_stats` helper directly before the `history_stats` tool (around line 153). Add these imports at the top of the file (after existing imports):

```python
import json as _json
```

(Note: `_json` is already imported inside `history_stats` — move it to module level.)

2. The full modified history_server.py additions should be:

After the `_db_path()` function and before `# Tools`, add a section comment and the helper:

```python
# ---------------------------------------------------------------------------
# Shared aggregation helper (used by both history_stats tool and
# mintmory://history/sources resource — MM-40)
# ---------------------------------------------------------------------------


def _aggregate_stats(db_path: str) -> dict[str, object]:
    """Aggregate indexed session-summary rows into stats dict.

    Returns: total_sessions, total_segments, by_collection, by_kind,
             earliest, latest. No per-session content is included.
    """
    import json as _json_inner  # local import keeps module-level clean

    store = query._open_history(db_path)
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
        meta: dict[str, Any] = _json_inner.loads(row["metadata"] or "{}")
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
```

3. Replace the body of `history_stats` to call `_aggregate_stats`:

```python
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
    result: dict[str, Any] = _aggregate_stats(_db_path())
    return result
```

4. After `history_stats`, add the resource and prompt:

```python
# ---------------------------------------------------------------------------
# Resources — read-on-demand structured data (MM-40)
# ---------------------------------------------------------------------------


@mcp.resource("mintmory://history/sources")
def mintmory_history_sources() -> dict[str, object]:
    """Indexed collections with per-collection counts and earliest/latest dates.
    No per-session content. Derived from the same aggregation as history_stats."""
    stats = _aggregate_stats(_db_path())
    # Return only the orientation fields — no per-session content
    return {
        "by_collection": stats["by_collection"],
        "total_sessions": stats["total_sessions"],
        "total_segments": stats["total_segments"],
        "earliest": stats["earliest"],
        "latest": stats["latest"],
    }


# ---------------------------------------------------------------------------
# Prompts — read-only guidance for history tools (MM-40)
# ---------------------------------------------------------------------------


@mcp.prompt()
def mintmory_changelog(repo: str = "", since: str = "90d", kind: str = "") -> str:
    """Guidance to query the agent-history changelog for a time window.

    References only READ tools — this server has no write capability.

    Args:
        repo: Optional repo name to filter (e.g. 'mintkey'). Empty = all repos.
        since: Relative window like '90d', '8w', '3m', '2y' (default '90d').
        kind: Optional kind filter (fix/feature/refactor/…). Empty = all kinds.
    """
    repo_clause = f", repo={repo!r}" if repo.strip() else ""
    kind_clause = f", kind={kind!r}" if kind.strip() else ""
    return (
        "## Agent-history changelog\n\n"
        "To see what changed, call history_timeline (a READ-only tool):\n\n"
        f"    history_timeline(\n"
        f"        since={since!r}{repo_clause}{kind_clause},\n"
        f"        limit=50,\n"
        f"    )\n\n"
        "Results are returned newest-first. Each row has: date, repo, kind, title,\n"
        "summary, session_id, and source_path back-links.\n\n"
        "Tips:\n"
        f"  • Use since='{since}' for the last {since} (e.g. '30d'=30 days, '2m'=2 months).\n"
        "  • Pass from_date/to_date (ISO strings) instead of since for absolute ranges.\n"
        "  • Use history_search(query_text=...) for topic-based recall across all time.\n"
        "  • Use history_stats() to see per-collection counts and the date range.\n\n"
        "This server is READ-ONLY: no memory_add, memory_archive, or other write tools\n"
        "are available here."
    )
```

- [ ] **Step 4.4: Run the history tests**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/test_resources_prompts.py -v 2>&1 | tail -30
```

Expected: All tests pass.

---

## Task 5: Run all existing tests to verify no regression

- [ ] **Step 5.1: Run the full test suite**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest -q 2>&1 | tail -20
```

Expected: All existing tests pass; new tests pass; coverage >= 80%.

---

## Task 6: Run ruff and mypy gates

- [ ] **Step 6.1: Run ruff check**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync ruff check packages/mcp/src/mintmory/mcp/_schema.py packages/mcp/src/mintmory/mcp/server.py packages/mcp/src/mintmory/mcp/history_server.py packages/mcp/tests/test_resources_prompts.py 2>&1
```

Expected: No errors. Fix any linting issues before moving on.

- [ ] **Step 6.2: Run ruff format**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync ruff format packages/mcp/src/mintmory/mcp/_schema.py packages/mcp/src/mintmory/mcp/server.py packages/mcp/src/mintmory/mcp/history_server.py packages/mcp/tests/test_resources_prompts.py
```

Expected: Files reformatted (or "N files left unchanged").

- [ ] **Step 6.3: Run ruff check again after format**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync ruff check . 2>&1 | tail -5
```

Expected: No errors.

- [ ] **Step 6.4: Run mypy**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync mypy packages 2>&1 | tail -20
```

Expected: `Success: no issues found in N source files`. Fix any type errors. Common issues:
- `dict[str, object]` return types on resource handlers must match the decorated function annotation.
- Add `from __future__ import annotations` if not present.
- `_aggregate_stats` should return `dict[str, object]` with a `# type: ignore[return-value]` on the int fields if mypy complains about `int` vs `object`.

If mypy reports errors, fix them. The most likely issue is that `dict[str, Any]` from `_aggregate_stats` may not match `dict[str, object]`. Use `dict[str, Any]` throughout to be consistent with the existing codebase pattern.

- [ ] **Step 6.5: Run full test suite one more time**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest -q 2>&1 | tail -10
```

---

## Task 7: Add docs section

**Files:**
- Modify: `docs/agent-history-mcp.md`

- [ ] **Step 7.1: Add "Resources & Prompts" section to `docs/agent-history-mcp.md`**

Insert after line 98 (after the "Typical agent use:" paragraph, before `---`), add:

```markdown
### Resources & Prompts (MM-40)

The history server also exposes:

**Resource:**
- `mintmory://history/sources` — per-collection session counts + earliest/latest dates. Read with your MCP client to get an orientation view without fetching session content.

**Prompt:**
- `mintmory_changelog(repo?, since?, kind?)` — guidance to call `history_timeline` for the requested window. Read-only; references no write tools.

The main `mintmory-mcp` server (for working memory) exposes:

**Resources:**
- `mintmory://schema` — all 8 memory categories, 12 link types, and 4 sources with one-line descriptions, plus the `MemoryRecord` field list.
- `mintmory://capabilities` — active configuration summary (embedding provider, LLM provider + enabled flag + model, vision provider, dreaming steps). Never includes API keys.

**Prompts:**
- `mintmory_onboard(db_path?, llm_enabled?)` — the MintMory adoption policy as a prompt.
- `mintmory_recall_before_task(intent, link_types?)` — search-first → act → session_feedback discipline.
- `mintmory_session_closeout(session_id, useful_ids?, stale_ids?)` — the session feedback close-out call.
```

- [ ] **Step 7.2: Run the full test suite to confirm docs edit did not break anything**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest -q 2>&1 | tail -5
```

---

## Task 8: Run openspec validate gate

- [ ] **Step 8.1: Run openspec validate**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
openspec validate add-mcp-resources-prompts --strict 2>&1 | tail -20
```

Expected: All scenarios pass. If any fail, check:
- Schema resource returns exactly 8 categories + 12 link types.
- Capabilities resource does not include `api_key` or absolute paths.
- History sources does not include per-session content.
- Changelog prompt text does not include write/add/archive/mutate words.

---

## Self-Review Against Spec

**Spec coverage check:**

| Requirement | Task |
|---|---|
| `mintmory://schema` with all 8 categories + 12 link types + descriptions | Task 1, 2 |
| `mintmory://capabilities` with no secrets | Task 2 |
| `mintmory://history/sources` read-only | Task 4 |
| `mintmory_recall_before_task` prompt | Task 3 |
| `mintmory_onboard` prompt | Task 3 |
| `mintmory_session_closeout` prompt | Task 3 |
| `mintmory_changelog` read-only prompt | Task 4 |
| Tests: 8 categories, 12 link types with descriptions | Task 1 |
| Tests: no api_key, no absolute path in capabilities | Task 2 |
| Tests: history/sources no per-session content | Task 4 |
| Tests: prompts listed with mintmory_ prefix | Task 3, 4 |
| Tests: recall mentions memory_search + session_feedback | Task 3 |
| Tests: changelog mentions history_timeline, no write words | Task 4 |
| Tests: manifest <= 8 items | Task 4 |
| Existing tests stay green | Task 5 |
| ruff + format clean | Task 6 |
| mypy 0 errors | Task 6 |
| Docs updated | Task 7 |
| openspec validate | Task 8 |

**Placeholder scan:** No TBD/TODO. All code is complete.

**Type consistency:** `build_schema()` returns `dict[str, object]`. Resource handlers return `dict[str, object]`. Prompt handlers return `str`. `_aggregate_stats()` returns `dict[str, object]`. All consistent.

**Known mypy risk:** The `_aggregate_stats` function mixes `int` and `str | None` values in a `dict[str, object]` — this is intentional; mypy will accept it since `int` and `str | None` are both subtypes of `object`.

**Known linter risk:** The `# noqa: PLC0415` on the `LLMProvider` import inside the capabilities handler. Move that import to the top of `server.py` instead to avoid it: `from mintmory.core.config import LLMProvider` is already safe to add since `LLMProvider` is already in `config.py`.
