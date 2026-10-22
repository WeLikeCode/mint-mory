"""Telemetry-runtime behaviour ``packages/mcp/tests/test_telemetry_init.py`` depends on (7.2).

Spec: observability › Telemetry enablement modes.

Task 7.2 keeps the MCP entry-point tests passing unchanged in their calls: ``server.main()``
still calls ``init_telemetry(load_settings().otel)`` before it starts serving (so the existing
fake still takes a ``settings`` argument), and ``test_main_telemetry_default_off_is_safe``
deletes ``MINTMORY_OTEL_ENABLED``, which now yields the ``auto`` mode. ``auto`` probes the
default collector endpoint and, with nothing listening, must still be a safe no-op; the same
entry point must still turn telemetry on when a collector answers, and an explicit off (the
``MINTMORY_OTEL_ENABLED=false`` suite default, or the ``OTEL_SDK_DISABLED`` kill switch) must
short-circuit before the probe.

The existing test only asserts "does not raise", so this module pins the same entry-point
behaviour deterministically (through the reachability seam) and adds the positive controls the
original lacked: a test that only asserted zero-value outcomes would prove nothing.

``_reset_telemetry`` shadows the root ``conftest.py`` fixture of the same name for this module
only: the tests own the telemetry state they install and stay runnable — and fail by assertion,
not error — against a unit base without ``telemetry.reset_telemetry`` and without the
``_endpoint_reachable`` seam.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.mcp import server

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


def _run_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the real ``server.main()`` without starting a transport loop."""
    monkeypatch.setattr(server.mcp, "run", _noop_run)
    monkeypatch.setattr("sys.argv", ["mintmory-mcp"])
    server.main()


def _noop_run(*args: Any, **kwargs: Any) -> None:
    return None


@pytest.mark.l4("C-2190b9f3")
def test_mcp_main_auto_without_a_collector_stays_a_safe_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deleted ``MINTMORY_OTEL_ENABLED`` (auto) + no collector: main() probes, exports nothing.

    The reachability seam is patched so the test never depends on what happens to listen on
    ``localhost:4318``: ``auto`` with no endpoint variable must probe the default endpoint and stay
    a no-op. The positive control proves the entry point is wired — the same call with a collector
    that answers turns telemetry on.
    """
    monkeypatch.delenv("MINTMORY_OTEL_ENABLED", raising=False)
    for variable in _ENDPOINT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

    assert hasattr(telemetry, "_endpoint_reachable"), (
        "the runtime must expose the reachability probe seam"
    )

    probes: list[str] = []

    def _unreachable(url: str, timeout: float = 0.1) -> bool:
        probes.append(url)
        return False

    monkeypatch.setattr(telemetry, "_endpoint_reachable", _unreachable)

    _run_main(monkeypatch)  # must not raise

    assert telemetry.is_enabled() is False
    assert probes == ["http://localhost:4318"], (
        "auto with no endpoint variable must probe the default endpoint exactly once"
    )

    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "console")
    monkeypatch.setattr(telemetry, "_endpoint_reachable", _reachable)
    _run_main(monkeypatch)

    assert telemetry.is_enabled() is True, "the entry point must be able to turn telemetry on"


@pytest.mark.l4("C-9d8f8f9c")
def test_mcp_main_explicit_off_wins_over_reachability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The suite default ``MINTMORY_OTEL_ENABLED=false`` and ``OTEL_SDK_DISABLED`` keep main() off.

    Both an explicit ``false`` and the standard kill switch must short-circuit before the
    reachability probe, even when that probe would have answered. The positive control (kill switch
    removed) proves the entry point is wired: the same call turns telemetry on.
    """
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "false")

    assert hasattr(telemetry, "_endpoint_reachable"), (
        "the runtime must expose the reachability probe seam"
    )

    probes: list[str] = []

    def _reachable(url: str, timeout: float = 0.1) -> bool:
        probes.append(url)
        return True

    monkeypatch.setattr(telemetry, "_endpoint_reachable", _reachable)

    _run_main(monkeypatch)

    assert telemetry.is_enabled() is False
    assert probes == [], "explicit off must short-circuit before the reachability probe"

    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "console")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "TRUE")
    _run_main(monkeypatch)

    assert telemetry.is_enabled() is False, "OTEL_SDK_DISABLED must win over an explicit true"
    assert probes == [], "the standard kill switch must short-circuit before the probe"

    monkeypatch.delenv("OTEL_SDK_DISABLED")
    _run_main(monkeypatch)

    assert telemetry.is_enabled() is True, "the entry point must be able to turn telemetry on"


def _reachable(url: str, timeout: float = 0.1) -> bool:
    return True
