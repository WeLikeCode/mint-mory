"""Task 2.1 gate: the stdio MCP server scenarios re-pinned under fresh names.

Spec: observability › Every entry point initialises telemetry once.

Task 2.1 is the unit's final check (the ruff/format/mypy/coverage gates). It adds no
behaviour of its own, so the stdio-server scenario of the delta is re-pinned here against
``server.main``/``history_server.main`` as they already are (TDD exemption: already
satisfied by task 1.4). The recorders assert the call happens exactly once, before
``mcp.run``, with no positional settings and each server's own ``default_service_name``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from mintmory.mcp import history_server, server

_Calls = list[tuple[str, tuple[Any, ...], dict[str, Any]]]


def _record_telemetry_and_run(monkeypatch: pytest.MonkeyPatch, module: Any) -> _Calls:
    """Replace ``module.init_telemetry``/``module.mcp.run`` with recorders sharing one list."""
    calls: _Calls = []

    def _record_init(*args: Any, **kwargs: Any) -> bool:
        calls.append(("init_telemetry", args, kwargs))
        return False

    def _record_run(*args: Any, **kwargs: Any) -> None:
        calls.append(("run", args, kwargs))

    monkeypatch.setattr(module, "init_telemetry", _record_init, raising=False)
    monkeypatch.setattr(module.mcp, "run", _record_run)
    return calls


@pytest.mark.l4("C-97901dac")
def test_gate_mcp_server_main_initialises_and_serves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``mintmory-mcp`` initialises once with its own service name and no settings."""
    calls = _record_telemetry_and_run(monkeypatch, server)
    monkeypatch.setattr(sys, "argv", ["mintmory-mcp"])

    server.main()

    assert [name for name, _args, _kwargs in calls] == ["init_telemetry", "run"]
    _name, args, kwargs = calls[0]
    assert args == (), "the stdio server must pass no positional settings"
    assert kwargs.get("default_service_name") == "mintmory-mcp"


@pytest.mark.l4("C-97901dac")
def test_gate_history_mcp_server_main_initialises_and_serves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``mintmory-history-mcp`` initialises once with its own service name and no settings."""
    calls = _record_telemetry_and_run(monkeypatch, history_server)
    monkeypatch.setenv("MINTMORY_HISTORY_DB", str(tmp_path / "agent-history.db"))
    monkeypatch.delenv("MINTMORY_DB", raising=False)
    monkeypatch.setattr(sys, "argv", ["mintmory-history-mcp"])

    history_server.main()

    assert [name for name, _args, _kwargs in calls] == ["init_telemetry", "run"]
    _name, args, kwargs = calls[0]
    assert args == (), "the stdio server must pass no positional settings"
    assert kwargs.get("default_service_name") == "mintmory-history-mcp"
