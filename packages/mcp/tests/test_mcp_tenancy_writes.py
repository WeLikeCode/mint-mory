"""RED tests for task 3 — create, modify and dream tools carry the process scope.

Every test drives the real fastmcp in-memory ``Client`` so it exercises tool
registration and serialisation as well as the tenant wiring. The small-store
link override (``MINTMORY_LINK_MIN_SHARED_ENTITIES=1``) is the same one the core
tenancy tests use: with the production default of two shared entities the R3.2 /
R4.2 example memories would share only one and no link would ever be proposed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mintmory.core import notes as core_notes
from mintmory.core import session as core_session
from mintmory.core import vision as vision_mod
from mintmory.core.llm import build_dreaming_engine as core_build_dreaming_engine
from mintmory.core.ports import StorageBackend
from mintmory.core.types import (
    CaptionRunReport,
    DreamIntensity,
    DreamReport,
    ImageDescription,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
    QuerySession,
)
from mintmory.mcp import server
from mintmory.mcp.server import mcp


@pytest.fixture
async def mcp_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Client[Any]]:
    """In-memory client on an isolated DB; the scope is reset on teardown."""
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "tenancy-writes.db"))
    monkeypatch.setenv("MINTMORY_LINK_MIN_SHARED_ENTITIES", "1")
    monkeypatch.delenv("MINTMORY_MCP_TENANT", raising=False)
    server._store = None
    server._scope_tenant = "global"
    try:
        async with Client(mcp) as client:
            yield client
    finally:
        if server._store is not None:
            server._store.close()
        server._store = None
        server._scope_tenant = "global"


@pytest.fixture
async def acme_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client[Any]]:
    """Client whose process scope is the existing tenant ``acme``."""
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "tenancy-writes-acme.db"))
    monkeypatch.setenv("MINTMORY_LINK_MIN_SHARED_ENTITIES", "1")
    monkeypatch.delenv("MINTMORY_MCP_TENANT", raising=False)
    server._store = None
    server._scope_tenant = "global"
    store = server._get_store()
    store.create_tenant("acme")
    server._bootstrap_scope("acme")
    try:
        async with Client(mcp) as client:
            yield client
    finally:
        if server._store is not None:
            server._store.close()
        server._store = None
        server._scope_tenant = "global"


def _add(
    store: StorageBackend,
    memory_id: str,
    content: str,
    tenant_id: str,
    **fields: Any,
) -> MemoryRecord:
    return store.add_memory(
        MemoryRecord(
            id=memory_id,
            content=content,
            category=MemoryCategory.FACT,
            source=MemorySource.AGENT,
            tenant_id=tenant_id,
            **fields,
        )
    )


def _seed_core(store: StorageBackend) -> None:
    """The R3.2 / R4.2 corpus: two global and two acme memories."""
    store.create_tenant("acme")
    _add(store, "g1", "Alice uses Postgres", "global")
    _add(store, "g2", "Carol uses Postgres", "global")
    _add(store, "a1", "Alice uses SQLite", "acme")
    _add(store, "a2", "Bob uses SQLite", "acme")


def _all_links(store: StorageBackend, memory_ids: list[str]) -> list[Any]:
    by_id: dict[str, Any] = {}
    for memory_id in memory_ids:
        for link in store.get_links(memory_id):
            by_id[link.id] = link
    return list(by_id.values())


def _seed_image(store: StorageBackend, path: Path, tenant_id: str) -> str:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    memory_id = f"img-{tenant_id}"
    store.add_memory(
        MemoryRecord(
            id=memory_id,
            content=f"Image file: {path.name}",
            category=MemoryCategory.CONTEXT,
            source=MemorySource.DOCUMENT,
            tenant_id=tenant_id,
            metadata={
                "collection": "tenancy",
                "path": str(path),
                "rel": path.name,
                "ext": ".png",
                "size": path.stat().st_size,
                "online_only": False,
                "folder": ".",
                "index_mode": "metadata",
            },
        )
    )
    return memory_id


def _spy(seen: dict[str, dict[str, Any]], name: str, original: Any) -> Any:
    """Record one call's args/kwargs, then delegate to ``original``."""

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen[name] = {"args": args, "kwargs": kwargs}
        return original(*args, **kwargs)

    return spy


def _tenant_kw(call: dict[str, Any]) -> Any:
    return call["kwargs"].get("tenant_id", "<missing>")


# ---------------------------------------------------------------------------
# R2.1 — every create / modify / dream tool passes the resolved tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3a9634d3")
async def test_create_modify_and_dream_tools_pass_the_resolved_tenant(
    mcp_client: Client[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    store = server._get_store()
    store.create_tenant("acme")
    seen: dict[str, dict[str, Any]] = {}

    for scope, effective, stamp in (("global", None, "global"), ("acme", "acme", "acme")):
        seen.clear()

        monkeypatch.setattr(store, "add_memory", _spy(seen, "add_memory", store.add_memory))
        monkeypatch.setattr(
            store, "archive_memory", _spy(seen, "archive_memory", store.archive_memory)
        )

        def fake_feedback(*args: Any, **kwargs: Any) -> QuerySession:
            seen["apply_feedback"] = {"args": args, "kwargs": kwargs}
            return QuerySession(id="fake-session", query_text="q")

        monkeypatch.setattr(core_session, "apply_feedback", fake_feedback)
        monkeypatch.setattr(
            server,
            "build_dreaming_engine",
            _spy(seen, "build_dreaming_engine", core_build_dreaming_engine),
        )
        monkeypatch.setattr(
            core_notes, "create_note", _spy(seen, "create_note", core_notes.create_note)
        )

        def fake_image_jobs(*args: Any, **kwargs: Any) -> list[Any]:
            seen["image_jobs"] = {"args": args, "kwargs": kwargs}
            return []

        def fake_caption_put(*args: Any, **kwargs: Any) -> ImageDescription:
            seen["image_caption_put"] = {"args": args, "kwargs": kwargs}
            return ImageDescription(
                record=MemoryRecord(content="description", category=MemoryCategory.CONTEXT),
                file_id="img",
                source_image="/img.png",
            )

        def fake_caption_run(*args: Any, **kwargs: Any) -> CaptionRunReport:
            seen["caption_pending_images"] = {"args": args, "kwargs": kwargs}
            return CaptionRunReport(provider="llm", described=1)

        monkeypatch.setattr(vision_mod, "image_jobs", fake_image_jobs)
        monkeypatch.setattr(vision_mod, "image_caption_put", fake_caption_put)
        monkeypatch.setattr(vision_mod, "captioner_from_settings", lambda settings: object())
        monkeypatch.setattr(vision_mod, "caption_pending_images", fake_caption_run)

        def fake_run_dream(*args: Any, **kwargs: Any) -> DreamReport:
            seen["run_dream"] = {"args": args, "kwargs": kwargs}
            return DreamReport(intensity=DreamIntensity(kwargs["intensity"]), duration_ms=0.0)

        monkeypatch.setattr(server, "run_dream", fake_run_dream)

        server._bootstrap_scope(scope)

        added = await mcp_client.call_tool(
            "memory_add", {"content": f"{scope} fact", "category": "fact"}
        )
        assert added.data["tenant_id"] == stamp
        assert seen["add_memory"]["kwargs"]["record"].tenant_id == stamp

        await mcp_client.call_tool("memory_archive", {"memory_id": "missing"})
        assert _tenant_kw(seen["archive_memory"]) == effective

        await mcp_client.call_tool("session_feedback", {"session_id": "fake-session"})
        assert _tenant_kw(seen["apply_feedback"]) == effective

        await mcp_client.call_tool("summary_jobs", {})
        assert _tenant_kw(seen["build_dreaming_engine"]) == stamp

        await mcp_client.call_tool("summary_put", {"concept": "zzz", "summary_text": "text"})
        assert _tenant_kw(seen["build_dreaming_engine"]) == stamp

        await mcp_client.call_tool("memory_note", {"content": f"{scope} note"})
        assert _tenant_kw(seen["create_note"]) == stamp

        await mcp_client.call_tool("image_jobs", {})
        assert _tenant_kw(seen["image_jobs"]) == stamp

        await mcp_client.call_tool(
            "image_caption_put", {"file_id_or_path": "img", "description": "text"}
        )
        assert _tenant_kw(seen["image_caption_put"]) == stamp

        await mcp_client.call_tool("vision_run", {})
        assert _tenant_kw(seen["caption_pending_images"]) == stamp

        await mcp_client.call_tool("memory_dream", {"intensity": "light"})
        assert _tenant_kw(seen["run_dream"]) == effective


# ---------------------------------------------------------------------------
# R2.3 — a TenantError raised in a tool surfaces as a fastmcp tool error
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-64910e2d")
async def test_tenant_error_from_a_tool_surfaces_as_a_tool_error(
    mcp_client: Client[Any],
) -> None:
    store = server._get_store()
    store.create_tenant("acme")
    _add(store, "a1", "Alice uses SQLite", "acme")
    server._bootstrap_scope("acme")
    store.set_tenant_active("acme", False)

    with pytest.raises(ToolError) as exc_info:
        await mcp_client.call_tool("memory_add", {"content": "blocked", "category": "fact"})
    assert "tenant 'acme' is inactive (read-only)" in str(exc_info.value)


# ---------------------------------------------------------------------------
# R3.1 — a named scope confines every write and hides foreign ids
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-8b67e092")
async def test_named_scope_writes_are_stamped_and_foreign_ids_are_not_found(
    acme_client: Client[Any],
) -> None:
    store = server._get_store()
    _seed_core(store)

    added = await acme_client.call_tool(
        "memory_add", {"content": "Tenant-only fact about zebras", "category": "fact"}
    )
    assert added.data["tenant_id"] == "acme"

    note = await acme_client.call_tool(
        "memory_note", {"content": "Tenant-only note", "about": "zebras"}
    )
    assert note.data["note"]["tenant_id"] == "acme"

    summary = await acme_client.call_tool(
        "summary_put", {"concept": "alice", "summary_text": "acme only"}
    )
    assert summary.data["tenant_id"] == "acme"
    assert store.get_summary("alice", "acme") is not None
    assert store.get_summary("alice", "global") is None

    archived = await acme_client.call_tool("memory_archive", {"memory_id": "g1"})
    assert archived.data.get("error") == "not_found"
    g1 = store.get_memory("g1")
    assert g1 is not None
    assert g1.is_active is True
    assert g1.is_archived is False


# ---------------------------------------------------------------------------
# R3.2 — the named-scope example end to end
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-8f404a82")
async def test_named_scope_scenario_reads_writes_and_dream_stay_in_tenant(
    acme_client: Client[Any],
) -> None:
    store = server._get_store()
    _seed_core(store)

    search = await acme_client.call_tool("memory_search", {"query": "Alice"})
    assert {memory["id"] for memory in search.data["memories"]} == {"a1"}
    query_session = store.get_session(search.data["session_id"])
    assert query_session is not None
    assert query_session.tenant_id == "acme"

    foreign = await acme_client.call_tool("memory_get", {"memory_id": "g1"})
    assert foreign.data is None

    stats = await acme_client.call_tool("memory_stats", {})
    assert stats.data["total_memories"] == 2

    feedback = await acme_client.call_tool(
        "session_feedback",
        {"session_id": search.data["session_id"], "useful_ids": ["g1"]},
    )
    assert feedback.data.get("error") == "conflict"
    g1 = store.get_memory("g1")
    assert g1 is not None
    assert g1.usefulness_score == 0.0
    concluded = store.get_session(search.data["session_id"])
    assert concluded is not None
    assert concluded.concluded is False

    report = await acme_client.call_tool("memory_dream", {"intensity": "light"})
    assert report.data["new_links"] == 1
    links = _all_links(store, ["g1", "g2", "a1", "a2"])
    assert {frozenset({link.source_memory_id, link.target_memory_id}) for link in links} == {
        frozenset({"a1", "a2"})
    }
    assert {link.tenant_id for link in links} == {"acme"}
    assert store.get_links("g1") == []
    assert store.get_links("g2") == []

    added = await acme_client.call_tool(
        "memory_add", {"content": "A brand new acme fact", "category": "fact"}
    )
    assert added.data["tenant_id"] == "acme"

    archived = await acme_client.call_tool("memory_archive", {"memory_id": "g1"})
    assert archived.data.get("error") == "not_found"
    g1_after = store.get_memory("g1")
    assert g1_after is not None
    assert g1_after.is_active is True


# ---------------------------------------------------------------------------
# R4.1 — the global scope spans reads, stamps global creates, keeps rows put
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-38da7fdc", "C-8b67e092")
async def test_global_scope_reads_span_tenants_and_creates_stay_global(
    mcp_client: Client[Any],
) -> None:
    store = server._get_store()
    _seed_core(store)
    server._bootstrap_scope("global")

    search = await mcp_client.call_tool("memory_search", {"query": "Alice"})
    assert {memory["id"] for memory in search.data["memories"]} == {"g1", "a1"}

    got = await mcp_client.call_tool("memory_get", {"memory_id": "a1"})
    assert got.data["id"] == "a1"
    assert got.data["tenant_id"] == "acme"

    added = await mcp_client.call_tool(
        "memory_add", {"content": "A global fact about zebras", "category": "fact"}
    )
    assert added.data["tenant_id"] == "global"

    note = await mcp_client.call_tool("memory_note", {"content": "check index", "about": "SQLite"})
    assert note.data["note"]["tenant_id"] == "global"
    assert note.data["anchor_memory_id"] != "a1"

    summary = await mcp_client.call_tool(
        "summary_put", {"concept": "alice", "summary_text": "global alice"}
    )
    assert summary.data["tenant_id"] == "global"

    archived = await mcp_client.call_tool("memory_archive", {"memory_id": "a1"})
    assert archived.data["archived"] is True
    a1 = store.get_memory("a1")
    assert a1 is not None
    assert a1.tenant_id == "acme"
    assert a1.is_archived is True

    server._bootstrap_scope("acme")
    tenant_added = await mcp_client.call_tool(
        "memory_add", {"content": "A tenant-only fact", "category": "fact"}
    )
    assert tenant_added.data["tenant_id"] == "acme"

    tenant_note = await mcp_client.call_tool("memory_note", {"content": "tenant note"})
    assert tenant_note.data["note"]["tenant_id"] == "acme"

    tenant_summary = await mcp_client.call_tool(
        "summary_put", {"concept": "bob", "summary_text": "acme bob"}
    )
    assert tenant_summary.data["tenant_id"] == "acme"


# ---------------------------------------------------------------------------
# R4.2 — the global-scope example end to end
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-8d39f34c", "C-8b67e092")
async def test_global_scope_scenario_spans_tenants_and_dreams_each(
    mcp_client: Client[Any],
) -> None:
    store = server._get_store()
    _seed_core(store)
    server._bootstrap_scope("global")

    report = await mcp_client.call_tool("memory_dream", {"intensity": "light"})
    assert report.data["new_links"] == 2
    links = _all_links(store, ["g1", "g2", "a1", "a2"])
    grouped: dict[str, set[frozenset[str]]] = {}
    for link in links:
        grouped.setdefault(link.tenant_id, set()).add(
            frozenset({link.source_memory_id, link.target_memory_id})
        )
    assert grouped == {
        "global": {frozenset({"g1", "g2"})},
        "acme": {frozenset({"a1", "a2"})},
    }
    assert all(
        "g1" not in {link.source_memory_id, link.target_memory_id}
        or "a1" not in {link.source_memory_id, link.target_memory_id}
        for link in links
    )

    search = await mcp_client.call_tool("memory_search", {"query": "Alice"})
    assert {memory["id"] for memory in search.data["memories"]} == {"g1", "a1"}

    got = await mcp_client.call_tool("memory_get", {"memory_id": "a1"})
    assert got.data["id"] == "a1"

    archived = await mcp_client.call_tool("memory_archive", {"memory_id": "a1"})
    assert archived.data["archived"] is True
    a1 = store.get_memory("a1")
    assert a1 is not None
    assert a1.is_archived is True
    assert a1.tenant_id == "acme"

    note = await mcp_client.call_tool("memory_note", {"content": "check index", "about": "SQLite"})
    assert note.data["note"]["tenant_id"] == "global"
    assert note.data["anchor_memory_id"] != "a1"

    summary = await mcp_client.call_tool(
        "summary_put", {"concept": "alice", "summary_text": "global alice summary"}
    )
    assert summary.data["tenant_id"] == "global"
    assert summary.data["memory_count"] == 1

    fetched = await mcp_client.call_tool("summary_get", {"concept": "alice"})
    assert fetched.data["summary_text"] == "global alice summary"

    listed = await mcp_client.call_tool("summary_list", {})
    assert {row["tenant_id"] for row in listed.data} == {"global"}
    assert [(row["tenant_id"], row["concept"]) for row in listed.data] == [("global", "alice")]

    server._bootstrap_scope("acme")
    stats = await mcp_client.call_tool("memory_stats", {})
    assert stats.data["total_memories"] == 2
    assert stats.data["archived"] == 1

    tenant_added = await mcp_client.call_tool(
        "memory_add", {"content": "A tenant-only fact", "category": "fact"}
    )
    assert tenant_added.data["tenant_id"] == "acme"


# ---------------------------------------------------------------------------
# R8.1 — a deactivated named scope keeps reads, refuses writes
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-e9fa90c0")
async def test_deactivated_named_scope_serves_reads_and_writes_raise(
    mcp_client: Client[Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = server._get_store()
    store.create_tenant("acme")
    _add(store, "a1", "Alice uses SQLite", "acme")
    _add(store, "a2", "Bob uses SQLite", "acme")
    _add(store, "a3", "Carol uses SQLite", "acme")
    image_id = _seed_image(store, tmp_path / "acme.png", "acme")

    server._bootstrap_scope("acme")
    before = await mcp_client.call_tool("memory_search", {"query": "Alice"})
    session_id = before.data["session_id"]
    assert session_id != ""

    store.set_tenant_active("acme", False)

    got = await mcp_client.call_tool("memory_get", {"memory_id": "a1"})
    assert got.data["id"] == "a1"

    search = await mcp_client.call_tool("memory_search", {"query": "Alice"})
    assert "a1" in {memory["id"] for memory in search.data["memories"]}
    assert search.data["session_id"] == ""

    jobs = await mcp_client.call_tool("summary_jobs", {})
    assert "sqlite" in {job["concept"] for job in jobs.data}

    images = await mcp_client.call_tool("image_jobs", {})
    assert [job["file_id"] for job in images.data] == [image_id]

    with pytest.raises(ToolError):
        await mcp_client.call_tool("memory_add", {"content": "blocked", "category": "fact"})
    with pytest.raises(ToolError):
        await mcp_client.call_tool("memory_archive", {"memory_id": "a1"})
    with pytest.raises(ToolError):
        await mcp_client.call_tool("session_feedback", {"session_id": session_id})
    with pytest.raises(ToolError):
        await mcp_client.call_tool("summary_put", {"concept": "sqlite", "summary_text": "blocked"})
    with pytest.raises(ToolError):
        await mcp_client.call_tool("memory_note", {"content": "blocked"})
    with pytest.raises(ToolError):
        await mcp_client.call_tool(
            "image_caption_put", {"file_id_or_path": image_id, "description": "blocked"}
        )

    class _FakeDescription:
        def __init__(self) -> None:
            self.record = MemoryRecord(content="described", category=MemoryCategory.CONTEXT)

    class _FakeCaptioner:
        def describe(self, image: Any) -> _FakeDescription:
            return _FakeDescription()

    monkeypatch.setattr(vision_mod, "captioner_from_settings", lambda settings: _FakeCaptioner())
    with pytest.raises(ToolError):
        await mcp_client.call_tool("vision_run", {})

    with pytest.raises(ToolError) as dream_error:
        await mcp_client.call_tool("memory_dream", {"intensity": "light"})
    assert "tenant 'acme' is inactive (read-only)" in str(dream_error.value)
    assert "dreaming failed for tenant(s)" not in str(dream_error.value)


# ---------------------------------------------------------------------------
# R8.2 — global modifications of an inactive tenant's row change nothing
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3d329b68", "C-e9fa90c0")
async def test_global_scope_modification_of_inactive_tenant_row_is_rejected(
    mcp_client: Client[Any],
) -> None:
    store = server._get_store()
    store.create_tenant("acme")
    _add(store, "a1", "Alice uses SQLite", "acme")
    store.create_session(QuerySession(id="global-session", query_text="Alice", tenant_id="global"))

    server._bootstrap_scope("global")
    store.set_tenant_active("acme", False)

    with pytest.raises(ToolError) as archive_error:
        await mcp_client.call_tool("memory_archive", {"memory_id": "a1"})
    assert "tenant 'acme' is inactive" in str(archive_error.value)
    a1 = store.get_memory("a1")
    assert a1 is not None
    assert a1.is_active is True
    assert a1.is_archived is False

    with pytest.raises(ToolError) as feedback_error:
        await mcp_client.call_tool(
            "session_feedback", {"session_id": "global-session", "useful_ids": ["a1"]}
        )
    assert "tenant 'acme' is inactive" in str(feedback_error.value)
    a1 = store.get_memory("a1")
    assert a1 is not None
    assert a1.usefulness_score == 0.0
    assert a1.reinforcement_count == 0
    session = store.get_session("global-session")
    assert session is not None
    assert session.concluded is False

    server._bootstrap_scope("acme")
    with pytest.raises(ToolError):
        await mcp_client.call_tool("memory_add", {"content": "blocked", "category": "fact"})
