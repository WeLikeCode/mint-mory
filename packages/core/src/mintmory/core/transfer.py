"""Cross-tenant copy — report, errors and the validation ladder (task 1).

``copy_between_tenants`` copies memories, their attached notes and the links
among the copied records from one tenant into another as one atomic operation.
The copy never moves: the source is never modified.

This green step implements the ``COPY_MAX`` cap, ``CopySelectionError``,
``CopyReport`` (which lives here, not in ``types.py``: it is neither stored nor
served by the HTTP API) and the rejection ladder of requirement 2 — first
failure wins, nothing read or written after it. The selection, duplicate
handling, record copy and link copy arrive in tasks 2–3, so a selection that
passes every check still raises ``NotImplementedError``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from mintmory.core.types import (
    MemoryFilter,
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
        raise NotImplementedError("selection and copy arrive in tasks 2 and 3")
    return report
