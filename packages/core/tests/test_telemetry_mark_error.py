"""``mark_error`` is the one way MintMory marks a span failed (task 5.1).

Spec: observability › One error-marking helper -
"``telemetry.mark_error(span, error_type: str) -> None`` SHALL be the one way MintMory marks a
span failed: on an SDK span it sets status ERROR without description and ``error.type`` =
``error_type``; on ``_NoopSpan`` (telemetry off, or traces ``none``) it does nothing; it SHALL
never raise. ``_NoopSpan`` gets no status method."

A real span opened through ``telemetry.span`` and marked with ``mark_error`` must reach the
in-memory exporter with an ERROR status (no description) and the ``error.type`` attribute; the
no-op span of the disabled shim must accept the same call without raising.
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
    process; resetting the once-guards keeps ``get_tracer_provider()`` meaningful regardless of
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
def test_mark_error_sets_status_and_error_type_on_a_real_span() -> None:
    """An SDK span marked failed exports with ERROR, no description and ``error.type``."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import StatusCode

    mark_error: Any = getattr(telemetry, "mark_error", None)
    assert mark_error is not None, "mark_error is missing"

    exporter = InMemorySpanExporter()
    try:
        result: Any = telemetry.init_telemetry(span_exporter=exporter)
    except TypeError:  # a unit base without the test seam is a failure, not an error
        result = "init_telemetry is missing the test seam"
    assert result is True

    with telemetry.span("a") as sp:
        mark_error(sp, "RuntimeError")

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["a"]
    finished = spans[0]
    assert finished.status.status_code == StatusCode.ERROR
    assert not finished.status.description
    assert finished.attributes is not None
    assert finished.attributes["error.type"] == "RuntimeError"


@pytest.mark.l4("C-65be7944")
def test_mark_error_on_a_noop_span_does_nothing() -> None:
    """With telemetry off, ``mark_error`` accepts a ``_NoopSpan`` and never raises."""
    mark_error: Any = getattr(telemetry, "mark_error", None)
    assert mark_error is not None, "mark_error is missing"

    with telemetry.span("a") as sp:
        assert isinstance(sp, telemetry._NoopSpan)
        mark_error(sp, "RuntimeError")
