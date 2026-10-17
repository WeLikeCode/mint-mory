"""The W3C trace-context header helpers, on and off (task 1.1).

Spec: observability › Outbound calls carry the trace context.

``telemetry.inject_trace_headers(headers)`` writes the current span's W3C ``traceparent`` (and
``tracestate``, never ``baggage``) into the carrier and returns it; with telemetry off it returns
the carrier untouched. ``telemetry.extract_context(carrier)`` returns the context extracted from an
inbound carrier — a malformed ``traceparent`` extracts to a context with no valid span, so the
request starts a new trace — and ``None`` with telemetry off. Both never raise.

The tests assert the real header/context each helper produces, so a zero-value stub cannot satisfy
them; ``extract_context`` is called on a well-formed carrier as well as a malformed one.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry

pytest.importorskip("opentelemetry.sdk")

_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
_PARENT_SPAN_ID = "00f067aa0ba902b7"
_CALLER_TRACEPARENT = f"00-{_TRACE_ID}-{_PARENT_SPAN_ID}-01"


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default global providers, so repeated inits stay meaningful."""
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


def _in_memory_exporter() -> Any:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    return InMemorySpanExporter()


def _enable(exporter: Any) -> None:
    assert telemetry.init_telemetry(span_exporter=exporter) is True


@pytest.mark.l4("C-1420ab97")
def test_extract_context_of_a_valid_traceparent_carries_its_trace() -> None:
    """A well-formed ``traceparent`` extracts to a context whose span is that remote span."""
    from opentelemetry import trace
    from opentelemetry.context import Context

    _enable(_in_memory_exporter())

    context = telemetry.extract_context({"traceparent": _CALLER_TRACEPARENT})

    assert isinstance(context, Context)
    span_context = trace.get_current_span(context).get_span_context()
    assert format(span_context.trace_id, "032x") == _TRACE_ID
    assert format(span_context.span_id, "016x") == _PARENT_SPAN_ID


@pytest.mark.l4("C-1420ab97")
def test_extract_context_of_garbage_starts_a_new_trace() -> None:
    """A malformed ``traceparent`` extracts to a context with no valid span, without raising."""
    from opentelemetry import trace
    from opentelemetry.context import Context

    _enable(_in_memory_exporter())

    context = telemetry.extract_context({"traceparent": "garbage"})

    assert isinstance(context, Context)
    span_context = trace.get_current_span(context).get_span_context()
    assert span_context.is_valid is False
    assert span_context.trace_id != int(_TRACE_ID, 16)


@pytest.mark.l4("C-83e1a4e6")
def test_inject_trace_headers_writes_the_current_span_into_the_carrier() -> None:
    """Inside a span, the helper adds a ``traceparent`` naming that span and returns the carrier."""
    _enable(_in_memory_exporter())

    headers: dict[str, str] = {}
    with telemetry.span("caller") as span:
        returned = telemetry.inject_trace_headers(headers)
        span_context = span.get_span_context()

    assert returned is headers
    assert "traceparent" in headers, headers
    assert format(span_context.trace_id, "032x") in headers["traceparent"]
    assert format(span_context.span_id, "016x") in headers["traceparent"]


@pytest.mark.l4("C-9970c315")
def test_inject_trace_headers_forwards_tracestate_and_never_baggage() -> None:
    """A caller's ``tracestate`` is forwarded; the inbound ``baggage`` is never sent onward."""
    _enable(_in_memory_exporter())
    caller_context = telemetry.extract_context(
        {
            "traceparent": _CALLER_TRACEPARENT,
            "tracestate": "vendor=1",
            "baggage": "user=SENTINEL-BAG-3",
        }
    )

    headers: dict[str, str] = {}
    with telemetry.span("caller", context=caller_context) as span:
        telemetry.inject_trace_headers(headers)
        span_context = span.get_span_context()

    assert "traceparent" in headers, headers
    assert format(span_context.trace_id, "032x") == _TRACE_ID
    assert headers["traceparent"].split("-")[1] == _TRACE_ID
    assert headers.get("tracestate") == "vendor=1"
    assert "baggage" not in headers


@pytest.mark.l4("C-c2076c0f")
def test_inject_trace_headers_off_leaves_the_carrier_untouched() -> None:
    """Telemetry off: the carrier is returned unchanged; telemetry on: a real ``traceparent``."""
    headers = {"x-custom": "keep"}
    assert telemetry.inject_trace_headers(headers) is headers
    assert headers == {"x-custom": "keep"}
    assert telemetry.extract_context({"traceparent": _CALLER_TRACEPARENT}) is None

    _enable(_in_memory_exporter())
    with telemetry.span("caller"):
        injected = telemetry.inject_trace_headers({})
    assert "traceparent" in injected, injected
