"""RED tests for task 1 — tenant-scoped record and entity reads.

They trace requirement 1.1 (every record/entity read gains a trailing
``tenant_id: str | None = None`` on ``SqliteBackend`` and the ``StorageBackend``
Protocol, with ``None``/concrete/unknown-tenant semantics), 1.2
(``get_memory`` returns ``None`` for a foreign row), 1.3 (``get_stats`` counts
one tenant only, ``None`` counts all and an unknown tenant is zeroed) and 1.4
(``list_summaries`` keeps ``ORDER BY concept`` and carries the tenant id).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from mintmory.core.ports import StorageBackend
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    MemoryCategory,
    MemoryRecord,
    MemorySummary,
    QuerySession,
)


@dataclass
class Seed:
    store: SqliteBackend
    g1: MemoryRecord
    g2: MemoryRecord
    g_note: MemoryRecord
    g_desc: MemoryRecord
    g_img: MemoryRecord
    g_stale: MemoryRecord
    g_flagged: MemoryRecord
    g_session: QuerySession
    a1: MemoryRecord
    a2: MemoryRecord
    a_note: MemoryRecord
    a_desc: MemoryRecord
    a_img: MemoryRecord
    a_stale: MemoryRecord
    a_flagged: MemoryRecord
    a_session: QuerySession


def _memory(
    store: SqliteBackend,
    content: str,
    tenant_id: str,
    *,
    metadata: dict[str, Any] | None = None,
    is_note: bool = False,
    is_stale: bool = False,
    flagged_for_review: bool = False,
    created_at: datetime | None = None,
) -> MemoryRecord:
    record = MemoryRecord(
        content=content,
        category=MemoryCategory.FACT,
        entity_ids=["Alice"],
        tenant_id=tenant_id,
        metadata=metadata or {},
        is_note=is_note,
        is_stale=is_stale,
        flagged_for_review=flagged_for_review,
    )
    if created_at is not None:
        record.created_at = created_at
    return store.add_memory(record)


def _link(
    store: SqliteBackend,
    source: str,
    target: str,
    link_type: ConceptLinkType,
    tenant_id: str,
) -> None:
    store.add_link(
        ConceptLink(
            source_memory_id=source,
            target_memory_id=target,
            link_type=link_type,
            tenant_id=tenant_id,
        )
    )


@pytest.fixture
def seed(tmp_path: Path) -> Seed:
    store = SqliteBackend(tmp_path / "mintmory.db")
    store.initialise()
    store.create_tenant("t1")

    g1 = _memory(store, "Alice uses Postgres", "global")
    g2 = _memory(store, "Alice uses MySQL", "global")
    _memory(store, "Alice uses Oracle", "global")
    g_note = _memory(
        store,
        "global note about g1",
        "global",
        is_note=True,
        metadata={"anchor": "g1"},
    )
    g_desc = _memory(
        store,
        "global description of g1",
        "global",
        metadata={"kind": "image_description"},
    )
    g_img = _memory(
        store,
        "global image",
        "global",
        metadata={"ext": ".png", "path": "/g.png", "rel": "g.png"},
    )
    g_stale = _memory(store, "global stale", "global", is_stale=True)
    g_flagged = _memory(store, "global flagged", "global", flagged_for_review=True)

    a1 = _memory(store, "Alice uses SQLite", "t1")
    a2 = _memory(store, "Alice uses Redis", "t1")
    a_note = _memory(
        store,
        "t1 note about a1",
        "t1",
        is_note=True,
        metadata={"anchor": "a1"},
    )
    a_desc = _memory(
        store,
        "t1 description of a1",
        "t1",
        metadata={"kind": "image_description"},
    )
    a_img = _memory(
        store,
        "t1 image",
        "t1",
        metadata={"ext": ".png", "path": "/t1.png", "rel": "t1.png"},
    )
    a_stale = _memory(store, "t1 stale", "t1", is_stale=True)
    a_flagged = _memory(store, "t1 flagged", "t1", flagged_for_review=True)

    _link(store, g1.id, g2.id, ConceptLinkType.RELATES_TO, "global")
    _link(store, g_note.id, g1.id, ConceptLinkType.ANNOTATES, "global")
    _link(store, g_desc.id, g1.id, ConceptLinkType.ANNOTATES, "global")
    _link(store, a1.id, a2.id, ConceptLinkType.RELATES_TO, "t1")
    _link(store, a_note.id, a1.id, ConceptLinkType.ANNOTATES, "t1")
    _link(store, a_desc.id, a1.id, ConceptLinkType.ANNOTATES, "t1")

    g_session = store.create_session(QuerySession(query_text="global query", tenant_id="global"))
    a_session = store.create_session(QuerySession(query_text="t1 query", tenant_id="t1"))

    store.upsert_summary(
        MemorySummary(
            concept="Gamma",
            summary_text="global summary",
            memory_count=3,
            tenant_id="global",
        )
    )
    store.upsert_summary(
        MemorySummary(
            concept="Alpha",
            summary_text="t1 summary",
            memory_count=1,
            tenant_id="t1",
        )
    )
    store.upsert_summary(
        MemorySummary(
            concept="Beta",
            summary_text="t1 summary",
            memory_count=1,
            tenant_id="t1",
        )
    )

    return Seed(
        store=store,
        g1=g1,
        g2=g2,
        g_note=g_note,
        g_desc=g_desc,
        g_img=g_img,
        g_stale=g_stale,
        g_flagged=g_flagged,
        g_session=g_session,
        a1=a1,
        a2=a2,
        a_note=a_note,
        a_desc=a_desc,
        a_img=a_img,
        a_stale=a_stale,
        a_flagged=a_flagged,
        a_session=a_session,
    )


# ---------------------------------------------------------------------------
# Requirement 1.1 — signatures on SQLite and the Protocol
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-91dbbaaa")
def test_read_signatures_declare_trailing_tenant_id() -> None:
    expected = {
        "get_memory": ["self", "memory_id", "tenant_id"],
        "get_links": ["self", "memory_id", "link_type", "tenant_id"],
        "get_annotating_notes": ["self", "memory_id", "cap", "tenant_id"],
        "get_annotating_descriptions": ["self", "memory_id", "cap", "tenant_id"],
        "find_image_file_record": ["self", "path_or_rel", "tenant_id"],
        "list_image_file_records": ["self", "tenant_id"],
        "list_notes": [
            "self",
            "entity",
            "anchor_substr",
            "upcoming",
            "overdue",
            "include_archived",
            "limit",
            "now",
            "tenant_id",
        ],
        "list_summaries": ["self", "tenant_id"],
        "get_session": ["self", "session_id", "tenant_id"],
        "get_stats": ["self", "tenant_id"],
        "memory_exists_with_content": ["self", "content", "tenant_id"],
    }
    for cls in (SqliteBackend, StorageBackend):
        for name, parameters in expected.items():
            signature = inspect.signature(getattr(cls, name))
            assert list(signature.parameters) == parameters, f"{cls.__name__}.{name}"
            assert signature.parameters["tenant_id"].default is None

    notes = inspect.signature(SqliteBackend.list_notes).parameters
    assert notes["tenant_id"].kind is inspect.Parameter.KEYWORD_ONLY


# ---------------------------------------------------------------------------
# Requirement 1.2 — get_memory
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-91dbbaaa", "C-a614e704")
def test_get_memory_is_tenant_scoped(seed: Seed) -> None:
    store = seed.store

    foreign = store.get_memory(seed.g1.id, tenant_id="t1")
    assert foreign is None

    scoped = store.get_memory(seed.a1.id, tenant_id="t1")
    assert scoped is not None
    assert scoped.content == "Alice uses SQLite"

    global_row = store.get_memory(seed.g1.id, tenant_id="global")
    assert global_row is not None
    assert global_row.content == "Alice uses Postgres"

    unscoped = store.get_memory(seed.g1.id, tenant_id=None)
    assert unscoped is not None
    assert unscoped.id == seed.g1.id

    assert store.get_memory(seed.g1.id, tenant_id="nope") is None
    assert store.get_memory(seed.a1.id, tenant_id="nope") is None


# ---------------------------------------------------------------------------
# Requirement 1.1 — the other record/entity reads
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-91dbbaaa")
def test_get_links_is_tenant_scoped(seed: Seed) -> None:
    store = seed.store

    scoped = store.get_links(seed.a1.id, tenant_id="t1")
    assert len(scoped) == 3
    assert all(link.tenant_id == "t1" for link in scoped)
    assert store.get_links(seed.g1.id, tenant_id="t1") == []

    global_links = store.get_links(seed.g1.id, tenant_id="global")
    assert len(global_links) == 3
    assert all(link.tenant_id == "global" for link in global_links)

    unscoped = store.get_links(seed.a1.id, tenant_id=None)
    assert {link.id for link in unscoped} == {link.id for link in scoped}

    assert store.get_links(seed.a1.id, tenant_id="nope") == []


@pytest.mark.l4("C-91dbbaaa")
def test_get_annotating_notes_is_tenant_scoped(seed: Seed) -> None:
    store = seed.store

    scoped = store.get_annotating_notes(seed.a1.id, 5, tenant_id="t1")
    assert [note.id for note in scoped] == [seed.a_note.id]

    unscoped = store.get_annotating_notes(seed.a1.id, 5, tenant_id=None)
    assert [note.id for note in unscoped] == [seed.a_note.id]

    assert store.get_annotating_notes(seed.a1.id, 5, tenant_id="global") == []
    assert store.get_annotating_notes(seed.a1.id, 5, tenant_id="nope") == []

    global_notes = store.get_annotating_notes(seed.g1.id, 5, tenant_id="global")
    assert [note.id for note in global_notes] == [seed.g_note.id]


@pytest.mark.l4("C-91dbbaaa")
def test_get_annotating_descriptions_is_tenant_scoped(seed: Seed) -> None:
    store = seed.store

    scoped = store.get_annotating_descriptions(seed.a1.id, 5, tenant_id="t1")
    assert [desc.id for desc in scoped] == [seed.a_desc.id]

    unscoped = store.get_annotating_descriptions(seed.a1.id, 5, tenant_id=None)
    assert [desc.id for desc in unscoped] == [seed.a_desc.id]

    assert store.get_annotating_descriptions(seed.a1.id, 5, tenant_id="global") == []
    assert store.get_annotating_descriptions(seed.a1.id, 5, tenant_id="nope") == []

    global_descs = store.get_annotating_descriptions(seed.g1.id, 5, tenant_id="global")
    assert [desc.id for desc in global_descs] == [seed.g_desc.id]


@pytest.mark.l4("C-91dbbaaa")
def test_find_image_file_record_is_tenant_scoped(seed: Seed) -> None:
    store = seed.store

    scoped = store.find_image_file_record("/t1.png", tenant_id="t1")
    assert scoped is not None
    assert scoped.id == seed.a_img.id

    unscoped = store.find_image_file_record("/t1.png", tenant_id=None)
    assert unscoped is not None
    assert unscoped.id == seed.a_img.id

    assert store.find_image_file_record("/t1.png", tenant_id="global") is None
    assert store.find_image_file_record("/t1.png", tenant_id="nope") is None


@pytest.mark.l4("C-91dbbaaa")
def test_list_image_file_records_is_tenant_scoped(seed: Seed) -> None:
    store = seed.store

    scoped = store.list_image_file_records(tenant_id="t1")
    assert {record.id for record in scoped} == {seed.a_img.id}

    unscoped = store.list_image_file_records(tenant_id=None)
    assert {record.id for record in unscoped} == {seed.g_img.id, seed.a_img.id}

    assert store.list_image_file_records(tenant_id="nope") == []


@pytest.mark.l4("C-91dbbaaa")
def test_list_notes_is_tenant_scoped(seed: Seed) -> None:
    store = seed.store

    scoped = store.list_notes(tenant_id="t1")
    assert {note.id for note in scoped} == {seed.a_note.id}

    unscoped = store.list_notes(tenant_id=None)
    assert {note.id for note in unscoped} == {seed.g_note.id, seed.a_note.id}

    assert store.list_notes(tenant_id="nope") == []


@pytest.mark.l4("C-91dbbaaa")
def test_get_session_is_tenant_scoped(seed: Seed) -> None:
    store = seed.store

    scoped = store.get_session(seed.a_session.id, tenant_id="t1")
    assert scoped is not None
    assert scoped.query_text == "t1 query"

    unscoped = store.get_session(seed.a_session.id, tenant_id=None)
    assert unscoped is not None
    assert unscoped.tenant_id == "t1"

    assert store.get_session(seed.a_session.id, tenant_id="global") is None
    assert store.get_session(seed.g_session.id, tenant_id="t1") is None
    assert store.get_session(seed.a_session.id, tenant_id="nope") is None


@pytest.mark.l4("C-91dbbaaa")
def test_memory_exists_with_content_is_tenant_scoped(seed: Seed) -> None:
    store = seed.store

    assert store.memory_exists_with_content(seed.a1.content, tenant_id="t1") is True
    assert store.memory_exists_with_content(seed.a1.content, tenant_id="global") is False
    assert store.memory_exists_with_content(seed.a1.content, tenant_id=None) is True
    assert store.memory_exists_with_content(seed.a1.content, tenant_id="nope") is False
    assert store.memory_exists_with_content(seed.g1.content, tenant_id="global") is True


# ---------------------------------------------------------------------------
# Requirement 1.3 — get_stats
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-91dbbaaa", "C-2f90553d")
def test_get_stats_is_tenant_scoped(seed: Seed) -> None:
    store = seed.store

    scoped = store.get_stats(tenant_id="t1")
    assert scoped is not None
    assert scoped.total_memories == 7
    assert scoped.active == 7
    assert scoped.stale == 1
    assert scoped.archived == 0
    assert scoped.concept_links == 3
    assert scoped.memory_summaries == 2
    assert scoped.avg_usefulness_score == 0.0
    assert scoped.avg_staleness_score == 0.0
    assert scoped.top_concepts == [("Alice", 7)]

    unscoped = store.get_stats(tenant_id=None)
    assert unscoped.total_memories == 15
    assert unscoped.active == 15
    assert unscoped.stale == 2
    assert unscoped.archived == 0
    assert unscoped.concept_links == 6
    assert unscoped.memory_summaries == 3
    assert unscoped.top_concepts == [("Alice", 15)]

    default_call = store.get_stats()
    assert default_call.total_memories == 15

    missing = store.get_stats(tenant_id="nope")
    assert missing.total_memories == 0
    assert missing.active == 0
    assert missing.stale == 0
    assert missing.archived == 0
    assert missing.concept_links == 0
    assert missing.memory_summaries == 0
    assert missing.avg_usefulness_score == 0.0
    assert missing.avg_staleness_score == 0.0
    assert missing.top_concepts == []


# ---------------------------------------------------------------------------
# Requirement 1.4 — list_summaries
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-91dbbaaa", "C-826339bd")
def test_list_summaries_is_tenant_scoped(seed: Seed) -> None:
    store = seed.store

    scoped = store.list_summaries(tenant_id="t1")
    assert [summary.concept for summary in scoped] == ["Alpha", "Beta"]
    assert all(summary.tenant_id == "t1" for summary in scoped)

    unscoped = store.list_summaries(tenant_id=None)
    assert [summary.concept for summary in unscoped] == ["Alpha", "Beta", "Gamma"]
    assert {summary.tenant_id for summary in unscoped} == {"global", "t1"}

    global_only = store.list_summaries(tenant_id="global")
    assert [summary.concept for summary in global_only] == ["Gamma"]

    assert store.list_summaries(tenant_id="nope") == []
