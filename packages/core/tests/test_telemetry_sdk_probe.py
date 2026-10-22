"""``_sdk_available`` survives a failing ``importlib.util.find_spec`` (fix FB-001).

Spec: observability › _sdk_available must catch ImportError and ValueError from — feedback
FB-001.

When the optional ``opentelemetry`` SDK is not installed, ``importlib.util.find_spec`` raises
``ModuleNotFoundError`` (an ``ImportError``) for ``opentelemetry.sdk``; it can also raise
``ValueError``. Either way the probe must answer ``False`` and ``init_telemetry`` must return
``False`` without raising: ``auto`` with nothing asked for stays silent, while an explicit
``true`` logs exactly one WARNING naming the ``mintmory-core[otel]`` extra.

These tests deliberately patch ``importlib.util.find_spec`` rather than the probe itself, so they
pin the probe's own error handling rather than the mode decision around it.
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Iterator

import pytest
from mintmory.core import telemetry

_ENDPOINT_VARIABLES = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
)


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default global providers."""
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


def _otel_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Only the WARNINGs ``telemetry.py`` logged on ``mintmory.telemetry``."""
    return [
        record
        for record in caplog.records
        if record.name == "mintmory.telemetry" and record.levelno == logging.WARNING
    ]


@pytest.mark.l4("C-248f68ba")
def test_module_not_found_from_find_spec_is_caught_and_warns_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """true mode + find_spec raising ModuleNotFoundError: False and one install-hint warning."""

    def _raise_module_not_found(name: str) -> object:
        raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    monkeypatch.setattr(importlib.util, "find_spec", _raise_module_not_found)
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    for variable in _ENDPOINT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    caplog.set_level(logging.WARNING, logger="mintmory.telemetry")

    try:
        result: object = telemetry.init_telemetry()
    except Exception as error:  # the requirement is that this never happens
        pytest.fail(f"init_telemetry raised {type(error).__name__}")

    assert result is False
    warnings = _otel_warnings(caplog)
    assert len(warnings) == 1, [record.getMessage() for record in warnings]
    assert "mintmory-core[otel]" in warnings[0].getMessage()


@pytest.mark.l4("C-248f68ba")
def test_value_error_from_find_spec_is_caught_and_auto_stays_silent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """auto mode + find_spec raising ValueError: False and no warning at all."""

    def _raise_value_error(name: str) -> object:
        raise ValueError(f"{name}.__spec__ is None")

    monkeypatch.setattr(importlib.util, "find_spec", _raise_value_error)
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "auto")
    for variable in _ENDPOINT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    caplog.set_level(logging.WARNING, logger="mintmory.telemetry")

    try:
        result: object = telemetry.init_telemetry()
    except Exception as error:  # the requirement is that this never happens
        pytest.fail(f"init_telemetry raised {type(error).__name__}")

    assert result is False
    assert _otel_warnings(caplog) == []
