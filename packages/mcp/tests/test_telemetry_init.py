"""
Regression test for the MCP entrypoint's OTel initialisation (bug: the deployed
mintmory-mcp SSE server never called init_telemetry(), so MINTMORY_OTEL_ENABLED=true
had no effect — only the REST API's lifespan did).

Observability › Every entry point initialises telemetry once: ``server.main()`` and
``history_server.main()`` call ``init_telemetry`` exactly once, before ``mcp.run()``,
with no settings and their own ``default_service_name`` so every process reports the
right service. ``mcp.run`` is monkeypatched to a no-op so the tests don't block on a
real server loop or transport.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.mcp import history_server, server


@pytest.mark.l4("C-97901dac")
def test_main_initialises_telemetry_before_serving(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """main() must call init_telemetry() with no settings and its own service name,
    before mcp.run() starts handling requests."""
    calls: list[str] = []
    init_settings: list[Any] = []
    init_kwargs: list[dict[str, Any]] = []

    def _fake_init_telemetry(settings: Any = None, **kwargs: Any) -> bool:
        calls.append("init_telemetry")
        init_settings.append(settings)
        init_kwargs.append(kwargs)
        return False

    def _fake_run(*args: Any, **kwargs: Any) -> None:
        calls.append("run")

    monkeypatch.setattr(server, "init_telemetry", _fake_init_telemetry)
    monkeypatch.setattr(server.mcp, "run", _fake_run)
    monkeypatch.setattr("sys.argv", ["mintmory-mcp"])

    server.main()

    assert calls == ["init_telemetry", "run"], (
        f"init_telemetry must run exactly once, before mcp.run() — got: {calls}"
    )
    assert init_settings == [None], "the stdio server must pass no positional settings"
    assert init_kwargs[0]["default_service_name"] == "mintmory-mcp", init_kwargs


@pytest.mark.l4("C-97901dac")
def test_history_main_initialises_telemetry_before_serving(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """history_server.main() must call init_telemetry() with no settings and its own
    service name, before mcp.run() starts handling requests."""
    calls: list[str] = []
    init_settings: list[Any] = []
    init_kwargs: list[dict[str, Any]] = []

    def _fake_init_telemetry(settings: Any = None, **kwargs: Any) -> bool:
        calls.append("init_telemetry")
        init_settings.append(settings)
        init_kwargs.append(kwargs)
        return False

    def _fake_run(*args: Any, **kwargs: Any) -> None:
        calls.append("run")

    monkeypatch.setattr(history_server, "init_telemetry", _fake_init_telemetry)
    monkeypatch.setattr(history_server.mcp, "run", _fake_run)
    monkeypatch.setenv("MINTMORY_HISTORY_DB", str(tmp_path / "agent-history.db"))
    monkeypatch.delenv("MINTMORY_DB", raising=False)
    monkeypatch.setattr("sys.argv", ["mintmory-history-mcp"])

    history_server.main()

    assert calls == ["init_telemetry", "run"], (
        f"init_telemetry must run exactly once, before mcp.run() — got: {calls}"
    )
    assert init_settings == [None], "the stdio server must pass no positional settings"
    assert init_kwargs[0]["default_service_name"] == "mintmory-history-mcp", init_kwargs


def test_main_telemetry_default_off_is_safe(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """With no MINTMORY_OTEL_* env set, main()'s init_telemetry call is a no-op
    (matches the API's default-off behaviour) and never raises."""
    monkeypatch.delenv("MINTMORY_OTEL_ENABLED", raising=False)
    monkeypatch.setattr(telemetry, "_endpoint_reachable", lambda url, timeout=0.1: False)
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: None)
    monkeypatch.setattr("sys.argv", ["mintmory-mcp"])

    server.main()  # must not raise
