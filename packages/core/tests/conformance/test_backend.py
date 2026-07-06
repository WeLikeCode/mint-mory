"""
StorageBackend port conformance suite — Phase 1.

Every test in this module uses the parametrised ``backend`` fixture defined in
``conftest.py``.  Today only the ``sqlite`` parameter runs; the ``postgres``
parameter auto-skips (Phase 2 not yet implemented).

MUST-PASS vs CAPABILITY-GATED matrix
======================================

MUST-PASS (every backend that correctly implements StorageBackend Protocol)
---------------------------------------------------------------------------
All tests NOT decorated with ``@pytest.mark.vector`` or ``@pytest.mark.trigram``.

This covers the behavioural contract for:
  • Memory CRUD round-trip fidelity (every column)
  • Entity re-extraction on content change; supplied entities preserved
  • Partial update; updated_at refresh; missing-ID KeyError
  • Archive (is_archived=True, is_active=False)
  • Supersede (superseded_by set, is_active=False, is_archived=True)
  • Feedback increment, stale threshold, score caps, missing-ID KeyError
  • Note stale-vote → flagged_for_review (not staleness); note useful-vote unchanged
  • Dreaming anomaly helpers: flagged, never-accessed, high-staleness/useful queries
  • Manifest upsert/get/paths/delete/replace (all ManifestEntry fields)
  • Links: add, get (both directions for symmetric types), directional filtering
  • search_around: depth 1 & 2, symmetric vs directional, min_strength, link_type filter
  • Sessions: create, get, record_query_results, update_session_feedback, mark_concluded
  • Summaries: upsert, get, list, upsert-replace
  • Stats: total_memories, active, stale, archived, concept_links, memory_summaries
  • FTS search: basic token match, prefix on compound word, space-split compound
  • Search filtering: archived excluded, stale excluded, include_archived semantics
  • Notes auto-include: channel is separate from total_found; archived notes excluded
  • anchor_candidates: side-effect-free; sorted (score, record) pairs; limit honoured
  • list_notes: plain note appears; archived excluded by default / included when True;
    temporal boundary — overdue vs upcoming semantics with explicit ``now=``
  • Vision/image methods: list_image_file_records (ORDER BY rel, id); find_image_file_record
    (most-recent active match; None for miss); get_annotating_descriptions (ANNOTATES
    reverse traversal; cap honoured; cap=0 returns [])

CAPABILITY-GATED
----------------
``@pytest.mark.vector`` — backend.vector_search_available() must return True.
  Tests call ``pytest.skip()`` inside the body if the capability is absent.
  Required capability: embedder attached AND the backend's vector extension loaded
  (sqlite-vec for SQLite; pgvector for Postgres).

``@pytest.mark.trigram`` — trigram substring-search capability required.
  Tests probe by doing a search for a known substring; if total_found == 0 they
  call ``pytest.skip()`` rather than failing.
  Required capability: FTS5 trigram tokenizer (SQLite); pg_trgm (Postgres).

Neither capability affects MUST-PASS status: a backend lacking a capability SKIPS
those tests rather than FAILING them, so the conformance suite is green for a
minimal backend that only implements FTS + relational methods.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from mintmory.core.ports import ManifestEntry, StorageBackend
from mintmory.core.scoring import STALE_INCREMENT, STALENESS_THRESHOLD, USEFUL_INCREMENT
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    LinkSource,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
    MemoryStats,
    MemorySummary,
    QueryResult,
    QuerySession,
    SearchAroundSpec,
    SearchRequest,
)

from conformance import BackendHandle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add(b: StorageBackend, content: str, **kw: Any) -> str:
    """Add a memory and return its ID.  Defaults: category=fact, source=agent."""
    kw.setdefault("category", "fact")
    kw.setdefault("source", "agent")
    return b.add_memory(content=content, **kw).id


def _link(
    b: StorageBackend,
    src: str,
    tgt: str,
    link_type: ConceptLinkType = ConceptLinkType.RELATES_TO,
    strength: float = 0.8,
) -> None:
    b.add_link(
        ConceptLink(
            source_memory_id=src,
            target_memory_id=tgt,
            link_type=link_type,
            strength=strength,
            source=LinkSource.USER,
        )
    )


def _note(b: StorageBackend, content: str) -> MemoryRecord:
    """Add a user-authored note (is_note=True)."""
    return b.add_memory(
        record=MemoryRecord(
            content=content,
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )


def _annotates(b: StorageBackend, note_id: str, target_id: str) -> None:
    """Create an ANNOTATES link from note → target."""
    b.add_link(
        ConceptLink(
            source_memory_id=note_id,
            target_memory_id=target_id,
            link_type=ConceptLinkType.ANNOTATES,
            entity="test",
            source=LinkSource.USER,
            strength=1.0,
            confidence=1.0,
        )
    )


# ===========================================================================
# Section 1 — Memory CRUD round-trip fidelity
# ===========================================================================


def test_memory_add_get_round_trip_all_fields(backend: BackendHandle) -> None:
    """Every non-default column survives a write → read cycle unchanged."""
    b = backend.backend
    rec = MemoryRecord(
        content="Round-trip fidelity check for all fields",
        category=MemoryCategory.SKILL,
        source=MemorySource.USER,
        confidence=0.42,
        verified=True,
        usefulness_score=3.5,
        staleness_score=1.5,
        reinforcement_count=2,
        retrieval_count=4,
        is_stale=False,
        metadata={"project": "alpha", "tags": ["x", "y"]},
        contradicts_ids=["id-a", "id-b"],
        is_note=False,
    )
    b.add_memory(rec)
    fetched = b.get_memory(rec.id)
    assert fetched is not None
    assert fetched.content == "Round-trip fidelity check for all fields"
    assert fetched.category == MemoryCategory.SKILL
    assert fetched.source == MemorySource.USER
    assert fetched.confidence == pytest.approx(0.42)
    assert fetched.verified is True
    assert fetched.usefulness_score == pytest.approx(3.5)
    assert fetched.staleness_score == pytest.approx(1.5)
    assert fetched.reinforcement_count == 2
    assert fetched.retrieval_count == 4
    assert fetched.metadata == {"project": "alpha", "tags": ["x", "y"]}
    assert set(fetched.contradicts_ids) == {"id-a", "id-b"}
    assert fetched.is_note is False


def test_memory_get_nonexistent_returns_none(backend: BackendHandle) -> None:
    assert backend.backend.get_memory("definitely-does-not-exist") is None


def test_memory_defaults_after_add(backend: BackendHandle) -> None:
    """Freshly added memory has correct zero-state defaults."""
    b = backend.backend
    rec = b.add_memory(content="defaults check", category="fact")
    assert rec.usefulness_score == pytest.approx(0.0)
    assert rec.staleness_score == pytest.approx(0.0)
    assert rec.reinforcement_count == 0
    assert rec.retrieval_count == 0
    assert rec.is_active is True
    assert rec.is_archived is False
    assert rec.is_stale is False
    assert rec.flagged_for_review is False
    assert rec.verified is False


def test_memory_entity_extraction_on_add(backend: BackendHandle) -> None:
    """Entity extraction runs at add time; well-known named terms are extracted."""
    b = backend.backend
    rec = b.add_memory(content="Claude uses MCP servers for tool calls.", category="fact")
    fetched = b.get_memory(rec.id)
    assert fetched is not None
    assert fetched.entity_ids  # extraction must yield at least one entity
    assert "claude" in fetched.entity_ids


def test_memory_supplied_entities_preserved(backend: BackendHandle) -> None:
    """When entity_ids are explicitly supplied they are stored as-is."""
    b = backend.backend
    rec = b.add_memory(
        content="some content here",
        category="fact",
        entity_ids=["custom-entity-alpha"],
    )
    assert rec.entity_ids == ["custom-entity-alpha"]


# ===========================================================================
# Section 2 — Update
# ===========================================================================


def test_memory_update_partial_fields(backend: BackendHandle) -> None:
    """Only the explicitly provided fields change; others are preserved."""
    b = backend.backend
    rec = b.add_memory(content="original content", category="fact", confidence=1.0)
    updated = b.update_memory(rec.id, confidence=0.5, verified=True)
    assert updated.confidence == pytest.approx(0.5)
    assert updated.verified is True
    assert updated.content == "original content"  # unchanged


def test_memory_update_refreshes_updated_at(backend: BackendHandle) -> None:
    """update_memory bumps updated_at to >= the pre-update value."""
    b = backend.backend
    rec = b.add_memory(content="timestamp check", category="fact")
    before = rec.updated_at
    updated = b.update_memory(rec.id, confidence=0.3)
    assert updated.updated_at >= before


def test_memory_update_content_reextracts_entities(backend: BackendHandle) -> None:
    """Changing content triggers entity re-extraction; old entities are replaced."""
    b = backend.backend
    rec = b.add_memory(content="Claude rules the world", category="fact")
    updated = b.update_memory(rec.id, content="Anthropic builds Sonnet models")
    assert "anthropic" in updated.entity_ids
    assert "claude" not in updated.entity_ids


def test_memory_update_missing_id_raises_key_error(backend: BackendHandle) -> None:
    with pytest.raises(KeyError):
        backend.backend.update_memory("nonexistent-id-xyz", confidence=0.5)


# ===========================================================================
# Section 3 — Archive & Supersede
# ===========================================================================


def test_memory_archive(backend: BackendHandle) -> None:
    """archive_memory sets is_archived=True and is_active=False."""
    b = backend.backend
    mid = _add(b, "archive me please")
    b.archive_memory(mid)
    fetched = b.get_memory(mid)
    assert fetched is not None
    assert fetched.is_archived is True
    assert fetched.is_active is False


def test_memory_supersede(backend: BackendHandle) -> None:
    """supersede_memory sets superseded_by, is_active=False, is_archived=True."""
    b = backend.backend
    authoritative = _add(b, "the authoritative replacement memory")
    superseded = _add(b, "the memory being replaced")
    b.supersede_memory(superseded, by_id=authoritative)
    fetched = b.get_memory(superseded)
    assert fetched is not None
    assert fetched.superseded_by == authoritative
    assert fetched.is_active is False
    assert fetched.is_archived is True


# ===========================================================================
# Section 4 — Feedback
# ===========================================================================


def test_feedback_useful_increments_score_and_count(backend: BackendHandle) -> None:
    b = backend.backend
    mid = _add(b, "useful memory content")
    b.apply_feedback(mid, useful=True, stale=False)
    fetched = b.get_memory(mid)
    assert fetched is not None
    assert fetched.usefulness_score == pytest.approx(USEFUL_INCREMENT)
    assert fetched.reinforcement_count == 1


def test_feedback_stale_increments_staleness(backend: BackendHandle) -> None:
    b = backend.backend
    mid = _add(b, "stale memory content")
    b.apply_feedback(mid, useful=False, stale=True)
    fetched = b.get_memory(mid)
    assert fetched is not None
    assert fetched.staleness_score == pytest.approx(STALE_INCREMENT)
    assert fetched.reinforcement_count == 0


def test_feedback_stale_threshold_sets_is_stale(backend: BackendHandle) -> None:
    """After enough stale votes, is_stale flips to True."""
    b = backend.backend
    mid = _add(b, "memory becoming stale")
    votes_needed = int(STALENESS_THRESHOLD / STALE_INCREMENT)
    for _ in range(votes_needed):
        b.apply_feedback(mid, useful=False, stale=True)
    fetched = b.get_memory(mid)
    assert fetched is not None
    assert fetched.staleness_score >= STALENESS_THRESHOLD
    assert fetched.is_stale is True


def test_feedback_usefulness_cap_at_ten(backend: BackendHandle) -> None:
    b = backend.backend
    mid = _add(b, "very useful memory")
    for _ in range(50):
        b.apply_feedback(mid, useful=True, stale=False)
    fetched = b.get_memory(mid)
    assert fetched is not None
    assert fetched.usefulness_score <= 10.0


def test_feedback_staleness_cap_at_ten(backend: BackendHandle) -> None:
    b = backend.backend
    mid = _add(b, "very stale memory")
    for _ in range(50):
        b.apply_feedback(mid, useful=False, stale=True)
    fetched = b.get_memory(mid)
    assert fetched is not None
    assert fetched.staleness_score <= 10.0


def test_feedback_missing_id_raises_key_error(backend: BackendHandle) -> None:
    with pytest.raises(KeyError):
        backend.backend.apply_feedback("nonexistent-id-xyz", useful=True, stale=False)


def test_feedback_note_stale_flags_not_penalises(backend: BackendHandle) -> None:
    """stale=True on a note sets flagged_for_review; staleness_score is UNCHANGED."""
    b = backend.backend
    note = _note(b, "A user note that someone votes stale")
    b.apply_feedback(note.id, useful=False, stale=True)
    fetched = b.get_memory(note.id)
    assert fetched is not None
    assert fetched.staleness_score == pytest.approx(0.0)  # staleness unchanged
    assert fetched.is_stale is False
    assert fetched.flagged_for_review is True


def test_feedback_note_useful_still_increments(backend: BackendHandle) -> None:
    """useful=True on a note still increments usefulness_score and reinforcement_count."""
    b = backend.backend
    note = _note(b, "A note worth reinforcing")
    b.apply_feedback(note.id, useful=True, stale=False)
    fetched = b.get_memory(note.id)
    assert fetched is not None
    assert fetched.usefulness_score == pytest.approx(USEFUL_INCREMENT)
    assert fetched.reinforcement_count == 1


# ===========================================================================
# Section 5 — Index manifest
# ===========================================================================


def test_manifest_upsert_get_all_fields(backend: BackendHandle) -> None:
    """upsert then get returns a ManifestEntry dict with every expected field."""
    b = backend.backend
    b.manifest_upsert(
        path="/docs/spec.md",
        collection="design-docs",
        size=4096,
        mtime=1_700_000_000.0,
        content_hash="deadbeef",
        index_mode="content",
        memory_ids=["m1", "m2", "m3"],
        online_only=False,
    )
    entry: ManifestEntry | None = b.manifest_get("/docs/spec.md")
    assert entry is not None
    assert isinstance(entry, dict)
    assert entry["path"] == "/docs/spec.md"
    assert entry["collection"] == "design-docs"
    assert entry["size"] == 4096
    assert entry["content_hash"] == "deadbeef"
    assert entry["index_mode"] == "content"
    assert entry["online_only"] == 0  # INTEGER bool in SQLite; Postgres may use False
    decoded = json.loads(entry["memory_ids"])
    assert set(decoded) == {"m1", "m2", "m3"}


def test_manifest_get_missing_returns_none(backend: BackendHandle) -> None:
    assert backend.backend.manifest_get("/nonexistent/path.txt") is None


def test_manifest_paths_returns_tracked_set(backend: BackendHandle) -> None:
    b = backend.backend
    paths = ["/a/alpha.txt", "/b/beta.txt", "/c/gamma.txt"]
    for p in paths:
        b.manifest_upsert(
            path=p,
            collection="col",
            size=1,
            mtime=0.0,
            index_mode="content",
            memory_ids=[],
            online_only=False,
        )
    result = b.manifest_paths("col")
    assert result == set(paths)


def test_manifest_delete_removes_path(backend: BackendHandle) -> None:
    b = backend.backend
    b.manifest_upsert(
        path="/del/file.txt",
        collection="col",
        size=1,
        mtime=0.0,
        index_mode="content",
        memory_ids=[],
        online_only=False,
    )
    b.manifest_delete("/del/file.txt")
    assert b.manifest_get("/del/file.txt") is None
    assert "/del/file.txt" not in b.manifest_paths("col")


def test_manifest_upsert_replaces_existing(backend: BackendHandle) -> None:
    """A second upsert for the same path updates all fields."""
    b = backend.backend
    b.manifest_upsert(
        path="/upsert/doc.txt",
        collection="col",
        size=10,
        mtime=1.0,
        content_hash="old",
        index_mode="content",
        memory_ids=["m-old"],
        online_only=False,
    )
    b.manifest_upsert(
        path="/upsert/doc.txt",
        collection="col",
        size=20,
        mtime=2.0,
        content_hash="new",
        index_mode="content",
        memory_ids=["m-new"],
        online_only=True,
    )
    entry = b.manifest_get("/upsert/doc.txt")
    assert entry is not None
    assert entry["size"] == 20
    assert entry["content_hash"] == "new"
    decoded = json.loads(entry["memory_ids"])
    assert decoded == ["m-new"]


# ===========================================================================
# Section 6 — ConceptLinks
# ===========================================================================


def test_link_add_get_basic(backend: BackendHandle) -> None:
    """add_link persists the link; get_links returns it for both endpoints."""
    b = backend.backend
    src = _add(b, "source memory for link test")
    tgt = _add(b, "target memory for link test")
    link = ConceptLink(
        source_memory_id=src,
        target_memory_id=tgt,
        link_type=ConceptLinkType.RELATES_TO,
        entity="test-entity",
        source=LinkSource.USER,
        strength=0.8,
        confidence=0.9,
    )
    stored = b.add_link(link)
    assert stored.id == link.id

    links_from_src = b.get_links(src)
    assert any(lk.target_memory_id == tgt for lk in links_from_src)


def test_link_symmetric_both_ends_reachable(backend: BackendHandle) -> None:
    """RELATES_TO is symmetric: get_links from either endpoint returns the link."""
    b = backend.backend
    a = _add(b, "symmetric end alpha")
    z = _add(b, "symmetric end zeta")
    _link(b, a, z, ConceptLinkType.RELATES_TO)

    links_a = b.get_links(a)
    links_z = b.get_links(z)
    ids_a = {lk.source_memory_id for lk in links_a} | {lk.target_memory_id for lk in links_a}
    ids_z = {lk.source_memory_id for lk in links_z} | {lk.target_memory_id for lk in links_z}
    assert z in ids_a
    assert a in ids_z


def test_link_dedup_insert_or_ignore(backend: BackendHandle) -> None:
    """Adding the same UNIQUE(source, target, link_type) twice does not duplicate."""
    b = backend.backend
    src = _add(b, "dedup link source")
    tgt = _add(b, "dedup link target")
    _link(b, src, tgt, ConceptLinkType.SIMILAR_TO)
    _link(b, src, tgt, ConceptLinkType.SIMILAR_TO)  # second add; must not duplicate
    links = b.get_links(src, link_type=ConceptLinkType.SIMILAR_TO)
    assert len(links) == 1


def test_link_filter_by_type(backend: BackendHandle) -> None:
    """get_links with link_type filters to that type only."""
    b = backend.backend
    src = _add(b, "link type filter source")
    a = _add(b, "relates target")
    c = _add(b, "refines target")
    _link(b, src, a, ConceptLinkType.RELATES_TO)
    _link(b, src, c, ConceptLinkType.REFINES)
    relates = b.get_links(src, link_type=ConceptLinkType.RELATES_TO)
    assert all(lk.link_type == ConceptLinkType.RELATES_TO for lk in relates)
    assert any(lk.target_memory_id == a for lk in relates)
    assert not any(lk.target_memory_id == c for lk in relates)


# ===========================================================================
# Section 7 — search_around
# ===========================================================================


def test_search_around_depth_1(backend: BackendHandle) -> None:
    b = backend.backend
    anchor = _add(b, "anchor node for traversal test")
    neighbor = _add(b, "direct neighbor of anchor")
    unrelated = _add(b, "completely unrelated memory here")
    _link(b, anchor, neighbor)
    result = b.search_around([anchor], SearchAroundSpec(depth=1))
    assert neighbor in result
    assert unrelated not in result
    assert anchor not in result  # anchors excluded from result


def test_search_around_depth_2(backend: BackendHandle) -> None:
    b = backend.backend
    a = _add(b, "depth zero node for BFS")
    lvl1 = _add(b, "depth one node BFS")
    lvl2 = _add(b, "depth two node BFS")
    _link(b, a, lvl1)
    _link(b, lvl1, lvl2)
    d1 = b.search_around([a], SearchAroundSpec(depth=1))
    assert lvl1 in d1
    assert lvl2 not in d1  # too far at depth=1
    d2 = b.search_around([a], SearchAroundSpec(depth=2))
    assert lvl1 in d2
    assert lvl2 in d2


def test_search_around_symmetric_reverse(backend: BackendHandle) -> None:
    """Symmetric link type (SIMILAR_TO) is traversable from the target end."""
    b = backend.backend
    a = _add(b, "symmetric traversal anchor node")
    peer = _add(b, "symmetric traversal peer node")
    _link(b, peer, a, ConceptLinkType.SIMILAR_TO)  # link points peer → a
    result = b.search_around([a], SearchAroundSpec(depth=1))
    assert peer in result  # must be reachable via symmetric traversal


def test_search_around_directional_not_reversed(backend: BackendHandle) -> None:
    """DEPENDS_ON is directional; traversal from target must NOT reach source."""
    b = backend.backend
    anchor = _add(b, "directed anchor for dependency test")
    upstream = _add(b, "upstream dependency source")
    _link(b, upstream, anchor, ConceptLinkType.DEPENDS_ON)
    result = b.search_around([anchor], SearchAroundSpec(depth=1))
    assert upstream not in result


def test_search_around_min_strength_filters(backend: BackendHandle) -> None:
    b = backend.backend
    anchor = _add(b, "strength filter anchor node")
    weak = _add(b, "weak link neighbor node")
    _link(b, anchor, weak, strength=0.1)
    result = b.search_around([anchor], SearchAroundSpec(depth=1, min_strength=0.5))
    assert weak not in result


def test_search_around_link_type_filter(backend: BackendHandle) -> None:
    b = backend.backend
    anchor = _add(b, "link type filter anchor")
    r = _add(b, "relates to neighbor")
    rf = _add(b, "refines neighbor")
    _link(b, anchor, r, ConceptLinkType.RELATES_TO)
    _link(b, anchor, rf, ConceptLinkType.REFINES)
    result = b.search_around(
        [anchor], SearchAroundSpec(depth=1, link_types=[ConceptLinkType.REFINES])
    )
    assert rf in result
    assert r not in result


def test_search_around_empty_anchors(backend: BackendHandle) -> None:
    assert backend.backend.search_around([], SearchAroundSpec(depth=1)) == []


# ===========================================================================
# Section 8 — QuerySession
# ===========================================================================


def test_session_create_and_get(backend: BackendHandle) -> None:
    b = backend.backend
    session = QuerySession(query_text="test query for session create")
    stored = b.create_session(session)
    assert stored.id == session.id
    fetched = b.get_session(session.id)
    assert fetched is not None
    assert fetched.query_text == "test query for session create"
    assert fetched.concluded is False


def test_session_get_missing_returns_none(backend: BackendHandle) -> None:
    assert backend.backend.get_session("nonexistent-session-id") is None


def test_session_record_query_results(backend: BackendHandle) -> None:
    b = backend.backend
    mid = _add(b, "memory recorded in query results")
    session = QuerySession(query_text="record results query")
    b.create_session(session)
    b.record_query_results(
        [QueryResult(session_id=session.id, memory_id=mid, relevance_score=0.87)]
    )
    # No public accessor for query_results; verify via session feedback round-trip.
    b.update_session_feedback(
        session_id=session.id,
        confidence_rating=4,
        reasoning="helpful",
        useful_ids=[mid],
        stale_ids=[],
    )
    updated = b.get_session(session.id)
    assert updated is not None
    assert updated.concluded is True
    assert mid in updated.useful_ids


def test_session_update_feedback_sets_fields(backend: BackendHandle) -> None:
    b = backend.backend
    mid_u = _add(b, "useful feedback memory alpha")
    mid_s = _add(b, "stale feedback memory beta")
    session = QuerySession(query_text="feedback fields check query")
    b.create_session(session)
    b.record_query_results(
        [
            QueryResult(session_id=session.id, memory_id=mid_u, relevance_score=0.9),
            QueryResult(session_id=session.id, memory_id=mid_s, relevance_score=0.4),
        ]
    )
    b.update_session_feedback(
        session_id=session.id,
        confidence_rating=3,
        reasoning="some reasoning",
        useful_ids=[mid_u],
        stale_ids=[mid_s],
    )
    sess = b.get_session(session.id)
    assert sess is not None
    assert sess.confidence_rating == 3
    assert sess.reasoning == "some reasoning"
    assert mid_u in sess.useful_ids
    assert mid_s in sess.stale_ids
    assert sess.concluded is True


def test_session_mark_concluded(backend: BackendHandle) -> None:
    b = backend.backend
    session = QuerySession(query_text="mark concluded no-feedback query")
    b.create_session(session)
    b.mark_session_concluded(session.id)
    fetched = b.get_session(session.id)
    assert fetched is not None
    assert fetched.concluded is True


# ===========================================================================
# Section 9 — MemorySummary
# ===========================================================================


def test_summary_upsert_and_get(backend: BackendHandle) -> None:
    b = backend.backend
    summary = MemorySummary(
        concept="kubernetes",
        summary_text="Kubernetes is a container orchestration system.",
        memory_count=5,
        is_current=True,
    )
    stored = b.upsert_summary(summary)
    assert stored.id == summary.id
    fetched = b.get_summary("kubernetes")
    assert fetched is not None
    assert fetched.concept == "kubernetes"
    assert fetched.summary_text == "Kubernetes is a container orchestration system."
    assert fetched.memory_count == 5


def test_summary_get_missing_returns_none(backend: BackendHandle) -> None:
    assert backend.backend.get_summary("no-such-concept") is None


def test_summary_list_returns_all(backend: BackendHandle) -> None:
    b = backend.backend
    concepts = ["alpha-concept", "beta-concept", "gamma-concept"]
    for c in concepts:
        b.upsert_summary(MemorySummary(concept=c, summary_text=f"{c} text", memory_count=1))
    result = b.list_summaries()
    found = {s.concept for s in result}
    assert found >= set(concepts)


def test_summary_upsert_replaces_existing(backend: BackendHandle) -> None:
    b = backend.backend
    b.upsert_summary(MemorySummary(concept="replace-me", summary_text="old text", memory_count=1))
    b.upsert_summary(MemorySummary(concept="replace-me", summary_text="new text", memory_count=9))
    fetched = b.get_summary("replace-me")
    assert fetched is not None
    assert fetched.summary_text == "new text"
    assert fetched.memory_count == 9


# ===========================================================================
# Section 10 — Stats
# ===========================================================================


def test_stats_counts_correct(backend: BackendHandle) -> None:
    """get_stats returns MemoryStats with counts consistent with the inserted state."""
    b = backend.backend
    # Insert memories in various states
    mid1 = _add(b, "active memory one")
    mid2 = _add(b, "active memory two")
    mid3 = _add(b, "memory to archive later")
    mid4 = _add(b, "memory to make stale later")
    _add(b, "active memory five")

    b.archive_memory(mid3)
    b.update_memory(mid4, is_stale=True)

    _link(b, mid1, mid2)
    b.upsert_summary(MemorySummary(concept="stats-concept", summary_text="x", memory_count=1))

    stats: MemoryStats = b.get_stats()
    assert stats.total_memories >= 5
    assert stats.archived >= 1
    assert stats.stale >= 1
    assert stats.concept_links >= 1
    assert stats.memory_summaries >= 1


# ===========================================================================
# Section 11 — Dreaming anomaly helpers
# ===========================================================================


def test_get_flagged_memories_returns_flagged(backend: BackendHandle) -> None:
    b = backend.backend
    flagged_id = _add(b, "flagged for review memory item", flagged_for_review=True)
    _add(b, "unflagged normal memory item")
    result = b.get_flagged_memories()
    ids = {m.id for m in result}
    assert flagged_id in ids


def test_get_never_accessed_stale_returns_target(backend: BackendHandle) -> None:
    b = backend.backend
    never_touched = _add(b, "never retrieved stale memory", staleness_score=4.0)
    result = b.get_never_accessed_stale(min_staleness=3.0)
    assert never_touched in {m.id for m in result}


def test_get_never_accessed_stale_excludes_notes(backend: BackendHandle) -> None:
    """Notes must NOT appear in get_never_accessed_stale output."""
    b = backend.backend
    note = b.add_memory(
        record=MemoryRecord(
            content="A stale note that should be excluded",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
            staleness_score=5.0,
        )
    )
    result = b.get_never_accessed_stale(min_staleness=3.0)
    assert note.id not in {m.id for m in result}


def test_get_high_staleness_useful_returns_target(backend: BackendHandle) -> None:
    b = backend.backend
    target = _add(b, "stale but still useful memory", staleness_score=6.0, usefulness_score=4.0)
    result = b.get_high_staleness_useful(min_staleness=5.0, min_usefulness=3.0)
    assert target in {m.id for m in result}


def test_get_high_staleness_useful_excludes_notes(backend: BackendHandle) -> None:
    """Notes must NOT appear in get_high_staleness_useful output."""
    b = backend.backend
    note = b.add_memory(
        record=MemoryRecord(
            content="A high-staleness high-usefulness note",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
            staleness_score=7.0,
            usefulness_score=6.0,
        )
    )
    result = b.get_high_staleness_useful(min_staleness=5.0, min_usefulness=3.0)
    assert note.id not in {m.id for m in result}


def test_get_anomaly_high_staleness_useful_ids(backend: BackendHandle) -> None:
    b = backend.backend
    mid = _add(b, "anomaly: high staleness + useful", staleness_score=6.0, usefulness_score=4.0)
    _add(b, "normal memory for comparison")
    result = b.get_anomaly_high_staleness_useful_ids(min_staleness=5.0, min_usefulness=3.0)
    assert isinstance(result, list)
    assert mid in result


def test_get_anomaly_never_accessed_ids(backend: BackendHandle) -> None:
    b = backend.backend
    # Use a cutoff far in the future so the just-created memory qualifies
    import datetime  # noqa: PLC0415

    future_cutoff = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat()
    mid = _add(b, "never retrieved fresh memory for anomaly check")
    result = b.get_anomaly_never_accessed_ids(cutoff_iso=future_cutoff)
    assert isinstance(result, list)
    assert mid in result


def test_get_anomaly_flagged_ids(backend: BackendHandle) -> None:
    b = backend.backend
    mid = _add(b, "flagged memory for anomaly id check", flagged_for_review=True)
    result = b.get_anomaly_flagged_ids()
    assert isinstance(result, list)
    assert mid in result


def test_list_active_memory_ids_includes_only_active(backend: BackendHandle) -> None:
    b = backend.backend
    active_id = _add(b, "active memory for listing test")
    archived_id = _add(b, "archived memory excluded from listing")
    b.archive_memory(archived_id)
    result = b.list_active_memory_ids()
    assert active_id in result
    assert archived_id not in result


def test_get_stale_archivable_ids(backend: BackendHandle) -> None:
    import datetime  # noqa: PLC0415

    b = backend.backend
    # Memory with is_stale=True, staleness_score high, never accessed
    mid = b.add_memory(
        record=MemoryRecord(
            content="stale archivable memory candidate",
            category=MemoryCategory.FACT,
            source=MemorySource.AGENT,
            is_stale=True,
            staleness_score=9.5,
        )
    ).id
    _add(b, "normal non-stale memory control")
    future_cutoff = (datetime.datetime.utcnow() + datetime.timedelta(days=365)).isoformat()
    result = b.get_stale_archivable_ids(min_staleness=8.0, cutoff_iso=future_cutoff)
    assert isinstance(result, list)
    assert mid in result


def test_get_rehabilitable_rows(backend: BackendHandle) -> None:
    import datetime  # noqa: PLC0415

    b = backend.backend
    # A stale memory that was recently accessed (last_accessed_at set)
    past = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat()
    mid = b.add_memory(
        record=MemoryRecord(
            content="rehabilitable stale memory recently accessed",
            category=MemoryCategory.FACT,
            source=MemorySource.AGENT,
            is_stale=True,
            staleness_score=3.0,
            usefulness_score=8.0,  # usefulness > staleness
            last_accessed_at=datetime.datetime.utcnow(),
        )
    ).id
    # cutoff = yesterday → our memory (last_accessed today) qualifies
    result = b.get_rehabilitable_rows(cutoff_iso=past)
    assert isinstance(result, list)
    ids = [r[0] for r in result]
    assert mid in ids


def test_get_existing_relates_to_pairs(backend: BackendHandle) -> None:
    b = backend.backend
    a = _add(b, "relates pairs endpoint alpha")
    z = _add(b, "relates pairs endpoint zeta")
    _link(b, a, z, ConceptLinkType.RELATES_TO)
    pairs = b.get_existing_relates_to_pairs()
    assert isinstance(pairs, set)
    assert frozenset({a, z}) in pairs


# ===========================================================================
# Section 12 — Search: FTS / filtering
# ===========================================================================


def test_search_basic_fts_finds_relevant(backend: BackendHandle) -> None:
    """Relevant memory appears in results; ranking is at least best-effort.

    Note: the conformance backend attaches a HashingEmbedder so the vector
    phase is active.  In a two-memory corpus the coffee machine memory may
    receive a small non-zero vector score and appear in the result set too.
    We assert only that the relevant memory (parking garage) is retrieved —
    not that the unrelated one is absent — to keep the test backend-agnostic
    across fusion strategies.
    """
    b = backend.backend
    mid = _add(b, "parking garage integration is complete and live")
    _add(b, "coffee machine broken in the kitchen today")
    resp = b.search(SearchRequest(query="parking garage"))
    assert resp.total_found >= 1
    assert mid in {m.id for m in resp.memories}


def test_search_prefix_matches_compound_word(backend: BackendHandle) -> None:
    """Prefix query 'video' should match 'VIDEOWALL' via prefix expansion."""
    b = backend.backend
    mid = _add(b, "PC VIDEOWALL U-Center login credentials username password")
    resp = b.search(SearchRequest(query="video wall display login"))
    assert mid in {m.id for m in resp.memories}


def test_search_space_split_compound_matches(backend: BackendHandle) -> None:
    """Query 'video wall' (two tokens) should match stored 'videowall' (one token)."""
    b = backend.backend
    mid = _add(b, "PC VIDEOWALL U-Center setup documentation notes")
    resp = b.search(SearchRequest(query="video wall"))
    assert mid in {m.id for m in resp.memories}


def test_search_creates_query_session(backend: BackendHandle) -> None:
    b = backend.backend
    _add(b, "session lineage check memory content")
    resp = b.search(SearchRequest(query="lineage"))
    assert resp.session_id
    session = b.get_session(resp.session_id)
    assert session is not None
    assert session.query_text == "lineage"


def test_search_bumps_retrieval_count(backend: BackendHandle) -> None:
    b = backend.backend
    mid = _add(b, "retrieval counter memory unique token")
    b.search(SearchRequest(query="retrieval counter"))
    fetched = b.get_memory(mid)
    assert fetched is not None
    assert fetched.retrieval_count >= 1


def test_search_excludes_archived_by_default(backend: BackendHandle) -> None:
    b = backend.backend
    mid = _add(b, "archived banana memory to hide")
    b.archive_memory(mid)
    resp = b.search(SearchRequest(query="banana"))
    assert mid not in {m.id for m in resp.memories}


def test_search_excludes_stale_by_default(backend: BackendHandle) -> None:
    b = backend.backend
    mid = b.add_memory(
        content="stale mango memory excluded default",
        category="fact",
        is_stale=True,
    ).id
    resp = b.search(SearchRequest(query="mango"))
    assert mid not in {m.id for m in resp.memories}


def test_search_respects_limit(backend: BackendHandle) -> None:
    b = backend.backend
    for i in range(6):
        _add(b, f"limited result number {i} apple orchard harvest")
    resp = b.search(SearchRequest(query="apple orchard", limit=3))
    assert len(resp.memories) <= 3


# ===========================================================================
# Section 13 — Notes auto-include channel
# ===========================================================================


def test_auto_include_not_counted_in_total_found(backend: BackendHandle) -> None:
    """Auto-included notes do NOT count toward total_found (separate channel)."""
    b = backend.backend
    target_id = _add(b, "result memory about Helm chart deployments and GitOps")
    note = _note(b, "my personal note about Helm GitOps workflow")
    _annotates(b, note.id, target_id)
    resp = b.search(SearchRequest(query="Helm chart deployments"))
    assert resp.total_found == len(resp.memories)


def test_auto_include_archived_notes_excluded(backend: BackendHandle) -> None:
    """An archived annotating note must NOT appear in notes_on_results."""
    b = backend.backend
    target_id = _add(b, "result memory about Terraform infrastructure code")
    note = _note(b, "an archived note about Terraform infrastructure")
    _annotates(b, note.id, target_id)
    b.archive_memory(note.id)
    resp = b.search(SearchRequest(query="Terraform infrastructure code"))
    if target_id in resp.notes_on_results:
        assert not any(n.id == note.id for n in resp.notes_on_results[target_id])


def test_auto_include_populates_notes_on_results(backend: BackendHandle) -> None:
    """A note that ANNOTATES a result memory appears in notes_on_results."""
    b = backend.backend
    target_id = _add(b, "Kangaroo facts about marsupials in Australia outback")
    note = _note(b, "my note about kangaroos and marsupials Australia")
    _annotates(b, note.id, target_id)
    resp = b.search(SearchRequest(query="kangaroo marsupial"))
    if target_id in {m.id for m in resp.memories}:
        # If the target ranked, its note must be in notes_on_results
        notes = resp.notes_on_results.get(target_id, [])
        assert any(n.id == note.id for n in notes)


# ===========================================================================
# Section 14 — Vector search (capability-gated)
# ===========================================================================


@pytest.mark.vector
def test_vector_search_returns_non_empty_results(backend: BackendHandle) -> None:
    """With embedder attached, vector phase produces scores for stored memories."""
    b = backend.backend
    if not b.vector_search_available():
        pytest.skip("vector search not available on this backend")
    _add(b, "kubernetes pod autoscaling deployment configuration")
    resp = b.search(SearchRequest(query="kubernetes autoscaling"))
    assert resp.total_found >= 1


@pytest.mark.vector
def test_vector_search_memory_exists_with_content(backend: BackendHandle) -> None:
    """memory_exists_with_content returns True for exact match, False otherwise."""
    b = backend.backend
    _add(b, "exact content for dedup check unique phrase here")
    assert b.memory_exists_with_content("exact content for dedup check unique phrase here") is True
    assert b.memory_exists_with_content("content that was never stored anywhere") is False


@pytest.mark.vector
def test_mixed_dimension_embedding_survival(backend: BackendHandle) -> None:
    """A memory with a different-dimension embedding causes NULL distance; search must not crash.

    This test exercises the backend's dimension guard:
    - SQLite: ``vec_distance_cosine`` returns NULL for mismatched BLOBs → row skipped in
      the vector phase; memory still found via FTS.
    - Postgres: ``WHERE vector_dims(embedding) = %s`` filters mismatched rows; memory
      still found via FTS.

    The test injects a wrong-dimension (8-dim) embedding directly into the DB so it
    bypasses the normal embedding pipeline.  Both backends expose a test-only injection
    helper so this test runs on ALL backends without skipping.
    """
    import numpy as np  # noqa: PLC0415

    b = backend.backend
    if not b.vector_search_available():
        pytest.skip("vector search not available on this backend")

    mid = _add(b, "PC VIDEOWALL credentials login note for cross-dim test")
    b2 = backend.new_connection()
    try:
        from mintmory.core.storage import SqliteBackend  # noqa: PLC0415

        if isinstance(b2, SqliteBackend):
            # Inject a raw 8-dim BLOB directly into SQLite.
            conn = b2.connect()
            conn.execute(
                "UPDATE memories SET embedding = ? WHERE id = ?",
                (np.zeros(8, dtype=np.float32).tobytes(), mid),
            )
            conn.commit()
        else:
            # PostgresBackend (and any future backend) exposes a test-only helper
            # that stores a wrong-dimension vector via the pool.
            from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415

            if not isinstance(b2, PostgresBackend):
                pytest.skip(f"mixed-dim injection not implemented for {type(b2).__name__}")
            b2._inject_wrong_dim_embedding(mid, dim=8)
    finally:
        b2.close()

    resp = b.search(SearchRequest(query="videowall login credentials"))
    # Search must not raise; the memory must still be found via FTS even though
    # the vector phase skips the mismatched-dimension row.
    assert mid in {m.id for m in resp.memories}


# ===========================================================================
# Section 15 — Trigram substring search (capability-gated)
# ===========================================================================


@pytest.mark.trigram
def test_trigram_substring_match(backend: BackendHandle) -> None:
    """'wall' is a substring of 'firewall'; trigram search must find the memory."""
    b = backend.backend
    mid = _add(b, "firewall configuration notes for security audit review")
    resp = b.search(SearchRequest(query="wall"))
    if resp.total_found == 0:
        pytest.skip("trigram substring search not available on this backend")
    assert mid in {m.id for m in resp.memories}


@pytest.mark.trigram
def test_trigram_finds_infix_substring(backend: BackendHandle) -> None:
    """Infix substring: 'center' inside 'U-Center' must be retrievable."""
    b = backend.backend
    mid = _add(b, "PC U-Center GNSS software configuration file location path")
    resp = b.search(SearchRequest(query="center software"))
    if resp.total_found == 0:
        pytest.skip("trigram substring search not available on this backend")
    assert mid in {m.id for m in resp.memories}


# ===========================================================================
# Section 16 — Cross-connection visibility
# ===========================================================================


def test_write_on_one_handle_visible_on_second(backend: BackendHandle) -> None:
    """A write committed on handle A must be visible to handle B (same DB)."""
    b1 = backend.backend
    mid = _add(b1, "cross-connection visibility check memory content unique")
    b2 = backend.new_connection()
    try:
        fetched = b2.get_memory(mid)
        assert fetched is not None
        assert fetched.content == "cross-connection visibility check memory content unique"
    finally:
        b2.close()


# ===========================================================================
# Section 17 — Ping
# ===========================================================================


def test_ping_returns_true(backend: BackendHandle) -> None:
    assert backend.backend.ping() is True


# ===========================================================================
# Section 18 — memory_exists_with_content (always available)
# ===========================================================================


def test_memory_exists_true_for_existing(backend: BackendHandle) -> None:
    b = backend.backend
    _add(b, "hello world test content exists check unique foobar")
    assert (
        b.memory_exists_with_content("hello world test content exists check unique foobar") is True
    )


def test_memory_exists_false_for_missing(backend: BackendHandle) -> None:
    assert (
        backend.backend.memory_exists_with_content("this content was never stored anywhere")
        is False
    )


# ===========================================================================
# Section 19 — vector_search_available (always callable)
# ===========================================================================


def test_vector_search_available_returns_bool(backend: BackendHandle) -> None:
    result = backend.backend.vector_search_available()
    assert isinstance(result, bool)


# ===========================================================================
# Section 20 — anchor_candidates (side-effect-free note-anchoring candidates)
# ===========================================================================


def test_anchor_candidates_returns_sorted_scored_pairs(backend: BackendHandle) -> None:
    """anchor_candidates returns (score, record) pairs <=limit, sorted best-first.

    The topically-relevant memory must rank first when it is the only FTS match.
    """
    b = backend.backend
    target = _add(b, "python asyncio event loop coroutine await concurrent future task")
    _add(b, "completely unrelated topic about kitchen appliances maintenance")
    _add(b, "cooking recipes dinner ideas ingredients spices preparation")

    results = b.anchor_candidates(about="python asyncio coroutine", limit=5)

    assert len(results) <= 5
    for score, rec in results:
        assert isinstance(score, float)
        assert isinstance(rec, MemoryRecord)
    scores = [s for s, _ in results]
    assert scores == sorted(scores, reverse=True), "pairs must be sorted best-first"
    ids = [rec.id for _, rec in results]
    assert target in ids, "topically-relevant memory must appear in candidates"
    # With isolated vocabularies the relevant memory is the sole FTS hit → rank 1
    assert results[0][1].id == target, "topically-relevant memory must rank first"


def test_anchor_candidates_side_effect_free(backend: BackendHandle) -> None:
    """anchor_candidates must NOT bump retrieval_count on any memory."""
    b = backend.backend
    mid = _add(b, "side effect check memory about software engineering principles design")
    before = b.get_memory(mid)
    assert before is not None
    count_before = before.retrieval_count

    b.anchor_candidates(about="software engineering principles", limit=3)

    after = b.get_memory(mid)
    assert after is not None
    assert after.retrieval_count == count_before, "anchor_candidates must NOT bump retrieval_count"


def test_anchor_candidates_limit_honoured(backend: BackendHandle) -> None:
    """anchor_candidates returns at most ``limit`` pairs regardless of corpus size."""
    b = backend.backend
    for i in range(10):
        _add(b, f"memory topic number {i} for anchor limit conformance test content here")
    results = b.anchor_candidates(about="memory topic limit test", limit=3)
    assert len(results) <= 3


# ===========================================================================
# Section 21 — list_notes (filtering, archived, temporal boundary)
# ===========================================================================


def test_list_notes_returns_plain_note(backend: BackendHandle) -> None:
    """A plain user note appears in list_notes() with default parameters."""
    b = backend.backend
    note = _note(b, "my personal reminder about the team meeting schedule agenda")
    results = b.list_notes()
    assert note.id in {r.id for r in results}


def test_list_notes_excludes_archived_by_default(backend: BackendHandle) -> None:
    """Archived notes are excluded when include_archived=False (default)."""
    b = backend.backend
    note = _note(b, "archived note that should be excluded from default list view")
    b.archive_memory(note.id)

    results_default = b.list_notes(include_archived=False)
    assert note.id not in {r.id for r in results_default}


def test_list_notes_includes_archived_when_flag_set(backend: BackendHandle) -> None:
    """include_archived=True brings archived notes back into list_notes()."""
    b = backend.backend
    note = _note(b, "archived note visible only with include_archived flag set true")
    b.archive_memory(note.id)

    results_all = b.list_notes(include_archived=True)
    assert note.id in {r.id for r in results_all}


def test_list_notes_overdue_includes_past_due(backend: BackendHandle) -> None:
    """A note with valid_from in the past appears under overdue=True.

    This pins the boundary semantics that differ between SQLite TEXT lexicographic
    comparison and Postgres timestamptz (design §6.5 porting risk).
    """
    import datetime  # noqa: PLC0415

    b = backend.backend
    past = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    note = b.add_memory(
        record=MemoryRecord(
            content="overdue note with past due date for temporal boundary conformance",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
            valid_from=past,
        )
    )
    check_now = datetime.datetime.utcnow()

    overdue = b.list_notes(overdue=True, now=check_now)
    assert note.id in {r.id for r in overdue}, "past-due note must appear under overdue=True"


def test_list_notes_overdue_not_in_upcoming(backend: BackendHandle) -> None:
    """A past-due note must NOT appear under upcoming=True (boundary is exclusive)."""
    import datetime  # noqa: PLC0415

    b = backend.backend
    past = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    note = b.add_memory(
        record=MemoryRecord(
            content="overdue note must be absent from upcoming list boundary check",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
            valid_from=past,
        )
    )
    check_now = datetime.datetime.utcnow()

    upcoming = b.list_notes(upcoming=True, now=check_now)
    assert note.id not in {r.id for r in upcoming}, (
        "past-due note must NOT appear under upcoming=True"
    )


# ===========================================================================
# Section 22 — Vision / image port methods
# ===========================================================================


def test_list_image_file_records_returns_ext_records(backend: BackendHandle) -> None:
    """list_image_file_records returns memories with 'ext' metadata ordered by rel then id."""
    b = backend.backend
    rec_a = b.add_memory(
        record=MemoryRecord(
            content="image file record alpha for vision conformance list order test",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            metadata={"ext": ".png", "rel": "a/image_alpha.png"},
        )
    )
    rec_b = b.add_memory(
        record=MemoryRecord(
            content="image file record beta for vision conformance list order test",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            metadata={"ext": ".png", "rel": "b/image_beta.png"},
        )
    )
    results = b.list_image_file_records()
    ids = [r.id for r in results]
    assert rec_a.id in ids, "first image file record must appear in list"
    assert rec_b.id in ids, "second image file record must appear in list"
    # ORDER BY json_extract(metadata,'$.rel'), id — 'a/...' < 'b/...' lexicographically
    assert ids.index(rec_a.id) < ids.index(rec_b.id), "records must be ordered by rel ASC"


def test_list_image_file_records_excludes_kind_tagged(backend: BackendHandle) -> None:
    """Memories with a 'kind' metadata key must NOT appear in list_image_file_records."""
    b = backend.backend
    desc = b.add_memory(
        record=MemoryRecord(
            content="image description excluded from file records list vision conformance",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            metadata={"ext": ".png", "rel": "a/img.png", "kind": "image_description"},
        )
    )
    results = b.list_image_file_records()
    assert desc.id not in {r.id for r in results}, (
        "memory with 'kind' metadata must be excluded from list_image_file_records"
    )


def test_find_image_file_record_returns_active_match(backend: BackendHandle) -> None:
    """find_image_file_record returns the most-recent active match for a known rel path."""
    b = backend.backend
    rec = b.add_memory(
        record=MemoryRecord(
            content="image file record for find conformance test active match check",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            metadata={"ext": ".png", "rel": "photos/team.png", "path": "/data/photos/team.png"},
        )
    )
    found = b.find_image_file_record("photos/team.png")
    assert found is not None, "find_image_file_record must return the matching record"
    assert found.id == rec.id


def test_find_image_file_record_returns_none_for_miss(backend: BackendHandle) -> None:
    """find_image_file_record returns None when no active record matches the path."""
    b = backend.backend
    result = b.find_image_file_record("nonexistent/path/image.png")
    assert result is None


def test_get_annotating_descriptions_returns_description(backend: BackendHandle) -> None:
    """get_annotating_descriptions returns image_description memories ANNOTATING target."""
    b = backend.backend
    target_id = _add(b, "target image memory for annotation conformance test unique content")
    desc = b.add_memory(
        record=MemoryRecord(
            content="caption describing the target image photo content details conformance",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            is_note=False,
            metadata={"kind": "image_description"},
        )
    )
    _annotates(b, desc.id, target_id)

    results = b.get_annotating_descriptions(target_id, cap=10)
    assert any(r.id == desc.id for r in results), (
        "image description must appear in get_annotating_descriptions results"
    )


def test_get_annotating_descriptions_honours_cap(backend: BackendHandle) -> None:
    """get_annotating_descriptions returns at most ``cap`` results."""
    b = backend.backend
    target_id = _add(b, "target image for cap test unique memory content phrase here now")
    for i in range(5):
        desc = b.add_memory(
            record=MemoryRecord(
                content=f"image description number {i} for cap conformance honour test",
                category=MemoryCategory.EPISODIC,
                source=MemorySource.USER,
                is_note=False,
                metadata={"kind": "image_description"},
            )
        )
        _annotates(b, desc.id, target_id)

    results = b.get_annotating_descriptions(target_id, cap=3)
    assert len(results) <= 3


def test_get_annotating_descriptions_cap_zero_returns_empty(backend: BackendHandle) -> None:
    """cap=0 must return [] immediately without hitting the database."""
    b = backend.backend
    target_id = _add(b, "target for zero cap get annotating descriptions test unique")
    desc = b.add_memory(
        record=MemoryRecord(
            content="image description for zero cap conformance test unique phrase",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            is_note=False,
            metadata={"kind": "image_description"},
        )
    )
    _annotates(b, desc.id, target_id)
    results = b.get_annotating_descriptions(target_id, cap=0)
    assert results == []
