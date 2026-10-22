"""Backend-agnostic conformance tests for tenant-scoped reads (R4.1).

Every check goes through the existing ``backend`` fixture and only calls
``StorageBackend`` Protocol methods, so the same file runs on SQLite in the L4
job and on a real Postgres database in the ``conformance-pg`` CI job.  A
concrete tenant sees only its own rows, ``None`` sees every tenant, and an
unknown tenant sees nothing.

The module imports the concrete backends only for the ``_store`` type check, as
the tenancy-writes conformance file does; no backend-specific method is called.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import pytest
from mintmory.core.ports import StorageBackend
from mintmory.core.storage import SqliteBackend
from mintmory.core.storage_postgres import PostgresBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    MemoryCategory,
    MemoryRecord,
    SearchAroundSpec,
    SearchRequest,
)

from conformance import BackendHandle

_G1 = "conformance-read-g1"
_G2 = "conformance-read-g2"
_A1 = "conformance-read-a1"
_A2 = "conformance-read-a2"


def _param_value(param: object) -> object:
    values = getattr(param, "values", (param,))
    return values[0]


def pytest_generate_tests(metafunc: Any) -> None:
    """Keep only the backend legs this environment can actually run.

    Without ``MINTMORY_TEST_PG_DSN`` the conformance fixture skips its Postgres
    leg; a skipped test proves nothing, so the leg is removed from collection
    here instead.  When a DSN is set the leg stays and both backends run (the
    ``conformance-pg`` job).
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


def _add(
    store: StorageBackend,
    memory_id: str,
    content: str,
    tenant_id: str,
    created_at: datetime,
) -> None:
    store.add_memory(
        MemoryRecord(
            id=memory_id,
            content=content,
            category=MemoryCategory.FACT,
            tenant_id=tenant_id,
            created_at=created_at,
        )
    )


def _seed(store: StorageBackend) -> None:
    """Two ``global`` and two ``t1`` memories with one link per tenant.

    Only ``g1`` and ``a1`` mention Alice, so a search for Alice isolates the
    tenancy predicate from ranking.  Explicit ids and timestamps keep every
    assertion independent of generated values.
    """
    store.create_tenant("t1")
    _add(store, _G1, "Alice uses Postgres", "global", datetime(2026, 1, 1))
    _add(store, _G2, "Bob uses MySQL", "global", datetime(2026, 1, 2))
    _add(store, _A1, "Alice uses SQLite", "t1", datetime(2026, 1, 3))
    _add(store, _A2, "Carol uses Redis", "t1", datetime(2026, 1, 4))
    store.add_link(
        ConceptLink(
            source_memory_id=_G1,
            target_memory_id=_G2,
            link_type=ConceptLinkType.RELATES_TO,
            tenant_id="global",
        )
    )
    store.add_link(
        ConceptLink(
            source_memory_id=_A1,
            target_memory_id=_A2,
            link_type=ConceptLinkType.RELATES_TO,
            tenant_id="t1",
        )
    )


@pytest.mark.l4("C-8a45446f")
def test_conformance_get_memory_is_tenant_scoped(backend: BackendHandle) -> None:
    store = _store(backend)
    _seed(store)

    scoped = store.get_memory(_A1, tenant_id="t1")
    assert scoped is not None
    assert scoped.id == _A1
    assert scoped.tenant_id == "t1"
    assert store.get_memory(_G1, tenant_id="t1") is None

    unscoped = store.get_memory(_G1, tenant_id=None)
    assert unscoped is not None
    assert unscoped.id == _G1
    assert store.get_memory(_A1, tenant_id=None) is not None

    assert store.get_memory(_A1, tenant_id="nope") is None
    assert store.get_memory(_G1, tenant_id="nope") is None


@pytest.mark.l4("C-8a45446f")
def test_conformance_list_memories_is_tenant_scoped(backend: BackendHandle) -> None:
    store = _store(backend)
    _seed(store)

    scoped = store.list_memories(tenant_id="t1")
    assert {memory.id for memory in scoped} == {_A1, _A2}
    assert all(memory.tenant_id == "t1" for memory in scoped)

    unscoped = store.list_memories(tenant_id=None)
    assert {memory.id for memory in unscoped} == {_G1, _G2, _A1, _A2}

    assert store.list_memories(tenant_id="nope") == []


@pytest.mark.l4("C-8a45446f")
def test_conformance_get_stats_is_tenant_scoped(backend: BackendHandle) -> None:
    store = _store(backend)
    _seed(store)

    scoped = store.get_stats(tenant_id="t1")
    assert scoped is not None
    assert scoped.total_memories == 2
    assert scoped.concept_links == 1

    unscoped = store.get_stats(tenant_id=None)
    assert unscoped is not None
    assert unscoped.total_memories == 4
    assert unscoped.concept_links == 2

    missing = store.get_stats(tenant_id="nope")
    assert missing is not None
    assert missing.total_memories == 0
    assert missing.concept_links == 0


@pytest.mark.l4("C-8a45446f")
def test_conformance_search_is_tenant_scoped(backend: BackendHandle) -> None:
    store = _store(backend)
    _seed(store)

    scoped = store.search(SearchRequest(query="Alice"), tenant_id="t1")
    assert scoped is not None
    scoped_ids = {memory.id for memory in scoped.memories}
    assert _A1 in scoped_ids
    assert scoped_ids <= {_A1, _A2}
    assert all(memory.tenant_id == "t1" for memory in scoped.memories)
    assert scoped.session_id != ""

    unscoped = store.search(SearchRequest(query="Alice"), tenant_id=None)
    assert unscoped is not None
    unscoped_ids = {memory.id for memory in unscoped.memories}
    assert {_G1, _A1} <= unscoped_ids
    assert unscoped_ids <= {_G1, _G2, _A1, _A2}
    assert {memory.tenant_id for memory in unscoped.memories} == {"global", "t1"}
    assert unscoped.session_id != ""

    missing = store.search(SearchRequest(query="Alice"), tenant_id="nope")
    assert missing is not None
    assert missing.memories == []
    assert missing.session_id == ""


@pytest.mark.l4("C-8a45446f")
def test_conformance_search_around_is_tenant_scoped(backend: BackendHandle) -> None:
    store = _store(backend)
    _seed(store)

    scoped = store.search_around([_G1, _A1], SearchAroundSpec(), tenant_id="t1")
    assert scoped == [_A2]

    unscoped = store.search_around([_G1, _A1], SearchAroundSpec(), tenant_id=None)
    assert set(unscoped) == {_G2, _A2}

    assert store.search_around([_G1, _A1], SearchAroundSpec(), tenant_id="nope") == []


@pytest.mark.l4("C-8a45446f")
def test_conformance_search_under_inactive_tenant_returns_no_session(
    backend: BackendHandle,
) -> None:
    store = _store(backend)
    _seed(store)

    active = store.search(SearchRequest(query="Alice"), tenant_id="t1")
    assert active is not None
    assert _A1 in {memory.id for memory in active.memories}
    assert active.session_id != ""

    store.set_tenant_active("t1", False)

    inactive = store.search(SearchRequest(query="Alice"), tenant_id="t1")
    assert inactive is not None
    assert _A1 in {memory.id for memory in inactive.memories}
    assert all(memory.tenant_id == "t1" for memory in inactive.memories)
    assert inactive.session_id == ""
