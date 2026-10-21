"""RED tests for task 3 — link copying and atomicity (``transfer.py``).

They trace requirement 6.1 (every link whose two endpoints are both copied is
recreated once, by source link id, in the destination tenant; a link with an
endpoint outside the copy is not created; the attached note's ``ANNOTATES``
link is included), requirement 7.3 (a destination deactivated during the copy
makes the next ``add_memory`` raise ``TenantInactiveError`` and rolls the copy
back; concurrent copies in one process are serialised), requirement 7.4 (the
Postgres interim fails closed before any write, entering ``transaction()``
before validation), and the link parts of R9.2, R9.3 and R9.8.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from mintmory.core import transfer
from mintmory.core.storage import SqliteBackend
from mintmory.core.storage_postgres import PostgresBackend
from mintmory.core.transfer import CopyReport
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    LinkSource,
    MemoryCategory,
    MemoryFilter,
    MemoryRecord,
    MemorySource,
    MemorySummary,
    TenantInactiveError,
    TenantNotFoundError,
)

from packages.core.tests.pg_fakes import FakeConnection, FakePool


@pytest.fixture
def store(tmp_path: Path) -> SqliteBackend:
    backend = SqliteBackend(tmp_path / "copy.db")
    backend.initialise()
    return backend


def _copy(store: SqliteBackend, **kwargs: Any) -> CopyReport:
    return transfer.copy_between_tenants(store, **kwargs)


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


def _seed(store: SqliteBackend) -> None:
    """R9.1 seed: acme with m1/m2/n1/m3, links, a summary, and global g1."""
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
    )
    _add(store, "m2", "Bob works at Acme", entity_ids=["Bob", "Acme"])
    _add(store, "m3", "Archived Alice fact", is_archived=True)
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


def _all_links(store: SqliteBackend, tenant: str, memory_ids: list[str]) -> list[ConceptLink]:
    seen: set[str] = set()
    links: list[ConceptLink] = []
    for memory_id in memory_ids:
        for link in store.get_links(memory_id, tenant_id=tenant):
            if link.id in seen:
                continue
            seen.add(link.id)
            links.append(link)
    return links


# ---------------------------------------------------------------------------
# R6.1 / R9.2 — links between copied records are recreated with rewritten ids
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-65fb9501", "C-38635874")
def test_copied_links_are_recreated_once_with_rewritten_endpoints(
    store: SqliteBackend,
) -> None:
    _seed(store)

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1", "m2"])

    assert report.memories_copied == 2
    assert report.notes_copied == 1
    assert report.links_copied == 2, "relates_to + annotates are each created once"
    assert set(report.id_map) == {"m1", "m2", "n1"}

    new_ids = list(report.id_map.values())
    links = _all_links(store, "beta", new_ids)
    assert len(links) == report.links_copied == 2

    by_type = {link.link_type: link for link in links}
    assert set(by_type) == {ConceptLinkType.RELATES_TO, ConceptLinkType.ANNOTATES}

    relates = by_type[ConceptLinkType.RELATES_TO]
    assert relates.source_memory_id == report.id_map["m1"]
    assert relates.target_memory_id == report.id_map["m2"]
    assert relates.entity == "Acme"
    assert relates.strength == pytest.approx(0.7)
    assert relates.confidence == pytest.approx(0.9)
    assert relates.source is LinkSource.USER
    assert relates.verified is True
    assert relates.tenant_id == "beta"

    annotates = by_type[ConceptLinkType.ANNOTATES]
    assert annotates.source_memory_id == report.id_map["n1"]
    assert annotates.target_memory_id == report.id_map["m1"]
    assert annotates.tenant_id == "beta"

    assert store.get_summary("acme", tenant_id="beta") is None


# ---------------------------------------------------------------------------
# R6.1 / R9.3 — a link with one endpoint outside the copy is not created
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-65fb9501", "C-ebb2acbb")
def test_link_with_endpoint_outside_the_copy_is_not_created(store: SqliteBackend) -> None:
    _seed(store)

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1"])

    assert report.memories_copied == 1
    assert report.notes_copied == 1
    assert report.links_copied == 1
    assert set(report.id_map) == {"m1", "n1"}

    links = _all_links(store, "beta", list(report.id_map.values()))
    assert len(links) == 1
    only = links[0]
    assert only.link_type is ConceptLinkType.ANNOTATES
    assert only.source_memory_id == report.id_map["n1"]
    assert only.target_memory_id == report.id_map["m1"]
    assert all(link.link_type is not ConceptLinkType.RELATES_TO for link in links), (
        "m2 is outside the copy"
    )


# ---------------------------------------------------------------------------
# R6.1 — a link to a skipped duplicate is not created
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-65fb9501")
def test_link_to_a_skipped_duplicate_is_not_created(store: SqliteBackend) -> None:
    _seed(store)
    _add(store, "b-existing", "Bob works at Acme", tenant="beta")

    report = _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1", "m2"])

    assert report.memories_copied == 1
    assert report.notes_copied == 1
    assert report.memories_skipped_duplicate == 1
    assert "m2" not in report.id_map
    assert report.links_copied == 1

    links = _all_links(store, "beta", list(report.id_map.values()))
    assert [link.link_type for link in links] == [ConceptLinkType.ANNOTATES]
    endpoints = {
        endpoint for link in links for endpoint in (link.source_memory_id, link.target_memory_id)
    }
    assert "b-existing" not in endpoints
    assert endpoints <= set(report.id_map.values())


# ---------------------------------------------------------------------------
# R7.1 / R9.8 — a failing link write rolls back every destination write
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-ad2c5b13", "C-49684d62")
def test_failing_add_link_rolls_everything_back(
    store: SqliteBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(store)

    def boom(link: ConceptLink) -> ConceptLink:
        raise RuntimeError("boom")

    monkeypatch.setattr(store, "add_link", boom)

    with pytest.raises(RuntimeError, match="boom"):
        _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1", "m2"])

    assert (
        store.list_memories(MemoryFilter(active_only=False, exclude_stale=False), tenant_id="beta")
        == []
    )


# ---------------------------------------------------------------------------
# R7.3 — a destination deactivated during the copy rolls the whole copy back
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-854a40b8")
def test_destination_deactivated_between_writes_rolls_back(
    store: SqliteBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(store)
    original = store.add_memory
    calls: list[MemoryRecord | None] = []

    def deactivate_then_add(record: MemoryRecord | None = None, **fields: Any) -> MemoryRecord:
        calls.append(record)
        if len(calls) == 2:
            store.connect().execute("UPDATE tenants SET is_active = 0 WHERE id = ?", ("beta",))
        return original(record=record, **fields)

    monkeypatch.setattr(store, "add_memory", deactivate_then_add)

    with pytest.raises(TenantInactiveError) as excinfo:
        _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1", "m2"])

    assert excinfo.value.tenant_id == "beta"
    assert (
        store.list_memories(MemoryFilter(active_only=False, exclude_stale=False), tenant_id="beta")
        == []
    )


# ---------------------------------------------------------------------------
# R7.3 — two concurrent copies in one process run one after the other
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-854a40b8")
def test_concurrent_copies_in_one_process_are_serialised(store: SqliteBackend) -> None:
    _seed(store)
    reports: list[CopyReport] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            reports.append(
                _copy(store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1", "m2"])
            )
        except BaseException as exc:  # surfaced in the main thread
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not errors
    assert len(reports) == 2
    copied = sorted(report.memories_copied for report in reports)
    assert copied == [0, 2], "the second copy sees the first one's committed rows"
    assert sum(report.notes_copied for report in reports) == 1
    assert sorted(report.memories_skipped_duplicate for report in reports) == [0, 2]

    rows = store.list_memories(
        MemoryFilter(active_only=False, exclude_stale=False), tenant_id="beta"
    )
    contents = sorted(record.content for record in rows)
    assert contents == ["Alice prefers mornings", "Alice works at Acme", "Bob works at Acme"]


# ---------------------------------------------------------------------------
# R7.4 — the Postgres interim fails closed inside transaction(), before writes
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-ae539615")
def test_postgres_copy_fails_closed_before_any_write() -> None:
    conn = FakeConnection()
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)

    with pytest.raises(TenantNotFoundError):
        transfer.copy_between_tenants(
            backend, source_tenant="acme", dest_tenant="beta", all_active=True
        )

    assert not [
        sql for sql, _params in conn.executed if sql.lstrip().startswith("INSERT INTO memories")
    ]
    assert conn.commits == 0
    assert conn.rollbacks == 1
