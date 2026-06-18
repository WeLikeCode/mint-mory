#!/usr/bin/env python
"""
MintMory dreaming daemon (ROADMAP M8).

An asyncio loop that periodically runs the full dreaming consolidation pass over
a MintMory SQLite database. The database path is taken from the ``MINTMORY_DB``
environment variable (default ``~/.mintmory/memory.db``); the interval between
runs from ``MINTMORY_DREAM_INTERVAL_HOURS`` (default 6 hours).

Design notes:
  * Each cycle runs ``DreamingEngine.run_full`` inside ``asyncio.to_thread`` so
    the blocking SQLite work never stalls the event loop.
  * The loop NEVER crashes on a step error — a failed cycle is logged via
    structlog and the daemon continues to the next interval.
  * Importing this module has no side effects: the loop only starts under the
    ``if __name__ == "__main__"`` guard.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import structlog
from mintmory.core.dreaming import DreamingEngine
from mintmory.core.storage import StorageAdapter

log = structlog.get_logger("mintmory.dreamd")

DEFAULT_DB_PATH = "~/.mintmory/memory.db"
DEFAULT_INTERVAL_HOURS = 6.0


def _db_path() -> str:
    """Resolve the database path from ``MINTMORY_DB`` (``~`` expanded)."""
    raw = os.environ.get("MINTMORY_DB", DEFAULT_DB_PATH)
    return str(Path(raw).expanduser())


def _interval_seconds() -> float:
    """Resolve the dream interval (seconds) from ``MINTMORY_DREAM_INTERVAL_HOURS``."""
    raw = os.environ.get("MINTMORY_DREAM_INTERVAL_HOURS")
    if raw is None:
        hours = DEFAULT_INTERVAL_HOURS
    else:
        try:
            hours = float(raw)
        except ValueError:
            log.warning(
                "invalid MINTMORY_DREAM_INTERVAL_HOURS; using default",
                value=raw,
                default_hours=DEFAULT_INTERVAL_HOURS,
            )
            hours = DEFAULT_INTERVAL_HOURS
    return max(0.0, hours) * 3600.0


def _run_cycle(engine: DreamingEngine) -> None:
    """Run one full dreaming cycle, logging the resulting report."""
    report = engine.run_full()
    log.info(
        "dream cycle complete",
        intensity=report.intensity.value,
        duration_ms=round(report.duration_ms, 2),
        new_links=report.new_links,
        new_summaries=report.new_summaries,
        contradictions_resolved=report.contradictions_resolved,
        memories_archived=report.memories_archived,
        memories_rehabilitated=report.memories_rehabilitated,
    )


async def dream_loop(
    engine: DreamingEngine,
    interval_seconds: float,
    *,
    iterations: int | None = None,
) -> None:
    """
    Run dreaming cycles forever (or ``iterations`` times, for tests).

    A step error in a cycle is caught, logged, and the loop continues after the
    interval — the daemon never crashes on a single bad run.
    """
    completed = 0
    while iterations is None or completed < iterations:
        try:
            await asyncio.to_thread(_run_cycle, engine)
        except Exception as exc:  # noqa: BLE001 - never crash the daemon
            log.error("dream cycle failed", error=str(exc), exc_info=True)
        completed += 1
        if iterations is not None and completed >= iterations:
            break
        await asyncio.sleep(interval_seconds)


async def main() -> None:
    """Daemon entrypoint: open the store, then loop forever."""
    db_path = _db_path()
    interval = _interval_seconds()

    # Ensure the parent directory exists for the default ~/.mintmory location.
    parent = Path(db_path).parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)

    adapter = StorageAdapter(db_path)
    adapter.initialise()
    engine = DreamingEngine(adapter)

    log.info(
        "mintmory dreamd starting",
        db_path=db_path,
        interval_hours=interval / 3600.0,
    )
    try:
        await dream_loop(engine, interval)
    finally:
        adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
