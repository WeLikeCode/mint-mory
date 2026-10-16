"""OTelSettings defaults, normalisation and fallbacks (task 2.1).

Spec: observability › Invalid MintMory telemetry settings fall back.

Task 2.1 reshapes ``OTelSettings`` into the runtime's read-once settings object: ``enabled`` becomes
the string ``"auto"`` (a bool would swallow the enablement mode), ``exporter`` defaults to the OTLP
exporter, ``service_name`` is unset (the entry point's default fills it in) and ``export_timeout_s``
is 3.0. Constructing it must never raise for a bad ``MINTMORY_OTEL_*`` value: each bad value logs
one WARNING on ``mintmory.telemetry`` naming the variable and falls back to the default; booleans
and case are normalised (``True`` and ``"TRUE"`` both mean ``"true"``).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest


def _settings_or_error(**kwargs: Any) -> tuple[Any, Exception | None]:
    """Build ``OTelSettings``, returning ``(settings, None)`` or ``(None, error)``.

    The requirement is that construction never raises, so a raise is captured and asserted on
    instead of escaping as a test error (which would not prove the fallback behaviour).
    """
    from mintmory.core.config import OTelSettings

    try:
        return OTelSettings(**kwargs), None
    except Exception as exc:
        return None, exc


def _otel_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """Only the WARNINGs ``config.py`` logged on ``mintmory.telemetry``."""
    return [
        record
        for record in caplog.records
        if record.name == "mintmory.telemetry" and record.levelno == logging.WARNING
    ]


@pytest.mark.l4("C-e1c42220")
def test_bad_mintmory_values_fall_back_with_one_warning_each(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A bad enabled/exporter/timeout warns once and falls back; construction does not raise."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "maybe")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "jaeger")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", "abc")
    caplog.set_level(logging.WARNING)

    settings, error = _settings_or_error()

    assert error is None, f"OTelSettings() must not raise for bad MINTMORY_OTEL_* values: {error!r}"
    assert settings.enabled == "auto"
    assert settings.exporter == "otlp"
    assert getattr(settings, "export_timeout_s", None) == 3.0

    warnings = _otel_warnings(caplog)
    messages = [record.getMessage() for record in warnings]
    assert len(warnings) == 3, messages
    for variable in (
        "MINTMORY_OTEL_ENABLED",
        "MINTMORY_OTEL_EXPORTER",
        "MINTMORY_OTEL_EXPORT_TIMEOUT_S",
    ):
        assert len([m for m in messages if variable in m]) == 1, (variable, messages)


@pytest.mark.l4("C-e1c42220")
def test_defaults_are_auto_otlp_no_service_name_and_three_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing set, OTelSettings carries the values every fallback targets."""
    monkeypatch.delenv("MINTMORY_OTEL_ENABLED", raising=False)
    monkeypatch.delenv("MINTMORY_OTEL_EXPORTER", raising=False)
    monkeypatch.delenv("MINTMORY_OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", raising=False)

    settings, error = _settings_or_error()

    assert error is None, f"OTelSettings() must not raise with no env set: {error!r}"
    assert settings.enabled == "auto"
    assert settings.exporter == "otlp"
    assert settings.service_name is None
    assert getattr(settings, "export_timeout_s", None) == 3.0


@pytest.mark.l4("C-e1c42220")
def test_boolean_and_case_are_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    """``True``/``"TRUE"``/``"False"`` all become the lowercase strings of the Literal."""
    for raw, expected in (("TRUE", "true"), ("True", "true"), ("FALSE", "false")):
        monkeypatch.setenv("MINTMORY_OTEL_ENABLED", raw)
        settings, error = _settings_or_error()
        assert error is None, f"OTelSettings() must not raise for enabled={raw!r}: {error!r}"
        assert settings.enabled == expected, (raw, settings.enabled)

    for value, expected in ((True, "true"), (False, "false")):
        settings, error = _settings_or_error(enabled=value)
        assert error is None, f"OTelSettings(enabled={value!r}) must not raise: {error!r}"
        assert settings.enabled == expected, (value, settings.enabled)


@pytest.mark.l4("C-e1c42220")
def test_valid_values_are_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    """Good values are passed through unchanged (no spurious fallback or warning)."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "false")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "console")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", "1.5")

    settings, error = _settings_or_error()

    assert error is None, f"OTelSettings() must not raise for valid values: {error!r}"
    assert settings.enabled == "false"
    assert settings.exporter == "console"
    assert getattr(settings, "export_timeout_s", None) == pytest.approx(1.5)


@pytest.mark.l4("C-e1c42220")
@pytest.mark.parametrize("raw", ["0", "-1", "abc"])
def test_non_positive_or_non_numeric_timeout_falls_back_to_three(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, raw: str
) -> None:
    """A timeout that is non-numeric or not positive warns once and falls back to 3.0."""
    monkeypatch.setenv("MINTMORY_OTEL_EXPORT_TIMEOUT_S", raw)
    caplog.set_level(logging.WARNING)

    settings, error = _settings_or_error()

    assert error is None, f"OTelSettings() must not raise for timeout={raw!r}: {error!r}"
    assert getattr(settings, "export_timeout_s", None) == 3.0
    warnings = _otel_warnings(caplog)
    messages = [record.getMessage() for record in warnings]
    assert len(warnings) == 1, messages
    assert "MINTMORY_OTEL_EXPORT_TIMEOUT_S" in messages[0]
