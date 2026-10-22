"""The exporter guards keep their wrapped exporter and stay real exporter subclasses (task 4.3).

Spec: observability › Export never blocks or floods when the collector is absent ›
Once per signal per streak.

``_GuardedSpanExporter`` and ``_GuardedMetricExporter`` wrap a configured exporter so a
failing export never raises and logs once per failure streak. A metric guard is handed to a
``PeriodicExportingMetricReader``, which reads ``_preferred_temporality`` and
``_preferred_aggregation`` off the exporter's ``MetricExporter`` base; the guard therefore has
to be a ``MetricExporter`` itself and forward those preferences, while both guards keep the
wrapped exporter in ``self._inner``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import pytest
from mintmory.core import telemetry


class _InnerMetricExporter:
    """A stand-in for a configured exporter, exposing the preferences the guard forwards."""

    def __init__(
        self,
        outcomes: Sequence[Any],
        preferred_temporality: Any,
        preferred_aggregation: Any,
    ) -> None:
        self._preferred_temporality = preferred_temporality
        self._preferred_aggregation = preferred_aggregation
        self._outcomes = list(outcomes)

    def export(self, metrics_data: Any, timeout_millis: float = 10_000, **kwargs: Any) -> Any:
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
        return None


@pytest.mark.l4("C-cd710a4c")
def test_guards_keep_inner_and_the_metric_guard_is_a_metric_exporter(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The metric guard forwards the inner preferences; both guards log once per streak."""
    metrics_export = pytest.importorskip("opentelemetry.sdk.metrics.export")
    from opentelemetry.sdk.metrics._internal.instrument import Counter
    from opentelemetry.sdk.metrics.view import SumAggregation
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    metric_exporter_base = metrics_export.MetricExporter
    result_success = metrics_export.MetricExportResult.SUCCESS
    result_failure = metrics_export.MetricExportResult.FAILURE
    temporality = {Counter: metrics_export.AggregationTemporality.DELTA}
    aggregation = {Counter: SumAggregation()}

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    caplog.set_level(logging.DEBUG, logger="mintmory.telemetry")

    inner_span = InMemorySpanExporter()
    span_guard = telemetry._GuardedSpanExporter(inner_span)
    assert span_guard._inner is inner_span

    inner_metric = _InnerMetricExporter(
        [result_failure, ConnectionError("boom"), result_success, result_failure],
        temporality,
        aggregation,
    )
    metric_guard = telemetry._GuardedMetricExporter(inner_metric)

    assert metric_guard._inner is inner_metric
    assert isinstance(metric_guard, metric_exporter_base)
    assert metric_guard._preferred_temporality == temporality
    assert metric_guard._preferred_aggregation == aggregation

    results = [metric_guard.export([]) for _ in range(4)]
    assert results == [result_failure, result_failure, result_success, result_failure]

    messages = [record.getMessage() for record in caplog.records]
    assert sum("telemetry: metric export failed" in message for message in messages) == 2
    assert sum("telemetry: metric export recovered" in message for message in messages) == 1
