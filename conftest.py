"""Repo-root pytest configuration.

Test-only tuning: the file-backed SQLite databases used by the CLI/MCP/API test
suites are opened by several short-lived connections per test. The production
``busy_timeout`` default (5s) is correct for multi-agent deployments but turns
those transient WAL lock waits into multi-second stalls under pytest. Cap it low
for the test session — production behaviour is unchanged (the constant default in
``storage._busy_timeout_ms`` stays 5000ms; the two unit tests that assert the
default/override manage this env var themselves).
"""

import os

os.environ.setdefault("MINTMORY_SQLITE_BUSY_TIMEOUT_MS", "100")
