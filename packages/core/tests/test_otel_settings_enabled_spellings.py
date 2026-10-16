"""MINTMORY_OTEL_ENABLED keeps every boolean spelling it accepted before (task 1.2).

Spec: observability › MINTMORY_OTEL_ENABLED keeps the boolean spellings it accepted before
(feedback FB-004).

Before the runtime's string modes, ``enabled`` was a plain pydantic ``bool``, so ``1``,
``yes`` and ``on`` meant true and ``0``, ``no`` and ``off`` meant false. The string mode must
keep every spelling pydantic's boolean parser accepts — mapped to ``"true"``/``"false"`` with
no WARNING — keep ``auto`` as the third mode, and only fall back to ``auto`` (one WARNING) for
a value pydantic would have rejected.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

_TRUE_SPELLINGS = ("1", "yes", "on", "t", "y")
_FALSE_SPELLINGS = ("0", "no", "off", "f", "n")

_BOOLEAN_SPELLINGS: list[tuple[str, str]] = [
    *((raw, "true") for raw in _TRUE_SPELLINGS),
    *((raw, "false") for raw in _FALSE_SPELLINGS),
    *((raw.upper(), "true") for raw in _TRUE_SPELLINGS),
    *((raw.upper(), "false") for raw in _FALSE_SPELLINGS),
]

_MODES: tuple[tuple[str, str], ...] = (
    ("auto", "auto"),
    ("AUTO", "auto"),
    ("true", "true"),
    ("TRUE", "true"),
    ("false", "false"),
    ("FALSE", "false"),
)


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


@pytest.mark.l4("C-2261ae94")
@pytest.mark.parametrize(("raw", "expected"), _BOOLEAN_SPELLINGS)
def test_boolean_spelling_maps_without_a_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    raw: str,
    expected: str,
) -> None:
    """1/yes/on/t/y mean true and 0/no/off/f/n mean false, silently, in any case."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", raw)
    caplog.set_level(logging.WARNING, logger="mintmory.telemetry")

    settings, error = _settings_or_error()

    assert error is None, f"OTelSettings() must not raise for enabled={raw!r}: {error!r}"
    assert settings.enabled == expected, (raw, settings.enabled)
    warnings = _otel_warnings(caplog)
    assert warnings == [], (raw, [record.getMessage() for record in warnings])


@pytest.mark.l4("C-2261ae94")
def test_modes_keep_meaning_and_invalid_values_fall_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """auto/true/false survive; boolean spellings map; anything else warns and falls back."""
    caplog.set_level(logging.WARNING, logger="mintmory.telemetry")

    # auto, true and false (any case) keep their meaning, silently.
    for raw, expected in _MODES:
        monkeypatch.setenv("MINTMORY_OTEL_ENABLED", raw)
        caplog.clear()
        settings, error = _settings_or_error()
        assert error is None, (raw, error)
        assert settings.enabled == expected, (raw, settings.enabled)
        warnings = _otel_warnings(caplog)
        assert warnings == [], (raw, [record.getMessage() for record in warnings])

    # The boolean spellings map to their boolean mode, silently.
    for raw, expected in _BOOLEAN_SPELLINGS:
        monkeypatch.setenv("MINTMORY_OTEL_ENABLED", raw)
        caplog.clear()
        settings, error = _settings_or_error()
        assert error is None, (raw, error)
        assert settings.enabled == expected, (raw, settings.enabled)
        warnings = _otel_warnings(caplog)
        assert warnings == [], (raw, [record.getMessage() for record in warnings])

    # Any value pydantic would reject still falls back to auto with exactly one WARNING.
    for raw in ("maybe", "2", "telemetry"):
        monkeypatch.setenv("MINTMORY_OTEL_ENABLED", raw)
        caplog.clear()
        settings, error = _settings_or_error()
        assert error is None, (raw, error)
        assert settings.enabled == "auto", (raw, settings.enabled)
        warnings = _otel_warnings(caplog)
        assert len(warnings) == 1, (raw, [record.getMessage() for record in warnings])
        assert "MINTMORY_OTEL_ENABLED" in warnings[0].getMessage(), (raw, warnings[0].getMessage())
