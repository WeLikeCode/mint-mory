"""
PostgreSQL soak test — concurrent write/read under load.

Skipped unless ``MINTMORY_TEST_PG_DSN`` is set in the environment.

Verifies that the PostgresBackend holds up under concurrent writers and
readers without deadlocks, constraint violations, or data loss:

  * N_WRITERS goroutines each insert M memories (add_memory)
  * N_READERS goroutines each search 3 times (search)
  * One apply_feedback goroutine fires stale+useful votes concurrently
  * After all tasks complete: get_stats() totals are consistent
  * No exception must propagate from any task (failures are collected and
    re-raised as a compound assertion)

  * Lost-update invariant test: N concurrent threads each fire one
    apply_feedback(useful=True) on the SAME memory_id; after all threads
    complete, reinforcement_count MUST equal N (atomicity of the single-UPDATE
    path — no lost increments).
"""

from __future__ import annotations

import os
import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pytest
from mintmory.core.config import StorageBackendEnum, StorageSettings
from mintmory.core.embedder import HashingEmbedder
from mintmory.core.storage_factory import build_storage
from mintmory.core.types import MemoryCategory, MemoryRecord, MemorySource, SearchRequest

# ---------------------------------------------------------------------------
# Parametric constants
# ---------------------------------------------------------------------------
N_WRITERS = 4
WRITES_PER_WRITER = 10  # 40 total memories
N_READERS = 4
READS_PER_READER = 3
TOTAL_EXPECTED_MEMORIES = N_WRITERS * WRITES_PER_WRITER

# ---------------------------------------------------------------------------
# Availability guard
# ---------------------------------------------------------------------------

_DSN = os.environ.get("MINTMORY_TEST_PG_DSN", "")
_PG_AVAILABLE = bool(_DSN)
_SKIP_REASON = "MINTMORY_TEST_PG_DSN not set — skipping soak test"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_backend() -> Generator[Any, None, None]:
    """Module-scoped PostgresBackend for the soak test (shared pool across tasks)."""
    if not _PG_AVAILABLE:
        pytest.skip(_SKIP_REASON)
    emb = HashingEmbedder(dim=64)
    backend = build_storage(
        StorageSettings(backend=StorageBackendEnum.POSTGRES, dsn=_DSN),
        embedder=emb,
    )
    backend.initialise()
    # Clean slate — soak test owns its own data
    from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415

    assert isinstance(backend, PostgresBackend)
    backend._truncate_all()
    yield backend
    backend.close()


# ---------------------------------------------------------------------------
# Soak test
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _PG_AVAILABLE, reason=_SKIP_REASON)
def test_pg_soak_concurrent(pg_backend: Any) -> None:
    """
    Concurrent write + read + feedback under the PostgresBackend.

    Success criteria:
    - All futures complete without exceptions
    - get_stats().total_memories == TOTAL_EXPECTED_MEMORIES
    - At least one search returns at least one result (non-empty corpus)
    """
    errors: list[Exception] = []
    lock = threading.Lock()

    def _record_error(exc: Exception) -> None:
        with lock:
            errors.append(exc)

    # ---- Writer tasks ----
    def _writer(writer_id: int) -> None:
        try:
            for i in range(WRITES_PER_WRITER):
                pg_backend.add_memory(
                    MemoryRecord(
                        content=f"soak writer={writer_id} seq={i} "
                        f"fact about distributed systems and concurrency",
                        category=MemoryCategory.FACT,
                        source=MemorySource.AGENT,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            _record_error(exc)

    # ---- Reader tasks ----
    def _reader(reader_id: int) -> None:
        try:
            for _ in range(READS_PER_READER):
                pg_backend.search(
                    SearchRequest(
                        query=f"distributed concurrency writer {reader_id}",
                        limit=5,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            _record_error(exc)

    # ---- Feedback task (applied after some data exists) ----
    def _feedback(backend: Any, memory_ids: list[str]) -> None:
        try:
            for mid in memory_ids[:5]:
                backend.apply_feedback(mid, useful=True, stale=False)
                backend.apply_feedback(mid, useful=False, stale=True)
        except Exception as exc:  # noqa: BLE001
            _record_error(exc)

    # Phase 1: concurrent writes
    with ThreadPoolExecutor(max_workers=N_WRITERS) as pool:
        futs = [pool.submit(_writer, i) for i in range(N_WRITERS)]
        for fut in as_completed(futs):
            fut.result()  # propagate any ThreadPoolExecutor wrapping exception

    # Report writer errors before asserting counts so the root cause is visible.
    assert not errors, f"Concurrent writer errors: {errors}"

    # Verify write count
    stats = pg_backend.get_stats()
    assert stats.total_memories == TOTAL_EXPECTED_MEMORIES, (
        f"Expected {TOTAL_EXPECTED_MEMORIES} memories, got {stats.total_memories}"
    )

    # Phase 2: concurrent reads + feedback
    all_ids = pg_backend.list_active_memory_ids()
    tasks: list[tuple[str, Any]] = [("reader", i) for i in range(N_READERS)]
    tasks.append(("feedback", all_ids))

    with ThreadPoolExecutor(max_workers=N_READERS + 1) as pool:
        futs2 = []
        for task in tasks:
            if task[0] == "reader":
                futs2.append(pool.submit(_reader, task[1]))
            else:
                futs2.append(pool.submit(_feedback, pg_backend, task[1]))
        for fut in as_completed(futs2):
            fut.result()

    # Report phase-2 errors before final assertions.
    assert not errors, f"Concurrent soak errors (phase 2): {errors}"

    # At least one search result expected (corpus is non-empty)
    resp = pg_backend.search(SearchRequest(query="distributed concurrency fact", limit=10))
    assert len(resp.memories) > 0, "Search returned 0 results after soak writes"

    # Stats still consistent
    final_stats = pg_backend.get_stats()
    assert final_stats.total_memories == TOTAL_EXPECTED_MEMORIES
    assert final_stats.active > 0


@pytest.mark.skipif(not _PG_AVAILABLE, reason=_SKIP_REASON)
def test_pg_apply_feedback_lost_update_invariant(pg_backend: Any) -> None:
    """
    Atomic lost-update guard for apply_feedback.

    N_CONCURRENT threads each fire one ``apply_feedback(useful=True, stale=False)``
    on the SAME memory simultaneously.  Because the backend uses a single atomic
    ``UPDATE … SET reinforcement_count = reinforcement_count + 1`` (no
    read-modify-write), every increment must land: after all threads complete
    ``reinforcement_count`` MUST equal N_CONCURRENT.

    We also interleave ``update_memory`` on the same row (which EXCLUDES counter
    columns from its write-set by design §6.3) to exercise the race between the two
    update paths and confirm neither clobbers the counter.
    """
    n_concurrent = 20
    errors: list[Exception] = []
    lock = threading.Lock()

    def _record_error(exc: Exception) -> None:
        with lock:
            errors.append(exc)

    # Create a fresh memory for this test (soak fixture owns the db but is module-scoped;
    # we add one extra row and track it via the returned id).
    target = pg_backend.add_memory(
        MemoryRecord(
            content="lost-update invariant test memory unique phrase",
            category=MemoryCategory.FACT,
            source=MemorySource.AGENT,
        )
    )
    mid = target.id

    def _vote() -> None:
        try:
            pg_backend.apply_feedback(mid, useful=True, stale=False)
        except Exception as exc:  # noqa: BLE001
            _record_error(exc)

    def _touch_content() -> None:
        """update_memory on the same row — must NOT reset reinforcement_count."""
        try:
            pg_backend.update_memory(mid, confidence=0.9)
        except Exception as exc:  # noqa: BLE001
            _record_error(exc)

    # Submit n_concurrent votes plus a few content-touch updates concurrently.
    tasks_: list[Any] = [_vote] * n_concurrent + [_touch_content] * 4
    with ThreadPoolExecutor(max_workers=n_concurrent + 4) as pool:
        futs3 = [pool.submit(fn) for fn in tasks_]
        for fut in as_completed(futs3):
            fut.result()

    assert not errors, f"Lost-update invariant errors: {errors}"

    result = pg_backend.get_memory(mid)
    assert result is not None
    assert result.reinforcement_count == n_concurrent, (
        f"Lost-update detected: expected reinforcement_count={n_concurrent}, "
        f"got {result.reinforcement_count}"
    )
