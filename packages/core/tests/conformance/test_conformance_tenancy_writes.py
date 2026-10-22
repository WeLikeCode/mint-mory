"""Backend-agnostic conformance tests for tenancy write behaviour (R7.1).

Every check uses only ``StorageBackend`` Protocol methods through the existing
``backend`` fixture, so the same file runs on SQLite in the L4 job and on a real
Postgres database in the ``conformance-pg`` CI job.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from mintmory.core.ports import StorageBackend
from mintmory.core.storage import SqliteBackend
from mintmory.core.storage_postgres import PostgresBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    CrossTenantLinkError,
    MemoryCategory,
    MemoryRecord,
    TenantInactiveError,
    TenantNotFoundError,
)

from conformance import BackendHandle


def _param_value(param: object) -> object:
    values = getattr(param, "values", (param,))
    return values[0]


def pytest_generate_tests(metafunc: Any) -> None:
    """Keep only the backend legs this environment can actually run.

    Without ``MINTMORY_TEST_PG_DSN`` the conformance fixture skips its Postgres
    leg; a skipped new test is not a failing red test, so the leg is removed from
    collection here instead.  When a DSN is set the leg stays and both backends
    run (the ``conformance-pg`` job).
    """
    if "backend" not in metafunc.fixturenames or os.environ.get("MINTMORY_TEST_PG_DSN"):
        return
    fixturedefs = getattr(metafunc, "_arg2fixturedefs", {})
    for fixturedef in fixturedefs.get("backend", ()):
        params = getattr(fixturedef, "params", None)
        if params:
            fixturedef.params = [p for p in params if _param_value(p) != "postgres"]


def _store(handle: BackendHandle) -> StorageBackend:
    backend = handle.backend
    assert isinstance(backend, (SqliteBackend, PostgresBackend))
    return backend


@pytest.mark.l4("C-9a8a10e6")
def test_write_to_missing_tenant_raises_and_writes_nothing(backend: BackendHandle) -> None:
    store = _store(backend)
    record = MemoryRecord(
        id="conf-missing-tenant-memory",
        content="a write to a missing tenant must not persist",
        category=MemoryCategory.FACT,
        tenant_id="conf-missing",
    )

    with pytest.raises(TenantNotFoundError) as err:
        store.add_memory(record=record)

    assert err.value.tenant_id == "conf-missing"
    assert store.get_memory(record.id) is None


@pytest.mark.l4("C-9a8a10e6")
def test_write_to_inactive_tenant_raises_and_writes_nothing(backend: BackendHandle) -> None:
    store = _store(backend)
    store.create_tenant("conf-inactive", "Inactive tenant")
    store.set_tenant_active("conf-inactive", False)
    record = MemoryRecord(
        id="conf-inactive-tenant-memory",
        content="a write to an inactive tenant must not persist",
        category=MemoryCategory.FACT,
        tenant_id="conf-inactive",
    )

    with pytest.raises(TenantInactiveError) as err:
        store.add_memory(record=record)

    assert err.value.tenant_id == "conf-inactive"
    assert store.get_memory(record.id) is None


@pytest.mark.l4("C-9a8a10e6")
def test_cross_tenant_add_link_raises(backend: BackendHandle) -> None:
    store = _store(backend)
    store.create_tenant("conf-a", "Tenant A")
    store.create_tenant("conf-b", "Tenant B")
    store.add_memory(
        MemoryRecord(
            id="conf-link-first",
            content="first conformance memory in tenant a",
            category=MemoryCategory.FACT,
            tenant_id="conf-a",
        )
    )
    store.add_memory(
        MemoryRecord(
            id="conf-link-second",
            content="second conformance memory in tenant b",
            category=MemoryCategory.FACT,
            tenant_id="conf-b",
        )
    )
    link = ConceptLink(
        source_memory_id="conf-link-first",
        target_memory_id="conf-link-second",
        link_type=ConceptLinkType.RELATES_TO,
        tenant_id="conf-a",
    )

    with pytest.raises(CrossTenantLinkError) as err:
        store.add_link(link)

    assert (
        err.value.first_id,
        err.value.first_tenant,
        err.value.second_id,
        err.value.second_tenant,
    ) == ("conf-link-first", "conf-a", "conf-link-second", "conf-b")


@pytest.mark.l4("C-9a8a10e6")
def test_archive_memory_in_another_tenant_raises_key_error(backend: BackendHandle) -> None:
    store = _store(backend)
    store.create_tenant("conf-owner", "Owner tenant")
    store.create_tenant("conf-other", "Other tenant")
    record = MemoryRecord(
        id="conf-archive-memory",
        content="conformance memory owned by another tenant",
        category=MemoryCategory.FACT,
        tenant_id="conf-owner",
    )
    store.add_memory(record=record)

    with pytest.raises(KeyError) as err:
        store.archive_memory(record.id, tenant_id="conf-other")

    assert record.id in str(err.value)
    stored = store.get_memory(record.id)
    assert stored is not None
    assert stored.is_archived is False


@pytest.mark.l4("C-9a8a10e6")
def test_transaction_that_raises_leaves_no_memory_rows(backend: BackendHandle) -> None:
    store = _store(backend)
    store.add_memory(
        MemoryRecord(
            id="conf-tx-survivor",
            content="committed before the transaction that rolls back",
            category=MemoryCategory.FACT,
        )
    )

    with pytest.raises(RuntimeError), store.transaction():
        store.add_memory(
            MemoryRecord(
                id="conf-tx-first",
                content="first write inside a transaction that rolls back",
                category=MemoryCategory.FACT,
            )
        )
        store.add_memory(
            MemoryRecord(
                id="conf-tx-second",
                content="second write inside a transaction that rolls back",
                category=MemoryCategory.FACT,
            )
        )
        raise RuntimeError("roll back the composed writes")

    kept = store.get_memory("conf-tx-survivor")
    assert kept is not None
    assert kept.content == "committed before the transaction that rolls back"
    assert store.get_memory("conf-tx-first") is None
    assert store.get_memory("conf-tx-second") is None
