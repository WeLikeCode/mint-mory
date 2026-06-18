"""
Unit tests for StorageAdapter CRUD, defaults, archive, feedback caps, update.

Uses :memory: SQLite and the shared deterministic FakeEmbedder from
mintmory.core.embedder (no model, no network).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mintmory.core.embedder import FakeEmbedder
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import (
    MemoryCategory,
    MemoryRecord,
    MemorySource,
    SearchRequest,
)


@pytest.fixture()
def store() -> StorageAdapter:
    s = StorageAdapter(":memory:")
    s.initialise()
    return s


@pytest.fixture()
def store_with_embedder() -> StorageAdapter:
    s = StorageAdapter(":memory:", embedder=FakeEmbedder())
    s.initialise()
    return s


# ---------------------------------------------------------------------------
# add / get round-trip
# ---------------------------------------------------------------------------


def test_add_memory_from_kwargs_round_trip(store: StorageAdapter) -> None:
    record = store.add_memory(
        content="The user prefers dark mode in VSCode.",
        category="preference",
        source="user",
        confidence=0.9,
        verified=True,
    )
    fetched = store.get_memory(record.id)
    assert fetched is not None
    assert fetched.content == "The user prefers dark mode in VSCode."
    assert fetched.category == MemoryCategory.PREFERENCE
    assert fetched.source == MemorySource.USER
    assert fetched.confidence == pytest.approx(0.9)
    assert fetched.verified is True


def test_add_memory_from_record(store: StorageAdapter) -> None:
    rec = MemoryRecord(content="Azure SQL Server config", category=MemoryCategory.FACT)
    stored = store.add_memory(rec)
    assert stored.id == rec.id
    fetched = store.get_memory(rec.id)
    assert fetched is not None
    assert fetched.content == "Azure SQL Server config"


def test_add_memory_extracts_entities(store: StorageAdapter) -> None:
    record = store.add_memory(content="Claude uses MCP servers.", category="fact")
    assert record.entity_ids  # non-empty
    fetched = store.get_memory(record.id)
    assert fetched is not None
    assert "claude" in fetched.entity_ids
    assert "mcp" in fetched.entity_ids


def test_add_memory_preserves_supplied_entities(store: StorageAdapter) -> None:
    record = store.add_memory(
        content="Some content here", category="fact", entity_ids=["custom-entity"]
    )
    assert record.entity_ids == ["custom-entity"]


def test_round_trip_preserves_all_fields(store: StorageAdapter) -> None:
    rec = MemoryRecord(
        content="Round trip fidelity check",
        category=MemoryCategory.SKILL,
        source=MemorySource.AGENT,
        confidence=0.42,
        verified=True,
        usefulness_score=3.5,
        staleness_score=1.5,
        reinforcement_count=2,
        retrieval_count=4,
        is_stale=False,
        metadata={"project_id": "alpha", "tags": ["x", "y"]},
        contradicts_ids=["a", "b"],
    )
    store.add_memory(rec)
    fetched = store.get_memory(rec.id)
    assert fetched is not None
    assert fetched.confidence == pytest.approx(0.42)
    assert fetched.usefulness_score == pytest.approx(3.5)
    assert fetched.staleness_score == pytest.approx(1.5)
    assert fetched.reinforcement_count == 2
    assert fetched.retrieval_count == 4
    assert fetched.metadata == {"project_id": "alpha", "tags": ["x", "y"]}
    assert fetched.contradicts_ids == ["a", "b"]


def test_get_nonexistent_returns_none(store: StorageAdapter) -> None:
    assert store.get_memory("does-not-exist") is None


# ---------------------------------------------------------------------------
# defaults
# ---------------------------------------------------------------------------


def test_add_sets_defaults(store: StorageAdapter) -> None:
    record = store.add_memory(content="default check", category="fact")
    assert record.usefulness_score == 0.0
    assert record.staleness_score == 0.0
    assert record.reinforcement_count == 0
    assert record.retrieval_count == 0
    assert record.is_active is True
    assert record.is_archived is False
    assert record.is_stale is False


# ---------------------------------------------------------------------------
# trigram substring index (best-effort)
# ---------------------------------------------------------------------------


def _table_exists(store: StorageAdapter, name: str) -> bool:
    conn = store.connect()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def test_trigram_table_created_by_default(store: StorageAdapter) -> None:
    # fts5 with the 'trigram' tokenizer is available in modern SQLite builds;
    # this environment is expected to support it.
    assert store._trigram_loaded is True
    assert _table_exists(store, "memories_trigram")


def test_trigram_disabled_skips_table_but_search_works() -> None:
    s = StorageAdapter(":memory:", enable_trigram=False)
    s.initialise()
    assert s._trigram_loaded is False
    assert _table_exists(s, "memories_trigram") is False
    s.add_memory(content="firewall configuration notes", category="fact")
    # Search must still work (degrades to FTS/vector) with no trigram table.
    resp = s.search(SearchRequest(query="firewall"))
    assert resp.total_found >= 1
    s.close()


def test_trigram_migrates_legacy_external_content(tmp_path: Path) -> None:
    # Reproduce the legacy external-content trigram variant whose delete trigger
    # corrupts the index after a 'rebuild' backfill ("database disk image is
    # malformed" on the next UPDATE). initialise() must migrate it to the robust
    # standalone table so retrieval bumps (UPDATEs) no longer raise.
    db = tmp_path / "legacy.db"
    s = StorageAdapter(str(db))
    s.initialise()
    mid = s.add_memory(content="firewall videowall notes", category="fact").id
    conn = s.connect()
    conn.executescript(
        "DROP TRIGGER IF EXISTS memories_trigram_insert;"
        "DROP TRIGGER IF EXISTS memories_trigram_update;"
        "DROP TRIGGER IF EXISTS memories_trigram_delete;"
        "DROP TABLE IF EXISTS memories_trigram;"
        "CREATE VIRTUAL TABLE memories_trigram USING fts5("
        "content, content='memories', content_rowid='rowid', tokenize='trigram');"
    )
    conn.execute("INSERT INTO memories_trigram(memories_trigram) VALUES('rebuild')")
    conn.commit()
    s.close()

    # Re-open the same file -> initialise() migrates the legacy table.
    s2 = StorageAdapter(str(db))
    s2.initialise()
    assert s2._trigram_loaded is True
    # search() performs a retrieval-bump UPDATE that previously raised "malformed".
    resp = s2.search(SearchRequest(query="wall"))  # substring of videowall/firewall
    assert mid in {m.id for m in resp.memories}
    s2.close()


# ---------------------------------------------------------------------------
# embedder
# ---------------------------------------------------------------------------


def test_embedding_stored_when_embedder_present(store_with_embedder: StorageAdapter) -> None:
    record = store_with_embedder.add_memory(content="embed me", category="fact")
    conn = store_with_embedder.connect()
    row = conn.execute("SELECT embedding FROM memories WHERE id = ?", (record.id,)).fetchone()
    assert row["embedding"] is not None


def test_embedding_null_when_no_embedder(store: StorageAdapter) -> None:
    record = store.add_memory(content="no embed", category="fact")
    conn = store.connect()
    row = conn.execute("SELECT embedding FROM memories WHERE id = ?", (record.id,)).fetchone()
    assert row["embedding"] is None


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------


def test_archive_memory(store: StorageAdapter) -> None:
    record = store.add_memory(content="archive me", category="fact")
    store.archive_memory(record.id)
    fetched = store.get_memory(record.id)
    assert fetched is not None
    assert fetched.is_archived is True
    assert fetched.is_active is False


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def test_update_memory_partial(store: StorageAdapter) -> None:
    record = store.add_memory(content="original", category="fact", confidence=1.0)
    updated = store.update_memory(record.id, confidence=0.5, verified=True)
    assert updated.confidence == pytest.approx(0.5)
    assert updated.verified is True
    assert updated.content == "original"


def test_update_refreshes_updated_at(store: StorageAdapter) -> None:
    record = store.add_memory(content="time check", category="fact")
    original = record.updated_at
    updated = store.update_memory(record.id, confidence=0.3)
    assert updated.updated_at >= original


def test_update_content_reextracts_entities(store: StorageAdapter) -> None:
    record = store.add_memory(content="Claude rules", category="fact")
    updated = store.update_memory(record.id, content="Anthropic builds Sonnet")
    assert "anthropic" in updated.entity_ids
    assert "claude" not in updated.entity_ids


def test_update_missing_raises(store: StorageAdapter) -> None:
    with pytest.raises(KeyError):
        store.update_memory("nope", confidence=0.1)


# ---------------------------------------------------------------------------
# apply_feedback (per-memory primitive, score caps)
# ---------------------------------------------------------------------------


def test_apply_feedback_useful_increments(store: StorageAdapter) -> None:
    record = store.add_memory(content="useful one", category="fact")
    store.apply_feedback(record.id, useful=True, stale=False)
    fetched = store.get_memory(record.id)
    assert fetched is not None
    assert fetched.usefulness_score == pytest.approx(0.5)
    assert fetched.reinforcement_count == 1


def test_apply_feedback_stale_increments(store: StorageAdapter) -> None:
    record = store.add_memory(content="stale one", category="fact")
    store.apply_feedback(record.id, useful=False, stale=True)
    fetched = store.get_memory(record.id)
    assert fetched is not None
    assert fetched.staleness_score == pytest.approx(1.0)
    assert fetched.reinforcement_count == 0


def test_apply_feedback_sets_is_stale_at_threshold(store: StorageAdapter) -> None:
    record = store.add_memory(content="becoming stale", category="fact")
    for _ in range(7):  # 7 * 1.0 = 7.0 >= STALENESS_THRESHOLD
        store.apply_feedback(record.id, useful=False, stale=True)
    fetched = store.get_memory(record.id)
    assert fetched is not None
    assert fetched.staleness_score >= 7.0
    assert fetched.is_stale is True


def test_usefulness_cap(store: StorageAdapter) -> None:
    record = store.add_memory(content="cap useful", category="fact")
    for _ in range(50):
        store.apply_feedback(record.id, useful=True, stale=False)
    fetched = store.get_memory(record.id)
    assert fetched is not None
    assert fetched.usefulness_score <= 10.0


def test_staleness_cap(store: StorageAdapter) -> None:
    record = store.add_memory(content="cap stale", category="fact")
    for _ in range(50):
        store.apply_feedback(record.id, useful=False, stale=True)
    fetched = store.get_memory(record.id)
    assert fetched is not None
    assert fetched.staleness_score <= 10.0


def test_apply_feedback_missing_raises(store: StorageAdapter) -> None:
    with pytest.raises(KeyError):
        store.apply_feedback("nope", useful=True, stale=False)


def test_apply_feedback_stale_on_note_flags_not_penalises(store: StorageAdapter) -> None:
    """stale=True on a note sets flagged_for_review=True; staleness_score is UNCHANGED.

    This is byte-identical to §5d — the stale-vote is redirected to review
    instead of incrementing staleness. Non-note path is unchanged.
    """
    from mintmory.core.types import MemoryRecord, MemorySource  # noqa: PLC0415

    note = store.add_memory(
        record=MemoryRecord(
            content="A note that someone flags as stale",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )
    store.apply_feedback(note.id, useful=False, stale=True)
    fetched = store.get_memory(note.id)
    assert fetched is not None
    # staleness_score must be UNCHANGED (still 0.0)
    assert fetched.staleness_score == pytest.approx(0.0)
    # is_stale must stay False (threshold not reached since staleness_score == 0)
    assert fetched.is_stale is False
    # flagged_for_review must be set to True
    assert fetched.flagged_for_review is True


def test_apply_feedback_stale_on_non_note_unchanged_from_today(store: StorageAdapter) -> None:
    """Stale vote on a non-note increments staleness_score exactly as before (§5d)."""
    record = store.add_memory(content="A regular fact", category="fact")
    store.apply_feedback(record.id, useful=False, stale=True)
    fetched = store.get_memory(record.id)
    assert fetched is not None
    from mintmory.core import scoring  # noqa: PLC0415

    assert fetched.staleness_score == pytest.approx(scoring.STALE_INCREMENT)
    assert fetched.flagged_for_review is False


def test_apply_feedback_useful_on_note_still_increments(store: StorageAdapter) -> None:
    """Useful vote is unchanged for notes — they can still be reinforced."""
    from mintmory.core.types import MemoryRecord, MemorySource  # noqa: PLC0415

    note = store.add_memory(
        record=MemoryRecord(
            content="A note worth reinforcing",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )
    store.apply_feedback(note.id, useful=True, stale=False)
    fetched = store.get_memory(note.id)
    assert fetched is not None
    from mintmory.core import scoring  # noqa: PLC0415

    assert fetched.usefulness_score == pytest.approx(scoring.USEFUL_INCREMENT)
    assert fetched.reinforcement_count == 1


def test_get_never_accessed_stale_excludes_notes(store: StorageAdapter) -> None:
    """get_never_accessed_stale must NOT return notes (design §5e)."""
    from mintmory.core.types import MemoryRecord, MemorySource  # noqa: PLC0415

    # A note with high staleness (impossible via feedback but set directly)
    note = store.add_memory(
        record=MemoryRecord(
            content="A stale note with high staleness score",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
            staleness_score=5.0,
        )
    )
    result = store.get_never_accessed_stale(min_staleness=3.0)
    assert note.id not in {m.id for m in result}


def test_get_high_staleness_useful_excludes_notes(store: StorageAdapter) -> None:
    """get_high_staleness_useful must NOT return notes (design §5e)."""
    from mintmory.core.types import MemoryRecord, MemorySource  # noqa: PLC0415

    note = store.add_memory(
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
    result = store.get_high_staleness_useful(min_staleness=5.0, min_usefulness=3.0)
    assert note.id not in {m.id for m in result}


def test_supersede_memory(store: StorageAdapter) -> None:
    """supersede_memory marks the target as superseded, inactive, and archived."""
    note = store.add_memory(content="The authoritative note", category="fact")
    other = store.add_memory(content="The superseded record", category="fact")
    store.supersede_memory(other.id, by_id=note.id)
    fetched = store.get_memory(other.id)
    assert fetched is not None
    assert fetched.superseded_by == note.id
    assert fetched.is_active is False
    assert fetched.is_archived is True


def test_get_annotating_notes_empty_when_no_links(store: StorageAdapter) -> None:
    """get_annotating_notes returns [] when no ANNOTATES link exists."""
    mem = store.add_memory(content="A memory with no annotations", category="fact")
    result = store.get_annotating_notes(mem.id, cap=5)
    assert result == []


def test_get_annotating_notes_cap_zero_returns_empty(store: StorageAdapter) -> None:
    """cap=0 must return [] immediately."""
    mem = store.add_memory(content="Any memory", category="fact")
    assert store.get_annotating_notes(mem.id, cap=0) == []


def test_get_annotating_notes_returns_annotating_note(store: StorageAdapter) -> None:
    """get_annotating_notes returns a note that ANNOTATES the target memory."""
    from mintmory.core.types import (  # noqa: PLC0415
        ConceptLink,
        ConceptLinkType,
        LinkSource,
        MemoryRecord,
        MemorySource,
    )

    target = store.add_memory(content="A target memory about Postgres", category="fact")
    note = store.add_memory(
        record=MemoryRecord(
            content="My note about the Postgres target",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )
    store.add_link(
        ConceptLink(
            source_memory_id=note.id,
            target_memory_id=target.id,
            link_type=ConceptLinkType.ANNOTATES,
            entity="Postgres",
            source=LinkSource.USER,
            strength=1.0,
            confidence=0.9,
        )
    )
    result = store.get_annotating_notes(target.id, cap=5)
    assert len(result) == 1
    assert result[0].id == note.id
    assert result[0].is_note is True


def test_get_annotating_notes_excludes_archived_notes(store: StorageAdapter) -> None:
    """Archived notes must not appear in get_annotating_notes."""
    from mintmory.core.types import (  # noqa: PLC0415
        ConceptLink,
        ConceptLinkType,
        LinkSource,
        MemoryRecord,
        MemorySource,
    )

    target = store.add_memory(content="Target with archived annotator", category="fact")
    note = store.add_memory(
        record=MemoryRecord(
            content="Archived note",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )
    store.add_link(
        ConceptLink(
            source_memory_id=note.id,
            target_memory_id=target.id,
            link_type=ConceptLinkType.ANNOTATES,
            entity="test",
            source=LinkSource.USER,
            strength=1.0,
            confidence=1.0,
        )
    )
    store.archive_memory(note.id)
    result = store.get_annotating_notes(target.id, cap=5)
    assert result == []


def test_list_notes_returns_only_notes(store: StorageAdapter) -> None:
    """list_notes only returns rows where is_note=1."""
    from mintmory.core.types import MemoryRecord, MemorySource  # noqa: PLC0415

    note = store.add_memory(
        record=MemoryRecord(
            content="Note to list",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )
    store.add_memory(content="Regular memory", category="fact")
    result = store.list_notes()
    ids = {r.id for r in result}
    assert note.id in ids
    assert all(r.is_note for r in result)


# ---------------------------------------------------------------------------
# dreaming helpers
# ---------------------------------------------------------------------------


def test_get_flagged_memories(store: StorageAdapter) -> None:
    flagged = store.add_memory(content="flagged item", category="fact", flagged_for_review=True)
    store.add_memory(content="normal item", category="fact")
    result = store.get_flagged_memories()
    assert [m.id for m in result] == [flagged.id]


def test_get_high_staleness_useful(store: StorageAdapter) -> None:
    target = store.add_memory(
        content="stale but useful",
        category="fact",
        staleness_score=6.0,
        usefulness_score=4.0,
    )
    store.add_memory(content="fresh", category="fact")
    result = store.get_high_staleness_useful(min_staleness=5.0, min_usefulness=3.0)
    assert target.id in {m.id for m in result}


def test_get_never_accessed_stale(store: StorageAdapter) -> None:
    target = store.add_memory(content="never touched", category="fact", staleness_score=4.0)
    result = store.get_never_accessed_stale(min_staleness=3.0)
    assert target.id in {m.id for m in result}


# ---------------------------------------------------------------------------
# Re-embed guard (design §3) — regression: _embed called iff content changes
# ---------------------------------------------------------------------------


def test_update_non_content_field_does_not_call_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Updating a non-content field (confidence) must NOT invoke _embed.

    The re-embed guard in update_memory only computes an embedding when
    'content' is among the changed fields AND the new value differs from the
    stored one.
    """
    s = StorageAdapter(":memory:", embedder=FakeEmbedder())
    s.initialise()
    record = s.add_memory(content="original content", category="fact")

    embed_call_count: list[int] = [0]
    original_embed = s._embed

    def spy_embed(text: str) -> bytes | None:
        embed_call_count[0] += 1
        return original_embed(text)

    monkeypatch.setattr(s, "_embed", spy_embed)

    # Update a non-content field — _embed must NOT be called.
    s.update_memory(record.id, confidence=0.42)
    assert embed_call_count[0] == 0, "_embed was called when only a non-content field changed"
    s.close()


def test_update_content_field_does_call_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Updating the content field to a new value MUST invoke _embed exactly once.

    The re-embed guard lets the embedding be refreshed only when content truly
    changes, keeping the embedding in sync with the stored text.
    """
    s = StorageAdapter(":memory:", embedder=FakeEmbedder())
    s.initialise()
    record = s.add_memory(content="original content", category="fact")

    embed_call_count: list[int] = [0]
    original_embed = s._embed

    def spy_embed(text: str) -> bytes | None:
        embed_call_count[0] += 1
        return original_embed(text)

    monkeypatch.setattr(s, "_embed", spy_embed)

    # Update the content to a different value — _embed must be called once.
    s.update_memory(record.id, content="completely different content")
    assert embed_call_count[0] == 1, "_embed was not called when content changed"
    s.close()
