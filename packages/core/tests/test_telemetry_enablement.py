"""Enablement modes and per-signal exporter selection (task 3.1).

Spec: observability › Telemetry enablement modes, and observability › Exporter selection and
endpoint resolution.

These tests pin the runtime's on/off decision and the per-signal exporter choice:

* ``auto`` (the default) stays a no-op unless the SDK is present and a collector is there: with
  no endpoint variable it probes the default endpoint, and an explicit endpoint variable
  short-circuits that probe. ``false`` and ``OTEL_SDK_DISABLED`` win over ``true``.
* Without the SDK the runtime returns False and warns once with the install hint, but only when
  the mode or an endpoint variable asked for telemetry.
* Console exporters write to stderr (stdout is the MCP stdio stream); a signal set to ``none``
  builds no provider for it, and turning both off is a clean, silent False.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry

_RESULT_MARKER = "L4-RESULT:"

_SUBPROCESS_PROBE = r"""
import json
import sys

from mintmory.core import telemetry

probe_calls = []


def _reachable(url, timeout=0.1):
    probe_calls.append(url)
    return False


telemetry._endpoint_reachable = _reachable
result = telemetry.init_telemetry()
print("L4-RESULT:" + json.dumps({
    "result": result,
    "sdk_imported": "opentelemetry.sdk" in sys.modules,
    "probe_calls": probe_calls,
}))
"""

_ENDPOINT_VARIABLES = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
)


def _otel_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Only the WARNINGs ``telemetry.py`` logged on ``mintmory.telemetry``."""
    return [
        record
        for record in caplog.records
        if record.name == "mintmory.telemetry" and record.levelno == logging.WARNING
    ]


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default global providers.

    A successful init makes its providers global, and the OTel API lets that happen only once
    per process. Resetting the two once-guards keeps the "no provider for a signal" assertions
    meaningful regardless of test order.
    """
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


@pytest.mark.l4("C-2190b9f3")
def test_auto_without_a_collector_stays_off_in_a_fresh_process() -> None:
    """auto, no endpoint variable, unreachable endpoint: False and the SDK is never imported.

    The suite's own process already imported the SDK, so this runs in a child ``python -c``
    with every ``OTEL_*``/``MINTMORY_OTEL_*`` variable stripped (the root conftest.py's
    ``MINTMORY_OTEL_ENABLED=false`` would otherwise be inherited).
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("MINTMORY_OTEL_") and not key.startswith("OTEL_")
    }
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_PROBE],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    result_lines = [line for line in proc.stdout.splitlines() if line.startswith(_RESULT_MARKER)]
    assert result_lines, proc.stdout
    payload: dict[str, Any] = json.loads(result_lines[0][len(_RESULT_MARKER) :])
    assert payload["result"] is False
    assert payload["sdk_imported"] is False, "a no-op auto init must not import opentelemetry.sdk"
    assert payload["probe_calls"], "auto with no endpoint variable must probe the default endpoint"


@pytest.mark.l4("C-aba1a372")
def test_auto_with_a_reachable_endpoint_turns_on_and_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """auto + a reachable default endpoint exports, and the probe is what decided it."""
    monkeypatch.delenv("MINTMORY_OTEL_ENABLED", raising=False)
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "console")
    for variable in _ENDPOINT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    calls: list[str] = []

    def _reachable(url: str, timeout: float = 0.1) -> bool:
        calls.append(url)
        return True

    monkeypatch.setattr(telemetry, "_endpoint_reachable", _reachable)

    assert telemetry.init_telemetry() is True
    assert calls, "auto with no endpoint variable must probe the default endpoint"


@pytest.mark.l4("C-aba1a372")
def test_auto_with_an_endpoint_variable_turns_on_and_skips_the_probe(
    monkeypatch: pytest.MonkeyPatch, otlp_receiver: Any
) -> None:
    """auto + a set endpoint variable exports and never probes the default endpoint."""
    monkeypatch.delenv("MINTMORY_OTEL_ENABLED", raising=False)
    monkeypatch.delenv("MINTMORY_OTEL_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", otlp_receiver.endpoint)
    calls: list[str] = []

    def _unexpected(url: str, timeout: float = 0.1) -> bool:
        calls.append(url)
        return False

    monkeypatch.setattr(telemetry, "_endpoint_reachable", _unexpected)

    assert telemetry.init_telemetry() is True
    assert calls == [], "an explicit endpoint variable must skip the reachability probe"


@pytest.mark.l4("C-9d8f8f9c")
def test_explicit_off_wins_over_auto_and_over_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither MINTMORY_OTEL_ENABLED=false nor OTEL_SDK_DISABLED=true initialises telemetry."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "false")
    assert telemetry.init_telemetry() is False

    telemetry.reset_telemetry()
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "TRUE")
    assert telemetry.init_telemetry() is False

    # And the complementary enabling path is real: the same true mode without the override on.
    telemetry.reset_telemetry()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "console")
    assert telemetry.init_telemetry() is True


@pytest.mark.l4("C-ead28cef")
def test_sdk_missing_stays_off_and_warns_only_with_a_hint(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Without the SDK: False always; one install-hint warning iff the mode/endpoint asked."""

    def _missing() -> bool:
        return False

    def _unreachable(url: str, timeout: float = 0.1) -> bool:
        return False

    monkeypatch.setattr(telemetry, "_sdk_available", _missing)
    monkeypatch.setattr(telemetry, "_endpoint_reachable", _unreachable)
    caplog.set_level(logging.WARNING, logger="mintmory.telemetry")

    # (a) explicit true, no endpoint variable -> one hint
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    for variable in _ENDPOINT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    caplog.clear()
    assert telemetry.init_telemetry() is False
    warnings = _otel_warnings(caplog)
    assert len(warnings) == 1, [record.getMessage() for record in warnings]
    assert "mintmory-core[otel]" in warnings[0].getMessage()

    # (b) auto + an endpoint variable -> one hint
    telemetry.reset_telemetry()
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "auto")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://127.0.0.1:4318/v1/traces")
    caplog.clear()
    assert telemetry.init_telemetry() is False
    warnings = _otel_warnings(caplog)
    assert len(warnings) == 1, [record.getMessage() for record in warnings]
    assert "mintmory-core[otel]" in warnings[0].getMessage()

    # (c) auto, nothing asked for -> silence
    telemetry.reset_telemetry()
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "auto")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    caplog.clear()
    assert telemetry.init_telemetry() is False
    assert _otel_warnings(caplog) == []


@pytest.mark.l4("C-4d7716fe")
def test_console_exporter_writes_to_stderr_never_stdout(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """MINTMORY_OTEL_EXPORTER=console keeps stdout clean and puts the span on stderr."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "console")

    assert telemetry.init_telemetry() is True
    with telemetry.span("console-probe"):
        pass
    try:
        telemetry.shutdown_telemetry()
    except NotImplementedError:
        from opentelemetry import trace as otel_trace

        provider: Any = otel_trace.get_tracer_provider()
        provider.force_flush()

    out, err = capfd.readouterr()
    assert out == "", "the console exporter must never write to stdout (the MCP stdio stream)"
    assert "console-probe" in err


@pytest.mark.l4("C-6fc7f4c6")
@pytest.mark.parametrize(
    ("traces", "metrics", "disabled_signal"),
    [
        ("console", "none", "metric"),
        ("none", "console", "tracer"),
    ],
)
def test_one_signal_switched_off_builds_no_provider_for_it(
    monkeypatch: pytest.MonkeyPatch, traces: str, metrics: str, disabled_signal: str
) -> None:
    """`none` for a signal builds no provider; the other signal still exports."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.delenv("MINTMORY_OTEL_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", traces)
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", metrics)

    assert telemetry.init_telemetry() is True

    if disabled_signal == "metric":
        from opentelemetry import metrics as otel_metrics
        from opentelemetry.sdk.metrics import MeterProvider

        assert telemetry._meter is None
        assert not isinstance(otel_metrics.get_meter_provider(), MeterProvider)
        telemetry.record_value("x", 1.0)
    else:
        from opentelemetry import trace as otel_trace
        from opentelemetry.sdk.trace import TracerProvider

        assert telemetry._tracer is None
        assert not isinstance(otel_trace.get_tracer_provider(), TracerProvider)
        with telemetry.span("a") as sp:
            assert isinstance(sp, telemetry._NoopSpan)


@pytest.mark.l4("C-690840ae")
def test_both_signals_off_returns_false_without_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """MINTMORY_OTEL_EXPORTER=none with enabled=true is a clean, silent no-op."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "none")
    caplog.set_level(logging.WARNING, logger="mintmory.telemetry")

    assert telemetry.init_telemetry() is False
    assert telemetry.is_enabled() is False
    assert _otel_warnings(caplog) == []

    # And the same enabled mode with an exporting signal is real, not always False.
    telemetry.reset_telemetry()
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "console")
    assert telemetry.init_telemetry() is True
