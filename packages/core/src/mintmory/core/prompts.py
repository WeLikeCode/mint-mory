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
