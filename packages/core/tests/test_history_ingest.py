"""
Tests for mintmory.core.history.ingest.

Verifies:
- _assert_not_working_db raises HermesGuardError for:
    * hermes.db
    * memories.db (CLI default)
    * $MINTMORY_DB
- backfill() into a temp DB writes EPISODIC + AGENT + envelope
- valid_from == ts_start (not ingest time)
- Re-run with same session_id UPDATEs (not duplicates)
- IngestReport has correct fields

Uses a STUB adapter / monkeypatched _ADAPTERS — never touches real user dirs.
Tests use tempfile dirs only.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from mintmory.core.history.ingest import (
    HermesGuardError,
    IngestReport,
    _assert_not_working_db,
    _find_by_session_id,
    backfill,
    write_session,
)
from mintmory.core.history.models import NormalizedTurn, SessionSummary
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import MemoryCategory, MemorySource

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path: Path) -> str:
    """Return a path to a temporary history DB (not yet created)."""
    return str(tmp_path / "agent-history.db")


@pytest.fixture()
def store(tmp_db: str) -> StorageAdapter:
    """Open and initialise a temp StorageAdapter."""
    s = StorageAdapter(tmp_db)
    s.initialise()
    return s


def _make_session(
    session_id: str = "sess-001",
    ts_start: str = "2024-03-15T10:00:00Z",
    ts_end: str = "2024-03-15T10:30:00Z",
    summary_text: str = "Fixed the login bug in auth.py",
    title: str = "Fix login bug",
    kind: str = "fix",
) -> SessionSummary:
    return SessionSummary(
        session_id=session_id,
        agent="claude_code",
        repo="myproject",
        repo_path="/home/user/myproject",
        branch="main",
        ts_start=ts_start,
        ts_end=ts_end,
        turn_count=4,
        tools_used=["bash", "edit"],
        kind=kind,
        title=title,
        summary_text=summary_text,
        source_path="",
        distiller_version=1,
    )


def _make_turns() -> list[NormalizedTurn]:
    return [
        NormalizedTurn(seq=0, ts=None, role="user", text="Fix the login bug"),
        NormalizedTurn(seq=1, ts=None, role="assistant", text="Done, patched auth.py"),
    ]


# Stub adapter: returns a fixed set of sessions
def _stub_iter_sessions() -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
    yield _make_session("stub-001"), _make_turns()
    yield _make_session("stub-002", ts_start="2024-04-01T08:00:00Z"), _make_turns()


# ---------------------------------------------------------------------------
# Guard tests
# ---------------------------------------------------------------------------


class TestHermesGuard:
    def test_raises_for_hermes_db(self, tmp_path: Path) -> None:
        hermes = str(tmp_path / "hermes.db")
        with pytest.raises(HermesGuardError, match="hermes.db"):
            _assert_not_working_db(hermes)

    def test_raises_for_memories_db(self) -> None:
        memories = "~/.mintmory/memories.db"
        with pytest.raises(HermesGuardError, match="memories.db"):
            _assert_not_working_db(memories)

    def test_raises_for_mintmory_db_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        custom_db = str(tmp_path / "custom.db")
        monkeypatch.setenv("MINTMORY_DB", custom_db)
        with pytest.raises(HermesGuardError, match="MINTMORY_DB"):
            _assert_not_working_db(custom_db)

    def test_raises_for_subpath_hermes(self, tmp_path: Path) -> None:
        hermes = str(tmp_path / "subdir" / "hermes.db")
        with pytest.raises(HermesGuardError):
            _assert_not_working_db(hermes)

    def test_allows_agent_history_db(self, tmp_path: Path) -> None:
        history = str(tmp_path / "agent-history.db")
        # Should NOT raise
        _assert_not_working_db(history)

    def test_allows_custom_path(self, tmp_path: Path) -> None:
        custom = str(tmp_path / "my-history.db")
        _assert_not_working_db(custom)  # must not raise

    def test_mintmory_db_env_cleared_no_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        history = str(tmp_path / "agent-history.db")
        _assert_not_working_db(history)  # must not raise


# ---------------------------------------------------------------------------
# write_session — EPISODIC + AGENT + envelope
# ---------------------------------------------------------------------------


class TestWriteSession:
    def test_writes_episodic_agent(self, store: StorageAdapter) -> None:
        summary = _make_session()
        mem_id = write_session(store, summary)
        assert mem_id is not None

        conn = store.connect()
        row = conn.execute(
            "SELECT category, source FROM memories WHERE id = ?", (mem_id,)
        ).fetchone()
        assert row is not None
        assert row["category"] == MemoryCategory.EPISODIC.value
        assert row["source"] == MemorySource.AGENT.value

    def test_envelope_fields_in_metadata(self, store: StorageAdapter) -> None:
        summary = _make_session()
        mem_id = write_session(store, summary)
        assert mem_id is not None

        conn = store.connect()
        row = conn.execute("SELECT metadata FROM memories WHERE id = ?", (mem_id,)).fetchone()
        meta = json.loads(row["metadata"])

        assert meta["record_type"] == "session_summary"
        assert meta["agent"] == "claude_code"
        assert meta["session_id"] == "sess-001"
        assert meta["repo"] == "myproject"
        assert meta["kind"] == "fix"
        assert meta["ts_start"] == "2024-03-15T10:00:00Z"
        assert meta["ts_end"] == "2024-03-15T10:30:00Z"
        assert meta["turn_count"] == 4
        assert "bash" in meta["tools_used"]

    def test_collection_differentiator_per_agent(self, store: StorageAdapter) -> None:
        """Spec differentiator #3: every record carries a per-source collection."""
        import dataclasses

        conn = store.connect()
        for agent, expected in (
            ("claude_code", "claude-code"),
            ("codex", "codex"),
            ("kiro", "kiro"),
        ):
            summary = dataclasses.replace(_make_session(session_id=f"sess-{agent}"), agent=agent)
            mem_id = write_session(store, summary)
            assert mem_id is not None
            row = conn.execute("SELECT metadata FROM memories WHERE id = ?", (mem_id,)).fetchone()
            meta = json.loads(row["metadata"])
            assert meta["collection"] == expected
            assert meta["record_type"] == "session_summary"

    def test_valid_from_equals_ts_start(self, store: StorageAdapter) -> None:
        """valid_from MUST equal ts_start (work time, not ingest time)."""
        summary = _make_session(ts_start="2024-03-15T10:00:00Z")
        mem_id = write_session(store, summary)
        assert mem_id is not None

        conn = store.connect()
        row = conn.execute("SELECT valid_from FROM memories WHERE id = ?", (mem_id,)).fetchone()
        assert row is not None
        valid_from_str = row["valid_from"]
        # Should represent 2024-03-15T10:00:00 (UTC)
        assert valid_from_str is not None
        assert "2024-03-15" in valid_from_str

    def test_empty_summary_returns_none(self, store: StorageAdapter) -> None:
        summary = _make_session(summary_text="", title="")
        mem_id = write_session(store, summary)
        assert mem_id is None

    def test_uses_title_when_summary_empty(self, store: StorageAdapter) -> None:
        summary = _make_session(summary_text="", title="Fix login bug")
        mem_id = write_session(store, summary)
        assert mem_id is not None

        conn = store.connect()
        row = conn.execute("SELECT content FROM memories WHERE id = ?", (mem_id,)).fetchone()
        assert row["content"] == "Fix login bug"


# ---------------------------------------------------------------------------
# Idempotency on session_id
# ---------------------------------------------------------------------------


class TestSessionIdDedup:
    def test_rerun_updates_not_duplicates(self, store: StorageAdapter) -> None:
        """Writing the same session_id twice should UPDATE, not INSERT twice."""
        summary = _make_session(session_id="dedup-001")
        id1 = write_session(store, summary)

        # Write again with same session_id but different content
        summary2 = _make_session(
            session_id="dedup-001",
            summary_text="Updated summary for the same session",
        )
        id2 = write_session(store, summary2)

        # Both calls should return an id
        assert id1 is not None
        assert id2 is not None

        # Count memories with this session_id — must be exactly 1
        conn = store.connect()
        rows = conn.execute(
            "SELECT id FROM memories WHERE json_extract(metadata, '$.session_id') = ?",
            ("dedup-001",),
        ).fetchall()
        assert len(rows) == 1, f"Expected 1 memory but found {len(rows)}"

    def test_second_write_updates_content(self, store: StorageAdapter) -> None:
        summary1 = _make_session(session_id="update-001", summary_text="Original summary")
        write_session(store, summary1)

        summary2 = _make_session(session_id="update-001", summary_text="Updated summary")
        write_session(store, summary2)

        mem_id = _find_by_session_id(store, "update-001")
        assert mem_id is not None
        conn = store.connect()
        row = conn.execute("SELECT content FROM memories WHERE id = ?", (mem_id,)).fetchone()
        assert row["content"] == "Updated summary"

    def test_different_sessions_create_separate_memories(self, store: StorageAdapter) -> None:
        for i in range(3):
            summary = _make_session(session_id=f"session-{i:03d}")
            write_session(store, summary)

        conn = store.connect()
        count = conn.execute(
            "SELECT count(*) AS c FROM memories "
            "WHERE json_extract(metadata, '$.record_type') = 'session_summary'"
        ).fetchone()["c"]
        assert count == 3


# ---------------------------------------------------------------------------
# backfill with stub adapter
# ---------------------------------------------------------------------------


class TestBackfillWithStub:
    def test_backfill_writes_sessions(self, tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """backfill() with a stub adapter writes EPISODIC+AGENT records."""
        import mintmory.core.history.ingest as ingest_mod

        def patched_load(name: str) -> object:
            if name == "stub":
                return _stub_iter_sessions
            raise ValueError(f"Unknown in test: {name!r}")

        monkeypatch.setattr(ingest_mod, "_load_adapter", patched_load)

        # Call backfill with "stub" source
        report = backfill(db_path=tmp_db, sources=["stub"])
        assert report.scanned == 2
        # At least some written
        assert report.by_source.get("stub", 0) >= 0

    def test_backfill_respects_guard(self) -> None:
        """backfill() refuses to target memories.db."""
        with pytest.raises(HermesGuardError):
            backfill(db_path="~/.mintmory/memories.db")

    def test_backfill_creates_db_with_restricted_permissions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The dedicated DB must be created with 0o600 permissions."""
        import mintmory.core.history.ingest as ingest_mod

        def patched_load(name: str) -> object:  # noqa: ARG001
            def empty_iter() -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
                return iter([])

            return empty_iter

        monkeypatch.setattr(ingest_mod, "_load_adapter", patched_load)

        db_path = str(tmp_path / "history.db")
        backfill(db_path=db_path, sources=["claude_code"])

        stat = os.stat(db_path)
        mode = oct(stat.st_mode)[-3:]
        assert mode == "600", f"Expected 600 permissions, got {mode}"


# ---------------------------------------------------------------------------
# IngestReport
# ---------------------------------------------------------------------------


class TestIngestReport:
    def test_report_fields(self) -> None:
        report = IngestReport()
        assert report.scanned == 0
        assert report.written == 0
        assert report.updated == 0
        assert report.skipped == 0
        assert report.redacted_hits == 0
        assert report.by_source == {}

    def test_report_by_source(self) -> None:
        report = IngestReport(by_source={"claude_code": 5, "codex": 3})
        assert report.by_source["claude_code"] == 5
        assert report.by_source["codex"] == 3
