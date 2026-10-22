"""The scrubber wraps *every* span exporter, outermost (task 4b.2).

Spec: observability › Exported spans carry no exception message -

    "Every span exporter, configured or injected, SHALL receive spans through a scrubber: in an
    ``exception`` event only ``exception.type`` is kept, and an ERROR status loses its
    description, for MintMory's spans and library spans (FastMCP's)."

Task 4b.1's tests pin the scrub semantics through an injected exporter. These pin the wiring:
the object handed to the span processor is ``_Scrubbing`` on the OTLP path (behind
``_GuardedSpanExporter`` and then the OTLP HTTP exporter), on the console path and on an injected
exporter, and a configured console export reaches stderr without the exception message.

Accepted finding F-0ad188: ``_Scrubbing`` keeps the exporter it wraps in ``_inner``, as
``_GuardedSpanExporter`` does, so the exporter-type check follows ``_inner`` until an object has
none and asserts the innermost exporter's type.

``_reset_telemetry`` here shadows the root ``conftest.py`` fixture of the same name for this
module only: these tests own the telemetry state they install and stay runnable (and fail by
assertion) against a unit base where ``telemetry.reset_telemetry`` is absent.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry

_SENTINEL = "SENTINEL-91c2"
_SCRUBBING = "mintmory.core.telemetry._Scrubbing"
_GUARD = "mintmory.core.telemetry._GuardedSpanExporter"
_CONSOLE = "opentelemetry.sdk.trace.export.ConsoleSpanExporter"
_OTLP_HTTP = "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
_IN_MEMORY = "opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter"


@pytest.fixture(autouse=True)
def _reset_telemetry() -> Iterator[None]:
    """Own this module's telemetry state; tolerate the helper being absent (unit base)."""
    reset = getattr(telemetry, "reset_telemetry", None)
    if reset is not None:
        reset()
    yield
    if reset is not None:
        reset()


def _exporter_chain() -> list[Any]:
    """The span exporter the processor got, then each ``_inner`` until an object has none."""
    provider = getattr(telemetry, "_tracer_provider", None)
    assert provider is not None, "init did not install a tracer provider"
    processor = provider._active_span_processor._span_processors[0]
    exporter = getattr(processor, "span_exporter", None)
    chain: list[Any] = []
    while exporter is not None:
        chain.append(exporter)
        exporter = getattr(exporter, "_inner", None)
    return chain


def _chain_names() -> list[str]:
    """Qualified type names of the exporter chain, outermost first."""
    return [f"{type(item).__module__}.{type(item).__qualname__}" for item in _exporter_chain()]


def _record_failing_exception(span: Any) -> None:
    """Record the sentinel exception and end the span with an ERROR status carrying it too."""
    from opentelemetry.trace import Status, StatusCode

    span.record_exception(RuntimeError(_SENTINEL))
    span.set_status(Status(StatusCode.ERROR, _SENTINEL))


@pytest.mark.l4("C-1457e823")
def test_scrubbing_is_outermost_on_the_otlp_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    """The OTLP path is ``_Scrubbing(_GuardedSpanExporter(OTLPSpanExporter))``."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.delenv("MINTMORY_OTEL_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "otlp")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")

    assert telemetry.init_telemetry() is True

    assert _chain_names() == [_SCRUBBING, _GUARD, _OTLP_HTTP]


@pytest.mark.l4("C-1457e823")
def test_scrubbing_is_outermost_on_the_console_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    """The console path is ``_Scrubbing(_GuardedSpanExporter(ConsoleSpanExporter))``."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.delenv("MINTMORY_OTEL_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "console")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")

    assert telemetry.init_telemetry() is True

    assert _chain_names() == [_SCRUBBING, _GUARD, _CONSOLE]


@pytest.mark.l4("C-1457e823")
def test_scrubbing_is_outermost_on_an_injected_exporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An injected exporter is wrapped as ``_Scrubbing(InMemorySpanExporter)``."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "false")
    exporter = InMemorySpanExporter()
    try:
        result: Any = telemetry.init_telemetry(span_exporter=exporter)
    except TypeError:  # a unit base without the test seam is a failure, not an error
        result = "init_telemetry is missing the test seam"
    assert result is True

    assert _chain_names() == [_SCRUBBING, _IN_MEMORY]


@pytest.mark.l4("C-1457e823")
def test_console_export_carries_no_exception_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A configured console exporter receives the scrubbed span on stderr, never stdout."""
    from opentelemetry import trace

    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.delenv("MINTMORY_OTEL_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "console")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")

    assert telemetry.init_telemetry() is True

    tracer = trace.get_tracer("library")
    with tracer.start_as_current_span("console-span") as span:
        _record_failing_exception(span)

    shutdown = getattr(telemetry, "shutdown_telemetry", None)
    if shutdown is not None:
        shutdown()
    captured = capsys.readouterr()

    assert "exception.type" in captured.err and "RuntimeError" in captured.err
    assert _SENTINEL not in captured.err
    assert captured.out == ""
