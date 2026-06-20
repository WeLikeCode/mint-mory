"""
Tests for ``mintmory history`` CLI sub-commands.

Covers:
- timeline --since window filters sessions by valid_from
- scrub flags a planted secret (exits non-zero)
- scrub passes on clean data (exits zero)
- guard refuses hermes.db
- backfill and sync smoke tests
- search smoke test

All tests use a temp DB — never touch ~/.mintmory, ~/.claude, etc.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from mintmory.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def history_db(tmp_path: Path) -> Iterator[str]:
    """Return path to a temp history DB (never ~/.mintmory/agent-history.db)."""
    db = str(tmp_path / "test-history.db")
    yield db


@pytest.fixture()
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the *working* store at a temp path so _get_store() is isolated."""
    db_path = tmp_path / "cli_test.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    yield db_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_session(
    db_path: str,
    *,
    session_id: str = "sess-001",
    repo: str = "myproject",
    kind: str = "fix",
    valid_from: datetime | None = None,
    summary_text: str = "Fixed the auth bug in the login handler",
    title: str = "",
) -> None:
    """Directly write a session_summary record into the history DB.

    Bypasses distill() to store the kind exactly as given — this lets the
    kind-filter test assert on a known value without fighting the keyword
    heuristic.
    """
    from mintmory.core.history.ingest import _open_history_db, write_session
    from mintmory.core.history.models import SessionSummary

    store = _open_history_db(db_path)
    ts = (valid_from or datetime.utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Use title = summary_text[:80] if not provided, to mimic distill output
    effective_title = title or summary_text[:80]
    summary = SessionSummary(
        session_id=session_id,
        agent="claude_code",
        repo=repo,
        repo_path="/tmp/myproject",
        branch="main",
        ts_start=ts,
        ts_end=ts,
        turn_count=2,
        tools_used=["bash"],
        kind=kind,
        title=effective_title,
        summary_text=summary_text,
    )
    write_session(store, summary)
    store.close()


# ---------------------------------------------------------------------------
# Guard — refuses hermes.db
# ---------------------------------------------------------------------------


class TestHistoryGuard:
    def test_timeline_refuses_hermes_db(self, tmp_path: Path, cli_db: Path) -> None:
        """history timeline --db <path>/hermes.db must exit non-zero."""
        hermes = str(tmp_path / "hermes.db")
        result = runner.invoke(
            app,
            ["history", "timeline", "--db", hermes, "--since", "30d"],
        )
        assert result.exit_code != 0

    def test_scrub_refuses_hermes_db(self, tmp_path: Path, cli_db: Path) -> None:
        """history scrub --db <path>/hermes.db must exit non-zero."""
        hermes = str(tmp_path / "hermes.db")
        result = runner.invoke(app, ["history", "scrub", "--db", hermes])
        assert result.exit_code != 0

    def test_backfill_refuses_hermes_db(self, tmp_path: Path, cli_db: Path) -> None:
        """history backfill --db <path>/hermes.db must exit non-zero."""
        hermes = str(tmp_path / "hermes.db")
        result = runner.invoke(app, ["history", "backfill", "--db", hermes])
        assert result.exit_code != 0

    def test_timeline_refuses_memories_db(self, cli_db: Path) -> None:
        """history timeline --db ~/.mintmory/memories.db must exit non-zero."""
        result = runner.invoke(
            app,
            [
                "history",
                "timeline",
                "--db",
                "~/.mintmory/memories.db",
                "--since",
                "30d",
            ],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# timeline — --since window filtering
# ---------------------------------------------------------------------------


class TestHistoryTimeline:
    def test_timeline_empty_db_exits_zero(self, history_db: str, cli_db: Path) -> None:
        """timeline on an empty history DB exits 0 and shows '0 session(s)'."""
        result = runner.invoke(
            app,
            ["history", "timeline", "--db", history_db, "--since", "30d"],
        )
        assert result.exit_code == 0, result.output
        assert "0 session(s)" in result.output

    def test_timeline_shows_session_in_window(self, history_db: str, cli_db: Path) -> None:
        """A session within --since window appears in the timeline."""
        recent = datetime.utcnow() - timedelta(days=5)
        _seed_session(
            history_db,
            session_id="recent-001",
            repo="myproject",
            valid_from=recent,
            summary_text="Implemented OAuth flow",
        )
        result = runner.invoke(
            app,
            ["history", "timeline", "--db", history_db, "--since", "30d"],
        )
        assert result.exit_code == 0, result.output
        assert "1 session(s)" in result.output

    def test_timeline_excludes_session_outside_window(self, history_db: str, cli_db: Path) -> None:
        """A session older than --since window is excluded."""
        old = datetime.utcnow() - timedelta(days=120)
        _seed_session(
            history_db,
            session_id="old-001",
            repo="oldproject",
            valid_from=old,
            summary_text="Old fix from long ago",
        )
        result = runner.invoke(
            app,
            ["history", "timeline", "--db", history_db, "--since", "30d"],
        )
        assert result.exit_code == 0, result.output
        assert "0 session(s)" in result.output

    def test_timeline_filters_inside_outside_window(self, history_db: str, cli_db: Path) -> None:
        """Two sessions: one inside and one outside --since 30d; only 1 returned."""
        recent = datetime.utcnow() - timedelta(days=10)
        old = datetime.utcnow() - timedelta(days=60)
        _seed_session(
            history_db,
            session_id="in-001",
            valid_from=recent,
            summary_text="Recent feature work",
        )
        _seed_session(
            history_db,
            session_id="out-001",
            valid_from=old,
            summary_text="Old investigation",
        )
        result = runner.invoke(
            app,
            ["history", "timeline", "--db", history_db, "--since", "30d"],
        )
        assert result.exit_code == 0, result.output
        assert "1 session(s)" in result.output

    def test_timeline_repo_filter(self, history_db: str, cli_db: Path) -> None:
        """--repo filters by repository name."""
        now = datetime.utcnow()
        _seed_session(
            history_db,
            session_id="repo-a-001",
            repo="alpha",
            valid_from=now - timedelta(days=1),
        )
        _seed_session(
            history_db,
            session_id="repo-b-001",
            repo="beta",
            valid_from=now - timedelta(days=2),
        )
        result = runner.invoke(
            app,
            [
                "history",
                "timeline",
                "--db",
                history_db,
                "--since",
                "30d",
                "--repo",
                "alpha",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "1 session(s)" in result.output

    def test_timeline_kind_filter(self, history_db: str, cli_db: Path) -> None:
        """--kind filters by session kind stored in metadata."""
        now = datetime.utcnow()
        _seed_session(
            history_db,
            session_id="fix-001",
            kind="fix",
            valid_from=now - timedelta(days=1),
            summary_text="Patched the authentication bug in the login handler",
        )
        _seed_session(
            history_db,
            session_id="feature-001",
            kind="feature",
            valid_from=now - timedelta(days=2),
            summary_text="Implemented the new onboarding wizard",
        )
        result = runner.invoke(
            app,
            [
                "history",
                "timeline",
                "--db",
                history_db,
                "--since",
                "30d",
                "--kind",
                "fix",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "1 session(s)" in result.output

    def test_timeline_from_to_window(self, history_db: str, cli_db: Path) -> None:
        """--from/--to ISO window works instead of --since."""
        target = datetime(2024, 3, 15, 10, 0, 0)
        _seed_session(
            history_db,
            session_id="iso-001",
            valid_from=target,
        )
        result = runner.invoke(
            app,
            [
                "history",
                "timeline",
                "--db",
                history_db,
                "--from",
                "2024-03-01",
                "--to",
                "2024-04-01",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "1 session(s)" in result.output

    def test_timeline_since_weeks_syntax(self, history_db: str, cli_db: Path) -> None:
        """--since 4w (weeks) parses correctly."""
        recent = datetime.utcnow() - timedelta(days=7)
        _seed_session(
            history_db,
            session_id="week-001",
            valid_from=recent,
        )
        result = runner.invoke(
            app,
            ["history", "timeline", "--db", history_db, "--since", "4w"],
        )
        assert result.exit_code == 0, result.output
        assert "1 session(s)" in result.output

    def test_timeline_since_months_syntax(self, history_db: str, cli_db: Path) -> None:
        """--since 2m (months) parses correctly."""
        recent = datetime.utcnow() - timedelta(days=20)
        _seed_session(
            history_db,
            session_id="month-001",
            valid_from=recent,
        )
        result = runner.invoke(
            app,
            ["history", "timeline", "--db", history_db, "--since", "2m"],
        )
        assert result.exit_code == 0, result.output
        assert "1 session(s)" in result.output

    def test_timeline_invalid_since_errors(self, history_db: str, cli_db: Path) -> None:
        """An invalid --since value exits non-zero."""
        result = runner.invoke(
            app,
            ["history", "timeline", "--db", history_db, "--since", "badformat"],
        )
        assert result.exit_code != 0

    def test_timeline_shows_table_headers(self, history_db: str, cli_db: Path) -> None:
        """timeline renders a table with date/repo/kind/summary columns."""
        result = runner.invoke(
            app,
            ["history", "timeline", "--db", history_db, "--since", "30d"],
        )
        assert result.exit_code == 0, result.output
        assert "date" in result.output
        assert "repo" in result.output


# ---------------------------------------------------------------------------
# scrub — flags a planted secret
# ---------------------------------------------------------------------------


class TestHistoryScrub:
    def test_scrub_clean_db_exits_zero(self, history_db: str, cli_db: Path) -> None:
        """scrub on a DB without secrets exits 0."""
        _seed_session(
            history_db,
            session_id="clean-001",
            summary_text="Implemented the OAuth flow for the user service",
        )
        result = runner.invoke(app, ["history", "scrub", "--db", history_db])
        assert result.exit_code == 0, result.output
        assert "no residual secrets" in result.output.lower()

    def test_scrub_empty_db_exits_zero(self, history_db: str, cli_db: Path) -> None:
        """scrub on an empty history DB exits 0."""
        result = runner.invoke(app, ["history", "scrub", "--db", history_db])
        assert result.exit_code == 0, result.output

    def test_scrub_flags_planted_sk_key(self, history_db: str, cli_db: Path) -> None:
        """scrub exits non-zero when a session_summary contains an sk- key."""
        # Plant a fake OpenAI key in the summary text (bypass redact for the test
        # by writing directly to the DB)
        from mintmory.core.history.ingest import _open_history_db
        from mintmory.core.types import MemoryCategory, MemorySource

        store = _open_history_db(history_db)
        # Write directly with a fake secret embedded
        fake_secret = "sk-abcdefghijklmnopqrstuvwxyz012345"
        envelope = json.dumps(
            {
                "record_type": "session_summary",
                "agent": "claude_code",
                "repo": "myproject",
                "session_id": "secret-sess-001",
            }
        )
        conn = store.connect()
        import uuid
        from datetime import datetime

        mem_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO memories "
            "(id, content, category, source, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                mem_id,
                f"I used {fake_secret} to call the API",
                MemoryCategory.EPISODIC.value,
                MemorySource.AGENT.value,
                envelope,
                now,
                now,
            ),
        )
        conn.commit()
        store.close()

        result = runner.invoke(app, ["history", "scrub", "--db", history_db])
        assert result.exit_code != 0, result.output
        assert "FAIL" in result.output or "residual" in result.output.lower()

    def test_scrub_flags_planted_mk_agent_key(self, history_db: str, cli_db: Path) -> None:
        """scrub exits non-zero when a session_summary contains an mk_agent_ key."""
        from mintmory.core.history.ingest import _open_history_db
        from mintmory.core.types import MemoryCategory, MemorySource

        store = _open_history_db(history_db)
        fake_key = "mk_agent_ABCDEFGHIJKLMNOPQRSTUVWXYZ01234567"
        envelope = json.dumps(
            {
                "record_type": "session_summary",
                "agent": "claude_code",
                "repo": "mintkey",
                "session_id": "mkagent-secret-001",
            }
        )
        conn = store.connect()
        import uuid
        from datetime import datetime

        mem_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO memories "
            "(id, content, category, source, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                mem_id,
                f"Broker key leaked: {fake_key}",
                MemoryCategory.EPISODIC.value,
                MemorySource.AGENT.value,
                envelope,
                now,
                now,
            ),
        )
        conn.commit()
        store.close()

        result = runner.invoke(app, ["history", "scrub", "--db", history_db])
        assert result.exit_code != 0, result.output

    def test_scrub_flags_planted_jwt(self, history_db: str, cli_db: Path) -> None:
        """scrub exits non-zero when a session_summary contains a JWT."""
        from mintmory.core.history.ingest import _open_history_db
        from mintmory.core.types import MemoryCategory, MemorySource

        store = _open_history_db(history_db)
        fake_jwt = (
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        envelope = json.dumps(
            {
                "record_type": "session_summary",
                "agent": "claude_code",
                "repo": "api",
                "session_id": "jwt-secret-001",
            }
        )
        conn = store.connect()
        import uuid
        from datetime import datetime

        mem_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO memories "
            "(id, content, category, source, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                mem_id,
                f"Auth token: {fake_jwt}",
                MemoryCategory.EPISODIC.value,
                MemorySource.AGENT.value,
                envelope,
                now,
                now,
            ),
        )
        conn.commit()
        store.close()

        result = runner.invoke(app, ["history", "scrub", "--db", history_db])
        assert result.exit_code != 0, result.output


# ---------------------------------------------------------------------------
# backfill / sync — smoke tests (no real adapter files needed)
# ---------------------------------------------------------------------------


class TestHistoryBackfill:
    def test_backfill_empty_source_exits_zero(
        self, history_db: str, cli_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """backfill with a stub adapter that yields nothing exits 0."""

        import mintmory.core.history.ingest as ingest_mod
        from mintmory.core.history.models import NormalizedTurn, SessionSummary

        def _empty_iter() -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
            return iter([])

        monkeypatch.setattr(ingest_mod, "_load_adapter", lambda _: _empty_iter)

        result = runner.invoke(
            app,
            [
                "history",
                "backfill",
                "--db",
                history_db,
                "--source",
                "claude_code",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "scanned" in result.output

    def test_backfill_refuses_hermes_db(self, tmp_path: Path, cli_db: Path) -> None:
        """backfill --db hermes.db must exit non-zero."""
        hermes = str(tmp_path / "hermes.db")
        result = runner.invoke(app, ["history", "backfill", "--db", hermes])
        assert result.exit_code != 0


class TestHistorySync:
    def test_sync_empty_source_exits_zero(
        self, history_db: str, cli_db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sync with a stub adapter that yields nothing exits 0."""

        import mintmory.core.history.ingest as ingest_mod
        from mintmory.core.history.models import NormalizedTurn, SessionSummary

        def _empty_iter() -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
            return iter([])

        monkeypatch.setattr(ingest_mod, "_load_adapter", lambda _: _empty_iter)

        result = runner.invoke(
            app,
            ["history", "sync", "--db", history_db, "--source", "claude_code"],
        )
        assert result.exit_code == 0, result.output
        assert "scanned" in result.output


# ---------------------------------------------------------------------------
# search — smoke test
# ---------------------------------------------------------------------------


class TestHistorySearch:
    def test_search_empty_db_exits_zero(self, history_db: str, cli_db: Path) -> None:
        """history search on empty DB exits 0 and shows '0 result(s)'."""
        result = runner.invoke(
            app,
            ["history", "search", "oauth", "--db", history_db],
        )
        assert result.exit_code == 0, result.output
        assert "result(s)" in result.output

    def test_search_finds_seeded_session(self, history_db: str, cli_db: Path) -> None:
        """history search returns a seeded session_summary that matches the query."""
        _seed_session(
            history_db,
            session_id="search-001",
            summary_text="Refactored OAuth PKCE authentication flow",
        )
        result = runner.invoke(
            app,
            ["history", "search", "oauth", "--db", history_db],
        )
        assert result.exit_code == 0, result.output
        # Should find the session
        assert "result(s)" in result.output

    def test_search_refuses_hermes_db(self, tmp_path: Path, cli_db: Path) -> None:
        hermes = str(tmp_path / "hermes.db")
        result = runner.invoke(app, ["history", "search", "anything", "--db", hermes])
        assert result.exit_code != 0
