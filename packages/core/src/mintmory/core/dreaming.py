"""
Dreaming consolidation engine (ROADMAP M5 + M8, FEATURES.md §9).

The ``DreamingEngine`` runs an offline consolidation pass over the memory store.
Every step is **idempotent** (AGENTS.md §4.4): running the engine twice on an
unchanged database produces the same ``DreamReport``, with ``new_links == 0`` and
``new_summaries == 0`` on the second run.

Two intensities:

  * ``run_light``  — steps 1–3 (anomaly detection, concept linking, summary gen).
  * ``run_full``   — steps 1–6 (light + contradiction resolution, archival,
    rehabilitation).

LLM-dependent steps take an INJECTED callable so tests stay deterministic (no
network, no real model):

  * ``summarizer(concept, contents) -> str``  produces a concept summary. If
    ``None``, step 3 is skipped (count 0).
  * ``conflict_resolver(record) -> list[BatchResolutionAction]`` resolves a
    flagged memory for non-note pairs. If ``None``, the deterministic note-authority
    pass (§6b) still runs — it does NOT depend on the LLM; only non-note-vs-non-note
    pairs are left unresolved when no resolver is configured.

All timing uses ``time.perf_counter`` (monotonic) so tests never depend on the
wall clock.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from itertools import combinations
from typing import TYPE_CHECKING

from mintmory.core import scoring, telemetry
from mintmory.core.config import LinkSettings, SummarySettings
from mintmory.core.storage import _utcnow
from mintmory.core.types import (
    AnomalyReport,
    BatchResolutionAction,
    ConceptLink,
    ConceptLinkType,
    DreamIntensity,
    DreamReport,
    LinkSource,
    MemoryRecord,
    MemorySummary,
    SummaryJob,
)

if TYPE_CHECKING:
    from mintmory.core.storage import StorageAdapter

# Anomaly-detection thresholds (FEATURES.md §9, Step 1).
HIGH_STALENESS_MIN: float = 6.0
HIGH_USEFULNESS_MIN: float = 5.0
NEVER_ACCESSED_DAYS: int = 7

# Archival window (FEATURES.md §9, Step 5).
ARCHIVE_INACTIVE_DAYS: int = 30

# Rehabilitation "retrieved recently" window (FEATURES.md §9, Step 6).
REHAB_RECENT_DAYS: int = 7

Summarizer = Callable[[str, list[str]], str]
ConflictResolver = Callable[[MemoryRecord], list[BatchResolutionAction]]


@dataclass(frozen=True)
class _LinkCandidate:
    """A candidate ``relates_to`` link between two active memories."""

    src: str
    tgt: str
    entity: str  # deterministic representative shared entity
    shared_count: int  # number of surviving shared entities
    strength: float


@dataclass(frozen=True)
class _SummarySelection:
    """One concept selected for summarisation, with summarizer-ready inputs.

    ``memory_count`` is the number of active, non-archived memories that mention
    the (non-stoplisted) concept — i.e. ``len`` of the contents collected for the
    concept BEFORE the ``max_contents`` cap. ``contents`` is the truncated,
    capped list actually fed to a summarizer. ``memory_ids`` are the ids of the
    contributing memories, in the same scan order, capped to ``max_contents``
    (parallel to ``contents``)."""

    concept: str
    contents: list[str]  # truncated to max_content_chars, capped to max_contents
    memory_count: int  # full active count for the concept (pre-cap)
    memory_ids: list[str]  # contributing memory ids, scan order, capped to max_contents


class DreamingEngine:
    """Offline, idempotent memory consolidation over a ``StorageAdapter``."""

    def __init__(
        self,
        adapter: StorageAdapter,
        summarizer: Summarizer | None = None,
        conflict_resolver: ConflictResolver | None = None,
        link_settings: LinkSettings | None = None,
        summary_settings: SummarySettings | None = None,
    ) -> None:
        self.adapter = adapter
        self.summarizer = summarizer
        self.conflict_resolver = conflict_resolver
        # Defaults reproduce today's behaviour (see config.py / EXPERIMENTS.md §2).
        self.link_settings = link_settings if link_settings is not None else LinkSettings()
        self.summary_settings = (
            summary_settings if summary_settings is not None else SummarySettings()
        )

    # ------------------------------------------------------------------
    # Public entrypoints
    # ------------------------------------------------------------------

    def run_light(self) -> DreamReport:
        """Run steps 1–3 (anomaly detection, linking, summaries)."""
        start = time.perf_counter()
        with telemetry.span("mintmory.dream.light") as sp:
            anomalies = self._detect_anomalies_traced()
            new_links = self._create_concept_links_traced()
            new_summaries = self._generate_summaries_traced()
            duration_ms = (time.perf_counter() - start) * 1000.0
            sp.set_attribute("new_links", new_links)
            sp.set_attribute("new_summaries", new_summaries)
            sp.set_attribute("contradictions_resolved", 0)
            sp.set_attribute("archived", 0)
            sp.set_attribute("rehabilitated", 0)
            telemetry.record_value(
                "mintmory.dream.duration_ms",
                duration_ms,
                intensity=DreamIntensity.LIGHT.value,
            )
        return DreamReport(
            intensity=DreamIntensity.LIGHT,
            duration_ms=duration_ms,
            new_links=new_links,
            new_summaries=new_summaries,
            anomalies=anomalies,
        )

    def run_full(self) -> DreamReport:
        """Run steps 1–6 (light + resolution + archival + rehabilitation)."""
        start = time.perf_counter()
        with telemetry.span("mintmory.dream.full") as sp:
            anomalies = self._detect_anomalies_traced()
            new_links = self._create_concept_links_traced()
            new_summaries = self._generate_summaries_traced()
            resolved = self._resolve_contradictions_traced()
            archived = self._archive_stale_traced()
            rehabilitated = self._rehabilitate_traced()
            duration_ms = (time.perf_counter() - start) * 1000.0
            sp.set_attribute("new_links", new_links)
            sp.set_attribute("new_summaries", new_summaries)
            sp.set_attribute("contradictions_resolved", resolved)
            sp.set_attribute("archived", archived)
            sp.set_attribute("rehabilitated", rehabilitated)
            telemetry.record_value(
                "mintmory.dream.duration_ms",
                duration_ms,
                intensity=DreamIntensity.FULL.value,
            )
        return DreamReport(
            intensity=DreamIntensity.FULL,
            duration_ms=duration_ms,
            new_links=new_links,
            new_summaries=new_summaries,
            contradictions_resolved=resolved,
            memories_archived=archived,
            memories_rehabilitated=rehabilitated,
            anomalies=anomalies,
        )

    # ------------------------------------------------------------------
    # Per-step telemetry wrappers (no behaviour change; no-op unless enabled)
    # ------------------------------------------------------------------
    # Each wrapper opens a ``mintmory.dream.step`` span tagged with the step
    # name and the step's count attribute. The public step methods stay pure
    # (and directly unit-tested), so wrapping is confined to the orchestrators.

    def _detect_anomalies_traced(self) -> AnomalyReport:
        with telemetry.span("mintmory.dream.step", step="anomaly") as sp:
            anomalies = self.detect_anomalies()
            sp.set_attribute(
                "count",
                len(anomalies.high_staleness_useful)
                + len(anomalies.never_accessed)
                + len(anomalies.contradictions),
            )
            return anomalies

    def _create_concept_links_traced(self) -> int:
        with telemetry.span("mintmory.dream.step", step="link") as sp:
            count = self.create_concept_links()
            sp.set_attribute("count", count)
            return count

    def _generate_summaries_traced(self) -> int:
        with telemetry.span("mintmory.dream.step", step="summary") as sp:
            count = self.generate_summaries()
            sp.set_attribute("count", count)
            return count

    def _resolve_contradictions_traced(self) -> int:
        with telemetry.span("mintmory.dream.step", step="resolve") as sp:
            count = self.resolve_contradictions()
            sp.set_attribute("count", count)
            return count

    def _archive_stale_traced(self) -> int:
        with telemetry.span("mintmory.dream.step", step="archive") as sp:
            count = self.archive_stale()
            sp.set_attribute("count", count)
            return count

    def _rehabilitate_traced(self) -> int:
        with telemetry.span("mintmory.dream.step", step="rehab") as sp:
            count = self.rehabilitate()
            sp.set_attribute("count", count)
            return count

    # ------------------------------------------------------------------
    # Step 1 — anomaly detection (READ-ONLY)
    # ------------------------------------------------------------------

    def detect_anomalies(self) -> AnomalyReport:
        """
        Read-only anomaly scan (FEATURES.md §9, Step 1). No writes.

        * ``high_staleness_useful`` — staleness >= 6.0 AND usefulness >= 5.0
          (contradictory signals — needs review). Notes (is_note=1) are excluded
          (§6a invariant: notes are never auto-stale).
        * ``never_accessed`` — active, ``retrieval_count = 0`` AND ``created_at``
          older than 7 days. Notes (is_note=1) are excluded.
        * ``contradictions`` — ``flagged_for_review = 1``. Notes CAN appear here
          (contested notes surface for human review via §5d / §6b).
        """
        conn = self.adapter.connect()

        high_rows = conn.execute(
            "SELECT id FROM memories "
            "WHERE staleness_score >= ? AND usefulness_score >= ? "
            "AND is_archived = 0 "
            "AND is_note = 0 "  # §6a: notes are exempt from staleness anomaly reports
            "ORDER BY id",
            (HIGH_STALENESS_MIN, HIGH_USEFULNESS_MIN),
        ).fetchall()
        high_staleness_useful = [row["id"] for row in high_rows]

        cutoff = (_utcnow() - timedelta(days=NEVER_ACCESSED_DAYS)).isoformat()
        never_rows = conn.execute(
            "SELECT id FROM memories "
            "WHERE retrieval_count = 0 AND created_at < ? "
            "AND is_active = 1 AND is_archived = 0 "
            "AND is_note = 0 "  # §6a: notes are exempt from never-accessed anomaly reports
            "ORDER BY id",
            (cutoff,),
        ).fetchall()
        never_accessed = [row["id"] for row in never_rows]

        flagged_rows = conn.execute(
            "SELECT id FROM memories WHERE flagged_for_review = 1 ORDER BY id"
        ).fetchall()
        contradictions = [row["id"] for row in flagged_rows]

        return AnomalyReport(
            high_staleness_useful=high_staleness_useful,
            never_accessed=never_accessed,
            contradictions=contradictions,
        )

    # ------------------------------------------------------------------
    # Step 2 — concept linking (idempotent via INSERT OR IGNORE)
    # ------------------------------------------------------------------

    def create_concept_links(self) -> int:
        """
        For each pair of ACTIVE memories sharing an entity, create a
        ``relates_to`` link (source='extraction') if absent.

        Behaviour is parameterised by ``self.link_settings`` (EXPERIMENTS.md §2);
        the defaults reproduce today's graph: ``min_shared_entities=1``,
        ``entity_df_cap_ratio=1.0`` (off), ``max_per_node=0`` (unbounded),
        empty stoplist, ``min_jaccard=0.0`` (off), flat strength 0.5.

        Filters are applied, in order, BEFORE forming a pair:
          1. drop stoplisted entities from the linking signal;
          2. if ``entity_df_cap_ratio < 1.0``, drop entities whose document
             frequency over active memories exceeds ``ratio * active_count``;
          3. a pair links only if it shares ``>= min_shared_entities`` of the
             surviving entities AND, if ``min_jaccard > 0``, entity-set
             Jaccard ``>= min_jaccard``;
          4. strength is IDF-weighted (clamped 0..1) when
             ``idf_weighted_strength`` is set, else flat 0.5;
          5. if ``max_per_node > 0``, keep each node's strongest links by a
             deterministic key so a re-run is idempotent.

        Counts ONLY newly-created links — existence is pre-checked against the
        current link set so a second run on an unchanged DB returns 0.
        """
        ls = self.link_settings
        stoplist = ls.stoplist
        conn = self.adapter.connect()
        rows = conn.execute(
            "SELECT id, entity_ids FROM memories WHERE is_active = 1 AND is_archived = 0"
        ).fetchall()

        # Per-memory surviving entity sets (after the stoplist drop), and the
        # DF (document frequency) of each entity over active memories.
        mem_entities: dict[str, set[str]] = {}
        entity_df: dict[str, int] = defaultdict(int)
        for row in rows:
            mem_record = self.adapter.get_memory(row["id"])
            if mem_record is None:
                continue
            kept = {e for e in mem_record.entity_ids if e not in stoplist}
            mem_entities[mem_record.id] = kept
            for entity in kept:
                entity_df[entity] += 1

        active_count = len(mem_entities)

        # DF cap: drop entities present in more than ratio*active_count active
        # memories from the linking signal (computed once per run).
        if ls.entity_df_cap_ratio < 1.0:
            df_threshold = ls.entity_df_cap_ratio * active_count
            dropped = {e for e, df in entity_df.items() if df > df_threshold}
            if dropped:
                mem_entities = {mid: (ents - dropped) for mid, ents in mem_entities.items()}

        # IDF of each surviving entity (smoothed) — used for IDF-weighted
        # strength. Recompute DF over the post-drop signal for consistency.
        idf: dict[str, float] = {}
        if ls.idf_weighted_strength:
            post_df: dict[str, int] = defaultdict(int)
            for ents in mem_entities.values():
                for entity in ents:
                    post_df[entity] += 1
            for entity, df in post_df.items():
                idf[entity] = math.log((active_count + 1) / (df + 1)) + 1.0

        # Map each surviving entity -> memory ids that mention it.
        entity_to_ids: dict[str, set[str]] = defaultdict(set)
        for mid, ents in mem_entities.items():
            for entity in ents:
                entity_to_ids[entity].add(mid)

        # Aggregate candidate pairs: shared entity set per unordered pair.
        pair_shared: dict[tuple[str, str], set[str]] = defaultdict(set)
        for entity, ids in entity_to_ids.items():
            if len(ids) < 2:
                continue
            for src, tgt in combinations(sorted(ids), 2):
                pair_shared[(src, tgt)].add(entity)

        # Existing relates_to pairs (order-insensitive) — pre-check so the count
        # reflects only genuinely-new links even though add_link is INSERT OR IGNORE.
        existing_pairs: set[frozenset[str]] = set()
        for link_row in conn.execute(
            "SELECT source_memory_id, target_memory_id FROM concept_links WHERE link_type = ?",
            (ConceptLinkType.RELATES_TO.value,),
        ).fetchall():
            existing_pairs.add(
                frozenset({link_row["source_memory_id"], link_row["target_memory_id"]})
            )

        # Build the candidate list applying the min-shared and Jaccard gates,
        # computing each candidate's strength and a representative entity.
        candidates: list[_LinkCandidate] = []
        for (src, tgt), shared in pair_shared.items():
            shared_count = len(shared)
            if shared_count < ls.min_shared_entities:
                continue
            if ls.min_jaccard > 0.0:
                union = mem_entities[src] | mem_entities[tgt]
                jaccard = shared_count / len(union) if union else 0.0
                if jaccard < ls.min_jaccard:
                    continue
            if ls.idf_weighted_strength:
                # Normalised summed IDF of the shared entities, clamped 0..1.
                summed = sum(idf.get(e, 1.0) for e in shared)
                max_idf = math.log((active_count + 1) / 1.0) + 1.0
                norm = summed / (shared_count * max_idf) if max_idf > 0 else 0.0
                strength = max(0.0, min(1.0, norm))
            else:
                strength = 0.5
            # Deterministic representative entity (stable across runs).
            entity = sorted(shared)[0]
            candidates.append(
                _LinkCandidate(
                    src=src,
                    tgt=tgt,
                    entity=entity,
                    shared_count=shared_count,
                    strength=strength,
                )
            )

        # max_per_node greedy cap: keep each node's strongest links by a
        # DETERMINISTIC key so the kept set is identical across runs.
        if ls.max_per_node > 0:
            candidates = self._cap_per_node(
                candidates,
                ls.max_per_node,
                hub_cap_multiplier=ls.hub_cap_multiplier,
                hub_degree_percentile=ls.hub_degree_percentile,
            )

        created = 0
        seen_pairs: set[frozenset[str]] = set()
        for cand in candidates:
            pair = frozenset({cand.src, cand.tgt})
            if pair in seen_pairs or pair in existing_pairs:
                continue
            seen_pairs.add(pair)
            self.adapter.add_link(
                ConceptLink(
                    source_memory_id=cand.src,
                    target_memory_id=cand.tgt,
                    link_type=ConceptLinkType.RELATES_TO,
                    entity=cand.entity,
                    strength=cand.strength,
                    source=LinkSource.EXTRACTION,
                )
            )
            existing_pairs.add(pair)
            created += 1

        return created

    @staticmethod
    def _cap_per_node(
        candidates: list[_LinkCandidate],
        max_per_node: int,
        *,
        hub_cap_multiplier: float = 1.0,
        hub_degree_percentile: float = 0.9,
    ) -> list[_LinkCandidate]:
        """Keep each node's strongest links using deterministic order ``(-shared_count,
        -strength, src, tgt)``.

        A link survives only if it fits within BOTH endpoints' effective budgets, so
        the result is symmetric and idempotent across runs on an unchanged DB.

        When ``hub_cap_multiplier <= 1.0`` (the default) the method behaves EXACTLY as
        the original uniform cap — no hub computation is performed.  When
        ``hub_cap_multiplier > 1.0`` nodes whose candidate-degree meets or exceeds the
        ``hub_degree_percentile`` nearest-rank threshold receive a larger budget of
        ``int(max_per_node * hub_cap_multiplier)`` links, letting hub concepts retain
        the cluster-connecting edges that a flat cap would sever.
        """
        ordered = sorted(
            candidates,
            key=lambda c: (-c.shared_count, -c.strength, c.src, c.tgt),
        )

        # No-op fast path: uniform cap, behaviour byte-identical to the original.
        if hub_cap_multiplier <= 1.0:
            degree: dict[str, int] = defaultdict(int)
            kept: list[_LinkCandidate] = []
            for cand in ordered:
                if degree[cand.src] >= max_per_node or degree[cand.tgt] >= max_per_node:
                    continue
                kept.append(cand)
                degree[cand.src] += 1
                degree[cand.tgt] += 1
            return kept

        # Hub-aware path -------------------------------------------------------
        # 1. Candidate-degree: number of candidates incident to each node.
        cand_degree: dict[str, int] = defaultdict(int)
        for cand in candidates:
            cand_degree[cand.src] += 1
            cand_degree[cand.tgt] += 1

        # 2. Hub threshold via nearest-rank at hub_degree_percentile.
        degs = sorted(cand_degree.values())
        threshold = degs[min(len(degs) - 1, math.floor(hub_degree_percentile * len(degs)))]

        # 3. Effective cap per node.
        hub_cap = int(max_per_node * hub_cap_multiplier)

        def _effective_cap(node: str) -> int:
            return hub_cap if cand_degree[node] >= threshold else max_per_node

        # 4. Greedy keep in the same deterministic order.
        used: dict[str, int] = defaultdict(int)
        hub_kept: list[_LinkCandidate] = []
        for cand in ordered:
            if used[cand.src] >= _effective_cap(cand.src) or used[cand.tgt] >= _effective_cap(
                cand.tgt
            ):
                continue
            hub_kept.append(cand)
            used[cand.src] += 1
            used[cand.tgt] += 1
        return hub_kept

    # ------------------------------------------------------------------
    # Step 3 — summary generation (idempotent via INSERT OR REPLACE on concept)
    # ------------------------------------------------------------------

    def _select_summary_concepts(self) -> list[_SummarySelection]:
        """Shared concept-selection + content-preparation for L3 summaries.

        Implements the EXACT selection currently inline in ``generate_summaries``
        (see design §0): active non-archived memories scanned ``ORDER BY id`` and
        reloaded via ``get_memory``; per-concept contents collected for every
        non-stoplisted entity; concepts kept when their content count >=
        ``summary_settings.min_memories``; ``top_k`` cap (deterministic tiebreak by
        concept); per-concept ``max_content_chars`` truncation then ``max_contents``
        cap. Returns one ``_SummarySelection`` per kept concept in final sorted
        concept order. Pure read — no writes, no summarizer/LLM call.
        """
        ss = self.summary_settings
        stoplist = self.link_settings.stoplist
        conn = self.adapter.connect()
        rows = conn.execute(
            "SELECT id, content, entity_ids FROM memories "
            "WHERE is_active = 1 AND is_archived = 0 ORDER BY id"
        ).fetchall()

        entity_to_contents: dict[str, list[str]] = defaultdict(list)
        entity_to_ids: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            mem_record = self.adapter.get_memory(row["id"])
            if mem_record is None:
                continue
            for entity in mem_record.entity_ids:
                if entity in stoplist:
                    continue
                entity_to_contents[entity].append(mem_record.content)
                entity_to_ids[entity].append(mem_record.id)

        # Select concepts: enough memories, not stoplisted.
        concepts = [
            concept
            for concept in sorted(entity_to_contents)
            if len(entity_to_contents[concept]) >= ss.min_memories
        ]

        # top_k cap: keep the most-evidenced concepts (deterministic tiebreak by
        # concept name so the kept set is stable across runs).
        if ss.top_k > 0 and len(concepts) > ss.top_k:
            concepts.sort(key=lambda c: (-len(entity_to_contents[c]), c))
            concepts = sorted(concepts[: ss.top_k])

        # Prepare the per-concept summarizer inputs (truncation + content cap)
        # once, in deterministic concept order. ``concepts`` is already sorted.
        selections: list[_SummarySelection] = []
        for concept in concepts:
            all_contents = entity_to_contents[concept]
            all_ids = entity_to_ids[concept]
            memory_count = len(all_contents)
            contents = all_contents
            if ss.max_content_chars > 0:
                contents = [c[: ss.max_content_chars] for c in contents]
            contents = contents[: ss.max_contents]
            memory_ids = all_ids[: ss.max_contents]
            selections.append(
                _SummarySelection(
                    concept=concept,
                    contents=contents,
                    memory_count=memory_count,
                    memory_ids=memory_ids,
                )
            )

        return selections

    def generate_summaries(self) -> int:
        """
        For each entity appearing in ``>= summary_min_memories`` active memories,
        call the injected summarizer over the memories' content and upsert a
        ``MemorySummary``.

        Behaviour is parameterised by ``self.summary_settings`` (and the linking
        stoplist); defaults reproduce today's behaviour (``min_memories=3``,
        ``top_k=0`` uncapped, ``max_contents=20``, ``max_content_chars=0``).

        §6c invariant: a note's content IS included in summary generation (it is
        an active, non-archived memory and provides authoritative context), but a
        note itself is NEVER replaced or archived by this step. ``generate_summaries``
        only writes ``MemorySummary`` rows and never mutates source memories.

        Concept selection (EXPERIMENTS.md §4.1):
          1. select entities with ``>= min_memories`` active memories;
          2. drop concepts in the linking stoplist;
          3. if ``top_k > 0`` keep the top_k by descending memory-count
             (deterministic tiebreak by concept name);
          4. truncate each content to ``max_content_chars`` (when > 0) and cap
             the list to ``max_contents`` before calling the summarizer.

        Returns the number of summaries created/updated. Skipped entirely
        (returns 0) when no summarizer is configured.
        """
        if self.summarizer is None:
            return 0

        ss = self.summary_settings
        prepared = self._select_summary_concepts()

        # Lever B (docs/OBSERVABILITY.md §3): when concurrency > 1 fan the
        # INDEPENDENT summarizer calls out through a bounded thread pool. The
        # number/identity of summaries is unaffected (only wall-clock changes):
        # the calls are pure with respect to the store, so we collect their
        # texts first, then write (INSERT OR REPLACE by concept) SERIALLY in
        # deterministic concept order. concurrency == 1 keeps the exact serial
        # path (no executor created), preserving today's behaviour and the
        # simple summarizer contract for unit tests.
        summarizer = self.summarizer
        if ss.concurrency > 1 and len(prepared) > 1:
            with ThreadPoolExecutor(max_workers=ss.concurrency) as pool:
                summary_texts = list(
                    pool.map(lambda sel: summarizer(sel.concept, sel.contents), prepared)
                )
        else:
            summary_texts = [summarizer(sel.concept, sel.contents) for sel in prepared]

        count = 0
        for sel, summary_text in zip(prepared, summary_texts, strict=True):
            # Idempotency (AGENTS.md §4.4): an unchanged DB must yield 0 on a
            # re-run. Skip the upsert (and the count) when an identical summary
            # already exists for this concept.
            existing = self.adapter.get_summary(sel.concept)
            if (
                existing is not None
                and existing.summary_text == summary_text
                and existing.memory_count == sel.memory_count
            ):
                continue
            self.adapter.upsert_summary(
                MemorySummary(
                    concept=sel.concept,
                    summary_text=summary_text,
                    memory_count=sel.memory_count,
                )
            )
            count += 1

        return count

    def collect_summary_jobs(self, include_all: bool = False) -> list[SummaryJob]:
        """Return the L3 concept-summary jobs for the active agent to write.

        Uses the SAME concept selection as ``generate_summaries`` (the shared
        ``_select_summary_concepts`` helper), so the set of candidate concepts and
        their truncated/capped contents are identical to what the configured-LLM path
        would summarise. Does NOT call any summarizer/LLM and does NOT require one
        configured (works with provider=none).

        By DEFAULT (``include_all=False``) returns only concepts that NEED a
        (re)summary — i.e. one of:
          * no current ``MemorySummary`` exists for the concept, OR
          * the stored summary's ``memory_count`` != the concept's current active
            count (the evidence drifted; the summary is out of date).
        With ``include_all=True`` returns one ``SummaryJob`` per qualifying concept
        regardless of existing summaries. Order is the helper's sorted concept order.
        """
        jobs: list[SummaryJob] = []
        for sel in self._select_summary_concepts():
            existing = self.adapter.get_summary(sel.concept)
            if not include_all:
                needs = existing is None or existing.memory_count != sel.memory_count
                if not needs:
                    continue
            jobs.append(
                SummaryJob(
                    concept=sel.concept,
                    memory_ids=sel.memory_ids,
                    contents=sel.contents,
                    memory_count=sel.memory_count,
                    current_summary=existing.summary_text if existing is not None else None,
                )
            )
        return jobs

    def _active_count_for_concept(self, concept: str) -> int:
        """Active, non-archived memory count for one concept, using the SAME rule as
        summary selection: a memory counts iff it is active + non-archived AND its
        ``entity_ids`` contain ``concept`` AND ``concept`` is not in the linking
        stoplist. Returns 0 for a stoplisted concept or one with no active memories.
        """
        if concept in self.link_settings.stoplist:
            return 0
        conn = self.adapter.connect()
        rows = conn.execute(
            "SELECT id FROM memories WHERE is_active = 1 AND is_archived = 0 ORDER BY id"
        ).fetchall()
        count = 0
        for row in rows:
            mem = self.adapter.get_memory(row["id"])
            if mem is None:
                continue
            count += sum(1 for e in mem.entity_ids if e == concept)
        return count

    def apply_summary(self, concept: str, summary_text: str) -> MemorySummary:
        """Persist an AGENT-SUPPLIED summary for one concept (BYO-LLM L3).

        Builds a ``MemorySummary`` with ``memory_count`` recomputed from the concept's
        CURRENT active count (the same count ``_select_summary_concepts`` would
        report) and ``is_current=True``, ``generated_at`` defaulted to now, then
        persists it via ``adapter.upsert_summary`` (INSERT OR REPLACE keyed on
        ``concept``). Idempotent: re-applying overwrites the concept's summary.

        Calls no summarizer/LLM; works with provider=none. The ``summary_text`` is
        stored verbatim (the agent already produced clean prose — no ``<think>``
        stripping, no prompt). Whitespace is left to the caller.
        """
        memory_count = self._active_count_for_concept(concept)
        return self.adapter.upsert_summary(
            MemorySummary(
                concept=concept,
                summary_text=summary_text,
                memory_count=memory_count,
            )
        )

    # ------------------------------------------------------------------
    # Step 4 — contradiction resolution (FULL only, idempotent via flag guard)
    # ------------------------------------------------------------------

    def resolve_contradictions(self) -> int:
        """
        For each ``flagged_for_review`` memory, run the deterministic note-authority
        pass first (§6b), then fall through to the injected resolver for non-note pairs.

        Note-authority pass (deterministic, works with ``provider=none``):
          - note vs non-note   → note wins: ``supersede_memory(other, by=note)``,
                                 clears flag on note (§6b cases 1–2, counts as resolved).
          - note vs note        → both stay flagged, breadcrumb added; NOT resolved
                                  (§6b case 3; skips the LLM resolver for this pair).
          - non-note vs non-note → falls through to the injected ``conflict_resolver``
                                   if configured, else left unchanged (§6b case 4).

        Idempotent (§9): supersede + flag-clear means a re-run sees no flagged memories
        for previously-resolved pairs; note-vs-note breadcrumb write is conditional so
        counts do not drift across repeated runs.

        The early-return ``if conflict_resolver is None`` is REMOVED (§6b): the
        authority pass runs regardless of whether an LLM resolver is configured.
        """
        resolved = 0
        for flagged in self.adapter.get_flagged_memories():
            # Guard: skip memories whose flag was already cleared (defensive —
            # get_flagged_memories already filters, but a resolver action could
            # have touched another flagged record earlier in the loop).
            current = self.adapter.get_memory(flagged.id)
            if current is None or not current.flagged_for_review:
                continue

            # ------------------------------------------------------------------
            # §6b — deterministic note-authority pass (runs even with no resolver)
            # ------------------------------------------------------------------
            handled, delta = self._apply_note_authority(current)
            if handled:
                resolved += delta  # delta=1 only for cases 1-2 (supersede); 0 otherwise
                continue

            # ------------------------------------------------------------------
            # §6b case 4 — non-note vs non-note: delegate to injected resolver
            # ------------------------------------------------------------------
            if self.conflict_resolver is None:
                # No resolver and not a note conflict → leave flagged (unchanged
                # from the old ``return 0`` path for this specific record).
                continue

            actions = self.conflict_resolver(current)
            for action in actions:
                self._apply_resolution(current, action)

            # Re-fetch: the flagged memory may have been archived by a DELETE
            # action targeting itself. Only clear the flag if it still exists
            # and is not archived (archive_memory does not touch the flag).
            after = self.adapter.get_memory(flagged.id)
            if after is not None and after.flagged_for_review:
                self.adapter.update_memory(flagged.id, flagged_for_review=False)
            resolved += 1

        return resolved

    def _apply_note_authority(self, current: MemoryRecord) -> tuple[bool, int]:
        """
        §6b deterministic note-authority resolution for one ``flagged_for_review``
        record. Returns ``(handled, resolved_delta)``: ``handled`` True means this
        record was dealt with by the authority pass (skip the LLM resolver);
        ``resolved_delta`` is 1 ONLY for cases 1-2 (an actual supersede) and 0 for
        case 3 (note-vs-note, deferred) and the lone-flagged-note guard, so the
        resolved count does not drift across runs (§9). Case 4 returns
        ``(False, 0)`` to fall through to the LLM resolver.

        Cases:
          1. ``current`` is a note, the contradicting ``other`` is not →
             note wins: supersede ``other`` by ``current``, clear ``current``'s flag.
          2. ``current`` is not a note, the contradicting ``other`` IS a note →
             note wins: supersede ``current`` by ``other``, clear ``other``'s flag.
          3. both are notes → leave both flagged; add ``metadata['note_conflict_with']``
             breadcrumb (conditional, idempotent) on each; return 1 (handled — no LLM
             resolver for note-vs-note).
          4. neither is a note → return 0 (fall through to existing resolver).

        A flagged note with EMPTY ``contradicts_ids`` and no resolver stays flagged
        (correct: it was flagged by a stale-vote per §5d and awaits human review).
        Returns 1 in that case ONLY when both sides are notes; otherwise 0 so the
        resolver path can run (but with an empty contradicts_ids it will NONE-action).
        """
        # Collect the other side(s) from contradicts_ids.  We resolve the FIRST
        # non-archived other we can load; additional contradictions are left for a
        # subsequent run (idempotent behaviour is preserved because supersede clears
        # the flag and removes the pair from flagged_memories on the next pass).
        other: MemoryRecord | None = None
        for other_id in current.contradicts_ids:
            candidate = self.adapter.get_memory(other_id)
            if candidate is not None and not candidate.is_archived:
                other = candidate
                break

        # If no loadable other exists, we cannot apply authority.  Return 0 so the
        # resolver path handles it (or it is left flagged if no resolver is configured).
        # Exception: if current is a note we still return 1 to prevent the LLM resolver
        # from touching a note with an empty/archived contradiction set — it will stay
        # flagged for human review (§6b: "flagged note with EMPTY contradicts_ids").
        if other is None:
            # A note with empty/archived contradictions stays flagged for human
            # review — handled (don't run the resolver) but NOT counted (idempotent).
            return (True, 0) if current.is_note else (False, 0)

        current_is_note = current.is_note
        other_is_note = other.is_note

        # Case 4: neither is a note → fall through to resolver.
        if not current_is_note and not other_is_note:
            return (False, 0)

        # Case 3: both are notes → flag-only, no supersede, NOT counted as resolved.
        if current_is_note and other_is_note:
            # Add breadcrumb conditionally to be idempotent (§9: counts must not drift).
            self._add_note_conflict_breadcrumb(current, other.id)
            self._add_note_conflict_breadcrumb(other, current.id)
            # Both remain flagged_for_review = 1 (do NOT clear, do NOT supersede).
            return (True, 0)  # handled (skip resolver) but deferred, not resolved

        # Cases 1 & 2: one is a note, the other is not. Clear the flag on BOTH
        # endpoints (winner and the superseded loser) so neither is re-processed on
        # a later run — get_flagged_memories does not filter archived rows (§9).
        if current_is_note:
            # Case 1: current (note) wins → supersede other.
            self.adapter.supersede_memory(other.id, by_id=current.id)
            self.adapter.update_memory(current.id, flagged_for_review=False)
            if other.flagged_for_review:
                self.adapter.update_memory(other.id, flagged_for_review=False)
        else:
            # Case 2: other (note) wins → supersede current (the flagged non-note).
            self.adapter.supersede_memory(current.id, by_id=other.id)
            self.adapter.update_memory(current.id, flagged_for_review=False)
            if other.flagged_for_review:
                self.adapter.update_memory(other.id, flagged_for_review=False)

        return (True, 1)

    def _add_note_conflict_breadcrumb(self, record: MemoryRecord, conflict_with_id: str) -> None:
        """Add ``metadata['note_conflict_with']`` breadcrumb to a note (idempotent).

        The write is skipped when the breadcrumb already matches, so repeated runs
        on an unchanged DB do not increment any counters or produce redundant writes.
        """
        metadata = dict(record.metadata)
        if metadata.get("note_conflict_with") == conflict_with_id:
            return  # already set — idempotent, no write
        metadata["note_conflict_with"] = conflict_with_id
        self.adapter.update_memory(record.id, metadata=metadata)

    def _apply_resolution(
        self,
        flagged: MemoryRecord,
        action: BatchResolutionAction,
    ) -> None:
        """Apply a single ``BatchResolutionAction`` (ADD/UPDATE/DELETE/NONE)."""
        target_id = action.target_id or flagged.id
        if action.action == "DELETE":
            target = self.adapter.get_memory(target_id)
            if target is not None and not target.is_archived:
                self.adapter.archive_memory(target_id)
        elif action.action == "UPDATE":
            target = self.adapter.get_memory(target_id)
            if target is not None:
                # No new content is carried by BatchResolutionAction; record the
                # resolution reason in metadata so the lineage is auditable, and
                # clear staleness signals that triggered the review.
                metadata = dict(target.metadata)
                if action.reason:
                    metadata["resolution_reason"] = action.reason
                self.adapter.update_memory(
                    target_id,
                    metadata=metadata,
                    flagged_for_review=False,
                )
        elif action.action == "ADD":
            content = action.reason.strip()
            if content:
                self.adapter.add_memory(
                    content=content,
                    category=flagged.category,
                    source=flagged.source,
                )
        # NONE: no mutation here — the flag is cleared by the caller.

    # ------------------------------------------------------------------
    # Step 5 — archival (FULL only, idempotent via is_archived guard)
    # ------------------------------------------------------------------

    def archive_stale(self) -> int:
        """
        Archive memories that are stale, highly stale-scored, and untouched for
        a long time (FEATURES.md §9, Step 5): ``is_stale = 1`` AND
        ``staleness_score >= ARCHIVE_THRESHOLD`` (9.0) AND last accessed older
        than 30 days (or never).

        §6a invariant: notes (``is_note = 1``) are NEVER auto-archived by staleness.
        A note can only be archived explicitly ("done") via ``archive_memory``.
        Notes never reach ``is_stale = 1`` via feedback (§5d), but the ``AND
        is_note = 0`` guard here is a belt-and-suspenders defence.

        Idempotent: already-archived memories are skipped.
        """
        conn = self.adapter.connect()
        cutoff = (_utcnow() - timedelta(days=ARCHIVE_INACTIVE_DAYS)).isoformat()
        rows = conn.execute(
            "SELECT id FROM memories "
            "WHERE is_stale = 1 AND staleness_score >= ? AND is_archived = 0 "
            "AND is_note = 0 "  # §6a: notes are exempt from staleness-based archival
            "AND (last_accessed_at IS NULL OR last_accessed_at < ?) "
            "ORDER BY id",
            (scoring.ARCHIVE_THRESHOLD, cutoff),
        ).fetchall()

        archived = 0
        for row in rows:
            self.adapter.archive_memory(row["id"])
            archived += 1
        return archived

    # ------------------------------------------------------------------
    # Step 6 — rehabilitation (FULL only, idempotent via is_stale guard)
    # ------------------------------------------------------------------

    def rehabilitate(self) -> int:
        """
        Rehabilitate stale-but-still-valued memories (FEATURES.md §9, Step 6):
        ``is_stale = 1`` AND ``usefulness_score > staleness_score`` AND retrieved
        recently (``last_accessed_at`` within the last 7 days). Sets
        ``is_stale = 0`` and reduces ``staleness_score`` by ``REHAB_DELTA``
        (floor 0).

        §6a invariant: notes never become ``is_stale = 1`` via feedback (§5d routes
        stale votes to ``flagged_for_review`` instead), so this step is naturally a
        no-op for notes — no explicit exclusion needed, but documented here for clarity.

        Idempotent: already-healthy (``is_stale = 0``) memories are skipped.
        """
        conn = self.adapter.connect()
        cutoff = (_utcnow() - timedelta(days=REHAB_RECENT_DAYS)).isoformat()
        rows = conn.execute(
            "SELECT id, staleness_score FROM memories "
            "WHERE is_stale = 1 AND usefulness_score > staleness_score "
            "AND is_archived = 0 "
            "AND last_accessed_at IS NOT NULL AND last_accessed_at >= ? "
            "ORDER BY id",
            (cutoff,),
        ).fetchall()

        rehabilitated = 0
        for row in rows:
            new_staleness = max(0.0, float(row["staleness_score"]) - scoring.REHAB_DELTA)
            self.adapter.update_memory(
                row["id"],
                is_stale=False,
                staleness_score=new_staleness,
            )
            rehabilitated += 1
        return rehabilitated
