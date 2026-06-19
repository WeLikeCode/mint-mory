"""
Tests for the agent-supplied summary flow (design §7, Group 7).

Covers:
  (a) _select_summary_concepts equivalence — same results as generate_summaries
      (order, memory_count, truncation/cap, memory_ids index-alignment,
      top_k cap, stoplist exclusion).
  (b) collect_summary_jobs — no-summarizer/provider=none returns jobs;
      include_all vs default; current_summary populated; counts; below-min and
      stoplisted concepts excluded.
  (c) apply_summary — verbatim text, correct memory_count, is_current=True;
      idempotent overwrite; the incremental round-trip invariant (a just-applied
      concept does NOT reappear from collect_summary_jobs on an unchanged DB).

All tests use an in-memory StorageAdapter with embedder=None (FTS-only, no
network) and do NOT call any summarizer or LLM — the whole point of
collect_summary_jobs / apply_summary is that they work with provider=none.
"""

from __future__ import annotations

from mintmory.core.config import LinkSettings, SummarySettings
from mintmory.core.dreaming import DreamingEngine, _SummarySelection
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import MemoryCategory, MemoryRecord, SummaryJob

# ---------------------------------------------------------------------------
# Shared helpers (mirror test_dreaming.py helpers so we own no shared state)
# ---------------------------------------------------------------------------


def _store() -> StorageAdapter:
    s = StorageAdapter(":memory:", embedder=None)
    s.initialise()
    return s


def _fake_summarizer(concept: str, contents: list[str]) -> str:
    return f"Summary of {concept} ({len(contents)} memories)."


def _permissive(**over: object) -> LinkSettings:
    base: dict[str, object] = {
        "min_shared_entities": 1,
        "max_per_node": 0,
        "idf_weighted_strength": False,
        "entity_df_cap_ratio": 1.0,
        "stoplist_csv": "",
    }
    base.update(over)
    return LinkSettings(**base)  # type: ignore[arg-type]


def _add_with_entities(store: StorageAdapter, entities: list[str]) -> MemoryRecord:
    content = "Note about " + ", ".join(entities) + "."
    return store.add_memory(
        record=MemoryRecord(
            content=content,
            category=MemoryCategory.FACT,
            entity_ids=entities,
        )
    )


# ---------------------------------------------------------------------------
# (a) _select_summary_concepts equivalence
# ---------------------------------------------------------------------------


def test_select_concepts_sorted_order() -> None:
    """_select_summary_concepts returns selections in alphabetically sorted concept order."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["zzz"])
    for _ in range(3):
        _add_with_entities(store, ["aaa"])
    for _ in range(3):
        _add_with_entities(store, ["mmm"])

    engine = DreamingEngine(store, link_settings=_permissive())
    selections = engine._select_summary_concepts()

    concepts = [s.concept for s in selections]
    assert concepts == sorted(concepts), "Concepts must be in sorted order"
    assert concepts == ["aaa", "mmm", "zzz"]


def test_select_concepts_memory_count_matches_generate_summaries() -> None:
    """memory_count in _SummarySelection matches what generate_summaries records.

    Uses the classic aaa×5 / bbb×4 / ccc×3 fixture from the design §7 spec.
    After generate_summaries runs, the stored MemorySummary.memory_count for
    each concept must equal the _SummarySelection.memory_count.
    """
    store = _store()
    for _ in range(5):
        _add_with_entities(store, ["aaa"])
    for _ in range(4):
        _add_with_entities(store, ["bbb"])
    for _ in range(3):
        _add_with_entities(store, ["ccc"])

    engine = DreamingEngine(store, summarizer=_fake_summarizer, link_settings=_permissive())

    selections = engine._select_summary_concepts()
    sel_by_concept = {s.concept: s for s in selections}

    # generate_summaries must agree on the memory_count.
    engine.generate_summaries()
    for concept, sel in sel_by_concept.items():
        stored = store.get_summary(concept)
        assert stored is not None, f"Expected a stored summary for {concept}"
        assert stored.memory_count == sel.memory_count, (
            f"memory_count mismatch for {concept}: "
            f"selection={sel.memory_count}, stored={stored.memory_count}"
        )

    expected_counts = {"aaa": 5, "bbb": 4, "ccc": 3}
    for concept, expected in expected_counts.items():
        assert sel_by_concept[concept].memory_count == expected


def test_select_concepts_max_content_chars_truncation() -> None:
    """max_content_chars truncates every content entry; memory_ids stay index-aligned."""
    store = _store()
    for i in range(3):
        rec = store.add_memory(
            record=MemoryRecord(
                content="A" * 50 + f" {i}",
                category=MemoryCategory.FACT,
                entity_ids=["myentity"],
            )
        )
        _ = rec  # keep reference to confirm it was stored

    settings = SummarySettings(max_content_chars=10)
    engine = DreamingEngine(store, link_settings=_permissive(), summary_settings=settings)
    selections = engine._select_summary_concepts()

    assert len(selections) == 1
    sel = selections[0]
    assert sel.concept == "myentity"
    for content in sel.contents:
        assert len(content) <= 10, f"Content not truncated: {content!r}"
    assert len(sel.contents) == len(sel.memory_ids), (
        "contents and memory_ids must be index-aligned (same length)"
    )


def test_select_concepts_max_contents_cap_and_memory_ids_alignment() -> None:
    """max_contents caps both contents and memory_ids; memory_count is the pre-cap count."""
    store = _store()
    added_ids = []
    for _ in range(6):
        rec = _add_with_entities(store, ["capped"])
        added_ids.append(rec.id)

    settings = SummarySettings(max_contents=4, min_memories=3)
    engine = DreamingEngine(store, link_settings=_permissive(), summary_settings=settings)
    selections = engine._select_summary_concepts()

    assert len(selections) == 1
    sel = selections[0]
    assert sel.concept == "capped"
    assert sel.memory_count == 6, "Pre-cap count must be 6"
    assert len(sel.contents) == 4, "Post-cap contents must be 4"
    assert len(sel.memory_ids) == 4, "Post-cap memory_ids must be 4"
    # memory_ids must be a subset of the added ids (capped to 4 of 6, scan order by id).
    assert set(sel.memory_ids).issubset(set(added_ids)), (
        "memory_ids must come from the known added set"
    )


def test_select_concepts_top_k_respects_descending_count_tiebreak() -> None:
    """top_k keeps the most-evidenced concepts; tiebreak by concept name (asc)."""
    store = _store()
    for _ in range(5):
        _add_with_entities(store, ["aaa"])
    for _ in range(4):
        _add_with_entities(store, ["bbb"])
    for _ in range(3):
        _add_with_entities(store, ["ccc"])

    settings = SummarySettings(top_k=2)
    engine = DreamingEngine(store, link_settings=_permissive(), summary_settings=settings)
    selections = engine._select_summary_concepts()

    concepts = [s.concept for s in selections]
    # top_k=2 keeps aaa (5) and bbb (4); ccc (3) is dropped.
    assert "aaa" in concepts
    assert "bbb" in concepts
    assert "ccc" not in concepts
    assert len(concepts) == 2
    # Final order is sorted after top_k selection.
    assert concepts == sorted(concepts)


def test_select_concepts_stoplist_excluded() -> None:
    """A stoplisted concept does not appear in _select_summary_concepts."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["keepme"])
    for _ in range(3):
        _add_with_entities(store, ["dropme"])

    engine = DreamingEngine(
        store,
        link_settings=_permissive(stoplist_csv="dropme"),
    )
    selections = engine._select_summary_concepts()
    concepts = [s.concept for s in selections]

    assert "keepme" in concepts
    assert "dropme" not in concepts


def test_select_concepts_below_min_memories_excluded() -> None:
    """Concepts with fewer than min_memories active memories are NOT selected."""
    store = _store()
    for _ in range(2):
        _add_with_entities(store, ["toofew"])  # only 2, default min=3
    for _ in range(3):
        _add_with_entities(store, ["enough"])

    engine = DreamingEngine(store, link_settings=_permissive())
    selections = engine._select_summary_concepts()
    concepts = [s.concept for s in selections]

    assert "enough" in concepts
    assert "toofew" not in concepts


def test_select_concepts_returns_list_of_summary_selection() -> None:
    """Return type is list[_SummarySelection] with the expected fields."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["alpha"])

    engine = DreamingEngine(store, link_settings=_permissive())
    selections = engine._select_summary_concepts()

    assert isinstance(selections, list)
    assert len(selections) >= 1
    sel = selections[0]
    assert isinstance(sel, _SummarySelection)
    assert sel.concept == "alpha"
    assert isinstance(sel.contents, list)
    assert isinstance(sel.memory_ids, list)
    assert isinstance(sel.memory_count, int)
    assert sel.memory_count >= 3


# ---------------------------------------------------------------------------
# Equivalence proof: _select_summary_concepts produces what generate_summaries uses
# ---------------------------------------------------------------------------


def test_select_concepts_include_all_equals_generate_summaries_set() -> None:
    """collect_summary_jobs(include_all=True) yields exactly the concepts generate_summaries would
    summarise on the same DB + settings (selection parity invariant, design §6)."""
    store = _store()
    for _ in range(5):
        _add_with_entities(store, ["aaa"])
    for _ in range(4):
        _add_with_entities(store, ["bbb"])
    for _ in range(3):
        _add_with_entities(store, ["ccc"])
    # Below min — must be absent from both.
    for _ in range(2):
        _add_with_entities(store, ["zzz"])

    settings = SummarySettings(top_k=2)
    engine = DreamingEngine(
        store,
        summarizer=_fake_summarizer,
        link_settings=_permissive(),
        summary_settings=settings,
    )

    job_concepts = {j.concept for j in engine.collect_summary_jobs(include_all=True)}
    engine.generate_summaries()
    summarised_concepts = {
        concept
        for concept in ("aaa", "bbb", "ccc", "zzz")
        if store.get_summary(concept) is not None
    }

    assert job_concepts == summarised_concepts, (
        f"collect_summary_jobs(include_all=True) returned {job_concepts!r} "
        f"but generate_summaries stored {summarised_concepts!r}"
    )


# ---------------------------------------------------------------------------
# (b) collect_summary_jobs
# ---------------------------------------------------------------------------


def test_collect_jobs_works_without_summarizer() -> None:
    """collect_summary_jobs works when summarizer=None (no LLM configured)."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["concept"])

    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())
    jobs = engine.collect_summary_jobs()
    assert len(jobs) >= 1
    assert jobs[0].concept == "concept"


def test_collect_jobs_default_returns_only_needy_concepts() -> None:
    """Default (include_all=False) omits concepts with a current, count-matching summary."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["concept"])

    engine = DreamingEngine(store, summarizer=_fake_summarizer, link_settings=_permissive())
    # Before any summary exists, the concept needs one.
    jobs_before = engine.collect_summary_jobs()
    assert any(j.concept == "concept" for j in jobs_before)

    # Generate the summary so the count matches.
    engine.generate_summaries()

    # Now the concept should be omitted by the default filter.
    jobs_after = engine.collect_summary_jobs()
    assert not any(j.concept == "concept" for j in jobs_after)


def test_collect_jobs_include_all_returns_every_qualifying_concept() -> None:
    """include_all=True returns qualifying concepts even when their summary is up to date."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["concept"])

    engine = DreamingEngine(store, summarizer=_fake_summarizer, link_settings=_permissive())
    engine.generate_summaries()

    # Default: nothing needed.
    assert engine.collect_summary_jobs() == []
    # include_all: still returns the concept.
    jobs = engine.collect_summary_jobs(include_all=True)
    assert any(j.concept == "concept" for j in jobs)


def test_collect_jobs_current_summary_populated_from_existing() -> None:
    """current_summary is set when a MemorySummary already exists, None otherwise."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["mysvc"])

    engine = DreamingEngine(store, summarizer=_fake_summarizer, link_settings=_permissive())

    # Before any summary: current_summary must be None.
    jobs_before = engine.collect_summary_jobs()
    assert len(jobs_before) == 1
    assert jobs_before[0].current_summary is None

    # Generate the summary, then re-fetch with include_all.
    engine.generate_summaries()
    jobs_after = engine.collect_summary_jobs(include_all=True)
    assert len(jobs_after) == 1
    assert jobs_after[0].current_summary is not None
    assert "mysvc" in jobs_after[0].current_summary.lower()


def test_collect_jobs_needy_when_memory_count_drifts() -> None:
    """A concept reappears in the default list when its active count changes
    after the summary was written (memory_count drift)."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["drifter"])

    engine = DreamingEngine(store, summarizer=_fake_summarizer, link_settings=_permissive())
    engine.generate_summaries()
    # Immediately after: no job needed.
    assert engine.collect_summary_jobs() == []

    # Add a new memory mentioning the concept → count drifts.
    _add_with_entities(store, ["drifter"])
    jobs = engine.collect_summary_jobs()
    assert any(j.concept == "drifter" for j in jobs)


def test_collect_jobs_fields_correct() -> None:
    """SummaryJob has correct concept, memory_ids, contents, memory_count."""
    store = _store()
    added_ids = []
    for _ in range(4):
        rec = _add_with_entities(store, ["widget"])
        added_ids.append(rec.id)

    settings = SummarySettings(max_contents=20, min_memories=3)
    engine = DreamingEngine(
        store, summarizer=None, link_settings=_permissive(), summary_settings=settings
    )
    jobs = engine.collect_summary_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert isinstance(job, SummaryJob)
    assert job.concept == "widget"
    assert job.memory_count == 4
    assert len(job.contents) == 4
    assert len(job.memory_ids) == 4
    assert set(job.memory_ids) == set(added_ids)


def test_collect_jobs_memory_ids_contents_index_aligned() -> None:
    """memory_ids and contents are index-parallel (same length, same order)."""
    store = _store()
    for _ in range(5):
        _add_with_entities(store, ["aligned"])

    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())
    jobs = engine.collect_summary_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert len(job.memory_ids) == len(job.contents)


def test_collect_jobs_memory_count_is_pre_cap() -> None:
    """memory_count is the full pre-cap count; contents and memory_ids are capped."""
    store = _store()
    for _ in range(6):
        _add_with_entities(store, ["precap"])

    settings = SummarySettings(max_contents=3, min_memories=3)
    engine = DreamingEngine(
        store, summarizer=None, link_settings=_permissive(), summary_settings=settings
    )
    jobs = engine.collect_summary_jobs()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.memory_count == 6, "memory_count must be pre-cap (6)"
    assert len(job.contents) == 3, "contents capped at max_contents (3)"
    assert len(job.memory_ids) == 3, "memory_ids capped at max_contents (3)"


def test_collect_jobs_stoplist_concept_excluded() -> None:
    """A stoplisted concept never appears in collect_summary_jobs."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["included"])
    for _ in range(3):
        _add_with_entities(store, ["excluded"])

    engine = DreamingEngine(
        store,
        summarizer=None,
        link_settings=_permissive(stoplist_csv="excluded"),
    )
    jobs = engine.collect_summary_jobs(include_all=True)
    job_concepts = {j.concept for j in jobs}
    assert "included" in job_concepts
    assert "excluded" not in job_concepts


def test_collect_jobs_below_min_memories_excluded() -> None:
    """Concepts below min_memories never appear in collect_summary_jobs."""
    store = _store()
    for _ in range(2):
        _add_with_entities(store, ["scarce"])  # below default min_memories=3
    for _ in range(3):
        _add_with_entities(store, ["sufficient"])

    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())
    jobs = engine.collect_summary_jobs(include_all=True)
    job_concepts = {j.concept for j in jobs}
    assert "sufficient" in job_concepts
    assert "scarce" not in job_concepts


# ---------------------------------------------------------------------------
# (c) apply_summary
# ---------------------------------------------------------------------------


def test_apply_summary_persists_verbatim_text() -> None:
    """apply_summary stores summary_text verbatim (no stripping or LLM)."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["myapp"])

    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())
    text = "  My hand-crafted summary for myapp.  "
    engine.apply_summary("myapp", text)

    stored = store.get_summary("myapp")
    assert stored is not None
    assert stored.summary_text == text


def test_apply_summary_memory_count_equals_active_count() -> None:
    """apply_summary sets memory_count == the active concept count
    (same as _select_summary_concepts would report)."""
    store = _store()
    for _ in range(4):
        _add_with_entities(store, ["counted"])

    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())
    sel_before = [s for s in engine._select_summary_concepts() if s.concept == "counted"]
    assert len(sel_before) == 1
    expected_count = sel_before[0].memory_count  # must be 4

    engine.apply_summary("counted", "Summary text.")

    stored = store.get_summary("counted")
    assert stored is not None
    assert stored.memory_count == expected_count
    assert stored.memory_count == 4


def test_apply_summary_is_current_true() -> None:
    """apply_summary always stores is_current=True."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["fresh"])

    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())
    engine.apply_summary("fresh", "Fresh summary.")

    stored = store.get_summary("fresh")
    assert stored is not None
    assert stored.is_current is True


def test_apply_summary_returns_memory_summary() -> None:
    """apply_summary returns a MemorySummary with the correct fields."""
    from mintmory.core.types import MemorySummary

    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["returned"])

    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())
    result = engine.apply_summary("returned", "Returned summary text.")

    assert isinstance(result, MemorySummary)
    assert result.concept == "returned"
    assert result.summary_text == "Returned summary text."
    assert result.memory_count == 3
    assert result.is_current is True


def test_apply_summary_idempotent_overwrite() -> None:
    """Calling apply_summary twice on the same concept overwrites the first call.
    The row id is stable (INSERT OR REPLACE by concept)."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["idm"])

    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())
    engine.apply_summary("idm", "First version.")
    first = store.get_summary("idm")
    assert first is not None

    engine.apply_summary("idm", "Second version.")
    second = store.get_summary("idm")
    assert second is not None
    assert second.summary_text == "Second version."
    # Should be only one summary row for this concept.
    summaries = store.list_summaries()
    idm_summaries = [s for s in summaries if s.concept == "idm"]
    assert len(idm_summaries) == 1


def test_apply_summary_no_drift_incremental_round_trip() -> None:
    """The no-drift invariant: apply_summary(c, text) then collect_summary_jobs()
    (default) does NOT return c on an unchanged DB."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["roundtrip"])

    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())

    # Before: concept needs a summary.
    jobs_before = engine.collect_summary_jobs()
    assert any(j.concept == "roundtrip" for j in jobs_before)

    # Apply the summary.
    engine.apply_summary("roundtrip", "Agent-written summary.")

    # After: concept must NOT appear in the default list (no drift).
    jobs_after = engine.collect_summary_jobs()
    assert not any(j.concept == "roundtrip" for j in jobs_after)


def test_apply_summary_works_without_summarizer() -> None:
    """apply_summary does not require a summarizer (works with provider=none)."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["nollm"])

    # No summarizer, no conflict_resolver.
    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())
    result = engine.apply_summary("nollm", "No LLM needed.")

    stored = store.get_summary("nollm")
    assert stored is not None
    assert result.summary_text == "No LLM needed."


def test_apply_summary_concept_absent_from_store_stores_count_zero() -> None:
    """apply_summary accepts any concept string, even one with no active memories.
    memory_count is 0 for absent/below-min concepts."""
    store = _store()

    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())
    engine.apply_summary("ghost_concept", "Nobody mentions this.")

    stored = store.get_summary("ghost_concept")
    assert stored is not None
    assert stored.memory_count == 0


def test_apply_summary_stoplisted_concept_stores_count_zero() -> None:
    """apply_summary on a stoplisted concept records memory_count=0 (the
    stoplist means no memories are counted for it)."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["verboten"])

    engine = DreamingEngine(
        store,
        summarizer=None,
        link_settings=_permissive(stoplist_csv="verboten"),
    )
    engine.apply_summary("verboten", "Even stoplisted can get a manual summary.")

    stored = store.get_summary("verboten")
    assert stored is not None
    assert stored.memory_count == 0


def test_apply_summary_no_drift_after_idempotent_second_apply() -> None:
    """After two apply_summary calls for the same concept on an unchanged DB,
    collect_summary_jobs() (default) still returns no job for that concept."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["twice"])

    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())
    engine.apply_summary("twice", "Version 1.")
    engine.apply_summary("twice", "Version 2.")

    jobs = engine.collect_summary_jobs()
    assert not any(j.concept == "twice" for j in jobs)


# ---------------------------------------------------------------------------
# Interaction: collect_summary_jobs + apply_summary multi-concept round-trip
# ---------------------------------------------------------------------------


def test_multi_concept_incremental_round_trip() -> None:
    """apply_summary for each returned job -> no further jobs on next default call."""
    store = _store()
    for _ in range(3):
        _add_with_entities(store, ["alpha"])
    for _ in range(3):
        _add_with_entities(store, ["beta"])
    for _ in range(3):
        _add_with_entities(store, ["gamma"])

    engine = DreamingEngine(store, summarizer=None, link_settings=_permissive())

    first_jobs = engine.collect_summary_jobs()
    assert len(first_jobs) == 3

    # Apply a summary for every returned job.
    for job in first_jobs:
        engine.apply_summary(job.concept, f"Agent summary for {job.concept}.")

    # No more jobs on an unchanged DB.
    remaining = engine.collect_summary_jobs()
    assert remaining == [], f"Expected no remaining jobs, got: {remaining}"
