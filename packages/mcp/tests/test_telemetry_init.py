"""
Regression test for the MCP entrypoint's OTel initialisation (bug: the deployed
mintmory-mcp SSE server never called init_telemetry(), so MINTMORY_OTEL_ENABLED=true
had no effect — only the REST API's lifespan did).

Mirrors packages/api/tests/test_health_and_otel.py's default-off assertion, but
exercises mintmory.mcp.server.main() itself. ``mcp.run`` is monkeypatched to a
no-op so the test doesn't block on a real server loop or transport.
"""

from __future__ import annotations

from typing import Any

import pytest
from mintmory.mcp import server


def test_main_initialises_telemetry_before_serving(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """main() must call init_telemetry() before mcp.run() starts handling requests."""
    calls: list[str] = []

    def _fake_init_telemetry(settings: Any = None, **kwargs: Any) -> bool:
        calls.append("init_telemetry")
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


def test_main_telemetry_default_off_is_safe(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """With no MINTMORY_OTEL_* env set, main()'s init_telemetry call is a no-op
    (matches the API's default-off behaviour) and never raises."""
    monkeypatch.delenv("MINTMORY_OTEL_ENABLED", raising=False)
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: None)
    monkeypatch.setattr("sys.argv", ["mintmory-mcp"])

    server.main()  # must not raise
