"""RED tests for task 4 — the tenant directory tools and the tenant inventory.

Covers ``TOOL_TENANT_SCOPE`` (R2.2), ``tenant_create`` (R5.1), ``tenant_list``
(R5.2), the R5.3 scenarios, the no-per-call-tenant-override schema scan (R6.1)
and concurrent tenant creation (R8.3). Tests that need the new tools assert the
declared inventory first, so the missing implementation fails as an assertion.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mintmory.core.ports import StorageBackend
from mintmory.mcp import server
from mintmory.mcp.server import mcp

_TENANT_KEYS = {"id", "name", "is_active", "created_at", "updated_at"}


@pytest.fixture
async def directory_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client[Any]]:
    """In-memory client on an isolated DB in the global scope."""
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "tenancy-directory.db"))
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
async def acme_directory_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client[Any]]:
    """In-memory client whose process scope is the existing tenant ``acme``."""
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "tenancy-directory-acme.db"))
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


def _declared_scope() -> dict[str, str]:
    """The declared tenant-scope inventory; fails as an assertion while absent."""
    declared = getattr(server, "TOOL_TENANT_SCOPE", None)
    assert isinstance(declared, dict), "server.py must define TOOL_TENANT_SCOPE"
    return cast(dict[str, str], declared)


def _store() -> StorageBackend:
    return server._get_store()


# ---------------------------------------------------------------------------
# R2.2 — the inventory covers every registered tool and its kind
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-6530b3da")
async def test_tool_inventory_matches_declared_tenant_scope(
    directory_client: Client[Any],
) -> None:
    expected = {
        "memory_add": "create",
        "memory_get": "read",
        "memory_search": "read",
        "memory_dream": "dream",
        "memory_stats": "read",
        "session_feedback": "modify",
        "memory_archive": "modify",
        "summary_list": "read",
        "summary_get": "read",
        "summary_jobs": "create",
        "summary_put": "create",
        "memory_note": "create",
        "notes_list": "read",
        "docs_changed_with": "read",
        "docs_timeline": "read",
        "image_jobs": "create",
        "image_caption_put": "create",
        "vision_run": "create",
        "tenant_create": "directory",
        "tenant_list": "directory",
    }
    declared = _declared_scope()
    names = {tool.name for tool in await directory_client.list_tools()}

    assert names == set(declared)
    assert declared == expected
    assert set(declared.values()) == {"read", "create", "modify", "dream", "directory"}
    assert {"tenant_create", "tenant_list"} <= names


# ---------------------------------------------------------------------------
# R5.1 / R5.3 — tenant_create
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-606a0944", "C-d8d0a9d2")
async def test_tenant_create_in_global_scope_returns_the_stored_tenant(
    directory_client: Client[Any],
) -> None:
    assert _declared_scope()["tenant_create"] == "directory"
    store = _store()
    assert store.get_tenant("acme") is None

    result = await directory_client.call_tool(
        "tenant_create", {"tenant_id": "acme", "name": "Acme Inc"}
    )

    stored = store.get_tenant("acme")
    assert stored is not None
    assert result.data == stored.model_dump(mode="json")
    assert result.data["id"] == "acme"
    assert result.data["name"] == "Acme Inc"
    assert result.data["is_active"] is True
    assert set(result.data) == _TENANT_KEYS
    assert server._scope_tenant == "global"


@pytest.mark.l4("C-606a0944", "C-d8d0a9d2")
async def test_tenant_create_in_named_scope_does_not_change_the_scope(
    acme_directory_client: Client[Any],
) -> None:
    assert _declared_scope()["tenant_create"] == "directory"
    assert server._scope_tenant == "acme"

    result = await acme_directory_client.call_tool(
        "tenant_create", {"tenant_id": "beta", "name": "Beta LLC"}
    )

    assert result.data["id"] == "beta"
    assert result.data["name"] == "Beta LLC"
    assert _store().get_tenant("beta") is not None
    assert server._scope_tenant == "acme"
    assert server._effective_tenant() == "acme"


@pytest.mark.l4("C-606a0944", "C-d8d0a9d2")
async def test_tenant_create_is_idempotent_and_keeps_the_existing_row(
    directory_client: Client[Any],
) -> None:
    assert _declared_scope()["tenant_create"] == "directory"

    first = await directory_client.call_tool(
        "tenant_create", {"tenant_id": "acme", "name": "First Name"}
    )
    second = await directory_client.call_tool(
        "tenant_create", {"tenant_id": "acme", "name": "Second Name"}
    )

    assert second.data == first.data
    assert second.data["name"] == "First Name"
    matching = [tenant for tenant in _store().list_tenants() if tenant.id == "acme"]
    assert len(matching) == 1
    assert matching[0].name == "First Name"


@pytest.mark.l4("C-606a0944", "C-d8d0a9d2")
async def test_tenant_create_invalid_id_surfaces_as_a_tool_error(
    directory_client: Client[Any],
) -> None:
    assert _declared_scope()["tenant_create"] == "directory"

    with pytest.raises(ToolError) as exc_info:
        await directory_client.call_tool("tenant_create", {"tenant_id": "Bad"})

    assert "invalid tenant id" in str(exc_info.value)
    assert _store().get_tenant("Bad") is None
    assert server._scope_tenant == "global"


# ---------------------------------------------------------------------------
# R5.2 / R5.3 — tenant_list
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-294c313a", "C-d8d0a9d2")
async def test_tenant_list_returns_every_tenant_in_global_scope(
    directory_client: Client[Any],
) -> None:
    assert _declared_scope()["tenant_list"] == "directory"
    store = _store()
    store.create_tenant("acme", "Acme Inc")
    store.create_tenant("beta", "Beta LLC")

    result = await directory_client.call_tool("tenant_list", {})

    rows = result.data
    assert {row["id"] for row in rows} == {tenant.id for tenant in store.list_tenants()}
    assert {"acme", "beta", "global"} <= {row["id"] for row in rows}
    assert all(set(row) == _TENANT_KEYS for row in rows)
    acme = next(row for row in rows if row["id"] == "acme")
    assert acme["name"] == "Acme Inc"
    assert acme["is_active"] is True
    assert server._scope_tenant == "global"


@pytest.mark.l4("C-294c313a", "C-d8d0a9d2")
async def test_tenant_list_returns_every_tenant_in_named_scope(
    acme_directory_client: Client[Any],
) -> None:
    assert _declared_scope()["tenant_list"] == "directory"
    store = _store()
    store.create_tenant("beta", "Beta LLC")

    result = await acme_directory_client.call_tool("tenant_list", {})

    rows = result.data
    assert {row["id"] for row in rows} == {tenant.id for tenant in store.list_tenants()}
    assert {"acme", "beta", "global"} <= {row["id"] for row in rows}
    assert all(set(row) == _TENANT_KEYS for row in rows)
    assert server._scope_tenant == "acme"


# ---------------------------------------------------------------------------
# R6.1 — no per-call scope override
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-aa92a5b1")
async def test_no_tool_exposes_a_tenant_selector(directory_client: Client[Any]) -> None:
    assert _declared_scope()["tenant_create"] == "directory"
    tools = await directory_client.list_tools()

    tenant_properties: dict[str, set[str]] = {}
    for tool in tools:
        properties = set(tool.inputSchema.get("properties", {}))
        selected = {name for name in properties if "tenant" in name}
        if selected:
            tenant_properties[tool.name] = selected

    assert tenant_properties == {"tenant_create": {"tenant_id"}}


# ---------------------------------------------------------------------------
# R8.3 — concurrent creation yields one row and there is no delete API
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-c92a2d86")
async def test_concurrent_tenant_create_returns_the_same_single_row(
    directory_client: Client[Any],
) -> None:
    assert _declared_scope()["tenant_create"] == "directory"

    first, second = await asyncio.gather(
        directory_client.call_tool("tenant_create", {"tenant_id": "acme", "name": "Acme"}),
        directory_client.call_tool("tenant_create", {"tenant_id": "acme", "name": "Acme"}),
    )

    assert first.data == second.data
    assert first.data["id"] == "acme"
    store = _store()
    matching = [tenant for tenant in store.list_tenants() if tenant.id == "acme"]
    assert len(matching) == 1
    assert not hasattr(store, "delete_tenant")

    tool_names = {tool.name for tool in await directory_client.list_tools()}
    assert not any(
        "tenant" in name and ("delete" in name or "remove" in name) for name in tool_names
    )
    listed = await directory_client.call_tool("tenant_list", {})
    assert "acme" in {row["id"] for row in listed.data}
