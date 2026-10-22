"""OTLP/HTTP export timeouts (task 4.2).

Spec: observability › Export never blocks or floods when the collector is absent -
"Export SHALL run off the calling thread with bounded queues and time out after
``MINTMORY_OTEL_EXPORT_TIMEOUT_S`` (default 3 s) unless an
``OTEL_EXPORTER_OTLP[_TRACES|_METRICS]_TIMEOUT`` is set."

The OTLP/HTTP exporters receive ``timeout=settings.export_timeout_s``; when a standard timeout
variable applies to a signal, MintMory passes no ``timeout`` and lets the SDK read the variable
(so an invalid one surfaces as the exporter's own ``ValueError``). The periodic metric reader
always gets ``export_timeout_millis`` from the same MintMory setting.

Both branches are pinned by recording the keyword arguments ``init_telemetry`` passes to the
OTLP exporter constructors and to ``PeriodicExportingMetricReader``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry

_ENDPOINT_VARIABLES = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
)
_TIMEOUT_VARIABLES = (
    "OTEL_EXPORTER_OTLP_TIMEOUT",
    "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT",
    "OTEL_EXPORTER_OTLP_METRICS_TIMEOUT",
)


class _RecordingSpanExporter:
    """Stands in for ``OTLPSpanExporter`` and records its constructor keyword arguments."""

    records: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        _RecordingSpanExporter.records.append(kwargs)

    def export(self, spans: Any) -> Any:
        from opentelemetry.sdk.trace.export import SpanExportResult

        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


class _RecordingMetricExporter:
    """Stands in for ``OTLPMetricExporter`` and records its constructor keyword arguments."""

    records: list[dict[str, Any]] = []
    # The periodic reader reads these off the exporter before it ever exports.
    _preferred_temporality: Any = {}
    _preferred_aggregation: Any = {}

    def __init__(self, **kwargs: Any) -> None:
        _RecordingMetricExporter.records.append(kwargs)

    def export(self, metrics_data: Any, timeout_millis: float = 10_000, **kwargs: Any) -> Any:
        from opentelemetry.sdk.metrics.export import MetricExportResult

        return MetricExportResult.SUCCESS

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
        return None

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default global providers.

    A successful init makes its providers global, and the OTel API allows that only once per
    process; resetting the once-guards keeps repeated inits in one test meaningful.
    """
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, list[dict[str, Any]]]]:
    """Patch the OTLP exporters and the periodic reader so ``init_telemetry`` calls recorders."""
    from opentelemetry.exporter.otlp.proto.http import metric_exporter, trace_exporter
    from opentelemetry.sdk.metrics import export as metrics_export

    _RecordingSpanExporter.records = []
    _RecordingMetricExporter.records = []
    reader_records: list[dict[str, Any]] = []
    real_reader = metrics_export.PeriodicExportingMetricReader

    def _reader(exporter: Any, **kwargs: Any) -> Any:
        reader_records.append(kwargs)
        return real_reader(exporter, **kwargs)

    monkeypatch.setattr(trace_exporter, "OTLPSpanExporter", _RecordingSpanExporter)
    monkeypatch.setattr(metric_exporter, "OTLPMetricExporter", _RecordingMetricExporter)
    monkeypatch.setattr(metrics_export, "PeriodicExportingMetricReader", _reader)
    yield {
        "spans": _RecordingSpanExporter.records,
        "metrics": _RecordingMetricExporter.records,
        "readers": reader_records,
    }


def _enable_otlp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both signals use the default OTLP exporter, with no standard variable in the way."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    for variable in _ENDPOINT_VARIABLES + _TIMEOUT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


@pytest.mark.l4("C-5412bab8", "C-18efd0f6")
def test_otlp_exporters_and_the_reader_take_the_mintmory_export_timeout(
    monkeypatch: pytest.MonkeyPatch,
    recorded: dict[str, list[dict[str, Any]]],
) -> None:
    """Without a standard timeout variable, both exporters and the reader use the setting."""
    _enable_otlp(monkeypatch)
    monkeypatch.setenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", "1.5")

    assert telemetry.init_telemetry() is True

    assert recorded["spans"][0]["timeout"] == 1.5
    assert recorded["metrics"][0]["timeout"] == 1.5
    assert recorded["readers"][0]["export_timeout_millis"] == 1500


@pytest.mark.l4("C-5412bab8", "C-18efd0f6")
def test_a_shared_standard_timeout_variable_defers_both_signals_to_the_sdk(
    monkeypatch: pytest.MonkeyPatch,
    recorded: dict[str, list[dict[str, Any]]],
) -> None:
    """A set ``OTEL_EXPORTER_OTLP_TIMEOUT`` is left for the SDK to read for every signal."""
    _enable_otlp(monkeypatch)
    monkeypatch.setenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", "1.5")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "9")

    assert telemetry.init_telemetry() is True

    assert "timeout" not in recorded["spans"][0], (
        "the SDK must read OTEL_EXPORTER_OTLP_TIMEOUT itself"
    )
    assert "timeout" not in recorded["metrics"][0], (
        "the SDK must read OTEL_EXPORTER_OTLP_TIMEOUT itself"
    )


@pytest.mark.l4("C-5412bab8", "C-18efd0f6")
def test_a_per_signal_timeout_variable_only_defers_that_signal(
    monkeypatch: pytest.MonkeyPatch,
    recorded: dict[str, list[dict[str, Any]]],
) -> None:
    """A traces-only timeout variable leaves metrics on the MintMory export timeout."""
    _enable_otlp(monkeypatch)
    monkeypatch.setenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", "1.5")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT", "9")

    assert telemetry.init_telemetry() is True

    assert "timeout" not in recorded["spans"][0], (
        "the SDK must read OTEL_EXPORTER_OTLP_TRACES_TIMEOUT itself"
    )
    assert recorded["metrics"][0]["timeout"] == 1.5
