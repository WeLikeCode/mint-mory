"""``record_histogram``: the parameterised histogram helper (task 1.3).

Spec: observability › HTTP server duration metric, and observability › Middleware telemetry
never alters a request.

``record_histogram(name, value, *, unit, boundaries=None, **attrs)`` records one point in the
histogram ``name`` through ``_instrument``, so the meter's factory receives ``unit`` and
``explicit_bucket_boundaries_advisory=boundaries`` on first creation. ``None`` attributes are
dropped, metrics off is a no-op, and the body never raises. The duration metric is a histogram
in seconds with the explicit bucket boundaries 0.005 … 10.

Each test reads the factory options and the recorded point back out, so a zero-value stub
cannot satisfy it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

import pytest
from mintmory.core import telemetry

pytest.importorskip("opentelemetry.sdk")


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default providers, so repeated inits stay meaningful."""
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


def _install(monkeypatch: pytest.MonkeyPatch, meter: Any) -> None:
    """Make ``telemetry`` enabled with the given meter and an empty instrument cache."""
    monkeypatch.setattr(telemetry, "_enabled", True)
    monkeypatch.setattr(telemetry, "_meter", meter)
    monkeypatch.setattr(telemetry, "_instruments", {})


class _RecordingHistogram:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, Any]]] = []

    def record(self, value: float, attributes: Mapping[str, Any]) -> None:
        self.calls.append((value, dict(attributes)))


class _RecordingMeter:
    """A meter that remembers every factory call and every recorded point."""

    def __init__(self) -> None:
        self.factory_calls: list[tuple[str, dict[str, Any]]] = []
        self.histograms: dict[str, _RecordingHistogram] = {}

    def create_histogram(self, name: str, **kwargs: Any) -> _RecordingHistogram:
        self.factory_calls.append((name, dict(kwargs)))
        return self.histograms.setdefault(name, _RecordingHistogram())


class _BrokenMeter:
    """A meter whose instrument creation raises, as a failing provider would."""

    def create_histogram(self, name: str, **kwargs: Any) -> Any:
        raise RuntimeError("meter-boom")


@pytest.mark.l4("C-7409b7a7")
def test_record_histogram_passes_unit_and_boundaries_to_the_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First creation hands the meter the unit and the advisory bucket boundaries."""
    boundaries = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
    meter = _RecordingMeter()
    _install(monkeypatch, meter)

    telemetry.record_histogram(
        "http.server.request.duration",
        0.012,
        unit="s",
        boundaries=boundaries,
        http_request_method="GET",
        http_route="/stats",
    )

    assert meter.factory_calls == [
        (
            "http.server.request.duration",
            {"unit": "s", "explicit_bucket_boundaries_advisory": boundaries},
        )
    ]
    histogram = meter.histograms.get("http.server.request.duration")
    assert histogram is not None
    assert histogram.calls == [(0.012, {"http_request_method": "GET", "http_route": "/stats"})]


@pytest.mark.l4("C-7409b7a7")
def test_record_histogram_drops_none_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    """``None`` attributes never reach the point; real ones do."""
    meter = _RecordingMeter()
    _install(monkeypatch, meter)

    telemetry.record_histogram("mintmory.probe.hist", 1.5, unit="ms", keep="x", drop=None)

    histogram = meter.histograms.get("mintmory.probe.hist")
    assert histogram is not None
    assert histogram.calls == [(1.5, {"keep": "x"})]


@pytest.mark.l4("C-7409b7a7")
def test_record_histogram_is_a_no_op_when_metrics_are_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With metrics off the meter is never touched; with them on the point still lands."""

    class _ExplodingMeter:
        def create_histogram(self, name: str, **kwargs: Any) -> Any:
            raise AssertionError("the meter must not be touched while metrics are off")

    monkeypatch.setattr(telemetry, "_enabled", False)
    monkeypatch.setattr(telemetry, "_meter", _ExplodingMeter())
    telemetry.record_histogram("mintmory.probe.hist", 1.0, unit="s", boundaries=(0.005, 0.01))

    meter = _RecordingMeter()
    _install(monkeypatch, meter)
    telemetry.record_histogram("mintmory.probe.hist", 2.0, unit="s", boundaries=(0.005, 0.01))

    assert meter.factory_calls
    histogram = meter.histograms.get("mintmory.probe.hist")
    assert histogram is not None
    assert histogram.calls == [(2.0, {})]


@pytest.mark.l4("C-a2f61e7e")
def test_record_histogram_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A raising factory is swallowed, and a healthy meter still records the point."""
    _install(monkeypatch, _BrokenMeter())
    try:
        telemetry.record_histogram("mintmory.probe.hist", 1.0, unit="s")
    except Exception as error:  # the guard's whole point is that this never happens
        pytest.fail(f"record_histogram let {type(error).__name__} escape")

    meter = _RecordingMeter()
    _install(monkeypatch, meter)
    telemetry.record_histogram("mintmory.probe.hist", 3.0, unit="s", http_route="/x")

    assert meter.factory_calls, "the healthy meter was never asked for the histogram"
    histogram = meter.histograms.get("mintmory.probe.hist")
    assert histogram is not None
    assert histogram.calls == [(3.0, {"http_route": "/x"})]


@pytest.mark.l4("C-7409b7a7", "C-a2f61e7e")
def test_record_histogram_exports_the_seconds_unit_and_explicit_bounds() -> None:
    """An in-memory reader sees unit ``s`` and the explicit bucket boundaries on the point."""
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    boundaries = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
    reader: Any = InMemoryMetricReader()
    assert telemetry.init_telemetry(metric_reader=reader) is True

    telemetry.record_histogram(
        "http.server.request.duration",
        0.012,
        unit="s",
        boundaries=boundaries,
        http_request_method="GET",
        http_route="/stats",
        http_response_status_code=200,
    )

    data = reader.get_metrics_data()
    assert data is not None, "no metrics were exported"
    metric = next(
        metric
        for resource_metrics in data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    )
    assert metric.name == "http.server.request.duration"
    assert metric.unit == "s"
    point = metric.data.data_points[0]
    assert tuple(point.explicit_bounds) == boundaries
    assert point.count == 1
    assert dict(point.attributes) == {
        "http_request_method": "GET",
        "http_route": "/stats",
        "http_response_status_code": 200,
    }
