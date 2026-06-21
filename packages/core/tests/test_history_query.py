"""
Tests for mintmory.core.history.query.

Covers:
- resolve_window: since grammar (d/w/m/y), mutual exclusion with from/to,
  default 90d, from/to parsing.
- timeline: window filter, repo filter, kind filter, newest-first ordering,
  correct row keys.
- search: returns only session_summary records, repo filter, since filter.
- _open_history: Hermes guard raises for hermes.db / memories.db.

Temp DBs are built via history.ingest.write_session with known valid_from dates.
Never touches ~/.mintmory.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from mintmory.core.history.ingest import HermesGuardError, write_session, write_session_segments
from mintmory.core.history.models import NormalizedTurn, Segment, SessionSummary
from mintmory.core.history.query import (
    DEFAULT_WINDOW_DAYS,
    _open_history,
    _shape_row,
    resolve_window,
    search,
    timeline,
)
from mintmory.core.storage import StorageAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    *,
    session_id: str = "sess-001",
    ts_start: str = "2025-01-15T10:00:00Z",
    ts_end: str = "2025-01-15T10:30:00Z",
    summary_text: str = "Fixed auth bug.",
    title: str = "Fix auth",
    kind: str = "fix",
    repo: str = "myproject",
    agent: str = "claude_code",
) -> SessionSummary:
    return SessionSummary(
        session_id=session_id,
        agent=agent,
        repo=repo,
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


def _open_store(db_path: str) -> StorageAdapter:
    s = StorageAdapter(db_path)
    s.initialise()
    return s


def _seed(store: StorageAdapter, **kwargs: object) -> None:
    """Write a session to the store (no distill step — just write_session directly)."""
    write_session(store, _make_session(**kwargs))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# resolve_window
# ---------------------------------------------------------------------------


class TestResolveWindow:
    def _now(self) -> datetime:
        return datetime(2026, 6, 1, 12, 0, 0)  # fixed fake "now"

    def test_default_is_90d(self) -> None:
        now = self._now()
        start, end = resolve_window(since=None, from_iso=None, to_iso=None, now=now)
        assert end == now
        assert start == now - timedelta(days=DEFAULT_WINDOW_DAYS)

    def test_since_days(self) -> None:
        now = self._now()
        start, end = resolve_window(since="30d", from_iso=None, to_iso=None, now=now)
        assert end == now
        assert start == now - timedelta(days=30)

    def test_since_weeks(self) -> None:
        now = self._now()
        start, end = resolve_window(since="4w", from_iso=None, to_iso=None, now=now)
        assert start == now - timedelta(days=28)

    def test_since_months(self) -> None:
        now = self._now()
        start, end = resolve_window(since="3m", from_iso=None, to_iso=None, now=now)
        assert start == now - timedelta(days=90)

    def test_since_years(self) -> None:
        now = self._now()
        start, end = resolve_window(since="2y", from_iso=None, to_iso=None, now=now)
        assert start == now - timedelta(days=730)

    def test_since_and_from_raises(self) -> None:
        now = self._now()
        with pytest.raises(ValueError, match="mutually exclusive"):
            resolve_window(since="30d", from_iso="2026-01-01", to_iso=None, now=now)

    def test_since_and_to_raises(self) -> None:
        now = self._now()
        with pytest.raises(ValueError, match="mutually exclusive"):
            resolve_window(since="7d", from_iso=None, to_iso="2026-06-01", now=now)

    def test_since_and_both_raises(self) -> None:
        now = self._now()
        with pytest.raises(ValueError, match="mutually exclusive"):
            resolve_window(since="7d", from_iso="2026-01-01", to_iso="2026-06-01", now=now)

    def test_from_iso_only(self) -> None:
        now = self._now()
        start, end = resolve_window(since=None, from_iso="2026-01-01", to_iso=None, now=now)
        assert start == datetime(2026, 1, 1)
        assert end == now

    def test_to_iso_only(self) -> None:
        now = self._now()
        start, end = resolve_window(since=None, from_iso=None, to_iso="2026-03-31", now=now)
        assert start == datetime.min
        assert end == datetime(2026, 3, 31)

    def test_from_and_to(self) -> None:
        now = self._now()
        start, end = resolve_window(since=None, from_iso="2026-01-01", to_iso="2026-03-31", now=now)
        assert start == datetime(2026, 1, 1)
        assert end == datetime(2026, 3, 31)

    def test_invalid_since_raises(self) -> None:
        now = self._now()
        with pytest.raises(ValueError, match="Invalid since"):
            resolve_window(since="notawindow", from_iso=None, to_iso=None, now=now)

    def test_invalid_unit_raises(self) -> None:
        now = self._now()
        with pytest.raises(ValueError, match="Invalid since"):
            resolve_window(since="7x", from_iso=None, to_iso=None, now=now)


# ---------------------------------------------------------------------------
# _open_history guard
# ---------------------------------------------------------------------------


class TestOpenHistoryGuard:
    def test_raises_for_hermes_db(self, tmp_path: Path) -> None:
        hermes = str(tmp_path / "hermes.db")
        with pytest.raises(HermesGuardError):
            _open_history(hermes)

    def test_raises_for_memories_db(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Ensure MINTMORY_DB is not set to avoid cross-contamination
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        memories = str(Path.home() / ".mintmory" / "memories.db")
        with pytest.raises(HermesGuardError):
            _open_history(memories)

    def test_raises_for_mintmory_db_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        working_db = str(tmp_path / "working.db")
        monkeypatch.setenv("MINTMORY_DB", working_db)
        with pytest.raises(HermesGuardError):
            _open_history(working_db)

    def test_accepts_valid_history_db(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        hist_db = str(tmp_path / "agent-history.db")
        store = _open_history(hist_db)
        assert store is not None
        store.close()


# ---------------------------------------------------------------------------
# timeline
# ---------------------------------------------------------------------------


class TestTimeline:
    def test_returns_rows_in_window(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "hist.db")
        store = _open_store(db)
        # Two sessions: one recent (within 30d), one old (90d ago)
        now = datetime.now(UTC).replace(tzinfo=None)
        recent = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old = (now - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed(store, session_id="sess-recent", ts_start=recent, ts_end=recent)
        _seed(store, session_id="sess-old", ts_start=old, ts_end=old)
        store.close()

        rows = timeline(db, since="30d")
        assert len(rows) == 1
        assert rows[0]["session_id"] == "sess-recent"

    def test_newest_first_ordering(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "hist2.db")
        store = _open_store(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        t1 = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        t2 = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        t3 = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed(store, session_id="sess-1", ts_start=t1, ts_end=t1)
        _seed(store, session_id="sess-2", ts_start=t2, ts_end=t2)
        _seed(store, session_id="sess-3", ts_start=t3, ts_end=t3)
        store.close()

        rows = timeline(db, since="30d")
        assert len(rows) == 3
        dates = [r["date"] for r in rows]
        assert dates == sorted(dates, reverse=True)

    def test_repo_filter(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "hist3.db")
        store = _open_store(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        t = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed(store, session_id="sess-a", ts_start=t, ts_end=t, repo="repoA")
        _seed(store, session_id="sess-b", ts_start=t, ts_end=t, repo="repoB")
        store.close()

        rows = timeline(db, since="30d", repo="repoA")
        assert len(rows) == 1
        assert rows[0]["repo"] == "repoA"

    def test_kind_filter(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "hist4.db")
        store = _open_store(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        t = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed(store, session_id="sess-fix", ts_start=t, ts_end=t, kind="fix")
        _seed(store, session_id="sess-feat", ts_start=t, ts_end=t, kind="feature")
        store.close()

        rows = timeline(db, since="30d", kind="fix")
        assert len(rows) == 1
        assert rows[0]["kind"] == "fix"

    def test_row_keys_present(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "hist5.db")
        store = _open_store(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        t = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed(store, session_id="sess-keys", ts_start=t, ts_end=t)
        store.close()

        rows = timeline(db, since="30d")
        assert len(rows) == 1
        row = rows[0]
        expected_keys = {
            "date",
            "ts_start",
            "agent",
            "collection",
            "repo",
            "branch",
            "kind",
            "title",
            "summary",
            "session_id",
            "source_path",
            # Phase-2 segment fields
            "segment_index",
            "segment_count",
            "turn_lo",
            "turn_hi",
            "outcome",
        }
        assert expected_keys == set(row.keys())

    def test_default_window_90d(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "hist6.db")
        store = _open_store(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        recent = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old = (now - timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed(store, session_id="sess-r", ts_start=recent, ts_end=recent)
        _seed(store, session_id="sess-o", ts_start=old, ts_end=old)
        store.close()

        rows = timeline(db)  # no since/from/to => default 90d
        assert len(rows) == 1
        assert rows[0]["session_id"] == "sess-r"

    def test_hermes_guard_in_timeline(self, tmp_path: Path) -> None:
        with pytest.raises(HermesGuardError):
            timeline(str(tmp_path / "hermes.db"))


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_returns_only_session_summaries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "srch.db")
        store = _open_store(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        t = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed(store, session_id="sess-srch", ts_start=t, ts_end=t, summary_text="OAuth login fix")
        # Add a plain (non-session-summary) memory — it must not appear in search results
        store.add_memory(content="OAuth documentation note", category="fact", source="agent")
        store.close()

        results = search(db, "oauth login")
        assert isinstance(results, list)
        assert results, "the seeded session summary should match"
        # Only real session summaries come back: the plain non-session memory's
        # content must never appear, and every row carries a real session_id.
        for row in results:
            assert row["session_id"]  # non-empty -> a genuine session summary
            assert "OAuth documentation note" not in row["summary"]
        assert any(r["session_id"] == "sess-srch" for r in results)

    def test_search_repo_filter(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "srch2.db")
        store = _open_store(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        t = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed(
            store,
            session_id="sess-ra",
            ts_start=t,
            ts_end=t,
            repo="repoA",
            summary_text="login bug fix repoA",
        )
        _seed(
            store,
            session_id="sess-rb",
            ts_start=t,
            ts_end=t,
            repo="repoB",
            summary_text="login bug fix repoB",
        )
        store.close()

        results = search(db, "login bug", repo="repoA")
        for row in results:
            assert row["repo"] == "repoA"

    def test_search_since_filter(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "srch3.db")
        store = _open_store(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        recent = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old = (now - timedelta(days=200)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed(
            store,
            session_id="sess-recent",
            ts_start=recent,
            ts_end=recent,
            summary_text="auth token refresh fix recent",
        )
        _seed(
            store,
            session_id="sess-old",
            ts_start=old,
            ts_end=old,
            summary_text="auth token refresh fix old",
        )
        store.close()

        results = search(db, "auth token", since="30d")
        # Old session is outside the window; should not appear
        session_ids = [r["session_id"] for r in results]
        assert "sess-old" not in session_ids

    def test_hermes_guard_in_search(self, tmp_path: Path) -> None:
        with pytest.raises(HermesGuardError):
            search(str(tmp_path / "hermes.db"), "anything")

    def test_row_shape_from_search(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "srch4.db")
        store = _open_store(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        t = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed(
            store,
            session_id="sess-shape",
            ts_start=t,
            ts_end=t,
            summary_text="database migration schema shape test",
        )
        store.close()

        results = search(db, "database migration schema")
        if results:
            row = results[0]
            expected_keys = {
                "date",
                "ts_start",
                "agent",
                "collection",
                "repo",
                "branch",
                "kind",
                "title",
                "summary",
                "session_id",
                "source_path",
                # Phase-2 segment fields
                "segment_index",
                "segment_count",
                "turn_lo",
                "turn_hi",
                "outcome",
            }
            assert expected_keys == set(row.keys())


def test_timeline_creates_missing_parent_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First-run query on a not-yet-existing parent dir returns empty, never crashes."""
    monkeypatch.delenv("MINTMORY_DB", raising=False)
    db = str(tmp_path / "nope" / "deeper" / "agent-history.db")  # parent does not exist
    rows = timeline(db, since="30d")  # must NOT raise sqlite OperationalError
    assert rows == []


# ---------------------------------------------------------------------------
# Phase-2 query tests: segment fields, tiebreak ordering, group_by_session
# ---------------------------------------------------------------------------


def _make_seg_session(
    session_id: str = "sess-seg-001",
    ts_start: str = "2025-06-01T10:00:00Z",
    ts_end: str = "2025-06-01T10:30:00Z",
) -> SessionSummary:
    return SessionSummary(
        session_id=session_id,
        agent="claude_code",
        repo="myproject",
        repo_path="/home/user/myproject",
        branch="main",
        ts_start=ts_start,
        ts_end=ts_end,
        turn_count=6,
        tools_used=["bash"],
        kind="investigation",
        title="",
        summary_text="",
        source_path="",
        distiller_version=1,
    )


def _make_seg_turns(n: int) -> list[NormalizedTurn]:
    return [
        NormalizedTurn(seq=i, ts=None, role="user" if i % 2 == 0 else "assistant", text=f"turn {i}")
        for i in range(n)
    ]


def _make_seg(idx: int, lo: int, hi: int, ts_start: str, ts_end: str) -> Segment:
    return Segment(idx=idx, turn_lo=lo, turn_hi=hi, ts_start=ts_start, ts_end=ts_end)


class TestPhase2ShapeRow:
    def test_shape_row_has_segment_fields(self) -> None:
        """_shape_row includes segment_index, segment_count, turn_lo, turn_hi, outcome."""
        meta = {
            "agent": "claude_code",
            "collection": "claude-code",
            "repo": "testrepo",
            "branch": "main",
            "kind": "fix",
            "title": "Fix bug",
            "session_id": "s1",
            "source_path": "/tmp/foo",
            "ts_start": "2025-06-01T10:00:00Z",
            "segment_index": 1,
            "segment_count": 3,
            "turn_lo": 5,
            "turn_hi": 10,
            "outcome": "partial",
        }
        row = _shape_row("summary text", meta, "2025-06-01T10:00:00")
        assert row["segment_index"] == 1
        assert row["segment_count"] == 3
        assert row["turn_lo"] == 5
        assert row["turn_hi"] == 10
        assert row["outcome"] == "partial"
        assert row["title"] == "Fix bug"

    def test_shape_row_defaults_for_single_segment(self) -> None:
        """Single-segment rows (no Phase-2 keys in meta) default to 0/1/''."""
        meta = {
            "agent": "claude_code",
            "collection": "claude-code",
            "repo": "r",
            "branch": "main",
            "kind": "fix",
            "title": "",
            "session_id": "s1",
            "source_path": "",
            "ts_start": "2025-06-01T10:00:00Z",
        }
        row = _shape_row("text", meta, "2025-06-01")
        assert row["segment_index"] == 0
        assert row["segment_count"] == 1
        assert row["turn_lo"] == 0
        assert row["turn_hi"] == 0
        assert row["outcome"] == ""


class TestPhase2TimelineTiebreak:
    def test_same_second_segments_ordered_by_segment_index(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two segments with the same valid_from must appear in ascending segment_index order."""
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "tiebreak.db")
        store = _open_store(db)

        session_id = "tiebreak-sess"
        # Same second for both segments
        same_ts = "2025-06-01T10:00:00Z"
        summary = _make_seg_session(session_id=session_id, ts_start=same_ts, ts_end=same_ts)
        turns = _make_seg_turns(4)
        segs = [
            _make_seg(0, 0, 1, same_ts, same_ts),
            _make_seg(1, 2, 3, same_ts, same_ts),
        ]
        write_session_segments(store, summary, segs, turns)
        store.close()

        rows = timeline(db, since="400d")
        session_rows = [r for r in rows if r["session_id"] == session_id]
        assert len(session_rows) == 2
        assert session_rows[0]["segment_index"] == 0
        assert session_rows[1]["segment_index"] == 1

    def test_timeline_row_keys_include_phase2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Timeline rows include segment_index, segment_count, turn_lo, turn_hi, outcome."""
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "seg-keys.db")
        store = _open_store(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        ts = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        summary = _make_seg_session(session_id="seg-keys-001", ts_start=ts, ts_end=ts)
        turns = _make_seg_turns(2)
        segs = [_make_seg(0, 0, 1, ts, ts)]
        write_session_segments(store, summary, segs, turns)
        store.close()

        rows = timeline(db, since="30d")
        assert len(rows) == 1
        row = rows[0]
        assert "segment_index" in row
        assert "segment_count" in row
        assert "turn_lo" in row
        assert "turn_hi" in row
        assert "outcome" in row
        assert "title" in row


class TestPhase2GroupBySession:
    def test_group_by_session_groups_segments(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """group_by_session=True groups segments by session, each group ascending by index."""
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "group.db")
        store = _open_store(db)

        now = datetime.now(UTC).replace(tzinfo=None)
        # Session A: 3 segments at t=10min ago
        ts_a = (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        summary_a = _make_seg_session("sess-group-A", ts_start=ts_a, ts_end=ts_a)
        turns_a = _make_seg_turns(6)
        segs_a = [
            _make_seg(0, 0, 1, ts_a, ts_a),
            _make_seg(1, 2, 3, ts_a, ts_a),
            _make_seg(2, 4, 5, ts_a, ts_a),
        ]
        write_session_segments(store, summary_a, segs_a, turns_a)

        # Session B: 2 segments at t=20min ago
        ts_b = (now - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
        summary_b = _make_seg_session("sess-group-B", ts_start=ts_b, ts_end=ts_b)
        turns_b = _make_seg_turns(4)
        segs_b = [
            _make_seg(0, 0, 1, ts_b, ts_b),
            _make_seg(1, 2, 3, ts_b, ts_b),
        ]
        write_session_segments(store, summary_b, segs_b, turns_b)
        store.close()

        rows = timeline(db, since="30d", group_by_session=True)
        # Session A is newer — its 3 segments come first
        sess_ids = [r["session_id"] for r in rows]
        a_positions = [i for i, sid in enumerate(sess_ids) if sid == "sess-group-A"]
        b_positions = [i for i, sid in enumerate(sess_ids) if sid == "sess-group-B"]

        # A's group comes before B's group
        assert max(a_positions) < min(b_positions)
        # Within each group, segment_index is ascending
        a_indices = [rows[p]["segment_index"] for p in a_positions]
        b_indices = [rows[p]["segment_index"] for p in b_positions]
        assert a_indices == sorted(a_indices)
        assert b_indices == sorted(b_indices)

    def test_group_by_session_false_is_flat(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """group_by_session=False (default) returns flat list in newest-first order."""
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "flat.db")
        store = _open_store(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        ts = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        summary = _make_seg_session("sess-flat-001", ts_start=ts, ts_end=ts)
        turns = _make_seg_turns(4)
        segs = [_make_seg(0, 0, 1, ts, ts), _make_seg(1, 2, 3, ts, ts)]
        write_session_segments(store, summary, segs, turns)
        store.close()

        rows = timeline(db, since="30d", group_by_session=False)
        # Should return 2 rows (flat, not nested)
        assert isinstance(rows, list)
        assert len(rows) == 2


class TestPhase2SearchSegmentFields:
    def test_search_rows_have_segment_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """search() rows include segment_index, segment_count, turn_lo, turn_hi, outcome."""
        monkeypatch.delenv("MINTMORY_DB", raising=False)
        db = str(tmp_path / "srch-seg.db")
        store = _open_store(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        ts = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        summary = _make_seg_session("seg-search-001", ts_start=ts, ts_end=ts)
        turns = _make_seg_turns(2)
        turns[0] = NormalizedTurn(
            seq=0, ts=None, role="user", text="implement OAuth2 authentication flow"
        )
        segs = [_make_seg(0, 0, 1, ts, ts)]
        write_session_segments(store, summary, segs, turns)
        store.close()

        results = search(db, "OAuth2 authentication")
        for row in results:
            assert "segment_index" in row
            assert "segment_count" in row
            assert "turn_lo" in row
            assert "turn_hi" in row
            assert "outcome" in row
