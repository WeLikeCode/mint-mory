"""
Tests for mintmory.core.history.models and mintmory.core.history.distill.

Verifies:
- AGENTS / KINDS constants are correct.
- NormalizedTurn and SessionSummary are proper dataclasses.
- distill() is pure and idempotent.
- Kind heuristic maps keywords correctly.
- 600/80-char caps are enforced.
- distill() never un-redacts.
"""

from __future__ import annotations

import pytest
from mintmory.core.history.distill import distill
from mintmory.core.history.models import (
    AGENTS,
    KINDS,
    NormalizedTurn,
    SessionSummary,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_agents_tuple() -> None:
    assert set(AGENTS) == {"claude_code", "codex", "kiro", "hermes"}


def test_kinds_tuple() -> None:
    expected = {"fix", "feature", "refactor", "investigation", "chore", "docs", "incident"}
    assert set(KINDS) == expected


# ---------------------------------------------------------------------------
# Dataclass basics
# ---------------------------------------------------------------------------


def test_normalized_turn_fields() -> None:
    t = NormalizedTurn(seq=0, ts="2024-01-01T00:00:00Z", role="user", text="hello")
    assert t.seq == 0
    assert t.role == "user"
    assert t.tool_name is None


def test_session_summary_defaults() -> None:
    s = SessionSummary(
        session_id="s1",
        agent="claude_code",
        repo="myrepo",
        repo_path="/home/user/myrepo",
        branch="main",
        ts_start="2024-01-01T10:00:00Z",
        ts_end="2024-01-01T10:30:00Z",
        turn_count=5,
    )
    assert s.kind == "investigation"
    assert s.title == ""
    assert s.summary_text == ""
    assert s.tools_used == []
    assert s.distiller_version == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_summary(**kwargs: object) -> SessionSummary:
    defaults: dict[str, object] = {
        "session_id": "test-session-001",
        "agent": "claude_code",
        "repo": "myproject",
        "repo_path": "/home/user/myproject",
        "branch": "main",
        "ts_start": "2024-01-15T09:00:00Z",
        "ts_end": "2024-01-15T09:45:00Z",
        "turn_count": 4,
        "tools_used": ["bash", "edit"],
    }
    defaults.update(kwargs)
    return SessionSummary(**defaults)  # type: ignore[arg-type]


def _make_turns(
    user_text: str = "Fix the bug in parser",
    assistant_text: str = "Done, patched the parser.",
) -> list[NormalizedTurn]:
    return [
        NormalizedTurn(seq=0, ts=None, role="user", text=user_text),
        NormalizedTurn(seq=1, ts=None, role="assistant", text=assistant_text),
    ]


# ---------------------------------------------------------------------------
# distill() basics
# ---------------------------------------------------------------------------


class TestDistillBasics:
    def test_distill_returns_new_instance(self) -> None:
        s = _make_summary()
        turns = _make_turns()
        result = distill(s, turns)
        assert result is not s

    def test_distill_fills_title(self) -> None:
        s = _make_summary()
        turns = _make_turns(user_text="Fix the login bug in auth.py")
        result = distill(s, turns)
        assert result.title == "Fix the login bug in auth.py"

    def test_distill_fills_summary_text(self) -> None:
        s = _make_summary()
        turns = _make_turns(
            user_text="Add dark mode toggle",
            assistant_text="Implemented dark mode via CSS variables.",
        )
        result = distill(s, turns)
        assert len(result.summary_text) > 0

    def test_distill_version_stays_1(self) -> None:
        s = _make_summary()
        turns = _make_turns()
        result = distill(s, turns)
        assert result.distiller_version == 1

    def test_distill_empty_turns(self) -> None:
        s = _make_summary()
        result = distill(s, [])
        # Should not crash; title/summary may be empty
        assert isinstance(result.title, str)
        assert isinstance(result.summary_text, str)


# ---------------------------------------------------------------------------
# Pure and idempotent
# ---------------------------------------------------------------------------


class TestDistillPureIdempotent:
    def test_pure_same_inputs_same_output(self) -> None:
        s = _make_summary()
        turns = _make_turns()
        r1 = distill(s, turns)
        r2 = distill(s, turns)
        assert r1.title == r2.title
        assert r1.summary_text == r2.summary_text
        assert r1.kind == r2.kind

    def test_idempotent_applying_twice(self) -> None:
        s = _make_summary()
        turns = _make_turns()
        r1 = distill(s, turns)
        r2 = distill(r1, turns)
        assert r1.title == r2.title
        assert r1.summary_text == r2.summary_text
        assert r1.kind == r2.kind


# ---------------------------------------------------------------------------
# Kind heuristic
# ---------------------------------------------------------------------------


class TestKindHeuristic:
    @pytest.mark.parametrize(
        "user_text,expected_kind",
        [
            ("Fix the null pointer bug", "fix"),
            ("fix: handle empty list error", "fix"),
            ("implement new dashboard feature", "feature"),
            ("Add user authentication", "feature"),
            ("refactor the database layer", "refactor"),
            ("rename UserModel to User", "refactor"),
            ("update the README docs", "docs"),
            ("write documentation for the API", "docs"),
            ("investigate the memory leak", "investigation"),
            ("explore the codebase structure", "investigation"),
        ],
    )
    def test_kind_heuristic(self, user_text: str, expected_kind: str) -> None:
        s = _make_summary()
        turns = _make_turns(user_text=user_text)
        result = distill(s, turns)
        assert result.kind == expected_kind, (
            f"Expected kind={expected_kind!r} for text={user_text!r}, got {result.kind!r}"
        )

    def test_kind_always_in_kinds(self) -> None:
        texts = [
            "some random task",
            "fix bug",
            "add feature",
            "update docs",
            "refactor code",
        ]
        for text in texts:
            s = _make_summary()
            turns = _make_turns(user_text=text)
            result = distill(s, turns)
            assert result.kind in KINDS


# ---------------------------------------------------------------------------
# Character caps
# ---------------------------------------------------------------------------


class TestCharCaps:
    def test_title_max_80_chars(self) -> None:
        long_text = "A" * 200
        s = _make_summary()
        turns = _make_turns(user_text=long_text)
        result = distill(s, turns)
        assert len(result.title) <= 80

    def test_summary_text_max_600_chars(self) -> None:
        long_user = "X" * 500
        long_assistant = "Y" * 500
        s = _make_summary()
        turns = _make_turns(user_text=long_user, assistant_text=long_assistant)
        result = distill(s, turns)
        assert len(result.summary_text) <= 600

    def test_title_first_line_only(self) -> None:
        user_text = "Fix the bug\nSecond line should be ignored\nThird line"
        s = _make_summary()
        turns = _make_turns(user_text=user_text)
        result = distill(s, turns)
        assert "\n" not in result.title
        assert result.title.startswith("Fix the bug")


# ---------------------------------------------------------------------------
# Never un-redacts
# ---------------------------------------------------------------------------


class TestNeverUnredacts:
    def test_redacted_placeholder_stays_redacted(self) -> None:
        """distill() MUST NOT expand or change redaction placeholders."""
        redacted_user = "Use [REDACTED:openai_sk] to call the API"
        redacted_assistant = "Called API with [REDACTED:jwt] token."
        s = _make_summary()
        turns = _make_turns(user_text=redacted_user, assistant_text=redacted_assistant)
        result = distill(s, turns)
        # Placeholders should remain intact — check at least one appears
        combined = result.title + result.summary_text
        assert "[REDACTED:openai_sk]" in combined or "[REDACTED:jwt]" in combined
        # No real secrets should appear
        assert "sk-" not in result.title
        assert "sk-" not in result.summary_text

    def test_no_secret_introduced(self) -> None:
        """distill() on clean inputs should produce clean outputs."""
        s = _make_summary()
        turns = _make_turns(
            user_text="Add a feature to support dark mode",
            assistant_text="Implemented toggle in settings.py",
        )
        result = distill(s, turns)
        assert "sk-" not in result.title
        assert "sk-" not in result.summary_text
        assert "mk_agent_" not in result.summary_text


# ---------------------------------------------------------------------------
# Tools in summary
# ---------------------------------------------------------------------------


class TestToolsInSummary:
    def test_tools_mentioned_in_summary(self) -> None:
        s = _make_summary(tools_used=["bash", "edit", "read"])
        turns = _make_turns()
        result = distill(s, turns)
        # Should contain tool names in summary
        assert "bash" in result.summary_text or "edit" in result.summary_text

    def test_no_tools_no_tools_hint(self) -> None:
        s = _make_summary(tools_used=[])
        turns = _make_turns()
        result = distill(s, turns)
        # Should not crash; summary should still be produced
        assert isinstance(result.summary_text, str)
