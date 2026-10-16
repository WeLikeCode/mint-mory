"""The module provider handles and their global installation on success (task 8.2).

Spec: observability › Global providers and repeated init.

A successful ``init_telemetry`` stores its providers in the module handles
``telemetry._tracer_provider`` / ``telemetry._meter_provider`` and installs them as the API's
global providers, so ``telemetry._tracer`` / ``telemetry._meter`` (and any library tracer) reach
the same exporters. A later init changes nothing; after a shutdown a fresh init installs a new
provider that becomes the global one.

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


@pytest.mark.l4("C-59c09ecd")
def test_init_installs_module_and_global_tracer_provider() -> None:
    """A successful init sets ``_tracer_provider``, ``_tracer`` and the global provider."""
    from opentelemetry import trace

    exporter = _in_memory_span_exporter()
    assert _init(span_exporter=exporter) is True

    provider = telemetry._tracer_provider
    assert provider is not None, "init did not record a tracer provider"
    assert trace.get_tracer_provider() is provider, "the module provider is not the global one"
    assert telemetry._tracer is not None, "init did not store the module tracer"

    with telemetry._tracer.start_as_current_span("via-module-tracer"):
        pass

    assert _span_names(exporter) == ["via-module-tracer"], _span_names(exporter)


@pytest.mark.l4("C-59c09ecd")
def test_init_installs_module_and_global_meter_provider() -> None:
    """A successful init sets ``_meter_provider``, ``_meter`` and the global provider."""
    from opentelemetry import metrics

    reader = _in_memory_metric_reader()
    assert _init(metric_reader=reader) is True

    provider = telemetry._meter_provider
    assert provider is not None, "init did not record a meter provider"
    assert metrics.get_meter_provider() is provider, "the module provider is not the global one"
    assert telemetry._meter is not None, "init did not store the module meter"

    telemetry.record_value("x", 1.0)

    assert "x" in _metric_names(reader), _metric_names(reader)


@pytest.mark.l4("C-59c09ecd")
def test_a_second_init_keeps_the_first_provider_and_tracer() -> None:
    """A later init returns True, keeps the provider, the tracer and the first exporter."""
    first = _in_memory_span_exporter()
    assert _init(span_exporter=first) is True
    provider = telemetry._tracer_provider
    tracer = telemetry._tracer

    second = _in_memory_span_exporter()
    assert _init(span_exporter=second) is True

    assert telemetry._tracer_provider is provider, "the second init replaced the provider"
    assert telemetry._tracer is tracer, "the second init replaced the tracer"
    with telemetry.span("kept"):
        pass

    assert _span_names(first) == ["kept"], _span_names(first)
    assert _span_names(second) == [], _span_names(second)


@pytest.mark.l4("C-836e8777")
def test_reinit_after_shutdown_installs_a_new_global_provider() -> None:
    """After a shutdown a fresh init installs a new global provider reached by library spans."""
    from opentelemetry import metrics, trace

    first_reader = _in_memory_metric_reader()
    first = _in_memory_span_exporter()
    assert _init(span_exporter=first, metric_reader=first_reader) is True
    first_tracer_provider = telemetry._tracer_provider
    first_meter_provider = telemetry._meter_provider
    assert first_tracer_provider is not None
    assert first_meter_provider is not None
    with telemetry.span("one"):
        pass
    assert _span_names(first) == ["one"], _span_names(first)

    shutdown = getattr(telemetry, "shutdown_telemetry", None)
    assert shutdown is not None, "shutdown_telemetry is missing"
    shutdown()

    second_reader = _in_memory_metric_reader()
    second = _in_memory_span_exporter()
    assert _init(span_exporter=second, metric_reader=second_reader) is True

    assert telemetry._tracer_provider is not first_tracer_provider
    assert telemetry._meter_provider is not first_meter_provider
    assert trace.get_tracer_provider() is telemetry._tracer_provider
    assert metrics.get_meter_provider() is telemetry._meter_provider

    with telemetry.span("two"):
        pass
    with trace.get_tracer("x").start_as_current_span("three"):
        pass
    telemetry.record_value("m", 1.0)

    assert sorted(_span_names(second)) == ["three", "two"], _span_names(second)
    assert _span_names(first) == ["one"], _span_names(first)
    assert "m" in _metric_names(second_reader), _metric_names(second_reader)
