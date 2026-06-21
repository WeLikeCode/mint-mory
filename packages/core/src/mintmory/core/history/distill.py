"""
history/distill.py — deterministic + LLM session distiller (Phase 2).

Public API:
  distill(summary, turns) -> SessionSummary
    Phase-1 API: whole-session deterministic distiller (distiller_version=1).
    Kept for backward compatibility; internally delegates to
    distill_segment_deterministic.

  distill_segment_deterministic(summary, seg_turns) -> SessionSummary
    Per-segment deterministic distiller (distiller_version=1).

  distill_llm(summary, seg_turns, chat, *, prev_context='') -> (SessionSummary, str)
    Per-segment LLM distiller (distiller_version=2). REDACTS every turn text
    and prev_context BEFORE building the prompt.  Returns (filled summary,
    next_context).  Raises ValueError on empty/garbage JSON (caller falls back).

Redaction boundary (INVARIANT):
  distill_segment_deterministic: no I/O; output redacted by write_session.
  distill_llm: EVERY turn text + prev_context is redact()'d BEFORE the prompt
  is built.  The returned summary fields are also redact()'d before persistence
  by write_session (defense in depth).  distill_llm MUST NOT undo redaction.

ChatFn = Callable[[str], str] — injected so tests use fake chat functions.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable

from mintmory.core.history.models import KINDS, NormalizedTurn, SessionSummary
from mintmory.core.history.redact import redact
from mintmory.core.llm import extract_json
from mintmory.core.prompts import HISTORY_SEGMENT_PROMPT

# Type alias for the chat callable (single-turn text in -> text out).
ChatFn = Callable[[str], str]

_TITLE_MAX = 80
_SUMMARY_MAX = 600

# Kind keyword heuristic — tested in order; first match wins.
# Each entry: (kind_name, list_of_keyword_regexes)
_KIND_RULES: list[tuple[str, list[str]]] = [
    (
        "fix",
        [r"\bfix\b", r"\bbug\b", r"\berror\b", r"\bpatch\b", r"\bhotfix\b", r"\bcorrect\b"],
    ),
    (
        "feature",
        [r"\badd\b", r"\bimplement\b", r"\bfeature\b", r"\bnew\b", r"\bbuild\b", r"\bcreate\b"],
    ),
    (
        "refactor",
        [
            r"\brefactor\b",
            r"\brename\b",
            r"\brestructure\b",
            r"\bcleanup\b",
            r"\bclean up\b",
            r"\bmove\b",
        ],
    ),
    (
        "docs",
        [
            r"\bdoc\b",
            r"\bdocs\b",
            r"\bdocumentation\b",
            r"\bdocument\b",
            r"\breadme\b",
            r"\bchangelog\b",
            r"\bcomment\b",
        ],
    ),
    (
        "incident",
        [r"\bincident\b", r"\boutage\b", r"\bdown\b", r"\bcrash\b", r"\bpanic\b", r"\bemergency\b"],
    ),
    (
        "chore",
        [
            r"\bchore\b",
            r"\bupgrade\b",
            r"\bdependency\b",
            r"\bdependencies\b",
            r"\bversion\b",
            r"\bbump\b",
        ],
    ),
    (
        "investigation",
        [
            r"\binvestigat\b",
            r"\bexplore\b",
            r"\banalyse\b",
            r"\banalyze\b",
            r"\bcheck\b",
            r"\bwhy\b",
            r"\bhow\b",
        ],
    ),
]


def _infer_kind(text: str) -> str:
    """Keyword heuristic over title+summary; returns one of KINDS."""
    lower = text.lower()
    for kind, patterns in _KIND_RULES:
        for pat in patterns:
            if re.search(pat, lower):
                return kind
    return "investigation"


def _first_user_turn(turns: list[NormalizedTurn]) -> str:
    """Return text of the first non-empty user turn, or ''."""
    for t in turns:
        if t.role == "user" and t.text.strip():
            return t.text.strip()
    return ""


def _last_assistant_turn(turns: list[NormalizedTurn]) -> str:
    """Return text of the last non-empty assistant turn, or ''."""
    for t in reversed(turns):
        if t.role == "assistant" and t.text.strip():
            return t.text.strip()
    return ""


def _collapse_ws(text: str) -> str:
    """Collapse runs of whitespace (including newlines) to single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def distill_segment_deterministic(
    summary: SessionSummary, seg_turns: list[NormalizedTurn]
) -> SessionSummary:
    """Deterministic per-segment distiller (Phase 2 API).

    Same heuristic as distill() but scoped to the segment's turn slice:
      - title: first user turn in the slice (<=80 chars, first line).
      - summary_text: 'Asked: <first user 200c> Outcome: <last assistant 300c>
        tools: …' (<=600 chars).
      - kind: keyword heuristic over title + summary.
      - distiller_version: 1.

    Pure and idempotent — no I/O, no LLM.
    """
    # --- title ---
    first_user = _first_user_turn(seg_turns)
    if first_user:
        first_line = first_user.split("\n")[0].strip()
        title = first_line[:_TITLE_MAX]
    else:
        title = summary.title[:_TITLE_MAX] if summary.title else ""

    # --- summary_text ---
    last_assistant = _last_assistant_turn(seg_turns)

    tools_sorted = sorted(set(summary.tools_used))
    tools_hint = f"tools: {', '.join(tools_sorted)}" if tools_sorted else ""

    parts: list[str] = []
    if first_user:
        ask = _collapse_ws(first_user)
        parts.append(f"Asked: {ask[:200]}")
    if last_assistant:
        outcome = _collapse_ws(last_assistant)
        parts.append(f"Outcome: {outcome[:300]}")
    if tools_hint:
        parts.append(tools_hint)

    summary_text = _collapse_ws(" ".join(parts))[:_SUMMARY_MAX]

    # --- kind ---
    kind_input = f"{title} {summary_text}"
    kind = _infer_kind(kind_input)
    if kind not in KINDS:
        kind = "investigation"

    return dataclasses.replace(
        summary,
        title=title,
        summary_text=summary_text,
        kind=kind,
        distiller_version=1,
    )


def distill_llm(
    summary: SessionSummary,
    seg_turns: list[NormalizedTurn],
    chat: ChatFn,
    *,
    prev_context: str = "",
) -> tuple[SessionSummary, str]:
    """LLM per-segment distiller (distiller_version=2).

    SECURITY: redact() is called on EVERY turn text and on prev_context BEFORE
    they are placed into the prompt.  Raw secrets MUST NOT reach the LLM.

    Algorithm:
      1. Build a redacted role-tagged transcript from seg_turns.
      2. Format HISTORY_SEGMENT_PROMPT with redacted prev_context + transcript.
      3. Call chat(prompt); parse JSON via extract_json.
      4. Validate/clamp: title<=80, summary<=600, kind in KINDS else 'investigation',
         outcome<=120, next_context<=300.
      5. Raise ValueError on empty / garbage / missing-required-field result
         (caller catches and falls back to deterministic).

    Returns (filled SessionSummary, next_context_str).
    next_context is also redacted before returning.
    distiller_version is set to 2.
    """
    outcome_max = 120
    next_ctx_max = 300
    tool_result_max = 400  # elide oversized tool_result bursts

    # 1. Build redacted transcript (HARD SECURITY BOUNDARY).
    transcript_lines: list[str] = []
    for turn in seg_turns:
        safe_text = redact(turn.text)
        role = turn.role
        if role == "tool" and len(safe_text) > tool_result_max:
            safe_text = safe_text[:tool_result_max] + " … [elided]"
        transcript_lines.append(f"[{role.upper()}] {safe_text}")
    transcript = "\n".join(transcript_lines)

    safe_prev_context = redact(prev_context)

    # 2. Build prompt.
    prompt = HISTORY_SEGMENT_PROMPT.format(
        prev_context=safe_prev_context,
        transcript=transcript,
        repo=summary.repo,
    )

    # 3. Call LLM.
    raw = chat(prompt)

    # 4. Parse JSON.
    data = extract_json(raw)
    if not data:
        raise ValueError(f"distill_llm: LLM returned empty/garbage JSON: {raw!r}")

    # Required fields
    title = str(data.get("title", "")).strip()
    kind = str(data.get("kind", "investigation")).strip()
    summary_text = str(data.get("summary", "")).strip()
    outcome = str(data.get("outcome", "")).strip()
    next_context = str(data.get("next_context", "")).strip()

    if not title and not summary_text:
        raise ValueError(f"distill_llm: LLM returned missing title+summary: {data!r}")

    # 5. Clamp / validate.
    title = title[:_TITLE_MAX]
    summary_text = summary_text[:_SUMMARY_MAX]
    if kind not in KINDS:
        kind = "investigation"
    outcome = outcome[:outcome_max]
    next_context = redact(next_context[:next_ctx_max])

    filled = dataclasses.replace(
        summary,
        title=title,
        summary_text=summary_text,
        kind=kind,
        outcome=outcome,
        distiller_version=2,
    )
    return filled, next_context


def distill(summary: SessionSummary, turns: list[NormalizedTurn]) -> SessionSummary:
    """Whole-session deterministic distiller — Phase-1 backward-compatible API.

    Delegates to distill_segment_deterministic (same heuristic, same output
    contract).  distiller_version stays 1.

    distill MUST NOT undo redaction; its output is redacted by write_session
    before persistence (raw turns are not pre-redacted here — distill_llm is
    the seam that MUST redact before LLM).
    """
    return distill_segment_deterministic(summary, turns)
