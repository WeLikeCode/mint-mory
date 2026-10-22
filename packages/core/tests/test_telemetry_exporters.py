"""OTLP exporter construction and endpoint resolution (task 3.3).

Spec: observability › Exporter selection and endpoint resolution, and observability ›
Bounded flush on exit › Pending spans are delivered on exit.

The default exporter is OTLP over HTTP/protobuf. ``init_telemetry`` hands the OTLP/HTTP
exporter constructors their endpoint differently depending on the standard variables:

* when an endpoint variable is set, the exporter is built **without** ``endpoint`` so the
  SDK reads the variable itself and appends the signal path (``/v1/traces``, ``/v1/metrics``);
* with no endpoint variable, MintMory passes the local default ``http://localhost:4318``
  plus the signal path.

Both branches are pinned here by recording the keyword arguments ``init_telemetry`` passes to
the OTLP exporter constructors. The console exporters' ``out=sys.stderr`` is pinned by the
enablement suite's ``test_console_exporter_writes_to_stderr_never_stdout``.
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
def recorded_exporters(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[dict[str, list[dict[str, Any]]]]:
    """Patch the OTLP exporter classes so ``init_telemetry`` calls the recorders."""
    from opentelemetry.exporter.otlp.proto.http import metric_exporter, trace_exporter

    _RecordingSpanExporter.records = []
    _RecordingMetricExporter.records = []
    monkeypatch.setattr(trace_exporter, "OTLPSpanExporter", _RecordingSpanExporter)
    monkeypatch.setattr(metric_exporter, "OTLPMetricExporter", _RecordingMetricExporter)
    yield {"spans": _RecordingSpanExporter.records, "metrics": _RecordingMetricExporter.records}


def _clear_endpoint_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in _ENDPOINT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


@pytest.mark.l4("C-16b8c487")
def test_otlp_exporters_default_to_the_local_collector_with_signal_paths(
    monkeypatch: pytest.MonkeyPatch,
    recorded_exporters: dict[str, list[dict[str, Any]]],
) -> None:
    """With no endpoint variable, both OTLP exporters target localhost plus their signal path."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    _clear_endpoint_variables(monkeypatch)

    assert telemetry.init_telemetry() is True

    assert recorded_exporters["spans"][0].get("endpoint") == "http://localhost:4318/v1/traces"
    assert recorded_exporters["metrics"][0].get("endpoint") == "http://localhost:4318/v1/metrics"


@pytest.mark.l4("C-16b8c487", "C-aba1a372")
def test_otlp_traces_exporter_defers_to_a_traces_specific_variable(
    monkeypatch: pytest.MonkeyPatch,
    recorded_exporters: dict[str, list[dict[str, Any]]],
) -> None:
    """A set ``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`` is left for the SDK to append the path to.

    The metrics signal has no variable, so it still gets the local default plus its path.
    """
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    _clear_endpoint_variables(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://traces.invalid:4318/v1/traces")

    assert telemetry.init_telemetry() is True

    assert "endpoint" not in recorded_exporters["spans"][0], (
        "the SDK must read OTEL_EXPORTER_OTLP_TRACES_ENDPOINT itself and append the path"
    )
    assert recorded_exporters["metrics"][0].get("endpoint") == "http://localhost:4318/v1/metrics"


@pytest.mark.l4("C-aba1a372")
def test_otlp_exporters_defer_to_the_shared_variable_and_default_without_one(
    monkeypatch: pytest.MonkeyPatch,
    recorded_exporters: dict[str, list[dict[str, Any]]],
) -> None:
    """A shared endpoint variable is left for the SDK; without it, the local default applies."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    _clear_endpoint_variables(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://shared.invalid:4318")

    assert telemetry.init_telemetry() is True
    assert "endpoint" not in recorded_exporters["spans"][0], (
        "the SDK must read OTEL_EXPORTER_OTLP_ENDPOINT itself and append /v1/traces"
    )
    assert "endpoint" not in recorded_exporters["metrics"][0], (
        "the SDK must read OTEL_EXPORTER_OTLP_ENDPOINT itself and append /v1/metrics"
    )

    telemetry.reset_telemetry()
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    assert telemetry.init_telemetry() is True
    assert recorded_exporters["spans"][-1].get("endpoint") == "http://localhost:4318/v1/traces"
    assert recorded_exporters["metrics"][-1].get("endpoint") == "http://localhost:4318/v1/metrics"
