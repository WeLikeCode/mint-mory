"""
history/distill.py — deterministic session distiller (LLM seam).

distill() fills title/kind/summary_text from the session turns WITHOUT
any network call or LLM. It is pure and idempotent:
  - same inputs always produce the same outputs
  - running twice produces the same SessionSummary

Redaction boundary: distill() does NOT itself send anything anywhere, and its
output (title/summary_text) is redacted by write_session BEFORE it is persisted,
so v1 never leaks. NOTE: the raw `turns` passed in are NOT pre-redacted. A future
distill_llm(summary, turns, client) seam MUST call redact() on each turn's text
before building any prompt — raw turns must never reach an LLM (spec: redact
BEFORE any LLM). v1 wires only distill(); distiller_version stays 1.
"""

from __future__ import annotations

import dataclasses
import re

from mintmory.core.history.models import KINDS, NormalizedTurn, SessionSummary

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


def distill(summary: SessionSummary, turns: list[NormalizedTurn]) -> SessionSummary:
    """
    Fill title/kind/summary_text deterministically (NO network, NO LLM) and
    return a NEW SessionSummary (dataclasses.replace). Rules:

    - title: first non-empty user turn, first line, trimmed to <= 80 chars.
    - summary_text (<= 600 chars, changelog voice): combine the first user
      turn (the ask) + the last assistant turn (the outcome) + a tools/files
      hint ('touched N files; tools: edit, bash'); collapse whitespace.
    - kind: keyword heuristic over title+summary.

    distill MUST NOT undo redaction; its output is redacted by write_session
    before persistence (raw turns themselves are not pre-redacted — see module
    docstring re: the future distill_llm seam).
    distiller_version stays 1.
    """
    # --- title ---
    first_user = _first_user_turn(turns)
    if first_user:
        first_line = first_user.split("\n")[0].strip()
        title = first_line[:_TITLE_MAX]
    else:
        title = summary.title[:_TITLE_MAX] if summary.title else ""

    # --- summary_text ---
    last_assistant = _last_assistant_turn(turns)

    # Tools hint
    tools_sorted = sorted(set(summary.tools_used))
    tools_hint = f"tools: {', '.join(tools_sorted)}" if tools_sorted else ""

    parts: list[str] = []
    if first_user:
        ask = _collapse_ws(first_user)
        # Trim to leave room for outcome + tools
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
    # Validate against KINDS (defensive)
    if kind not in KINDS:
        kind = "investigation"

    return dataclasses.replace(
        summary,
        title=title,
        summary_text=summary_text,
        kind=kind,
        distiller_version=1,
    )
