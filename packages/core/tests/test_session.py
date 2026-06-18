"""Unit tests for the QuerySession feedback loop (core/session.py, ROADMAP M3).

Covers the four-step lifecycle (create -> record -> feedback -> conclude), the
documented score increments + caps (FEATURES.md §6), the already-concluded
guard (PLAN.md §1b -> HTTP 409), the ConflictCheckResult field-name invariant
(AGENTS.md §4.1), and round-trip persistence of the concluded session row.
"""

from __future__ import annotations

import pytest
from mintmory.core import session as session_mod
from mintmory.core.embedder import FakeEmbedder
from mintmory.core.prompts import FEEDBACK_PROMPT
from mintmory.core.scoring import (
    STALE_INCREMENT,
    STALENESS_THRESHOLD,
    USEFUL_INCREMENT,
)
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import (
    ConflictCheckResult,
    ConflictDetail,
    MemoryCategory,
    MemoryRecord,
    QueryResult,
)


@pytest.fixture()
def store() -> StorageAdapter:
    s = StorageAdapter(":memory:", embedder=FakeEmbedder())
    s.initialise()
    return s


def _add(store: StorageAdapter, content: str) -> str:
    return store.add_memory(content=content, category=MemoryCategory.FACT).id


def _seed(store: StorageAdapter) -> tuple[str, str, str]:
    """Add 3 memories and return their ids."""
    return (
        _add(store, "the deploy freeze ends June 20"),
        _add(store, "the staging database lives in us-east-1"),
        _add(store, "Alice is the tech lead"),
    )


# ---------------------------------------------------------------------------
# Lifecycle: create -> record -> feedback
# ---------------------------------------------------------------------------


def test_create_session_persists_and_returns(store: StorageAdapter) -> None:
    sess = session_mod.create_session(store, "what is the deploy freeze date")
    assert sess.query_text == "what is the deploy freeze date"
    assert sess.concluded is False
    fetched = store.get_session(sess.id)
    assert fetched is not None
    assert fetched.id == sess.id


def test_record_results_stamps_session_id(store: StorageAdapter) -> None:
    a, b, _c = _seed(store)
    sess = session_mod.create_session(store, "query")
    # Build results WITHOUT a meaningful session_id; record_results must stamp it.
    results = [
        QueryResult(session_id="placeholder", memory_id=a, relevance_score=0.9),
        QueryResult(session_id="placeholder", memory_id=b, relevance_score=0.4),
    ]
    session_mod.record_results(store, sess.id, results)

    conn = store.connect()
    rows = conn.execute(
        "SELECT memory_id FROM query_results WHERE session_id = ? ORDER BY memory_id",
        (sess.id,),
    ).fetchall()
    assert {row["memory_id"] for row in rows} == {a, b}


def test_apply_feedback_updates_scores_by_documented_increments(store: StorageAdapter) -> None:
    a, b, c = _seed(store)
    sess = session_mod.create_session(store, "query")
    session_mod.record_results(
        store,
        sess.id,
        [
            QueryResult(session_id=sess.id, memory_id=a, relevance_score=0.9),
            QueryResult(session_id=sess.id, memory_id=b, relevance_score=0.5),
            QueryResult(session_id=sess.id, memory_id=c, relevance_score=0.1),
        ],
    )

    refreshed = session_mod.apply_feedback(
        store,
        sess.id,
        useful_ids=[a],
        stale_ids=[b],
        confidence_rating=4,
        reasoning="a was on point; b was outdated",
    )

    mem_a = store.get_memory(a)
    mem_b = store.get_memory(b)
    mem_c = store.get_memory(c)
    assert mem_a is not None and mem_b is not None and mem_c is not None

    # useful: usefulness += USEFUL_INCREMENT, reinforcement_count += 1, staleness untouched.
    assert mem_a.usefulness_score == pytest.approx(USEFUL_INCREMENT)
    assert mem_a.reinforcement_count == 1
    assert mem_a.staleness_score == pytest.approx(0.0)
    # stale: staleness += STALE_INCREMENT, usefulness untouched.
    assert mem_b.staleness_score == pytest.approx(STALE_INCREMENT)
    assert mem_b.usefulness_score == pytest.approx(0.0)
    # untouched memory stays at zero.
    assert mem_c.usefulness_score == pytest.approx(0.0)
    assert mem_c.staleness_score == pytest.approx(0.0)

    # The returned session reflects the assessment.
    assert refreshed.concluded is True
    assert refreshed.confidence_rating == 4
    assert refreshed.useful_ids == [a]
    assert refreshed.stale_ids == [b]


def test_apply_feedback_sets_query_result_flags(store: StorageAdapter) -> None:
    a, b, _c = _seed(store)
    sess = session_mod.create_session(store, "query")
    session_mod.record_results(
        store,
        sess.id,
        [
            QueryResult(session_id=sess.id, memory_id=a, relevance_score=0.9),
            QueryResult(session_id=sess.id, memory_id=b, relevance_score=0.5),
        ],
    )
    session_mod.apply_feedback(store, sess.id, useful_ids=[a], stale_ids=[b])

    conn = store.connect()
    rows = {
        row["memory_id"]: row
        for row in conn.execute(
            "SELECT memory_id, was_useful, was_stale FROM query_results WHERE session_id = ?",
            (sess.id,),
        ).fetchall()
    }
    assert rows[a]["was_useful"] == 1
    assert rows[a]["was_stale"] == 0
    assert rows[b]["was_useful"] == 0
    assert rows[b]["was_stale"] == 1


# ---------------------------------------------------------------------------
# Score caps: never exceed 10.0 across many cycles
# ---------------------------------------------------------------------------


def test_scores_never_exceed_cap_over_50_cycles(store: StorageAdapter) -> None:
    mem_id = _add(store, "a fact that gets repeatedly reinforced and aged")
    for _ in range(50):
        sess = session_mod.create_session(store, "repeat query")
        session_mod.record_results(
            store,
            sess.id,
            [QueryResult(session_id=sess.id, memory_id=mem_id, relevance_score=1.0)],
        )
        session_mod.apply_feedback(store, sess.id, useful_ids=[mem_id], stale_ids=[mem_id])

    mem = store.get_memory(mem_id)
    assert mem is not None
    assert mem.usefulness_score <= 10.0
    assert mem.staleness_score <= 10.0
    # Both increments saturate at the cap given 50 cycles.
    assert mem.usefulness_score == pytest.approx(10.0)
    assert mem.staleness_score == pytest.approx(10.0)


def test_staleness_threshold_flips_is_stale(store: StorageAdapter) -> None:
    mem_id = _add(store, "a fact that goes stale")
    # STALE_INCREMENT per cycle; cross STALENESS_THRESHOLD.
    cycles = int(STALENESS_THRESHOLD // STALE_INCREMENT) + 1
    for _ in range(cycles):
        sess = session_mod.create_session(store, "q")
        session_mod.apply_feedback(store, sess.id, useful_ids=[], stale_ids=[mem_id])
    mem = store.get_memory(mem_id)
    assert mem is not None
    assert mem.staleness_score >= STALENESS_THRESHOLD
    assert mem.is_stale is True


# ---------------------------------------------------------------------------
# Already-concluded guard (PLAN.md §1b -> 409)
# ---------------------------------------------------------------------------


def test_apply_feedback_twice_raises(store: StorageAdapter) -> None:
    a, _b, _c = _seed(store)
    sess = session_mod.create_session(store, "query")
    session_mod.record_results(
        store,
        sess.id,
        [QueryResult(session_id=sess.id, memory_id=a, relevance_score=0.9)],
    )
    session_mod.apply_feedback(store, sess.id, useful_ids=[a], stale_ids=[])

    with pytest.raises(ValueError, match="already concluded"):
        session_mod.apply_feedback(store, sess.id, useful_ids=[a], stale_ids=[])


def test_apply_feedback_twice_does_not_double_apply_scores(store: StorageAdapter) -> None:
    a, _b, _c = _seed(store)
    sess = session_mod.create_session(store, "query")
    session_mod.apply_feedback(store, sess.id, useful_ids=[a], stale_ids=[])
    mem_after_first = store.get_memory(a)
    assert mem_after_first is not None

    with pytest.raises(ValueError):
        session_mod.apply_feedback(store, sess.id, useful_ids=[a], stale_ids=[])

    # Score must be unchanged — the guard fires before any mutation.
    mem_after_second = store.get_memory(a)
    assert mem_after_second is not None
    assert mem_after_second.usefulness_score == pytest.approx(mem_after_first.usefulness_score)
    assert mem_after_second.reinforcement_count == mem_after_first.reinforcement_count


def test_apply_feedback_unknown_session_raises(store: StorageAdapter) -> None:
    with pytest.raises(ValueError, match="not found"):
        session_mod.apply_feedback(store, "no-such-session", useful_ids=[], stale_ids=[])


# ---------------------------------------------------------------------------
# conclude_session (TTL-abandoned, idempotent)
# ---------------------------------------------------------------------------


def test_conclude_session_marks_concluded_without_feedback(store: StorageAdapter) -> None:
    sess = session_mod.create_session(store, "abandoned query")
    session_mod.conclude_session(store, sess.id)
    fetched = store.get_session(sess.id)
    assert fetched is not None
    assert fetched.concluded is True
    assert fetched.useful_ids == []
    assert fetched.stale_ids == []


def test_conclude_session_idempotent(store: StorageAdapter) -> None:
    sess = session_mod.create_session(store, "abandoned query")
    session_mod.conclude_session(store, sess.id)
    session_mod.conclude_session(store, sess.id)  # second call is a no-op
    fetched = store.get_session(sess.id)
    assert fetched is not None
    assert fetched.concluded is True


def test_conclude_session_missing_is_noop(store: StorageAdapter) -> None:
    # Must not raise for a missing session id.
    session_mod.conclude_session(store, "no-such-session")


# ---------------------------------------------------------------------------
# Persistence round-trip of the concluded session row
# ---------------------------------------------------------------------------


def test_session_row_round_trip(store: StorageAdapter) -> None:
    a, b, _c = _seed(store)
    sess = session_mod.create_session(store, "round trip query")
    session_mod.record_results(
        store,
        sess.id,
        [
            QueryResult(session_id=sess.id, memory_id=a, relevance_score=0.7),
            QueryResult(session_id=sess.id, memory_id=b, relevance_score=0.3),
        ],
    )
    session_mod.apply_feedback(
        store,
        sess.id,
        useful_ids=[a],
        stale_ids=[b],
        confidence_rating=5,
        reasoning="clear winner",
    )

    fetched = store.get_session(sess.id)
    assert fetched is not None
    assert fetched.concluded is True
    assert fetched.confidence_rating == 5
    assert fetched.reasoning == "clear winner"
    assert fetched.useful_ids == [a]
    assert fetched.stale_ids == [b]


# ---------------------------------------------------------------------------
# build_feedback_prompt
# ---------------------------------------------------------------------------


def test_build_feedback_prompt_includes_ids_and_answer(store: StorageAdapter) -> None:
    a = _add(store, "alpha fact")
    b = _add(store, "beta fact")
    mems = [store.get_memory(a), store.get_memory(b)]
    assert all(m is not None for m in mems)
    prompt = session_mod.build_feedback_prompt(
        [m for m in mems if m is not None],
        answer="the answer I produced",
    )
    assert a in prompt
    assert b in prompt
    assert "alpha fact" in prompt
    assert "the answer I produced" in prompt
    # It is the FEEDBACK_PROMPT, not the contradiction prompt.
    assert "useful_ids" in prompt
    assert "{memories}" not in prompt  # placeholder was filled
    assert "{answer}" not in prompt


def test_build_feedback_prompt_uses_feedback_template(store: StorageAdapter) -> None:
    # Empty memory list still produces a valid filled prompt.
    prompt = session_mod.build_feedback_prompt([], answer="x")
    expected = FEEDBACK_PROMPT.format(memories="", answer="x")
    assert prompt == expected


# ---------------------------------------------------------------------------
# AGENTS.md §4.1 — ConflictCheckResult field-name invariant guard
# ---------------------------------------------------------------------------


def test_conflict_check_result_field_names() -> None:
    fields = set(ConflictCheckResult.model_fields)
    assert "has_conflict" in fields
    assert "conflicts" in fields
    # Forbidden v0 draft names must never appear.
    assert "is_contradiction" not in fields
    assert "contradicts_memory_ids" not in fields


def test_conflict_detail_uses_existing_memory_id() -> None:
    detail_fields = set(ConflictDetail.model_fields)
    assert "existing_memory_id" in detail_fields
    assert "contradicts_memory_ids" not in detail_fields

    result = ConflictCheckResult(
        has_conflict=True,
        conflicts=[
            ConflictDetail(
                new_fact="deploy freeze ends June 20",
                existing_memory_id="mem_abc123",
                existing_content="deploy freeze ends June 25",
                type="contradiction",
            )
        ],
    )
    assert result.has_conflict is True
    assert result.conflicts[0].existing_memory_id == "mem_abc123"


def test_memory_record_enforces_score_cap_at_model_level() -> None:
    # Pydantic-level guard mirrors the storage clamp (AGENTS.md §4.3).
    with pytest.raises(ValueError):
        MemoryRecord(content="x", category=MemoryCategory.FACT, usefulness_score=10.5)
    with pytest.raises(ValueError):
        MemoryRecord(content="x", category=MemoryCategory.FACT, staleness_score=11.0)
