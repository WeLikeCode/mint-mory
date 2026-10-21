"""Tests for the tenancy-aware MCP fixtures (R9.1).

The MCP tenancy suite drives the real fastmcp in-memory ``Client``. Each fixture
must bind the process to its own SQLite file, set the named scope through
``_bootstrap_scope`` for ``acme_client``, and put the module globals back
(``_scope_tenant == "global"`` and ``_store is None``) on teardown so no test
inherits another test's scope.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from mintmory.core.ports import StorageBackend
from mintmory.core.types import TENANT_GLOBAL, MemoryCategory, MemoryRecord, MemorySource
from mintmory.mcp import server
from mintmory.mcp.server import mcp


def _bootstrap(scope: str) -> None:
    """Call the startup hook, failing by assertion when it is absent or zeroed."""
    bootstrap = getattr(server, "_bootstrap_scope", None)
    assert callable(bootstrap), "server._bootstrap_scope is required"
    bootstrap(scope)


def _scope() -> Any:
    return getattr(server, "_scope_tenant", "<missing>")


def _tool(result: Any) -> Any:
    assert result is not None, "tool call returned no result object"
    return result


def _reset_module_state() -> None:
    if server._store is not None:
        server._store.close()
    server._store = None
    server._scope_tenant = TENANT_GLOBAL


async def _mcp_client_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[Client[Any], None]:
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "tenancy-fixtures.db"))
    monkeypatch.delenv("MINTMORY_MCP_TENANT", raising=False)
    server._store = None
    server._scope_tenant = TENANT_GLOBAL
    try:
        async with Client(mcp) as client:
            yield client
    finally:
        _reset_module_state()


async def _acme_client_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[Client[Any], None]:
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "tenancy-fixtures-acme.db"))
    monkeypatch.delenv("MINTMORY_MCP_TENANT", raising=False)
    server._store = None
    server._scope_tenant = TENANT_GLOBAL
    store = server._get_store()
    store.create_tenant("acme")
    _bootstrap("acme")
    try:
        async with Client(mcp) as client:
            yield client
    finally:
        _reset_module_state()


@pytest.fixture
async def mcp_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[Client[Any], None]:
    """In-memory client in the global scope; both globals reset on teardown."""
    async for client in _mcp_client_body(tmp_path, monkeypatch):
        yield client


@pytest.fixture
async def acme_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[Client[Any], None]:
    """In-memory client bootstrapped to the existing tenant ``acme``."""
    async for client in _acme_client_body(tmp_path, monkeypatch):
        yield client


@pytest.mark.l4("C-ac779f2c")
async def test_acme_client_fixture_bootstraps_the_named_scope(
    acme_client: Client[Any],
) -> None:
    store: StorageBackend = server._get_store()
    assert _scope() == "acme"
    effective = getattr(server, "_effective_tenant", None)
    assert callable(effective)
    assert effective() == "acme"

    added = _tool(
        await acme_client.call_tool(
            "memory_add", {"content": "Fixture fact about zebras", "category": "fact"}
        )
    )
    assert added.data.get("tenant_id") == "acme"

    foreign = store.add_memory(
        MemoryRecord(
            content="A global fact about zebras",
            category=MemoryCategory.FACT,
            source=MemorySource.AGENT,
            tenant_id=TENANT_GLOBAL,
        )
    )
    assert foreign is not None and foreign.id
    hidden = _tool(await acme_client.call_tool("memory_get", {"memory_id": foreign.id}))
    assert hidden.data is None


@pytest.mark.l4("C-ac779f2c")
async def test_acme_client_fixture_teardown_restores_scope_and_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator = _acme_client_body(tmp_path, monkeypatch)
    client = await anext(generator)
    try:
        assert _scope() == "acme"
        assert server._store is not None
        added = _tool(
            await client.call_tool(
                "memory_add", {"content": "Teardown fact about zebras", "category": "fact"}
            )
        )
        assert added.data.get("tenant_id") == "acme"
    finally:
        await generator.aclose()

    assert _scope() == TENANT_GLOBAL
    assert server._store is None


@pytest.mark.l4("C-ac779f2c")
async def test_mcp_client_fixture_starts_in_the_global_scope(
    mcp_client: Client[Any],
) -> None:
    assert _scope() == TENANT_GLOBAL
    effective = getattr(server, "_effective_tenant", None)
    assert callable(effective)
    assert effective() is None

    added = _tool(
        await mcp_client.call_tool(
            "memory_add", {"content": "Global fixture fact about zebras", "category": "fact"}
        )
    )
    assert added.data.get("tenant_id") == TENANT_GLOBAL

    store: StorageBackend = server._get_store()
    tenant = store.create_tenant("acme")
    assert tenant is not None and tenant.id == "acme"
    _bootstrap("acme")
    switched = _tool(
        await mcp_client.call_tool(
            "memory_add", {"content": "Named fixture fact about zebras", "category": "fact"}
        )
    )
    assert switched.data.get("tenant_id") == "acme"
