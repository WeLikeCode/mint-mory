"""RED tests for the R3.2 cap on filter/all_active rows before duplicate skipping.

They trace C-3affbf7d (the remaining filter/all_active rows are capped after
superseded rows are dropped) and C-18a7043f (the cap applies even when some of
the remaining rows are duplicates in the destination, and nothing is written).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mintmory.core import transfer
from mintmory.core.storage import SqliteBackend
from mintmory.core.transfer import CopySelectionError
from mintmory.core.types import MemoryCategory, MemoryFilter, MemoryRecord


@pytest.fixture
def cap_store(tmp_path: Path) -> SqliteBackend:
    backend = SqliteBackend(tmp_path / "cap-selection.db")
    backend.initialise()
    backend.create_tenant("acme")
    backend.create_tenant("beta")
    return backend


def _cap_add(
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


def _cap_dest_contents(store: SqliteBackend) -> list[str]:
    rows = store.list_memories(
        MemoryFilter(active_only=False, exclude_stale=False), tenant_id="beta"
    )
    return [record.content for record in rows]


@pytest.mark.l4("C-3affbf7d", "C-18a7043f")
def test_all_active_cap_counts_remaining_rows_including_destination_duplicates(
    cap_store: SqliteBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cap_add(cap_store, "m1", "First fact")
    _cap_add(cap_store, "m2", "Second fact")
    _cap_add(cap_store, "m3", "Third fact")
    _cap_add(cap_store, "m4", "Superseded fact", superseded_by="m1")
    _cap_add(cap_store, "b-dup", "First fact", tenant="beta")
    monkeypatch.setattr(transfer, "COPY_MAX", 2)
    before = _cap_dest_contents(cap_store)

    with pytest.raises(CopySelectionError) as excinfo:
        transfer.copy_between_tenants(
            cap_store, source_tenant="acme", dest_tenant="beta", all_active=True
        )

    assert str(excinfo.value) == "selection exceeds 2 memories"
    assert _cap_dest_contents(cap_store) == before


@pytest.mark.l4("C-3affbf7d", "C-18a7043f")
def test_filter_cap_counts_remaining_rows_including_destination_duplicates(
    cap_store: SqliteBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cap_add(cap_store, "m1", "First fact")
    _cap_add(cap_store, "m2", "Second fact")
    _cap_add(cap_store, "m3", "Third fact")
    _cap_add(cap_store, "m4", "Superseded fact", superseded_by="m1")
    _cap_add(cap_store, "b-dup", "First fact", tenant="beta")
    monkeypatch.setattr(transfer, "COPY_MAX", 2)
    before = _cap_dest_contents(cap_store)

    with pytest.raises(CopySelectionError) as excinfo:
        transfer.copy_between_tenants(
            cap_store,
            source_tenant="acme",
            dest_tenant="beta",
            filter=MemoryFilter(category=MemoryCategory.FACT),
        )

    assert str(excinfo.value) == "selection exceeds 2 memories"
    assert _cap_dest_contents(cap_store) == before
