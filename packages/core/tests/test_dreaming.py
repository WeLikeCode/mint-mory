"""
Unit tests for the dreaming consolidation engine (FEATURES.md §9).

All tests use an in-memory ``StorageAdapter`` with ``embedder=None`` (FTS-only,
no model, no network) and inject deterministic fake summarizer / conflict
resolver callables. The over-arching invariant under test is idempotency
(AGENTS.md §4.4): a second run on an unchanged DB creates no new links/summaries.
"""

from __future__ import annotations

from datetime import timedelta

from mintmory.core.config import LinkSettings, SummarySettings
from mintmory.core.dreaming import DreamingEngine, _LinkCandidate
from mintmory.core.storage import StorageAdapter, _iso, _utcnow
from mintmory.core.types import (
    BatchResolutionAction,
    ConceptLinkType,
    MemoryCategory,
    MemoryRecord,
)


def _store() -> StorageAdapter:
    s = StorageAdapter(":memory:", embedder=None)
    s.initialise()
    return s


def _fake_summarizer(concept: str, contents: list[str]) -> str:
    """Deterministic summary: concept + count, no LLM."""
    return f"Summary of {concept} ({len(contents)} memories)."


def _permissive(**over: object) -> LinkSettings:
    """The old permissive linking defaults (min_shared=1, no stoplist/cap), for
    tests that exercise the linking MECHANISM independently of the production-tuned
    defaults adopted in config.py (min_shared=2 + stoplist + max_per_node=25)."""
    base: dict[str, object] = {
        "min_shared_entities": 1,
        "max_per_node": 0,
        "idf_weighted_strength": False,
        "entity_df_cap_ratio": 1.0,
        "stoplist_csv": "",
    }
    base.update(over)
    return LinkSettings(**base)  # type: ignore[arg-type]


def _backdate(store: StorageAdapter, memory_id: str, *, created_days: int) -> None:
    """Push a memory's created_at into the past (storage.update_memory can't)."""
    ts = _iso(_utcnow() - timedelta(days=created_days))
    with store.transaction() as conn:
        conn.execute(
            "UPDATE memories SET created_at = ? WHERE id = ?",
            (ts, memory_id),
        )


def _set_last_accessed(store: StorageAdapter, memory_id: str, *, days_ago: int) -> None:
    ts = _iso(_utcnow() - timedelta(days=days_ago))
    with store.transaction() as conn:
        conn.execute(
            "UPDATE memories SET last_accessed_at = ? WHERE id = ?",
            (ts, memory_id),
        )


def _add_with_entities(store: StorageAdapter, entities: list[str]) -> MemoryRecord:
    """Add a memory with an explicit entity_ids list (bypasses regex extraction)."""
    content = "Note about " + ", ".join(entities) + "."
    return store.add_memory(
        record=MemoryRecord(
            content=content,
            category=MemoryCategory.FACT,
            entity_ids=entities,
        )
    )


# ---------------------------------------------------------------------------
# Idempotency — the central invariant (AGENTS.md §4.4)
# ---------------------------------------------------------------------------


def test_dream_idempotency() -> None:
    """run_light twice: 2nd run creates no new links or summaries."""
    store = _store()
    # Three memories all sharing the "Postgres" entity (>=3 -> summary too).
    for i in range(3):
        store.add_memory(
            content=f"Postgres tuning note number {i} about Postgres.",
            category=MemoryCategory.FACT,
        )
    engine = DreamingEngine(store, summarizer=_fake_summarizer, link_settings=_permissive())

    first = engine.run_light()
    assert first.new_links > 0
    assert first.new_summaries >= 1

    second = engine.run_light()
    assert second.new_links == 0
    assert second.new_summaries == 0


def test_full_dream_idempotency() -> None:
    """run_full twice: 2nd run creates no new links."""
    store = _store()
    for i in range(3):
        store.add_memory(
            content=f"Redis cache configuration {i} for Redis.",
            category=MemoryCategory.FACT,
        )
    engine = DreamingEngine(store, summarizer=_fake_summarizer, link_settings=_permissive())

    first = engine.run_full()
    assert first.new_links > 0

    second = engine.run_full()
    assert second.new_links == 0
    assert second.new_summaries == 0


# ---------------------------------------------------------------------------
# Step 1 — anomaly detection (read-only)
# ---------------------------------------------------------------------------


def test_anomaly_detection() -> None:
    """A high-staleness/high-usefulness memory appears in the anomaly report."""
    store = _store()
    rec = store.add_memory(
        record=MemoryRecord(
            content="Stale but useful API endpoint URL https://api.example.com",
            category=MemoryCategory.FACT,
            staleness_score=8.0,
            usefulness_score=7.0,
        )
    )
    engine = DreamingEngine(store)
    report = engine.run_light()
    assert report.anomalies is not None
    assert rec.id in report.anomalies.high_staleness_useful


def test_anomaly_never_accessed() -> None:
    """An old, never-retrieved active memory is flagged as never_accessed."""
    store = _store()
    rec = store.add_memory(content="An old fact nobody has read.", category=MemoryCategory.FACT)
    _backdate(store, rec.id, created_days=10)
    engine = DreamingEngine(store)
    report = engine.run_light()
    assert report.anomalies is not None
    assert rec.id in report.anomalies.never_accessed


def test_anomaly_detection_is_read_only() -> None:
    """detect_anomalies performs no writes (stats unchanged)."""
    store = _store()
    store.add_memory(
        record=MemoryRecord(
            content="contradictory signal memory",
            category=MemoryCategory.FACT,
            staleness_score=8.0,
            usefulness_score=7.0,
            flagged_for_review=True,
        )
    )
    engine = DreamingEngine(store)
    before = store.get_stats()
    engine.detect_anomalies()
    after = store.get_stats()
    assert before == after


# ---------------------------------------------------------------------------
# Step 2 — concept linking
# ---------------------------------------------------------------------------


def test_concept_linking() -> None:
    """Two memories sharing an entity create exactly one relates_to link."""
    store = _store()
    a = store.add_memory(content="Kubernetes runs the cluster.", category=MemoryCategory.FACT)
    b = store.add_memory(content="We upgraded Kubernetes today.", category=MemoryCategory.FACT)
    engine = DreamingEngine(store, link_settings=_permissive())

    created = engine.create_concept_links()
    assert created == 1

    links = store.get_links(a.id, link_type=ConceptLinkType.RELATES_TO)
    assert len(links) == 1
    assert {links[0].source_memory_id, links[0].target_memory_id} == {a.id, b.id}
    assert links[0].source.value == "extraction"
    assert links[0].strength == 0.5
    # Idempotent second pass.
    assert engine.create_concept_links() == 0


def test_concept_linking_skips_no_shared_entity() -> None:
    """Memories with no shared entity create no links."""
    store = _store()
    store.add_memory(content="Kubernetes orchestration.", category=MemoryCategory.FACT)
    store.add_memory(content="Postgres database server.", category=MemoryCategory.FACT)
    engine = DreamingEngine(store)
    assert engine.create_concept_links() == 0


# ---------------------------------------------------------------------------
# Step 3 — summary generation
# ---------------------------------------------------------------------------


def test_summaries_require_three_memories() -> None:
    """Summary only generated for entities in >= 3 active memories."""
    store = _store()
    for i in range(3):
        store.add_memory(
            content=f"Docker container note {i} on Docker.", category=MemoryCategory.FACT
        )
    engine = DreamingEngine(store, summarizer=_fake_summarizer)
    assert engine.generate_summaries() >= 1
    summary = store.get_summary("docker")
    assert summary is not None
    assert "docker" in summary.summary_text.lower()


def test_summaries_skipped_without_summarizer() -> None:
    """No summarizer -> generate_summaries returns 0."""
    store = _store()
    for i in range(3):
        store.add_memory(content=f"Docker note {i} on Docker.", category=MemoryCategory.FACT)
    engine = DreamingEngine(store, summarizer=None)
    assert engine.generate_summaries() == 0


# ---------------------------------------------------------------------------
# Step 4 — contradiction resolution (FULL only)
# ---------------------------------------------------------------------------


def test_contradiction_resolution() -> None:
    """A flagged memory + DELETE resolver -> resolved, archived, flag cleared."""
    store = _store()
    flagged = store.add_memory(
        record=MemoryRecord(
            content="The server runs on port 8080.",
            category=MemoryCategory.FACT,
            flagged_for_review=True,
        )
    )

    def resolver(record: MemoryRecord) -> list[BatchResolutionAction]:
        return [BatchResolutionAction(action="DELETE", target_id=record.id, reason="superseded")]

    engine = DreamingEngine(store, conflict_resolver=resolver)
    resolved = engine.resolve_contradictions()
    assert resolved == 1

    after = store.get_memory(flagged.id)
    assert after is not None
    assert after.is_archived is True
    # archive does not touch the flag, but resolution leaves no flagged memories.
    assert store.get_flagged_memories() == []


def test_contradiction_resolution_update_clears_flag() -> None:
    """An UPDATE action clears the flag and records the reason in metadata."""
    store = _store()
    flagged = store.add_memory(
        record=MemoryRecord(
            content="Default timeout is 30 seconds.",
            category=MemoryCategory.FACT,
            flagged_for_review=True,
        )
    )

    def resolver(record: MemoryRecord) -> list[BatchResolutionAction]:
        return [BatchResolutionAction(action="UPDATE", target_id=record.id, reason="clarified")]

    engine = DreamingEngine(store, conflict_resolver=resolver)
    assert engine.resolve_contradictions() == 1

    after = store.get_memory(flagged.id)
    assert after is not None
    assert after.flagged_for_review is False
    assert after.metadata.get("resolution_reason") == "clarified"
    # Idempotent: nothing left flagged.
    assert engine.resolve_contradictions() == 0


def test_contradiction_resolution_skipped_without_resolver() -> None:
    """No resolver -> resolve_contradictions returns 0 and leaves the flag set."""
    store = _store()
    flagged = store.add_memory(
        record=MemoryRecord(
            content="Some flagged fact.",
            category=MemoryCategory.FACT,
            flagged_for_review=True,
        )
    )
    engine = DreamingEngine(store, conflict_resolver=None)
    assert engine.resolve_contradictions() == 0
    after = store.get_memory(flagged.id)
    assert after is not None
    assert after.flagged_for_review is True


# ---------------------------------------------------------------------------
# Step 5 — archival (FULL only)
# ---------------------------------------------------------------------------


def test_archive_stale() -> None:
    """A very stale, long-untouched memory is archived; re-run is a no-op."""
    store = _store()
    rec = store.add_memory(
        record=MemoryRecord(
            content="Ancient stale fact about XYZ.",
            category=MemoryCategory.FACT,
            is_stale=True,
            staleness_score=9.5,
        )
    )
    _set_last_accessed(store, rec.id, days_ago=60)
    engine = DreamingEngine(store)

    assert engine.archive_stale() == 1
    after = store.get_memory(rec.id)
    assert after is not None
    assert after.is_archived is True
    # Idempotent.
    assert engine.archive_stale() == 0


def test_archive_skips_recent_stale() -> None:
    """Stale + high-score but recently accessed -> NOT archived."""
    store = _store()
    rec = store.add_memory(
        record=MemoryRecord(
            content="Recently touched stale fact.",
            category=MemoryCategory.FACT,
            is_stale=True,
            staleness_score=9.5,
        )
    )
    _set_last_accessed(store, rec.id, days_ago=1)
    engine = DreamingEngine(store)
    assert engine.archive_stale() == 0


# ---------------------------------------------------------------------------
# Step 6 — rehabilitation (FULL only)
# ---------------------------------------------------------------------------


def test_rehabilitation() -> None:
    """Stale memory with usefulness>staleness + recent retrieval -> un-stale."""
    store = _store()
    rec = store.add_memory(
        record=MemoryRecord(
            content="Stale-flagged but high-value fact.",
            category=MemoryCategory.FACT,
            is_stale=True,
            staleness_score=7.0,
            usefulness_score=9.0,
        )
    )
    _set_last_accessed(store, rec.id, days_ago=2)
    engine = DreamingEngine(store)

    report = engine.run_full()
    assert report.memories_rehabilitated == 1

    after = store.get_memory(rec.id)
    assert after is not None
    assert after.is_stale is False
    assert after.staleness_score == 5.0  # 7.0 - REHAB_DELTA (2.0)
    # Idempotent: already healthy -> skipped.
    assert engine.rehabilitate() == 0


def test_rehabilitation_skips_stale_without_recent_access() -> None:
    """No recent retrieval -> rehabilitation is skipped."""
    store = _store()
    rec = store.add_memory(
        record=MemoryRecord(
            content="Stale high-value fact untouched recently.",
            category=MemoryCategory.FACT,
            is_stale=True,
            staleness_score=7.0,
            usefulness_score=9.0,
        )
    )
    _set_last_accessed(store, rec.id, days_ago=30)
    engine = DreamingEngine(store)
    assert engine.rehabilitate() == 0


# ---------------------------------------------------------------------------
# Report shape
# ---------------------------------------------------------------------------


def test_run_full_report_fields() -> None:
    """run_full populates a FULL report with non-negative timing."""
    store = _store()
    store.add_memory(content="A single fact.", category=MemoryCategory.FACT)
    engine = DreamingEngine(store, summarizer=_fake_summarizer)
    report = engine.run_full()
    assert report.intensity.value == "full"
    assert report.duration_ms >= 0.0
    assert report.anomalies is not None


# ---------------------------------------------------------------------------
# Step 2 — config-driven concept linking (EXPERIMENTS.md §2)
# ---------------------------------------------------------------------------


def test_link_min_shared_entities_reduces_links() -> None:
    """min_shared_entities=2 produces FEWER links than the default of 1.

    Fixture: a/b share TWO entities; c shares only ONE with a (and b).
    Default links all three pairs (a-b, a-c, b-c); requiring >=2 keeps only a-b.
    """
    store = _store()
    _add_with_entities(store, ["alpha", "beta"])
    _add_with_entities(store, ["alpha", "beta"])
    _add_with_entities(store, ["alpha"])

    default_engine = DreamingEngine(store, link_settings=_permissive())
    default_links = default_engine.create_concept_links()
    assert default_links == 3  # a-b, a-c, b-c (each shares >= 1)

    # Fresh DB for the stricter run so the pre-check sees no existing links.
    store2 = _store()
    a2 = _add_with_entities(store2, ["alpha", "beta"])
    b2 = _add_with_entities(store2, ["alpha", "beta"])
    _add_with_entities(store2, ["alpha"])
    strict_engine = DreamingEngine(store2, link_settings=_permissive(min_shared_entities=2))
    strict_links = strict_engine.create_concept_links()
    assert strict_links == 1  # only a-b shares two entities
    assert strict_links < default_links

    links = store2.get_links(a2.id, link_type=ConceptLinkType.RELATES_TO)
    assert len(links) == 1
    assert {links[0].source_memory_id, links[0].target_memory_id} == {a2.id, b2.id}
    # Idempotent second pass.
    assert strict_engine.create_concept_links() == 0


def test_link_stoplist_excludes_entity() -> None:
    """A stoplisted entity does not contribute to linking."""
    store = _store()
    # Two memories share ONLY the stoplisted "noise" entity -> no link.
    _add_with_entities(store, ["noise"])
    _add_with_entities(store, ["noise"])
    engine = DreamingEngine(store, link_settings=_permissive(stoplist_csv="noise"))
    assert engine.create_concept_links() == 0

    # Control: without the stoplist they DO link.
    store2 = _store()
    _add_with_entities(store2, ["noise"])
    _add_with_entities(store2, ["noise"])
    assert DreamingEngine(store2, link_settings=_permissive()).create_concept_links() == 1


def test_link_entity_df_cap_drops_ubiquitous_entity() -> None:
    """A near-ubiquitous entity is dropped from the linking signal by the DF cap."""
    store = _store()
    # "common" appears in ALL 4 memories (df=4, ratio=1.0); "rare" in only 2.
    _add_with_entities(store, ["common", "rare"])
    _add_with_entities(store, ["common", "rare"])
    _add_with_entities(store, ["common"])
    _add_with_entities(store, ["common"])

    # Baseline: every pair shares "common" -> all 6 pairs link.
    baseline = DreamingEngine(store, link_settings=_permissive()).create_concept_links()
    assert baseline == 6

    # With df_cap_ratio=0.5, "common" (df=4 > 0.5*4=2) is dropped; only the two
    # memories sharing "rare" (df=2, not > 2) still link -> 1 link.
    store2 = _store()
    _add_with_entities(store2, ["common", "rare"])
    _add_with_entities(store2, ["common", "rare"])
    _add_with_entities(store2, ["common"])
    _add_with_entities(store2, ["common"])
    capped = DreamingEngine(
        store2, link_settings=_permissive(entity_df_cap_ratio=0.5)
    ).create_concept_links()
    assert capped == 1
    assert capped < baseline


def test_link_max_per_node_caps_degree_and_is_idempotent() -> None:
    """max_per_node bounds each node's degree; a second run still yields 0."""
    store = _store()
    # A hub "h" shares "x" with four spokes -> hub degree 4 without a cap.
    hub = _add_with_entities(store, ["x"])
    spokes = [_add_with_entities(store, ["x"]) for _ in range(4)]

    engine = DreamingEngine(store, link_settings=_permissive(max_per_node=2))
    created = engine.create_concept_links()

    # Each of the 5 nodes may hold at most 2 links; degree of the hub <= 2.
    hub_links = store.get_links(hub.id, link_type=ConceptLinkType.RELATES_TO)
    assert len(hub_links) <= 2
    for spoke in spokes:
        spoke_links = store.get_links(spoke.id, link_type=ConceptLinkType.RELATES_TO)
        assert len(spoke_links) <= 2
    assert created > 0

    # Determinism / idempotency: a second run on the unchanged DB adds nothing.
    assert engine.create_concept_links() == 0


def test_link_max_per_node_uncapped_default() -> None:
    """max_per_node=0 (default) leaves the hub fully connected."""
    store = _store()
    hub = _add_with_entities(store, ["x"])
    for _ in range(4):
        _add_with_entities(store, ["x"])
    DreamingEngine(store, link_settings=_permissive()).create_concept_links()
    hub_links = store.get_links(hub.id, link_type=ConceptLinkType.RELATES_TO)
    assert len(hub_links) == 4


# ---------------------------------------------------------------------------
# Step 3 — config-driven summary generation (EXPERIMENTS.md §4.1)
# ---------------------------------------------------------------------------


def test_summary_top_k_caps_number_of_summaries() -> None:
    """summary top_k limits how many concepts get summarised."""
    store = _store()
    # Three concepts each in >= 3 memories: "aaa" x5, "bbb" x4, "ccc" x3.
    for _ in range(5):
        _add_with_entities(store, ["aaa"])
    for _ in range(4):
        _add_with_entities(store, ["bbb"])
    for _ in range(3):
        _add_with_entities(store, ["ccc"])

    # Default: all three concepts summarised.
    default_count = DreamingEngine(store, summarizer=_fake_summarizer).generate_summaries()
    assert default_count == 3

    # top_k=2 -> only the two most-evidenced concepts (aaa, bbb).
    store2 = _store()
    for _ in range(5):
        _add_with_entities(store2, ["aaa"])
    for _ in range(4):
        _add_with_entities(store2, ["bbb"])
    for _ in range(3):
        _add_with_entities(store2, ["ccc"])
    engine = DreamingEngine(
        store2, summarizer=_fake_summarizer, summary_settings=SummarySettings(top_k=2)
    )
    assert engine.generate_summaries() == 2
    assert store2.get_summary("aaa") is not None
    assert store2.get_summary("bbb") is not None
    assert store2.get_summary("ccc") is None
    # Idempotent re-run.
    assert engine.generate_summaries() == 0


def test_summary_stoplist_concept_not_summarised() -> None:
    """A stoplisted concept is excluded from summary generation."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["keepme"])
    for _ in range(3):
        _add_with_entities(store, ["dropme"])

    engine = DreamingEngine(
        store,
        summarizer=_fake_summarizer,
        link_settings=LinkSettings(stoplist_csv="dropme"),
    )
    count = engine.generate_summaries()
    assert count == 1
    assert store.get_summary("keepme") is not None
    assert store.get_summary("dropme") is None


def _seed_summary_concepts(store: StorageAdapter) -> None:
    """Six concepts each in >= 3 active memories (deterministic fixture)."""
    for concept, n in (
        ("aaa", 5),
        ("bbb", 4),
        ("ccc", 3),
        ("ddd", 6),
        ("eee", 3),
        ("fff", 4),
    ):
        for _ in range(n):
            _add_with_entities(store, [concept])


def test_summary_concurrency_matches_serial_and_is_idempotent() -> None:
    """concurrency=4 yields the SAME set of summaries as concurrency=1.

    Lever B (docs/OBSERVABILITY.md §3) only changes wall-clock: the count and
    identity (concepts + texts) of summaries must be identical, and a 2nd run on
    the unchanged DB must still create 0. Uses a fake summarizer (no LLM); OTel is
    disabled by default, so the wrapping spans are no-ops.
    """
    # Serial baseline (concurrency=1 -> exact legacy path).
    serial_store = _store()
    _seed_summary_concepts(serial_store)
    serial_engine = DreamingEngine(
        serial_store,
        summarizer=_fake_summarizer,
        summary_settings=SummarySettings(concurrency=1),
    )
    serial_count = serial_engine.generate_summaries()

    # Concurrent run on an INDEPENDENT, identically-seeded DB.
    concurrent_store = _store()
    _seed_summary_concepts(concurrent_store)
    concurrent_engine = DreamingEngine(
        concurrent_store,
        summarizer=_fake_summarizer,
        summary_settings=SummarySettings(concurrency=4),
    )
    concurrent_count = concurrent_engine.generate_summaries()

    # Same NUMBER of summaries regardless of concurrency.
    assert concurrent_count == serial_count
    assert concurrent_count == 6

    # Same SET of concepts AND identical summary text per concept.
    concepts = ["aaa", "bbb", "ccc", "ddd", "eee", "fff"]
    for concept in concepts:
        serial_summary = serial_store.get_summary(concept)
        concurrent_summary = concurrent_store.get_summary(concept)
        assert serial_summary is not None
        assert concurrent_summary is not None
        assert concurrent_summary.summary_text == serial_summary.summary_text
        assert concurrent_summary.memory_count == serial_summary.memory_count

    # Idempotency holds for the concurrent path: 2nd run on the unchanged DB
    # creates no new summaries (writes are INSERT OR REPLACE by concept).
    assert concurrent_engine.generate_summaries() == 0


# ---------------------------------------------------------------------------
# Hub-aware pruning (design §5 / §1b leann-informed-tuning)
# ---------------------------------------------------------------------------


def _make_candidates(pairs: list[tuple[str, str]]) -> list[_LinkCandidate]:
    """Build _LinkCandidate objects with flat strength=0.5, shared_count=1."""
    return [
        _LinkCandidate(src=s, tgt=t, entity="e", shared_count=1, strength=0.5) for s, t in pairs
    ]


def _reference_uniform_cap(
    candidates: list[_LinkCandidate], max_per_node: int
) -> list[tuple[str, str]]:
    """Independent reference impl of the PRE-hub uniform cap, so the no-op proof
    compares the production fast path against a known-good baseline (not against
    itself). Mirrors the original greedy: deterministic order, both endpoints
    under the cap."""
    ordered = sorted(candidates, key=lambda c: (-c.shared_count, -c.strength, c.src, c.tgt))
    degree: dict[str, int] = {}
    kept: list[tuple[str, str]] = []
    for cand in ordered:
        if degree.get(cand.src, 0) >= max_per_node or degree.get(cand.tgt, 0) >= max_per_node:
            continue
        kept.append((cand.src, cand.tgt))
        degree[cand.src] = degree.get(cand.src, 0) + 1
        degree[cand.tgt] = degree.get(cand.tgt, 0) + 1
    return kept


def test_hub_cap_multiplier_1_matches_uniform_cap() -> None:
    """hub_cap_multiplier=1.0 must reproduce the legacy uniform cap EXACTLY.

    No-op proof: compare the production hub-aware path (multiplier 1.0) against an
    INDEPENDENT reference implementation of the old uniform cap — including the
    deterministic (src, tgt) ORDER — so a regression in the fast path is caught.
    """
    # A star plus a chain, so the greedy order and per-node caps actually bite.
    pairs = [("h", f"s{i}") for i in range(4)] + [("a", "b"), ("b", "c")]
    candidates = _make_candidates(pairs)

    reference = _reference_uniform_cap(candidates, max_per_node=2)
    hub_kept = DreamingEngine._cap_per_node(candidates, max_per_node=2, hub_cap_multiplier=1.0)
    default_kept = DreamingEngine._cap_per_node(candidates, max_per_node=2)

    # Ordered (src, tgt) equality — locks both the kept set AND the deterministic order.
    assert [(c.src, c.tgt) for c in hub_kept] == reference
    assert [(c.src, c.tgt) for c in default_kept] == reference


def test_hub_cap_multiplier_2_hub_keeps_more_than_non_hub() -> None:
    """hub_cap_multiplier=2.0 lets a high-degree hub node keep more links than a non-hub.

    Fixture:
      - hub   "h": appears in 4 candidates (high degree -> hub).
      - spoke "s0": appears in only 1 candidate (low degree -> non-hub).
      - max_per_node = 2.

    With multiplier=1.0 (uniform) the hub is capped at 2. With multiplier=2.0 the
    hub's effective cap becomes 4 (2 * 2.0) so it can keep all 4 incident links,
    while the non-hub "s0" still has its base cap of 2 (which it never exceeds anyway).
    The key assertion: hub's degree in the result with multiplier=2.0 > hub's degree
    under the uniform cap.
    """
    # h -- s0, h -- s1, h -- s2, h -- s3
    pairs = [("h", f"s{i}") for i in range(4)]
    candidates = _make_candidates(pairs)

    uniform_kept = DreamingEngine._cap_per_node(candidates, max_per_node=2)
    hub_kept = DreamingEngine._cap_per_node(candidates, max_per_node=2, hub_cap_multiplier=2.0)

    def _degree(kept: list[_LinkCandidate], node: str) -> int:
        return sum(1 for c in kept if c.src == node or c.tgt == node)

    hub_degree_uniform = _degree(uniform_kept, "h")
    hub_degree_hub_aware = _degree(hub_kept, "h")

    # Hub retains MORE links under hub-aware pruning.
    assert hub_degree_hub_aware > hub_degree_uniform
    # And it can now keep all four (effective cap = 2 * 2 = 4).
    assert hub_degree_hub_aware == 4


# ---------------------------------------------------------------------------
# Personal notes — archival exempt (design §6a)
# ---------------------------------------------------------------------------


def test_archive_stale_skips_note_even_at_max_staleness() -> None:
    """archive_stale must NEVER auto-archive a note, even at staleness=10 (§6a)."""
    store = _store()
    note = store.add_memory(
        record=MemoryRecord(
            content="A note that is artificially stale",
            category=MemoryCategory.FACT,
            is_note=True,
            is_stale=True,
            staleness_score=10.0,
        )
    )
    _set_last_accessed(store, note.id, days_ago=60)
    engine = DreamingEngine(store)
    archived = engine.archive_stale()
    assert archived == 0
    after = store.get_memory(note.id)
    assert after is not None
    assert after.is_archived is False


def test_archive_stale_skips_note_old_access() -> None:
    """archive_stale skips a note even when last_accessed is old (§6a belt-and-suspenders)."""
    store = _store()
    note = store.add_memory(
        record=MemoryRecord(
            content="Stale note from long ago",
            category=MemoryCategory.FACT,
            is_note=True,
            is_stale=True,
            staleness_score=9.5,
        )
    )
    _set_last_accessed(store, note.id, days_ago=365)
    engine = DreamingEngine(store)
    assert engine.archive_stale() == 0
    assert store.get_memory(note.id) is not None
    assert store.get_memory(note.id).is_archived is False  # type: ignore[union-attr]


def test_archive_stale_still_archives_non_note() -> None:
    """archive_stale still archives non-notes normally (§6a: note exemption is targeted)."""
    store = _store()
    non_note = store.add_memory(
        record=MemoryRecord(
            content="Ancient stale non-note fact XYZ",
            category=MemoryCategory.FACT,
            is_stale=True,
            staleness_score=9.5,
        )
    )
    _set_last_accessed(store, non_note.id, days_ago=60)
    engine = DreamingEngine(store)
    assert engine.archive_stale() == 1
    after = store.get_memory(non_note.id)
    assert after is not None
    assert after.is_archived is True


# ---------------------------------------------------------------------------
# Personal notes — anomaly detection excludes notes (design §6a)
# ---------------------------------------------------------------------------


def test_anomaly_report_excludes_notes_from_high_staleness_useful() -> None:
    """A note with high staleness + usefulness does NOT appear in high_staleness_useful."""
    store = _store()
    note = store.add_memory(
        record=MemoryRecord(
            content="A note with high staleness and usefulness",
            category=MemoryCategory.FACT,
            is_note=True,
            staleness_score=8.0,
            usefulness_score=7.0,
        )
    )
    engine = DreamingEngine(store)
    report = engine.detect_anomalies()
    assert note.id not in report.high_staleness_useful


def test_anomaly_report_excludes_notes_from_never_accessed() -> None:
    """A note that was never accessed does NOT appear in never_accessed anomalies."""
    store = _store()
    note = store.add_memory(
        record=MemoryRecord(
            content="An old note nobody has read",
            category=MemoryCategory.FACT,
            is_note=True,
        )
    )
    _backdate(store, note.id, created_days=30)
    engine = DreamingEngine(store)
    report = engine.detect_anomalies()
    assert note.id not in report.never_accessed


def test_anomaly_report_includes_contested_note_in_contradictions() -> None:
    """A flagged note (stale-voted) DOES appear in contradictions list for human review."""
    store = _store()
    note = store.add_memory(
        record=MemoryRecord(
            content="A contested note that someone stale-voted",
            category=MemoryCategory.FACT,
            is_note=True,
            flagged_for_review=True,
        )
    )
    engine = DreamingEngine(store)
    report = engine.detect_anomalies()
    assert note.id in report.contradictions


# ---------------------------------------------------------------------------
# Personal notes — contradiction authority (design §6b)
# ---------------------------------------------------------------------------


def test_note_authority_note_wins_over_non_note() -> None:
    """Case 1/2: note vs inferred → note wins; non-note is superseded (§6b)."""
    store = _store()
    inferred = store.add_memory(
        record=MemoryRecord(
            content="Inferred fact: the sky is green",
            category=MemoryCategory.FACT,
            flagged_for_review=True,
            contradicts_ids=[],  # will be set on the note side
        )
    )
    note = store.add_memory(
        record=MemoryRecord(
            content="User note: the sky is blue",
            category=MemoryCategory.FACT,
            is_note=True,
            flagged_for_review=True,
            contradicts_ids=[inferred.id],
        )
    )
    # Engine with NO resolver — authority pass must still run
    engine = DreamingEngine(store, conflict_resolver=None)
    resolved = engine.resolve_contradictions()

    # At least 1 resolved
    assert resolved >= 1

    # inferred should be superseded
    after_inferred = store.get_memory(inferred.id)
    assert after_inferred is not None
    assert after_inferred.superseded_by == note.id or after_inferred.is_archived is True

    # note's flag should be cleared
    after_note = store.get_memory(note.id)
    assert after_note is not None
    assert after_note.flagged_for_review is False


def test_note_authority_note_vs_note_leaves_both_flagged() -> None:
    """Case 3: note-vs-note → both stay flagged, no supersede, resolved count=0 (§6b)."""
    store = _store()
    note_a = store.add_memory(
        record=MemoryRecord(
            content="Note A: remember X is true",
            category=MemoryCategory.FACT,
            is_note=True,
            flagged_for_review=True,
            contradicts_ids=[],  # will link via contradicts_ids on note_b
        )
    )
    note_b = store.add_memory(
        record=MemoryRecord(
            content="Note B: remember X is false",
            category=MemoryCategory.FACT,
            is_note=True,
            flagged_for_review=True,
            contradicts_ids=[note_a.id],
        )
    )

    engine = DreamingEngine(store, conflict_resolver=None)
    resolved = engine.resolve_contradictions()

    # Note-vs-note is handled but NOT counted as resolved (deferred) — the count
    # must be 0, and must not drift on a re-run (regression: it returned 2 twice).
    assert resolved == 0
    assert engine.resolve_contradictions() == 0  # idempotent count

    after_a = store.get_memory(note_a.id)
    after_b = store.get_memory(note_b.id)
    assert after_a is not None
    assert after_b is not None
    # Neither is superseded; BOTH remain flagged for human review.
    assert after_a.superseded_by is None
    assert after_b.superseded_by is None
    assert after_a.flagged_for_review is True
    assert after_b.flagged_for_review is True


def test_note_authority_case2_non_note_flagged_is_idempotent() -> None:
    """Case 2: the FLAGGED record is the non-note; the note wins (§6b, §9).

    Regression: case 2 must clear the superseded non-note's flag, else it stays
    flagged + archived and is re-'resolved' on every run (count drift / non-idempotent).
    """
    store = _store()
    note = store.add_memory(
        record=MemoryRecord(
            content="User note: the prod URL is https://new.example.com",
            category=MemoryCategory.FACT,
            is_note=True,
        )
    )
    inferred = store.add_memory(
        record=MemoryRecord(
            content="Inferred: the prod URL is https://old.example.com",
            category=MemoryCategory.FACT,
            flagged_for_review=True,  # the NON-note is the flagged record (case 2)
            contradicts_ids=[note.id],
        )
    )
    engine = DreamingEngine(store, conflict_resolver=None)

    assert engine.resolve_contradictions() == 1  # one real supersede
    after = store.get_memory(inferred.id)
    assert after is not None
    assert after.superseded_by == note.id
    assert after.flagged_for_review is False  # the fix: superseded record's flag cleared

    # Idempotent: nothing left flagged → a re-run resolves 0.
    assert engine.resolve_contradictions() == 0


def test_note_authority_offline_no_resolver_non_note_left_unchanged() -> None:
    """Case 4: non-note vs non-note with NO resolver → left flagged, resolved=0 (§6b)."""
    store = _store()
    rec1 = store.add_memory(
        record=MemoryRecord(
            content="Non-note fact one",
            category=MemoryCategory.FACT,
            flagged_for_review=True,
        )
    )
    rec2 = store.add_memory(
        record=MemoryRecord(
            content="Non-note fact two contradicting",
            category=MemoryCategory.FACT,
            flagged_for_review=False,
        )
    )
    store.update_memory(rec1.id, contradicts_ids=[rec2.id])

    engine = DreamingEngine(store, conflict_resolver=None)
    resolved = engine.resolve_contradictions()
    assert resolved == 0

    after = store.get_memory(rec1.id)
    assert after is not None
    assert after.flagged_for_review is True


def test_note_authority_idempotent_second_run() -> None:
    """Re-running resolve_contradictions after a note-authority resolution is a no-op (§9)."""
    store = _store()
    inferred = store.add_memory(
        record=MemoryRecord(
            content="Inferred claim to be superseded",
            category=MemoryCategory.FACT,
        )
    )
    store.add_memory(
        record=MemoryRecord(
            content="User note wins",
            category=MemoryCategory.FACT,
            is_note=True,
            flagged_for_review=True,
            contradicts_ids=[inferred.id],
        )
    )

    engine = DreamingEngine(store, conflict_resolver=None)
    engine.resolve_contradictions()
    second = engine.resolve_contradictions()

    # Second run: nothing left to resolve
    assert second == 0


def test_note_authority_note_vs_note_breadcrumb_idempotent() -> None:
    """note-vs-note breadcrumb write is conditional; repeated runs do not drift counts (§9)."""
    store = _store()
    note_a = store.add_memory(
        record=MemoryRecord(
            content="Note A: conflicting claim alpha",
            category=MemoryCategory.FACT,
            is_note=True,
            flagged_for_review=True,
        )
    )
    note_b = store.add_memory(
        record=MemoryRecord(
            content="Note B: conflicting claim beta",
            category=MemoryCategory.FACT,
            is_note=True,
            flagged_for_review=True,
            contradicts_ids=[note_a.id],
        )
    )

    engine = DreamingEngine(store, conflict_resolver=None)
    engine.resolve_contradictions()
    engine.resolve_contradictions()  # second run — must not produce new writes

    after_b = store.get_memory(note_b.id)
    assert after_b is not None
    # Breadcrumb must be present (set on first run)
    assert after_b.metadata.get("note_conflict_with") == note_a.id


def test_hub_cap_multiplier_deterministic_and_idempotent() -> None:
    """_cap_per_node with hub_cap_multiplier > 1.0 is deterministic and idempotent.

    Calling the pure function twice on the same input list must return the same
    set of (src, tgt) pairs in the same order.
    """
    pairs = [
        ("a", "b"),
        ("a", "c"),
        ("a", "d"),
        ("b", "c"),
        ("b", "d"),
    ]
    candidates = _make_candidates(pairs)

    first = DreamingEngine._cap_per_node(candidates, max_per_node=2, hub_cap_multiplier=1.5)
    second = DreamingEngine._cap_per_node(candidates, max_per_node=2, hub_cap_multiplier=1.5)

    assert [(c.src, c.tgt) for c in first] == [(c.src, c.tgt) for c in second]
