"""
Tests for GET /healthz, GET /readyz (health endpoints) and the telemetry
default-off / enabled+otlp paths added in MM-42.

Mirrors the TestClient fixture pattern from test_routes.py.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mintmory.api import app as app_module


@pytest.fixture
def client(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """A TestClient backed by a throwaway DB, with the global store reset."""
    db_file = tmp_path / "health_test.db"  # type: ignore[operator]
    monkeypatch.setenv("MINTMORY_DB", str(db_file))
    monkeypatch.setattr(app_module, "_store", None)
    with TestClient(app_module.app) as test_client:
        yield test_client
    monkeypatch.setattr(app_module, "_store", None)


# ---------------------------------------------------------------------------
# GET /healthz
# ---------------------------------------------------------------------------


def test_healthz_returns_200_and_ok_body(client: TestClient) -> None:
    """GET /healthz must return 200 {"status": "ok"} without touching the DB."""
    resp = client.get("/healthz")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /readyz
# ---------------------------------------------------------------------------


def test_readyz_returns_200_and_ready_with_store_up(client: TestClient) -> None:
    """GET /readyz returns 200 {"status": "ready"} when the DB is reachable."""
    resp = client.get("/readyz")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ready"}


def test_readyz_returns_503_when_select_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /readyz returns 503 when the DB execute raises an exception."""
    from mintmory.core.storage import StorageAdapter

    class _BrokenConnection:
        def execute(self, *args: Any, **kwargs: Any) -> Any:
            raise sqlite3.OperationalError("injected DB failure")

    monkeypatch.setattr(StorageAdapter, "connect", lambda self: _BrokenConnection())

    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json().get("detail") == "store not ready"


# ---------------------------------------------------------------------------
# Telemetry — default OFF
# ---------------------------------------------------------------------------


def test_telemetry_default_off_returns_false() -> None:
    """init_telemetry with enabled=False (the default) must return False."""
    from mintmory.core.config import OTelSettings
    from mintmory.core.telemetry import init_telemetry

    result = init_telemetry(OTelSettings())
    assert result is False


def test_telemetry_is_enabled_false_by_default() -> None:
    """is_enabled() must be False when OTel is not configured."""
    from mintmory.core.telemetry import is_enabled

    # The OTel SDK is not installed in this CI env (--extra cochange only),
    # so init_telemetry always returns False and _enabled stays False.
    assert is_enabled() is False


# ---------------------------------------------------------------------------
# Telemetry — enabled + otlp (requires SDK; skipped when absent)
# ---------------------------------------------------------------------------


def test_telemetry_metric_exporter_matches_configured_exporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """enabled + exporter='otlp' -> OTLP metric exporter; 'console' -> console.

    Requires the [otel] SDK (importorskip). We capture the exporter passed to the
    metric reader by wrapping PeriodicExportingMetricReader (delegating to the real
    reader so its construction succeeds) and assert the exporter TYPE for each
    branch — this actually exercises the new OTLP metric branch with a real SDK.
    """
    export_mod = pytest.importorskip("opentelemetry.sdk.metrics.export")
    me_mod = pytest.importorskip("opentelemetry.exporter.otlp.proto.http.metric_exporter")

    import mintmory.core.telemetry as telemetry_mod
    from mintmory.core.config import OTelSettings

    real_reader = export_mod.PeriodicExportingMetricReader
    captured: list[Any] = []

    def _recording_reader(exporter: Any, *args: Any, **kwargs: Any) -> Any:
        captured.append(exporter)
        return real_reader(exporter, *args, **kwargs)

    monkeypatch.setattr(export_mod, "PeriodicExportingMetricReader", _recording_reader)

    def _reset() -> None:
        # init_telemetry is idempotent; clear module state so each branch runs.
        telemetry_mod._enabled = False
        telemetry_mod._tracer = None
        telemetry_mod._meter = None

    try:
        _reset()
        assert telemetry_mod.init_telemetry(OTelSettings(enabled=True, exporter="otlp")) is True
        assert isinstance(captured[-1], me_mod.OTLPMetricExporter)

        _reset()
        assert telemetry_mod.init_telemetry(OTelSettings(enabled=True, exporter="console")) is True
        assert isinstance(captured[-1], export_mod.ConsoleMetricExporter)
    finally:
        _reset()
