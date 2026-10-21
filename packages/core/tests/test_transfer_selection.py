"""RED tests for task 2 — selection, duplicates and record copy (``transfer.py``).

They trace requirement 3 (selection and one-level note expansion), requirement
4 (duplicate handling), requirement 5 (the copied record mapping), requirement
7.1/7.2 (one transaction / source unchanged) and the record parts of R9.2,
R9.4, R9.5, R9.6 and R9.9. Link copying is task 3 and is deliberately not
asserted here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from mintmory.core import transfer
from mintmory.core.storage import SqliteBackend
from mintmory.core.transfer import CopyReport, CopySelectionError
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    LinkSource,
    MemoryCategory,
    MemoryFilter,
    MemoryRecord,
    MemorySource,
    MemorySummary,
    SearchRequest,
)


@pytest.fixture
def store(tmp_path: Path) -> SqliteBackend:
    return _new_store(tmp_path)


def _new_store(tmp_path: Path, name: str = "copy.db") -> SqliteBackend:
    backend = SqliteBackend(tmp_path / name)
    backend.initialise()
    return backend


def _copy(store: SqliteBackend, **kwargs: Any) -> CopyReport:
    """Call the entry point, turning the task-1 placeholder into an assertion.

    ``copy_between_tenants`` still ends in ``NotImplementedError`` until task 2
    is implemented. Reporting that as an assertion keeps the red step a real
    failure instead of a collection/execution error.
    """
    try:
        return transfer.copy_between_tenants(store, **kwargs)
    except NotImplementedError as exc:
        raise AssertionError(f"copy_between_tenants is not implemented yet: {exc}") from exc


def _add(
    store: SqliteBackend,
    memory_id: str,
    content: str,
    tenant: str = "acme",
    **fields: Any,
) -> MemoryRecord:
    if "category" not in fields:
        fields["category"] = MemoryCategory.FACT
    return store.add_memory(
        record=MemoryRecord(id=memory_id, content=content, tenant_id=tenant, **fields)
    )


def _link(
    store: SqliteBackend,
    source_id: str,
    target_id: str,
    link_type: ConceptLinkType,
    tenant: str = "acme",
    **fields: Any,
) -> ConceptLink:
    return store.add_link(
        ConceptLink(
            source_memory_id=source_id,
            target_memory_id=target_id,
            link_type=link_type,
            tenant_id=tenant,
            **fields,
        )
    )


def _all_memories(store: SqliteBackend, tenant: str) -> list[MemoryRecord]:
    rows = (
        store.connect()
        .execute("SELECT id FROM memories WHERE tenant_id = ? ORDER BY id", (tenant,))
        .fetchall()
    )
    records = [store.get_memory(str(row["id"]), tenant_id=tenant) for row in rows]
    return [record for record in records if record is not None]


def _contents(store: SqliteBackend, tenant: str) -> list[str]:
    return [record.content for record in _all_memories(store, tenant)]


def _memory_dumps(store: SqliteBackend, tenant: str) -> dict[str, dict[str, Any]]:
    return {record.id: record.model_dump() for record in _all_memories(store, tenant)}


def _link_dumps(
    store: SqliteBackend, tenant: str, memory_ids: list[str]
) -> dict[str, dict[str, Any]]:
    links: dict[str, dict[str, Any]] = {}
    for memory_id in memory_ids:
        for link in store.get_links(memory_id, tenant_id=tenant):
            links[link.id] = link.model_dump()
    return links


def _seed(store: SqliteBackend) -> None:
    """R9.1 seed: acme with m1/m2/n1/m3, a summary, and global g1."""
    store.create_tenant("acme")
    store.create_tenant("beta")
    _add(
        store,
        "m1",
        "Alice works at Acme",
        source=MemorySource.USER,
        entity_ids=["Alice", "Acme"],
        confidence=0.8,
        verified=True,
        valid_from=datetime(2026, 1, 1),
        valid_until=datetime(2027, 1, 1),
        usefulness_score=4.0,
        staleness_score=2.0,
        reinforcement_count=3,
        retrieval_count=5,
        contradicts_ids=["m2"],
        flagged_for_review=True,
        last_accessed_at=datetime(2026, 6, 1),
        metadata={"project": "x"},
        created_at=datetime(2020, 1, 1),
        updated_at=datetime(2020, 1, 1),
    )
    _add(
        store,
        "m2",
        "Bob works at Acme",
        entity_ids=["Bob", "Acme"],
        created_at=datetime(2020, 1, 2),
        updated_at=datetime(2020, 1, 2),
    )
    _add(
        store,
        "m3",
        "Archived Alice fact",
        is_archived=True,
        created_at=datetime(2019, 1, 1),
        updated_at=datetime(2019, 1, 1),
    )
    _add(
        store,
        "n1",
        "Alice prefers mornings",
        category=MemoryCategory.EPISODIC,
        source=MemorySource.USER,
        verified=True,
        is_note=True,
        entity_ids=["Alice"],
        metadata={"anchor_memory_id": "m1"},
        created_at=datetime(2020, 1, 3),
        updated_at=datetime(2020, 1, 3),
    )
    _link(
        store,
        "m1",
        "m2",
        ConceptLinkType.RELATES_TO,
        entity="Acme",
        strength=0.7,
        confidence=0.9,
        source=LinkSource.USER,
        verified=True,
    )
    _link(
        store,
        "n1",
        "m1",
        ConceptLinkType.ANNOTATES,
        entity="Alice",
        strength=1.0,
        confidence=1.0,
        source=LinkSource.USER,
        verified=True,
    )
    _add(store, "g1", "Global fact", tenant="global")
    store.upsert_summary(
        MemorySummary(concept="acme", summary_text="Acme summary", memory_count=2, tenant_id="acme")
    )


# ---------------------------------------------------------------------------
# R3.1 — explicit ids: input order, no repeats, unfit rows counted once
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-0380775d", "C-d9e27376")
def test_explicit_ids_copy_in_input_order_and_count_unfit_rows_once(
    store: SqliteBackend,
) -> None:
    _seed(store)
    store.create_tenant("gamma")
    _add(store, "m4", "Inactive Alice fact", is_active=False)
    _add(store, "m5", "Superseded Alice fact", superseded_by="m1")
    _add(store, "gamma-row", "Gamma secret", tenant="gamma")

    report = _copy(
        store,
        source_tenant="acme",
        dest_tenant="beta",
        memory_ids=["m2", "m1", "m2", "m3", "m4", "m5", "nope", "gamma-row"],
    )

    assert report.memories_copied == 2
    assert report.notes_copied == 1
    assert report.memories_skipped_not_found == 5
    assert report.memories_skipped_duplicate == 0
    assert list(report.id_map) == ["m2", "m1", "n1"]

    contents = _contents(store, "beta")
    assert contents.count("Bob works at Acme") == 1
    assert contents.count("Alice works at Acme") == 1
    assert contents.count("Alice prefers mornings") == 1
    assert "Archived Alice fact" not in contents
    assert "Inactive Alice fact" not in contents
    assert "Superseded Alice fact" not in contents
    assert "Gamma secret" not in contents


# ---------------------------------------------------------------------------
# R3.2 — filter and all_active selection, superseded dropped, cap after drop
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3affbf7d")
def test_filter_selects_matching_rows_and_drops_superseded(store: SqliteBackend) -> None:
    _seed(store)
    _add(store, "m4", "Stale Alice fact", is_stale=True)
    _add(store, "m5", "Superseded Alice fact", superseded_by="m1")

    report = _copy(
        store,
        source_tenant="acme",
        dest_tenant="beta",
        filter=MemoryFilter(category=MemoryCategory.FACT),
    )

    assert report.memories_copied == 2
    assert report.notes_copied == 1
    assert report.memories_skipped_not_found == 0
    assert report.memories_skipped_duplicate == 0
    assert set(report.id_map) == {"m1", "m2", "n1"}

    contents = _contents(store, "beta")
    assert contents.count("Alice works at Acme") == 1
    assert contents.count("Bob works at Acme") == 1
    assert "Stale Alice fact" not in contents
    assert "Superseded Alice fact" not in contents


@pytest.mark.l4("C-3affbf7d")
def test_filter_with_exclude_stale_false_keeps_stale_rows(store: SqliteBackend) -> None:
    _seed(store)
    _add(store, "m4", "Stale Alice fact", is_stale=True)

    report = _copy(
        store,
        source_tenant="acme",
        dest_tenant="beta",
        filter=MemoryFilter(category=MemoryCategory.FACT, exclude_stale=False),
    )

    assert report.memories_copied == 3
    assert report.notes_copied == 1
    assert _contents(store, "beta").count("Stale Alice fact") == 1


@pytest.mark.l4("C-3affbf7d", "C-c38088c4")
def test_all_active_includes_stale_rows_and_drops_superseded(store: SqliteBackend) -> None:
    _seed(store)
    _add(store, "m4", "Stale Alice fact", is_stale=True)
    _add(store, "m5", "Superseded Alice fact", superseded_by="m1")

    report = _copy(store, source_tenant="acme", dest_tenant="beta", all_active=True)

    assert report.memories_copied == 3
    assert report.notes_copied == 1
    assert report.memories_skipped_not_found == 0
    assert report.memories_skipped_duplicate == 0
    assert "m5" not in report.id_map
    contents = _contents(store, "beta")
    assert contents.count("Alice works at Acme") == 1
    assert contents.count("Bob works at Acme") == 1
    assert contents.count("Stale Alice fact") == 1
    assert "Superseded Alice fact" not in contents


@pytest.mark.l4("C-3affbf7d")
def test_all_active_cap_applies_after_superseded_rows_are_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _new_store(tmp_path, "cap-after-drop.db")
    store.create_tenant("acme")
    store.create_tenant("beta")
    _add(store, "m1", "First fact")
    _add(store, "m2", "Second fact")
    _add(store, "m5", "Superseded fact", superseded_by="m1")
    monkeypatch.setattr(transfer, "COPY_MAX", 2)

    report = _copy(store, source_tenant="acme", dest_tenant="beta", all_active=True)

    assert report.memories_copied == 2
    assert "m5" not in report.id_map
    assert "Superseded fact" not in _contents(store, "beta")


# ---------------------------------------------------------------------------
# R3.3 — id rows first, then filter rows, de-duplicated first occurrence wins
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-d9e27376")
def test_id_rows_come_before_filter_rows_and_dedupe_first_occurrence(
    store: SqliteBackend,
) -> None:
    _seed(store)

    report = _copy(
        store,
        source_tenant="acme",
        dest_tenant="beta",
        memory_ids=["m2"],
        filter=MemoryFilter(category=MemoryCategory.FACT),
    )

    assert list(report.id_map) == ["m2", "m1", "n1"]
    assert report.memories_copied == 2
    assert report.notes_copied == 1
    contents = _contents(store, "beta")
    assert contents.count("Alice works at Acme") == 1
    assert contents.count("Bob works at Acme") == 1


# ---------------------------------------------------------------------------
# R3.4 — one level of attached notes, dedupe, cap
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-93dcf70e")
def test_attached_note_selected_and_attached_is_copied_once(store: SqliteBackend) -> None:
    _seed(store)

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1", "n1"])

    assert report.memories_copied == 1
    assert report.notes_copied == 1
    assert report.notes_skipped_duplicate == 0
    assert list(report.id_map) == ["m1", "n1"]
    assert _contents(store, "beta").count("Alice prefers mornings") == 1


@pytest.mark.l4("C-93dcf70e", "C-02945d2c")
def test_inactive_and_superseded_attached_notes_are_ignored_and_uncounted(
    store: SqliteBackend,
) -> None:
    _seed(store)
    _add(
        store,
        "n2",
        "Inactive note about Alice",
        category=MemoryCategory.EPISODIC,
        is_note=True,
        is_active=False,
        metadata={"anchor_memory_id": "m1"},
    )
    _add(
        store,
        "n3",
        "Superseded note about Alice",
        category=MemoryCategory.EPISODIC,
        is_note=True,
        superseded_by="m1",
        metadata={"anchor_memory_id": "m1"},
    )
    _link(store, "n2", "m1", ConceptLinkType.ANNOTATES)
    _link(store, "n3", "m1", ConceptLinkType.ANNOTATES)

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1"])

    assert report.memories_copied == 1
    assert report.notes_copied == 1
    assert report.notes_skipped_duplicate == 0
    assert report.memories_skipped_duplicate == 0
    assert report.memories_skipped_not_found == 0
    contents = _contents(store, "beta")
    assert contents.count("Alice prefers mornings") == 1
    assert "Inactive note about Alice" not in contents
    assert "Superseded note about Alice" not in contents


@pytest.mark.l4("C-93dcf70e")
def test_note_expansion_pushes_the_selection_over_copy_max(
    store: SqliteBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(store)
    monkeypatch.setattr(transfer, "COPY_MAX", 1)

    with pytest.raises(CopySelectionError) as excinfo:
        _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1"])

    assert str(excinfo.value) == "selection exceeds 1 memories"


# ---------------------------------------------------------------------------
# R4.1 / R4.2 — duplicates are skipped and expand nothing
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-7c07d4ec", "C-dde5363b")
def test_existing_destination_content_skips_record_and_expands_no_note(
    store: SqliteBackend,
) -> None:
    _seed(store)
    _add(store, "b-existing", "Alice works at Acme", tenant="beta")
    before = store.get_memory("b-existing", tenant_id="beta")
    assert before is not None
    before_dump = before.model_dump()

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1"])

    assert report.memories_copied == 0
    assert report.notes_copied == 0
    assert report.memories_skipped_duplicate == 1
    assert report.notes_skipped_duplicate == 0
    assert report.links_copied == 0
    assert report.id_map == {}

    contents = _contents(store, "beta")
    assert contents.count("Alice works at Acme") == 1
    assert "Alice prefers mornings" not in contents
    after = store.get_memory("b-existing", tenant_id="beta")
    assert after is not None
    assert after.model_dump() == before_dump


@pytest.mark.l4("C-7c07d4ec")
def test_note_duplicate_is_counted_in_notes_skipped_duplicate(store: SqliteBackend) -> None:
    _seed(store)
    _add(
        store,
        "b-note",
        "Alice prefers mornings",
        tenant="beta",
        category=MemoryCategory.EPISODIC,
        is_note=True,
    )

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1"])

    assert report.memories_copied == 1
    assert report.notes_copied == 0
    assert report.memories_skipped_duplicate == 0
    assert report.notes_skipped_duplicate == 1
    assert _contents(store, "beta").count("Alice prefers mornings") == 1


@pytest.mark.l4("C-7c07d4ec", "C-02945d2c")
def test_two_source_records_with_the_same_content_copies_one_and_counts_one_duplicate(
    tmp_path: Path,
) -> None:
    store = _new_store(tmp_path, "same-content.db")
    store.create_tenant("acme")
    store.create_tenant("beta")
    _add(store, "a1", "Duplicate content")
    _add(store, "a2", "Duplicate content")

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["a1", "a2"])

    assert report.memories_copied == 1
    assert report.memories_skipped_duplicate == 1
    assert _contents(store, "beta").count("Duplicate content") == 1


@pytest.mark.l4("C-7c07d4ec", "C-93dcf70e")
def test_skipped_duplicates_do_not_count_toward_copy_max(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _new_store(tmp_path, "dup-cap.db")
    store.create_tenant("acme")
    store.create_tenant("beta")
    _add(store, "dup", "Already there")
    _add(store, "m2", "Second fact")
    _add(store, "m3", "Third fact")
    _add(store, "b-dup", "Already there", tenant="beta")
    monkeypatch.setattr(transfer, "COPY_MAX", 2)

    report = _copy(store, source_tenant="acme", dest_tenant="beta", all_active=True)

    assert report.memories_copied == 2
    assert report.memories_skipped_duplicate == 1
    assert "b-dup" not in report.id_map
    contents = _contents(store, "beta")
    assert contents.count("Second fact") == 1
    assert contents.count("Third fact") == 1


# ---------------------------------------------------------------------------
# R4.3 — force copies duplicates, destination check includes archived/inactive
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-1e794dc0", "C-7c07d4ec")
def test_force_copies_duplicates_and_destination_check_sees_archived_and_inactive(
    tmp_path: Path,
) -> None:
    store = _new_store(tmp_path, "force.db")
    store.create_tenant("acme")
    store.create_tenant("beta")
    _add(store, "m1", "Same content")
    _add(store, "m2", "Other content")
    _add(store, "b-archived", "Same content", tenant="beta", is_archived=True)
    _add(store, "b-inactive", "Other content", tenant="beta", is_active=False)

    first = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1", "m2"])
    assert first.memories_copied == 0
    assert first.memories_skipped_duplicate == 2

    forced = _copy(
        store,
        source_tenant="acme",
        dest_tenant="beta",
        memory_ids=["m1", "m2"],
        force=True,
    )
    assert forced.memories_copied == 2
    assert forced.memories_skipped_duplicate == 0

    contents = _contents(store, "beta")
    assert contents.count("Same content") == 2
    assert contents.count("Other content") == 2

    copied = store.get_memory(forced.id_map["m1"], tenant_id="beta")
    assert copied is not None
    assert copied.is_active is True
    assert copied.is_archived is False
    assert copied.metadata["copied_from_tenant"] == "acme"


@pytest.mark.l4("C-1e794dc0")
def test_force_copies_in_plan_duplicates_too(tmp_path: Path) -> None:
    store = _new_store(tmp_path, "force-in-plan.db")
    store.create_tenant("acme")
    store.create_tenant("beta")
    _add(store, "a1", "In-plan duplicate")
    _add(store, "a2", "In-plan duplicate")

    report = _copy(
        store,
        source_tenant="acme",
        dest_tenant="beta",
        memory_ids=["a1", "a2"],
        force=True,
    )

    assert report.memories_copied == 2
    assert report.memories_skipped_duplicate == 0
    assert _contents(store, "beta").count("In-plan duplicate") == 2


# ---------------------------------------------------------------------------
# R4.4 / R9.4 — a re-run without force creates no record
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-8b953633", "C-38e5f134", "C-7c07d4ec")
def test_rerunning_the_same_copy_creates_no_record(store: SqliteBackend) -> None:
    _seed(store)
    first = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1", "m2"])
    assert first.memories_copied == 2
    assert first.notes_copied == 1
    before_ids = {record.id for record in _all_memories(store, "beta")}

    second = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1", "m2"])

    assert second.memories_copied == 0
    assert second.notes_copied == 0
    assert second.memories_skipped_duplicate == 2
    assert second.notes_skipped_duplicate == 0
    assert second.id_map == {}
    after_ids = {record.id for record in _all_memories(store, "beta")}
    assert after_ids == before_ids


@pytest.mark.l4("C-38e5f134")
def test_force_recopies_m1_m2_and_n1(store: SqliteBackend) -> None:
    _seed(store)
    _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1", "m2"])

    forced = _copy(
        store,
        source_tenant="acme",
        dest_tenant="beta",
        memory_ids=["m1", "m2"],
        force=True,
    )

    assert forced.memories_copied == 2
    assert forced.notes_copied == 1
    contents = _contents(store, "beta")
    assert contents.count("Alice works at Acme") == 2
    assert contents.count("Bob works at Acme") == 2
    assert contents.count("Alice prefers mornings") == 2


# ---------------------------------------------------------------------------
# R5.1 — fresh uuid, destination tenant, now timestamps
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-1dcc08a5")
def test_every_copy_gets_a_fresh_uuid_dest_tenant_and_now_timestamps(
    store: SqliteBackend,
) -> None:
    _seed(store)
    source = store.get_memory("m1", tenant_id="acme")
    assert source is not None

    before = datetime.now(UTC).replace(tzinfo=None)
    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1"])
    after = datetime.now(UTC).replace(tzinfo=None)

    copied = store.get_memory(report.id_map["m1"], tenant_id="beta")
    assert copied is not None
    assert copied.id != source.id
    assert uuid.UUID(copied.id).version == 4
    assert copied.tenant_id == "beta"
    assert before <= copied.created_at <= after
    assert before <= copied.updated_at <= after
    assert copied.created_at == copied.updated_at
    assert copied.created_at != source.created_at


# ---------------------------------------------------------------------------
# R5.2 / R5.3 — copied fields kept, state reset
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-b9c11bfc", "C-38635874")
def test_copied_record_keeps_copied_fields(store: SqliteBackend) -> None:
    _seed(store)
    source = store.get_memory("m1", tenant_id="acme")
    assert source is not None

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1"])
    copied = store.get_memory(report.id_map["m1"], tenant_id="beta")
    assert copied is not None

    assert copied.content == source.content
    assert copied.category == source.category
    assert copied.source == source.source
    assert copied.verified == source.verified is True
    assert copied.is_note == source.is_note is False
    assert copied.confidence == source.confidence
    assert copied.valid_from == source.valid_from
    assert copied.valid_until == source.valid_until
    assert copied.entity_ids == source.entity_ids


@pytest.mark.l4("C-53994c9f", "C-38635874")
def test_copied_record_state_is_reset(store: SqliteBackend) -> None:
    _seed(store)
    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1"])
    copied = store.get_memory(report.id_map["m1"], tenant_id="beta")
    assert copied is not None

    assert copied.usefulness_score == 0.0
    assert copied.staleness_score == 0.0
    assert copied.reinforcement_count == 0
    assert copied.retrieval_count == 0
    assert copied.is_stale is False
    assert copied.is_active is True
    assert copied.is_archived is False
    assert copied.superseded_by is None
    assert copied.flagged_for_review is False
    assert copied.contradicts_ids == []
    assert copied.last_accessed_at is None


# ---------------------------------------------------------------------------
# R5.4 — metadata merge, provenance overwrite, anchor rewrite / removal
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-28775698")
def test_metadata_merge_overwrites_provenance_and_rewrites_the_anchor(
    tmp_path: Path,
) -> None:
    store = _new_store(tmp_path, "metadata.db")
    store.create_tenant("acme")
    store.create_tenant("beta")
    _add(
        store,
        "m1",
        "Alice works at Acme",
        metadata={
            "project": "x",
            "copied_from_tenant": "spoof",
            "source_memory_id": "spoof",
        },
    )
    _add(
        store,
        "n1",
        "Alice prefers mornings",
        category=MemoryCategory.EPISODIC,
        is_note=True,
        metadata={"anchor_memory_id": "m1", "keep": "n"},
    )
    _link(store, "n1", "m1", ConceptLinkType.ANNOTATES)

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1"])

    copied_memory = store.get_memory(report.id_map["m1"], tenant_id="beta")
    assert copied_memory is not None
    assert copied_memory.metadata == {
        "project": "x",
        "copied_from_tenant": "acme",
        "source_memory_id": "m1",
    }
    copied_note = store.get_memory(report.id_map["n1"], tenant_id="beta")
    assert copied_note is not None
    assert copied_note.metadata == {
        "anchor_memory_id": report.id_map["m1"],
        "keep": "n",
        "copied_from_tenant": "acme",
        "source_memory_id": "n1",
    }


@pytest.mark.l4("C-28775698")
def test_metadata_anchor_is_removed_when_anchor_memory_is_not_copied(
    tmp_path: Path,
) -> None:
    store = _new_store(tmp_path, "anchor-removal.db")
    store.create_tenant("acme")
    store.create_tenant("beta")
    _add(store, "m1", "Alice works at Acme")
    _add(
        store,
        "n2",
        "Standalone note",
        category=MemoryCategory.EPISODIC,
        is_note=True,
        metadata={"anchor_memory_id": "m1", "keep": "n"},
    )

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["n2"])

    assert report.notes_copied == 1
    copied = store.get_memory(report.id_map["n2"], tenant_id="beta")
    assert copied is not None
    assert "anchor_memory_id" not in copied.metadata
    assert copied.metadata == {
        "keep": "n",
        "copied_from_tenant": "acme",
        "source_memory_id": "n2",
    }


# ---------------------------------------------------------------------------
# R5.5 — written through add_memory (indexed by the store)
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-b418242c")
def test_copies_are_written_through_add_memory(
    store: SqliteBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(store)
    calls: list[MemoryRecord | None] = []
    original = store.add_memory

    def spy(record: MemoryRecord | None = None, **fields: Any) -> MemoryRecord:
        calls.append(record)
        return original(record=record, **fields)

    monkeypatch.setattr(store, "add_memory", spy)

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1", "m2"])

    assert len(calls) == 3
    assert all(record is not None for record in calls)
    written_ids = {record.id for record in calls if record is not None}
    assert written_ids == set(report.id_map.values())


# ---------------------------------------------------------------------------
# R7.1 — one transaction: a failure rolls the destination back
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-49684d62")
def test_exception_during_writes_rolls_back_the_destination(
    store: SqliteBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(store)
    calls: list[MemoryRecord | None] = []
    original = store.add_memory

    def flaky(record: MemoryRecord | None = None, **fields: Any) -> MemoryRecord:
        calls.append(record)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return original(record=record, **fields)

    monkeypatch.setattr(store, "add_memory", flaky)

    with pytest.raises(RuntimeError, match="boom"):
        _copy(
            store,
            source_tenant="acme",
            dest_tenant="beta",
            memory_ids=["m1", "m2"],
        )

    assert len(calls) == 2
    assert (
        store.list_memories(MemoryFilter(active_only=False, exclude_stale=False), tenant_id="beta")
        == []
    )


# ---------------------------------------------------------------------------
# R7.2 — the source tenant is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-ba8edb36")
def test_source_rows_are_identical_after_all_active_copy(store: SqliteBackend) -> None:
    _seed(store)
    before_memories = _memory_dumps(store, "acme")
    before_links = _link_dumps(store, "acme", ["m1", "m2", "m3", "n1"])
    before_summary = store.get_summary("acme", tenant_id="acme")
    assert before_summary is not None
    before_summary_dump = before_summary.model_dump()

    _copy(store, source_tenant="acme", dest_tenant="beta", all_active=True)

    assert _memory_dumps(store, "acme") == before_memories
    assert _link_dumps(store, "acme", ["m1", "m2", "m3", "n1"]) == before_links
    after_summary = store.get_summary("acme", tenant_id="acme")
    assert after_summary is not None
    assert after_summary.model_dump() == before_summary_dump


# ---------------------------------------------------------------------------
# R9.2 — records part of the seeded copy
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-38635874", "C-b418242c", "C-ba8edb36")
def test_seeded_copy_reports_places_provenance_and_search_finds_it(
    store: SqliteBackend,
) -> None:
    _seed(store)
    before_memories = _memory_dumps(store, "acme")
    before_links = _link_dumps(store, "acme", ["m1", "m2", "m3", "n1"])

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1", "m2"])

    assert report.memories_copied == 2
    assert report.notes_copied == 1
    assert report.memories_skipped_duplicate == 0
    assert report.memories_skipped_not_found == 0
    assert list(report.id_map) == ["m1", "m2", "n1"]
    assert len(_all_memories(store, "beta")) == 3

    copied_m1 = store.get_memory(report.id_map["m1"], tenant_id="beta")
    assert copied_m1 is not None
    assert copied_m1.content == "Alice works at Acme"
    assert copied_m1.category == MemoryCategory.FACT
    assert copied_m1.source == MemorySource.USER
    assert copied_m1.verified is True
    assert copied_m1.confidence == 0.8
    assert copied_m1.valid_from == datetime(2026, 1, 1)
    assert copied_m1.valid_until == datetime(2027, 1, 1)
    assert copied_m1.entity_ids == ["Alice", "Acme"]
    assert copied_m1.usefulness_score == 0.0
    assert copied_m1.staleness_score == 0.0
    assert copied_m1.reinforcement_count == 0
    assert copied_m1.retrieval_count == 0
    assert copied_m1.contradicts_ids == []
    assert copied_m1.flagged_for_review is False
    assert copied_m1.last_accessed_at is None
    assert copied_m1.is_stale is False
    assert copied_m1.is_active is True
    assert copied_m1.is_archived is False
    assert copied_m1.superseded_by is None
    assert copied_m1.metadata["project"] == "x"
    assert copied_m1.metadata["copied_from_tenant"] == "acme"
    assert copied_m1.metadata["source_memory_id"] == "m1"

    copied_n1 = store.get_memory(report.id_map["n1"], tenant_id="beta")
    assert copied_n1 is not None
    assert copied_n1.is_note is True
    assert copied_n1.metadata["anchor_memory_id"] == report.id_map["m1"]

    assert store.get_summary("acme", tenant_id="beta") is None
    assert _memory_dumps(store, "acme") == before_memories
    assert _link_dumps(store, "acme", ["m1", "m2", "m3", "n1"]) == before_links

    response = store.search(SearchRequest(query="Alice"), tenant_id="beta")
    assert any(memory.content == "Alice works at Acme" for memory in response.memories)


# ---------------------------------------------------------------------------
# R9.5 — missing / archived / other-tenant ids write nothing
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-02945d2c", "C-0380775d")
def test_unknown_archived_and_global_ids_count_as_not_found(store: SqliteBackend) -> None:
    _seed(store)

    report = _copy(
        store,
        source_tenant="acme",
        dest_tenant="beta",
        memory_ids=["m3", "nope", "g1"],
    )

    assert report.memories_skipped_not_found == 3
    assert report.memories_copied == 0
    assert report.notes_copied == 0
    assert report.id_map == {}
    assert (
        store.list_memories(MemoryFilter(active_only=False, exclude_stale=False), tenant_id="beta")
        == []
    )


# ---------------------------------------------------------------------------
# R9.6 — all_active copies m1, m2 and n1 each once
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-c38088c4")
def test_all_active_copies_m1_m2_and_n1_each_once(store: SqliteBackend) -> None:
    _seed(store)

    report = _copy(store, source_tenant="acme", dest_tenant="beta", all_active=True)

    assert report.memories_copied == 2
    assert report.notes_copied == 1
    assert report.memories_skipped_duplicate == 0
    assert list(report.id_map) == ["m1", "m2", "n1"]
    contents = _contents(store, "beta")
    assert contents.count("Alice works at Acme") == 1
    assert contents.count("Bob works at Acme") == 1
    assert contents.count("Alice prefers mornings") == 1


# ---------------------------------------------------------------------------
# R9.9 — the selection cap
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-7b613be5")
def test_all_active_over_the_patched_cap_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _new_store(tmp_path, "patched-cap.db")
    store.create_tenant("acme")
    store.create_tenant("beta")
    _add(store, "m1", "First memory")
    _add(store, "m2", "Second memory")
    _add(store, "m3", "Third memory")
    monkeypatch.setattr(transfer, "COPY_MAX", 2)

    with pytest.raises(CopySelectionError) as excinfo:
        _copy(store, source_tenant="acme", dest_tenant="beta", all_active=True)

    assert str(excinfo.value) == "selection exceeds 2 memories"
    assert (
        store.list_memories(MemoryFilter(active_only=False, exclude_stale=False), tenant_id="beta")
        == []
    )
