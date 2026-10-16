"""Repo-root pytest configuration.

Test-only tuning: the file-backed SQLite databases used by the CLI/MCP/API test
suites are opened by several short-lived connections per test. The production
``busy_timeout`` default (5s) is correct for multi-agent deployments but turns
those transient WAL lock waits into multi-second stalls under pytest. Cap it low
for the test session — production behaviour is unchanged (the constant default in
``storage._busy_timeout_ms`` stays 5000ms; the two unit tests that assert the
default/override manage this env var themselves).

Telemetry (task 1.1): every package's tests run with ``MINTMORY_OTEL_ENABLED=false``
by default, and an autouse fixture returns the telemetry module to its no-op shim
before and after each test, so no test builds a network exporter by accident.
"""

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("MINTMORY_SQLITE_BUSY_TIMEOUT_MS", "100")
os.environ.setdefault("MINTMORY_OTEL_ENABLED", "false")


@pytest.fixture(autouse=True)
def _reset_telemetry() -> Iterator[None]:
    """Keep each test on the no-op telemetry shim (spec: shared test fixtures)."""
    from mintmory.core import telemetry

    telemetry.reset_telemetry()
    yield
    telemetry.reset_telemetry()
