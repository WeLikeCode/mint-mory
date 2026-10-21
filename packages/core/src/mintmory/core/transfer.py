"""Cross-tenant copy — selection, duplicates and record mapping.

``copy_between_tenants`` copies memories, their attached notes and the links
among the copied records from one tenant into another as one atomic operation.
The copy never moves: the source is never modified.

This module implements the ``COPY_MAX`` cap, ``CopySelectionError``,
``CopyReport`` (which lives here, not in ``types.py``: it is neither stored nor
served by the HTTP API), the rejection ladder of requirement 2, the selection
and one-level note expansion of requirement 3, duplicate handling of
requirement 4 and the record mapping of requirement 5. Everything runs inside
one ``store.transaction()`` so a failure writes nothing in the destination.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from mintmory.core.types import (
    MemoryFilter,
    MemoryRecord,
    TenantInactiveError,
    TenantNotFoundError,
    validate_tenant_id,
)
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from mintmory.core.ports import StorageBackend

COPY_MAX: Final[int] = 10_000


class CopySelectionError(ValueError):
    """The requested selection is invalid or empty; nothing has been written."""


def _is_empty_filter(filter: MemoryFilter) -> bool:
    """True when every selecting field of the filter keeps its default value.

    ``active_only`` and ``exclude_stale`` are not selecting fields: a filter
    that only changes them is still an empty filter (an empty filter never
    reads as "copy everything"; only ``all_active=True`` requests that).
    """
    return (
        filter.category is None
        and filter.source is None
        and filter.entity is None
        and not filter.verified_only
        and filter.min_usefulness is None
        and filter.max_staleness is None
    )


class CopyReport(BaseModel):
    """Outcome of one cross-tenant copy."""

    source_tenant: str
    dest_tenant: str
    memories_copied: int = 0  # copied records with is_note False
    memories_skipped_duplicate: int = 0
    memories_skipped_not_found: int = 0
    notes_copied: int = 0  # copied records with is_note True
    notes_skipped_duplicate: int = 0
    links_copied: int = 0  # every link created, ANNOTATES included
    id_map: dict[str, str] = Field(default_factory=dict)  # source id -> new id


def _select(
    store: StorageBackend,
    *,
    source_tenant: str,
    memory_ids: list[str] | None,
    filter: MemoryFilter | None,
    all_active: bool,
    report: CopyReport,
) -> list[MemoryRecord]:
    """Return the source rows for the selection: ids first, then filter rows."""
    selected: list[MemoryRecord] = []

    seen_ids: set[str] = set()
    for memory_id in memory_ids or []:
        if memory_id in seen_ids:
            continue
        seen_ids.add(memory_id)
        record = store.get_memory(memory_id, tenant_id=source_tenant)
        if (
            record is None
            or record.is_archived
            or not record.is_active
            or record.superseded_by is not None
        ):
            report.memories_skipped_not_found += 1
            continue
        selected.append(record)

    if all_active:
        rows = store.list_memories(MemoryFilter(exclude_stale=False), tenant_id=source_tenant)
    elif filter is not None:
        rows = store.list_memories(
            filter.model_copy(update={"active_only": True}), tenant_id=source_tenant
        )
    else:
        rows = []
    selected.extend(row for row in rows if row.superseded_by is None)
    return selected


def _copy_record(
    source: MemoryRecord, id_map: dict[str, str], source_tenant: str, dest_tenant: str
) -> MemoryRecord:
    """Build the destination record: copied fields, reset state, rewritten metadata."""
    metadata = {
        **source.metadata,
        "copied_from_tenant": source_tenant,
        "source_memory_id": source.id,
    }
    if "anchor_memory_id" in metadata:
        anchor = metadata["anchor_memory_id"]
        if isinstance(anchor, str) and anchor in id_map:
            metadata["anchor_memory_id"] = id_map[anchor]
        else:
            metadata.pop("anchor_memory_id", None)

    now = datetime.now(UTC).replace(tzinfo=None)
    return MemoryRecord(
        id=id_map[source.id],
        content=source.content,
        category=source.category,
        entity_ids=list(source.entity_ids),
        confidence=source.confidence,
        source=source.source,
        verified=source.verified,
        valid_from=source.valid_from,
        valid_until=source.valid_until,
        is_note=source.is_note,
        created_at=now,
        updated_at=now,
        metadata=metadata,
        tenant_id=dest_tenant,
    )


def _count_copied(report: CopyReport, record: MemoryRecord) -> None:
    if record.is_note:
        report.notes_copied += 1
    else:
        report.memories_copied += 1


def _count_duplicate(report: CopyReport, record: MemoryRecord) -> None:
    if record.is_note:
        report.notes_skipped_duplicate += 1
    else:
        report.memories_skipped_duplicate += 1


def copy_between_tenants(
    store: StorageBackend,
    *,
    source_tenant: str,
    dest_tenant: str,
    memory_ids: list[str] | None = None,
    filter: MemoryFilter | None = None,
    all_active: bool = False,
    force: bool = False,
) -> CopyReport:
    """Copy the selected memories (and attached notes) between two tenants."""
    report = CopyReport(source_tenant=source_tenant, dest_tenant=dest_tenant)
    with store.transaction():
        validate_tenant_id(source_tenant)
        validate_tenant_id(dest_tenant)
        if source_tenant == dest_tenant:
            raise CopySelectionError("source and destination are the same tenant")
        if all_active and (memory_ids or filter is not None):
            raise CopySelectionError("all_active cannot be combined with memory_ids or filter")
        if filter is not None and _is_empty_filter(filter):
            raise CopySelectionError(
                "empty filter: use all_active=True to copy every active memory"
            )
        if not memory_ids and filter is None and not all_active:
            raise CopySelectionError("empty selection: pass memory_ids, filter or all_active=True")
        if memory_ids and len(set(memory_ids)) > COPY_MAX:
            raise CopySelectionError(f"selection exceeds {COPY_MAX} memories")
        if store.get_tenant(source_tenant) is None:
            raise TenantNotFoundError(source_tenant)
        destination = store.get_tenant(dest_tenant)
        if destination is None:
            raise TenantNotFoundError(dest_tenant)
        if not destination.is_active:
            raise TenantInactiveError(dest_tenant)

        selected = _select(
            store,
            source_tenant=source_tenant,
            memory_ids=memory_ids,
            filter=filter,
            all_active=all_active,
            report=report,
        )

        plan: list[MemoryRecord] = []
        seen: set[str] = set()
        planned_contents: set[str] = set()

        def consider(record: MemoryRecord) -> bool:
            if record.id in seen:
                return False
            seen.add(record.id)
            if not force and (
                record.content in planned_contents
                or store.memory_exists_with_content(record.content, tenant_id=dest_tenant)
            ):
                _count_duplicate(report, record)
                return False
            planned_contents.add(record.content)
            report.id_map[record.id] = str(uuid.uuid4())
            plan.append(record)
            return True

        for record in selected:
            consider(record)

        for record in list(plan):
            for note in store.get_annotating_notes(record.id, COPY_MAX, tenant_id=source_tenant):
                if note.is_active and note.superseded_by is None:
                    consider(note)

        if len(plan) > COPY_MAX:
            raise CopySelectionError(f"selection exceeds {COPY_MAX} memories")

        for record in plan:
            store.add_memory(record=_copy_record(record, report.id_map, source_tenant, dest_tenant))
            _count_copied(report, record)
    return report
