"""
QuerySession feedback loop — the passive self-assessment cycle (ROADMAP M3).

This module orchestrates the four-step session lifecycle described in
FEATURES.md §7 on top of the per-memory feedback primitive that lives in
``StorageAdapter.apply_feedback`` (PLAN.md §1b):

  1. ``create_session(adapter, query_text)``   — open a QuerySession row.
  2. ``record_results(adapter, sid, results)``  — record retrieved memories.
  3. _(the agent answers the user using the retrieved memories)_
  4. ``apply_feedback(adapter, sid, useful_ids, stale_ids, ...)`` — reinforce
     useful memories, penalise stale ones, and conclude the session.

The session-level ``apply_feedback`` is a thin orchestrator: it calls the
storage primitive once per memory id (which owns clamping + the staleness
threshold, AGENTS.md §4.3) and then stamps the assessment onto the
``query_sessions`` / ``query_results`` rows. Concluding a session that is
already concluded raises ``ValueError`` (callers map this to HTTP 409).

``build_feedback_prompt`` formats ``prompts.FEEDBACK_PROMPT`` for the LLM that
produces the feedback. The LLM call itself is always injected by the caller, so
this module performs no network or model I/O and the tests stay deterministic.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mintmory.core.prompts import FEEDBACK_PROMPT
from mintmory.core.types import MemoryRecord, QueryResult, QuerySession

if TYPE_CHECKING:
    from mintmory.core.storage import StorageAdapter


def _utcnow() -> datetime:
    """Naive UTC datetime, matching the model defaults (``datetime.utcnow``)."""
    return datetime.now(UTC).replace(tzinfo=None)


def create_session(adapter: StorageAdapter, query_text: str) -> QuerySession:
    """Open a new QuerySession, persist it, and return the stored record."""
    session = QuerySession(query_text=query_text)
    return adapter.create_session(session)


def record_results(
    adapter: StorageAdapter,
    session_id: str,
    results: list[QueryResult],
) -> None:
    """Record retrieved memories for a session.

    Thin wrapper over ``adapter.record_query_results`` that stamps
    ``session_id`` onto every result so callers can build ``QueryResult``
    objects without repeating the session id.
    """
    stamped = [result.model_copy(update={"session_id": session_id}) for result in results]
    adapter.record_query_results(stamped)


def apply_feedback(
    adapter: StorageAdapter,
    session_id: str,
    useful_ids: list[str],
    stale_ids: list[str],
    confidence_rating: int | None = None,
    reasoning: str | None = None,
) -> QuerySession:
    """Apply passive self-assessment feedback and conclude the session.

    For each id in ``useful_ids`` the per-memory primitive is called with
    ``useful=True, stale=False`` (usefulness += USEFUL_INCREMENT, capped at
    10.0; reinforcement_count += 1). For each id in ``stale_ids`` it is called
    with ``useful=False, stale=True`` (staleness += STALE_INCREMENT, capped at
    10.0; ``is_stale`` flips once the threshold is reached). All clamping and
    the staleness threshold live in storage (AGENTS.md §4.3).

    The ``query_sessions`` row is then updated with the assessment
    (``confidence_rating``, ``reasoning``, ``useful_ids``/``stale_ids`` JSON,
    ``concluded = 1``) and the matching ``query_results`` rows get their
    ``was_useful`` / ``was_stale`` flags set.

    Raises:
        ValueError: if the session does not exist or is already concluded
            (callers map this to HTTP 409 Conflict). The check is performed
            before any score mutation so feedback is never applied twice.
    """
    session = adapter.get_session(session_id)
    if session is None:
        raise ValueError(f"session {session_id!r} not found")
    if session.concluded:
        raise ValueError(f"session {session_id!r} is already concluded")

    for memory_id in useful_ids:
        adapter.apply_feedback(memory_id, useful=True, stale=False)
    for memory_id in stale_ids:
        adapter.apply_feedback(memory_id, useful=False, stale=True)

    useful_set = set(useful_ids)
    stale_set = set(stale_ids)

    with adapter.transaction() as conn:
        conn.execute(
            "UPDATE query_sessions SET confidence_rating = ?, reasoning = ?, "
            "useful_ids = ?, stale_ids = ?, concluded = 1 WHERE id = ?",
            (
                confidence_rating,
                reasoning,
                json.dumps(useful_ids),
                json.dumps(stale_ids),
                session_id,
            ),
        )
        for memory_id in useful_set | stale_set:
            conn.execute(
                "UPDATE query_results SET was_useful = ?, was_stale = ? "
                "WHERE session_id = ? AND memory_id = ?",
                (
                    1 if memory_id in useful_set else 0,
                    1 if memory_id in stale_set else 0,
                    session_id,
                    memory_id,
                ),
            )

    refreshed = adapter.get_session(session_id)
    assert refreshed is not None  # just updated, row exists
    return refreshed


def conclude_session(adapter: StorageAdapter, session_id: str) -> None:
    """Mark a session concluded with no feedback (idempotent).

    Used for TTL-abandoned sessions: the agent never submitted feedback, so no
    scores change — the row is simply flipped to ``concluded = 1``. Calling
    this on an already-concluded or missing session is a no-op.
    """
    with adapter.transaction() as conn:
        conn.execute(
            "UPDATE query_sessions SET concluded = 1 WHERE id = ?",
            (session_id,),
        )


def build_feedback_prompt(memories: Iterable[MemoryRecord], answer: str) -> str:
    """Format ``prompts.FEEDBACK_PROMPT`` for the self-assessment LLM call.

    Memories are rendered one per line as ``<id> :: <content>`` (the format the
    prompt's schema documents). The returned string is handed to the injected
    LLM callable by the caller; this function performs no I/O.
    """
    rendered = "\n".join(f"{mem.id} :: {mem.content}" for mem in memories)
    return FEEDBACK_PROMPT.format(memories=rendered, answer=answer)
