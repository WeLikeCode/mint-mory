"""RED tests for task 5 — tenant discoverability of the MCP server.

Covers the two capability keys in normal and fallback mode (R7.1) and the
``TENANCY:`` sentence appended to the server instructions (R7.2).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from mintmory.mcp import server
from mintmory.mcp.server import mcp

_TENANCY_SENTENCE = (
    "TENANCY: this server is bound to one tenant scope for its lifetime "
    "(see mintmory://capabilities); the global scope reads every tenant and "
    "writes the global tenant, a named scope reads and writes only its tenant. "
    "tenant_create and tenant_list manage the tenant directory."
)


@pytest.fixture
async def capabilities_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client[Any]]:
    """In-memory client on an isolated DB; the scope is set per test."""
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "tenancy-capabilities.db"))
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


async def _capabilities(client: Client[Any]) -> dict[str, Any]:
    content = await client.read_resource("mintmory://capabilities")
    data = json.loads(content[0].text)  # type: ignore[union-attr]
    assert isinstance(data, dict)
    return data


@pytest.mark.l4("C-d9314674")
async def test_capabilities_global_scope_reports_global_and_not_scoped(
    capabilities_client: Client[Any],
) -> None:
    server._scope_tenant = "global"
    data = await _capabilities(capabilities_client)
    assert data.get("tenant_scope") == "global"
    assert data.get("tenant_scoped") is False


@pytest.mark.l4("C-d9314674")
async def test_capabilities_named_scope_reports_tenant_and_scoped(
    capabilities_client: Client[Any],
) -> None:
    server._scope_tenant = "acme"
    data = await _capabilities(capabilities_client)
    assert data.get("tenant_scope") == "acme"
    assert data.get("tenant_scoped") is True


@pytest.mark.l4("C-d9314674")
async def test_capabilities_fallback_global_scope(
    capabilities_client: Client[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise() -> Any:
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr(server, "load_settings", _raise)
    server._scope_tenant = "global"
    data = await _capabilities(capabilities_client)
    assert data["error"] == "settings unavailable"
    assert data.get("tenant_scope") == "global"
    assert data.get("tenant_scoped") is False


@pytest.mark.l4("C-d9314674")
async def test_capabilities_fallback_named_scope(
    capabilities_client: Client[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise() -> Any:
        raise RuntimeError("settings unavailable")

    monkeypatch.setattr(server, "load_settings", _raise)
    server._scope_tenant = "acme"
    data = await _capabilities(capabilities_client)
    assert data["error"] == "settings unavailable"
    assert data.get("tenant_scope") == "acme"
    assert data.get("tenant_scoped") is True


@pytest.mark.l4("C-e0e1d349")
def test_instructions_end_with_tenancy_sentence() -> None:
    assert mcp.instructions is not None
    assert mcp.instructions.endswith(_TENANCY_SENTENCE)
