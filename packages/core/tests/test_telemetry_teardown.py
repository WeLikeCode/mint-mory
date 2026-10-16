"""The bounded teardown behind ``shutdown_telemetry`` is shared with init (task 5.2).

Spec: observability › Bounded flush on exit -
"``shutdown_telemetry(timeout_s=2.0)`` SHALL be the one teardown: providers' ``shutdown()`` in a
daemon thread named ``mintmory-telemetry-shutdown`` awaited at most ``timeout_s``, then clear the
module state (``_tracer``, ``_meter``, the providers, the ``_instruments`` cache), release the
API's global providers and restore the ``opentelemetry.exporter.otlp.proto.http`` level init
saved ... It SHALL be safe to repeat and without a prior init. ... A successful init ... SHALL
call ``atexit.register(shutdown_telemetry)`` ... and set the flag; ``shutdown_telemetry`` keeps
it, so a process registers once however often it re-initialises."

The teardown contract is pinned through the public seam and the module state the spec names:

* a provider whose ``shutdown`` never returns cannot hold the caller past ``timeout_s``; the
  module state is already cleared and the bounded daemon thread is still parked (the test sets
  the event at the end so the thread does not leak);
* a span that ends just before exit is flushed to the collector on the way out;
* the OTLP/HTTP exporter logger round-trips CRITICAL -> the saved level over two cycles;
* one ``atexit`` hook is registered however often a process re-initialises, the SDK providers
  register none, and the test-only reset re-arms it once more.

``_reset_telemetry`` here shadows the root ``conftest.py`` fixture of the same name for this
module only: these tests own the telemetry state they install and stay runnable against a unit
base where ``telemetry.reset_telemetry`` is absent.
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
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


def _require_shutdown() -> Any:
    """The one teardown entry point the spec names; a missing one is a failure, not an error."""
    shutdown = getattr(telemetry, "shutdown_telemetry", None)
    assert shutdown is not None, "shutdown_telemetry is missing"
    return shutdown


@pytest.mark.l4("C-b7126d33")
def test_teardown_bounds_a_provider_whose_shutdown_never_returns() -> None:
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

    assert telemetry.init_telemetry(span_exporter=_StuckShutdownExporter()) is True
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
def test_teardown_flushes_a_finished_span_to_the_collector(
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
def test_teardown_restores_the_exporter_logger_over_two_cycles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
def test_teardown_registers_one_atexit_hook_across_reinits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One hook however often a process re-initialises; the reset re-arms it once more."""
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    shutdown = _require_shutdown()
    reset = getattr(telemetry, "reset_telemetry", None)
    assert reset is not None, "reset_telemetry is missing"

    calls: list[Any] = []
    monkeypatch.setattr(atexit, "register", calls.append)

    assert (
        telemetry.init_telemetry(
            span_exporter=InMemorySpanExporter(), metric_reader=InMemoryMetricReader()
        )
        is True
    )
    assert telemetry._atexit_registered is True
    assert (
        telemetry.init_telemetry(
            span_exporter=InMemorySpanExporter(), metric_reader=InMemoryMetricReader()
        )
        is True
    )

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
        telemetry.init_telemetry(
            span_exporter=InMemorySpanExporter(), metric_reader=InMemoryMetricReader()
        )
        is True
    )
    assert calls == [shutdown]

    reset()
    assert telemetry._atexit_registered is False
    assert (
        telemetry.init_telemetry(
            span_exporter=InMemorySpanExporter(), metric_reader=InMemoryMetricReader()
        )
        is True
    )
    assert calls == [shutdown, shutdown]
