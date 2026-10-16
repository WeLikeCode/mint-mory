"""``init_telemetry`` never raises and rolls back its partial build (task 4.5).

Spec: observability › Telemetry init never raises -
"``init_telemetry`` SHALL NOT raise. ... Any exception while importing the SDK or building
exporters, processors, readers or providers ... SHALL be caught: init runs
``shutdown_telemetry``'s teardown on what it built under the lock it already holds (not taken
again), so no global provider, no state and the saved logger level restored, logs one WARNING
on ``mintmory.telemetry`` containing ``telemetry disabled: init failed (<exception class
name>)`` without the message, and returns False. Callers need no guard."

The first test makes the *metric* build fail after the tracer build already succeeded (an
invalid OTLP timeout surfaces as the exporter's own ``ValueError``), so the teardown must
release the provider that was already installed, not just what was left half-built. The second
pins the "constructs ``OTelSettings()``, never ``load_settings()``" clause: an invalid value of
a *different* settings group must not turn a span into a failure.

``_reset_telemetry`` here shadows the root ``conftest.py`` fixture of the same name for this
module only: these tests own the telemetry state they install and stay runnable (and fail by
assertion) against a unit base where ``telemetry.reset_telemetry`` is absent.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry

_EXPORTER_LOGGER = "opentelemetry.exporter.otlp.proto.http"
_ENDPOINT_VARIABLES = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
)


@pytest.fixture(autouse=True)
def _reset_telemetry() -> Iterator[None]:
    """Own this module's telemetry state; tolerate the helper being absent (unit base)."""
    reset = getattr(telemetry, "reset_telemetry", None)
    if reset is not None:
        reset()
    yield
    if reset is not None:
        reset()


@pytest.mark.l4("C-c724dabe")
def test_a_failed_build_after_the_tracer_is_up_tears_everything_down(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Trace exporter built, metric exporter ValueError: no state, no global, warning, False."""
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace import TracerProvider

    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.delenv("MINTMORY_OTEL_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "console")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "otlp")
    for variable in _ENDPOINT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_TIMEOUT", "abc")
    exporter_logger = logging.getLogger(_EXPORTER_LOGGER)
    exporter_logger.setLevel(logging.NOTSET)
    caplog.set_level(logging.DEBUG)

    result = telemetry.init_telemetry()

    assert result is False
    assert telemetry.is_enabled() is False
    assert telemetry._tracer is None
    assert telemetry._meter is None
    assert telemetry._tracer_provider is None
    assert telemetry._meter_provider is None
    assert telemetry._saved_exporter_level is None
    assert not isinstance(otel_trace.get_tracer_provider(), TracerProvider)
    assert exporter_logger.level == logging.NOTSET

    messages = [record.getMessage() for record in caplog.records]
    assert any("telemetry disabled: init failed (ValueError)" in message for message in messages), (
        messages
    )
    assert not any("could not convert" in message for message in messages), messages

    # The failure left a clean slate: a corrected init still exports.
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "console")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_TIMEOUT")
    assert telemetry.init_telemetry() is True


@pytest.mark.l4("C-044e54eb")
def test_init_does_not_read_another_settings_group(monkeypatch: pytest.MonkeyPatch) -> None:
    """MINTMORY_SUMMARY_CONCURRENCY=0 does not stop an injected init from tagging its spans."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    monkeypatch.setenv("MINTMORY_SUMMARY_CONCURRENCY", "0")
    exporter = InMemorySpanExporter()

    try:
        result: Any = telemetry.init_telemetry(
            default_service_name="mintmory-cli", span_exporter=exporter
        )
    except TypeError:  # a unit base without the test seam is a failure, not an error
        result = "init_telemetry is missing the test seam"
    assert result is True

    with telemetry.span("cli-probe"):
        pass

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["cli-probe"]
    assert {span.resource.attributes.get("service.name") for span in spans} == {"mintmory-cli"}
    assert telemetry.is_enabled() is True
