"""RED tests for task 6 — the storage Protocol and the Postgres interim.

They trace requirement 6.1 (``StorageBackend`` declares the four tenant
directory methods, the keyed summary/manifest signatures and ``ManifestEntry``
carries ``tenant_id``), 6.2 (``PostgresBackend`` satisfies the Protocol and
rejects every non-global tenant with ``TenancyNotSupportedError`` before it
touches its pool) and 6.3 (one function per stubbed method, all of which answer
without opening a connection).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import datetime
from typing import cast

import pytest
from mintmory.core.ports import ManifestEntry, StorageBackend
from mintmory.core.storage_postgres import PostgresBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    MemoryCategory,
    MemoryRecord,
    MemorySummary,
    QueryResult,
    QuerySession,
    TenancyNotSupportedError,
    Tenant,
)


def _backend() -> PostgresBackend:
    backend = PostgresBackend("postgresql://unused")
    assert backend._pool is None
    return backend


def _assert_tenant_parameter(
    func: Callable[..., object],
    *,
    keyword_only: bool,
    default: object,
) -> None:
    params = inspect.signature(func).parameters
    assert "tenant_id" in params, f"{func!r} has no tenant_id parameter"
    assert params["tenant_id"].default == default
    if keyword_only:
        assert params["tenant_id"].kind is inspect.Parameter.KEYWORD_ONLY


# ---------------------------------------------------------------------------
# Requirement 6.1 — Protocol declarations
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-eed56474")
def test_protocol_declares_tenant_directory_methods() -> None:
    for name in ("create_tenant", "get_tenant", "list_tenants", "set_tenant_active"):
        assert hasattr(StorageBackend, name), f"StorageBackend is missing {name}"


@pytest.mark.l4("C-eed56474")
def test_protocol_tenant_signatures_and_manifest_entry() -> None:
    assert "tenant_id" in ManifestEntry.__annotations__

    _assert_tenant_parameter(StorageBackend.get_summary, keyword_only=False, default="global")

    for name in ("manifest_get", "manifest_paths", "manifest_delete"):
        _assert_tenant_parameter(getattr(StorageBackend, name), keyword_only=True, default="global")

    manifest_upsert = inspect.signature(StorageBackend.manifest_upsert).parameters
    _assert_tenant_parameter(StorageBackend.manifest_upsert, keyword_only=True, default="global")
    assert "content_hash" in manifest_upsert
    assert manifest_upsert["content_hash"].default is None

    tenant_methods = {
        "create_tenant": ["self", "tenant_id", "name"],
        "get_tenant": ["self", "tenant_id"],
        "list_tenants": ["self"],
        "set_tenant_active": ["self", "tenant_id", "active"],
    }
    tenant_params = {
        name: inspect.signature(getattr(StorageBackend, name)).parameters for name in tenant_methods
    }
    for name, expected in tenant_methods.items():
        assert list(tenant_params[name]) == expected
    assert tenant_params["create_tenant"]["name"].default == ""


# ---------------------------------------------------------------------------
# Requirement 6.2 + 6.3 — the shared guard
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_require_global_tenant_tenancy() -> None:
    assert isinstance(
        inspect.getattr_static(PostgresBackend, "_require_global_tenant"), staticmethod
    )
    assert PostgresBackend._require_global_tenant(None, "read") is None
    assert PostgresBackend._require_global_tenant("global", "read") is None
    with pytest.raises(TenancyNotSupportedError):
        PostgresBackend._require_global_tenant("t1", "read")


# ---------------------------------------------------------------------------
# Requirement 6.2 + 6.3 — summary methods
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_get_summary_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_summary, keyword_only=False, default="global")
    get_summary = cast(Callable[..., object], backend.get_summary)
    with pytest.raises(TenancyNotSupportedError):
        get_summary("acme", tenant_id="t1")
    assert backend._pool is None


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_upsert_summary_tenancy() -> None:
    backend = _backend()
    summary = MemorySummary(
        concept="acme",
        summary_text="Acme summary",
        memory_count=1,
        tenant_id="t1",
    )
    with pytest.raises(TenancyNotSupportedError):
        backend.upsert_summary(summary)
    assert backend._pool is None


# ---------------------------------------------------------------------------
# Requirement 6.2 + 6.3 — manifest methods
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_manifest_get_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.manifest_get, keyword_only=True, default="global")
    manifest_get = cast(Callable[..., object], backend.manifest_get)
    with pytest.raises(TenancyNotSupportedError):
        manifest_get("/a", tenant_id="t1")
    assert backend._pool is None


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_manifest_upsert_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.manifest_upsert, keyword_only=True, default="global")
    manifest_upsert = cast(Callable[..., object], backend.manifest_upsert)
    with pytest.raises(TenancyNotSupportedError):
        manifest_upsert(
            "/a",
            "default",
            size=1,
            mtime=0.0,
            online_only=False,
            index_mode="content",
            memory_ids=[],
            tenant_id="t1",
        )
    assert backend._pool is None


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_manifest_paths_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.manifest_paths, keyword_only=True, default="global")
    manifest_paths = cast(Callable[..., object], backend.manifest_paths)
    with pytest.raises(TenancyNotSupportedError):
        manifest_paths("default", tenant_id="t1")
    assert backend._pool is None


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_manifest_delete_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.manifest_delete, keyword_only=True, default="global")
    manifest_delete = cast(Callable[..., object], backend.manifest_delete)
    with pytest.raises(TenancyNotSupportedError):
        manifest_delete("/a", tenant_id="t1")
    assert backend._pool is None


# ---------------------------------------------------------------------------
# Requirement 6.2 + 6.3 — write methods
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_add_memory_tenancy() -> None:
    backend = _backend()
    record = MemoryRecord(
        content="Alice works at Acme", category=MemoryCategory.FACT, tenant_id="t1"
    )
    with pytest.raises(TenancyNotSupportedError):
        backend.add_memory(record)
    assert backend._pool is None


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_add_link_tenancy() -> None:
    backend = _backend()
    link = ConceptLink(
        source_memory_id="m1",
        target_memory_id="m2",
        link_type=ConceptLinkType.RELATES_TO,
        tenant_id="t1",
    )
    with pytest.raises(TenancyNotSupportedError):
        backend.add_link(link)
    assert backend._pool is None


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_create_session_tenancy() -> None:
    backend = _backend()
    session = QuerySession(query_text="who works at Acme?", tenant_id="t1")
    with pytest.raises(TenancyNotSupportedError):
        backend.create_session(session)
    assert backend._pool is None


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_record_query_results_tenancy() -> None:
    backend = _backend()
    result = QueryResult(
        session_id="s1",
        memory_id="m1",
        relevance_score=1.0,
        tenant_id="t1",
    )
    with pytest.raises(TenancyNotSupportedError):
        backend.record_query_results([result])
    assert backend._pool is None


# ---------------------------------------------------------------------------
# Requirement 6.2 + 6.3 — tenant directory methods
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_get_tenant_tenancy() -> None:
    backend = _backend()
    global_tenant = backend.get_tenant("global")
    assert global_tenant == Tenant(
        id="global",
        name="Global (default) tenant",
        is_active=True,
        created_at=datetime(1970, 1, 1),
        updated_at=datetime(1970, 1, 1),
    )
    assert backend.get_tenant("t1") is None
    assert backend._pool is None


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_list_tenants_tenancy() -> None:
    backend = _backend()
    tenants = backend.list_tenants()
    assert [tenant.id for tenant in tenants] == ["global"]
    assert tenants[0].name == "Global (default) tenant"
    assert tenants[0].is_active is True
    assert backend._pool is None


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_create_tenant_tenancy() -> None:
    backend = _backend()
    with pytest.raises(TenancyNotSupportedError):
        backend.create_tenant("acme", "Acme Corp")
    assert backend._pool is None


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_set_tenant_active_tenancy() -> None:
    backend = _backend()
    with pytest.raises(TenancyNotSupportedError):
        backend.set_tenant_active("global", False)
    assert backend._pool is None


# ---------------------------------------------------------------------------
# Task 1 — the Postgres interim transaction() raises before any pool access
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-74b68113")
def test_pg_transaction_tenancy() -> None:
    backend = _backend()
    transaction = getattr(backend, "transaction", None)
    assert transaction is not None, "PostgresBackend must provide an interim transaction()"
    with pytest.raises(TenancyNotSupportedError) as excinfo, transaction():
        pass  # pragma: no cover — the interim raises before yielding
    assert isinstance(excinfo.value, TenancyNotSupportedError)
    assert getattr(excinfo.value, "operation", None) == "transaction"
    assert backend._pool is None
