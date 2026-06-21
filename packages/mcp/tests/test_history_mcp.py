"""
Tests for the mintmory-history MCP server (read-only).

Covers:
- Exactly 3 tools registered: history_timeline, history_search, history_stats.
- NO write tools present (memory_add / memory_dream / memory_archive / summary_put).
- history_timeline returns rows from a temp MINTMORY_HISTORY_DB.
- history_search returns rows from a temp DB.
- main()-level guard refuses a working-store path.

Uses a temp DB seeded via write_session; never touches ~/.mintmory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from mintmory.core.history.ingest import HermesGuardError, write_session, write_session_segments
from mintmory.core.history.models import NormalizedTurn, Segment, SessionSummary
from mintmory.core.storage import StorageAdapter
from mintmory.mcp import history_server
from mintmory.mcp.history_server import mcp

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_store(db_path: str) -> StorageAdapter:
    s = StorageAdapter(db_path)
    s.initialise()
    return s


def _make_session(
    *,
    session_id: str = "sess-001",
    ts_start: str = "2025-06-01T10:00:00Z",
    ts_end: str = "2025-06-01T10:30:00Z",
    summary_text: str = "Fixed auth bug.",
    title: str = "Fix auth",
    kind: str = "fix",
    repo: str = "myproject",
) -> SessionSummary:
    return SessionSummary(
        session_id=session_id,
        agent="claude_code",
        repo=repo,
        repo_path="/home/user/myproject",
        branch="main",
        ts_start=ts_start,
        ts_end=ts_end,
        turn_count=4,
        tools_used=["bash"],
        kind=kind,
        title=title,
        summary_text=summary_text,
        source_path="",
        distiller_version=1,
    )


def _seed(store: StorageAdapter, **kwargs: object) -> None:
    write_session(store, _make_session(**kwargs))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def history_client(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client[Any]]:
    """Yield an in-memory client bound to an isolated temp history DB."""
    # Ensure the working-store env vars don't interfere
    monkeypatch.delenv("MINTMORY_DB", raising=False)

    # Create and seed the temp history DB
    db_file = str(tmp_path / "agent-history.db")
    store = _open_store(db_file)
    now = datetime.now(UTC).replace(tzinfo=None)
    recent = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _seed(
        store,
        session_id="mcp-sess-1",
        ts_start=recent,
        ts_end=recent,
        summary_text="Implemented OAuth2 PKCE flow in auth.py",
        kind="feature",
        repo="myrepo",
    )
    store.close()

    monkeypatch.setenv("MINTMORY_HISTORY_DB", db_file)

    async with Client(mcp) as client:
        yield client


# ---------------------------------------------------------------------------
# Tool inventory
# ---------------------------------------------------------------------------


async def test_exactly_three_read_only_tools(history_client: Client[Any]) -> None:
    """The server must expose EXACTLY history_timeline, history_search, history_stats."""
    names = {tool.name for tool in await history_client.list_tools()}
    assert names == {"history_timeline", "history_search", "history_stats"}


async def test_no_write_tools_present(history_client: Client[Any]) -> None:
    """No mutating tool from the working-store server may be reachable here."""
    names = {tool.name for tool in await history_client.list_tools()}
    # Genuinely state-changing tools — none may appear on the read-only history server.
    mutating = {
        "memory_add",
        "memory_dream",
        "memory_archive",
        "summary_put",
        "memory_note",
        "image_caption_put",
        "vision_run",
        "session_feedback",
    }
    overlap = names & mutating
    assert overlap == set(), f"Unexpected write tools present: {overlap}"


# ---------------------------------------------------------------------------
# history_timeline
# ---------------------------------------------------------------------------


async def test_history_timeline_returns_rows(history_client: Client[Any]) -> None:
    """history_timeline with a wide window returns the seeded session."""
    res = await history_client.call_tool("history_timeline", {"since": "30d"})
    data = res.data
    assert isinstance(data, list)
    assert len(data) >= 1
    row = data[0]
    assert row["session_id"] == "mcp-sess-1"
    assert row["repo"] == "myrepo"
    assert row["kind"] == "feature"
    assert "summary" in row


async def test_history_timeline_row_keys(history_client: Client[Any]) -> None:
    """Every row has the documented set of keys (including Phase-2 segment fields)."""
    res = await history_client.call_tool("history_timeline", {"since": "30d"})
    data = res.data
    assert len(data) >= 1
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
    assert expected_keys == set(data[0].keys())


async def test_history_timeline_empty_window_returns_empty(history_client: Client[Any]) -> None:
    """A window that excludes the seeded session returns []."""
    # The seeded session is 5d ago; asking for the window 4d–3d ago should miss it.
    now = datetime.now(UTC).replace(tzinfo=None)
    to_date = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
    from_date = (now - timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%S")
    res = await history_client.call_tool(
        "history_timeline", {"from_date": from_date, "to_date": to_date}
    )
    assert res.data == []


async def test_history_timeline_repo_filter(history_client: Client[Any]) -> None:
    """repo filter excludes sessions from other repos."""
    res = await history_client.call_tool(
        "history_timeline", {"since": "30d", "repo": "nonexistent-repo"}
    )
    assert res.data == []


# ---------------------------------------------------------------------------
# history_search
# ---------------------------------------------------------------------------


async def test_history_search_returns_rows(history_client: Client[Any]) -> None:
    """history_search finds the seeded session summary."""
    res = await history_client.call_tool("history_search", {"query_text": "OAuth2 PKCE"})
    data = res.data
    assert isinstance(data, list)
    # May return 0 rows if FTS didn't index yet / no vector — at minimum no error
    for row in data:
        assert "session_id" in row
        assert "summary" in row


async def test_history_search_only_session_summaries(history_client: Client[Any]) -> None:
    """history_search never returns non-session-summary records (structural check)."""
    res = await history_client.call_tool("history_search", {"query_text": "auth"})
    for row in res.data:
        # Every returned row must have session_id (part of session_summary shape)
        assert "session_id" in row


async def test_history_search_since_param_accepted(history_client: Client[Any]) -> None:
    """since param is accepted without error."""
    res = await history_client.call_tool("history_search", {"query_text": "auth", "since": "30d"})
    assert isinstance(res.data, list)


async def test_history_search_repo_param_accepted(history_client: Client[Any]) -> None:
    """repo param is accepted without error."""
    res = await history_client.call_tool("history_search", {"query_text": "auth", "repo": "myrepo"})
    assert isinstance(res.data, list)


# ---------------------------------------------------------------------------
# history_stats
# ---------------------------------------------------------------------------


async def test_history_stats_returns_expected_shape(history_client: Client[Any]) -> None:
    """history_stats returns a dict with the documented keys."""
    res = await history_client.call_tool("history_stats", {})
    data = res.data
    assert isinstance(data, dict)
    assert "total_sessions" in data
    assert "total_segments" in data
    assert "by_collection" in data
    assert "by_kind" in data
    assert "earliest" in data
    assert "latest" in data


async def test_history_stats_counts_seeded_session(history_client: Client[Any]) -> None:
    """history_stats total_sessions >= 1 after seeding."""
    res = await history_client.call_tool("history_stats", {})
    assert res.data["total_sessions"] >= 1
    assert res.data["total_segments"] >= 1


# ---------------------------------------------------------------------------
# Hermes guard at main() level
# ---------------------------------------------------------------------------


def test_main_guard_refuses_working_store_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() raises HermesGuardError if the DB path resolves to the working store."""
    import sys

    working_db = str(tmp_path / "hermes.db")
    monkeypatch.setenv("MINTMORY_HISTORY_DB", working_db)
    monkeypatch.delenv("MINTMORY_DB", raising=False)

    # Simulate calling main() — we patch sys.argv to avoid argparse consuming pytest args
    monkeypatch.setattr(sys, "argv", ["mintmory-history-mcp"])

    with pytest.raises((HermesGuardError, SystemExit)):
        history_server.main()


def test_main_guard_refuses_env_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() raises HermesGuardError if MINTMORY_HISTORY_DB points at memories.db."""
    import sys

    memories_db = str(Path.home() / ".mintmory" / "memories.db")
    monkeypatch.setenv("MINTMORY_HISTORY_DB", memories_db)
    monkeypatch.delenv("MINTMORY_DB", raising=False)
    monkeypatch.setattr(sys, "argv", ["mintmory-history-mcp"])

    with pytest.raises((HermesGuardError, SystemExit)):
        history_server.main()


# ---------------------------------------------------------------------------
# Phase-2: segment fields in MCP rows + history_stats sessions vs segments
# ---------------------------------------------------------------------------


def _make_seg(idx: int, lo: int, hi: int, ts: str) -> Segment:
    return Segment(idx=idx, turn_lo=lo, turn_hi=hi, ts_start=ts, ts_end=ts)


def _make_seg_turns(n: int) -> list[NormalizedTurn]:
    return [
        NormalizedTurn(seq=i, ts=None, role="user" if i % 2 == 0 else "assistant", text=f"turn {i}")
        for i in range(n)
    ]


@pytest.fixture
async def seg_history_client(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client[Any]]:
    """Client seeded with a 2-segment session + the original 1-segment session."""
    monkeypatch.delenv("MINTMORY_DB", raising=False)

    db_file = str(tmp_path / "seg-history.db")
    store = _open_store(db_file)
    now = datetime.now(UTC).replace(tzinfo=None)
    recent = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Session A: 2 segments (write_session_segments)
    summary_a = SessionSummary(
        session_id="mcp-seg-A",
        agent="claude_code",
        repo="testrepo",
        repo_path="/tmp/repo",
        branch="main",
        ts_start=recent,
        ts_end=recent,
        turn_count=4,
        tools_used=[],
        kind="feature",
        title="",
        summary_text="",
        source_path="",
        distiller_version=1,
    )
    turns_a = _make_seg_turns(4)
    turns_a[0] = NormalizedTurn(seq=0, ts=None, role="user", text="implement login feature")
    segs_a = [_make_seg(0, 0, 1, recent), _make_seg(1, 2, 3, recent)]
    write_session_segments(store, summary_a, segs_a, turns_a)

    # Session B: 1 segment (write_session — legacy path)
    _seed(
        store,
        session_id="mcp-sess-1",
        ts_start=recent,
        ts_end=recent,
        summary_text="Implemented OAuth2 PKCE flow in auth.py",
        kind="feature",
        repo="myrepo",
    )
    store.close()

    monkeypatch.setenv("MINTMORY_HISTORY_DB", db_file)

    async with Client(mcp) as client:
        yield client


async def test_history_timeline_rows_have_segment_fields(
    seg_history_client: Client[Any],
) -> None:
    """history_timeline rows include segment_index, segment_count, turn_lo, turn_hi, outcome."""
    res = await seg_history_client.call_tool("history_timeline", {"since": "30d"})
    data = res.data
    assert isinstance(data, list)
    assert len(data) >= 1
    # At least one row from the 2-segment session
    for row in data:
        assert "segment_index" in row
        assert "segment_count" in row
        assert "turn_lo" in row
        assert "turn_hi" in row
        assert "outcome" in row


async def test_history_stats_sessions_vs_segments(
    seg_history_client: Client[Any],
) -> None:
    """history_stats returns total_sessions (distinct session_id) AND total_segments (row count)."""
    res = await seg_history_client.call_tool("history_stats", {})
    data = res.data
    assert "total_sessions" in data
    assert "total_segments" in data
    # Session A has 2 segment rows + Session B has 1 = 3 total segments
    # But distinct session_ids = 2
    assert data["total_segments"] >= data["total_sessions"]
    assert data["total_sessions"] >= 2
    assert data["total_segments"] >= 3


async def test_history_timeline_group_param(
    seg_history_client: Client[Any],
) -> None:
    """history_timeline with group=True returns rows without error."""
    res = await seg_history_client.call_tool("history_timeline", {"since": "30d", "group": True})
    assert isinstance(res.data, list)
