"""
M2 Gate (partial): Scoring formula unit tests.

Pure math tests — no IO, no LLM, no DB.
"""

import math
from datetime import datetime, timedelta

import pytest
from mintmory.core.scoring import (
    DECAY_BONUS_MAX,
    DEFAULT_DECAY_RATE,
    NOTE_BONUS,
    STALENESS_WEIGHT,
    USEFULNESS_WEIGHT,
    effective_score,
    increment_staleness,
    increment_usefulness,
    recency_bonus,
    rrf_merge,
)


class TestRecencyBonus:
    def test_max_when_just_accessed(self) -> None:
        now = datetime(2026, 6, 15)
        bonus = recency_bonus(now, now=now)
        assert math.isclose(bonus, DECAY_BONUS_MAX, rel_tol=1e-6)

    def test_zero_when_never_accessed(self) -> None:
        assert recency_bonus(None) == 0.0

    def test_decays_over_time(self) -> None:
        now = datetime(2026, 6, 15)
        accessed_30_days_ago = now - timedelta(days=30)
        bonus = recency_bonus(accessed_30_days_ago, now=now)
        expected = DECAY_BONUS_MAX * math.exp(-DEFAULT_DECAY_RATE * 30)
        assert math.isclose(bonus, expected, rel_tol=1e-6)

    def test_positive_always(self) -> None:
        now = datetime(2026, 6, 15)
        accessed_5_years_ago = now - timedelta(days=5 * 365)
        assert recency_bonus(accessed_5_years_ago, now=now) > 0


class TestEffectiveScore:
    def test_useful_memory_scores_higher(self) -> None:
        base = 0.7
        useful = effective_score(base, usefulness_score=8.0, staleness_score=0.0)
        not_useful = effective_score(base, usefulness_score=0.0, staleness_score=0.0)
        assert useful > not_useful

    def test_stale_memory_scores_lower(self) -> None:
        base = 0.7
        stale = effective_score(base, usefulness_score=0.0, staleness_score=8.0)
        fresh = effective_score(base, usefulness_score=0.0, staleness_score=0.0)
        assert stale < fresh

    def test_formula_is_correct(self) -> None:
        now = datetime(2026, 6, 15)
        accessed = now - timedelta(days=10)
        base = 0.5
        score = effective_score(
            base,
            usefulness_score=5.0,
            staleness_score=2.0,
            last_accessed_at=accessed,
            now=now,
        )
        expected = (
            base
            + 5.0 * USEFULNESS_WEIGHT
            - 2.0 * STALENESS_WEIGHT
            + DECAY_BONUS_MAX * math.exp(-DEFAULT_DECAY_RATE * 10)
        )
        assert math.isclose(score, expected, rel_tol=1e-6)


class TestNoteBonusScoring:
    """Tests for the note_bonus parameter (design §3)."""

    def test_note_bonus_zero_default_unchanged(self) -> None:
        """note_bonus=0.0 (default) reproduces today's scoring exactly — byte-identical."""
        base = 0.6
        score_default = effective_score(base, usefulness_score=0.0, staleness_score=0.0)
        score_no_bonus = effective_score(
            base,
            usefulness_score=0.0,
            staleness_score=0.0,
            is_note=False,
            note_bonus=0.0,
        )
        score_note_no_bonus = effective_score(
            base,
            usefulness_score=0.0,
            staleness_score=0.0,
            is_note=True,
            note_bonus=0.0,
        )
        assert math.isclose(score_default, score_no_bonus, rel_tol=1e-9)
        assert math.isclose(score_default, score_note_no_bonus, rel_tol=1e-9)

    def test_is_note_true_adds_bonus(self) -> None:
        """is_note=True with a positive note_bonus raises the score."""
        base = 0.5
        non_note = effective_score(
            base, usefulness_score=0.0, staleness_score=0.0, is_note=False, note_bonus=0.05
        )
        note = effective_score(
            base, usefulness_score=0.0, staleness_score=0.0, is_note=True, note_bonus=0.05
        )
        assert note > non_note
        assert math.isclose(note - non_note, 0.05, rel_tol=1e-9)

    def test_is_note_false_bonus_not_applied(self) -> None:
        """is_note=False: note_bonus is NOT added even if it is non-zero."""
        base = 0.5
        score = effective_score(
            base, usefulness_score=0.0, staleness_score=0.0, is_note=False, note_bonus=0.5
        )
        expected = base + 0.0 * USEFULNESS_WEIGHT - 0.0 * STALENESS_WEIGHT + recency_bonus(None)
        assert math.isclose(score, expected, rel_tol=1e-9)

    def test_note_bonus_constant_is_0_05(self) -> None:
        """NOTE_BONUS constant must be 0.05 (design §3)."""
        assert math.isclose(NOTE_BONUS, 0.05, rel_tol=1e-9)

    def test_note_ranks_higher_than_non_note_equal_base(self) -> None:
        """A note and a non-note with equal base relevance: note ranks first (§3)."""
        base = 0.7
        note_score = effective_score(
            base, usefulness_score=0.0, staleness_score=0.0, is_note=True, note_bonus=0.05
        )
        non_note_score = effective_score(
            base, usefulness_score=0.0, staleness_score=0.0, is_note=False, note_bonus=0.05
        )
        assert note_score > non_note_score

    def test_formula_is_correct_with_note_bonus(self) -> None:
        """The full formula is: base + usefulness*w - staleness*w + recency + (bonus if note)."""
        now = datetime(2026, 6, 15)
        accessed = now - timedelta(days=10)
        base = 0.5
        score = effective_score(
            base,
            usefulness_score=3.0,
            staleness_score=1.5,
            last_accessed_at=accessed,
            now=now,
            is_note=True,
            note_bonus=0.05,
        )
        expected = (
            base
            + 3.0 * USEFULNESS_WEIGHT
            - 1.5 * STALENESS_WEIGHT
            + DECAY_BONUS_MAX * math.exp(-DEFAULT_DECAY_RATE * 10)
            + 0.05
        )
        assert math.isclose(score, expected, rel_tol=1e-6)


class TestCapInvariants:
    def test_usefulness_capped_at_10(self) -> None:
        assert increment_usefulness(9.5) == 10.0
        assert increment_usefulness(10.0) == 10.0
        assert increment_usefulness(10.0, increment=5.0) == 10.0

    def test_staleness_capped_at_10(self) -> None:
        assert increment_staleness(9.5) == 10.0
        assert increment_staleness(10.0) == 10.0

    def test_small_increments_work(self) -> None:
        assert math.isclose(increment_usefulness(3.0, increment=1.0), 4.0)
        assert math.isclose(increment_staleness(2.0, increment=1.0), 3.0)


class TestRRFMerge:
    def test_document_in_both_lists_ranks_higher(self) -> None:
        fts = {"mem_a": 1.0, "mem_b": 0.5}
        vec = {"mem_a": 1.0, "mem_c": 0.8}
        merged = rrf_merge(fts, vec)
        # mem_a appears in both lists → highest RRF score
        assert merged["mem_a"] > merged["mem_b"]
        assert merged["mem_a"] > merged["mem_c"]

    def test_document_only_in_one_list(self) -> None:
        fts = {"mem_x": 1.0}
        vec = {"mem_y": 1.0}
        merged = rrf_merge(fts, vec)
        assert "mem_x" in merged
        assert "mem_y" in merged

    def test_empty_inputs(self) -> None:
        assert rrf_merge({}, {}) == {}
        assert rrf_merge({"a": 1.0}, {}) == {"a": pytest.approx(1.0 / 61)}

    def test_variadic_three_lists_fuses_all(self) -> None:
        fts = {"mem_a": 1.0, "mem_b": 0.5}
        trigram = {"mem_a": 1.0, "mem_c": 0.7}
        vec = {"mem_a": 1.0, "mem_d": 0.3}
        merged = rrf_merge(fts, trigram, vec)
        # mem_a is top-ranked in all three lists → highest fused score.
        assert merged["mem_a"] > merged["mem_b"]
        assert merged["mem_a"] > merged["mem_c"]
        assert merged["mem_a"] > merged["mem_d"]
        # A doc in all three outranks a doc in only one.
        assert merged["mem_a"] > max(merged["mem_b"], merged["mem_c"], merged["mem_d"])

    def test_variadic_skips_empty_lists(self) -> None:
        # An empty middle list must not change the fused result.
        fts = {"mem_a": 1.0}
        vec = {"mem_a": 1.0}
        with_empty = rrf_merge(fts, {}, vec)
        without_empty = rrf_merge(fts, vec)
        assert with_empty == pytest.approx(without_empty)

    def test_variadic_single_list_matches_two_arg(self) -> None:
        # A doc present in all three lists (rank 1 each) sums 3 * 1/(k+1).
        merged = rrf_merge({"a": 1.0}, {"a": 1.0}, {"a": 1.0})
        assert merged == {"a": pytest.approx(3.0 / 61)}
