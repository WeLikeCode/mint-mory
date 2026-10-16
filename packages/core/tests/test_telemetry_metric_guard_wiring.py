"""The metric guard wraps the configured metric exporter (fix-1 task 1.2).

Spec: observability › _build_meter_provider must wrap the configured metric exporter with —
feedback FB-002:

    "WHEN a metric export fails because the configured OTLP collector is unreachable (endpoint
    on a closed port, three force_flush calls) THEN exactly one WARNING 'telemetry: metric
    export failed' is logged per failure streak on the mintmory.telemetry logger."

``_build_meter_provider`` has to hand the reader a ``_GuardedMetricExporter`` around the
configured exporter, exactly as ``_build_tracer_provider`` wraps its span exporter, so a metric
export that cannot reach the collector becomes a FAILURE that is logged once instead of raised
or flooded. The guard is a ``MetricExporter``, so it forwards the reader's temporality.

``_reset_telemetry`` here shadows the root ``conftest.py`` fixture of the same name for this
module only: these tests own the telemetry state they install and stay runnable (and fail by
assertion) against a unit base where ``telemetry.reset_telemetry`` is absent.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry


@pytest.fixture(autouse=True)
def _reset_telemetry() -> Iterator[None]:
    """Own this module's telemetry state; tolerate the helper being absent (unit base)."""
    reset = getattr(telemetry, "reset_telemetry", None)
    if reset is not None:
        reset()
    yield
    if reset is not None:
        reset()


def _metric_exporter_chain() -> list[Any]:
    """The metric exporter the reader got, then each ``_inner`` until an object has none."""
    provider = getattr(telemetry, "_meter_provider", None)
    assert provider is not None, "init did not install a meter provider"
    readers = list(provider._sdk_config.metric_readers)
    assert len(readers) == 1, readers
    exporter = getattr(readers[0], "_exporter", None)
    chain: list[Any] = []
    while exporter is not None:
        chain.append(exporter)
        exporter = getattr(exporter, "_inner", None)
    return chain


@pytest.mark.l4("C-0f789a7e")
def test_metric_guard_wraps_the_otlp_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    """The OTLP metric path is ``_GuardedMetricExporter(OTLPMetricExporter)``."""
    me_mod = pytest.importorskip("opentelemetry.exporter.otlp.proto.http.metric_exporter")

    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)

    assert telemetry.init_telemetry() is True

    chain = _metric_exporter_chain()
    assert len(chain) == 2, chain
    assert isinstance(chain[0], telemetry._GuardedMetricExporter)
    assert isinstance(chain[1], me_mod.OTLPMetricExporter)
    assert chain[0]._inner is chain[1]


@pytest.mark.l4("C-0f789a7e")
def test_metric_guard_wraps_the_console_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    """The console metric path is ``_GuardedMetricExporter(ConsoleMetricExporter)``."""
    export_mod = pytest.importorskip("opentelemetry.sdk.metrics.export")

    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "console")
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)

    assert telemetry.init_telemetry() is True

    chain = _metric_exporter_chain()
    assert len(chain) == 2, chain
    assert isinstance(chain[0], telemetry._GuardedMetricExporter)
    assert isinstance(chain[1], export_mod.ConsoleMetricExporter)
    assert chain[0]._inner is chain[1]


@pytest.mark.l4("C-0f789a7e")
def test_unreachable_metric_collector_warns_once(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    closed_port: int,
) -> None:
    """Three failed metric exports against a closed port: one WARNING, then silence."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{closed_port}")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", "0.2")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "0.2")
    caplog.set_level(logging.DEBUG, logger="mintmory.telemetry")

    assert telemetry.init_telemetry() is True

    provider: Any = telemetry._meter_provider
    assert provider is not None
    for _ in range(3):
        telemetry.add_count("metric-guard-probe", 1)
        provider.force_flush()

    failed = [
        record.getMessage()
        for record in caplog.records
        if "telemetry: metric export failed" in record.getMessage()
    ]
    assert len(failed) == 1, failed
