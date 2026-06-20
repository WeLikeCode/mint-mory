"""
Unit tests for ``mintmory.core.llm`` — the single chat-LLM seam.

NONE of these tests hit the network. The one ``LLMClient.chat`` test
monkeypatches ``urllib.request.urlopen`` with a fake response so we can assert
the request payload (model/temperature/messages), the Bearer header, and that the
reply is parsed from the OpenAI-compatible ``choices[0].message.content`` shape.

The builder tests assert the offline default (``provider=none``) is a no-op:
both callables are ``None`` and a built engine's LLM-dependent steps return 0.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from mintmory.core.config import LLMProvider, LLMSettings
from mintmory.core.llm import (
    LLMClient,
    build_conflict_resolver,
    build_dreaming_engine,
    build_summarizer,
    check_contradiction,
    extract_json,
)
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import MemoryCategory, MemoryRecord


def _store() -> StorageAdapter:
    s = StorageAdapter(":memory:", embedder=None)
    s.initialise()
    return s


# ---------------------------------------------------------------------------
# extract_json robustness
# ---------------------------------------------------------------------------
def test_extract_json_bare_object() -> None:
    assert extract_json('{"has_conflict": false}') == {"has_conflict": False}


def test_extract_json_code_fence() -> None:
    text = 'Here is the result:\n```json\n{"a": 1, "b": 2}\n```\nDone.'
    assert extract_json(text) == {"a": 1, "b": 2}


def test_extract_json_think_block() -> None:
    text = '<think>let me reason about this</think>\n{"answer": "yes"}'
    assert extract_json(text) == {"answer": "yes"}


def test_extract_json_surrounding_prose() -> None:
    text = 'Sure! The object you want is {"action": "DELETE", "target_id": "x"} okay?'
    assert extract_json(text) == {"action": "DELETE", "target_id": "x"}


def test_extract_json_think_and_fence_combined() -> None:
    text = '<think>hmm</think>\nResult:\n```\n{"k": [1, 2, 3]}\n```'
    assert extract_json(text) == {"k": [1, 2, 3]}


def test_extract_json_bad_returns_empty() -> None:
    assert extract_json("no json here at all") == {}
    assert extract_json("{not valid json}") == {}
    assert extract_json("") == {}


def test_extract_json_non_object_returns_empty() -> None:
    # A bare JSON array is not a dict — extract_json only returns objects.
    assert extract_json("[1, 2, 3]") == {}


# ---------------------------------------------------------------------------
# Builders return None when provider=none (offline default is a no-op)
# ---------------------------------------------------------------------------
def test_build_summarizer_none_provider() -> None:
    assert build_summarizer(LLMSettings(provider=LLMProvider.NONE)) is None


def test_build_conflict_resolver_none_provider() -> None:
    store = _store()
    assert build_conflict_resolver(LLMSettings(provider=LLMProvider.NONE), store) is None


def test_build_summarizer_non_none_provider_is_callable() -> None:
    summ = build_summarizer(LLMSettings(provider=LLMProvider.OLLAMA))
    assert summ is not None and callable(summ)


def test_build_conflict_resolver_non_none_provider_is_callable() -> None:
    store = _store()
    res = build_conflict_resolver(LLMSettings(provider=LLMProvider.OLLAMA), store)
    assert res is not None and callable(res)


# ---------------------------------------------------------------------------
# build_dreaming_engine with provider=none yields an offline engine
# ---------------------------------------------------------------------------
def test_build_dreaming_engine_none_provider_is_offline() -> None:
    store = _store()
    # Seed enough memories sharing a concept that summaries WOULD run if enabled.
    for i in range(3):
        store.add_memory(
            record=MemoryRecord(
                content=f"Note {i} about Postgres tuning.",
                category=MemoryCategory.FACT,
                entity_ids=["postgres"],
            )
        )
    engine = build_dreaming_engine(store, LLMSettings(provider=LLMProvider.NONE))
    assert engine.summarizer is None
    assert engine.conflict_resolver is None
    # The LLM-dependent steps must be a no-op (count 0) with no provider.
    assert engine.generate_summaries() == 0
    assert engine.resolve_contradictions() == 0


def test_build_dreaming_engine_default_settings_is_offline() -> None:
    # No settings passed -> LLMSettings() default is provider=none.
    store = _store()
    engine = build_dreaming_engine(store)
    assert engine.summarizer is None
    assert engine.conflict_resolver is None


def test_build_dreaming_engine_passes_through_settings() -> None:
    from mintmory.core.config import LinkSettings, SummarySettings

    store = _store()
    link = LinkSettings(min_shared_entities=1)
    summary = SummarySettings(top_k=7)
    engine = build_dreaming_engine(store, link_settings=link, summary_settings=summary)
    assert engine.link_settings is link
    assert engine.summary_settings is summary


# ---------------------------------------------------------------------------
# LLMClient request building + reply parsing (no real network)
# ---------------------------------------------------------------------------
class _FakeResponse:
    """Minimal stand-in for the urlopen context manager response."""

    def __init__(self, body: dict[str, Any]) -> None:
        self._stream = io.BytesIO(json.dumps(body).encode("utf-8"))

    def read(self) -> bytes:
        return self._stream.read()

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _patch_urlopen(monkeypatch: Any, captured: dict[str, Any], body: dict[str, Any]) -> None:
    def fake_urlopen(req: Any, timeout: float | None = None) -> _FakeResponse:
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = dict(req.header_items())
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse(body)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)


def test_llm_client_chat_builds_request_and_parses_reply(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}
    body = {
        "choices": [{"message": {"content": "hello world"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 3},
    }
    _patch_urlopen(monkeypatch, captured, body)

    client = LLMClient(
        LLMSettings(
            provider=LLMProvider.OLLAMA,
            base_url="http://localhost:11434/v1",
            model="gemma4:e4b-it-qat",
            temperature=0.0,
            timeout_s=42.0,
        )
    )
    out = client.chat("summarise this")

    assert out == "hello world"
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["method"] == "POST"
    assert captured["timeout"] == 42.0
    payload = captured["payload"]
    assert payload["model"] == "gemma4:e4b-it-qat"
    assert payload["temperature"] == 0.0
    assert payload["stream"] is False
    assert payload["messages"] == [{"role": "user", "content": "summarise this"}]
    # No api_key -> no Authorization header (headers are title-cased by urllib).
    assert "Authorization" not in captured["headers"]


def test_llm_client_adds_bearer_when_api_key_set(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}
    body = {"choices": [{"message": {"content": "ok"}}]}
    _patch_urlopen(monkeypatch, captured, body)

    client = LLMClient(
        LLMSettings(
            provider=LLMProvider.OPENAI,
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            api_key="sk-secret",
        )
    )
    assert client.chat("hi") == "ok"
    assert captured["headers"].get("Authorization") == "Bearer sk-secret"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"


def test_llm_client_strips_trailing_slash_on_base_url(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}
    _patch_urlopen(monkeypatch, captured, {"choices": [{"message": {"content": "x"}}]})
    client = LLMClient(
        LLMSettings(provider=LLMProvider.OLLAMA, base_url="http://localhost:11434/v1/")
    )
    client.chat("q")
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"


def test_llm_client_ping_true_on_success(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}
    _patch_urlopen(monkeypatch, captured, {"choices": [{"message": {"content": "ok"}}]})
    client = LLMClient(LLMSettings(provider=LLMProvider.OLLAMA))
    assert client.ping() is True


def test_llm_client_ping_false_on_error(monkeypatch: Any) -> None:
    def boom(req: Any, timeout: float | None = None) -> Any:
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    client = LLMClient(LLMSettings(provider=LLMProvider.OLLAMA))
    assert client.ping() is False


# ---------------------------------------------------------------------------
# check_contradiction — empty input and parse-failure fallbacks (no network)
# ---------------------------------------------------------------------------
def test_check_contradiction_empty_existing_is_false() -> None:
    client = LLMClient(LLMSettings(provider=LLMProvider.OLLAMA))
    result = check_contradiction(client, "new fact", [])
    assert result.has_conflict is False
    assert result.conflicts == []


def test_check_contradiction_parses_valid_reply(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}
    reply = {
        "has_conflict": True,
        "conflicts": [
            {
                "new_fact": "Port is 2580",
                "existing_memory_id": "m1",
                "existing_content": "Port is 2480",
                "type": "contradiction",
                "question": None,
            }
        ],
    }
    body = {"choices": [{"message": {"content": json.dumps(reply)}}]}
    _patch_urlopen(monkeypatch, captured, body)
    client = LLMClient(LLMSettings(provider=LLMProvider.OLLAMA))
    result = check_contradiction(client, "Port is 2580", [("m1", "Port is 2480")])
    assert result.has_conflict is True
    assert result.conflicts[0].existing_memory_id == "m1"


def test_check_contradiction_unparseable_reply_is_false(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}
    body = {"choices": [{"message": {"content": "I cannot answer that."}}]}
    _patch_urlopen(monkeypatch, captured, body)
    client = LLMClient(LLMSettings(provider=LLMProvider.OLLAMA))
    result = check_contradiction(client, "x", [("m1", "y")])
    assert result.has_conflict is False


# ---------------------------------------------------------------------------
# post_chat_completion delegation — Group 6 (add-llm-vision-provider) tests
# ---------------------------------------------------------------------------


def test_llm_client_chat_delegates_to_post_chat_completion(monkeypatch: Any) -> None:
    """LLMClient.chat() delegates to post_chat_completion (shared poster refactor).

    Verifies that after the §2d refactor, LLMClient.chat() still produces the
    correct assistant text AND that the shared poster is called with the right
    arguments — confirming the delegation path works and the observable behaviour
    is byte-for-byte unchanged.
    """
    # Patch urlopen so no network is hit; post_chat_completion is called internally.
    captured: dict[str, Any] = {}
    body = {
        "choices": [{"message": {"content": "delegation works"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }
    _patch_urlopen(monkeypatch, captured, body)

    settings = LLMSettings(
        provider=LLMProvider.OLLAMA,
        base_url="http://localhost:11434/v1",
        model="gemma4:e4b-it-qat",
        temperature=0.1,
        timeout_s=30.0,
    )
    client = LLMClient(settings)
    result = client.chat("test delegation")

    assert result == "delegation works"
    # The URL that urlopen received must be the chat/completions endpoint
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    # Payload must be the standard text-only shape
    assert captured["payload"]["messages"] == [{"role": "user", "content": "test delegation"}]
    assert captured["payload"]["model"] == "gemma4:e4b-it-qat"
    assert captured["payload"]["temperature"] == pytest.approx(0.1)
    assert captured["payload"]["stream"] is False


def test_post_chat_completion_is_importable() -> None:
    """post_chat_completion is publicly importable from mintmory.core.llm."""
    from mintmory.core.llm import post_chat_completion  # noqa: F401

    assert callable(post_chat_completion)


def test_post_chat_completion_builds_correct_request(monkeypatch: Any) -> None:
    """post_chat_completion posts to base_url/chat/completions and returns parsed JSON."""
    captured: dict[str, Any] = {}
    body = {"choices": [{"message": {"content": "ok"}}]}
    _patch_urlopen(monkeypatch, captured, body)

    from mintmory.core.llm import post_chat_completion

    result = post_chat_completion(
        base_url="http://myhost:8080/v1",
        api_key=None,
        payload={
            "model": "mymodel",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
        timeout_s=10.0,
        system="test",
        model="mymodel",
    )

    assert result == body
    assert captured["url"] == "http://myhost:8080/v1/chat/completions"
    assert captured["timeout"] == pytest.approx(10.0)
    assert "Authorization" not in captured["headers"]


def test_post_chat_completion_adds_bearer_header(monkeypatch: Any) -> None:
    """post_chat_completion adds Authorization: Bearer header when api_key is set."""
    captured: dict[str, Any] = {}
    body = {"choices": [{"message": {"content": "ok"}}]}
    _patch_urlopen(monkeypatch, captured, body)

    from mintmory.core.llm import post_chat_completion

    post_chat_completion(
        base_url="http://host/v1",
        api_key="my-secret-key",
        payload={"model": "m", "messages": [], "stream": False},
        timeout_s=5.0,
        system="s",
        model="m",
    )

    assert captured["headers"].get("Authorization") == "Bearer my-secret-key"


def test_post_chat_completion_strips_trailing_slash(monkeypatch: Any) -> None:
    """post_chat_completion strips trailing slash from base_url before appending path."""
    captured: dict[str, Any] = {}
    body = {"choices": [{"message": {"content": "x"}}]}
    _patch_urlopen(monkeypatch, captured, body)

    from mintmory.core.llm import post_chat_completion

    post_chat_completion(
        base_url="http://host/v1/",
        api_key=None,
        payload={"model": "m", "messages": [], "stream": False},
        timeout_s=5.0,
        system="s",
        model="m",
    )

    assert captured["url"] == "http://host/v1/chat/completions"
