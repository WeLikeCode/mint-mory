"""RED tests for task 3 — MCP dreaming and summary transports on a multi-tenant DB.

They trace requirement 3.1 (``memory_dream`` dreams every tenant through
``run_dream``), 3.2 (the tool still returns a ``DreamReport``, the per-tenant
total), 3.3 (``DreamFailedError`` surfaces as a ``ToolError``), 4.1
(``summary_jobs`` / ``summary_put`` stay on the global tenant) and 4.2 (the image
path relies on the core ``global`` defaults).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mintmory.core.dreaming import DreamingEngine
from mintmory.core.ports import StorageBackend
from mintmory.core.types import (
    ConceptLink,
    DreamReport,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
)
from mintmory.mcp import server
from mintmory.mcp.server import mcp


@pytest.fixture
async def mcp_client(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Client[Any]]:
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
            tenant_id=tenant_id,
            **fields,
        )
    )


def _seed_two_tenants(store: StorageBackend) -> None:
    store.create_tenant("t1")
    _add(store, "g1", "Alice works at Acme", "global")
    _add(store, "g2", "Bob works at Acme", "global")
    _add(store, "a1", "Alice works at Acme", "t1")
    _add(store, "a2", "Carol works at Acme", "t1")
    _add(store, "a3", "Dan works at Acme", "t1")


def _seed_summary_tenants(store: StorageBackend) -> None:
    store.create_tenant("t1")
    for index in range(3):
        _add(
            store,
            f"g{index}",
            f"Global {index} fact",
            "global",
            entity_ids=["globalconcept"],
        )
        _add(
            store,
            f"a{index}",
            f"Tenant {index} fact",
            "t1",
            entity_ids=["tenantconcept"],
        )


def _all_links(store: StorageBackend, memory_ids: list[str]) -> list[ConceptLink]:
    by_id: dict[str, ConceptLink] = {}
    for memory_id in memory_ids:
        for link in store.get_links(memory_id):
            by_id[link.id] = link
    return list(by_id.values())


@pytest.mark.l4("C-7881686c", "C-d9c39ea3")
async def test_memory_dream_runs_each_tenant_without_cross_tenant_links(
    mcp_client: Client[Any],
) -> None:
    store = server._get_store()
    _seed_two_tenants(store)

    try:
        res = await mcp_client.call_tool("memory_dream", {"intensity": "light"})
    except ToolError as exc:
        raise AssertionError(f"memory_dream must not fail on a multi-tenant DB: {exc}") from exc

    report = DreamReport(**res.data)
    assert report.intensity.value == "light"
    assert report.new_links == 4

    grouped: dict[str, set[frozenset[str]]] = defaultdict(set)
    for link in _all_links(store, ["g1", "g2", "a1", "a2", "a3"]):
        grouped[link.tenant_id].add(frozenset({link.source_memory_id, link.target_memory_id}))
    assert grouped == {
        "global": {frozenset({"g1", "g2"})},
        "t1": {
            frozenset({"a1", "a2"}),
            frozenset({"a1", "a3"}),
            frozenset({"a2", "a3"}),
        },
    }


@pytest.mark.l4("C-63860dbc")
async def test_memory_dream_failure_surfaces_as_a_tool_error(
    mcp_client: Client[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: DreamingEngine) -> DreamReport:
        raise RuntimeError("boom")

    monkeypatch.setattr(DreamingEngine, "run_light", boom)
    monkeypatch.setattr(DreamingEngine, "run_full", boom)

    with pytest.raises(ToolError) as exc_info:
        await mcp_client.call_tool("memory_dream", {"intensity": "light"})

    assert "dreaming failed for tenant(s): global (RuntimeError: boom)" in str(exc_info.value)


@pytest.mark.l4("C-a0213e6c")
async def test_summary_paths_stay_on_the_global_tenant(mcp_client: Client[Any]) -> None:
    store = server._get_store()
    _seed_summary_tenants(store)

    jobs = await mcp_client.call_tool("summary_jobs", {})
    assert [job["concept"] for job in jobs.data] == ["globalconcept"]

    put = await mcp_client.call_tool(
        "summary_put", {"concept": "tenantconcept", "summary_text": "Global only."}
    )
    assert put.data["memory_count"] == 0
    assert store.get_summary("tenantconcept", "global") is not None
    assert store.get_summary("tenantconcept", "t1") is None


@pytest.mark.l4("C-051abf8f")
async def test_image_jobs_use_the_global_default(
    mcp_client: Client[Any],
) -> None:
    store = server._get_store()
    store.create_tenant("t1")
    for memory_id, tenant_id, rel in (
        ("img-global", "global", "global.png"),
        ("img-tenant", "t1", "tenant.png"),
    ):
        store.add_memory(
            MemoryRecord(
                id=memory_id,
                content=f"Image file: {rel}",
                category=MemoryCategory.CONTEXT,
                source=MemorySource.DOCUMENT,
                tenant_id=tenant_id,
                metadata={
                    "collection": "test",
                    "path": f"/fake/{rel}",
                    "rel": rel,
                    "ext": ".png",
                    "size": 1024,
                    "mtime": 1_700_000_000.0,
                    "online_only": False,
                    "folder": ".",
                    "index_mode": "metadata",
                },
            )
        )

    jobs = await mcp_client.call_tool("image_jobs", {})

    assert [job["file_id"] for job in jobs.data] == ["img-global"]
