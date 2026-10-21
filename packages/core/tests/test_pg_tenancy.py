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
    MemoryFilter,
    MemoryRecord,
    MemorySummary,
    QueryResult,
    QuerySession,
    SearchAroundSpec,
    SearchRequest,
    TenancyNotSupportedError,
    Tenant,
)

from packages.core.tests.pg_fakes import FakeConnection, FakePool


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


@pytest.mark.l4("C-1b7a83e9")
def test_pg_transaction_tenancy() -> None:
    conn = FakeConnection()
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)

    with backend.transaction() as yielded:
        assert yielded is conn

    assert conn.commits == 1


# ---------------------------------------------------------------------------
# Task 4 — the Postgres interim id-only writes reject a non-global tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3810642f")
def test_pg_archive_memory_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.archive_memory, keyword_only=False, default=None)
    archive_memory = cast(Callable[..., object], backend.archive_memory)
    with pytest.raises(TenancyNotSupportedError):
        archive_memory("m1", tenant_id="t1")
    assert backend._pool is None


@pytest.mark.l4("C-3810642f")
def test_pg_supersede_memory_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.supersede_memory, keyword_only=False, default=None)
    supersede_memory = cast(Callable[..., object], backend.supersede_memory)
    with pytest.raises(TenancyNotSupportedError):
        supersede_memory("m1", "m2", tenant_id="t1")
    assert backend._pool is None


@pytest.mark.l4("C-3810642f")
def test_pg_apply_feedback_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.apply_feedback, keyword_only=False, default=None)
    apply_feedback = cast(Callable[..., object], backend.apply_feedback)
    with pytest.raises(TenancyNotSupportedError):
        apply_feedback("m1", True, False, tenant_id="t1")
    assert backend._pool is None


@pytest.mark.l4("C-44a91f81")
def test_pg_update_memory_tenancy() -> None:
    backend = _backend()
    update_memory = cast(Callable[..., object], backend.update_memory)
    with pytest.raises(TenancyNotSupportedError):
        update_memory("m1", tenant_id="t1")
    assert backend._pool is None


# ---------------------------------------------------------------------------
# Task 6 — tenant-scoped reads and the Postgres interim
# ---------------------------------------------------------------------------


def _assert_read_surface_complete() -> None:
    """R5.1/R5.2: every read of R1.1 plus ``list_memories`` takes a tenant.

    Rechecked by every per-method test so the whole read surface is declared on
    both the Protocol and the Postgres interim, not just the method under test.
    """
    expected = {
        "get_memory": False,
        "search": True,
        "search_around": False,
        "get_links": False,
        "get_annotating_notes": False,
        "get_annotating_descriptions": False,
        "find_image_file_record": False,
        "anchor_candidates": False,
        "list_image_file_records": False,
        "list_notes": True,
        "list_summaries": False,
        "get_session": False,
        "get_stats": False,
        "memory_exists_with_content": False,
        "get_flagged_memories": False,
        "get_never_accessed_stale": False,
        "get_high_staleness_useful": False,
        "get_anomaly_high_staleness_useful_ids": False,
        "get_anomaly_never_accessed_ids": False,
        "get_anomaly_flagged_ids": False,
        "list_active_memory_ids": True,
        "get_stale_archivable_ids": False,
        "get_rehabilitable_rows": False,
        "get_existing_relates_to_pairs": False,
        "list_memories": True,
    }
    missing: list[str] = []
    wrong_default: list[str] = []
    for owner in (StorageBackend, PostgresBackend):
        for name in expected:
            params = inspect.signature(getattr(owner, name)).parameters
            if "tenant_id" not in params:
                missing.append(f"{owner.__name__}.{name}")
            elif params["tenant_id"].default is not None:
                wrong_default.append(f"{owner.__name__}.{name}")
    assert missing == [], f"reads missing tenant_id: {missing}"
    assert wrong_default == [], f"reads with a non-None tenant default: {wrong_default}"


def _assert_read_rejects_tenant(
    backend: PostgresBackend,
    operation: str,
    invoke: Callable[[], object],
) -> None:
    _assert_read_surface_complete()
    with pytest.raises(TenancyNotSupportedError) as excinfo:
        invoke()
    assert excinfo.value.operation == operation
    assert backend._pool is None


@pytest.mark.l4("C-588818fc")
def test_protocol_declares_tenant_read_signatures() -> None:
    _assert_read_surface_complete()


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_memory_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_memory, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "get_memory",
        lambda: backend.get_memory("m1", tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_search_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.search, keyword_only=True, default=None)
    _assert_read_rejects_tenant(
        backend,
        "search",
        lambda: backend.search(SearchRequest(query="Alice"), tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_search_around_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.search_around, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "search_around",
        lambda: backend.search_around(["m1"], SearchAroundSpec(), tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_links_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_links, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "get_links",
        lambda: backend.get_links("m1", tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_annotating_notes_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_annotating_notes, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "get_annotating_notes",
        lambda: backend.get_annotating_notes("m1", 3, tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_annotating_descriptions_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_annotating_descriptions, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "get_annotating_descriptions",
        lambda: backend.get_annotating_descriptions("m1", 3, tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_find_image_file_record_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.find_image_file_record, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "find_image_file_record",
        lambda: backend.find_image_file_record("/x.png", tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_anchor_candidates_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.anchor_candidates, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "anchor_candidates",
        lambda: backend.anchor_candidates("Alice", tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_list_image_file_records_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.list_image_file_records, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "list_image_file_records",
        lambda: backend.list_image_file_records(tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_list_notes_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.list_notes, keyword_only=True, default=None)
    _assert_read_rejects_tenant(
        backend,
        "list_notes",
        lambda: backend.list_notes(tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_list_summaries_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.list_summaries, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "list_summaries",
        lambda: backend.list_summaries(tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_session_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_session, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "get_session",
        lambda: backend.get_session("s1", tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_stats_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_stats, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "get_stats",
        lambda: backend.get_stats(tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_memory_exists_with_content_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.memory_exists_with_content, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "memory_exists_with_content",
        lambda: backend.memory_exists_with_content("Alice", tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_flagged_memories_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_flagged_memories, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "get_flagged_memories",
        lambda: backend.get_flagged_memories(tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_never_accessed_stale_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_never_accessed_stale, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "get_never_accessed_stale",
        lambda: backend.get_never_accessed_stale(tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_high_staleness_useful_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_high_staleness_useful, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "get_high_staleness_useful",
        lambda: backend.get_high_staleness_useful(tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_anomaly_high_staleness_useful_ids_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(
        backend.get_anomaly_high_staleness_useful_ids, keyword_only=False, default=None
    )
    _assert_read_rejects_tenant(
        backend,
        "get_anomaly_high_staleness_useful_ids",
        lambda: backend.get_anomaly_high_staleness_useful_ids(5.0, 3.0, tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_anomaly_never_accessed_ids_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(
        backend.get_anomaly_never_accessed_ids, keyword_only=False, default=None
    )
    _assert_read_rejects_tenant(
        backend,
        "get_anomaly_never_accessed_ids",
        lambda: backend.get_anomaly_never_accessed_ids("2020-01-01T00:00:00+00:00", tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_anomaly_flagged_ids_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_anomaly_flagged_ids, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "get_anomaly_flagged_ids",
        lambda: backend.get_anomaly_flagged_ids(tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_list_active_memory_ids_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.list_active_memory_ids, keyword_only=True, default=None)
    _assert_read_rejects_tenant(
        backend,
        "list_active_memory_ids",
        lambda: backend.list_active_memory_ids(tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_stale_archivable_ids_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_stale_archivable_ids, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "get_stale_archivable_ids",
        lambda: backend.get_stale_archivable_ids(5.0, "2020-01-01T00:00:00+00:00", tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_rehabilitable_rows_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.get_rehabilitable_rows, keyword_only=False, default=None)
    _assert_read_rejects_tenant(
        backend,
        "get_rehabilitable_rows",
        lambda: backend.get_rehabilitable_rows("2020-01-01T00:00:00+00:00", tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_existing_relates_to_pairs_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(
        backend.get_existing_relates_to_pairs, keyword_only=False, default=None
    )
    _assert_read_rejects_tenant(
        backend,
        "get_existing_relates_to_pairs",
        lambda: backend.get_existing_relates_to_pairs(tenant_id="t1"),
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_list_memories_tenancy() -> None:
    backend = _backend()
    _assert_tenant_parameter(backend.list_memories, keyword_only=True, default=None)
    _assert_read_rejects_tenant(
        backend,
        "list_memories",
        lambda: backend.list_memories(),
    )
    _assert_read_rejects_tenant(
        backend,
        "list_memories",
        lambda: backend.list_memories(tenant_id="t1"),
    )
    _assert_read_rejects_tenant(
        backend,
        "list_memories",
        lambda: backend.list_memories(MemoryFilter(), tenant_id="t1", limit=0),
    )
