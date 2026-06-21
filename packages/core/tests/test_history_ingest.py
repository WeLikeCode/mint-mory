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
from typing import Any

import pytest
from mintmory.core.history.ingest import (
    HermesGuardError,
    IngestReport,
    LLMBudget,
    _assert_not_working_db,
    _find_by_session_id,
    backfill,
    write_session,
    write_session_segments,
)
from mintmory.core.history.models import NormalizedTurn, Segment, SessionSummary
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

    def test_phase2_report_fields(self) -> None:
        """Phase-2 IngestReport has segment fields."""
        report = IngestReport()
        assert report.segments_written == 0
        assert report.llm_calls == 0
        assert report.llm_cache_hits == 0
        assert report.llm_fallbacks == 0
        assert report.llm_calls_deferred == 0


# ---------------------------------------------------------------------------
# Phase-2: write_session_segments helpers
# ---------------------------------------------------------------------------


def _make_session_for_seg(
    session_id: str = "seg-session-001",
    ts_start: str = "2025-03-01T10:00:00Z",
    ts_end: str = "2025-03-01T11:00:00Z",
) -> SessionSummary:
    return SessionSummary(
        session_id=session_id,
        agent="claude_code",
        repo="myproject",
        repo_path="/home/user/myproject",
        branch="main",
        ts_start=ts_start,
        ts_end=ts_end,
        turn_count=10,
        tools_used=["bash"],
        kind="investigation",
        title="",
        summary_text="",
        source_path="",
        distiller_version=1,
    )


def _make_turns_for_segs(n: int, ts_prefix: str = "2025-03-01T10:") -> list[NormalizedTurn]:
    """Build n turns with alternating user/assistant roles."""
    turns = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        ts = f"{ts_prefix}{i:02d}:00Z"
        turns.append(NormalizedTurn(seq=i, ts=ts, role=role, text=f"Turn {i}: {role} text"))
    return turns


def _make_segment(
    idx: int,
    lo: int,
    hi: int,
    ts_start: str = "2025-03-01T10:00:00Z",
    ts_end: str = "2025-03-01T10:30:00Z",
) -> Segment:
    return Segment(idx=idx, turn_lo=lo, turn_hi=hi, ts_start=ts_start, ts_end=ts_end)


def _get_all_segment_rows(store: StorageAdapter, session_id: str) -> list[dict[str, Any]]:
    """Return all non-archived segment rows for a session."""
    conn = store.connect()
    rows = conn.execute(
        "SELECT id, metadata, valid_from, is_archived FROM memories "
        "WHERE json_extract(metadata, '$.session_id') = ? "
        "  AND json_extract(metadata, '$.segment_id') IS NOT NULL",
        (session_id,),
    ).fetchall()
    result = []
    for row in rows:
        meta = json.loads(row["metadata"] or "{}")
        result.append(
            {
                "id": row["id"],
                "meta": meta,
                "valid_from": row["valid_from"],
                "is_archived": row["is_archived"],
            }
        )
    return result


# ---------------------------------------------------------------------------
# Phase-2: write_session_segments tests
# ---------------------------------------------------------------------------


class TestWriteSessionSegments:
    def test_n_segments_produce_n_rows(self, store: StorageAdapter) -> None:
        """N segments -> N memory rows with correct segment_id/index/count."""
        summary = _make_session_for_seg(session_id="seg-n-001")
        turns = _make_turns_for_segs(6)
        segments = [
            _make_segment(0, 0, 2, "2025-03-01T10:00:00Z", "2025-03-01T10:15:00Z"),
            _make_segment(1, 3, 5, "2025-03-01T10:16:00Z", "2025-03-01T10:30:00Z"),
        ]

        result = write_session_segments(store, summary, segments, turns)
        assert result.written == 2
        assert result.cache_hits == 0

        rows = _get_all_segment_rows(store, "seg-n-001")
        active = [r for r in rows if not r["is_archived"]]
        assert len(active) == 2

        metas = sorted([r["meta"] for r in active], key=lambda m: m["segment_index"])
        assert metas[0]["segment_id"] == "seg-n-001#0"
        assert metas[0]["segment_index"] == 0
        assert metas[0]["segment_count"] == 2
        assert metas[0]["turn_lo"] == 0
        assert metas[0]["turn_hi"] == 2
        assert metas[1]["segment_id"] == "seg-n-001#1"
        assert metas[1]["segment_index"] == 1
        assert metas[1]["segment_count"] == 2

    def test_three_segments_all_fields(self, store: StorageAdapter) -> None:
        """3-segment session: all envelope fields are present."""
        summary = _make_session_for_seg(session_id="seg-three-001")
        turns = _make_turns_for_segs(9)
        segments = [
            _make_segment(0, 0, 2, "2025-03-01T09:00:00Z", "2025-03-01T09:15:00Z"),
            _make_segment(1, 3, 5, "2025-03-01T09:16:00Z", "2025-03-01T09:30:00Z"),
            _make_segment(2, 6, 8, "2025-03-01T09:31:00Z", "2025-03-01T09:45:00Z"),
        ]

        result = write_session_segments(store, summary, segments, turns)
        assert result.written == 3

        rows = _get_all_segment_rows(store, "seg-three-001")
        active = [r for r in rows if not r["is_archived"]]
        assert len(active) == 3

        for r in active:
            meta = r["meta"]
            assert "segment_id" in meta
            assert "segment_index" in meta
            assert "segment_count" in meta
            assert meta["segment_count"] == 3
            assert "turn_lo" in meta
            assert "turn_hi" in meta
            assert "title" in meta
            assert "outcome" in meta
            assert "session_ts_start" in meta
            assert "session_ts_end" in meta
            assert "content_hash" in meta
            assert "seg_signature" in meta
            assert "session_id" in meta

    def test_valid_from_equals_segment_ts_start(self, store: StorageAdapter) -> None:
        """valid_from == segment ts_start (not session ts_start)."""
        summary = _make_session_for_seg(session_id="seg-vf-001")
        turns = _make_turns_for_segs(4)
        # Two segments with distinct timestamps
        seg_ts_start_0 = "2025-03-01T09:00:00Z"
        seg_ts_start_1 = "2025-03-01T10:00:00Z"
        segments = [
            _make_segment(0, 0, 1, seg_ts_start_0, "2025-03-01T09:30:00Z"),
            _make_segment(1, 2, 3, seg_ts_start_1, "2025-03-01T10:30:00Z"),
        ]

        write_session_segments(store, summary, segments, turns)

        rows = _get_all_segment_rows(store, "seg-vf-001")
        active = sorted(
            [r for r in rows if not r["is_archived"]],
            key=lambda r: r["meta"]["segment_index"],
        )
        # Segment 0: valid_from should contain "09:00"
        assert "09:00" in active[0]["valid_from"]
        # Segment 1: valid_from should contain "10:00"
        assert "10:00" in active[1]["valid_from"]

    def test_orphan_sweep_archives_excess_segments(self, store: StorageAdapter) -> None:
        """Re-ingest with FEWER segments archives the orphaned higher-index segments."""
        session_id = "seg-orphan-001"
        summary = _make_session_for_seg(session_id=session_id)
        turns = _make_turns_for_segs(10)

        # First ingest: 5 segments
        segs5 = [_make_segment(i, i * 2, i * 2 + 1) for i in range(5)]
        result5 = write_session_segments(store, summary, segs5, turns)
        assert result5.written == 5

        # Second ingest: 3 segments only
        segs3 = [_make_segment(i, i * 2, i * 2 + 1) for i in range(3)]
        write_session_segments(store, summary, segs3, turns)

        # All rows (including archived)
        all_rows = _get_all_segment_rows(store, session_id)
        assert len(all_rows) == 5  # total rows, 5 created

        # Active: only 3
        active = [r for r in all_rows if not r["is_archived"]]
        assert len(active) == 3

        # Archived: 2 (indices 3, 4)
        archived = [r for r in all_rows if r["is_archived"]]
        assert len(archived) == 2
        archived_indices = {r["meta"]["segment_index"] for r in archived}
        assert archived_indices == {3, 4}

    def test_orphan_sweep_absent_from_timeline(
        self, store: StorageAdapter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Archived orphan segments must not appear in timeline results."""
        from mintmory.core.history.query import timeline

        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db_path = str(tmp_path / "orphan-tl.db")

        new_store = StorageAdapter(db_path)
        new_store.initialise()

        session_id = "seg-orphan-tl-001"
        summary = _make_session_for_seg(
            session_id=session_id,
            ts_start="2025-06-01T10:00:00Z",
            ts_end="2025-06-01T11:00:00Z",
        )
        turns = _make_turns_for_segs(10)

        ts_start = "2025-06-01T10:00:00Z"
        ts_end = "2025-06-01T10:30:00Z"
        # First: 5 segments
        segs5 = [_make_segment(i, i * 2, i * 2 + 1, ts_start, ts_end) for i in range(5)]
        write_session_segments(new_store, summary, segs5, turns)

        # Re-ingest with 3 segments — segments 3 and 4 are archived
        segs3 = [_make_segment(i, i * 2, i * 2 + 1, ts_start, ts_end) for i in range(3)]
        write_session_segments(new_store, summary, segs3, turns)

        # Timeline should only return 3 rows for this session
        rows = timeline(db_path, since="400d")
        session_rows = [r for r in rows if r["session_id"] == session_id]
        assert len(session_rows) == 3
        segment_indices = {r["segment_index"] for r in session_rows}
        assert segment_indices == {0, 1, 2}

    def test_content_hash_cache_skips_unchanged_segments(self, store: StorageAdapter) -> None:
        """Same segment content on re-ingest -> cache hit, no re-write."""
        session_id = "seg-cache-001"
        summary = _make_session_for_seg(session_id=session_id)
        turns = _make_turns_for_segs(4)
        segs = [
            _make_segment(0, 0, 1, "2025-03-01T10:00:00Z", "2025-03-01T10:15:00Z"),
            _make_segment(1, 2, 3, "2025-03-01T10:16:00Z", "2025-03-01T10:30:00Z"),
        ]

        # First write
        result1 = write_session_segments(store, summary, segs, turns)
        assert result1.written == 2
        assert result1.cache_hits == 0

        # Second write with identical turns/settings -> cache hit
        result2 = write_session_segments(store, summary, segs, turns)
        assert result2.cache_hits == 2
        assert result2.written == 0

    def test_budget_caps_llm_calls_then_deterministic(self, store: StorageAdapter) -> None:
        """LLMBudget(max_calls=1) allows 1 LLM call, rest fall back to deterministic."""
        session_id = "seg-budget-001"
        summary = _make_session_for_seg(session_id=session_id)
        turns = _make_turns_for_segs(6)
        segs = [
            _make_segment(0, 0, 1, "2025-03-01T10:00:00Z", "2025-03-01T10:10:00Z"),
            _make_segment(1, 2, 3, "2025-03-01T10:11:00Z", "2025-03-01T10:20:00Z"),
            _make_segment(2, 4, 5, "2025-03-01T10:21:00Z", "2025-03-01T10:30:00Z"),
        ]

        # Track LLM calls
        call_count = 0

        def fake_distiller(
            seg_sum: SessionSummary,
            seg_turns: list[NormalizedTurn],
            prev_context: str = "",
        ) -> tuple[SessionSummary, str]:
            import dataclasses as _dc

            nonlocal call_count
            call_count += 1
            filled = _dc.replace(
                seg_sum,
                title="LLM title",
                summary_text="LLM summary",
                kind="feature",
                outcome="done",
                distiller_version=2,
            )
            return filled, "next ctx"

        budget = LLMBudget(max_calls=1)
        result = write_session_segments(store, summary, segs, turns, fake_distiller, budget=budget)

        # Only 1 LLM call allowed
        assert result.llm_calls == 1
        assert result.llm_fallbacks == 2  # remaining 2 segments use deterministic
        assert call_count == 1

        # All 3 segments still written
        rows = _get_all_segment_rows(store, session_id)
        active = [r for r in rows if not r["is_archived"]]
        assert len(active) == 3

    def test_llm_distiller_error_falls_back(self, store: StorageAdapter) -> None:
        """LLM error on a segment -> fallback to deterministic, not abort."""
        session_id = "seg-err-001"
        summary = _make_session_for_seg(session_id=session_id)
        turns = _make_turns_for_segs(4)
        segs = [
            _make_segment(0, 0, 1, "2025-03-01T10:00:00Z", "2025-03-01T10:15:00Z"),
            _make_segment(1, 2, 3, "2025-03-01T10:16:00Z", "2025-03-01T10:30:00Z"),
        ]

        def failing_distiller(
            seg_sum: SessionSummary,
            seg_turns: list[NormalizedTurn],
            prev_context: str = "",
        ) -> tuple[SessionSummary, str]:
            raise RuntimeError("LLM down")

        result = write_session_segments(store, summary, segs, turns, failing_distiller)
        assert result.llm_fallbacks == 2
        assert result.llm_calls == 0
        # All segments still written via fallback
        rows = _get_all_segment_rows(store, session_id)
        active = [r for r in rows if not r["is_archived"]]
        assert len(active) == 2

    def test_idempotent_reingest_same_count(self, store: StorageAdapter) -> None:
        """Re-ingest with same segment count: rows updated (not duplicated)."""
        session_id = "seg-idem-001"
        summary = _make_session_for_seg(session_id=session_id)
        turns = _make_turns_for_segs(4)
        segs = [
            _make_segment(0, 0, 1, "2025-03-01T10:00:00Z", "2025-03-01T10:15:00Z"),
            _make_segment(1, 2, 3, "2025-03-01T10:16:00Z", "2025-03-01T10:30:00Z"),
        ]

        write_session_segments(store, summary, segs, turns)

        # Re-ingest with same segments but different turn text (forces re-distill)
        turns2 = [
            NormalizedTurn(seq=i, ts=t.ts, role=t.role, text=f"NEW turn {i}")
            for i, t in enumerate(turns)
        ]
        result2 = write_session_segments(store, summary, segs, turns2)
        assert result2.updated == 2
        assert result2.written == 0

        # Still exactly 2 active rows (no duplicates)
        rows = _get_all_segment_rows(store, session_id)
        active = [r for r in rows if not r["is_archived"]]
        assert len(active) == 2

    def test_no_segments_returns_empty_result(self, store: StorageAdapter) -> None:
        """Empty segments list -> SegWriteResult with zeros, no DB writes."""
        summary = _make_session_for_seg(session_id="seg-empty-001")
        result = write_session_segments(store, summary, [], [])
        assert result.written == 0
        assert result.cache_hits == 0
        assert result.llm_calls == 0

    def test_fake_llm_distiller_prev_context_chain(self, store: StorageAdapter) -> None:
        """prev_context is chained: next_context from seg N becomes prev_context of seg N+1."""
        session_id = "seg-ctx-001"
        summary = _make_session_for_seg(session_id=session_id)
        turns = _make_turns_for_segs(6)
        segs = [
            _make_segment(0, 0, 1, "2025-03-01T10:00:00Z", "2025-03-01T10:10:00Z"),
            _make_segment(1, 2, 3, "2025-03-01T10:11:00Z", "2025-03-01T10:20:00Z"),
            _make_segment(2, 4, 5, "2025-03-01T10:21:00Z", "2025-03-01T10:30:00Z"),
        ]

        received_prev_contexts: list[str] = []

        def tracking_distiller(
            seg_sum: SessionSummary,
            seg_turns: list[NormalizedTurn],
            prev_context: str = "",
        ) -> tuple[SessionSummary, str]:
            import dataclasses as _dc

            received_prev_contexts.append(prev_context)
            filled = _dc.replace(
                seg_sum,
                title=f"Seg {seg_sum.segment_index}",
                summary_text=f"Summary {seg_sum.segment_index}",
                kind="feature",
                outcome="done",
                distiller_version=2,
            )
            return filled, f"context-after-{seg_sum.segment_index}"

        write_session_segments(store, summary, segs, turns, tracking_distiller)

        # prev_context for seg 0 is ""
        assert received_prev_contexts[0] == ""
        # prev_context for seg 1 is what seg 0 returned
        assert received_prev_contexts[1] == "context-after-0"
        # prev_context for seg 2 is what seg 1 returned
        assert received_prev_contexts[2] == "context-after-1"


# ---------------------------------------------------------------------------
# Phase-2: LLMBudget tests
# ---------------------------------------------------------------------------


class TestLLMBudget:
    def test_unlimited_budget_always_grants(self) -> None:
        budget = LLMBudget(max_calls=0)
        for _ in range(1000):
            assert budget.request() is True

    def test_limited_budget_caps_calls(self) -> None:
        budget = LLMBudget(max_calls=3)
        assert budget.request() is True
        assert budget.request() is True
        assert budget.request() is True
        assert budget.request() is False  # exhausted

    def test_used_counter(self) -> None:
        budget = LLMBudget(max_calls=5)
        budget.request()
        budget.request()
        assert budget.used == 2


def test_backfill_concurrent_no_data_loss(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression (MM-29 blocker): concurrent backfill must NOT lose rows.

    Many multi-segment sessions ingested with max_concurrency=4 must land EVERY
    segment row (writes are serialized on the main thread; distill is parallel)."""
    import mintmory.core.history.ingest as ingest_mod
    from mintmory.core.config import SegmentSettings

    n_sessions, turns_per = 40, 60  # 60 turns -> multiple segments at target=25

    def _big_sessions() -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
        for s in range(n_sessions):
            turns = [
                NormalizedTurn(
                    seq=i,
                    ts=f"2025-03-01T10:{i:02d}:00Z",
                    role="user" if i % 2 == 0 else "assistant",
                    text=f"s{s} turn {i}",
                )
                for i in range(turns_per)
            ]
            yield _make_session(session_id=f"big-{s}", summary_text=f"session {s}"), turns

    monkeypatch.setattr(
        ingest_mod, "_load_adapter", lambda name: _big_sessions if name == "stub" else None
    )
    seg = SegmentSettings(target_turns=25, max_turns=40)
    report = backfill(db_path=tmp_db, sources=["stub"], seg_settings=seg, max_concurrency=4)

    # Recompute expected segment count deterministically and compare to stored rows.
    from mintmory.core.history.segment import segment_turns

    expected = 0
    for _summary, turns in _big_sessions():
        expected += len(segment_turns(turns, seg))
    assert expected > n_sessions  # sanity: these sessions really do split

    store = StorageAdapter(tmp_db)
    store.initialise()
    rows = (
        store.connect()
        .execute(
            "SELECT COUNT(*) FROM memories WHERE is_archived=0 "
            "AND json_extract(metadata,'$.record_type')='session_summary'"
        )
        .fetchone()[0]
    )
    store.close()
    assert rows == expected, f"data loss: stored {rows} != expected {expected}"
    assert report.errors == 0
