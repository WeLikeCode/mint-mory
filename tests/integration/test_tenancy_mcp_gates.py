"""Gate witness for the tenant-scoped MCP unit (R9.3).

The unit's gates are the repo lint/type/test commands, and the test gate fails
under 80% coverage. The tenancy work must not add a Postgres, Docker or network
dependency: this test pins the gate configuration and then runs a scoped MCP
workflow on a local SQLite file with outbound sockets blocked.
"""

from __future__ import annotations

import socket
import tomllib
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from mintmory.core.types import TENANT_GLOBAL
from mintmory.mcp import server
from mintmory.mcp.server import mcp

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _bootstrap(scope: str) -> None:
    bootstrap = getattr(server, "_bootstrap_scope", None)
    assert callable(bootstrap), "server._bootstrap_scope is required"
    bootstrap(scope)


def _tool(result: Any) -> Any:
    assert result is not None, "tool call returned no result object"
    return result


def _no_network(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("network access attempted in a tenancy test")


def _assert_gate_configuration() -> None:
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    addopts = pyproject["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--cov-fail-under=80" in addopts
    testpaths = pyproject["tool"]["pytest"]["ini_options"]["testpaths"]
    assert "packages/mcp/tests" in testpaths
    assert "tests/integration" in testpaths

    harness = (_REPO_ROOT / ".l4" / "config.yaml").read_text(encoding="utf-8")
    assert "gates:" in harness
    assert ".venv/bin/pytest" in harness
    assert "--junitxml=.l4-out/junit.xml" in harness


@pytest.mark.l4("C-533591f4")
async def test_scoped_tenancy_runs_on_sqlite_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _assert_gate_configuration()
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "tenancy-gate.db"))
    monkeypatch.delenv("MINTMORY_MCP_TENANT", raising=False)
    monkeypatch.setattr(socket, "create_connection", _no_network)
    monkeypatch.setattr(socket.socket, "connect", _no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _no_network)
    server._store = None
    server._scope_tenant = TENANT_GLOBAL
    try:
        async with Client(mcp) as client:
            store = server._get_store()
            tenant = store.create_tenant("acme")
            assert tenant is not None and tenant.id == "acme"
            _bootstrap("acme")

            added = _tool(
                await client.call_tool(
                    "memory_add", {"content": "Gate fact about zebras", "category": "fact"}
                )
            ).data
            assert added.get("tenant_id") == "acme"

            search = _tool(await client.call_tool("memory_search", {"query": "zebras"})).data
            assert added.get("id") in {memory.get("id") for memory in search.get("memories", [])}
            session = store.get_session(search.get("session_id", ""))
            assert session is not None
            assert session.tenant_id == "acme"

            tenants = _tool(await client.call_tool("tenant_list", {})).data
            assert "acme" in {row.get("id") for row in tenants}
            assert {"id", "name", "is_active"} <= {key for row in tenants for key in row}
            assert all(isinstance(row.get("is_active"), bool) for row in tenants)
    finally:
        if server._store is not None:
            server._store.close()
        server._store = None
        server._scope_tenant = TENANT_GLOBAL
