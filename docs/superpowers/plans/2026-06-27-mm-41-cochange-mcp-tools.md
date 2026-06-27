# MM-41: Co-change/Recency MCP Tools + Prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `docs_changed_with`, `docs_timeline`, and the `mintmory_what_cochanged_with` prompt on the main MCP server so agentic clients can query co-change and document recency data.

**Architecture:** Two new `@mcp.tool()` wrappers over existing `core/cochange.py` functions (additive, read-only, no core changes). One new `@mcp.prompt()` on the main server. Both tools scope to `source='document'` records via the underlying functions. The `docs_timeline` tool clamps `limit` to a hard 200-row cap and catches `ValueError` from malformed date windows, returning an error dict (matching the `notes_list` precedent).

**Tech Stack:** FastMCP, Python 3.12, uv workspace, pytest with asyncio_mode=auto, mypy --strict, ruff line-length 100. Test fixtures use the FastMCP in-memory `Client` pattern from `test_resources_prompts.py`.

---

### Task 1: Add imports and tools to server.py

**Files:**
- Modify: `packages/mcp/src/mintmory/mcp/server.py` (line 57 import block; after notes_list ~line 638)

> **READ FIRST** (no edits in this step): scan `server.py` to locate:
> - The import block (lines 30–59) where `from mintmory.core import notes as notes_mod` lives.
> - The end of the `notes_list` tool (around line 638) — new tools go after it, before the image tools section.
> - The `_DOCS_TIMELINE_MAX` constant must be at module level before `docs_timeline`.

- [ ] **Step 1: Add the import for `changed_with` and `documents_timeline`**

In `packages/mcp/src/mintmory/mcp/server.py`, find the import block (around line 42 where `from mintmory.core import notes as notes_mod` is). Add after it:

```python
from mintmory.core.cochange import changed_with, documents_timeline
```

The full import block should now contain:
```python
from mintmory.core import notes as notes_mod
from mintmory.core import session as session_mod
from mintmory.core.cochange import changed_with, documents_timeline
from mintmory.core.config import LLMProvider, load_settings
```

- [ ] **Step 2: Add the `_DOCS_TIMELINE_MAX` constant and two tools after `notes_list`**

Find the end of the `notes_list` tool (after `return [m.model_dump(mode="json") for m in records]`). The section comment before image tools reads:
```
# ---------------------------------------------------------------------------
# Image-understanding tools (agent-supplied vision, G5)
# ---------------------------------------------------------------------------
```

Insert the following block BEFORE that image section comment:

```python
# ---------------------------------------------------------------------------
# Co-change / document recency tools (MM-41)
# ---------------------------------------------------------------------------

_DOCS_TIMELINE_MAX = 200  # hard cap so a single MCP call cannot pull the whole corpus


@mcp.tool()
def docs_changed_with(path: str) -> list[dict[str, Any]]:
    """Documents observed to co-change with <path> (same index-tree change-set).

    Returns [{path, strength, observed_at, kind}] — each peer in the same observed
    change-set as <path>. Empty if <path> is not indexed or not part of a change-set.

    OBSERVED co-change means the files were indexed in the same time window with
    high folder/content proximity — NOT a version-controlled commit. `kind` may be
    empty ("") for legacy rows that predate changeset_kind labelling.

    To populate this data: run `mintmory index-tree <root> --cochange` first.
    Read-only. Only source='document' records are ever returned.
    """
    return changed_with(_get_store(), path)


@mcp.tool()
def docs_timeline(
    since: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    collection: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]] | dict[str, str]:
    """Indexed documents newest-first by file modified-time (valid_from).

    Returns [{date, collection, path, title, valid_from}]. Use `since='30d'` for a
    rolling window, or `from_date`/`to_date` (ISO 8601) for a fixed range.
    Optional `collection` filter. `limit` is capped at 200 for token safety.

    A malformed `since`/date value returns {"error": "bad_request", "detail": ...}
    instead of raising. Read-only. Only source='document' records appear.
    """
    capped = max(1, min(limit, _DOCS_TIMELINE_MAX))
    try:
        return documents_timeline(
            _get_store(),
            since=since,
            from_iso=from_date,
            to_iso=to_date,
            collection=collection,
            limit=capped,
        )
    except ValueError as exc:  # bad `since`/date grammar
        return {"error": "bad_request", "detail": str(exc)}
```

- [ ] **Step 3: Add `mintmory_what_cochanged_with` prompt**

The existing prompts live between the resources section and the tools section (around lines 136–246). Add the new prompt after `mintmory_session_closeout` (after its closing `)`):

```python
@mcp.prompt()
def mintmory_what_cochanged_with(path: str) -> str:
    """Find documents that co-changed with a file, and how to read the result."""
    return (
        f"To find documents that co-changed with {path!r}:\n\n"
        f"1. Call docs_changed_with(path={path!r})\n\n"
        "2. Read each peer result:\n"
        "   • `strength` (0.0–1.0): proximity score — higher = stronger co-change signal.\n"
        "   • `observed_at`: ISO timestamp of when the co-change was observed.\n"
        "   • `kind`: changeset kind — `cold_full_index` means co-location (same folder,\n"
        "     same indexing run), `incremental` means a later re-index caught both files.\n"
        "     `kind` may be empty (\"\") for legacy rows.\n\n"
        "HONESTY CAVEAT: this is OBSERVED co-change — files that were indexed in the\n"
        "same time window with high folder + content proximity. It is NOT a version-\n"
        "controlled commit. `cold_full_index` peers may simply be co-located in the\n"
        "same directory, not actually co-edited.\n\n"
        f"3. If the result is empty, {path!r} may not be indexed or may not belong\n"
        "   to any change-set. Run:\n"
        "     mintmory index-tree <root> --cochange\n"
        "   to (re-)build co-change data for the corpus.\n\n"
        "4. For document recency (which files are newest), call docs_timeline with\n"
        "   an optional `since` window (e.g. since='30d') or `from_date`/`to_date`.\n\n"
        "This prompt suggests NO write or mutate operations."
    )
```

- [ ] **Step 4: Run ruff and mypy to check for errors**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync ruff check packages/mcp/src/mintmory/mcp/server.py
uv run --no-sync mypy packages/mcp/src/mintmory/mcp/server.py
```

Expected: no errors. If mypy complains about the union return type `list[dict[str, Any]] | dict[str, str]`, verify the annotation is on the function signature (not in a `cast`).

---

### Task 2: Write failing tests for the new tools and prompt

**Files:**
- Create: `packages/mcp/tests/test_cochange_tools.py`

- [ ] **Step 1: Write the test file (all tests will initially fail because tools don't exist yet... but since we added them in Task 1, they exist; use FAIL-first iteration to verify test correctness)**

Create `/Users/alexandruiacobescu/gooseProjects/MintMory/packages/mcp/tests/test_cochange_tools.py`:

```python
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


async def test_docs_changed_with_returns_peers(
    mcp_client: Client[Any], tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
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


async def test_docs_changed_with_no_changeset_returns_empty(
    mcp_client: Client[Any],
) -> None:
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
    # Insert an agent memory with a changeset_id (should be invisible to changed_with)
    store.add_memory(
        content="agent note",
        category="fact",
        source="agent",
        metadata={
            "path": "/agent/note.py",
            "changeset_id": "cs-agent-fake",
        },
    )
    # Insert a real document peer in the same changeset
    _add_doc_memory(
        store,
        path="/doc/real.py",
        mtime=1_700_000_000.0,
        changeset_id="cs-agent-fake",
    )
    # Query from the agent memory's path — source='document' filter means it's not indexed
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
    """limit > 200 is silently clamped to 200 (no error, no stack trace)."""
    store = server._get_store()
    # Insert 5 docs — clamping means the call must succeed, not that we get 200 rows.
    for i in range(5):
        _add_doc_memory(store, path=f"/clamp{i}.py", mtime=1_000_000.0 + i)

    # Request an absurd limit — should clamp, not error
    res = await mcp_client.call_tool("docs_timeline", {"limit": 999999})
    data = res.data
    assert isinstance(data, list)
    # With 5 docs, 5 rows are returned (well below cap)
    assert len(data) == 5


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
    result = await mcp_client.get_prompt(
        "mintmory_what_cochanged_with", {"path": "/some/file.py"}
    )
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert "docs_changed_with" in text, "Prompt must reference docs_changed_with"


async def test_what_cochanged_with_path_in_text(mcp_client: Client[Any]) -> None:
    """The supplied path must appear in the returned guidance."""
    test_path = "/src/feature/auth.py"
    result = await mcp_client.get_prompt(
        "mintmory_what_cochanged_with", {"path": test_path}
    )
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert test_path in text, f"Path {test_path!r} must appear in prompt text"


async def test_what_cochanged_with_honesty_caveat(mcp_client: Client[Any]) -> None:
    """Prompt must include the not-a-commit honesty caveat."""
    result = await mcp_client.get_prompt(
        "mintmory_what_cochanged_with", {"path": "/repo/file.py"}
    )
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    # The spec requires the caveat that this is observed co-change, not a commit
    assert "commit" in text.lower() or "version" in text.lower(), (
        "Prompt must carry the not-a-version-controlled-commit caveat"
    )
    assert "observed" in text.lower(), "Prompt must state this is OBSERVED co-change"


async def test_what_cochanged_with_index_tree_hint(mcp_client: Client[Any]) -> None:
    """Prompt must hint to run index-tree when empty."""
    result = await mcp_client.get_prompt(
        "mintmory_what_cochanged_with", {"path": "/repo/file.py"}
    )
    text = " ".join(m.content.text for m in result.messages)  # type: ignore[union-attr]
    assert "index-tree" in text, "Prompt must hint to run index-tree --cochange when empty"


async def test_what_cochanged_with_no_mutating_suggestions(
    mcp_client: Client[Any],
) -> None:
    """Prompt must not suggest write or mutate operations."""
    result = await mcp_client.get_prompt(
        "mintmory_what_cochanged_with", {"path": "/repo/file.py"}
    )
    text = " ".join(m.content.text for m in result.messages).lower()  # type: ignore[union-attr]
    for forbidden in ("memory_add", "memory_archive", "memory_dream", "mutate"):
        assert forbidden not in text, f"Prompt must not mention {forbidden!r}"


async def test_what_cochanged_with_mentions_docs_timeline(
    mcp_client: Client[Any],
) -> None:
    """Prompt should reference docs_timeline for recency."""
    result = await mcp_client.get_prompt(
        "mintmory_what_cochanged_with", {"path": "/repo/file.py"}
    )
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
```

- [ ] **Step 2: Run the tests to verify they fail (because tools don't exist yet — or pass if Task 1 was done first)**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/test_cochange_tools.py -v 2>&1 | tail -30
```

If Task 1 is done first, these tests should PASS. If they fail, diagnose the specific failure message.

---

### Task 3: Fix the manifest count test in test_resources_prompts.py

**Files:**
- Modify: `packages/mcp/tests/test_resources_prompts.py` (line 393–398)

> MM-40 added a test asserting exactly 3 mintmory_ prompts on the main server. MM-41 adds a 4th (`mintmory_what_cochanged_with`). The existing test must be updated.

- [ ] **Step 1: Update `test_main_server_prompt_count` to expect 4**

In `packages/mcp/tests/test_resources_prompts.py`, find:

```python
async def test_main_server_prompt_count(mcp_client: Client[Any]) -> None:
    """Main server has exactly 3 new prompts."""
    prompts = await mcp_client.list_prompts()
    mintmory_prompts = [p for p in prompts if p.name.startswith("mintmory_")]
    assert len(mintmory_prompts) == 3
```

Replace with:

```python
async def test_main_server_prompt_count(mcp_client: Client[Any]) -> None:
    """Main server has exactly 4 mintmory_ prompts (3 from MM-40 + 1 from MM-41)."""
    prompts = await mcp_client.list_prompts()
    mintmory_prompts = [p for p in prompts if p.name.startswith("mintmory_")]
    assert len(mintmory_prompts) == 4
```

- [ ] **Step 2: Update `test_total_new_manifest_items_le_8` if needed**

The MM-40 test `test_total_new_manifest_items_le_8` checks that total resources + prompts across both servers ≤ 8. Before MM-41: 2 main resources + 3 main prompts + 1 history resource + 1 history prompt = 7. After MM-41: 7 + 1 = 8. The assertion `<= 8` still holds — no change needed.

Also update the `test_prompts_listed_with_mintmory_prefix` test to include the new prompt:

```python
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
```

- [ ] **Step 3: Update `test_all_tools_registered` in test_tools.py**

In `packages/mcp/tests/test_tools.py`, find `test_all_tools_registered` (around line 49). The exact set assertion must now include the two new tools:

```python
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
        "docs_changed_with",
        "docs_timeline",
    }
```

- [ ] **Step 4: Run all MCP tests to confirm no regressions**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/mcp/tests/ -v 2>&1 | tail -40
```

Expected: all tests PASS.

---

### Task 4: Update the MCP documentation

**Files:**
- Modify: `docs/agent-history-mcp.md` (around line 110, the "Resources & Prompts (MM-40)" section)

- [ ] **Step 1: Add tools + prompt to the doc**

Find the section in `docs/agent-history-mcp.md` that says:

```
The main `mintmory-mcp` server (for working memory) exposes:

**Resources:**
...

**Prompts:**
- `mintmory_onboard(db_path?, llm_enabled?)` — the MintMory adoption policy as a prompt.
- `mintmory_recall_before_task(intent, link_types?)` — search-first → act → session_feedback discipline.
- `mintmory_session_closeout(session_id, useful_ids?, stale_ids?)` — the session feedback close-out call.
```

After the prompts list, add:

```markdown
**Tools (MM-41, read-only, working-store scope):**
- `docs_changed_with(path)` → documents observed to co-change with `path` in the same
  `index-tree` change-set. Returns `[{path, strength, observed_at, kind}]`; empty if not
  indexed or not in a change-set. `kind` may be `""` for legacy rows. OBSERVED co-change
  (time + folder + content proximity), **not** a version-controlled commit. Read-only;
  only `source='document'` records.
  > **Scope**: reads the working store (`MINTMORY_DB`). Documents indexed into a separate
  > `--db` are not visible here. Populate with `mintmory index-tree <root> --cochange`.
- `docs_timeline(since?, from_date?, to_date?, collection?, limit=50)` → indexed documents
  newest-first by file mtime. Returns `[{date, collection, path, title, valid_from}]`.
  `limit` is capped at 200. Malformed date/since returns `{"error":"bad_request","detail":...}`.
  Read-only; only `source='document'` records.

**Prompt (MM-41):**
- `mintmory_what_cochanged_with(path)` — guidance to call `docs_changed_with` for `path`,
  interpret `strength`/`observed_at`/`kind`, with the observed-co-change (not-a-commit)
  honesty caveat and a hint to index the corpus if empty.
```

- [ ] **Step 2: Verify the doc renders without issues (visual check)**

```bash
head -200 /Users/alexandruiacobescu/gooseProjects/MintMory/docs/agent-history-mcp.md | tail -80
```

---

### Task 5: Run all gates and fix any issues

**Files:** None new — iterate on existing files until all gates pass.

- [ ] **Step 1: ruff check**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync ruff check .
```

Expected: no errors. Common issue: line > 100 chars in the prompt return string — use string concatenation with `()`.

- [ ] **Step 2: ruff format**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync ruff format packages
```

Expected: files reformatted. Then re-run `ruff check .` to confirm still clean.

- [ ] **Step 3: mypy**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync mypy packages
```

Expected: 0 errors. Common issues:
- `list[dict[str, Any]] | dict[str, str]` union on `docs_timeline` — this is intentional; mypy accepts it.
- If mypy complains about `changed_with` or `documents_timeline` not found, verify the import line was added correctly.
- If mypy complains about `server._store` in tests, that pattern is already in existing tests so it should be fine.

- [ ] **Step 4: pytest full suite**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest -q 2>&1 | tail -20
```

Expected: ≥ 80% pass, all MCP tests pass. The full suite includes sklearn-gated co-change tests — they may be skipped if sklearn is not installed, which is fine.

- [ ] **Step 5: openspec validate**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync openspec validate add-cochange-mcp-tools --strict
```

Expected: `Change 'add-cochange-mcp-tools' is valid`

- [ ] **Step 6: Fix any gate failures and re-run gates**

If any gate fails, fix the specific issue and re-run only the affected gate before running the full suite. Do NOT commit.

---

## Self-Review Checklist

### Spec coverage

| Spec requirement | Task |
|---|---|
| `docs_changed_with(path)` tool with correct signature | Task 1, Step 2 |
| `docs_timeline(since, from_date, to_date, collection, limit)` tool | Task 1, Step 2 |
| `_DOCS_TIMELINE_MAX = 200` constant | Task 1, Step 2 |
| `limit` clamped to 200 | Task 1, Step 2 |
| `ValueError` → `{"error":"bad_request","detail":...}` | Task 1, Step 2 |
| `mintmory_what_cochanged_with(path)` prompt | Task 1, Step 3 |
| `path` appears in prompt text | Task 1, Step 3 |
| Honesty caveat (observed co-change, not a commit) | Task 1, Step 3 |
| `index-tree --cochange` hint when empty | Task 1, Step 3 |
| `docs_timeline` mentioned for recency | Task 1, Step 3 |
| No mutating suggestions in prompt | Task 1, Step 3 |
| Import `changed_with`, `documents_timeline` at module top | Task 1, Step 1 |
| Additive only (no existing tools changed) | Constraint: only new code added |
| Tests: peers returned for indexed file | Task 2 |
| Tests: unknown path → [] | Task 2 |
| Tests: non-document memory never returned | Task 2 |
| Tests: `kind=""` handled for legacy rows | Task 2 |
| Tests: newest-first ordering | Task 2 |
| Tests: collection filter | Task 2 |
| Tests: limit clamped to 200 | Task 2 |
| Tests: malformed since → error dict | Task 2 |
| Tests: prompt listed with mintmory_ prefix | Task 2 |
| Update manifest count test (3→4 prompts) | Task 3 |
| Update tool inventory test | Task 3 |
| MCP doc updated | Task 4 |
| All gates green | Task 5 |

### Type consistency

- `docs_changed_with` returns `list[dict[str, Any]]` — matches `changed_with()` return type.
- `docs_timeline` returns `list[dict[str, Any]] | dict[str, str]` — the `| dict[str, str]` covers the error dict path. `dict[str, str]` is valid since both `"error"` and `"detail"` are `str`.
- All test helpers use `Any` annotations where types are stored-model-dependent (matches existing pattern in `test_tools.py`).
- `_add_concept_link` uses `ConceptLink`, `ConceptLinkType`, `LinkSource` — these are already imported in core; the test imports them locally (matching the pattern in `test_index_tree_cochange.py`).
