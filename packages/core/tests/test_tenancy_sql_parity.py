"""SQL parity for the tenant-scoped reads (requirement 2.2).

Every read of requirement 1.1 except ``search`` is called twice with a trace
callback registered on ``store.connect()``: once with ``tenant_id=None`` and
once with ``"t1"``.  The unscoped call may not execute any ``tenant_id =``
predicate (today's SQL is reproduced exactly); the scoped call must carry it in
every ``SELECT`` that reads ``memories``, ``concept_links``,
``memory_summaries`` or ``query_sessions``.  The same tests assert real answers
from every read, and the signatures of the candidate-phase helpers, so they are
not satisfied by a zero-value implementation.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    MemoryCategory,
    MemoryRecord,
    MemoryStats,
    MemorySummary,
    QuerySession,
    SearchAroundSpec,
)

Reader = Callable[[str | None], object]

_SCOPED_TABLES = ("memories", "concept_links", "memory_summaries", "query_sessions")

_SIGNATURES: dict[str, list[str]] = {
    "get_memory": ["self", "memory_id", "tenant_id"],
    "search_around": ["self", "anchor_ids", "spec", "tenant_id"],
    "get_links": ["self", "memory_id", "link_type", "tenant_id"],
    "get_annotating_notes": ["self", "memory_id", "cap", "tenant_id"],
    "get_annotating_descriptions": ["self", "memory_id", "cap", "tenant_id"],
    "find_image_file_record": ["self", "path_or_rel", "tenant_id"],
    "anchor_candidates": ["self", "about", "limit", "tenant_id"],
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
    "get_flagged_memories": ["self", "tenant_id"],
    "get_never_accessed_stale": ["self", "days_old", "min_staleness", "tenant_id"],
    "get_high_staleness_useful": ["self", "min_staleness", "min_usefulness", "tenant_id"],
    "get_anomaly_high_staleness_useful_ids": [
        "self",
        "min_staleness",
        "min_usefulness",
        "tenant_id",
    ],
    "get_anomaly_never_accessed_ids": ["self", "cutoff_iso", "tenant_id"],
    "get_anomaly_flagged_ids": ["self", "tenant_id"],
    "list_active_memory_ids": ["self", "ordered", "tenant_id"],
    "get_stale_archivable_ids": ["self", "min_staleness", "cutoff_iso", "tenant_id"],
    "get_rehabilitable_rows": ["self", "cutoff_iso", "tenant_id"],
    "get_existing_relates_to_pairs": ["self", "tenant_id"],
    "_fts_scores": ["self", "query", "limit", "tenant_id"],
    "_trigram_scores": ["self", "query", "limit", "tenant_id"],
    "_vector_scores": ["self", "query", "query_embedding", "limit", "tenant_id"],
    "_load_memories": ["self", "ids", "tenant_id"],
}


@dataclass
class ParitySeed:
    store: SqliteBackend
    a1: MemoryRecord
    a2: MemoryRecord
    a_note: MemoryRecord
    a_desc: MemoryRecord
    a_img: MemoryRecord
    a_flagged: MemoryRecord
    a_never_stale: MemoryRecord
    a_high: MemoryRecord
    a_archivable: MemoryRecord
    a_rehab: MemoryRecord
    a_never_id: MemoryRecord
    a_session: QuerySession


def _memory(
    store: SqliteBackend,
    memory_id: str,
    content: str,
    tenant_id: str,
    **fields: Any,
) -> MemoryRecord:
    record = MemoryRecord(
        id=memory_id,
        content=content,
        category=MemoryCategory.FACT,
        entity_ids=["Alice"],
        tenant_id=tenant_id,
        **fields,
    )
    store.add_memory(record)
    return record


def _link(
    store: SqliteBackend,
    link_id: str,
    source: str,
    target: str,
    link_type: ConceptLinkType,
    tenant_id: str,
) -> None:
    store.add_link(
        ConceptLink(
            id=link_id,
            source_memory_id=source,
            target_memory_id=target,
            link_type=link_type,
            tenant_id=tenant_id,
        )
    )


@pytest.fixture
def parity(tmp_path: Path) -> ParitySeed:
    store = SqliteBackend(tmp_path / "mintmory.db")
    store.initialise()
    store.create_tenant("t1")

    old = datetime(1999, 1, 1)
    recent = datetime(2026, 1, 1)

    a1 = _memory(store, "a1", "Alice uses SQLite", "t1", created_at=datetime(2026, 1, 1))
    a2 = _memory(store, "a2", "Bob uses Redis", "t1", created_at=datetime(2026, 1, 2))
    a_note = _memory(
        store,
        "a-note",
        "Alice note",
        "t1",
        is_note=True,
        metadata={"anchor": "a1"},
    )
    a_desc = _memory(
        store,
        "a-desc",
        "Alice description",
        "t1",
        metadata={"kind": "image_description"},
    )
    a_img = _memory(
        store,
        "a-img",
        "Alice image",
        "t1",
        metadata={"ext": ".png", "path": "/t1.png", "rel": "t1.png"},
    )
    a_flagged = _memory(store, "a-flagged", "Alice flagged", "t1", flagged_for_review=True)
    a_never_stale = _memory(
        store,
        "a-never-stale",
        "Alice never accessed stale",
        "t1",
        staleness_score=4.0,
    )
    a_high = _memory(
        store,
        "a-high",
        "Alice high staleness useful",
        "t1",
        staleness_score=6.0,
        usefulness_score=4.0,
        last_accessed_at=recent,
    )
    a_archivable = _memory(
        store,
        "a-archivable",
        "Alice stale archivable",
        "t1",
        is_stale=True,
        staleness_score=9.0,
        usefulness_score=1.0,
        last_accessed_at=old,
    )
    a_rehab = _memory(
        store,
        "a-rehab",
        "Alice rehabilitable",
        "t1",
        is_stale=True,
        staleness_score=1.0,
        usefulness_score=9.0,
        last_accessed_at=recent,
    )
    a_never_id = _memory(
        store,
        "a-never-id",
        "Alice never retrieved",
        "t1",
        created_at=old,
    )

    _link(store, "link-relates", a1.id, a2.id, ConceptLinkType.RELATES_TO, "t1")
    _link(store, "link-note", a_note.id, a1.id, ConceptLinkType.ANNOTATES, "t1")
    _link(store, "link-desc", a_desc.id, a1.id, ConceptLinkType.ANNOTATES, "t1")

    a_session = QuerySession(id="a-session", query_text="t1 parity", tenant_id="t1")
    store.create_session(a_session)

    store.upsert_summary(
        MemorySummary(
            id="a-summary",
            concept="Alpha",
            summary_text="t1 summary",
            memory_count=5,
            tenant_id="t1",
        )
    )

    return ParitySeed(
        store=store,
        a1=a1,
        a2=a2,
        a_note=a_note,
        a_desc=a_desc,
        a_img=a_img,
        a_flagged=a_flagged,
        a_never_stale=a_never_stale,
        a_high=a_high,
        a_archivable=a_archivable,
        a_rehab=a_rehab,
        a_never_id=a_never_id,
        a_session=a_session,
    )


def _assert_tenant_parameters() -> None:
    for name, parameters in _SIGNATURES.items():
        signature = inspect.signature(getattr(SqliteBackend, name))
        assert list(signature.parameters) == parameters, f"SqliteBackend.{name}"
        assert signature.parameters["tenant_id"].default is None, f"SqliteBackend.{name}"


def _readers(seed: ParitySeed) -> dict[str, Reader]:
    store = seed.store
    return {
        "get_memory": lambda tenant: store.get_memory(seed.a1.id, tenant),
        "search_around": lambda tenant: store.search_around(
            [seed.a1.id], SearchAroundSpec(), tenant
        ),
        "get_links": lambda tenant: store.get_links(seed.a1.id, None, tenant),
        "get_annotating_notes": lambda tenant: store.get_annotating_notes(seed.a1.id, 5, tenant),
        "get_annotating_descriptions": lambda tenant: store.get_annotating_descriptions(
            seed.a1.id, 5, tenant
        ),
        "find_image_file_record": lambda tenant: store.find_image_file_record("/t1.png", tenant),
        "anchor_candidates": lambda tenant: store.anchor_candidates("Alice", 5, tenant),
        "list_image_file_records": lambda tenant: store.list_image_file_records(tenant),
        "list_notes": lambda tenant: store.list_notes(tenant_id=tenant),
        "list_summaries": lambda tenant: store.list_summaries(tenant),
        "get_session": lambda tenant: store.get_session(seed.a_session.id, tenant),
        "get_stats": lambda tenant: store.get_stats(tenant),
        "memory_exists_with_content": lambda tenant: store.memory_exists_with_content(
            "Alice uses SQLite", tenant
        ),
        "get_flagged_memories": lambda tenant: store.get_flagged_memories(tenant),
        "get_never_accessed_stale": lambda tenant: store.get_never_accessed_stale(7, 3.0, tenant),
        "get_high_staleness_useful": lambda tenant: store.get_high_staleness_useful(
            5.0, 3.0, tenant
        ),
        "get_anomaly_high_staleness_useful_ids": (
            lambda tenant: store.get_anomaly_high_staleness_useful_ids(5.0, 3.0, tenant)
        ),
        "get_anomaly_never_accessed_ids": (
            lambda tenant: store.get_anomaly_never_accessed_ids("2000-01-01T00:00:00", tenant)
        ),
        "get_anomaly_flagged_ids": lambda tenant: store.get_anomaly_flagged_ids(tenant),
        "list_active_memory_ids": lambda tenant: store.list_active_memory_ids(
            ordered=True, tenant_id=tenant
        ),
        "get_stale_archivable_ids": lambda tenant: store.get_stale_archivable_ids(
            5.0, "2100-01-01T00:00:00", tenant
        ),
        "get_rehabilitable_rows": lambda tenant: store.get_rehabilitable_rows(
            "2025-01-01T00:00:00", tenant
        ),
        "get_existing_relates_to_pairs": (
            lambda tenant: store.get_existing_relates_to_pairs(tenant)
        ),
    }


def _assert_real(name: str, result: object) -> None:
    if isinstance(result, bool):
        assert result is True, f"{name} returned False"
    elif isinstance(result, (list, set)):
        assert len(result) > 0, f"{name} returned an empty collection"
    elif isinstance(result, MemoryStats):
        assert result.total_memories > 0, f"{name} counted no memories"
    else:
        assert result is not None, f"{name} returned None"


def _is_scoped_select(sql: str) -> bool:
    stripped = sql.lstrip()
    if not stripped.upper().startswith("SELECT"):
        return False
    return any(table in sql for table in _SCOPED_TABLES)


@pytest.mark.l4("C-dea5cddd")
def test_unscoped_reads_emit_todays_sql_without_tenant_predicate(parity: ParitySeed) -> None:
    _assert_tenant_parameters()
    store = parity.store

    probe = store.get_memory(parity.a1.id)
    assert probe is not None
    assert probe.content == "Alice uses SQLite"

    conn = store.connect()
    assert conn is not None

    for name, reader in _readers(parity).items():
        statements: list[str] = []
        conn.set_trace_callback(statements.append)
        try:
            result = reader(None)
        finally:
            conn.set_trace_callback(None)
        _assert_real(name, result)
        offenders = [sql for sql in statements if "tenant_id =" in sql]
        assert offenders == [], f"{name} traced a tenant predicate: {offenders}"


@pytest.mark.l4("C-51a6a3d3", "C-dea5cddd")
def test_scoped_reads_put_tenant_predicate_in_every_select(parity: ParitySeed) -> None:
    _assert_tenant_parameters()
    store = parity.store

    probe = store.get_memory(parity.a1.id, "t1")
    assert probe is not None
    assert probe.content == "Alice uses SQLite"

    conn = store.connect()
    assert conn is not None

    for name, reader in _readers(parity).items():
        statements: list[str] = []
        conn.set_trace_callback(statements.append)
        try:
            result = reader("t1")
        finally:
            conn.set_trace_callback(None)
        _assert_real(name, result)
        relevant = [sql for sql in statements if _is_scoped_select(sql)]
        assert relevant, f"{name} traced no SELECT over a scoped table: {statements}"
        missing = [sql for sql in relevant if "tenant_id =" not in sql]
        assert missing == [], f"{name} traced an unscoped SELECT: {missing}"
