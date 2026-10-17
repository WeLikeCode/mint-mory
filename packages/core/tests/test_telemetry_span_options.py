"""``span()``'s kind, parent context and exception options, and ``run_in_context`` (task 1.1).

Spec: observability › Span kind, parent context and exception options, and observability ›
Worker threads keep the trace.

``span(name, *, kind, context, record_exception, set_status_on_exception, **attrs)`` passes those
four options to ``start_as_current_span``: an unknown ``kind`` maps to INTERNAL and the defaults
are the SDK's (so the two flags let ``command_span`` leave exit code 0 unmarked). The off shim
``_NoopSpan`` gains a no-op ``update_name``. ``run_in_context(fn)`` runs ``fn`` on a fresh copy of
the caller's context, so spans opened on worker threads stay in the caller's trace.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry

pytest.importorskip("opentelemetry.sdk")


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default providers, tolerating repeated inits."""
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


def _finished_by_name(exporter: Any) -> dict[str, Any]:
    return {span.name: span for span in exporter.get_finished_spans()}


@pytest.mark.l4("C-844f12f2")
def test_span_kind_maps_known_values_and_falls_back_to_internal() -> None:
    """``server``/``client`` map to their kind; any other value maps to INTERNAL."""
    from opentelemetry.trace import SpanKind

    exporter = _in_memory_exporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True

    with telemetry.span("a", kind="server"):
        pass
    with telemetry.span("c", kind="client"):
        pass
    with telemetry.span("d", kind="bogus"):
        pass

    spans = _finished_by_name(exporter)
    assert spans["a"].kind == SpanKind.SERVER
    assert spans["c"].kind == SpanKind.CLIENT
    assert spans["d"].kind == SpanKind.INTERNAL


@pytest.mark.l4("C-844f12f2")
def test_span_exception_options_reach_the_span() -> None:
    """The flags suppress recording and status; the SDK defaults record one scrubbed event."""
    from opentelemetry.trace import StatusCode

    exporter = _in_memory_exporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True

    with (
        pytest.raises(RuntimeError),
        telemetry.span("b", record_exception=False, set_status_on_exception=False),
    ):
        raise RuntimeError("SENTINEL-12")
    with pytest.raises(RuntimeError), telemetry.span("c"):
        raise RuntimeError("SENTINEL-12")

    assert {span.name for span in exporter.get_finished_spans()} == {"b", "c"}
    spans = _finished_by_name(exporter)
    quiet = spans["b"]
    assert quiet.status.status_code == StatusCode.UNSET
    assert list(quiet.events) == []

    failed = spans["c"]
    assert failed.status.status_code == StatusCode.ERROR
    assert not failed.status.description
    events = [event for event in failed.events if event.name == "exception"]
    assert len(events) == 1
    assert dict(events[0].attributes or {}) == {"exception.type": "RuntimeError"}


@pytest.mark.l4("C-844f12f2")
def test_span_context_sets_an_explicit_parent() -> None:
    """An explicit ``context`` makes the span a child of that context, not the current span."""
    from opentelemetry import trace

    exporter = _in_memory_exporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True

    with telemetry.span("root") as root:
        root_context = trace.set_span_in_context(root)
    with telemetry.span("child", context=root_context):
        pass

    spans = _finished_by_name(exporter)
    assert spans["child"].parent is not None
    assert spans["child"].parent.span_id == spans["root"].context.span_id


@pytest.mark.l4("C-844f12f2")
def test_span_options_on_the_off_shim_are_a_noop_with_update_name() -> None:
    """With telemetry off the options are accepted and ``update_name`` is a no-op."""
    with telemetry.span("a", kind="server", record_exception=False) as span:
        assert isinstance(span, telemetry._NoopSpan)
        span.update_name("b")


@pytest.mark.l4("C-711e3d68")
def test_run_in_context_keeps_the_trace_across_four_threads() -> None:
    """Four worker threads run inside the caller's span: same trace id, children of the root."""
    exporter = _in_memory_exporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True

    trace_ids: list[str] = []
    lock = threading.Lock()

    def task() -> None:
        with telemetry.span("task") as span:
            trace_id = format(span.get_span_context().trace_id, "032x")
            with lock:
                trace_ids.append(trace_id)

    with telemetry.span("root-a") as root:
        root_trace_id = format(root.get_span_context().trace_id, "032x")
        run = telemetry.run_in_context(task)
        threads = [threading.Thread(target=run) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert len(trace_ids) == 4
    assert set(trace_ids) == {root_trace_id}
    task_spans = [span for span in exporter.get_finished_spans() if span.name == "task"]
    assert len(task_spans) == 4
    assert {format(span.context.trace_id, "032x") for span in task_spans} == {root_trace_id}
