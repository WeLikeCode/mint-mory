"""Task 9.1 gate: the whole observability delta re-pinned under fresh names.

Spec: ``openspec/changes/add-telemetry-runtime/specs/observability/spec.md``.

Task 9.1 is the unit's final check (the ``telemetry.py`` docstring update and the
ruff/mypy/pytest gates). It adds no behaviour of its own, so every scenario of the
delta is re-pinned here, once more, against the runtime that already satisfies it
(TDD exemption: already satisfied by tasks 1-8). Each test drives the public seam or
the module state the spec names and asserts a real, non-empty answer, so it fails on
the pre-unit base where only the no-op shim exists.

Helpers tolerate a missing symbol (``getattr``/``try``) and turn it into an assertion
failure rather than an error, so a unit base without the runtime fails by assertion.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.config import OTelSettings

_RESULT_MARKER = "L4-RESULT:"
_SENTINEL = "SENTINEL-91c2"

_ENDPOINT_VARIABLES = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
)
_SERVICE_VARIABLES = (
    "OTEL_SERVICE_NAME",
    "OTEL_RESOURCE_ATTRIBUTES",
    "MINTMORY_OTEL_SERVICE_NAME",
)

_SUBPROCESS_PROBE = r"""
import json
import sys

from mintmory.core import telemetry

probe_calls = []


def _reachable(url, timeout=0.1):
    probe_calls.append(url)
    return False


telemetry._endpoint_reachable = _reachable
result = telemetry.init_telemetry()
print("L4-RESULT:" + json.dumps({
    "result": result,
    "sdk_imported": "opentelemetry.sdk" in sys.modules,
    "probe_calls": probe_calls,
}))
"""


@pytest.fixture(autouse=True)
def _reset_telemetry() -> Iterator[None]:
    """Own this module's telemetry state; tolerate the helper being absent (unit base)."""
    reset = getattr(telemetry, "reset_telemetry", None)
    if reset is not None:
        reset()
    yield
    if reset is not None:
        reset()


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default global providers.

    A successful init makes its providers global and the OTel API allows that only once
    per process; resetting the once-guards keeps repeated inits in one test meaningful.
    """
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


def _init(**kwargs: Any) -> Any:
    """The test seam; a unit base without it is a failure, not an error."""
    try:
        return telemetry.init_telemetry(**kwargs)
    except TypeError:
        return "init_telemetry is missing the test seam"


def _require(name: str) -> Any:
    """A module symbol this task's scenario names; missing is a failure, not an error."""
    value = getattr(telemetry, name, None)
    assert value is not None, f"telemetry.{name} is missing"
    return value


def _require_shutdown() -> Any:
    """The one teardown the spec names; a missing one is a failure, not an error."""
    shutdown = getattr(telemetry, "shutdown_telemetry", None)
    assert shutdown is not None, "shutdown_telemetry is missing"
    return shutdown


def _in_memory_span_exporter() -> Any:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    return InMemorySpanExporter()


def _in_memory_metric_reader() -> Any:
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    return InMemoryMetricReader()


def _span_names(exporter: Any) -> list[str]:
    return [span.name for span in exporter.get_finished_spans()]


def _metric_names(reader: Any) -> list[str]:
    data = reader.get_metrics_data()
    if data is None:
        return []
    names: list[str] = []
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                names.append(metric.name)
    return names


def _otel_messages(caplog: pytest.LogCaptureFixture, level: int = logging.WARNING) -> list[str]:
    """Messages WARNING-and-above logged on ``mintmory.telemetry``."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "mintmory.telemetry" and record.levelno >= level
    ]


def _clear_endpoint_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in _ENDPOINT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


# ---------------------------------------------------------------------------
# Telemetry enablement modes
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-2190b9f3")
def test_gate_auto_without_collector_stays_off_in_a_fresh_process() -> None:
    """auto, no endpoint variable, unreachable endpoint: False and the SDK is never imported."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("MINTMORY_OTEL_") and not key.startswith("OTEL_")
    }
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_PROBE],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    result_lines = [line for line in proc.stdout.splitlines() if line.startswith(_RESULT_MARKER)]
    assert result_lines, proc.stdout
    payload: dict[str, Any] = json.loads(result_lines[0][len(_RESULT_MARKER) :])
    assert payload["result"] is False
    assert payload["sdk_imported"] is False, "a no-op auto init must not import opentelemetry.sdk"
    assert payload["probe_calls"], "auto with no endpoint variable must probe the default endpoint"


@pytest.mark.l4("C-aba1a372")
def test_gate_auto_turns_on_with_a_collector(
    monkeypatch: pytest.MonkeyPatch, otlp_receiver: Any
) -> None:
    """auto exports when the probe finds a collector, and skips the probe when one is configured."""
    monkeypatch.delenv("MINTMORY_OTEL_ENABLED", raising=False)
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "console")
    _clear_endpoint_variables(monkeypatch)
    calls: list[str] = []

    def _reachable(url: str, timeout: float = 0.1) -> bool:
        calls.append(url)
        return True

    monkeypatch.setattr(telemetry, "_endpoint_reachable", _reachable, raising=False)

    assert telemetry.init_telemetry() is True
    assert calls, "auto with no endpoint variable must probe the default endpoint"

    telemetry.reset_telemetry()
    monkeypatch.delenv("MINTMORY_OTEL_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", otlp_receiver.endpoint)
    probes: list[str] = []

    def _unexpected(url: str, timeout: float = 0.1) -> bool:
        probes.append(url)
        return False

    monkeypatch.setattr(telemetry, "_endpoint_reachable", _unexpected, raising=False)

    assert telemetry.init_telemetry() is True
    assert probes == [], "an explicit endpoint variable must skip the reachability probe"


@pytest.mark.l4("C-9d8f8f9c")
def test_gate_explicit_off_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither MINTMORY_OTEL_ENABLED=false nor OTEL_SDK_DISABLED=true initialises telemetry."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "false")
    assert telemetry.init_telemetry() is False

    telemetry.reset_telemetry()
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "TRUE")
    assert telemetry.init_telemetry() is False

    telemetry.reset_telemetry()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "console")
    assert telemetry.init_telemetry() is True


@pytest.mark.l4("C-ead28cef")
def test_gate_sdk_missing_warns_only_with_a_hint(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Without the SDK: False always; one install-hint warning iff the mode/endpoint asked."""
    monkeypatch.setattr(telemetry, "_sdk_available", lambda: False, raising=False)
    monkeypatch.setattr(
        telemetry, "_endpoint_reachable", lambda url, timeout=0.1: False, raising=False
    )
    caplog.set_level(logging.WARNING, logger="mintmory.telemetry")

    # (a) explicit true, no endpoint variable -> one hint
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    _clear_endpoint_variables(monkeypatch)
    caplog.clear()
    assert telemetry.init_telemetry() is False
    warnings = _otel_messages(caplog)
    assert len(warnings) == 1, warnings
    assert "mintmory-core[otel]" in warnings[0]

    # (b) auto + an endpoint variable -> one hint
    telemetry.reset_telemetry()
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "auto")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://127.0.0.1:4318/v1/traces")
    caplog.clear()
    assert telemetry.init_telemetry() is False
    warnings = _otel_messages(caplog)
    assert len(warnings) == 1, warnings
    assert "mintmory-core[otel]" in warnings[0]

    # (c) auto, nothing asked for -> silence
    telemetry.reset_telemetry()
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "auto")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    caplog.clear()
    assert telemetry.init_telemetry() is False
    assert _otel_messages(caplog) == []


# ---------------------------------------------------------------------------
# Exporter selection and endpoint resolution
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-4d7716fe")
def test_gate_console_output_never_reaches_stdout(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """MINTMORY_OTEL_EXPORTER=console keeps stdout clean and puts the span on stderr."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "console")
    shutdown = _require_shutdown()

    assert telemetry.init_telemetry() is True
    with telemetry.span("console-probe"):
        pass
    shutdown()

    out, err = capfd.readouterr()
    assert out == "", "the console exporter must never write to stdout (the MCP stdio stream)"
    assert "console-probe" in err


@pytest.mark.l4("C-6fc7f4c6")
@pytest.mark.parametrize(
    ("traces", "metrics", "disabled_signal"),
    [
        ("console", "none", "metric"),
        ("none", "console", "tracer"),
    ],
)
def test_gate_one_signal_switched_off_builds_no_provider_for_it(
    monkeypatch: pytest.MonkeyPatch, traces: str, metrics: str, disabled_signal: str
) -> None:
    """`none` for a signal builds no provider; the other signal still exports."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.delenv("MINTMORY_OTEL_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", traces)
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", metrics)

    assert telemetry.init_telemetry() is True

    if disabled_signal == "metric":
        from opentelemetry import metrics as otel_metrics
        from opentelemetry.sdk.metrics import MeterProvider

        assert telemetry._meter is None
        assert not isinstance(otel_metrics.get_meter_provider(), MeterProvider)
        telemetry.record_value("x", 1.0)
    else:
        from opentelemetry import trace as otel_trace
        from opentelemetry.sdk.trace import TracerProvider

        assert telemetry._tracer is None
        assert not isinstance(otel_trace.get_tracer_provider(), TracerProvider)
        with telemetry.span("a") as sp:
            assert isinstance(sp, telemetry._NoopSpan)


@pytest.mark.l4("C-690840ae")
def test_gate_both_signals_off_returns_false_without_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """MINTMORY_OTEL_EXPORTER=none with enabled=true is a clean, silent no-op."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "none")
    caplog.set_level(logging.WARNING, logger="mintmory.telemetry")

    assert telemetry.init_telemetry() is False
    assert telemetry.is_enabled() is False
    assert _otel_messages(caplog) == []

    telemetry.reset_telemetry()
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "console")
    assert telemetry.init_telemetry() is True


# ---------------------------------------------------------------------------
# Export never blocks or floods when the collector is absent
# ---------------------------------------------------------------------------
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


@pytest.mark.l4("C-5412bab8")
def test_gate_export_runs_off_the_calling_thread(
    monkeypatch: pytest.MonkeyPatch, closed_port: int
) -> None:
    """200 spans exported to a closed port are handed to the guard on another thread."""
    guard_class = _require("_GuardedSpanExporter")
    shutdown = _require_shutdown()
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{closed_port}")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", "0.2")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "0.2")

    export_threads: list[int] = []
    original: Any = guard_class.export

    def _recording(self: Any, spans: Any) -> Any:
        export_threads.append(threading.get_ident())
        return original(self, spans)

    monkeypatch.setattr(guard_class, "export", _recording)

    assert telemetry.init_telemetry() is True
    test_thread = threading.get_ident()
    for _ in range(200):
        with telemetry.span("thread-probe"):
            pass
    shutdown()

    assert export_threads, "the guarded span exporter must receive the batch"
    assert all(thread != test_thread for thread in export_threads), export_threads


@pytest.mark.l4("C-18efd0f6")
def test_gate_unreachable_collector_logs_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, closed_port: int
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
    assert sum("telemetry: trace export failed" in message for message in messages) == 1, messages

    exporter_warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("opentelemetry.exporter") and record.levelno >= logging.WARNING
    ]
    assert exporter_warnings == [], exporter_warnings


@pytest.mark.l4("C-cd710a4c")
def test_gate_guard_logs_once_per_signal_per_streak(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Four scripted exports per signal: one failure WARNING each and one recovery INFO each."""
    from opentelemetry.sdk.metrics.export import MetricExportResult
    from opentelemetry.sdk.trace.export import SpanExportResult

    guard_class = _require("_GuardedSpanExporter")
    metric_guard_class = _require("_GuardedMetricExporter")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    caplog.set_level(logging.DEBUG, logger="mintmory.telemetry")

    span_guard = guard_class(
        _ScriptedSpanExporter(
            [
                SpanExportResult.FAILURE,
                ConnectionError("boom"),
                SpanExportResult.SUCCESS,
                SpanExportResult.FAILURE,
            ]
        )
    )
    metric_guard = metric_guard_class(
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

    caplog.clear()
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    quiet_span = guard_class(
        _ScriptedSpanExporter(
            [
                SpanExportResult.FAILURE,
                ConnectionError("boom"),
                SpanExportResult.SUCCESS,
                SpanExportResult.FAILURE,
            ]
        )
    )
    quiet_metric = metric_guard_class(
        _ScriptedMetricExporter(
            [
                MetricExportResult.FAILURE,
                ConnectionError("boom"),
                MetricExportResult.SUCCESS,
                MetricExportResult.FAILURE,
            ]
        )
    )
    assert quiet_span.export([]) == SpanExportResult.FAILURE
    assert quiet_metric.export([]) == MetricExportResult.FAILURE
    assert _otel_messages(caplog) == []


# ---------------------------------------------------------------------------
# Invalid MintMory telemetry settings fall back
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-e1c42220")
def test_gate_bad_mintmory_values_fall_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A bad enabled/exporter/timeout warns once and falls back; construction does not raise."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "maybe")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "jaeger")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", "abc")
    caplog.set_level(logging.WARNING)

    settings = OTelSettings()

    assert settings.enabled == "auto"
    assert settings.exporter == "otlp"
    assert settings.export_timeout_s == 3.0

    warnings = _otel_messages(caplog)
    assert len(warnings) == 3, warnings
    for variable in (
        "MINTMORY_OTEL_ENABLED",
        "MINTMORY_OTEL_EXPORTER",
        "MINTMORY_OTEL_EXPORT_TIMEOUT_S",
    ):
        assert sum(variable in message for message in warnings) == 1, (variable, warnings)


# ---------------------------------------------------------------------------
# Invalid standard OpenTelemetry variables fall back
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-3852f755")
def test_gate_bad_standard_values_fall_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """An unknown exporter and protocol warn once; the span lands on stderr."""
    shutdown = _require_shutdown()
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.delenv("MINTMORY_OTEL_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "jaeger,console")
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "nonsense")
    monkeypatch.setattr(
        telemetry, "_endpoint_reachable", lambda url, timeout=0.1: True, raising=False
    )
    caplog.set_level(logging.WARNING)

    assert telemetry.init_telemetry() is True
    with telemetry.span("console-probe"):
        pass
    shutdown()

    _out, err = capfd.readouterr()
    assert "console-probe" in err

    warnings = _otel_messages(caplog)
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


# ---------------------------------------------------------------------------
# Telemetry init never raises
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-c724dabe")
def test_gate_init_failure_turns_telemetry_off(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A ValueError from the OTLP exporter is swallowed: False, one class-only WARNING."""
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace import TracerProvider

    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "abc")
    exporter_logger = logging.getLogger("opentelemetry.exporter.otlp.proto.http")
    level_before = exporter_logger.level
    caplog.set_level(logging.DEBUG)

    result = telemetry.init_telemetry()

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
    assert _init(span_exporter=_in_memory_span_exporter()) is True


@pytest.mark.l4("C-044e54eb")
def test_gate_another_settings_group_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """MINTMORY_SUMMARY_CONCURRENCY=0 does not stop an injected init from tagging its spans."""
    monkeypatch.setenv("MINTMORY_SUMMARY_CONCURRENCY", "0")
    exporter = _in_memory_span_exporter()

    assert _init(default_service_name="mintmory-cli", span_exporter=exporter) is True

    with telemetry.span("cli-probe"):
        pass

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["cli-probe"]
    assert {span.resource.attributes.get("service.name") for span in spans} == {"mintmory-cli"}


# ---------------------------------------------------------------------------
# Bounded flush on exit
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-b7126d33")
def test_gate_exit_is_bounded_when_export_hangs() -> None:
    """A ``shutdown`` that never returns cannot hold the caller; the state is cleared regardless."""
    from opentelemetry.sdk.trace.export import SpanExportResult

    shutdown = _require_shutdown()
    release = threading.Event()

    class _StuckShutdownExporter:
        def export(self, spans: Any) -> Any:
            return SpanExportResult.SUCCESS

        def shutdown(self) -> None:
            release.wait(5.0)

        def force_flush(self, timeout_millis: int = 30_000) -> bool:
            return True

    assert _init(span_exporter=_StuckShutdownExporter()) is True
    assert telemetry.is_enabled() is True

    started = time.monotonic()
    try:
        shutdown(timeout_s=0.2)
        elapsed = time.monotonic() - started

        assert elapsed < 1.0, elapsed
        assert telemetry.is_enabled() is False
        assert telemetry._tracer is None
        assert telemetry._tracer_provider is None

        parked = [
            thread
            for thread in threading.enumerate()
            if thread.name == "mintmory-telemetry-shutdown"
        ]
        assert parked, [thread.name for thread in threading.enumerate()]
        assert all(thread.daemon for thread in parked)
    finally:
        release.set()
        for thread in threading.enumerate():
            if thread.name == "mintmory-telemetry-shutdown":
                thread.join(timeout=2.0)


@pytest.mark.l4("C-16b8c487")
def test_gate_pending_spans_are_delivered_on_exit(
    monkeypatch: pytest.MonkeyPatch, otlp_receiver: Any
) -> None:
    """A span that ends just before exit is flushed to the collector on the way out."""
    shutdown = _require_shutdown()
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", otlp_receiver.endpoint)

    assert telemetry.init_telemetry() is True

    with telemetry.span("x"):
        pass
    shutdown()

    assert "/v1/traces" in [path for path, _ in otlp_receiver.requests]
    assert "x" in [name for name, _ in otlp_receiver.spans()]
    assert telemetry.is_enabled() is False
    assert telemetry._tracer is None


@pytest.mark.l4("C-1d2bd9a4")
def test_gate_exporter_logger_level_is_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    """CRITICAL while telemetry runs; the level saved before the first mute afterwards."""
    shutdown = _require_shutdown()
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")

    exporter_logger = logging.getLogger("opentelemetry.exporter.otlp.proto.http")
    exporter_logger.setLevel(logging.NOTSET)

    assert telemetry.init_telemetry() is True
    assert exporter_logger.level == logging.CRITICAL

    shutdown()
    assert exporter_logger.level == logging.NOTSET

    assert telemetry.init_telemetry() is True
    assert exporter_logger.level == logging.CRITICAL

    shutdown()
    assert exporter_logger.level == logging.NOTSET


@pytest.mark.l4("C-fa66b065")
def test_gate_one_atexit_hook_none_from_the_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """One hook however often a process re-initialises; the reset re-arms it once more."""
    shutdown = _require_shutdown()
    reset = getattr(telemetry, "reset_telemetry", None)
    assert reset is not None, "reset_telemetry is missing"

    calls: list[Any] = []
    monkeypatch.setattr(atexit, "register", calls.append)

    assert (
        _init(span_exporter=_in_memory_span_exporter(), metric_reader=_in_memory_metric_reader())
        is True
    )
    assert (
        _init(span_exporter=_in_memory_span_exporter(), metric_reader=_in_memory_metric_reader())
        is True
    )

    assert telemetry._atexit_registered is True
    tracer_provider = telemetry._tracer_provider
    meter_provider = telemetry._meter_provider
    assert tracer_provider is not None
    assert meter_provider is not None
    assert tracer_provider._atexit_handler is None
    assert meter_provider._atexit_handler is None
    assert calls == [shutdown]

    shutdown()
    assert telemetry._atexit_registered is True
    assert (
        _init(span_exporter=_in_memory_span_exporter(), metric_reader=_in_memory_metric_reader())
        is True
    )
    assert calls == [shutdown]

    reset()
    assert telemetry._atexit_registered is False
    assert (
        _init(span_exporter=_in_memory_span_exporter(), metric_reader=_in_memory_metric_reader())
        is True
    )
    assert calls == [shutdown, shutdown]


# ---------------------------------------------------------------------------
# Resource identifies the process
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-a58004cf")
def test_gate_resource_uses_the_callers_default_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no service-name variable, the entry point's default names the process."""
    for variable in _SERVICE_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    exporter = _in_memory_span_exporter()

    assert _init(default_service_name="mintmory-cli", span_exporter=exporter) is True
    with telemetry.span("cli"):
        pass

    assert _span_names(exporter) == ["cli"], _span_names(exporter)
    attributes = dict(exporter.get_finished_spans()[0].resource.attributes)
    assert attributes.get("service.name") == "mintmory-cli", attributes
    assert attributes.get("service.version"), attributes


@pytest.mark.l4("C-a556a3c6")
def test_gate_standard_variables_win(monkeypatch: pytest.MonkeyPatch) -> None:
    """``OTEL_SERVICE_NAME`` beats MintMory's; ``OTEL_RESOURCE_ATTRIBUTES`` overrides the rest."""
    monkeypatch.setenv("OTEL_SERVICE_NAME", "memo")
    monkeypatch.setenv("MINTMORY_OTEL_SERVICE_NAME", "other")
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES", "deployment.environment.name=dev,service.namespace=team"
    )
    exporter = _in_memory_span_exporter()

    assert _init(default_service_name="mintmory-cli", span_exporter=exporter) is True
    with telemetry.span("a"):
        pass

    assert _span_names(exporter) == ["a"], _span_names(exporter)
    attributes = dict(exporter.get_finished_spans()[0].resource.attributes)
    assert attributes.get("service.name") == "memo", attributes
    assert attributes.get("deployment.environment.name") == "dev", attributes
    assert attributes.get("service.namespace") == "team", attributes


# ---------------------------------------------------------------------------
# Sampling and propagation follow the OpenTelemetry environment
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-19d78666")
def test_gate_context_propagates_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API's W3C propagator injects the current span's trace and span ids."""
    from opentelemetry import propagate

    exporter = _in_memory_span_exporter()
    assert _init(span_exporter=exporter) is True

    carrier: dict[str, str] = {}
    with telemetry.span("parent") as span:
        propagate.inject(carrier)
        context = getattr(span, "get_span_context", lambda: None)()

    assert context is not None, "telemetry.span did not yield an SDK span"
    assert context.is_valid is True
    assert "traceparent" in carrier, carrier
    assert format(context.trace_id, "032x") in carrier["traceparent"], carrier
    assert format(context.span_id, "016x") in carrier["traceparent"], carrier


@pytest.mark.l4("C-50f410cd")
def test_gate_sampling_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """``OTEL_TRACES_SAMPLER=always_off`` drops every span; the default sampler keeps them."""
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "always_off")
    exporter = _in_memory_span_exporter()
    assert _init(span_exporter=exporter) is True
    with telemetry.span("dropped"):
        pass
    assert _span_names(exporter) == [], _span_names(exporter)

    reset = getattr(telemetry, "reset_telemetry", None)
    assert reset is not None, "reset_telemetry is missing"
    reset()
    monkeypatch.delenv("OTEL_TRACES_SAMPLER", raising=False)

    default_exporter = _in_memory_span_exporter()
    assert _init(span_exporter=default_exporter) is True
    with telemetry.span("kept"):
        pass
    assert _span_names(default_exporter) == ["kept"], _span_names(default_exporter)


# ---------------------------------------------------------------------------
# Exported spans carry no exception message
# ---------------------------------------------------------------------------
def _record_failing_exception(span: Any) -> None:
    """Record the sentinel exception and end the span with an ERROR status carrying it too."""
    from opentelemetry.trace import Status, StatusCode

    span.record_exception(RuntimeError(_SENTINEL))
    span.set_status(Status(StatusCode.ERROR, _SENTINEL))


@pytest.mark.l4("C-1457e823")
def test_gate_library_exception_is_scrubbed() -> None:
    """A library's recorded exception reaches the exporter as its type only."""
    from opentelemetry import trace
    from opentelemetry.trace import StatusCode

    exporter = _in_memory_span_exporter()
    assert _init(span_exporter=exporter) is True

    tracer = trace.get_tracer("library")
    with tracer.start_as_current_span("library-span") as span:
        _record_failing_exception(span)

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["library-span"]
    exported = spans[0]
    events = [event for event in exported.events if event.name == "exception"]
    assert len(events) == 1
    assert events[0].attributes.get("exception.type") == "RuntimeError"
    assert all(_SENTINEL not in str(value) for value in dict(events[0].attributes).values())
    assert exported.status.status_code == StatusCode.ERROR
    assert _SENTINEL not in (exported.status.description or "")
    assert _SENTINEL not in str(dict(exported.attributes))


# ---------------------------------------------------------------------------
# One error-marking helper
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-65be7944")
def test_gate_marking_a_span_on() -> None:
    """An SDK span marked failed exports with ERROR, no description and ``error.type``."""
    from opentelemetry.trace import StatusCode

    mark_error = _require("mark_error")
    exporter = _in_memory_span_exporter()
    assert _init(span_exporter=exporter) is True

    with telemetry.span("a") as sp:
        mark_error(sp, "RuntimeError")

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["a"]
    finished = spans[0]
    assert finished.status.status_code == StatusCode.ERROR
    assert not finished.status.description
    assert finished.attributes is not None
    assert finished.attributes["error.type"] == "RuntimeError"


@pytest.mark.l4("C-65be7944")
def test_gate_marking_a_span_off() -> None:
    """With telemetry off, ``mark_error`` accepts a ``_NoopSpan`` and never raises."""
    mark_error = _require("mark_error")

    with telemetry.span("a") as sp:
        assert isinstance(sp, telemetry._NoopSpan)
        mark_error(sp, "RuntimeError")


# ---------------------------------------------------------------------------
# Telemetry test seam
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-e8aa74fe")
def test_gate_injection_beats_the_suites_off_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """An injected exporter enables export despite ``MINTMORY_OTEL_ENABLED=false``."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "false")
    exporter = _in_memory_span_exporter()

    assert _init(span_exporter=exporter) is True
    with telemetry.span("injected"):
        pass

    assert _span_names(exporter) == ["injected"], _span_names(exporter)
    assert telemetry.is_enabled() is True


@pytest.mark.l4("C-90d20140")
def test_gate_single_injection_builds_no_network_exporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An injected signal leaves the other off and never constructs a configured exporter."""
    from opentelemetry.exporter.otlp.proto.http import metric_exporter, trace_exporter

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")

    class _Exploding:
        def __init__(self, **kwargs: Any) -> None:
            raise AssertionError("an injected signal must not build a configured exporter")

    monkeypatch.setattr(trace_exporter, "OTLPSpanExporter", _Exploding)
    monkeypatch.setattr(metric_exporter, "OTLPMetricExporter", _Exploding)

    span_exporter = _in_memory_span_exporter()
    assert _init(span_exporter=span_exporter) is True
    assert telemetry._meter is None
    with telemetry.span("only-traces"):
        pass
    assert _span_names(span_exporter) == ["only-traces"], _span_names(span_exporter)

    reset = getattr(telemetry, "reset_telemetry", None)
    assert reset is not None, "reset_telemetry is missing"
    reset()

    reader = _in_memory_metric_reader()
    assert _init(metric_reader=reader) is True
    assert telemetry._tracer is None
    telemetry.record_value("x", 1.0)
    assert "x" in _metric_names(reader), _metric_names(reader)


# ---------------------------------------------------------------------------
# Global providers and repeated init
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-59c09ecd")
def test_gate_a_second_init_changes_nothing() -> None:
    """A later init returns True and leaves the first exporter in place."""
    first = _in_memory_span_exporter()
    assert _init(span_exporter=first) is True

    second = _in_memory_span_exporter()
    assert _init(span_exporter=second) is True

    with telemetry.span("kept"):
        pass

    assert _span_names(first) == ["kept"], _span_names(first)
    assert _span_names(second) == [], _span_names(second)


@pytest.mark.l4("C-836e8777")
def test_gate_reinitialisation_after_shutdown() -> None:
    """Both a MintMory span and a library span reach the second exporter after a shutdown."""
    from opentelemetry import trace

    shutdown = _require_shutdown()
    first = _in_memory_span_exporter()
    assert _init(span_exporter=first) is True
    with telemetry.span("one"):
        pass
    assert _span_names(first) == ["one"], _span_names(first)

    shutdown()

    second = _in_memory_span_exporter()
    assert _init(span_exporter=second) is True
    with telemetry.span("two"):
        pass
    with trace.get_tracer("x").start_as_current_span("three"):
        pass

    assert sorted(_span_names(second)) == ["three", "two"], _span_names(second)
    assert _span_names(first) == ["one"], _span_names(first)


# ---------------------------------------------------------------------------
# Shared telemetry test fixtures (the reset default, exercised in-process)
# ---------------------------------------------------------------------------
@pytest.mark.l4("C-29c6c2b6")
def test_gate_reset_telemetry_restores_the_noop_shim() -> None:
    """The autouse reset fixture needs telemetry.reset_telemetry() to clear the module state."""
    reset = getattr(telemetry, "reset_telemetry", None)
    assert reset is not None, "reset_telemetry is missing"
    telemetry._enabled = True
    telemetry._tracer = object()
    telemetry._meter = object()
    telemetry._instruments["probe"] = object()
    try:
        reset()
        assert telemetry.is_enabled() is False
        assert telemetry._tracer is None
        assert telemetry._meter is None
        assert telemetry._instruments == {}
    finally:
        telemetry._enabled = False
        telemetry._tracer = None
        telemetry._meter = None
        telemetry._instruments.clear()
        with contextlib.suppress(Exception):
            telemetry.reset_telemetry()
