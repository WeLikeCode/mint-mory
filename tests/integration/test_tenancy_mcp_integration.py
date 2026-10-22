"""Integration gate for the tenant-scoped MCP server (R9.2).

R3.2 (named scope is a hard boundary) and R4.2 (global scope spans tenants and
creates in ``global``) run against one real SQLite file path, switching the
process scope between the two phases. The database is reset between the phases
so each example starts from its own fresh corpus, exactly as the criteria
describe.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from mintmory.core.ports import StorageBackend
from mintmory.core.types import (
    TENANT_GLOBAL,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
    MemorySummary,
)
from mintmory.mcp import server
from mintmory.mcp.server import mcp


@pytest.fixture
def tenancy_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """One real SQLite file for the whole test; both module globals reset."""
    db_path = tmp_path / "tenancy_mcp.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    monkeypatch.setenv("MINTMORY_LINK_MIN_SHARED_ENTITIES", "1")
    monkeypatch.delenv("MINTMORY_MCP_TENANT", raising=False)
    server._store = None
    server._scope_tenant = TENANT_GLOBAL
    try:
        yield db_path
    finally:
        if server._store is not None:
            server._store.close()
        server._store = None
        server._scope_tenant = TENANT_GLOBAL


def _bootstrap(scope: str) -> None:
    bootstrap = getattr(server, "_bootstrap_scope", None)
    assert callable(bootstrap), "server._bootstrap_scope is required"
    bootstrap(scope)


def _tool(result: Any) -> Any:
    assert result is not None, "tool call returned no result object"
    return result


def _fresh_store(db_path: Path) -> StorageBackend:
    """Drop the previous phase's database rows and start a new adapter."""
    if server._store is not None:
        server._store.close()
    server._store = None
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)
    store = server._get_store()
    assert store is not None
    return store


def _add(store: StorageBackend, memory_id: str, content: str, tenant_id: str) -> None:
    record = store.add_memory(
        MemoryRecord(
            id=memory_id,
            content=content,
            category=MemoryCategory.FACT,
            source=MemorySource.AGENT,
            tenant_id=tenant_id,
        )
    )
    assert record is not None and record.id == memory_id


def _seed_core(store: StorageBackend) -> None:
    """R3.2 / R4.2 corpus: two global and two acme memories."""
    store.create_tenant("acme")
    _add(store, "g1", "Alice uses Postgres", TENANT_GLOBAL)
    _add(store, "g2", "Carol uses Postgres", TENANT_GLOBAL)
    _add(store, "a1", "Alice uses SQLite", "acme")
    _add(store, "a2", "Bob uses SQLite", "acme")


def _all_links(store: StorageBackend, memory_ids: list[str]) -> list[Any]:
    by_id: dict[str, Any] = {}
    for memory_id in memory_ids:
        links = store.get_links(memory_id)
        assert links is not None
        for link in links:
            by_id[link.id] = link
    return list(by_id.values())


@pytest.mark.l4("C-7b6a9a1f")
async def test_one_sqlite_file_switches_between_acme_and_global(
    tenancy_file: Path,
) -> None:
    async with Client(mcp) as client:
        # ---- Phase 1: R3.2 — named scope ``acme`` is a hard boundary ----
        store = _fresh_store(tenancy_file)
        _seed_core(store)
        _bootstrap("acme")

        search = _tool(await client.call_tool("memory_search", {"query": "Alice"})).data
        assert search.get("session_id"), "a named-scope search must open an acme session"
        assert {memory.get("id") for memory in search.get("memories", [])} == {"a1"}
        session = store.get_session(search.get("session_id", ""))
        assert session is not None
        assert session.tenant_id == "acme"

        foreign = _tool(await client.call_tool("memory_get", {"memory_id": "g1"}))
        assert foreign.data is None

        archived = _tool(await client.call_tool("memory_archive", {"memory_id": "g1"})).data
        assert archived.get("error") == "not_found"
        g1 = store.get_memory("g1")
        assert g1 is not None
        assert g1.is_active is True

        stats = _tool(await client.call_tool("memory_stats", {})).data
        assert stats.get("total_memories") == 2

        added = _tool(
            await client.call_tool(
                "memory_add", {"content": "A fresh acme fact about zebras", "category": "fact"}
            )
        ).data
        assert added.get("tenant_id") == "acme"

        feedback = _tool(
            await client.call_tool(
                "session_feedback",
                {"session_id": search.get("session_id", ""), "useful_ids": ["g1"]},
            )
        ).data
        assert feedback.get("error") == "conflict"
        g1 = store.get_memory("g1")
        assert g1 is not None
        assert g1.usefulness_score == 0.0
        concluded = store.get_session(search.get("session_id", ""))
        assert concluded is not None
        assert concluded.concluded is False

        dream = _tool(await client.call_tool("memory_dream", {"intensity": "light"})).data
        assert dream.get("new_links") == 1
        links = _all_links(store, ["g1", "g2", "a1", "a2"])
        assert {frozenset({link.source_memory_id, link.target_memory_id}) for link in links} == {
            frozenset({"a1", "a2"})
        }
        assert {link.tenant_id for link in links} == {"acme"}
        assert store.get_links("g1") == []
        assert store.get_links("g2") == []

        # ---- Phase 2: R4.2 — global scope spans tenants, creates in global ----
        store = _fresh_store(tenancy_file)
        _seed_core(store)
        _bootstrap("global")

        dream = _tool(await client.call_tool("memory_dream", {"intensity": "light"})).data
        assert dream.get("new_links") == 2
        links = _all_links(store, ["g1", "g2", "a1", "a2"])
        grouped: dict[str, set[frozenset[str]]] = {}
        for link in links:
            grouped.setdefault(link.tenant_id, set()).add(
                frozenset({link.source_memory_id, link.target_memory_id})
            )
        assert grouped == {
            TENANT_GLOBAL: {frozenset({"g1", "g2"})},
            "acme": {frozenset({"a1", "a2"})},
        }
        assert all(
            not ({"g1", "a1"} <= {link.source_memory_id, link.target_memory_id}) for link in links
        )

        search = _tool(await client.call_tool("memory_search", {"query": "Alice"})).data
        assert {memory.get("id") for memory in search.get("memories", [])} == {"g1", "a1"}

        got = _tool(await client.call_tool("memory_get", {"memory_id": "a1"})).data
        assert got.get("id") == "a1"
        assert got.get("tenant_id") == "acme"

        note = _tool(
            await client.call_tool("memory_note", {"content": "check index", "about": "SQLite"})
        ).data
        assert note.get("note", {}).get("tenant_id") == TENANT_GLOBAL
        assert note.get("anchor_memory_id") != "a1"

        store.upsert_summary(
            MemorySummary(
                concept="bob",
                summary_text="acme bob",
                memory_count=1,
                tenant_id="acme",
            )
        )
        summary = _tool(
            await client.call_tool(
                "summary_put", {"concept": "alice", "summary_text": "global alice summary"}
            )
        ).data
        assert summary.get("tenant_id") == TENANT_GLOBAL
        assert summary.get("memory_count") == 1

        fetched = _tool(await client.call_tool("summary_get", {"concept": "alice"})).data
        assert fetched.get("summary_text") == "global alice summary"

        listed = _tool(await client.call_tool("summary_list", {})).data
        assert {row.get("tenant_id") for row in listed} == {TENANT_GLOBAL, "acme"}
        assert (TENANT_GLOBAL, "alice") in {
            (row.get("tenant_id"), row.get("concept")) for row in listed
        }

        archived = _tool(await client.call_tool("memory_archive", {"memory_id": "a1"})).data
        assert archived.get("archived") is True
        a1 = store.get_memory("a1")
        assert a1 is not None
        assert a1.tenant_id == "acme"
        assert a1.is_archived is True
