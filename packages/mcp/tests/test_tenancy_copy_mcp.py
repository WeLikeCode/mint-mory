"""RED tests for task 4 — the MCP ``tenant_copy`` tool (R8.1, R9.10 MCP part).

The tool is global-scope only: a named-scope server refuses it before reading
anything, unknown filter keys are rejected (pydantic would silently ignore
them), and the report is returned as ``CopyReport.model_dump(mode="json")``.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, cast

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mintmory.core.ports import StorageBackend
from mintmory.core.transfer import CopyReport
from mintmory.core.types import (
    MemoryCategory,
    MemoryFilter,
    MemoryRecord,
    MemorySource,
    ScopeRequiredError,
)
from mintmory.mcp import server
from mintmory.mcp.server import mcp

_REPORT_FIELDS = {
    "source_tenant",
    "dest_tenant",
    "memories_copied",
    "memories_skipped_duplicate",
    "memories_skipped_not_found",
    "notes_copied",
    "notes_skipped_duplicate",
    "links_copied",
    "id_map",
}


@pytest.fixture
async def copy_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client[Any]]:
    """In-memory client on an isolated DB in the global scope."""
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "copy-mcp.db"))
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
async def acme_copy_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client[Any]]:
    """Client whose process scope is the existing tenant ``acme``."""
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "copy-mcp-acme.db"))
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


def _tenant_copy_tool() -> Callable[..., dict[str, Any]]:
    """The tool function; fails as an assertion while it does not exist."""
    tool = getattr(server, "tenant_copy", None)
    assert callable(tool), "server.py must define a tenant_copy tool"
    return cast(Callable[..., dict[str, Any]], tool)


def _seed(store: StorageBackend, memory_id: str, content: str, tenant_id: str) -> MemoryRecord:
    return store.add_memory(
        MemoryRecord(
            id=memory_id,
            content=content,
            category=MemoryCategory.FACT,
            source=MemorySource.AGENT,
            tenant_id=tenant_id,
        )
    )


# ---------------------------------------------------------------------------
# R8.1 — registration, inventory kind and the tenant-parameter scan
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3a04fd3e")
async def test_tenant_copy_is_registered_as_a_copy_scope_tool(copy_client: Client[Any]) -> None:
    declared = _declared_scope()
    assert declared.get("tenant_copy") == "copy"

    tools = {tool.name: tool for tool in await copy_client.list_tools()}
    assert "tenant_copy" in tools
    properties = set(tools["tenant_copy"].inputSchema.get("properties", {}))
    assert {name for name in properties if "tenant" in name} == {
        "source_tenant",
        "dest_tenant",
    }
    assert {
        "source_tenant",
        "dest_tenant",
        "memory_ids",
        "filter",
        "all_active",
        "force",
    } <= properties


# ---------------------------------------------------------------------------
# R8.1 — signature and the scope check before any read
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3a04fd3e")
def test_tenant_copy_signature_and_scope_check_before_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tenant_copy_tool()
    params = inspect.signature(tool).parameters
    assert list(params) == [
        "source_tenant",
        "dest_tenant",
        "memory_ids",
        "filter",
        "all_active",
        "force",
    ]
    assert params["source_tenant"].default is inspect.Parameter.empty
    assert params["dest_tenant"].default is inspect.Parameter.empty
    assert params["memory_ids"].default is None
    assert params["filter"].default is None
    assert params["all_active"].default is False
    assert params["force"].default is False

    monkeypatch.setattr(server, "_scope_tenant", "acme")
    reads: list[str] = []

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        reads.append("read")
        raise AssertionError("tenant_copy touched the store before the scope check")

    monkeypatch.setattr(server, "copy_between_tenants", forbidden, raising=False)
    monkeypatch.setattr(server, "_get_store", forbidden, raising=False)

    with pytest.raises(ScopeRequiredError) as exc_info:
        tool(source_tenant="acme", dest_tenant="beta", all_active=True)

    assert exc_info.value.operation == "tenant_copy"
    assert exc_info.value.scope == "acme"
    assert reads == []


# ---------------------------------------------------------------------------
# R8.1 — unknown filter keys are rejected, not ignored
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3a04fd3e")
def test_tenant_copy_rejects_unknown_filter_keys_before_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tenant_copy_tool()
    monkeypatch.setattr(server, "_scope_tenant", "global")
    reads: list[str] = []

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        reads.append("read")
        raise AssertionError("tenant_copy read the store before validating the filter")

    monkeypatch.setattr(server, "_get_store", forbidden, raising=False)
    monkeypatch.setattr(server, "copy_between_tenants", forbidden, raising=False)

    with pytest.raises(ValueError) as exc_info:
        tool(
            source_tenant="acme",
            dest_tenant="beta",
            filter={"zebra": 1, "alpha": True},
        )

    assert str(exc_info.value) == "unknown filter key(s): ['alpha', 'zebra']"
    assert reads == []


# ---------------------------------------------------------------------------
# R8.1 / R2.1(d) — the filter is parsed with MemoryFilter.model_validate
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3a04fd3e")
async def test_tenant_copy_invalid_filter_value_is_a_tool_error(
    copy_client: Client[Any],
) -> None:
    assert _declared_scope().get("tenant_copy") == "copy"

    with pytest.raises(ToolError) as exc_info:
        await copy_client.call_tool(
            "tenant_copy",
            {
                "source_tenant": "acme",
                "dest_tenant": "beta",
                "filter": {"category": "not_a_category"},
            },
        )

    message = str(exc_info.value)
    assert "category" in message
    assert "not_a_category" in message


@pytest.mark.l4("C-3a04fd3e")
async def test_tenant_copy_empty_filter_is_a_selection_error(copy_client: Client[Any]) -> None:
    assert _declared_scope().get("tenant_copy") == "copy"

    with pytest.raises(ToolError) as exc_info:
        await copy_client.call_tool(
            "tenant_copy",
            {"source_tenant": "acme", "dest_tenant": "beta", "filter": {}},
        )

    assert "empty filter: use all_active=True to copy every active memory" in str(exc_info.value)


# ---------------------------------------------------------------------------
# R9.10 (MCP part) — named scope refuses, global scope returns the report
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-654ba513")
async def test_named_scope_tenant_copy_raises_and_writes_nothing(
    acme_copy_client: Client[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _declared_scope().get("tenant_copy") == "copy"
    store = server._get_store()
    store.create_tenant("beta")
    _seed(store, "m1", "Alice works at Acme", "acme")

    reads: list[str] = []
    original_get_memory = store.get_memory

    def spy_get_memory(memory_id: str, tenant_id: str | None = None) -> MemoryRecord | None:
        reads.append(memory_id)
        return original_get_memory(memory_id, tenant_id=tenant_id)

    monkeypatch.setattr(store, "get_memory", spy_get_memory)

    with pytest.raises(ToolError) as exc_info:
        await acme_copy_client.call_tool(
            "tenant_copy",
            {
                "source_tenant": "acme",
                "dest_tenant": "beta",
                "memory_ids": ["m1"],
            },
        )

    message = str(exc_info.value)
    assert "requires the global scope" in message
    assert "tenant 'acme'" in message
    assert reads == []
    assert (
        store.list_memories(
            MemoryFilter(active_only=False, exclude_stale=False),
            tenant_id="beta",
        )
        == []
    )


@pytest.mark.l4("C-654ba513", "C-3a04fd3e")
async def test_global_scope_tenant_copy_returns_the_report_json(copy_client: Client[Any]) -> None:
    assert _declared_scope().get("tenant_copy") == "copy"
    store = server._get_store()
    store.create_tenant("acme")
    store.create_tenant("beta")
    _seed(store, "m1", "Alice works at Acme", "acme")

    result = await copy_client.call_tool(
        "tenant_copy",
        {
            "source_tenant": "acme",
            "dest_tenant": "beta",
            "memory_ids": ["m1"],
        },
    )

    data = result.data
    assert isinstance(data, dict)
    assert set(data) == _REPORT_FIELDS
    assert list(data["id_map"]) == ["m1"]
    new_id = data["id_map"]["m1"]

    expected = CopyReport(
        source_tenant="acme",
        dest_tenant="beta",
        memories_copied=1,
        id_map={"m1": new_id},
    ).model_dump(mode="json")
    assert data == expected

    copied = store.get_memory(new_id, tenant_id="beta")
    assert copied is not None
    assert copied.content == "Alice works at Acme"
    assert copied.tenant_id == "beta"
