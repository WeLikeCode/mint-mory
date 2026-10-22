"""Two threads that init telemetry at once build only one set of providers (task 1.1).

Spec: observability › init_telemetry: one set of providers when two threads init at once
(feedback FB-003).

The module-level ``_enabled`` flag is checked before ``_shutdown_lock`` and the check is not
repeated inside it, so two threads that pass it together both build providers: the second
overwrites ``telemetry._tracer_provider`` while the first stays the process-global provider.
Spans then reach only the first exporter and ``shutdown_telemetry`` flushes the orphan. A
barrier inside ``_sdk_available`` — the last step before the lock on the injected path — makes
both threads pass the ``_enabled`` check before either enters the lock, so the race is
deterministic.

``_reset_telemetry`` here shadows the root ``conftest.py`` fixture of the same name for this
module only: these tests own the telemetry state they install and stay runnable (and fail by
assertion) against a unit base where ``telemetry.reset_telemetry`` is absent.
"""

from __future__ import annotations

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
    process; resetting the once-guards keeps an init in one test meaningful.
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


@pytest.mark.l4("C-1d1f7ab8")
def test_two_threads_init_at_once_build_one_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two concurrent inits build one provider; that one is global and shutdown clears it."""
    from opentelemetry import trace

    barrier = threading.Barrier(2)
    original_sdk_available = telemetry._sdk_available
    waited = threading.local()

    def _synced_sdk_available() -> bool:
        result = bool(original_sdk_available())
        if result and not getattr(waited, "done", False):
            waited.done = True
            barrier.wait(timeout=5.0)
        return result

    monkeypatch.setattr(telemetry, "_sdk_available", _synced_sdk_available)

    first = _in_memory_span_exporter()
    second = _in_memory_span_exporter()
    results: list[Any] = [None, None]
    errors: list[BaseException] = []

    def _run(index: int, exporter: Any) -> None:
        try:
            results[index] = _init(span_exporter=exporter)
        except BaseException as error:  # pragma: no cover - surfaced by the assertion below
            errors.append(error)

    threads = [
        threading.Thread(target=_run, args=(0, first), name="init-a"),
        threading.Thread(target=_run, args=(1, second), name="init-b"),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10.0)

    assert not errors, errors
    assert results == [True, True], results

    assert telemetry._tracer_provider is trace.get_tracer_provider(), (
        "the module provider is not the process-global one: two sets were built"
    )
    assert telemetry._tracer_provider is not None

    with telemetry.span("once"):
        pass

    first_names = _span_names(first)
    second_names = _span_names(second)
    assert len(first_names) + len(second_names) == 1, (first_names, second_names)

    wired = _wired_innermost_exporters()
    assert len(wired) == 1, wired
    assert wired[0] in (first, second)

    shutdown = getattr(telemetry, "shutdown_telemetry", None)
    assert shutdown is not None, "shutdown_telemetry is missing"
    shutdown()

    assert telemetry._tracer_provider is None, "shutdown did not clear the module provider"
    assert telemetry.is_enabled() is False, "shutdown did not disable telemetry"
