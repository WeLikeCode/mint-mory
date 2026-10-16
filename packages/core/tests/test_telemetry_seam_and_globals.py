"""The injection test seam and the global providers across repeated inits (task 8.1).

Spec: observability › Telemetry test seam and observability › Global providers and repeated
init.

* ``init_telemetry(span_exporter=...)`` uses an injected exporter through a synchronous
  processor and enables telemetry even when the environment says off (the suite's
  ``MINTMORY_OTEL_ENABLED=false`` default or the standard ``OTEL_SDK_DISABLED`` kill switch);
* injecting only one signal leaves the other off and never builds a configured (network)
  exporter for it;
* each successful init makes its providers the global ones, so a library's own tracer reaches
  the same exporter; after a successful init a later init changes nothing and returns True;
* after a shutdown a fresh init installs a new provider and both MintMory and library spans
  reach only the new exporter.

``_reset_telemetry`` here shadows the root ``conftest.py`` fixture of the same name for this
module only: these tests own the telemetry state they install and stay runnable (and fail by
assertion) against a unit base where ``telemetry.reset_telemetry`` is absent.
"""

from __future__ import annotations

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


def _init(**kwargs: Any) -> Any:
    """The test seam; a unit base without it is a failure, not an error."""
    try:
        return telemetry.init_telemetry(**kwargs)
    except TypeError:
        return "init_telemetry is missing the test seam"


def _in_memory_span_exporter() -> Any:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    return InMemorySpanExporter()


def _in_memory_metric_reader() -> Any:
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    return InMemoryMetricReader()


def _span_names(exporter: Any) -> list[str]:
    return [span.name for span in exporter.get_finished_spans()]


def _wired_innermost_exporters() -> list[Any]:
    """The innermost exporter behind each processor of the installed tracer provider."""
    provider = getattr(telemetry, "_tracer_provider", None)
    assert provider is not None, "init did not install a tracer provider"
    wired: list[Any] = []
    for processor in provider._active_span_processor._span_processors:
        exporter = getattr(processor, "span_exporter", None)
        innermost = exporter
        while exporter is not None:
            innermost = exporter
            exporter = getattr(exporter, "_inner", None)
        if innermost is not None:
            wired.append(innermost)
    return wired


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


@pytest.mark.l4("C-e8aa74fe")
def test_injection_beats_the_suites_off_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """An injected exporter enables export despite ``MINTMORY_OTEL_ENABLED=false``."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "false")
    exporter = _in_memory_span_exporter()

    assert _init(span_exporter=exporter) is True
    with telemetry.span("injected"):
        pass

    assert _span_names(exporter) == ["injected"], _span_names(exporter)
    assert telemetry.is_enabled() is True


@pytest.mark.l4("C-e8aa74fe")
def test_injection_beats_the_sdk_kill_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The seam enables and wires the injected exporter despite ``OTEL_SDK_DISABLED=true``.

    The MintMory runtime builds its provider and installs the injected exporter even though the
    environment asks the SDK off; that the SDK's own provider then yields a no-op tracer is the
    SDK honouring its kill switch, not the seam failing to inject.
    """
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    exporter = _in_memory_span_exporter()

    assert _init(span_exporter=exporter) is True
    assert telemetry.is_enabled() is True
    assert exporter in _wired_innermost_exporters()


@pytest.mark.l4("C-90d20140")
def test_single_injection_builds_no_network_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
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


@pytest.mark.l4("C-59c09ecd")
def test_a_second_init_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
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
def test_reinit_after_shutdown_uses_only_the_second_exporter() -> None:
    """Both a MintMory span and a library span reach the second exporter after a shutdown."""
    from opentelemetry import trace

    first = _in_memory_span_exporter()
    assert _init(span_exporter=first) is True
    with telemetry.span("one"):
        pass
    assert _span_names(first) == ["one"], _span_names(first)

    shutdown = getattr(telemetry, "shutdown_telemetry", None)
    assert shutdown is not None, "shutdown_telemetry is missing"
    shutdown()

    second = _in_memory_span_exporter()
    assert _init(span_exporter=second) is True
    with telemetry.span("two"):
        pass
    with trace.get_tracer("x").start_as_current_span("three"):
        pass

    assert sorted(_span_names(second)) == ["three", "two"], _span_names(second)
    assert _span_names(first) == ["one"], _span_names(first)
