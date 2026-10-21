"""Copy memories, attached notes and links from one tenant into another.

Signature-only stubs for the red step of task 1 (report, errors and
validation): the callable and the selection error exist so tests can import
them; no behaviour yet. ``COPY_MAX``, ``CopyReport`` and the validation order
of requirement 2 land in the green step.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mintmory.core.ports import StorageBackend
    from mintmory.core.types import MemoryFilter


class CopySelectionError(ValueError):
    pass


def copy_between_tenants(
    store: StorageBackend,
    *,
    source_tenant: str,
    dest_tenant: str,
    memory_ids: list[str] | None = None,
    filter: MemoryFilter | None = None,
    all_active: bool = False,
    force: bool = False,
) -> Any:
    """Return a ``CopyReport`` describing the copy of the requested selection."""
    raise NotImplementedError
