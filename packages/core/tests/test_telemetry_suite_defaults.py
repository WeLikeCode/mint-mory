"""The root conftest.py telemetry defaults (spec: observability › Shared telemetry test fixtures).

Task 1.1 gives every package's tests ``MINTMORY_OTEL_ENABLED=false`` by default and an autouse
``telemetry.reset_telemetry()`` around each test. These tests pin both facts: one reads the
environment the root conftest.py seeds, the other the reset helper the autouse fixture calls.
"""

from __future__ import annotations

import os

import mintmory.core.telemetry as telemetry
import pytest


@pytest.mark.l4("C-29c6c2b6")
def test_suite_runs_with_otel_disabled_by_default() -> None:
    """The root conftest.py defaults MINTMORY_OTEL_ENABLED to "false" for every package's tests."""
    assert os.environ.get("MINTMORY_OTEL_ENABLED") == "false"


@pytest.mark.l4("C-29c6c2b6")
def test_reset_telemetry_restores_the_noop_shim() -> None:
    """The autouse reset fixture needs telemetry.reset_telemetry() to clear the module state."""
    telemetry._enabled = True
    telemetry._tracer = object()
    telemetry._meter = object()
    telemetry._instruments["probe"] = object()
    try:
        telemetry.reset_telemetry()
        assert telemetry.is_enabled() is False
        assert telemetry._tracer is None
        assert telemetry._meter is None
        assert telemetry._instruments == {}
    finally:
        telemetry._enabled = False
        telemetry._tracer = None
        telemetry._meter = None
        telemetry._instruments.clear()
