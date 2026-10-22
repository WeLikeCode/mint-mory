"""The export scrubber drops exception messages.

Spec: observability › Exported spans carry no exception message.

Spec: "Every span exporter, configured or injected, SHALL receive spans through a scrubber: in an
``exception`` event only ``exception.type`` is kept, and an ERROR status loses its description, for
MintMory's spans and library spans (FastMCP's)."

A library span (``opentelemetry.trace.get_tracer``) and a MintMory span (``telemetry.span``) that
record a sentinel-carrying ``RuntimeError`` and end with an ERROR status must reach the in-memory
exporter with the type only: the message and stacktrace are gone from the event, the status
description is gone and no value anywhere on the span carries the sentinel.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry

_SENTINEL = "SENTINEL-91c2"


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default global providers.

    A successful init makes its providers global, and the OTel API allows that only once per
    process; resetting the once-guards lets ``get_tracer("library")`` resolve to this test's
    provider whatever ran before it.
    """
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


def _record_failing_exception(span: Any) -> None:
    """Record the sentinel exception and end the span with an ERROR status carrying it too."""
    from opentelemetry.trace import Status, StatusCode

    span.record_exception(RuntimeError(_SENTINEL))
    span.set_status(Status(StatusCode.ERROR, _SENTINEL))


def _exception_event(span: Any) -> Any:
    """The single ``exception`` event of an exported span."""
    events = [event for event in span.events if event.name == "exception"]
    assert len(events) == 1, [event.name for event in span.events]
    return events[0]


def _assert_scrubbed(exported: Any) -> None:
    """The exported span keeps the exception type but nothing that carries the sentinel."""
    from opentelemetry.trace import StatusCode

    event = _exception_event(exported)
    assert event.attributes.get("exception.type") == "RuntimeError"

    for key, value in dict(event.attributes).items():
        assert _SENTINEL not in str(value), (key, value)

    assert exported.status.status_code == StatusCode.ERROR
    assert _SENTINEL not in (exported.status.description or "")
    assert _SENTINEL not in str(dict(exported.attributes))


@pytest.mark.l4("C-1457e823")
def test_library_span_exception_is_scrubbed() -> None:
    """A library's recorded exception reaches the exporter as its type only."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True

    tracer = trace.get_tracer("library")
    with tracer.start_as_current_span("library-span") as span:
        _record_failing_exception(span)

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["library-span"]
    _assert_scrubbed(spans[0])


@pytest.mark.l4("C-1457e823")
def test_mintmory_span_exception_is_scrubbed() -> None:
    """A MintMory span through ``telemetry.span`` is scrubbed the same way."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True

    with telemetry.span("mintmory-span") as span:
        _record_failing_exception(span)

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["mintmory-span"]
    _assert_scrubbed(spans[0])
