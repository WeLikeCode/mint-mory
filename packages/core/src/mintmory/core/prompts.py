"""
LLM prompt templates for MintMory's self-maintaining behaviours.

These are kept in one module so the session feedback loop (``session.py``) and
the dreaming consolidation engine (``dreaming.py``) share a single, audited
source for the exact JSON contracts the LLM must return.

CRITICAL (AGENTS.md §4.1 / FEATURES.md §8): the contradiction schema is
``{has_conflict, conflicts[].existing_memory_id}`` — NEVER the v1.0 draft's
``is_contradiction`` / ``contradicts_memory_ids``. ``ConflictCheckResult`` in
``types.py`` is the Pydantic model that validates the returned JSON.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Contradiction detection (FEATURES.md §8) — validated by ConflictCheckResult.
# Placeholders: {new_fact}, {existing_memories}
# ---------------------------------------------------------------------------
CONTRADICTION_DETECTION_PROMPT = """\
You are the consistency checker for a typed memory system. A new fact is about
to be stored. Compare it against the existing memories below and identify any
that it CONTRADICTS (cannot both be true) or is AMBIGUOUS with (possibly
compatible but unclear, needs a clarifying question).

New fact:
{new_fact}

Existing memories (id :: content):
{existing_memories}

Return ONLY a JSON object with EXACTLY this schema:
{{
  "has_conflict": <true|false>,
  "conflicts": [
    {{
      "new_fact": "<the new fact text>",
      "existing_memory_id": "<id of the conflicting existing memory>",
      "existing_content": "<content of that existing memory>",
      "type": "contradiction" | "ambiguity",
      "question": "<clarifying question, only for ambiguity; otherwise null>"
    }}
  ]
}}

Rules:
- The top-level field is "has_conflict" (boolean). NOT "is_contradiction".
- Each conflict references a single "existing_memory_id" (string). NOT a list
  named "contradicts_memory_ids".
- If there are no conflicts, return {{"has_conflict": false, "conflicts": []}}.
- "question" is non-null only when "type" is "ambiguity".
"""

# ---------------------------------------------------------------------------
# Passive self-assessment feedback (FEATURES.md §7).
# Placeholders: {memories}, {answer}
# ---------------------------------------------------------------------------
FEEDBACK_PROMPT = """\
You just answered a query using the following memories.
Which memories were actually useful in forming your answer?
Which were stale or incorrect?
Rate your confidence (1=very low, 5=very high).

Memories retrieved (id :: content):
{memories}

Your answer:
{answer}

Return ONLY a JSON object with this schema:
{{
  "useful_ids": ["<memory id>", ...],
  "stale_ids": ["<memory id>", ...],
  "confidence_rating": <1-5>,
  "reasoning": "<short explanation>"
}}
"""

# ---------------------------------------------------------------------------
# Image caption (vision provider 'llm') — default prompt for LLMCaptioner.
# Overridden at runtime by MINTMORY_VISION_VISION_PROMPT (non-empty value wins).
# ---------------------------------------------------------------------------
IMAGE_CAPTION_PROMPT = (
    "Describe this image in 2-4 sentences for a search index. State what it "
    "depicts and transcribe ALL legible text verbatim (labels, captions, UI "
    "strings, diagram nodes). Be specific: keep names, numbers, and on-screen "
    "text. Reply with ONLY the description (no preamble)."
)

# ---------------------------------------------------------------------------
# History segment distiller (Phase 2).
# Placeholders: {prev_context}, {transcript}, {repo}
# ---------------------------------------------------------------------------
HISTORY_SEGMENT_PROMPT = """\
You are summarising one segment of an agentic coding session in the repository \
"{repo}" as a changelog entry.

Previous segment context (what happened before this segment):
{prev_context}

Session transcript (role-tagged, secrets already redacted):
{transcript}

Output ONLY a strict JSON object — no prose, no markdown fences — with EXACTLY \
these keys:

{{
  "title": "<imperative verb phrase, ≤8 words>",
  "kind": "<one of: fix | feature | refactor | investigation | chore | docs | incident>",
  "summary": "<what was done or decided — ≤2 sentences>",
  "outcome": "<single short clause: done | partial | blocked | …>",
  "next_context": "<≤1 sentence to brief the next segment>"
}}

Rules:
- "title" must start with an imperative verb and be ≤8 words.
- "kind" must be exactly one of the seven values listed above.
- "summary" ≤2 sentences; focus on decisions and concrete changes.
- "outcome" ≤1 short clause (e.g. "done", "partial — tests pending").
- "next_context" ≤1 sentence; leave blank ("") if this is the final segment.
- Do NOT include any text outside the JSON object.
"""

# ---------------------------------------------------------------------------
# L3 concept summary (dreaming step 3). Placeholders: {concept}, {notes}
# ---------------------------------------------------------------------------
SUMMARY_PROMPT = """\
You are consolidating an agent's memory. Write a 2-3 sentence synthesis of
everything known about the concept '{concept}' from the notes below. Be specific:
keep concrete names, numbers, dates, and decisions. Reply with ONLY the synthesis
(no preamble).

Notes:
{notes}
"""
