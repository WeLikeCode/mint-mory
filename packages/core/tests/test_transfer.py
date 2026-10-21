"""RED tests for task 1 — the copy report, its error and the validation order.

They trace requirement 1.1 (``transfer.py`` defines ``COPY_MAX``,
``CopySelectionError``, ``CopyReport`` and ``copy_between_tenants``, with
``CopyReport`` living in ``transfer.py`` and not in ``types.py``), requirement
2.1 (the rejection ladder (a)–(h), first failure wins, exact messages) and
requirement 2.2 (a whole-tenant copy is requested only by ``all_active=True``;
an empty filter is never read as "copy everything"), each rejection checked
with its type and message as requirement 9.7 asks.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
from mintmory.core import transfer
from mintmory.core import types as core_types
from mintmory.core.storage import SqliteBackend
from mintmory.core.transfer import CopySelectionError
from mintmory.core.types import (
    TENANT_ID_PATTERN,
    InvalidTenantIdError,
    MemoryCategory,
    MemoryFilter,
    TenantInactiveError,
    TenantNotFoundError,
)


@pytest.fixture
def store(tmp_path: Path) -> SqliteBackend:
    backend = SqliteBackend(tmp_path / "copy.db")
    backend.initialise()
    return backend


# ---------------------------------------------------------------------------
# Requirement 1.1 — the module surface
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-66378bd9")
def test_transfer_module_defines_report_error_and_entry_point() -> None:
    sentinel: Any = object()
    assert getattr(transfer, "COPY_MAX", sentinel) == 10_000

    selection_error = getattr(transfer, "CopySelectionError", sentinel)
    assert selection_error is not sentinel
    assert issubclass(selection_error, ValueError)

    assert not hasattr(core_types, "CopyReport"), "CopyReport lives in transfer.py"
    report_cls = getattr(transfer, "CopyReport", sentinel)
    assert report_cls is not sentinel
    fields = report_cls.model_fields
    assert set(fields) == {
        "source_tenant",
        "dest_tenant",
        "memories_copied",
        "memories_skipped_duplicate",
        "memories_skipped_not_found",
        "notes_copied",
        "notes_skipped_duplicate",
        "links_copied",
        "id_map",
    }
    assert fields["source_tenant"].is_required()
    assert fields["dest_tenant"].is_required()
    for name in (
        "memories_copied",
        "memories_skipped_duplicate",
        "memories_skipped_not_found",
        "notes_copied",
        "notes_skipped_duplicate",
        "links_copied",
    ):
        assert fields[name].default == 0, f"{name} must default to 0"
    assert fields["id_map"].default_factory is dict

    report = report_cls(source_tenant="acme", dest_tenant="beta")
    assert report.source_tenant == "acme"
    assert report.dest_tenant == "beta"
    assert report.memories_copied == 0
    assert report.memories_skipped_duplicate == 0
    assert report.memories_skipped_not_found == 0
    assert report.notes_copied == 0
    assert report.notes_skipped_duplicate == 0
    assert report.links_copied == 0
    assert report.id_map == {}

    entry = transfer.copy_between_tenants
    assert callable(entry)
    params = inspect.signature(entry).parameters
    assert set(params) == {
        "store",
        "source_tenant",
        "dest_tenant",
        "memory_ids",
        "filter",
        "all_active",
        "force",
    }
    assert params["store"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    for name in (
        "source_tenant",
        "dest_tenant",
        "memory_ids",
        "filter",
        "all_active",
        "force",
    ):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY, name
    for name, default in (
        ("memory_ids", None),
        ("filter", None),
        ("all_active", False),
        ("force", False),
    ):
        assert params[name].default == default
    assert params["source_tenant"].default is inspect.Parameter.empty
    assert params["dest_tenant"].default is inspect.Parameter.empty


# ---------------------------------------------------------------------------
# Requirement 2.1 (a) — validate_tenant_id on both ids, before everything else
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-21e82523", "C-63f0307a")
def test_invalid_tenant_ids_are_rejected_first(store: SqliteBackend) -> None:
    with pytest.raises(InvalidTenantIdError) as source_exc:
        transfer.copy_between_tenants(
            store, source_tenant="ACME", dest_tenant="beta", memory_ids=["m1"]
        )
    assert str(source_exc.value) == f"invalid tenant id 'ACME': expected {TENANT_ID_PATTERN}"
    assert source_exc.value.tenant_id == "ACME"

    with pytest.raises(InvalidTenantIdError) as dest_exc:
        transfer.copy_between_tenants(
            store, source_tenant="acme", dest_tenant="BETA", memory_ids=["m1"]
        )
    assert dest_exc.value.tenant_id == "BETA"

    with pytest.raises(InvalidTenantIdError) as same_exc:
        transfer.copy_between_tenants(store, source_tenant="ACME", dest_tenant="ACME")
    assert same_exc.value.tenant_id == "ACME"


# ---------------------------------------------------------------------------
# Requirement 2.1 (b) — source_tenant == dest_tenant, before tenant lookups
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-21e82523", "C-63f0307a")
def test_same_source_and_destination_rejected(store: SqliteBackend) -> None:
    with pytest.raises(CopySelectionError) as ids_exc:
        transfer.copy_between_tenants(
            store, source_tenant="acme", dest_tenant="acme", memory_ids=["m1"]
        )
    assert str(ids_exc.value) == "source and destination are the same tenant"

    with pytest.raises(CopySelectionError) as all_active_exc:
        transfer.copy_between_tenants(
            store, source_tenant="acme", dest_tenant="acme", all_active=True
        )
    assert str(all_active_exc.value) == "source and destination are the same tenant"


# ---------------------------------------------------------------------------
# Requirement 2.1 (c) — all_active cannot be combined with memory_ids or filter
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-21e82523", "C-63f0307a")
def test_all_active_conflicts_with_ids_or_filter(store: SqliteBackend) -> None:
    message = "all_active cannot be combined with memory_ids or filter"

    with pytest.raises(CopySelectionError) as ids_exc:
        transfer.copy_between_tenants(
            store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1"], all_active=True
        )
    assert str(ids_exc.value) == message

    with pytest.raises(CopySelectionError) as filled_filter_exc:
        transfer.copy_between_tenants(
            store,
            source_tenant="acme",
            dest_tenant="beta",
            filter=MemoryFilter(category=MemoryCategory.FACT),
            all_active=True,
        )
    assert str(filled_filter_exc.value) == message

    with pytest.raises(CopySelectionError) as empty_filter_exc:
        transfer.copy_between_tenants(
            store,
            source_tenant="acme",
            dest_tenant="beta",
            filter=MemoryFilter(),
            all_active=True,
        )
    assert str(empty_filter_exc.value) == message


@pytest.mark.l4("C-21e82523", "C-18841969")
def test_all_active_with_empty_memory_ids_passes_validation(store: SqliteBackend) -> None:
    store.create_tenant("acme")

    with pytest.raises(TenantNotFoundError) as empty_ids_exc:
        transfer.copy_between_tenants(
            store, source_tenant="acme", dest_tenant="ghost", memory_ids=[], all_active=True
        )
    assert empty_ids_exc.value.tenant_id == "ghost"

    with pytest.raises(TenantNotFoundError) as bare_exc:
        transfer.copy_between_tenants(
            store, source_tenant="acme", dest_tenant="ghost", all_active=True
        )
    assert bare_exc.value.tenant_id == "ghost"


# ---------------------------------------------------------------------------
# Requirement 2.1 (d) / requirement 2.2 — the empty filter is never a whole copy
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-21e82523", "C-18841969", "C-63f0307a")
def test_empty_filter_is_rejected(store: SqliteBackend) -> None:
    message = "empty filter: use all_active=True to copy every active memory"
    empty_filters = (
        MemoryFilter(),
        MemoryFilter(active_only=False),
        MemoryFilter(exclude_stale=False),
    )
    for empty in empty_filters:
        with pytest.raises(CopySelectionError) as excinfo:
            transfer.copy_between_tenants(
                store, source_tenant="acme", dest_tenant="beta", filter=empty
            )
        assert str(excinfo.value) == message


@pytest.mark.l4("C-18841969")
def test_non_empty_filter_passes_validation(store: SqliteBackend) -> None:
    store.create_tenant("acme")

    with pytest.raises(TenantNotFoundError) as category_exc:
        transfer.copy_between_tenants(
            store,
            source_tenant="acme",
            dest_tenant="ghost",
            filter=MemoryFilter(category=MemoryCategory.FACT),
        )
    assert category_exc.value.tenant_id == "ghost"

    with pytest.raises(TenantNotFoundError) as usefulness_exc:
        transfer.copy_between_tenants(
            store,
            source_tenant="acme",
            dest_tenant="ghost",
            filter=MemoryFilter(min_usefulness=1.0, verified_only=True),
        )
    assert usefulness_exc.value.tenant_id == "ghost"


# ---------------------------------------------------------------------------
# Requirement 2.1 (e) — no selection at all
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-21e82523", "C-63f0307a")
def test_empty_selection_is_rejected(store: SqliteBackend) -> None:
    message = "empty selection: pass memory_ids, filter or all_active=True"

    with pytest.raises(CopySelectionError) as bare_exc:
        transfer.copy_between_tenants(store, source_tenant="acme", dest_tenant="beta")
    assert str(bare_exc.value) == message

    with pytest.raises(CopySelectionError) as empty_ids_exc:
        transfer.copy_between_tenants(
            store, source_tenant="acme", dest_tenant="beta", memory_ids=[]
        )
    assert str(empty_ids_exc.value) == message


# ---------------------------------------------------------------------------
# Requirement 2.1 (f) — more than COPY_MAX distinct explicit ids
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-21e82523", "C-63f0307a")
def test_selection_over_copy_max_is_rejected(store: SqliteBackend) -> None:
    ids = [f"mem-{i:05d}" for i in range(10_001)]
    with pytest.raises(CopySelectionError) as excinfo:
        transfer.copy_between_tenants(
            store, source_tenant="acme", dest_tenant="beta", memory_ids=ids
        )
    assert str(excinfo.value) == "selection exceeds 10000 memories"


@pytest.mark.l4("C-21e82523")
def test_copy_max_boundary_counts_distinct_ids(store: SqliteBackend) -> None:
    store.create_tenant("acme")
    exactly = [f"mem-{i:05d}" for i in range(10_000)]
    with_repeat = [exactly[0], *exactly]
    assert len(with_repeat) == 10_001

    with pytest.raises(TenantNotFoundError) as boundary_exc:
        transfer.copy_between_tenants(
            store, source_tenant="acme", dest_tenant="ghost", memory_ids=exactly
        )
    assert boundary_exc.value.tenant_id == "ghost"

    with pytest.raises(TenantNotFoundError) as distinct_exc:
        transfer.copy_between_tenants(
            store, source_tenant="acme", dest_tenant="ghost", memory_ids=with_repeat
        )
    assert distinct_exc.value.tenant_id == "ghost"


# ---------------------------------------------------------------------------
# Requirement 2.1 (g)/(h) — tenant directory checks
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-21e82523", "C-63f0307a")
def test_source_tenant_is_checked_before_destination(store: SqliteBackend) -> None:
    with pytest.raises(TenantNotFoundError) as both_exc:
        transfer.copy_between_tenants(
            store, source_tenant="ghost-a", dest_tenant="ghost-b", memory_ids=["m1"]
        )
    assert str(both_exc.value) == "tenant 'ghost-a' not found"

    store.create_tenant("beta")
    with pytest.raises(TenantNotFoundError) as source_exc:
        transfer.copy_between_tenants(
            store, source_tenant="ghost-a", dest_tenant="beta", memory_ids=["m1"]
        )
    assert source_exc.value.tenant_id == "ghost-a"


@pytest.mark.l4("C-21e82523", "C-63f0307a")
def test_inactive_destination_tenant_is_rejected(store: SqliteBackend) -> None:
    store.create_tenant("acme")
    store.create_tenant("beta")
    store.set_tenant_active("beta", False)

    with pytest.raises(TenantInactiveError) as excinfo:
        transfer.copy_between_tenants(
            store, source_tenant="acme", dest_tenant="beta", memory_ids=["m1"]
        )
    assert str(excinfo.value) == "tenant 'beta' is inactive (read-only)"
    assert excinfo.value.tenant_id == "beta"


@pytest.mark.l4("C-21e82523", "C-63f0307a")
def test_inactive_source_tenant_is_allowed(store: SqliteBackend) -> None:
    store.create_tenant("sunk")
    store.set_tenant_active("sunk", False)

    with pytest.raises(TenantNotFoundError) as excinfo:
        transfer.copy_between_tenants(
            store, source_tenant="sunk", dest_tenant="ghost", memory_ids=["m1"]
        )
    assert excinfo.value.tenant_id == "ghost"
