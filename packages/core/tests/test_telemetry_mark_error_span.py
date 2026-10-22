"""``mark_error`` marks a real span failed and ignores the disabled shim (task 5.3).

Spec: observability › One error-marking helper -
"``telemetry.mark_error(span, error_type: str) -> None`` SHALL be the one way MintMory marks a
span failed: on an SDK span it sets status ERROR without description and ``error.type`` =
``error_type``; on ``_NoopSpan`` (telemetry off, or traces ``none``) it does nothing; it SHALL
never raise. ``_NoopSpan`` gets no status method."

These are the two halves of the same contract: marking an SDK span reached through
``telemetry.span`` exports an ERROR status with no description and the ``error.type`` attribute,
while the ``_NoopSpan`` of the off shim accepts the identical call without raising.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from mintmory.core import telemetry


@pytest.fixture(autouse=True)
def _reset_this_module() -> Iterator[None]:
    """Return the shim to its no-op state, tolerating a unit base without ``reset_telemetry``."""
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
    process; resetting the once-guards keeps ``set_tracer_provider`` meaningful regardless of
    test order.
    """
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


@pytest.mark.l4("C-65be7944")
def test_mark_error_sets_error_status_without_description_and_records_the_type() -> None:
    """A span marked through ``telemetry.span`` exports ERROR, no description and ``error.type``."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import StatusCode

    exporter = InMemorySpanExporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True

    with telemetry.span("a") as span:
        telemetry.mark_error(span, "RuntimeError")

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["a"]
    finished = spans[0]
    assert finished.status.status_code == StatusCode.ERROR
    assert not finished.status.description
    assert finished.attributes is not None
    assert finished.attributes["error.type"] == "RuntimeError"


@pytest.mark.l4("C-65be7944")
def test_mark_error_is_silent_on_the_off_shim_and_marks_a_real_span() -> None:
    """With telemetry off the call is a no-op; a real span in the same test is still marked."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import StatusCode

    with telemetry.span("off") as noop_span:
        assert isinstance(noop_span, telemetry._NoopSpan)
        telemetry.mark_error(noop_span, "RuntimeError")

    exporter = InMemorySpanExporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True
    with telemetry.span("a") as span:
        telemetry.mark_error(span, "ValueError")

    finished = exporter.get_finished_spans()
    assert [span.name for span in finished] == ["a"]
    assert finished[0].status.status_code == StatusCode.ERROR
    assert not finished[0].status.description
    assert finished[0].attributes is not None
    assert finished[0].attributes["error.type"] == "ValueError"
