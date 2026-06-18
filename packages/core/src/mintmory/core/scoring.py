"""
Scoring and decay formulas.

Exponential decay copied from widemem/scoring/decay.py (confirmed accurate
by OPUS audit — the only formula in the research that matched the source code).

Scoring formula (from FEATURES.md corrected):
  effective_score = base_relevance
                  + usefulness_score * USEFULNESS_WEIGHT   (default 0.3)
                  - staleness_score  * STALENESS_WEIGHT    (default 0.2)
                  + recency_bonus                          (exponential decay)
                  + note_bonus (if is_note, default 0.0 for backward compat)

Where:
  recency_bonus = DECAY_BONUS_MAX * exp(-decay_rate * days_since_access)
  DECAY_BONUS_MAX = 0.1
  decay_rate      = 0.01 (configurable per memory type)
  NOTE_BONUS      = 0.05 (authority boost for user-authored notes; same scale as
                   recency bonus — tie-breaker, not a hammer)
"""

from __future__ import annotations

import math
from datetime import datetime

# Default weights (configurable in mintmory.toml)
USEFULNESS_WEIGHT: float = 0.3
STALENESS_WEIGHT: float = 0.2
DECAY_BONUS_MAX: float = 0.1
DEFAULT_DECAY_RATE: float = 0.01

# Authority boost for is_note rows (see NoteSettings.note_bonus in config.py).
# This constant is the recommended default; effective_score defaults note_bonus=0.0
# so all existing callers are unaffected until they opt in.
NOTE_BONUS: float = 0.05

# Feedback / dreaming increments (FEATURES.md §6; PLAN.md §1b)
USEFUL_INCREMENT: float = 0.5
STALE_INCREMENT: float = 1.0
STALENESS_THRESHOLD: float = 7.0
ARCHIVE_THRESHOLD: float = 9.0
REHAB_DELTA: float = 2.0


def recency_bonus(
    last_accessed_at: datetime | None,
    decay_rate: float = DEFAULT_DECAY_RATE,
    now: datetime | None = None,
) -> float:
    """
    Exponential recency bonus — widemem decay.py formula (confirmed accurate).

    Returns a value in [0, DECAY_BONUS_MAX]:
      0.1 if just accessed (days = 0)
      ~0.073 after 30 days (decay_rate=0.01)
      ~0.005 after 500 days
    """
    if last_accessed_at is None:
        return 0.0
    _now = now or datetime.utcnow()
    days = max(0.0, (_now - last_accessed_at).total_seconds() / 86_400)
    return DECAY_BONUS_MAX * math.exp(-decay_rate * days)


def effective_score(
    base_relevance: float,
    usefulness_score: float,
    staleness_score: float,
    last_accessed_at: datetime | None = None,
    usefulness_weight: float = USEFULNESS_WEIGHT,
    staleness_weight: float = STALENESS_WEIGHT,
    decay_rate: float = DEFAULT_DECAY_RATE,
    now: datetime | None = None,
    is_note: bool = False,
    note_bonus: float = 0.0,
) -> float:
    """Composite retrieval score. Higher is better.

    Useful memories surface first; stale memories are penalised; recently
    accessed memories get a small recency boost. When ``is_note`` is True a
    flat ``note_bonus`` is added (authority boost for user-authored notes, same
    additive scale as the recency bonus). ``note_bonus`` defaults to 0.0 so all
    existing callers and unconfigured callers are byte-identical to before.
    The real value is threaded in by ``StorageAdapter.search()`` from
    ``NoteSettings.note_bonus`` (see config.py §2 / storage.py §5a).
    """
    return (
        base_relevance
        + usefulness_score * usefulness_weight
        - staleness_score * staleness_weight
        + recency_bonus(last_accessed_at, decay_rate=decay_rate, now=now)
        + (note_bonus if is_note else 0.0)
    )


def increment_usefulness(current: float, increment: float = 1.0) -> float:
    """Increment usefulness_score, capped at 10.0 (invariant from AGENTS.md §4)."""
    return min(10.0, current + increment)


def increment_staleness(current: float, increment: float = 1.0) -> float:
    """Increment staleness_score, capped at 10.0 (invariant from AGENTS.md §4)."""
    return min(10.0, current + increment)


def rrf_merge(*score_dicts: dict[str, float], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion over N ranked score dicts (higher score = better
    rank within each list). Empty dicts are skipped. RRF(d)=Σ 1/(k+rank_i(d))."""
    merged: dict[str, float] = {}
    for scores in score_dicts:
        if not scores:
            continue
        for rank, doc_id in enumerate(
            sorted(scores, key=scores.get, reverse=True),  # type: ignore[arg-type]
            start=1,
        ):
            merged[doc_id] = merged.get(doc_id, 0.0) + 1.0 / (k + rank)
    return merged
