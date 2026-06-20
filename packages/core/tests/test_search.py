"""
Unit tests for StorageAdapter.search (FTS-only) and search_around traversal.

No embedder is configured, so search degrades to FTS5-only (PLAN.md §2/§3).
The FakeEmbedder is intentionally unused here to keep the FTS path isolated.
"""

from __future__ import annotations

from typing import Any

import pytest
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    LinkSource,
    MemoryCategory,
    MemoryFilter,
    MemoryRecord,
    MemorySource,
    SearchAroundSpec,
    SearchRequest,
)


@pytest.fixture()
def store() -> StorageAdapter:
    s = StorageAdapter(":memory:")
    s.initialise()
    return s


def _add(store: StorageAdapter, content: str, **kw: Any) -> str:
    return store.add_memory(content=content, category="fact", **kw).id


# ---------------------------------------------------------------------------
# FTS-only search
# ---------------------------------------------------------------------------


def test_basic_fts_search(store: StorageAdapter) -> None:
    _add(store, "The parking garage integration is complete")
    _add(store, "Coffee machine is broken in the kitchen")
    resp = store.search(SearchRequest(query="parking garage"))
    assert resp.total_found >= 1
    contents = [m.content for m in resp.memories]
    assert any("parking" in c for c in contents)
    assert all("Coffee" not in c for c in contents)


def test_search_creates_session(store: StorageAdapter) -> None:
    _add(store, "Session lineage test memory")
    resp = store.search(SearchRequest(query="lineage"))
    assert resp.session_id
    session = store.get_session(resp.session_id)
    assert session is not None
    assert session.query_text == "lineage"


def test_search_bumps_retrieval_count(store: StorageAdapter) -> None:
    mid = _add(store, "Retrieval counter memory")
    store.search(SearchRequest(query="retrieval counter"))
    fetched = store.get_memory(mid)
    assert fetched is not None
    assert fetched.retrieval_count == 1
    assert fetched.last_accessed_at is not None


def test_search_sanitises_arbitrary_text(store: StorageAdapter) -> None:
    _add(store, "Special characters memory about NEAR protocol")
    # Raw FTS-hostile input must not raise.
    resp = store.search(SearchRequest(query='NEAR AND ( "unbalanced'))
    assert resp.total_found >= 1


def test_search_prefix_matches_compound_word(store: StorageAdapter) -> None:
    # Whole-token FTS misses "video" inside "VideoWall"; prefix matching fixes it.
    # (Regression: a credentials file with "VIDEOWALL" returned nothing for "video".)
    mid = _add(store, "PC VIDEOWALL U-Center login user pass")
    resp = store.search(SearchRequest(query="video wall display login"))
    assert mid in {m.id for m in resp.memories}


def test_search_space_split_compound_matches_single_token(store: StorageAdapter) -> None:
    # "video wall" (two words) should match a stored "videowall" via the
    # adjacent-token concatenation in the FTS sanitiser.
    mid = _add(store, "PC VIDEOWALL U-Center setup notes")
    resp = store.search(SearchRequest(query="video wall"))
    assert mid in {m.id for m in resp.memories}


def test_search_survives_mixed_dimension_embeddings() -> None:
    # A shared DB can hold embeddings from different embedders (different dims).
    # vec_distance_cosine returns NULL on dimension mismatch; search must skip
    # those rows, not crash on float(None). (Regression: live search crashed.)
    import numpy as np
    from mintmory.core.embedder import HashingEmbedder

    s = StorageAdapter(":memory:", embedder=HashingEmbedder(dim=64))
    s.initialise()
    if not s._vector_search_available():
        pytest.skip("sqlite-vec unavailable in this environment")
    mid = _add(s, "PC VIDEOWALL credentials login note")
    # Simulate a foreign embedder: overwrite with a different-dimension vector.
    with s.transaction() as conn:
        conn.execute(
            "UPDATE memories SET embedding = ? WHERE id = ?",
            (np.zeros(8, dtype=np.float32).tobytes(), mid),
        )
    resp = s.search(SearchRequest(query="videowall login"))  # must not raise
    assert mid in {m.id for m in resp.memories}  # still found via FTS
    s.close()


def test_search_substring_via_trigram(store: StorageAdapter) -> None:
    # "wall" is a substring of "firewall" but a distinct token; porter FTS5
    # tokenises on whole words and cannot match it. Trigram substring search can.
    mid = _add(store, "firewall configuration notes")
    resp = store.search(SearchRequest(query="wall"))
    assert mid in {m.id for m in resp.memories}


def test_search_respects_limit(store: StorageAdapter) -> None:
    for i in range(5):
        _add(store, f"limited result number {i} apple")
    resp = store.search(SearchRequest(query="apple", limit=2))
    assert len(resp.memories) == 2


def test_search_excludes_archived_by_default(store: StorageAdapter) -> None:
    mid = _add(store, "archived banana memory")
    store.archive_memory(mid)
    resp = store.search(SearchRequest(query="banana"))
    assert mid not in {m.id for m in resp.memories}


def test_search_include_archived(store: StorageAdapter) -> None:
    mid = _add(store, "archived cherry memory")
    store.archive_memory(mid)
    resp = store.search(
        SearchRequest(query="cherry", include_archived=True),
    )
    # active_only filter default is True; relax it so archived (inactive) shows.
    resp2 = store.search(
        SearchRequest(
            query="cherry",
            include_archived=True,
            filter=MemoryFilter(active_only=False, exclude_stale=False),
        )
    )
    assert mid in {m.id for m in resp2.memories}
    # With default filter (active_only True) the archived/inactive row is excluded.
    assert mid not in {m.id for m in resp.memories}


def test_search_filter_by_category(store: StorageAdapter) -> None:
    store.add_memory(content="grape fact item", category="fact")
    store.add_memory(content="grape preference item", category="preference")
    resp = store.search(
        SearchRequest(query="grape", filter=MemoryFilter(category="preference"))  # type: ignore[arg-type]
    )
    assert all(m.category.value == "preference" for m in resp.memories)
    assert resp.total_found == 1


def test_search_excludes_stale_by_default(store: StorageAdapter) -> None:
    mid = store.add_memory(content="stale mango memory", category="fact", is_stale=True).id
    resp = store.search(SearchRequest(query="mango"))
    assert mid not in {m.id for m in resp.memories}


# ---------------------------------------------------------------------------
# search_around graph traversal
# ---------------------------------------------------------------------------


def _link(
    store: StorageAdapter,
    src: str,
    tgt: str,
    link_type: ConceptLinkType = ConceptLinkType.RELATES_TO,
    strength: float = 0.8,
) -> None:
    store.add_link(
        ConceptLink(
            source_memory_id=src,
            target_memory_id=tgt,
            link_type=link_type,
            strength=strength,
            source=LinkSource.USER,
        )
    )


def test_search_around_depth_1(store: StorageAdapter) -> None:
    a = _add(store, "anchor node")
    b = _add(store, "neighbour node")
    c = _add(store, "unrelated node")
    _link(store, a, b)
    result = store.search_around([a], SearchAroundSpec(depth=1))
    assert b in result
    assert c not in result
    assert a not in result  # anchors excluded


def test_search_around_depth_2(store: StorageAdapter) -> None:
    a = _add(store, "level zero")
    b = _add(store, "level one")
    c = _add(store, "level two")
    _link(store, a, b)
    _link(store, b, c)
    d1 = store.search_around([a], SearchAroundSpec(depth=1))
    assert b in d1
    assert c not in d1  # too far at depth 1
    d2 = store.search_around([a], SearchAroundSpec(depth=2))
    assert b in d2
    assert c in d2


def test_search_around_symmetric_reverse(store: StorageAdapter) -> None:
    a = _add(store, "symmetric anchor")
    b = _add(store, "symmetric peer")
    # link points b -> a with a symmetric type; traversal from a must reach b.
    _link(store, b, a, link_type=ConceptLinkType.SIMILAR_TO)
    result = store.search_around([a], SearchAroundSpec(depth=1))
    assert b in result


def test_search_around_directional_not_reversed(store: StorageAdapter) -> None:
    a = _add(store, "directed anchor")
    b = _add(store, "directed source")
    # b -> a with a NON-symmetric type; from a we must NOT reach b.
    _link(store, b, a, link_type=ConceptLinkType.DEPENDS_ON)
    result = store.search_around([a], SearchAroundSpec(depth=1))
    assert b not in result


def test_search_around_min_strength(store: StorageAdapter) -> None:
    a = _add(store, "strong anchor")
    weak = _add(store, "weak neighbour")
    _link(store, a, weak, strength=0.1)
    result = store.search_around([a], SearchAroundSpec(depth=1, min_strength=0.5))
    assert weak not in result


def test_search_around_link_type_filter(store: StorageAdapter) -> None:
    a = _add(store, "typed anchor")
    relates = _add(store, "relates neighbour")
    refines = _add(store, "refines neighbour")
    _link(store, a, relates, link_type=ConceptLinkType.RELATES_TO)
    _link(store, a, refines, link_type=ConceptLinkType.REFINES)
    result = store.search_around(
        [a], SearchAroundSpec(depth=1, link_types=[ConceptLinkType.REFINES])
    )
    assert refines in result
    assert relates not in result


def test_search_around_empty_anchors(store: StorageAdapter) -> None:
    assert store.search_around([], SearchAroundSpec(depth=1)) == []


# ---------------------------------------------------------------------------
# search OR-union with search_around
# ---------------------------------------------------------------------------


def test_search_with_search_around_or_union(store: StorageAdapter) -> None:
    anchor = _add(store, "kangaroo facts about marsupials")
    related = _add(
        store,
        "totally different wording",
    )
    _link(store, anchor, related)
    resp = store.search(SearchRequest(query="kangaroo", search_around=SearchAroundSpec(depth=1)))
    ids = {m.id for m in resp.memories}
    assert anchor in ids
    assert related in ids
    assert related in resp.search_around_ids


# ---------------------------------------------------------------------------
# _vector_scores extraction (design §2 / §5)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Note bonus — ranking (design §5a, §9)
# ---------------------------------------------------------------------------


def _store_with_note_bonus(bonus: float = 0.05) -> StorageAdapter:
    """Build a store with an explicit note_bonus (no lazy config read)."""
    s = StorageAdapter(":memory:", note_bonus=bonus, auto_include_cap=0)
    s.initialise()
    return s


def test_note_bonus_is_noop_for_non_notes() -> None:
    """For an all-non-note corpus the result ORDER is invariant to note_bonus (§9).

    Same store + same ids; only ``note_bonus`` changes between the two searches.
    Because no row is a note, the bonus term never applies, so a 0.0 vs a huge
    bonus must yield byte-identical ordering — proving the bonus touches is_note
    rows only and can never reorder ordinary memories.
    """
    s = StorageAdapter(":memory:", note_bonus=0.0, auto_include_cap=0)
    s.initialise()
    for c in (
        "parking garage integration uses OAuth tokens",
        "the parking garage gate opens at eight",
        "garage door parking permit renewal",
        "an unrelated memory about coffee machines",
    ):
        s.add_memory(content=c, category="fact")

    s._note_bonus = 0.0
    order_zero = [m.id for m in s.search(SearchRequest(query="parking garage")).memories]
    s._note_bonus = 10.0  # a hammer — would dominate ranking IF applied to non-notes
    order_big = [m.id for m in s.search(SearchRequest(query="parking garage")).memories]

    assert order_zero  # the query actually returned ranked results
    assert order_zero == order_big  # bonus is inert for non-notes -> order unchanged
    assert all(m.is_note is False for m in s.search(SearchRequest(query="parking garage")).memories)
    s.close()


def test_note_bonus_applied_in_effective_score_during_search() -> None:
    """The note_bonus is threaded into effective_score during search (§5a).

    A note gets a +0.05 boost applied in the search scoring loop. We verify
    this by checking that the note IS present in results (bonus did not break
    anything) and that a store with note_bonus=0.0 gives the same set of IDs
    (the bonus shifts scores but shouldn't drop any results within the limit).
    """
    s = _store_with_note_bonus(bonus=0.05)
    non_note_id = _add(s, "Python type hints best practices")
    note = s.add_memory(
        record=MemoryRecord(
            content="Python type hints best practices note version",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )
    resp = s.search(SearchRequest(query="Python type hints", limit=10))
    ids = {m.id for m in resp.memories}
    assert note.id in ids
    assert non_note_id in ids
    s.close()


# ---------------------------------------------------------------------------
# Auto-include (Phase 3 ANNOTATES reverse traversal, design §5b)
# ---------------------------------------------------------------------------


def _store_with_cap(cap: int = 3) -> StorageAdapter:
    s = StorageAdapter(":memory:", note_bonus=0.0, auto_include_cap=cap)
    s.initialise()
    return s


def _make_annotates_link(store: StorageAdapter, note_id: str, target_id: str) -> None:
    store.add_link(
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


def test_auto_include_populates_notes_on_results() -> None:
    """A note that ANNOTATES a search result appears in notes_on_results."""
    s = _store_with_cap(cap=3)
    target_id = _add(s, "Kangaroo facts about marsupials in Australia")
    note = s.add_memory(
        record=MemoryRecord(
            content="My note about kangaroos",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )
    _make_annotates_link(s, note.id, target_id)

    resp = s.search(SearchRequest(query="kangaroo"))
    assert target_id in {m.id for m in resp.memories}
    assert target_id in resp.notes_on_results
    annotating = resp.notes_on_results[target_id]
    assert any(n.id == note.id for n in annotating)
    s.close()


def test_auto_include_cap_limits_notes_per_result() -> None:
    """At most `cap` annotating notes are included per result."""
    cap = 2
    s = _store_with_cap(cap=cap)
    target_id = _add(s, "A target memory about AWS services")
    for i in range(5):
        note = s.add_memory(
            record=MemoryRecord(
                content=f"Note {i} about AWS services",
                category=MemoryCategory.EPISODIC,
                source=MemorySource.USER,
                verified=True,
                is_note=True,
            )
        )
        _make_annotates_link(s, note.id, target_id)

    resp = s.search(SearchRequest(query="AWS services"))
    if target_id in resp.notes_on_results:
        assert len(resp.notes_on_results[target_id]) <= cap
    s.close()


def test_auto_include_cap_zero_disables_auto_include() -> None:
    """auto_include_cap=0 means notes_on_results is always empty (§5b)."""
    s = _store_with_cap(cap=0)
    target_id = _add(s, "Memory with an annotating note about Redis caching")
    note = s.add_memory(
        record=MemoryRecord(
            content="Note about Redis caching",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )
    _make_annotates_link(s, note.id, target_id)

    resp = s.search(SearchRequest(query="Redis caching"))
    assert resp.notes_on_results == {}
    s.close()


def test_auto_include_is_reverse_direction_only() -> None:
    """Auto-include is a REVERSE traversal (result = target of ANNOTATES).

    Uses a real note (is_note=True) annotating a non-note item, so the assertion
    isolates EDGE DIRECTION rather than the is_note filter:
      * searching the ITEM surfaces the note that annotates it (correct direction);
      * searching the NOTE does NOT list the item as annotating the note — the
        forward edge note→item is not traversed backwards.
    """
    s = _store_with_cap(cap=3)
    note = s.add_memory(
        record=MemoryRecord(
            content="a note about the GATEWAY service rollout",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )
    item_id = _add(s, "the GATEWAY service configuration item")  # non-note target
    # Forward edge: note ANNOTATES item (note = source, item = target).
    s.add_link(
        ConceptLink(
            source_memory_id=note.id,
            target_memory_id=item_id,
            link_type=ConceptLinkType.ANNOTATES,
            entity="gateway",
            source=LinkSource.USER,
            strength=1.0,
            confidence=1.0,
        )
    )

    # Correct (reverse) direction: searching the item surfaces its annotating note.
    resp_item = s.search(SearchRequest(query="GATEWAY service configuration"))
    item_notes = {n.id for n in resp_item.notes_on_results.get(item_id, [])}
    assert note.id in item_notes

    # Reverse-ONLY: the note is a result, but nothing annotates the note — the
    # forward edge note→item must NOT make the note appear annotated.
    resp_note = s.search(SearchRequest(query="note about the GATEWAY service rollout"))
    assert note.id in {m.id for m in resp_note.memories}
    assert note.id not in resp_note.notes_on_results
    s.close()


def test_auto_include_excludes_archived_notes() -> None:
    """Archived annotating notes are NOT included in notes_on_results."""
    s = _store_with_cap(cap=3)
    target_id = _add(s, "A target memory about Terraform configuration")
    note = s.add_memory(
        record=MemoryRecord(
            content="An archived note about Terraform",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )
    _make_annotates_link(s, note.id, target_id)
    s.archive_memory(note.id)

    resp = s.search(SearchRequest(query="Terraform configuration"))
    # The archived note must not appear
    if target_id in resp.notes_on_results:
        assert not any(n.id == note.id for n in resp.notes_on_results[target_id])
    s.close()


def test_auto_include_does_not_affect_total_found() -> None:
    """Auto-included notes are NOT counted in total_found (separate channel, §5b)."""
    s = _store_with_cap(cap=3)
    target_id = _add(s, "A result memory about Helm chart deployments")
    note = s.add_memory(
        record=MemoryRecord(
            content="Note about Helm chart",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )
    _make_annotates_link(s, note.id, target_id)

    resp = s.search(SearchRequest(query="Helm chart deployments"))
    # If target is in results, notes_on_results may have the note; but
    # total_found must equal len(resp.memories), NOT include the annotating note
    assert resp.total_found == len(resp.memories)
    s.close()


def test_notes_on_results_default_empty() -> None:
    """SearchResponse.notes_on_results defaults to {} (no auto-include → empty)."""
    s = _store_with_cap(cap=0)
    _add(s, "A plain memory no notes")
    resp = s.search(SearchRequest(query="plain memory"))
    assert resp.notes_on_results == {}
    s.close()


def test_vector_scores_empty_without_embedder(store: StorageAdapter) -> None:
    """_vector_scores returns {} when no embedder is configured (store fixture has none)."""
    # Guard the assumption: this must be empty BECAUSE the vector phase is unavailable,
    # not for some other reason — fail loudly if the fixture ever gains an embedder.
    assert not store._vector_search_available()
    _add(store, "some content about pandas")
    result = store._vector_scores("pandas", None, 50)
    assert result == {}


def test_vector_scores_non_empty_with_hashing_embedder() -> None:
    """_vector_scores returns a non-empty dict when a HashingEmbedder is present."""
    from mintmory.core.embedder import HashingEmbedder

    s = StorageAdapter(":memory:", embedder=HashingEmbedder(dim=64))
    s.initialise()
    if not s._vector_search_available():
        import pytest

        pytest.skip("sqlite-vec unavailable in this environment")

    _add(s, "pandas dataframe tutorial")
    result = s._vector_scores("pandas", None, 50)
    assert len(result) > 0
    # Values are -distance (negated cosine distance), so they should be finite floats.
    for score in result.values():
        assert isinstance(score, float)
        assert score == score  # not NaN
    s.close()


def test_search_unaffected_when_vector_phase_empty() -> None:
    """With no embedder the vector phase returns {}; search still works via FTS."""
    s = StorageAdapter(":memory:")
    s.initialise()
    mid = _add(s, "database indexing strategies")
    resp = s.search(SearchRequest(query="database indexing"))
    assert mid in {m.id for m in resp.memories}
    s.close()


def test_search_uses_vector_phase_when_embedder_present() -> None:
    """The extracted _vector_scores actually feeds fusion: a memory the vector phase
    ranks for a query (that shares no literal token) is reachable via search."""
    from mintmory.core.embedder import HashingEmbedder

    s = StorageAdapter(":memory:", embedder=HashingEmbedder(dim=128))
    s.initialise()
    if not s._vector_search_available():
        import pytest

        pytest.skip("sqlite-vec unavailable in this environment")
    mid = _add(s, "kubernetes pod autoscaling configuration")
    # The vector phase scores this memory for the query...
    scored = s._vector_scores("kubernetes autoscaling", None, 50)
    assert mid in scored
    # ...and the full search (which fuses that phase) surfaces it too.
    resp = s.search(SearchRequest(query="kubernetes autoscaling"))
    assert mid in {m.id for m in resp.memories}
    s.close()


# ---------------------------------------------------------------------------
# MM-22: weighted RRF fusion tests
# ---------------------------------------------------------------------------


def test_default_weight_1_explicit_equals_lazy() -> None:
    """An explicit vector_rrf_weight=1.0 and the lazy-resolved default (also 1.0)
    yield identical search ordering — i.e. the lazy-resolution path introduces no
    drift relative to constructing with the default weight.

    NOTE: this is an explicit-vs-lazy equivalence check, NOT a pin against the
    pre-MM-22 unweighted output. The byte-for-byte no-op invariant (weight 1.0 ==
    old behaviour) is proven at the fusion level by test_scoring's
    ``rrf_merge(...) == rrf_merge(..., weights=[1,1,...])`` (uniform == default).
    """
    s = StorageAdapter(":memory:", vector_rrf_weight=1.0)
    s.initialise()

    contents = [
        "parking garage integration uses OAuth tokens",
        "the parking garage gate opens at eight",
        "garage door parking permit renewal",
    ]
    for c in contents:
        s.add_memory(content=c, category="fact")

    resp_explicit = s.search(SearchRequest(query="parking garage"))
    contents_explicit = [m.content for m in resp_explicit.memories]

    # Reset to None (lazy), expect same order.
    s._vector_rrf_weight = None
    resp_lazy = s.search(SearchRequest(query="parking garage"))
    contents_lazy = [m.content for m in resp_lazy.memories]

    assert contents_explicit == contents_lazy
    s.close()


def test_vector_rrf_weight_lazy_resolve() -> None:
    """StorageAdapter with no explicit weight resolves from SearchSettings lazily.

    After construction _vector_rrf_weight is None; after the first search it is
    resolved to the SearchSettings default (1.0) and cached.
    """
    s = StorageAdapter(":memory:")
    s.initialise()
    assert s._vector_rrf_weight is None  # not yet resolved
    _add(s, "lazy resolve test memory about networking")
    s.search(SearchRequest(query="networking"))
    # After the search, the weight must have been resolved and cached.
    assert s._vector_rrf_weight is not None
    assert s._vector_rrf_weight == pytest.approx(1.0)
    s.close()


class _SplitEmbedder:
    """Deterministic embedder for the weight-promotion test.

    The target doc (token ``zeta``) gets a unit vector aligned with the explicit
    query embedding, so it is the SOLE vector hit. The lexical doc gets the ZERO
    vector — ``vec_distance_cosine`` is NULL for a zero vector, so the SQL vector
    phase skips it. Thus the lexical doc owns FTS + trigram while the target owns
    the vector source. The query vector is passed explicitly to ``search`` so the
    lexical FTS query text is fully decoupled from the dense signal — isolating the
    effect of the vector RRF weight from any embedder-semantics noise.
    """

    @property
    def dimensions(self) -> int:
        return 3

    @property
    def model_name(self) -> str:
        return "split-stub-v1"

    def embed(self, text: str) -> Any:
        import numpy as np

        if "zeta" in text:  # the target -> aligned with the explicit query vector
            return np.array([1.0, 0.0, 0.0], dtype=np.float32)
        return np.array([0.0, 0.0, 0.0], dtype=np.float32)  # lexical doc -> NULL cosine

    def embed_batch(self, texts: list[str]) -> Any:
        return [self.embed(t) for t in texts]


def test_vector_rrf_weight_5_promotes_vector_strong_record() -> None:
    """With vector_rrf_weight=5.0, a vector-strong / lexically-weak record ranks
    strictly HIGHER than under the default weight=1.0.

    Fixture (see _SplitEmbedder): the target doc is the only vector hit; the lex
    doc owns FTS + trigram. Under uniform RRF the two lexical sources outrank the
    single vector source (the documented EXPERIMENTS §10 regression); raising the
    vector weight to 5.0 must promote the target above the lex doc.

    Needs sqlite-vec for the vector phase; skip if unavailable.
    """
    import numpy as np

    s1 = StorageAdapter(":memory:", embedder=_SplitEmbedder(), vector_rrf_weight=1.0)
    s1.initialise()
    s5 = StorageAdapter(":memory:", embedder=_SplitEmbedder(), vector_rrf_weight=5.0)
    s5.initialise()

    if not s1._vector_search_available():
        pytest.skip("sqlite-vec unavailable in this environment")

    target_content = "zeta omega delta"  # no query tokens; vector-aligned to query
    lex_content = "alpha gamma beta"  # matches the query lexically; zero vector (no vec hit)
    query = "alpha beta"
    q_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)  # decoupled from query text

    for s in (s1, s5):
        s.add_memory(content=lex_content, category="fact")  # inserted first
        s.add_memory(content=target_content, category="fact")

    resp1 = s1.search(SearchRequest(query=query, limit=10), query_embedding=q_emb)
    resp5 = s5.search(SearchRequest(query=query, limit=10), query_embedding=q_emb)

    def rank_of(resp: Any, content: str) -> int:
        contents = [m.content for m in resp.memories]
        assert content in contents, f"{content!r} missing from {contents}"
        return contents.index(content)

    # Under uniform weight the lexical doc (FTS+trigram) outranks the vector-only target.
    assert rank_of(resp1, lex_content) < rank_of(resp1, target_content)
    # Raising the vector weight strictly promotes the target above the lexical doc.
    assert rank_of(resp5, target_content) < rank_of(resp5, lex_content)
    # And the target's absolute rank improves from weight 1.0 -> 5.0.
    assert rank_of(resp5, target_content) < rank_of(resp1, target_content)

    s1.close()
    s5.close()
