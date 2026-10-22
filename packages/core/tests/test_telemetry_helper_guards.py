"""Recording a metric or a span attribute never raises into the caller (fix-2 task 1.1).

Spec: observability › Rejected hold: the diff is longer than 120000 characters: the judge saw
only the start — finding H-e0757174, criterion C-f0d6331e.

``counts_added``, ``add_count``, ``record_value`` and the span attributes set by ``embed_span``
and ``file_span`` are telemetry helpers: when the meter, a counter's ``add``, a histogram's
``record`` or a span's ``set_attribute`` raises, the error stays inside telemetry and the
wrapped work still happens. Each test also asks the helper for a real answer with a working
meter or span, so a no-op stub cannot satisfy it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import pytest
from mintmory.core import telemetry

pytest.importorskip("opentelemetry.sdk")


def _install(monkeypatch: pytest.MonkeyPatch, meter: Any) -> None:
    """Make ``telemetry`` enabled with the given meter and an empty instrument cache."""
    monkeypatch.setattr(telemetry, "_enabled", True)
    monkeypatch.setattr(telemetry, "_meter", meter)
    monkeypatch.setattr(telemetry, "_instruments", {})


class _RecordingCounter:
    def __init__(self) -> None:
        self.calls: list[tuple[int, dict[str, Any]]] = []

    def add(self, value: int, attributes: Mapping[str, Any]) -> None:
        self.calls.append((value, dict(attributes)))


class _RecordingHistogram:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, Any]]] = []

    def record(self, value: float, attributes: Mapping[str, Any]) -> None:
        self.calls.append((value, dict(attributes)))


class _RecordingMeter:
    """A meter whose counters and histograms record every point they receive."""

    def __init__(self) -> None:
        self.counters: dict[str, _RecordingCounter] = {}
        self.histograms: dict[str, _RecordingHistogram] = {}

    def create_counter(self, name: str, **kwargs: Any) -> _RecordingCounter:
        return self.counters.setdefault(name, _RecordingCounter())

    def create_histogram(self, name: str, **kwargs: Any) -> _RecordingHistogram:
        return self.histograms.setdefault(name, _RecordingHistogram())


class _BrokenMeter:
    """A meter whose instrument creation raises, as a failing provider would."""

    def create_counter(self, name: str, **kwargs: Any) -> Any:
        raise RuntimeError("meter-boom")

    def create_histogram(self, name: str, **kwargs: Any) -> Any:
        raise RuntimeError("meter-boom")


class _FlakyCounter:
    """A counter whose first ``add`` raises, then records like a healthy one."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, dict[str, Any]]] = []
        self._failed = False

    def add(self, value: int, attributes: Mapping[str, Any]) -> None:
        if not self._failed:
            self._failed = True
            raise RuntimeError("counter-boom")
        self.calls.append((value, dict(attributes)))


class _FlakyHistogram:
    """A histogram whose first ``record`` raises, then records like a healthy one."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, Any]]] = []
        self._failed = False

    def record(self, value: float, attributes: Mapping[str, Any]) -> None:
        if not self._failed:
            self._failed = True
            raise RuntimeError("histogram-boom")
        self.calls.append((value, dict(attributes)))


class _FlakyMeter:
    def __init__(self) -> None:
        self.counters: dict[str, _FlakyCounter] = {}
        self.histograms: dict[str, _FlakyHistogram] = {}

    def create_counter(self, name: str, **kwargs: Any) -> _FlakyCounter:
        return self.counters.setdefault(name, _FlakyCounter())

    def create_histogram(self, name: str, **kwargs: Any) -> _FlakyHistogram:
        return self.histograms.setdefault(name, _FlakyHistogram())


@pytest.mark.l4("C-f0d6331e")
def test_add_count_survives_a_meter_that_cannot_create_instruments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising ``create_counter`` is swallowed; a healthy meter still records the point."""
    _install(monkeypatch, _BrokenMeter())

    try:
        telemetry.add_count("mintmory.probe.add_count", 1)
    except Exception as error:  # the guard's whole point is that this never happens
        pytest.fail(f"add_count let {type(error).__name__} escape")

    recorder = _RecordingMeter()
    _install(monkeypatch, recorder)
    telemetry.add_count("mintmory.probe.add_count", 4, category="fact")
    assert recorder.counters["mintmory.probe.add_count"].calls == [(4, {"category": "fact"})]


@pytest.mark.l4("C-f0d6331e")
def test_add_count_survives_a_counter_add_that_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising ``counter.add`` is swallowed; a later add on the same counter still lands."""
    meter = _FlakyMeter()
    _install(monkeypatch, meter)

    try:
        telemetry.add_count("mintmory.probe.counter_add", 1)
    except Exception as error:
        pytest.fail(f"add_count let {type(error).__name__} escape")

    telemetry.add_count("mintmory.probe.counter_add", 2, category="skill")
    assert meter.counters["mintmory.probe.counter_add"].calls == [(2, {"category": "skill"})]


@pytest.mark.l4("C-f0d6331e")
def test_record_value_survives_a_meter_that_cannot_create_instruments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising ``create_histogram`` is swallowed; a healthy meter still records the point."""
    _install(monkeypatch, _BrokenMeter())

    try:
        telemetry.record_value("mintmory.probe.record_value", 1.5, unit="ms", phase="fts")
    except Exception as error:
        pytest.fail(f"record_value let {type(error).__name__} escape")

    recorder = _RecordingMeter()
    _install(monkeypatch, recorder)
    telemetry.record_value("mintmory.probe.record_value", 2.5, unit="ms", phase="fts")
    assert recorder.histograms["mintmory.probe.record_value"].calls == [(2.5, {"phase": "fts"})]


@pytest.mark.l4("C-f0d6331e")
def test_record_value_survives_a_histogram_record_that_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising ``histogram.record`` is swallowed; a later record on the same histogram lands."""
    meter = _FlakyMeter()
    _install(monkeypatch, meter)

    try:
        telemetry.record_value("mintmory.probe.histogram_record", 1.0, unit="ms")
    except Exception as error:
        pytest.fail(f"record_value let {type(error).__name__} escape")

    telemetry.record_value("mintmory.probe.histogram_record", 3.0, unit="ms", phase="graph")
    assert meter.histograms["mintmory.probe.histogram_record"].calls == [(3.0, {"phase": "graph"})]


class _Category:
    def __init__(self, value: str) -> None:
        self.value = value


class _Record:
    def __init__(self, category: str) -> None:
        self.category = _Category(category)


@pytest.mark.l4("C-f0d6331e")
def test_counts_added_returns_the_record_when_the_counter_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising ``add_count`` never stops ``add_memory`` from returning its stored record."""

    def _broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("count-boom")

    monkeypatch.setattr(telemetry, "add_count", _broken)

    def _add(category: str) -> _Record:
        return _Record(category)

    wrapped = telemetry.counts_added(_add)
    try:
        record = wrapped("fact")
    except Exception as error:
        pytest.fail(f"counts_added let {type(error).__name__} escape")

    assert isinstance(record, _Record)
    assert record.category.value == "fact"


class _AttributeRaisingSpan:
    """A span whose every attribute write raises, as a broken SDK span would."""

    def __init__(self) -> None:
        self.attempted: list[str] = []

    def set_attribute(self, key: str, value: Any) -> None:
        self.attempted.append(key)
        raise RuntimeError("set-attribute-boom")

    def set_attributes(self, attributes: Mapping[str, Any]) -> None:
        self.attempted.extend(attributes)
        raise RuntimeError("set-attribute-boom")

    def set_status(self, status: Any) -> None:
        raise RuntimeError("set-status-boom")

    def record_exception(self, exc: BaseException) -> None:
        raise RuntimeError("record-exception-boom")

    def is_recording(self) -> bool:
        return True


class _AttributeRaisingTracer:
    """A tracer that hands out spans whose attribute writes raise."""

    def __init__(self) -> None:
        self.spans: list[_AttributeRaisingSpan] = []

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any) -> Iterator[Any]:
        span = _AttributeRaisingSpan()
        self.spans.append(span)
        yield span


def _install_broken_tracer(monkeypatch: pytest.MonkeyPatch) -> _AttributeRaisingTracer:
    tracer = _AttributeRaisingTracer()
    monkeypatch.setattr(telemetry, "_enabled", True)
    monkeypatch.setattr(telemetry, "_tracer", tracer)
    return tracer


@pytest.mark.l4("C-f0d6331e")
def test_span_attribute_failure_does_not_escape_the_context_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising ``set_attribute`` is swallowed and the ``with`` body still runs."""
    tracer = _install_broken_tracer(monkeypatch)

    reached = False
    try:
        with telemetry.span("mintmory.probe.span", phase="fts"):
            reached = True
    except Exception as error:
        pytest.fail(f"span let {type(error).__name__} escape")

    assert reached is True
    assert [key for span in tracer.spans for key in span.attempted] == ["phase"]


class _EmbedderStub:
    provider = "hashing"
    model_name = "hashing-v1"
    dimensions = 8

    def embed(self, text: str) -> list[str]:
        return [text]


@pytest.mark.l4("C-f0d6331e")
def test_embed_span_still_returns_when_span_attributes_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The embedder's answer survives a failing ``mintmory.embed`` attribute write."""
    tracer = _install_broken_tracer(monkeypatch)

    wrapped = telemetry.embed_span(_EmbedderStub.embed)
    try:
        vector = wrapped(_EmbedderStub(), "alpha")
    except Exception as error:
        pytest.fail(f"embed_span let {type(error).__name__} escape")

    assert vector == ["alpha"]
    attempted = [key for span in tracer.spans for key in span.attempted]
    assert "mintmory.embed.provider" in attempted


@pytest.mark.l4("C-f0d6331e")
def test_file_span_body_runs_when_span_attributes_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing file attribute write does not stop the guarded conversion block."""
    tracer = _install_broken_tracer(monkeypatch)

    reached = False
    try:
        with telemetry.file_span("mintmory.convert.file", suffix=".txt", size_bytes=3):
            reached = True
    except Exception as error:
        pytest.fail(f"file_span let {type(error).__name__} escape")

    assert reached is True
    attempted = [key for span in tracer.spans for key in span.attempted]
    assert "mintmory.file.suffix" in attempted
