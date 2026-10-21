"""RED tests for task 1 — tenant-scope settings and fail-fast MCP startup.

Each test traces one of the startup criteria of the tenant-scoped MCP unit:
``McpSettings`` (R1.1), the ``--tenant`` / ``MINTMORY_MCP_TENANT`` resolution
(R1.2), ``_bootstrap_scope`` (R1.3), ``main()``'s bootstrap-before-run order and
error handling (R1.4), the module-level scope globals (R1.5), and the concrete
``main()`` scenarios (R1.6).
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from mintmory.core import config as config_mod
from mintmory.core import notes as core_notes
from mintmory.core.cochange import changed_with as core_changed_with
from mintmory.core.cochange import documents_timeline as core_documents_timeline
from mintmory.core.ports import StorageBackend
from mintmory.core.types import (
    InvalidTenantIdError,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
    MemorySummary,
    TenantNotFoundError,
)
from mintmory.mcp import server
from mintmory.mcp.server import mcp


@pytest.fixture
def tenant_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[StorageBackend]:
    """A fresh SQLite store for one test; resets the module singleton afterwards."""
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "tenancy.db"))
    monkeypatch.delenv("MINTMORY_MCP_TENANT", raising=False)
    server._store = None
    try:
        yield server._get_store()
    finally:
        if server._store is not None:
            server._store.close()
        server._store = None


_SCOPE_DEFINED_AT_IMPORT = hasattr(server, "_scope_tenant")


def _restore_scope_state() -> None:
    if _SCOPE_DEFINED_AT_IMPORT:
        server.__dict__["_scope_tenant"] = "global"
    elif "_scope_tenant" in server.__dict__:
        del server.__dict__["_scope_tenant"]


@pytest.fixture(autouse=True)
def _reset_scope() -> Iterator[None]:
    """Keep the module-global scope from leaking between tests (R9.1 in a later task)."""
    _restore_scope_state()
    yield
    _restore_scope_state()


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    calls: list[dict[str, Any]],
) -> int | None:
    """Drive ``server.main()`` and return its SystemExit code (None on success)."""

    def _recording_run(**kwargs: Any) -> None:
        calls.append(kwargs)

    def _no_telemetry(*args: Any, **kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(sys, "argv", ["mintmory-mcp", *argv])
    monkeypatch.setattr(server.mcp, "run", _recording_run)
    monkeypatch.setattr(server, "init_telemetry", _no_telemetry)
    try:
        server.main()
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else 1
    return None


# ---------------------------------------------------------------------------
# R1.1 — McpSettings
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-782096db")
def test_mcp_settings_defaults_to_empty_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MINTMORY_MCP_TENANT", raising=False)
    settings_cls = getattr(config_mod, "McpSettings", None)
    assert settings_cls is not None, "config.py must define McpSettings"
    settings = settings_cls()
    assert settings.tenant == ""
    assert settings_cls.model_config.get("env_prefix") == "MINTMORY_MCP_"
    assert settings_cls.model_config.get("extra") == "ignore"


@pytest.mark.l4("C-782096db")
def test_mcp_settings_reads_tenant_from_prefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINTMORY_MCP_TENANT", "acme")
    monkeypatch.setenv("MINTMORY_MCP_UNRELATED", "ignored")
    settings_cls = getattr(config_mod, "McpSettings", None)
    assert settings_cls is not None, "config.py must define McpSettings"
    assert settings_cls().tenant == "acme"


# ---------------------------------------------------------------------------
# R1.3 — _bootstrap_scope
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3f8c9acb")
def test_bootstrap_scope_sets_an_existing_active_tenant(tenant_store: StorageBackend) -> None:
    tenant_store.create_tenant("acme")
    server._bootstrap_scope("acme")
    assert getattr(server, "_scope_tenant", None) == "acme"


@pytest.mark.l4("C-3f8c9acb")
def test_bootstrap_scope_rejects_invalid_id_before_opening_the_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom() -> StorageBackend:
        raise AssertionError("_get_store must not run before validate_tenant_id")

    monkeypatch.setattr(server, "_get_store", _boom)
    with pytest.raises(InvalidTenantIdError):
        server._bootstrap_scope("Bad")
    assert getattr(server, "_scope_tenant", None) == "global"


@pytest.mark.l4("C-3f8c9acb")
def test_bootstrap_scope_missing_tenant_raises_and_never_creates_it(
    tenant_store: StorageBackend,
) -> None:
    with pytest.raises(TenantNotFoundError) as exc_info:
        server._bootstrap_scope("nope")
    assert "tenant 'nope' not found" in str(exc_info.value)
    assert tenant_store.get_tenant("nope") is None
    assert getattr(server, "_scope_tenant", None) == "global"


@pytest.mark.l4("C-3f8c9acb")
def test_bootstrap_scope_global_needs_no_tenant_row(tenant_store: StorageBackend) -> None:
    server._bootstrap_scope("global")
    assert getattr(server, "_scope_tenant", None) == "global"
    assert server._store is tenant_store
    assert tenant_store.get_tenant("acme") is None


@pytest.mark.l4("C-3f8c9acb")
def test_bootstrap_scope_warns_and_continues_for_inactive_tenant(
    tenant_store: StorageBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    tenant_store.create_tenant("acme")
    tenant_store.set_tenant_active("acme", False)
    server._bootstrap_scope("acme")
    captured = capsys.readouterr()
    assert (
        "mintmory-mcp: warning: tenant 'acme' is inactive; this server is read-only" in captured.err
    )
    assert getattr(server, "_scope_tenant", None) == "acme"


# ---------------------------------------------------------------------------
# R1.5 — module-level scope globals
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-70a0d49a")
def test_scope_tenant_defaults_to_global_at_import() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from mintmory.mcp import server; print(server._scope_tenant)"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout.strip() == "global", result.stderr


@pytest.mark.l4("C-70a0d49a")
def test_effective_tenant_maps_global_to_none_and_named_scope_to_itself() -> None:
    server.__dict__["_scope_tenant"] = "global"
    assert server._effective_tenant() is None
    server.__dict__["_scope_tenant"] = "acme"
    assert server._effective_tenant() == "acme"


# ---------------------------------------------------------------------------
# R1.2 / R1.4 / R1.6 — main() resolution, bootstrap and fail-fast
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-8da08d08", "C-5a923d15", "C-f37e9647")
def test_main_without_option_or_env_uses_global_scope(
    tenant_store: StorageBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    code = _run_main(monkeypatch, [], calls)
    assert code is None
    assert calls == [{"transport": "stdio"}]
    assert getattr(server, "_scope_tenant", None) == "global"


@pytest.mark.l4("C-8da08d08", "C-5a923d15", "C-f37e9647")
def test_main_uses_existing_tenant_from_env(
    tenant_store: StorageBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_store.create_tenant("acme")
    monkeypatch.setenv("MINTMORY_MCP_TENANT", "acme")
    calls: list[dict[str, Any]] = []
    code = _run_main(monkeypatch, [], calls)
    assert code is None
    assert calls == [{"transport": "stdio"}]
    assert getattr(server, "_scope_tenant", None) == "acme"


@pytest.mark.l4("C-8da08d08", "C-5a923d15", "C-f37e9647")
def test_main_cli_tenant_overrides_env(
    tenant_store: StorageBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_store.create_tenant("acme")
    monkeypatch.setenv("MINTMORY_MCP_TENANT", "other")
    calls: list[dict[str, Any]] = []
    code = _run_main(monkeypatch, ["--tenant", "acme"], calls)
    assert code is None
    assert calls == [{"transport": "stdio"}]
    assert getattr(server, "_scope_tenant", None) == "acme"


@pytest.mark.l4("C-8da08d08", "C-5a923d15", "C-f37e9647")
def test_main_missing_tenant_exits_one_without_running(
    tenant_store: StorageBackend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, Any]] = []
    code = _run_main(monkeypatch, ["--tenant", "nope"], calls)
    captured = capsys.readouterr()
    assert code == 1
    assert calls == []
    assert "mintmory-mcp: error: tenant 'nope' not found" in captured.err


@pytest.mark.l4("C-8da08d08", "C-5a923d15", "C-f37e9647")
def test_main_invalid_tenant_exits_one_without_running(
    tenant_store: StorageBackend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, Any]] = []
    code = _run_main(monkeypatch, ["--tenant", "Bad"], calls)
    captured = capsys.readouterr()
    assert code == 1
    assert calls == []
    assert "invalid tenant id" in captured.err


@pytest.mark.l4("C-8da08d08", "C-5a923d15", "C-f37e9647")
def test_main_inactive_tenant_starts_and_warns(
    tenant_store: StorageBackend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tenant_store.create_tenant("acme")
    tenant_store.set_tenant_active("acme", False)
    calls: list[dict[str, Any]] = []
    code = _run_main(monkeypatch, ["--tenant", "acme"], calls)
    captured = capsys.readouterr()
    assert code is None
    assert calls == [{"transport": "stdio"}]
    assert (
        "mintmory-mcp: warning: tenant 'acme' is inactive; this server is read-only" in captured.err
    )
    assert getattr(server, "_scope_tenant", None) == "acme"


@pytest.mark.l4("C-8da08d08", "C-5a923d15", "C-f37e9647")
def test_main_sse_bootstraps_then_runs_on_the_requested_port(
    tenant_store: StorageBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_store.create_tenant("acme")
    calls: list[dict[str, Any]] = []
    code = _run_main(monkeypatch, ["--transport", "sse", "--tenant", "acme"], calls)
    assert code is None
    assert calls == [{"transport": "sse", "port": 8081}]
    assert getattr(server, "_scope_tenant", None) == "acme"


# ---------------------------------------------------------------------------
# Task 2 — read tools carry the process scope and honour both scopes
# ---------------------------------------------------------------------------


@pytest.fixture
async def tenancy_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client[Any]]:
    """In-memory MCP client on an isolated DB, with the scope reset on teardown."""
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "tenancy-reads.db"))
    monkeypatch.delenv("MINTMORY_MCP_TENANT", raising=False)
    server._store = None
    try:
        async with Client(mcp) as client:
            yield client
    finally:
        if server._store is not None:
            server._store.close()
        server._store = None


def _record_call(seen: dict[str, dict[str, Any]], name: str, original: Any) -> Any:
    """Wrap ``original`` so the call's args/kwargs land in ``seen[name]``."""

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen[name] = {"args": args, "kwargs": kwargs}
        return original(*args, **kwargs)

    return spy


def _tenant_argument(call: dict[str, Any], position: int) -> Any:
    """The effective tenant of a recorded call (keyword or positional)."""
    if "tenant_id" in call["kwargs"]:
        return call["kwargs"]["tenant_id"]
    if len(call["args"]) > position:
        return call["args"][position]
    return "<missing>"


def _seed_core_memories(store: StorageBackend) -> dict[str, str]:
    """Minimal R3.2/R4.2 corpus: two global and two acme memories."""
    store.create_tenant("acme")
    rows = {
        "g1": ("Alice uses Postgres", "global"),
        "g2": ("Carol uses Postgres", "global"),
        "a1": ("Alice uses SQLite", "acme"),
        "a2": ("Bob uses SQLite", "acme"),
    }
    ids: dict[str, str] = {}
    for key, (content, tenant_id) in rows.items():
        record = store.add_memory(
            record=MemoryRecord(
                content=content,
                category=MemoryCategory.FACT,
                source=MemorySource.AGENT,
                tenant_id=tenant_id,
            )
        )
        ids[key] = record.id
    return ids


def _seed_doc(store: StorageBackend, *, tenant_id: str, path: str, changeset_id: str) -> None:
    store.add_memory(
        record=MemoryRecord(
            content=f"[doc] {path}",
            category=MemoryCategory.CONTEXT,
            source=MemorySource.DOCUMENT,
            valid_from=datetime(2024, 1, 1),
            metadata={
                "path": path,
                "rel": path.lstrip("/"),
                "collection": "tenancy",
                "changeset_id": changeset_id,
                "changeset_kind": "cold_full_index",
                "changeset_observed_at": "2024-01-01T00:00:00",
            },
            tenant_id=tenant_id,
        )
    )


def _seed_extras(store: StorageBackend) -> None:
    """Notes, summaries and co-change documents for both tenants."""
    for content, tenant_id in (
        ("global note about the index", "global"),
        ("acme note about the index", "acme"),
    ):
        store.add_memory(
            record=MemoryRecord(
                content=content,
                category=MemoryCategory.EPISODIC,
                source=MemorySource.USER,
                is_note=True,
                tenant_id=tenant_id,
            )
        )
    for concept, text, tenant_id in (
        ("alice", "global alice", "global"),
        ("alice", "acme alice", "acme"),
        ("bob", "acme bob", "acme"),
    ):
        store.upsert_summary(
            MemorySummary(
                concept=concept,
                summary_text=text,
                memory_count=1,
                tenant_id=tenant_id,
            )
        )
    _seed_doc(store, tenant_id="global", path="/repo/g_a.py", changeset_id="cs-g")
    _seed_doc(store, tenant_id="global", path="/repo/g_b.py", changeset_id="cs-g")
    _seed_doc(store, tenant_id="acme", path="/repo/a_a.py", changeset_id="cs-a")
    _seed_doc(store, tenant_id="acme", path="/repo/a_b.py", changeset_id="cs-a")


@pytest.mark.l4("C-3a9634d3")
@pytest.mark.parametrize(
    ("scope", "expected_effective"),
    [("global", None), ("acme", "acme")],
)
async def test_read_tools_pass_the_resolved_tenant(
    tenancy_client: Client[Any],
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    expected_effective: str | None,
) -> None:
    store = server._get_store()
    store.create_tenant("acme")
    seen: dict[str, dict[str, Any]] = {}
    for name in ("get_memory", "search", "get_stats", "list_summaries", "get_summary"):
        monkeypatch.setattr(store, name, _record_call(seen, name, getattr(store, name)))
    monkeypatch.setattr(
        core_notes,
        "notes_list",
        _record_call(seen, "notes_list", core_notes.notes_list),
    )
    monkeypatch.setattr(
        server, "changed_with", _record_call(seen, "changed_with", core_changed_with)
    )
    monkeypatch.setattr(
        server,
        "documents_timeline",
        _record_call(seen, "documents_timeline", core_documents_timeline),
    )

    server._bootstrap_scope(scope)

    await tenancy_client.call_tool("memory_get", {"memory_id": "missing"})
    await tenancy_client.call_tool("memory_search", {"query": "missing"})
    await tenancy_client.call_tool("memory_stats", {})
    await tenancy_client.call_tool("summary_list", {})
    await tenancy_client.call_tool("summary_get", {"concept": "missing"})
    await tenancy_client.call_tool("notes_list", {})
    await tenancy_client.call_tool("docs_changed_with", {"path": "/repo/none.py"})
    await tenancy_client.call_tool("docs_timeline", {})

    assert _tenant_argument(seen["get_memory"], 1) == expected_effective
    assert _tenant_argument(seen["search"], 1) == expected_effective
    assert _tenant_argument(seen["get_stats"], 0) == expected_effective
    assert _tenant_argument(seen["list_summaries"], 0) == expected_effective
    assert _tenant_argument(seen["get_summary"], 1) == scope
    assert _tenant_argument(seen["notes_list"], 5) == expected_effective
    assert _tenant_argument(seen["changed_with"], 2) == expected_effective
    assert _tenant_argument(seen["documents_timeline"], 1) == expected_effective


@pytest.mark.l4("C-8b67e092")
async def test_named_scope_reads_are_confined_to_the_tenant(
    tenancy_client: Client[Any],
) -> None:
    store = server._get_store()
    ids = _seed_core_memories(store)
    server._bootstrap_scope("acme")

    got = await tenancy_client.call_tool("memory_get", {"memory_id": ids["g1"]})
    assert got.data is None
    own = await tenancy_client.call_tool("memory_get", {"memory_id": ids["a1"]})
    assert own.data["id"] == ids["a1"]

    search = await tenancy_client.call_tool("memory_search", {"query": "Alice"})
    assert {memory["id"] for memory in search.data["memories"]} == {ids["a1"]}
    query_session = store.get_session(search.data["session_id"])
    assert query_session is not None
    assert query_session.tenant_id == "acme"

    stats = await tenancy_client.call_tool("memory_stats", {})
    assert stats.data["total_memories"] == 2

    _seed_extras(store)

    summaries = await tenancy_client.call_tool("summary_list", {})
    assert {summary["tenant_id"] for summary in summaries.data} == {"acme"}
    assert {summary["concept"] for summary in summaries.data} == {"alice", "bob"}

    summary = await tenancy_client.call_tool("summary_get", {"concept": "alice"})
    assert summary.data["summary_text"] == "acme alice"

    notes = await tenancy_client.call_tool("notes_list", {})
    assert {note["tenant_id"] for note in notes.data} == {"acme"}
    assert len(notes.data) == 1

    foreign_peers = await tenancy_client.call_tool("docs_changed_with", {"path": "/repo/g_a.py"})
    assert foreign_peers.data == []
    peers = await tenancy_client.call_tool("docs_changed_with", {"path": "/repo/a_a.py"})
    assert [peer["path"] for peer in peers.data] == ["/repo/a_b.py"]

    timeline = await tenancy_client.call_tool("docs_timeline", {})
    assert {row["path"] for row in timeline.data} == {"/repo/a_a.py", "/repo/a_b.py"}


@pytest.mark.l4("C-38da7fdc")
async def test_global_scope_reads_span_every_tenant(
    tenancy_client: Client[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    store = server._get_store()
    ids = _seed_core_memories(store)
    _seed_extras(store)

    seen: dict[str, dict[str, Any]] = {}
    monkeypatch.setattr(store, "search", _record_call(seen, "search", store.search))
    server._bootstrap_scope("global")

    search = await tenancy_client.call_tool("memory_search", {"query": "Alice"})
    assert {memory["id"] for memory in search.data["memories"]} == {ids["g1"], ids["a1"]}
    assert _tenant_argument(seen["search"], 1) is None

    got = await tenancy_client.call_tool("memory_get", {"memory_id": ids["a1"]})
    assert got.data["id"] == ids["a1"]
    assert got.data["tenant_id"] == "acme"

    stats = await tenancy_client.call_tool("memory_stats", {})
    assert stats.data["total_memories"] == 10

    summaries = await tenancy_client.call_tool("summary_list", {})
    assert {summary["tenant_id"] for summary in summaries.data} == {"global", "acme"}
    assert {(summary["tenant_id"], summary["concept"]) for summary in summaries.data} == {
        ("global", "alice"),
        ("acme", "alice"),
        ("acme", "bob"),
    }

    summary = await tenancy_client.call_tool("summary_get", {"concept": "alice"})
    assert summary.data["summary_text"] == "global alice"

    notes = await tenancy_client.call_tool("notes_list", {})
    assert {note["tenant_id"] for note in notes.data} == {"global", "acme"}

    global_peers = await tenancy_client.call_tool("docs_changed_with", {"path": "/repo/g_a.py"})
    assert [peer["path"] for peer in global_peers.data] == ["/repo/g_b.py"]
    acme_peers = await tenancy_client.call_tool("docs_changed_with", {"path": "/repo/a_a.py"})
    assert [peer["path"] for peer in acme_peers.data] == ["/repo/a_b.py"]

    timeline = await tenancy_client.call_tool("docs_timeline", {})
    assert {row["path"] for row in timeline.data} == {
        "/repo/g_a.py",
        "/repo/g_b.py",
        "/repo/a_a.py",
        "/repo/a_b.py",
    }
