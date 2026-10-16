"""The OTLP/HTTP exporter logger level is muted then restored (task 4.4).

Spec: observability › Bounded flush on exit › "The exporter logger level is restored", and
observability › Export never blocks or floods when the collector is absent -
"While telemetry runs, logger ``opentelemetry.exporter.otlp.proto.http`` SHALL be at
CRITICAL."

Building a real OTLP/HTTP exporter saves the exporter logger's level the first time it mutes
it and raises the level to CRITICAL; ``shutdown_telemetry`` puts the saved level back. These
tests drive the round trip through the public ``init_telemetry`` / ``shutdown_telemetry`` seam
against a real (unreached) OTLP/HTTP endpoint, so a level saved as CRITICAL by a later init
would fail the second restore.

``_reset_telemetry`` here shadows the root conftest.py fixture of the same name for this
module only: this test owns the telemetry state it installs and must still run (and fail by
assertion) on code where the root fixture's ``telemetry.reset_telemetry`` helper is absent.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from mintmory.core import telemetry

_EXPORTER_LOGGER = "opentelemetry.exporter.otlp.proto.http"


@pytest.fixture(autouse=True)
def _reset_telemetry() -> Iterator[None]:
    """Own this module's telemetry state; tolerate the helper being absent (unit base)."""
    reset = getattr(telemetry, "reset_telemetry", None)
    if reset is not None:
        reset()
    yield
    if reset is not None:
        reset()


def _enable_otlp(monkeypatch: pytest.MonkeyPatch) -> None:
    """One real OTLP exporter for each signal, pointed at an endpoint nobody listens on."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")


@pytest.mark.l4("C-1d2bd9a4")
def test_otlp_exporter_logger_is_critical_while_running_and_restored_after_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One init/shutdown cycle: CRITICAL while telemetry runs, the starting level afterwards."""
    _enable_otlp(monkeypatch)
    exporter_logger = logging.getLogger(_EXPORTER_LOGGER)
    exporter_logger.setLevel(logging.NOTSET)

    assert telemetry.init_telemetry() is True
    assert exporter_logger.level == logging.CRITICAL

    telemetry.shutdown_telemetry()
    assert exporter_logger.level == logging.NOTSET


@pytest.mark.l4("C-1d2bd9a4")
def test_otlp_exporter_logger_level_round_trips_across_two_init_shutdown_cycles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second init re-mutes and a second shutdown restores; the saved level is re-read first."""
    _enable_otlp(monkeypatch)
    exporter_logger = logging.getLogger(_EXPORTER_LOGGER)
    exporter_logger.setLevel(logging.NOTSET)

    assert telemetry.init_telemetry() is True
    assert exporter_logger.level == logging.CRITICAL
    telemetry.shutdown_telemetry()
    assert exporter_logger.level == logging.NOTSET

    assert telemetry.init_telemetry() is True
    assert exporter_logger.level == logging.CRITICAL
    telemetry.shutdown_telemetry()
    assert exporter_logger.level == logging.NOTSET
