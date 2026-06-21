"""
Tests for mintmory.core.llm.build_history_distiller and _is_local_base_url.

Design.md §6 / spec.md contract:
  build_history_distiller returns None when:
    - llm.provider is NONE (offline default), OR
    - llm.base_url is non-local AND seg.allow_cloud_llm is False.

  Returns a callable when:
    - provider is not NONE AND (base_url is local OR allow_cloud_llm is True).

  _is_local_base_url(url) returns True for localhost / 127.x.x.x / ::1 / [::1].

All tests are OFFLINE — no network, no real LLM.
"""

from __future__ import annotations

import pytest
from mintmory.core.config import LLMProvider, LLMSettings, SegmentSettings
from mintmory.core.llm import _is_local_base_url, build_history_distiller

# ---------------------------------------------------------------------------
# _is_local_base_url
# ---------------------------------------------------------------------------


class TestIsLocalBaseUrl:
    def test_localhost_is_local(self) -> None:
        assert _is_local_base_url("http://localhost:11434/v1") is True

    def test_localhost_uppercase_is_local(self) -> None:
        # hostnames are case-insensitive
        assert _is_local_base_url("http://LOCALHOST:11434/v1") is True

    def test_127_0_0_1_is_local(self) -> None:
        assert _is_local_base_url("http://127.0.0.1:8789/v1") is True

    def test_127_x_x_x_is_local(self) -> None:
        assert _is_local_base_url("http://127.1.2.3/v1") is True

    def test_ipv6_loopback_bracket_is_local(self) -> None:
        assert _is_local_base_url("http://[::1]:11434/v1") is True

    def test_remote_openai_is_not_local(self) -> None:
        assert _is_local_base_url("https://api.openai.com/v1") is False

    def test_remote_portkey_is_not_local(self) -> None:
        assert _is_local_base_url("http://portkey.mycompany.com:8789/v1") is False

    def test_192_168_is_not_local(self) -> None:
        # Private but not loopback.
        assert _is_local_base_url("http://192.168.1.1/v1") is False

    def test_10_x_x_x_is_not_local(self) -> None:
        assert _is_local_base_url("http://10.0.0.1/v1") is False


# ---------------------------------------------------------------------------
# build_history_distiller — None cases
# ---------------------------------------------------------------------------


class TestBuildHistoryDistillerNone:
    def _seg(self, allow_cloud_llm: bool = False) -> SegmentSettings:
        return SegmentSettings(allow_cloud_llm=allow_cloud_llm)

    def test_provider_none_returns_none(self) -> None:
        """provider=NONE always -> None regardless of base_url."""
        llm = LLMSettings(provider=LLMProvider.NONE)
        result = build_history_distiller(llm, self._seg())
        assert result is None

    def test_provider_none_with_local_url_still_none(self) -> None:
        """Even with a local URL, provider=NONE -> None."""
        llm = LLMSettings(
            provider=LLMProvider.NONE,
            base_url="http://localhost:11434/v1",
        )
        result = build_history_distiller(llm, self._seg())
        assert result is None

    def test_non_local_url_without_allow_cloud_returns_none(self) -> None:
        """Non-local URL + allow_cloud_llm=False -> None (egress gate)."""
        llm = LLMSettings(
            provider=LLMProvider.OPENAI,
            base_url="https://api.openai.com/v1",
        )
        result = build_history_distiller(llm, self._seg(allow_cloud_llm=False))
        assert result is None

    def test_portkey_gateway_without_allow_cloud_returns_none(self) -> None:
        """Portkey at non-localhost -> None without allow_cloud_llm."""
        llm = LLMSettings(
            provider=LLMProvider.OPENAI,
            base_url="http://portkey.example.com:8789/v1",
        )
        result = build_history_distiller(llm, self._seg(allow_cloud_llm=False))
        assert result is None


# ---------------------------------------------------------------------------
# build_history_distiller — non-None (callable) cases
# ---------------------------------------------------------------------------


class TestBuildHistoryDistillerCallable:
    def _seg(self, allow_cloud_llm: bool = False) -> SegmentSettings:
        return SegmentSettings(allow_cloud_llm=allow_cloud_llm)

    def test_local_url_with_ollama_provider_is_callable(self) -> None:
        """Local base_url + non-NONE provider -> callable."""
        llm = LLMSettings(
            provider=LLMProvider.OLLAMA,
            base_url="http://localhost:11434/v1",
        )
        result = build_history_distiller(llm, self._seg())
        assert result is not None
        assert callable(result)

    def test_127_url_with_provider_is_callable(self) -> None:
        llm = LLMSettings(
            provider=LLMProvider.OLLAMA,
            base_url="http://127.0.0.1:8789/v1",
        )
        result = build_history_distiller(llm, self._seg())
        assert result is not None
        assert callable(result)

    def test_non_local_url_with_allow_cloud_is_callable(self) -> None:
        """Non-local URL is allowed when seg.allow_cloud_llm=True."""
        llm = LLMSettings(
            provider=LLMProvider.OPENAI,
            base_url="https://api.openai.com/v1",
        )
        result = build_history_distiller(llm, self._seg(allow_cloud_llm=True))
        assert result is not None
        assert callable(result)

    def test_callable_signature_accepts_summary_turns_prev_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The returned callable accepts (summary, seg_turns, prev_context='')."""
        import json

        from mintmory.core.history.models import NormalizedTurn, SessionSummary

        llm = LLMSettings(
            provider=LLMProvider.OLLAMA,
            base_url="http://localhost:11434/v1",
        )
        result = build_history_distiller(llm, self._seg())
        assert result is not None

        # Patch urlopen so the LLM call doesn't go to the network.

        fake_reply = {
            "title": "Fix the parser",
            "kind": "fix",
            "summary": "Fixed parser edge case.",
            "outcome": "done",
            "next_context": "",
        }
        body = {
            "choices": [{"message": {"content": json.dumps(fake_reply)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        class _FakeResp:
            def read(self) -> bytes:
                return json.dumps(body).encode()

            def __enter__(self) -> _FakeResp:
                return self

            def __exit__(self, *a: object) -> None:
                pass

        monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _FakeResp())

        summary = SessionSummary(
            session_id="s1",
            agent="claude_code",
            repo="repo",
            repo_path="/r",
            branch="main",
            ts_start="2024-01-01T10:00:00Z",
            ts_end="2024-01-01T10:30:00Z",
            turn_count=2,
        )
        turns = [NormalizedTurn(seq=0, ts=None, role="user", text="Fix parser")]

        filled, next_ctx = result(summary, turns, "")
        assert filled.title == "Fix the parser"
        assert filled.distiller_version == 2
        assert isinstance(next_ctx, str)
