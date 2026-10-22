"""Task 2.1 gate: the deployment scenarios re-pinned under fresh names.

Spec: deployment › Telemetry activation at API startup.

Task 2.1 is the unit's final check (the ruff/format/mypy/coverage gates). It adds no
behaviour of its own, so the three API scenarios of the delta are re-pinned here against
the lifespan that already satisfies them (TDD exemption: already satisfied by task 1.3).
Each test starts the real ``mintmory.api.app.app`` under ``TestClient`` and asserts a
real, non-zero answer (the recorded activator arguments, the flushed call order), so it
fails on a base without the lifespan wiring.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mintmory.api import app as app_module
from mintmory.core import telemetry

_OTLP_ENDPOINT_VARIABLES = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
)


@pytest.fixture
def gate_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the API at a throwaway DB and reset the global store around startup."""
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "api_telemetry_gate.db"))
    monkeypatch.setattr(app_module, "_store", None)
    yield
    monkeypatch.setattr(app_module, "_store", None)


def _record_activator(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, dict[str, Any]]]:
    """Wrap ``mintmory.api.app.init_telemetry`` with a recorder that still initialises."""
    calls: list[tuple[Any, dict[str, Any]]] = []
    real_init = telemetry.init_telemetry

    def _record(settings: Any = None, **kwargs: Any) -> bool:
        calls.append((settings, kwargs))
        return real_init(settings, **kwargs)

    monkeypatch.setattr(app_module, "init_telemetry", _record)
    return calls


@pytest.mark.l4("C-5d7fad0c")
def test_gate_api_uses_noop_shim_without_a_collector(
    gate_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In ``auto`` with no collector the API stays off under ``mintmory-api``.

    The off result is the zero value, so the test also asserts the recorded activator
    argument (the non-zero default service name) and that the lifespan ran.
    """
    monkeypatch.delenv("MINTMORY_OTEL_ENABLED", raising=False)
    for variable in _OTLP_ENDPOINT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(telemetry, "_endpoint_reachable", lambda url, timeout=0.1: False)

    calls = _record_activator(monkeypatch)
    with TestClient(app_module.app) as client:
        assert client.get("/healthz").status_code == 200
        assert telemetry.is_enabled() is False

    assert calls, "the API lifespan must activate telemetry once at startup"
    _settings, kwargs = calls[0]
    assert kwargs.get("default_service_name") == "mintmory-api"


@pytest.mark.l4("C-59ff07c0")
def test_gate_api_enables_telemetry_when_configured(
    gate_db: None, monkeypatch: pytest.MonkeyPatch, closed_port: int
) -> None:
    """``MINTMORY_OTEL_ENABLED=true`` turns the API's telemetry on under ``mintmory-api``."""
    pytest.importorskip("opentelemetry.sdk")
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{closed_port}")

    calls = _record_activator(monkeypatch)
    with TestClient(app_module.app) as client:
        assert client.get("/healthz").status_code == 200
        assert telemetry.is_enabled() is True

    assert calls, "the API lifespan must activate telemetry once at startup"
    _settings, kwargs = calls[0]
    assert kwargs.get("default_service_name") == "mintmory-api"


@pytest.mark.l4("C-5fc161bb")
def test_gate_api_shutdown_flushes_then_closes_store(
    gate_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At shutdown the API flushes telemetry before closing the store."""
    calls: list[str] = []

    class _RecordingStore:
        def initialise(self) -> None:
            return None

        def close(self) -> None:
            calls.append("close")

    def _build_recording_store(*args: Any, **kwargs: Any) -> _RecordingStore:
        return _RecordingStore()

    def _record_shutdown(*args: Any, **kwargs: Any) -> None:
        calls.append("shutdown_telemetry")

    monkeypatch.setattr(app_module, "build_storage", _build_recording_store)
    monkeypatch.setattr(app_module, "shutdown_telemetry", _record_shutdown)

    with TestClient(app_module.app) as client:
        assert client.get("/healthz").status_code == 200

    assert calls == ["shutdown_telemetry", "close"]
