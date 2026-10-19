"""
Shared hybrid-search pipeline for MintMory storage backends.

Backends implement three score methods (``_fts_scores``, ``_trigram_scores``,
``_vector_scores``) and four data-access callables; this module owns the
backend-independent orchestration:

  candidate scoring sources → RRF merge → min-max normalise → load records
  → filter → effective_score → sort → limit → search_around union
  → notes auto-include → session record → retrieval bump → SearchResponse

The ``fuse_and_search`` function handles the full search() pipeline.
The ``fuse_and_rank`` function handles anchor_candidates() (no session, no bump).

Design reference: design.md §5.1 — "a new backend implements only the three
score methods and inherits identical fusion."
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from mintmory.core import scoring, telemetry
from mintmory.core.types import (
    MemoryFilter,
    MemoryRecord,
    QueryResult,
    QuerySession,
    SearchAroundSpec,
    SearchRequest,
    SearchResponse,
)

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Internal filter helper (same logic as SqliteBackend._passes_filter)
# ---------------------------------------------------------------------------


def _passes_filter(mem: MemoryRecord, filt: MemoryFilter, include_archived: bool) -> bool:
    if not include_archived and mem.is_archived:
        return False
    if filt.active_only and not mem.is_active:
        return False
    if filt.exclude_stale and mem.is_stale:
        return False
    if filt.category is not None and mem.category != filt.category:
        return False
    if filt.source is not None and mem.source != filt.source:
        return False
    if filt.verified_only and not mem.verified:
        return False
    if filt.entity is not None and filt.entity.lower() not in {e.lower() for e in mem.entity_ids}:
        return False
    if filt.min_usefulness is not None and mem.usefulness_score < filt.min_usefulness:
        return False
    if filt.max_staleness is not None and mem.staleness_score > filt.max_staleness:  # noqa: SIM103
        return False
    return True


# ---------------------------------------------------------------------------
# Shared fusion + normalisation (used by both fuse_and_search and fuse_and_rank)
# ---------------------------------------------------------------------------


def _merge_and_normalise(
    fts_scores: dict[str, float],
    trigram_scores: dict[str, float],
    vector_scores: dict[str, float],
    vector_rrf_weight: float,
) -> dict[str, float]:
    """Merge score dicts via RRF and min-max normalise to [0, 1]."""
    paired = [
        (fts_scores, 1.0),
        (trigram_scores, 1.0),
        (vector_scores, vector_rrf_weight),
    ]
    paired = [(s, wt) for (s, wt) in paired if s]

    if not paired:
        return {}
    if len(paired) == 1:
        base_scores: dict[str, float] = paired[0][0]
    else:
        base_scores = scoring.rrf_merge(*[s for s, _ in paired], weights=[wt for _, wt in paired])

    # Min-max normalise to [0, 1] so relevance dominates over usefulness/recency.
    if base_scores:
        lo = min(base_scores.values())
        span = max(base_scores.values()) - lo
        if span > 0:
            base_scores = {mid: (s - lo) / span for mid, s in base_scores.items()}
        else:
            base_scores = dict.fromkeys(base_scores, 1.0)

    return base_scores


# ---------------------------------------------------------------------------
# Public API: collect_scores (traced score-stage collection)
# ---------------------------------------------------------------------------


def collect_scores(
    *,
    fts_fn: Callable[[], dict[str, float]],
    trigram_fn: Callable[[], dict[str, float]],
    vector_fn: Callable[[], dict[str, float]],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Run the three score stages, each traced and timed by ``search_phase``.

    Returns ``(fts, trigram, vector)``. Each stage runs inside its
    ``mintmory.search.<phase>`` span and reports its result count, so a stage with
    nothing to do still records a span with ``mintmory.result_count`` = 0 and a
    latency point. Shared by both storage backends; ``anchor_candidates`` calls the
    score methods directly, so note anchoring records no search phase.
    """
    with telemetry.search_phase("fts") as handle:
        fts_scores = fts_fn()
        handle.set_count(len(fts_scores))
    with telemetry.search_phase("substring") as handle:
        trigram_scores = trigram_fn()
        handle.set_count(len(trigram_scores))
    with telemetry.search_phase("vector") as handle:
        vector_scores = vector_fn()
        handle.set_count(len(vector_scores))
    return fts_scores, trigram_scores, vector_scores


# ---------------------------------------------------------------------------
# Public API: fuse_and_search (full search pipeline)
# ---------------------------------------------------------------------------


def fuse_and_search(
    *,
    request: SearchRequest,
    fts_scores: dict[str, float],
    trigram_scores: dict[str, float],
    vector_scores: dict[str, float],
    vector_rrf_weight: float,
    load_memories_fn: Callable[[list[str]], list[MemoryRecord]],
    bump_retrieval_fn: Callable[[list[str], datetime], None],
    create_session_fn: Callable[[QuerySession], QuerySession],
    record_query_results_fn: Callable[[list[QueryResult]], None],
    get_annotating_notes_fn: Callable[[str, int], list[MemoryRecord]],
    search_around_fn: Callable[[list[str], SearchAroundSpec], list[str]],
    note_bonus: float,
    auto_include_cap: int,
    now: datetime,
    tenant_id: str | None = None,
    record_session: bool = True,
) -> SearchResponse:
    """
    Backend-independent fusion + scoring pipeline.

    Backends call this after computing their three score dicts, passing their
    own data-access methods as callables.  The entire fusion / filtering /
    session-recording / retrieval-bumping logic lives here so it is identical
    across all backends.
    """
    if tenant_id is not None or record_session is not True:
        raise NotImplementedError
    with telemetry.search_phase("fusion") as handle:
        base_scores = _merge_and_normalise(
            fts_scores, trigram_scores, vector_scores, vector_rrf_weight
        )

        candidate_ids = list(base_scores.keys())
        memories = load_memories_fn(candidate_ids)

        filt = request.filter or MemoryFilter()

        scored: list[tuple[float, MemoryRecord]] = []
        for mem in memories:
            if not _passes_filter(mem, filt, request.include_archived):
                continue
            eff = scoring.effective_score(
                base_relevance=base_scores.get(mem.id, 0.0),
                usefulness_score=mem.usefulness_score,
                staleness_score=mem.staleness_score,
                last_accessed_at=mem.last_accessed_at,
                now=now,
                is_note=mem.is_note,
                note_bonus=note_bonus,
            )
            scored.append((eff, mem))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        primary = [mem for _, mem in scored[: request.limit]]

        # Graph traversal union (anchors always kept).
        around_ids: list[str] = []
        if request.search_around is not None and primary:
            anchor_ids = [mem.id for mem in primary]
            around_ids = search_around_fn(anchor_ids, request.search_around)
            existing = {mem.id for mem in primary}
            for extra in load_memories_fn(around_ids):
                if extra.id not in existing:
                    primary.append(extra)
                    existing.add(extra.id)

        # Auto-include notes annotating each primary result (separate channel).
        notes_on_results: dict[str, list[MemoryRecord]] = {}
        if auto_include_cap > 0:
            for mem in primary:
                annotating = get_annotating_notes_fn(mem.id, auto_include_cap)
                if annotating:
                    notes_on_results[mem.id] = annotating

        # Decision lineage: persist session + results, bump retrieval counters.
        session = QuerySession(query_text=request.query)
        create_session_fn(session)
        results = [
            QueryResult(
                session_id=session.id,
                memory_id=mem.id,
                relevance_score=base_scores.get(mem.id, 0.0),
            )
            for mem in primary
        ]
        record_query_results_fn(results)
        bump_retrieval_fn([mem.id for mem in primary], now)

        response = SearchResponse(
            session_id=session.id,
            memories=primary,
            total_found=len(primary),
            search_around_ids=around_ids,
            notes_on_results=notes_on_results,
        )
        handle.set_count(len(response.memories))
    return response


# ---------------------------------------------------------------------------
# Public API: fuse_and_rank (anchor_candidates — side-effect-free)
# ---------------------------------------------------------------------------


def fuse_and_rank(
    *,
    fts_scores: dict[str, float],
    trigram_scores: dict[str, float],
    vector_scores: dict[str, float],
    vector_rrf_weight: float,
    load_memories_fn: Callable[[list[str]], list[MemoryRecord]],
    limit: int,
) -> list[tuple[float, MemoryRecord]]:
    """
    Fuse score sources and return (score, record) pairs sorted best-first.

    Used by anchor_candidates() — does NOT create a QuerySession, does NOT
    record query_results, and does NOT bump retrieval counters.
    """
    base_scores = _merge_and_normalise(fts_scores, trigram_scores, vector_scores, vector_rrf_weight)

    candidate_ids = list(base_scores.keys())
    memories = load_memories_fn(candidate_ids)
    scored = [(base_scores.get(m.id, 0.0), m) for m in memories]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:limit]
