"""An injected exporter without the SDK says why telemetry is off (fix FB-006).

Spec: observability › an injected exporter without the SDK says why telemetry is off —
feedback FB-006.

``init_telemetry(span_exporter=...)`` / ``init_telemetry(metric_reader=...)`` ask for
telemetry through the caller's own exporter or reader. When the optional ``opentelemetry``
SDK is not installed (``_sdk_available()`` returns False) the call must return ``False``,
install no provider, and log exactly one WARNING on ``mintmory.telemetry`` that names the
missing SDK and the ``mintmory-core[otel]`` extra, so the caller learns why it is off
instead of silently getting a no-op shim.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default global providers.

    A successful init makes its providers global and the OTel API allows that only once
    per process; resetting the once-guards keeps the "no provider installed" assertions
    meaningful regardless of test order.
    """
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


@pytest.mark.l4("C-4f65c0b6")
@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"span_exporter": object()}, id="span_exporter"),
        pytest.param({"metric_reader": object()}, id="metric_reader"),
    ],
)
def test_an_injected_exporter_without_the_sdk_warns_why_telemetry_is_off(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    kwargs: dict[str, Any],
) -> None:
    """SDK missing + an injected exporter/reader: False, no provider, one install hint."""

    def _missing() -> bool:
        return False

    monkeypatch.setattr(telemetry, "_sdk_available", _missing)
    caplog.set_level(logging.WARNING, logger="mintmory.telemetry")

    result = telemetry.init_telemetry(**kwargs)

    assert result is False
    assert telemetry.is_enabled() is False
    assert telemetry._tracer is None
    assert telemetry._meter is None

    warnings = _otel_warnings(caplog)
    assert len(warnings) == 1, [record.getMessage() for record in warnings]
    message = warnings[0].getMessage()
    assert "sdk" in message.lower(), message
    assert "mintmory-core[otel]" in message, message
