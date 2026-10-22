"""Task 9.1 gate: a CLI-package test drives the shared ``otlp_receiver`` fixture.

Spec: observability › Shared telemetry test fixtures › A CLI-package test uses the receiver.

The runtime is exercised through the real OTLP/HTTP exporter over loopback: the test asks
for the root ``conftest.py`` receiver, points ``OTEL_EXPORTER_OTLP_ENDPOINT`` at it, creates
a span and shuts telemetry down, then reads the span back off the receiver. This pins both
the fixture (available to ``packages/cli/tests`` by name) and the runtime that reaches it.
"""

from __future__ import annotations

from typing import Any

import pytest
from mintmory.core import telemetry


@pytest.mark.l4("C-29c6c2b6")
def test_gate_cli_package_test_uses_the_shared_receiver(
    monkeypatch: pytest.MonkeyPatch, otlp_receiver: Any
) -> None:
    """A CLI-package test reaches the receiver and finds the span the runtime exported."""
    shutdown = getattr(telemetry, "shutdown_telemetry", None)
    assert shutdown is not None, "shutdown_telemetry is missing"

    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", otlp_receiver.endpoint)

    assert telemetry.init_telemetry() is True
    with telemetry.span("x"):
        pass
    shutdown()

    assert "x" in [name for name, _attributes in otlp_receiver.spans()]
