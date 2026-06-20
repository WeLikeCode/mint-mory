"""
The single module that talks to a chat LLM (docs/OBSERVABILITY.md §1.3).

This supersedes the ad-hoc chat/contradiction logic that used to live in
``scripts/local_llm.py``. It depends on stdlib ``urllib`` + ``json`` only — the
OpenAI-compatible ``/chat/completions`` shape is identical across Ollama, LM
Studio, vLLM and OpenAI, so no ``openai`` SDK is required.

Everything is config-driven (``LLMSettings``) with a fully offline default:
``provider=none`` makes every builder return ``None`` (or an engine whose
LLM-dependent steps return 0), exactly reproducing today's ``summarizer=None`` /
``conflict_resolver=None`` behaviour.

Each chat call is wrapped in the telemetry seam (``mintmory.core.telemetry``),
which is a NO-OP unless ``MINTMORY_OTEL_ENABLED=true`` — it never changes
behaviour. We use the OTel GenAI semantic conventions (``gen_ai.*``) for spans.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from typing import TYPE_CHECKING, Any

from mintmory.core import telemetry
from mintmory.core.config import LinkSettings, LLMProvider, LLMSettings, SummarySettings
from mintmory.core.dreaming import ConflictResolver, DreamingEngine, Summarizer
from mintmory.core.prompts import CONTRADICTION_DETECTION_PROMPT, SUMMARY_PROMPT
from mintmory.core.types import BatchResolutionAction, ConflictCheckResult, MemoryRecord

if TYPE_CHECKING:
    from mintmory.core.storage import StorageAdapter

# Tolerant JSON-extraction helpers (moved from scripts/local_llm.py).
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


# ---------------------------------------------------------------------------
# Robust JSON extraction
# ---------------------------------------------------------------------------
def extract_json(text: str) -> dict[str, Any]:
    """Best-effort extraction of a single JSON object from an LLM reply.

    Tolerates ``<think>`` blocks, ```` ```json ```` code fences, and
    leading/trailing prose. Returns ``{}`` if nothing parseable is found.
    """
    cleaned = _THINK_RE.sub("", text).strip()
    fence = _FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        obj: Any = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


# ---------------------------------------------------------------------------
# Shared OpenAI-compatible /chat/completions poster (stdlib urllib only)
# ---------------------------------------------------------------------------


def post_chat_completion(
    *,
    base_url: str,
    api_key: str | None,
    payload: dict[str, Any],
    timeout_s: float,
    system: str,
    model: str,
    extra_attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST an OpenAI-compatible ``/chat/completions`` ``payload`` and return the
    parsed JSON dict.

    Wraps the call in the existing ``gen_ai.chat`` span + ``mintmory.llm.*``
    metrics (no-op unless OTel on). Raises ``urllib.error.URLError`` /
    ``TimeoutError`` / ``json.JSONDecodeError`` to the caller (``LLMClient``
    maps as today; ``LLMCaptioner`` wraps in ``VisionError``).

    ``system`` sets ``gen_ai.system`` (e.g. the provider name).
    ``model`` sets ``gen_ai.request.model`` for telemetry.
    """
    headers: dict[str, str] = {"content-type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    attrs: dict[str, Any] = {
        "gen_ai.system": system,
        "gen_ai.request.model": model,
    }
    if extra_attrs:
        attrs.update(extra_attrs)
    start = time.perf_counter()
    ok = False
    with telemetry.span("gen_ai.chat", **attrs) as sp:
        try:
            with urllib.request.urlopen(  # noqa: S310 (configured base_url)
                req, timeout=timeout_s
            ) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
            usage = data.get("usage")
            if isinstance(usage, dict):
                in_tok = usage.get("prompt_tokens")
                out_tok = usage.get("completion_tokens")
                if in_tok is not None:
                    sp.set_attribute("gen_ai.usage.input_tokens", in_tok)
                if out_tok is not None:
                    sp.set_attribute("gen_ai.usage.output_tokens", out_tok)
            ok = True
            return data
        finally:
            ms = (time.perf_counter() - start) * 1000.0
            sp.set_attribute("latency_ms", ms)
            sp.set_attribute("ok", ok)
            telemetry.record_value("mintmory.llm.latency_ms", ms, model=model)
            telemetry.add_count("mintmory.llm.calls", model=model, ok=ok)


# ---------------------------------------------------------------------------
# OpenAI-compatible /chat/completions client (stdlib only)
# ---------------------------------------------------------------------------
class LLMClient:
    """Thin OpenAI-compatible ``/chat/completions`` client (stdlib ``urllib``).

    Works against Ollama, LM Studio, vLLM and OpenAI. A
    ``Authorization: Bearer <api_key>`` header is added iff ``api_key`` is set.
    """

    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings

    def _build_request(self, prompt: str) -> urllib.request.Request:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.settings.temperature,
            "stream": False,
        }
        headers = {"content-type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        return urllib.request.Request(
            self.settings.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

    def chat(self, prompt: str) -> str:
        """Single-turn chat completion; returns the assistant message text.

        Delegates to ``post_chat_completion`` (shared urllib poster). Wrapped in
        a ``gen_ai.chat`` span and ``mintmory.llm.*`` metrics (no-op unless OTel
        is enabled). Observable behaviour is byte-for-byte identical to the prior
        direct implementation.
        """
        model = self.settings.model
        provider = self.settings.provider.value
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.settings.temperature,
            "stream": False,
        }
        data = post_chat_completion(
            base_url=self.settings.base_url,
            api_key=self.settings.api_key,
            payload=payload,
            timeout_s=self.settings.timeout_s,
            system=provider,
            model=model,
            extra_attrs={"prompt_chars": len(prompt)},  # parity with pre-refactor span
        )
        content: str = data["choices"][0]["message"]["content"]
        return content

    def ping(self) -> bool:
        """Cheap liveness probe — ``True`` if a trivial chat succeeds."""
        try:
            return bool(self.chat("Reply with the single word: ok"))
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Contradiction detection
# ---------------------------------------------------------------------------
def check_contradiction(
    client: LLMClient,
    new_fact: str,
    existing: list[tuple[str, str]],
) -> ConflictCheckResult:
    """Run ``CONTRADICTION_DETECTION_PROMPT`` for one new fact vs existing.

    ``existing`` is a list of ``(memory_id, content)`` pairs. Returns
    ``has_conflict=False`` on an empty input or any parse/validation failure.
    """
    if not existing:
        return ConflictCheckResult(has_conflict=False, conflicts=[])
    rendered = "\n".join(f"{mid} :: {content}" for mid, content in existing)
    raw = client.chat(
        CONTRADICTION_DETECTION_PROMPT.format(new_fact=new_fact, existing_memories=rendered)
    )
    data = extract_json(raw)
    try:
        return ConflictCheckResult.model_validate(data)
    except Exception:
        return ConflictCheckResult(has_conflict=False, conflicts=[])


# ---------------------------------------------------------------------------
# Builders — turn LLMSettings into the DreamingEngine callables (or None)
# ---------------------------------------------------------------------------
def build_summarizer(settings: LLMSettings) -> Summarizer | None:
    """Build an L3 summarizer callable, or ``None`` when ``provider=none``."""
    if settings.provider is LLMProvider.NONE:
        return None
    client = LLMClient(settings)

    def summarize(concept: str, contents: list[str]) -> str:
        notes = "\n".join(f"- {c}" for c in contents)
        raw = client.chat(SUMMARY_PROMPT.format(concept=concept, notes=notes))
        # Strip <think>...</think> so reasoning models (e.g. MiniMax-M2.x via the
        # Portkey gateway) yield a clean summary, not their chain-of-thought.
        return _THINK_RE.sub("", raw).strip()

    return summarize


def build_conflict_resolver(
    settings: LLMSettings,
    adapter: StorageAdapter,
) -> ConflictResolver | None:
    """Build a conflict-resolver callable, or ``None`` when ``provider=none``.

    For a flagged record, asks the LLM which of its contradicting memories is
    outdated and should be archived (DELETE). Falls back to ``NONE`` on any
    failure so the dreaming step stays safe.
    """
    if settings.provider is LLMProvider.NONE:
        return None
    client = LLMClient(settings)

    def resolve(record: MemoryRecord) -> list[BatchResolutionAction]:
        others: list[tuple[str, str]] = []
        for cid in record.contradicts_ids:
            other = adapter.get_memory(cid)
            if other is not None:
                others.append((other.id, other.content))
        if not others:
            return [BatchResolutionAction(action="NONE", reason="no live conflicts")]
        rendered = "\n".join(f"{cid} :: {content}" for cid, content in others)
        prompt = (
            f"A new memory conflicts with older ones.\n"
            f"NEW ({record.id}): {record.content}\n"
            f"OLDER:\n{rendered}\n\n"
            f"Which ONE memory is now OUTDATED and should be archived? Reply ONLY JSON: "
            f'{{"action": "DELETE", "target_id": "<id of outdated memory>", '
            f'"reason": "<short reason>"}}  (use action NONE if none is outdated).'
        )
        data = extract_json(client.chat(prompt))
        try:
            return [BatchResolutionAction.model_validate(data)]
        except Exception:
            return [BatchResolutionAction(action="NONE", reason="unparseable resolver reply")]

    return resolve


def build_dreaming_engine(
    adapter: StorageAdapter,
    llm_settings: LLMSettings | None = None,
    link_settings: LinkSettings | None = None,
    summary_settings: SummarySettings | None = None,
) -> DreamingEngine:
    """Wire a ``DreamingEngine`` from settings.

    With ``provider=none`` (the default) both LLM callables are ``None``, so
    ``generate_summaries()`` and ``resolve_contradictions()`` return 0 — exactly
    today's offline behaviour. Link/summary settings are passed through.
    """
    llm = llm_settings if llm_settings is not None else LLMSettings()
    return DreamingEngine(
        adapter,
        summarizer=build_summarizer(llm),
        conflict_resolver=build_conflict_resolver(llm, adapter),
        link_settings=link_settings,
        summary_settings=summary_settings,
    )
