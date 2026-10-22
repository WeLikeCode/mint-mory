"""Export resilience, invalid-variable fallbacks and init-never-raises (task 4.1).

Spec: observability › Export never blocks or floods when the collector is absent,
observability › Invalid MintMory telemetry settings fall back, observability ›
Invalid standard OpenTelemetry variables fall back, observability › Telemetry init never raises.

These tests pin the runtime's failure paths:

* an export runs on the SDK's own thread, and a failing one is logged once per signal
  per failure streak on ``mintmory.telemetry`` while the noisy exporter logger is muted;
* a bad ``MINTMORY_OTEL_*`` value falls back with one WARNING naming it, and the fallback
  value still flows into ``init_telemetry``;
* an unknown standard exporter, protocol or sampler falls back, the protocol checked once
  even though it is shared, and the SDK's own sampler WARNING is left in place;
* an exception while building an exporter never escapes ``init_telemetry``: it returns
  False, releases what it built, logs only the exception's class, and a later init works;
* ``init_telemetry`` constructs ``OTelSettings()`` itself, so an invalid variable of another
  settings group cannot turn a span into a failure.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.config import OTelSettings

_ENDPOINT_VARIABLES = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
)


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default global providers.

    A successful init makes its providers global, and the OTel API lets that happen only once
    per process. Resetting the two once-guards keeps the ``get_tracer_provider()`` assertions
    and the ``force_flush()`` calls meaningful regardless of test order.
    """
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


def _mintmory_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """The messages WARNING-and-above records logged on ``mintmory.telemetry``."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "mintmory.telemetry" and record.levelno >= logging.WARNING
    ]


class _ScriptedSpanExporter:
    """A span exporter whose ``export`` runs a fixed script of results and exceptions."""

    def __init__(self, outcomes: Sequence[Any]) -> None:
        self._outcomes = list(outcomes)

    def export(self, spans: Any) -> Any:
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


class _ScriptedMetricExporter:
    """A metric exporter whose ``export`` runs a fixed script of results and exceptions."""

    def __init__(self, outcomes: Sequence[Any]) -> None:
        self._outcomes = list(outcomes)

    def export(self, metrics_data: Any, timeout_millis: float = 10_000, **kwargs: Any) -> Any:
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
        return None

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True


@pytest.mark.l4("C-18efd0f6")
def test_unreachable_collector_warns_once_and_mutes_the_exporter_logger(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    closed_port: int,
) -> None:
    """Three failed exports against a closed port: one WARNING, no exporter noise."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{closed_port}")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", "0.2")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "0.2")
    caplog.set_level(logging.DEBUG)

    assert telemetry.init_telemetry() is True

    from opentelemetry import trace as otel_trace

    provider: Any = otel_trace.get_tracer_provider()
    for _ in range(3):
        with telemetry.span("unreachable-probe"):
            pass
        provider.force_flush()

    messages = [record.getMessage() for record in caplog.records]
    failed = [message for message in messages if "telemetry: trace export failed" in message]
    assert len(failed) == 1, messages

    exporter_warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("opentelemetry.exporter") and record.levelno >= logging.WARNING
    ]
    assert exporter_warnings == [], exporter_warnings


@pytest.mark.l4("C-5412bab8")
def test_export_runs_off_the_caller_thread(
    monkeypatch: pytest.MonkeyPatch, closed_port: int
) -> None:
    """200 spans exported to a closed port are handed to the guard on another thread."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{closed_port}")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", "0.2")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "0.2")

    export_threads: list[int] = []
    original: Any = telemetry._GuardedSpanExporter.export

    def _recording(self: Any, spans: Any) -> Any:
        export_threads.append(threading.get_ident())
        return original(self, spans)

    monkeypatch.setattr(telemetry._GuardedSpanExporter, "export", _recording)

    assert telemetry.init_telemetry() is True
    test_thread = threading.get_ident()
    for _ in range(200):
        with telemetry.span("thread-probe"):
            pass
    with contextlib.suppress(NotImplementedError):
        telemetry.shutdown_telemetry()

    assert export_threads, "the guarded span exporter must receive the batch"
    assert all(thread != test_thread for thread in export_threads), export_threads


@pytest.mark.l4("C-cd710a4c")
def test_guards_log_once_per_signal_per_streak(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Four scripted exports per signal: failures, one recovery, one failure, one WARNING each."""
    from opentelemetry.sdk.metrics.export import MetricExportResult
    from opentelemetry.sdk.trace.export import SpanExportResult

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    caplog.set_level(logging.DEBUG, logger="mintmory.telemetry")

    span_guard = telemetry._GuardedSpanExporter(
        _ScriptedSpanExporter(
            [
                SpanExportResult.FAILURE,
                ConnectionError("boom"),
                SpanExportResult.SUCCESS,
                SpanExportResult.FAILURE,
            ]
        )
    )
    metric_guard = telemetry._GuardedMetricExporter(
        _ScriptedMetricExporter(
            [
                MetricExportResult.FAILURE,
                ConnectionError("boom"),
                MetricExportResult.SUCCESS,
                MetricExportResult.FAILURE,
            ]
        )
    )

    span_results = [span_guard.export([]) for _ in range(4)]
    metric_results = [metric_guard.export([]) for _ in range(4)]

    assert span_results == [
        SpanExportResult.FAILURE,
        SpanExportResult.FAILURE,
        SpanExportResult.SUCCESS,
        SpanExportResult.FAILURE,
    ]
    assert metric_results == [
        MetricExportResult.FAILURE,
        MetricExportResult.FAILURE,
        MetricExportResult.SUCCESS,
        MetricExportResult.FAILURE,
    ]

    messages = [record.getMessage() for record in caplog.records]
    assert sum("telemetry: trace export failed" in message for message in messages) == 2
    assert sum("telemetry: metric export failed" in message for message in messages) == 2
    assert sum("telemetry: trace export recovered" in message for message in messages) == 1
    assert sum("telemetry: metric export recovered" in message for message in messages) == 1

    # Without the endpoint variable the failures are DEBUG: not one WARNING.
    caplog.clear()
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    quiet_span = telemetry._GuardedSpanExporter(
        _ScriptedSpanExporter(
            [
                SpanExportResult.FAILURE,
                ConnectionError("boom"),
                SpanExportResult.SUCCESS,
                SpanExportResult.FAILURE,
            ]
        )
    )
    quiet_metric = telemetry._GuardedMetricExporter(
        _ScriptedMetricExporter(
            [
                MetricExportResult.FAILURE,
                ConnectionError("boom"),
                MetricExportResult.SUCCESS,
                MetricExportResult.FAILURE,
            ]
        )
    )
    quiet_span_results = [quiet_span.export([]) for _ in range(4)]
    quiet_metric_results = [quiet_metric.export([]) for _ in range(4)]

    assert quiet_span_results[0] == SpanExportResult.FAILURE
    assert quiet_metric_results[0] == MetricExportResult.FAILURE
    assert _mintmory_warnings(caplog) == []


@pytest.mark.l4("C-e1c42220")
def test_bad_mintmory_values_fall_back_and_flow_into_init(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Bad MINTMORY_OTEL_* values warn once each, fall back, and the settings still initialise."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "maybe")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "jaeger")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", "abc")
    caplog.set_level(logging.WARNING, logger="mintmory.telemetry")

    settings = OTelSettings()

    assert settings.enabled == "auto"
    assert settings.exporter == "otlp"
    assert settings.export_timeout_s == 3.0

    warnings = _mintmory_warnings(caplog)
    assert len(warnings) == 3, warnings
    for variable in (
        "MINTMORY_OTEL_ENABLED",
        "MINTMORY_OTEL_EXPORTER",
        "MINTMORY_OTEL_EXPORT_TIMEOUT_S",
    ):
        assert sum(variable in message for message in warnings) == 1, (variable, warnings)

    assert telemetry.init_telemetry(settings, span_exporter=InMemorySpanExporter()) is True
    telemetry.reset_telemetry()


@pytest.mark.l4("C-3852f755")
def test_bad_standard_values_fall_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """An unknown exporter and protocol warn once; the span lands on stderr."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.delenv("MINTMORY_OTEL_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "jaeger,console")
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "nonsense")
    monkeypatch.setattr(telemetry, "_endpoint_reachable", lambda url, timeout=0.1: True)
    caplog.set_level(logging.WARNING)

    assert telemetry.init_telemetry() is True
    with telemetry.span("console-probe"):
        pass
    try:
        telemetry.shutdown_telemetry()
    except NotImplementedError:
        from opentelemetry import trace as otel_trace

        provider: Any = otel_trace.get_tracer_provider()
        provider.force_flush()

    _out, err = capfd.readouterr()
    assert "console-probe" in err

    warnings = _mintmory_warnings(caplog)
    assert len(warnings) == 2, warnings
    assert sum("OTEL_TRACES_EXPORTER" in message for message in warnings) == 1, warnings
    assert sum("OTEL_EXPORTER_OTLP_PROTOCOL" in message for message in warnings) == 1, warnings

    sampler_warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name == "opentelemetry.sdk.trace.sampling" and record.levelno >= logging.WARNING
    ]
    assert any("Couldn't recognize sampler" in message for message in sampler_warnings), (
        sampler_warnings
    )


@pytest.mark.l4("C-c724dabe")
def test_init_never_raises_when_an_exporter_cannot_be_built(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A ValueError from the OTLP exporter is swallowed: False, one class-only WARNING."""
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "abc")
    exporter_logger = logging.getLogger("opentelemetry.exporter.otlp.proto.http")
    level_before = exporter_logger.level
    caplog.set_level(logging.DEBUG)

    try:
        result = telemetry.init_telemetry()
    except Exception as error:  # the requirement is that this never happens
        pytest.fail(f"init_telemetry raised {type(error).__name__}")

    assert result is False
    assert telemetry.is_enabled() is False
    assert not isinstance(otel_trace.get_tracer_provider(), TracerProvider)

    messages = [record.getMessage() for record in caplog.records]
    assert any("telemetry disabled: init failed (ValueError)" in message for message in messages), (
        messages
    )
    assert not any("could not convert" in message for message in messages), messages
    assert exporter_logger.level == level_before

    telemetry.reset_telemetry()
    assert telemetry.init_telemetry(span_exporter=InMemorySpanExporter()) is True


@pytest.mark.l4("C-044e54eb")
def test_init_ignores_another_invalid_settings_group(monkeypatch: pytest.MonkeyPatch) -> None:
    """MINTMORY_SUMMARY_CONCURRENCY=0 does not stop an injected init from tagging its spans."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("MINTMORY_SUMMARY_CONCURRENCY", "0")
    exporter = InMemorySpanExporter()

    assert (
        telemetry.init_telemetry(default_service_name="mintmory-cli", span_exporter=exporter)
        is True
    )
    with telemetry.span("cli-probe"):
        pass

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["cli-probe"]
    assert {span.resource.attributes.get("service.name") for span in spans} == {"mintmory-cli"}
