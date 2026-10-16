"""``shutdown_telemetry`` is the one bounded teardown (task 5.1).

Spec: observability › Bounded flush on exit -
"``shutdown_telemetry(timeout_s=2.0)`` SHALL be the one teardown: providers' ``shutdown()``
in a daemon thread named ``mintmory-telemetry-shutdown`` awaited at most ``timeout_s``, then
clear the module state ..., release the API's global providers and restore the ... level ...
A successful init while the module flag ``_atexit_registered`` is False SHALL call
``atexit.register(shutdown_telemetry)`` ... and set the flag; ``shutdown_telemetry`` keeps it ...
``reset_telemetry()`` ... unregisters and clears it."

These tests pin the exit contract:

* a provider whose ``shutdown`` never returns cannot block the caller: ``shutdown_telemetry``
  returns within ``timeout_s``, leaves the no-op shim, and the bounded daemon thread is still
  parked (the test sets the event at the end so the thread does not leak);
* a span that ends just before exit is flushed by ``shutdown_telemetry`` and reaches the OTLP
  collector;
* one ``atexit`` hook is registered, however often a process re-initialises, and the test-only
  reset unregisters it so a later init re-arms it once more.

``_reset_telemetry`` here shadows the root ``conftest.py`` fixture of the same name for this
module only: these tests own the telemetry state they install and stay runnable against a unit
base where ``telemetry.reset_telemetry`` is absent.
"""

from __future__ import annotations

import atexit
import threading
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


@pytest.mark.l4("C-b7126d33")
def test_shutdown_is_bounded_when_a_provider_shutdown_hangs() -> None:
    """A shutdown that never returns cannot hold the caller past ``timeout_s``."""
    from opentelemetry.sdk.trace.export import SpanExportResult

    release = threading.Event()

    class _HangingShutdownExporter:
        def export(self, spans: Any) -> Any:
            return SpanExportResult.SUCCESS

        def shutdown(self) -> None:
            release.wait(5.0)

        def force_flush(self, timeout_millis: int = 30_000) -> bool:
            return True

    try:
        result: Any = telemetry.init_telemetry(span_exporter=_HangingShutdownExporter())
    except TypeError:  # a unit base without the test seam is a failure, not an error
        result = "init_telemetry is missing the test seam"
    assert result is True

    shutdown: Any = getattr(telemetry, "shutdown_telemetry", None)
    assert shutdown is not None, "shutdown_telemetry is missing"

    try:
        shutdown(timeout_s=0.2)

        assert telemetry.is_enabled() is False
        names = [thread.name for thread in threading.enumerate()]
        assert "mintmory-telemetry-shutdown" in names, names
    finally:
        release.set()
        for thread in threading.enumerate():
            if thread.name == "mintmory-telemetry-shutdown":
                thread.join(timeout=2.0)


@pytest.mark.l4("C-16b8c487")
def test_pending_spans_are_delivered_on_exit(
    monkeypatch: pytest.MonkeyPatch, otlp_receiver: Any
) -> None:
    """A span that ends just before shutdown is flushed to the collector on the way out."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", otlp_receiver.endpoint)

    result: Any = telemetry.init_telemetry()
    assert result is True

    shutdown: Any = getattr(telemetry, "shutdown_telemetry", None)
    assert shutdown is not None, "shutdown_telemetry is missing"

    with telemetry.span("x"):
        pass
    shutdown()

    paths = [path for path, _ in otlp_receiver.requests]
    assert "/v1/traces" in paths, paths
    names = [name for name, _ in otlp_receiver.spans()]
    assert "x" in names, names


@pytest.mark.l4("C-fa66b065")
def test_one_atexit_hook_is_registered_and_rearmed_by_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated inits register one hook; the SDK providers register none; reset re-arms it."""
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    calls: list[Any] = []
    monkeypatch.setattr(atexit, "register", calls.append)

    try:
        result: Any = telemetry.init_telemetry(
            span_exporter=InMemorySpanExporter(), metric_reader=InMemoryMetricReader()
        )
    except TypeError:  # a unit base without the test seam is a failure, not an error
        result = "init_telemetry is missing the test seam"
    assert result is True

    shutdown: Any = getattr(telemetry, "shutdown_telemetry", None)
    reset: Any = getattr(telemetry, "reset_telemetry", None)
    assert shutdown is not None and reset is not None, "shutdown/reset seam is missing"

    assert (
        telemetry.init_telemetry(
            span_exporter=InMemorySpanExporter(), metric_reader=InMemoryMetricReader()
        )
        is True
    )
    shutdown()
    assert (
        telemetry.init_telemetry(
            span_exporter=InMemorySpanExporter(), metric_reader=InMemoryMetricReader()
        )
        is True
    )

    assert calls == [shutdown]
    assert telemetry._atexit_registered is True

    tracer_provider = telemetry._tracer_provider
    meter_provider = telemetry._meter_provider
    assert tracer_provider is not None
    assert meter_provider is not None
    assert tracer_provider._atexit_handler is None
    assert meter_provider._atexit_handler is None

    reset()
    assert telemetry._atexit_registered is False
    assert (
        telemetry.init_telemetry(
            span_exporter=InMemorySpanExporter(), metric_reader=InMemoryMetricReader()
        )
        is True
    )
    assert len(calls) == 2


@pytest.mark.l4("C-fa66b065")
def test_a_false_init_registers_no_atexit_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    """An init that returns False registers no exit hook and leaves the flag clear."""
    calls: list[Any] = []
    monkeypatch.setattr(atexit, "register", calls.append)
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "none")

    result: Any = telemetry.init_telemetry()

    assert result is False
    assert calls == []
    assert telemetry._atexit_registered is False
