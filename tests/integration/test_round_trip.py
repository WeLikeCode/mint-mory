"""
M1 integration gate: round-trip through StorageAdapter.

These tests do NOT mock — they use a real SQLite file in a tmp_path.
All tests in this file form the M1 "green gate": schema initialises,
a memory can be added and retrieved, and the M2 baseline for full CRUD.

Run: pytest tests/integration/test_round_trip.py -v
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import MemoryCategory


@pytest.fixture
def store(tmp_path: Path) -> StorageAdapter:
    s = StorageAdapter(str(tmp_path / "test.db"))
    s.initialise()
    return s


@pytest.fixture
def minimal_record() -> dict:
    return {
        "content": "The user prefers dark mode.",
        "category": "preference",
        "source": "user",
        "confidence": 1.0,
        "verified": True,
    }


# ---------------------------------------------------------------------------
# M1: Schema and initialise
# ---------------------------------------------------------------------------


class TestM1Schema:
    def test_initialise_is_idempotent(self, tmp_path: Path) -> None:
        """Running initialise twice must not raise."""
        s = StorageAdapter(str(tmp_path / "test.db"))
        s.initialise()
        s.initialise()

    def test_foreign_keys_on(self, store: StorageAdapter) -> None:
        # PRAGMA foreign_keys is per-connection and is NOT persisted in the DB
        # file (AGENTS.md §4.5). A fresh raw connection would report 0; the
        # invariant is that the adapter sets it ON on every connection it opens.
        result = store.connect().execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1, "PRAGMA foreign_keys must be ON for adapter connections"

    def test_wal_mode(self, store: StorageAdapter) -> None:
        conn = sqlite3.connect(store.db_path)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        conn.close()
        assert result[0] == "wal"

    def test_all_tables_present(self, store: StorageAdapter) -> None:
        conn = sqlite3.connect(store.db_path)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        required = {
            "memories",
            "concept_links",
            "memory_summaries",
            "query_sessions",
            "query_results",
        }
        assert required.issubset(tables)


# ---------------------------------------------------------------------------
# M2: CRUD round-trip
# ---------------------------------------------------------------------------


class TestM2CRUD:
    """These tests will fail with NotImplementedError until M2 is implemented."""

    def test_add_and_get_memory(self, store: StorageAdapter, minimal_record: dict) -> None:
        record = store.add_memory(**minimal_record)
        assert record.id is not None
        fetched = store.get_memory(record.id)
        assert fetched is not None
        assert fetched.content == "The user prefers dark mode."
        assert fetched.category == MemoryCategory.PREFERENCE

    def test_get_nonexistent_returns_none(self, store: StorageAdapter) -> None:
        assert store.get_memory("nonexistent-id") is None

    def test_add_sets_defaults(self, store: StorageAdapter, minimal_record: dict) -> None:
        record = store.add_memory(**minimal_record)
        assert record.usefulness_score == 0.0
        assert record.staleness_score == 0.0
        assert record.is_active is True
        assert record.is_archived is False
        assert record.is_stale is False
        assert record.reinforcement_count == 0

    def test_archive_memory(self, store: StorageAdapter, minimal_record: dict) -> None:
        record = store.add_memory(**minimal_record)
        store.archive_memory(record.id)
        fetched = store.get_memory(record.id)
        assert fetched is not None
        assert fetched.is_archived is True
        assert fetched.is_active is False

    def test_usefulness_cap(self, store: StorageAdapter, minimal_record: dict) -> None:
        record = store.add_memory(**minimal_record)
        for _ in range(20):
            store.apply_feedback(record.id, useful=True, stale=False)
        fetched = store.get_memory(record.id)
        assert fetched is not None
        assert fetched.usefulness_score <= 10.0, "usefulness_score must be capped at 10.0"

    def test_staleness_cap(self, store: StorageAdapter, minimal_record: dict) -> None:
        record = store.add_memory(**minimal_record)
        for _ in range(20):
            store.apply_feedback(record.id, useful=False, stale=True)
        fetched = store.get_memory(record.id)
        assert fetched is not None
        assert fetched.staleness_score <= 10.0, "staleness_score must be capped at 10.0"

    def test_get_stats_returns_dict(self, store: StorageAdapter) -> None:
        stats = store.get_stats()
        assert stats is not None


# ---------------------------------------------------------------------------
# M3: QuerySession round-trip
# ---------------------------------------------------------------------------


class TestM3Sessions:
    """M3 gate: session creation and feedback loop."""

    def test_session_feedback_updates_scores(
        self, store: StorageAdapter, minimal_record: dict
    ) -> None:
        pytest.skip("M3: implement session_feedback in storage.py first")
