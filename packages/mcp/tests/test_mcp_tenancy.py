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
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mintmory.core import config as config_mod
from mintmory.core.ports import StorageBackend
from mintmory.core.types import InvalidTenantIdError, TenantNotFoundError
from mintmory.mcp import server


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
