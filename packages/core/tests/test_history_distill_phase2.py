"""
Phase-2 tests for mintmory.core.history.distill.

Tests:
  - distill_segment_deterministic: per-slice heuristic (like distill(), scoped).
  - distill_llm: FAKE chat fn; returns clamped fields + next_context.
  - Security: planted secret (mk_agent_/JWT) in a turn NEVER appears in the
    prompt the fake chat receives.
  - Garbage/empty JSON -> raises ValueError (caller falls back to deterministic).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from mintmory.core.history.distill import (
    ChatFn,
    distill_llm,
    distill_segment_deterministic,
)
from mintmory.core.history.models import (
    KINDS,
    NormalizedTurn,
    SessionSummary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_summary(**kwargs: Any) -> SessionSummary:
    defaults: dict[str, Any] = {
        "session_id": "sess-001",
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
    return SessionSummary(**defaults)


def _make_turns(
    user_text: str = "Fix the bug in parser",
    assistant_text: str = "Done, patched the parser.",
) -> list[NormalizedTurn]:
    return [
        NormalizedTurn(seq=0, ts=None, role="user", text=user_text),
        NormalizedTurn(seq=1, ts=None, role="assistant", text=assistant_text),
    ]


def _fake_chat(response_json: dict[str, Any]) -> ChatFn:
    """Return a ChatFn that always returns the given JSON dict as a string."""
    captured: list[str] = []

    def _chat(prompt: str) -> str:
        captured.append(prompt)
        return json.dumps(response_json)

    _chat.captured = captured  # type: ignore[attr-defined]
    return _chat


# ---------------------------------------------------------------------------
# distill_segment_deterministic
# ---------------------------------------------------------------------------


class TestDistillSegmentDeterministic:
    def test_title_from_first_user_turn(self) -> None:
        s = _make_summary()
        turns = _make_turns(user_text="Add dark mode toggle")
        result = distill_segment_deterministic(s, turns)
        assert result.title == "Add dark mode toggle"

    def test_title_max_80_chars(self) -> None:
        long_text = "A" * 200
        s = _make_summary()
        turns = _make_turns(user_text=long_text)
        result = distill_segment_deterministic(s, turns)
        assert len(result.title) <= 80

    def test_summary_text_max_600_chars(self) -> None:
        s = _make_summary()
        turns = _make_turns(user_text="X" * 500, assistant_text="Y" * 500)
        result = distill_segment_deterministic(s, turns)
        assert len(result.summary_text) <= 600

    def test_kind_in_kinds(self) -> None:
        s = _make_summary()
        turns = _make_turns(user_text="Fix the login bug")
        result = distill_segment_deterministic(s, turns)
        assert result.kind in KINDS

    def test_distiller_version_is_1(self) -> None:
        s = _make_summary()
        turns = _make_turns()
        result = distill_segment_deterministic(s, turns)
        assert result.distiller_version == 1

    def test_pure_same_input_same_output(self) -> None:
        s = _make_summary()
        turns = _make_turns()
        r1 = distill_segment_deterministic(s, turns)
        r2 = distill_segment_deterministic(s, turns)
        assert r1.title == r2.title
        assert r1.summary_text == r2.summary_text
        assert r1.kind == r2.kind

    def test_empty_slice_does_not_crash(self) -> None:
        s = _make_summary()
        result = distill_segment_deterministic(s, [])
        assert isinstance(result.title, str)
        assert isinstance(result.summary_text, str)

    def test_returns_new_instance(self) -> None:
        s = _make_summary()
        turns = _make_turns()
        result = distill_segment_deterministic(s, turns)
        assert result is not s

    def test_kind_fix_keyword(self) -> None:
        s = _make_summary()
        turns = _make_turns(user_text="Fix the null pointer error")
        result = distill_segment_deterministic(s, turns)
        assert result.kind == "fix"

    def test_kind_feature_keyword(self) -> None:
        s = _make_summary()
        turns = _make_turns(user_text="Add new authentication feature")
        result = distill_segment_deterministic(s, turns)
        assert result.kind == "feature"


# ---------------------------------------------------------------------------
# distill_llm — happy path with FAKE chat
# ---------------------------------------------------------------------------


class TestDistillLlmHappyPath:
    def _valid_response(self) -> dict[str, Any]:
        return {
            "title": "Fix the auth bug",
            "kind": "fix",
            "summary": "Patched the login flow. Tests updated.",
            "outcome": "done",
            "next_context": "Auth module is stable now.",
        }

    def test_returns_filled_summary_and_next_context(self) -> None:
        s = _make_summary()
        turns = _make_turns()
        chat = _fake_chat(self._valid_response())
        filled, next_ctx = distill_llm(s, turns, chat)
        assert filled.title == "Fix the auth bug"
        assert filled.kind == "fix"
        assert filled.summary_text == "Patched the login flow. Tests updated."
        assert filled.outcome == "done"
        assert next_ctx == "Auth module is stable now."

    def test_distiller_version_is_2(self) -> None:
        s = _make_summary()
        turns = _make_turns()
        chat = _fake_chat(self._valid_response())
        filled, _ = distill_llm(s, turns, chat)
        assert filled.distiller_version == 2

    def test_title_clamped_to_80(self) -> None:
        resp = {**self._valid_response(), "title": "A" * 200}
        chat = _fake_chat(resp)
        filled, _ = distill_llm(_make_summary(), _make_turns(), chat)
        assert len(filled.title) <= 80

    def test_summary_clamped_to_600(self) -> None:
        resp = {**self._valid_response(), "summary": "X" * 1000}
        chat = _fake_chat(resp)
        filled, _ = distill_llm(_make_summary(), _make_turns(), chat)
        assert len(filled.summary_text) <= 600

    def test_outcome_clamped_to_120(self) -> None:
        resp = {**self._valid_response(), "outcome": "O" * 200}
        chat = _fake_chat(resp)
        filled, _ = distill_llm(_make_summary(), _make_turns(), chat)
        assert len(filled.outcome) <= 120

    def test_next_context_clamped_to_300(self) -> None:
        resp = {**self._valid_response(), "next_context": "N" * 500}
        chat = _fake_chat(resp)
        _, next_ctx = distill_llm(_make_summary(), _make_turns(), chat)
        assert len(next_ctx) <= 300

    def test_invalid_kind_becomes_investigation(self) -> None:
        resp = {**self._valid_response(), "kind": "unknown_kind"}
        chat = _fake_chat(resp)
        filled, _ = distill_llm(_make_summary(), _make_turns(), chat)
        assert filled.kind == "investigation"

    def test_kind_all_valid_values_accepted(self) -> None:
        for k in KINDS:
            resp = {**self._valid_response(), "kind": k}
            chat = _fake_chat(resp)
            filled, _ = distill_llm(_make_summary(), _make_turns(), chat)
            assert filled.kind == k

    def test_prev_context_passed_through(self) -> None:
        """prev_context is included in the prompt (after redaction)."""
        resp = self._valid_response()
        chat = _fake_chat(resp)
        turns = _make_turns()
        _, _ = distill_llm(_make_summary(), turns, chat, prev_context="Previous work done.")
        captured_prompt = chat.captured[0]  # type: ignore[attr-defined]
        assert "Previous work done." in captured_prompt


# ---------------------------------------------------------------------------
# SECURITY: planted secrets must NEVER reach the LLM
# ---------------------------------------------------------------------------


class TestRedactionBeforeLLM:
    """HARD SECURITY BOUNDARY: distill_llm MUST redact every turn text and
    prev_context before building the prompt.  No live secret reaches the LLM.
    """

    def _check_no_secret_in_prompt(
        self,
        turns: list[NormalizedTurn],
        prev_context: str = "",
        *,
        secret: str,
    ) -> None:
        """Assert the captured prompt does NOT contain `secret`."""
        resp = {
            "title": "Safe title",
            "kind": "investigation",
            "summary": "Some summary.",
            "outcome": "done",
            "next_context": "",
        }
        chat = _fake_chat(resp)
        distill_llm(_make_summary(), turns, chat, prev_context=prev_context)
        captured_prompt = chat.captured[0]  # type: ignore[attr-defined]
        assert secret not in captured_prompt, f"Secret {secret!r} leaked into the LLM prompt!"

    def test_mk_agent_key_in_turn_is_redacted(self) -> None:
        secret = "mk_agent_ABCDEFGHIJ1234567890KLMNOPQRST"
        turns = [
            NormalizedTurn(seq=0, ts=None, role="user", text=f"Here is my key: {secret}"),
        ]
        self._check_no_secret_in_prompt(turns, secret=secret)

    def test_jwt_in_turn_is_redacted(self) -> None:
        # A syntactically valid JWT (base64url segments).
        secret = "eyJhbGciOiJFZERTQSJ9.eyJzdWIiOiJ0ZXN0In0.AAABBBCCC111222DDD"
        turns = [
            NormalizedTurn(seq=0, ts=None, role="assistant", text=f"Token: {secret}"),
        ]
        self._check_no_secret_in_prompt(turns, secret=secret)

    def test_secret_in_prev_context_is_redacted(self) -> None:
        secret = "mk_agent_ZZZZZZZZZZZZZZZZZZZZZZZZZ"
        turns = _make_turns()
        self._check_no_secret_in_prompt(
            turns,
            prev_context=f"The previous token was {secret}.",
            secret=secret,
        )

    def test_multiple_secrets_all_redacted(self) -> None:
        secret_a = "mk_agent_AAAAAAAAAAAAAAAAAAAAAAA"
        secret_b = "eyJhbGciOiJFZERTQSJ9.eyJ4IjoieSJ9.XXXXXXXXXXXXXXXXXXX"
        turns = [
            NormalizedTurn(seq=0, ts=None, role="user", text=f"key={secret_a} token={secret_b}"),
        ]
        chat_fn = _fake_chat(
            {
                "title": "t",
                "kind": "fix",
                "summary": "s",
                "outcome": "done",
                "next_context": "",
            }
        )
        distill_llm(_make_summary(), turns, chat_fn)
        prompt = chat_fn.captured[0]  # type: ignore[attr-defined]
        assert secret_a not in prompt
        assert secret_b not in prompt
        # Placeholder must appear.
        assert "[REDACTED:" in prompt

    def test_next_context_with_secret_is_redacted(self) -> None:
        """next_context returned by the LLM with a secret is also redacted."""
        secret = "mk_agent_SSSSSSSSSSSSSSSSSSSSSSSSS"
        resp = {
            "title": "t",
            "kind": "fix",
            "summary": "s",
            "outcome": "done",
            "next_context": f"Remember the key: {secret}",
        }
        chat = _fake_chat(resp)
        _, next_ctx = distill_llm(_make_summary(), _make_turns(), chat)
        assert secret not in next_ctx
        assert "[REDACTED:" in next_ctx


# ---------------------------------------------------------------------------
# Garbage / empty JSON -> raises ValueError
# ---------------------------------------------------------------------------


class TestDistillLlmGarbageInput:
    def _chat_returning(self, text: str) -> ChatFn:
        def _c(prompt: str) -> str:
            return text

        return _c

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="empty/garbage"):
            distill_llm(_make_summary(), _make_turns(), self._chat_returning(""))

    def test_non_json_raises(self) -> None:
        with pytest.raises(ValueError):
            distill_llm(
                _make_summary(), _make_turns(), self._chat_returning("I don't know what to say.")
            )

    def test_json_without_title_and_summary_raises(self) -> None:
        garbage = json.dumps({"kind": "fix", "outcome": "done"})
        with pytest.raises(ValueError):
            distill_llm(_make_summary(), _make_turns(), self._chat_returning(garbage))

    def test_empty_json_object_raises(self) -> None:
        with pytest.raises(ValueError):
            distill_llm(_make_summary(), _make_turns(), self._chat_returning("{}"))

    def test_partial_json_with_title_is_ok(self) -> None:
        """A response with just a title (no summary) should succeed — title alone is enough."""
        resp = json.dumps(
            {
                "title": "Fix login bug",
                "kind": "fix",
                "summary": "",
                "outcome": "",
                "next_context": "",
            }
        )
        # Empty summary but title present -> should NOT raise.
        filled, _ = distill_llm(_make_summary(), _make_turns(), self._chat_returning(resp))
        assert filled.title == "Fix login bug"

    def test_think_block_stripped_before_json_parse(self) -> None:
        """<think>...</think> blocks are stripped before JSON extraction."""
        resp = "<think>Let me summarise this.</think>\n" + json.dumps(
            {
                "title": "Refactor auth module",
                "kind": "refactor",
                "summary": "Moved auth logic into a separate module.",
                "outcome": "done",
                "next_context": "Auth module refactored.",
            }
        )
        filled, next_ctx = distill_llm(_make_summary(), _make_turns(), self._chat_returning(resp))
        assert filled.title == "Refactor auth module"
        assert filled.kind == "refactor"


# ---------------------------------------------------------------------------
# distill_llm preserves non-LLM summary fields
# ---------------------------------------------------------------------------


class TestDistillLlmPreservesFields:
    def test_session_metadata_preserved(self) -> None:
        """Fields not touched by distill_llm are preserved unchanged."""
        s = _make_summary(session_id="my-session", repo="special-repo", branch="dev")
        resp = {
            "title": "Fix thing",
            "kind": "fix",
            "summary": "Fixed it.",
            "outcome": "done",
            "next_context": "",
        }
        filled, _ = distill_llm(s, _make_turns(), _fake_chat(resp))
        assert filled.session_id == "my-session"
        assert filled.repo == "special-repo"
        assert filled.branch == "dev"


# ---------------------------------------------------------------------------
# MM-30: Prompt-cap tests (bound-llm-distiller)
# ---------------------------------------------------------------------------


class TestPromptCap:
    """Design §5: A huge segment yields a bounded, ask-preserving prompt."""

    def _valid_response(self) -> dict[str, Any]:
        return {
            "title": "Fix the bug",
            "kind": "fix",
            "summary": "Patched it.",
            "outcome": "done",
            "next_context": "",
        }

    def _make_huge_turns(
        self,
        n_user: int = 4,
        huge_char_count: int = 200_000,
        secret: str = "",
    ) -> list[NormalizedTurn]:
        """Build turns with one 200k-char user turn and several long turns."""
        turns: list[NormalizedTurn] = []
        seq = 0
        # First user turn: the "ask" — contains the secret to verify redaction
        suffix_len = huge_char_count - 100 - len(secret) - 2
        first_text = ("A" * 100) + (f" {secret} " if secret else "") + ("B" * suffix_len)
        turns.append(NormalizedTurn(seq=seq, ts=None, role="user", text=first_text))
        seq += 1
        # Several long assistant turns
        for i in range(3):
            turns.append(
                NormalizedTurn(
                    seq=seq,
                    ts=None,
                    role="assistant",
                    text=f"Assistant response {i}: " + "X" * 5000,
                )
            )
            seq += 1
        # More user turns
        for i in range(n_user - 1):
            turns.append(
                NormalizedTurn(
                    seq=seq,
                    ts=None,
                    role="user",
                    text=f"User follow-up {i}: " + "Y" * 3000,
                )
            )
            seq += 1
            turns.append(
                NormalizedTurn(seq=seq, ts=None, role="assistant", text=f"Reply {i}: " + "Z" * 2000)
            )
            seq += 1
        # Last turn
        turns.append(NormalizedTurn(seq=seq, ts=None, role="assistant", text="Final outcome: done"))
        return turns

    def test_prompt_bounded_by_max_prompt_chars(self) -> None:
        """A 200k-char turn -> prompt transcript length <= max_prompt_chars + small overhead."""
        max_turn = 500
        max_prompt = 2000
        turns = self._make_huge_turns(huge_char_count=200_000)
        captured_prompts: list[str] = []

        def capturing_chat(prompt: str) -> str:
            captured_prompts.append(prompt)
            return json.dumps(self._valid_response())

        distill_llm(
            _make_summary(),
            turns,
            capturing_chat,
            max_turn_chars=max_turn,
            max_prompt_chars=max_prompt,
        )

        assert captured_prompts, "chat function was never called"
        prompt = captured_prompts[0]
        # The transcript must be bounded; allow small overhead for the prompt template
        # and elision markers. We verify the prompt length is reasonable (not 200k chars).
        marker_overhead = 200  # for elision markers and prompt template boilerplate
        assert len(prompt) <= max_prompt + marker_overhead + 2000, (
            f"Prompt length {len(prompt)} exceeds max_prompt_chars={max_prompt} by too much"
        )

    def test_every_user_turn_present_in_prompt(self) -> None:
        """Every user turn's (truncated) text must appear in the bounded prompt."""
        max_turn = 200
        max_prompt = 3000
        # Create turns where each user turn has a unique marker
        turns: list[NormalizedTurn] = []
        user_markers = [f"USERMARKER{i:03d}" for i in range(4)]
        for i, marker in enumerate(user_markers):
            turns.append(
                NormalizedTurn(
                    seq=len(turns), ts=None, role="user", text=marker + " " + "A" * 10000
                )
            )
            turns.append(
                NormalizedTurn(
                    seq=len(turns), ts=None, role="assistant", text=f"Reply {i}: " + "X" * 10000
                )
            )

        captured_prompts: list[str] = []

        def capturing_chat(prompt: str) -> str:
            captured_prompts.append(prompt)
            return json.dumps(self._valid_response())

        distill_llm(
            _make_summary(),
            turns,
            capturing_chat,
            max_turn_chars=max_turn,
            max_prompt_chars=max_prompt,
        )

        assert captured_prompts
        prompt = captured_prompts[0]
        # Each user turn's unique marker must be visible in the prompt.
        for marker in user_markers:
            assert marker in prompt, f"User turn marker {marker!r} missing from prompt"

    def test_first_ask_and_last_turn_survive(self) -> None:
        """The first user turn (ask) and last turn always survive elision."""
        max_turn = 100
        max_prompt = 1000
        first_ask_marker = "FIRSTASKMARKER"
        last_turn_marker = "LASTTURNMARKER"
        turns = [
            NormalizedTurn(seq=0, ts=None, role="user", text=first_ask_marker + " " + "A" * 5000),
            NormalizedTurn(seq=1, ts=None, role="assistant", text="Middle 1: " + "B" * 5000),
            NormalizedTurn(seq=2, ts=None, role="assistant", text="Middle 2: " + "C" * 5000),
            NormalizedTurn(
                seq=3, ts=None, role="assistant", text=last_turn_marker + " " + "D" * 5000
            ),
        ]

        captured_prompts: list[str] = []

        def capturing_chat(prompt: str) -> str:
            captured_prompts.append(prompt)
            return json.dumps(self._valid_response())

        distill_llm(
            _make_summary(),
            turns,
            capturing_chat,
            max_turn_chars=max_turn,
            max_prompt_chars=max_prompt,
        )

        assert captured_prompts
        prompt = captured_prompts[0]
        assert first_ask_marker in prompt, "First user ask must survive elision"
        assert last_turn_marker in prompt, "Last turn must survive elision"

    def test_secret_not_in_prompt_after_redaction_and_truncation(self) -> None:
        """Planted secret is redacted BEFORE truncation — must never appear in prompt."""
        secret = "mk_agent_SECRETSECRETSECRETSECRETXYZ"
        max_turn = 500
        max_prompt = 2000
        turns = self._make_huge_turns(huge_char_count=200_000, secret=secret)

        captured_prompts: list[str] = []

        def capturing_chat(prompt: str) -> str:
            captured_prompts.append(prompt)
            return json.dumps(self._valid_response())

        distill_llm(
            _make_summary(),
            turns,
            capturing_chat,
            max_turn_chars=max_turn,
            max_prompt_chars=max_prompt,
        )

        assert captured_prompts
        prompt = captured_prompts[0]
        assert secret not in prompt, f"Secret {secret!r} leaked into the bounded prompt!"

    def test_per_turn_truncation(self) -> None:
        """Each turn's text is individually capped to max_turn_chars."""
        max_turn = 100
        max_prompt = 50000  # large enough so no total elision needed
        long_text = "X" * 10000
        turns = [
            NormalizedTurn(seq=0, ts=None, role="user", text=long_text),
            NormalizedTurn(seq=1, ts=None, role="assistant", text=long_text),
        ]

        captured_prompts: list[str] = []

        def capturing_chat(prompt: str) -> str:
            captured_prompts.append(prompt)
            return json.dumps(self._valid_response())

        distill_llm(
            _make_summary(),
            turns,
            capturing_chat,
            max_turn_chars=max_turn,
            max_prompt_chars=max_prompt,
        )

        assert captured_prompts
        prompt = captured_prompts[0]
        # The raw long text must not appear verbatim (it's been truncated).
        assert long_text not in prompt
        # But truncation marker must appear.
        assert "[truncated]" in prompt

    def test_prev_context_capped_to_max_turn_chars(self) -> None:
        """prev_context is also capped to max_turn_chars."""
        max_turn = 50
        max_prompt = 10000
        long_prev = "P" * 5000

        captured_prompts: list[str] = []

        def capturing_chat(prompt: str) -> str:
            captured_prompts.append(prompt)
            return json.dumps(self._valid_response())

        distill_llm(
            _make_summary(),
            _make_turns(),
            capturing_chat,
            prev_context=long_prev,
            max_turn_chars=max_turn,
            max_prompt_chars=max_prompt,
        )

        assert captured_prompts
        prompt = captured_prompts[0]
        # The full 5000-char prev_context must not appear.
        assert long_prev not in prompt
        assert "[truncated]" in prompt


def test_prompt_bounded_when_user_turns_alone_exceed_budget() -> None:
    """MM-30 review: when user turns ALONE exceed max_prompt_chars, boundedness still
    holds and the first ask + last turn survive (middle user turns may be elided)."""
    valid = {"title": "t", "kind": "fix", "summary": "s", "outcome": "done", "next_context": ""}
    chat = _fake_chat(valid)
    s = _make_summary()
    # 60 user turns x 5000 chars each => ~300k chars of user text alone, max_prompt_chars=12000.
    turns = [
        NormalizedTurn(seq=i, ts=None, role="user", text=f"ASK-{i} " + ("x" * 5000))
        for i in range(60)
    ]
    distill_llm(s, turns, chat, max_turn_chars=2000, max_prompt_chars=12000)
    prompt = chat.captured[-1]  # type: ignore[attr-defined]
    # The transcript portion must be bounded (allow generous template overhead).
    assert len(prompt) <= 12000 + 4000, f"prompt not bounded: {len(prompt)}"
    # First ask and last turn survive.
    assert "ASK-0 " in prompt
    assert "ASK-59 " in prompt
    # It actually elided something.
    assert "elided" in prompt


def test_no_secret_survives_truncation() -> None:
    """A secret in a turn that gets TRUNCATED must still be redacted (redact-before-truncate)."""
    valid = {"title": "t", "kind": "fix", "summary": "s", "outcome": "done", "next_context": ""}
    chat = _fake_chat(valid)
    s = _make_summary()
    secret = "mk_agent_" + "A" * 40
    turns = [
        NormalizedTurn(seq=0, ts=None, role="user", text="do it " + secret + " " + ("y" * 6000)),
        NormalizedTurn(seq=1, ts=None, role="assistant", text="ok"),
    ]
    distill_llm(s, turns, chat, max_turn_chars=500, max_prompt_chars=12000)
    prompt = chat.captured[-1]  # type: ignore[attr-defined]
    assert secret not in prompt
    assert "[REDACTED:mk_agent]" in prompt
