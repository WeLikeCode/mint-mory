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
from typing import Any

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
    ProtectedTenantError,
    QueryResult,
    QuerySession,
    SearchAroundSpec,
    SearchRequest,
    TenancyNotSupportedError,
    Tenant,
    TenantImmutableError,
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


def _read_responder(sql: str, params: Any) -> list[Any]:
    normalised = " ".join(sql.split())
    if normalised.startswith("SELECT is_active FROM tenants"):
        return [{"is_active": True}]
    if "COUNT(" in normalised:
        return [(0,)]
    if "AVG(" in normalised:
        return [(None, None)]
    return []


def _read_backend() -> tuple[PostgresBackend, FakeConnection]:
    conn = FakeConnection(responder=_read_responder)
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)
    return backend, conn


def _normalised_statements(conn: FakeConnection) -> list[tuple[str, tuple[Any, ...]]]:
    return [
        (" ".join(sql.split()), () if params is None else tuple(params))
        for sql, params in conn.executed
    ]


def _assert_read_tenancy(invoke: Callable[[PostgresBackend, str | None], object]) -> None:
    _assert_read_surface_complete()
    backend, conn = _read_backend()
    invoke(backend, "t1")
    scoped = _normalised_statements(conn)
    assert scoped, "read executed no statement"
    for sql, params in scoped:
        assert sql.upper().startswith("SELECT"), sql
        assert "tenant_id = %s" in sql, sql
        assert "t1" in params, params
    conn.executed.clear()
    invoke(backend, None)
    for sql, _params in _normalised_statements(conn):
        assert "tenant_id =" not in sql, sql


def _assert_keyed_read_scoped(
    backend: PostgresBackend,
    conn: FakeConnection,
    invoke: Callable[[], object],
    expected_params: tuple[Any, ...],
) -> None:
    invoke()
    statements = _normalised_statements(conn)
    assert statements
    sql, params = statements[0]
    assert sql.upper().startswith("SELECT"), sql
    assert "tenant_id = %s" in sql, sql
    assert params == expected_params, params


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
    assert not hasattr(PostgresBackend, "_require_global_tenant")
    assert issubclass(TenancyNotSupportedError, NotImplementedError)


# ---------------------------------------------------------------------------
# Requirement 6.2 + 6.3 — summary methods
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_get_summary_tenancy() -> None:
    backend, conn = _read_backend()
    _assert_tenant_parameter(backend.get_summary, keyword_only=False, default="global")
    _assert_keyed_read_scoped(
        backend, conn, lambda: backend.get_summary("c", tenant_id="t1"), ("c", "t1")
    )


@pytest.mark.l4("C-a7f825e4", "C-0e897873", "C-1b7a83e9")
def test_pg_upsert_summary_tenancy() -> None:
    backend, conn = _write_backend(_write_responder())
    summary = MemorySummary(
        concept="acme",
        summary_text="Acme summary",
        memory_count=1,
        tenant_id="t1",
    )

    backend.upsert_summary(summary)

    insert_sql, insert_params = _write_statement(conn, "INSERT INTO memory_summaries")
    assert "t1" in insert_params
    assert conn.commits == 1


# ---------------------------------------------------------------------------
# Requirement 6.2 + 6.3 — manifest methods
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_manifest_get_tenancy() -> None:
    backend, conn = _read_backend()
    _assert_tenant_parameter(backend.manifest_get, keyword_only=True, default="global")
    _assert_keyed_read_scoped(
        backend, conn, lambda: backend.manifest_get("/a", tenant_id="t1"), ("/a", "t1")
    )


@pytest.mark.l4("C-a7f825e4", "C-0e897873", "C-1b7a83e9")
def test_pg_manifest_upsert_tenancy() -> None:
    backend, conn = _write_backend(_write_responder())
    _assert_tenant_parameter(backend.manifest_upsert, keyword_only=True, default="global")

    backend.manifest_upsert(
        "/a",
        "default",
        size=1,
        mtime=0.0,
        online_only=False,
        index_mode="content",
        memory_ids=[],
        tenant_id="t1",
    )

    insert_sql, insert_params = _write_statement(conn, "INSERT INTO index_manifest")
    assert "t1" in insert_params
    assert conn.commits == 1


@pytest.mark.l4("C-a7f825e4", "C-0e897873")
def test_pg_manifest_paths_tenancy() -> None:
    backend, conn = _read_backend()
    _assert_tenant_parameter(backend.manifest_paths, keyword_only=True, default="global")
    _assert_keyed_read_scoped(
        backend, conn, lambda: backend.manifest_paths("c", tenant_id="t1"), ("c", "t1")
    )


@pytest.mark.l4("C-a7f825e4", "C-0e897873", "C-1b7a83e9")
def test_pg_manifest_delete_tenancy() -> None:
    backend, conn = _write_backend(_write_responder())
    _assert_tenant_parameter(backend.manifest_delete, keyword_only=True, default="global")

    backend.manifest_delete("/a", tenant_id="t1")

    delete_sql, delete_params = _write_statement(conn, "DELETE FROM index_manifest")
    assert delete_params == ("/a", "t1")
    assert conn.commits == 1


# ---------------------------------------------------------------------------
# Requirement 6.2 + 6.3 — write methods
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-a7f825e4", "C-0e897873", "C-1b7a83e9")
def test_pg_add_memory_tenancy() -> None:
    backend, conn = _write_backend(_write_responder())
    record = MemoryRecord(
        content="Alice works at Acme", category=MemoryCategory.FACT, tenant_id="t1"
    )

    backend.add_memory(record)

    insert_sql, insert_params = _write_statement(conn, "INSERT INTO memories")
    assert "t1" in insert_params
    assert conn.commits == 1


@pytest.mark.l4("C-a7f825e4", "C-0e897873", "C-1b7a83e9")
def test_pg_add_link_tenancy() -> None:
    backend, conn = _write_backend(_write_responder())
    link = ConceptLink(
        source_memory_id="m1",
        target_memory_id="m2",
        link_type=ConceptLinkType.RELATES_TO,
        tenant_id="t1",
    )

    backend.add_link(link)

    insert_sql, insert_params = _write_statement(conn, "INSERT INTO concept_links")
    assert "t1" in insert_params
    assert conn.commits == 1


@pytest.mark.l4("C-a7f825e4", "C-0e897873", "C-1b7a83e9")
def test_pg_create_session_tenancy() -> None:
    backend, conn = _write_backend(_write_responder())
    session = QuerySession(query_text="who works at Acme?", tenant_id="t1")

    backend.create_session(session)

    insert_sql, insert_params = _write_statement(conn, "INSERT INTO query_sessions")
    assert "t1" in insert_params
    assert conn.commits == 1


@pytest.mark.l4("C-a7f825e4", "C-0e897873", "C-1b7a83e9")
def test_pg_record_query_results_tenancy() -> None:
    backend, conn = _write_backend(_write_responder())
    result = QueryResult(
        session_id="s1",
        memory_id="m1",
        relevance_score=1.0,
        tenant_id="t1",
    )

    backend.record_query_results([result])

    insert_sql, insert_params = _write_statement(conn, "INSERT INTO query_results")
    assert "t1" in insert_params
    assert conn.commits == 1


# ---------------------------------------------------------------------------
# Requirement 6.2 + 6.3 — tenant directory methods
# ---------------------------------------------------------------------------


def _tenant_row(
    tenant_id: str,
    name: str,
    is_active: bool,
    created_at: datetime,
    updated_at: datetime,
) -> dict[str, object]:
    return {
        "id": tenant_id,
        "name": name,
        "is_active": is_active,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _write_memory_row(memory_id: str, tenant_id: str) -> dict[str, object]:
    stamp = datetime(2026, 1, 1)
    return {
        "id": memory_id,
        "content": "Alice works at Acme",
        "category": MemoryCategory.FACT.value,
        "entity_ids": ["Alice"],
        "confidence": 1.0,
        "source": "agent",
        "verified": False,
        "valid_from": None,
        "valid_until": None,
        "usefulness_score": 0.0,
        "staleness_score": 0.0,
        "reinforcement_count": 0,
        "retrieval_count": 0,
        "is_stale": False,
        "is_active": True,
        "is_archived": False,
        "superseded_by": None,
        "flagged_for_review": False,
        "contradicts_ids": [],
        "is_note": False,
        "created_at": stamp,
        "updated_at": stamp,
        "last_accessed_at": None,
        "metadata": {},
        "tenant_id": tenant_id,
    }


def _write_session_row(session_id: str, tenant_id: str) -> dict[str, object]:
    return {
        "id": session_id,
        "query_text": "who works at Acme?",
        "created_at": datetime(2026, 1, 1),
        "confidence_rating": None,
        "reasoning": None,
        "useful_ids": [],
        "stale_ids": [],
        "concluded": False,
        "tenant_id": tenant_id,
    }


def _write_summary_row(summary_id: str, concept: str, tenant_id: str) -> dict[str, object]:
    return {
        "id": summary_id,
        "concept": concept,
        "summary_text": "Acme summary",
        "memory_count": 1,
        "is_current": True,
        "generated_at": datetime(2026, 1, 1),
        "tenant_id": tenant_id,
    }


def _write_responder(tenant_id: str = "t1") -> Callable[[str, Any], list[Any]]:
    """Answer the write guard, tenant lookups and row reads for one tenant."""

    def responder(sql: str, params: Any) -> list[Any]:
        normalised = " ".join(sql.split())
        if normalised.startswith("SELECT is_active FROM tenants"):
            return [{"is_active": True}]
        if normalised.startswith("SELECT tenant_id FROM memories WHERE id = %s"):
            return [{"tenant_id": tenant_id}]
        if "FROM memories WHERE id = %s" in normalised:
            return [_write_memory_row(str(params[0]), tenant_id)]
        if normalised.startswith("SELECT tenant_id FROM query_sessions WHERE id = %s"):
            return [{"tenant_id": tenant_id}]
        if "FROM query_sessions WHERE id = %s" in normalised:
            return [_write_session_row(str(params[0]), tenant_id)]
        if normalised.startswith(
            "SELECT id FROM memory_summaries WHERE tenant_id = %s AND concept = %s"
        ):
            return [{"id": "sum1"}]
        if "FROM memory_summaries" in normalised:
            return [_write_summary_row("sum1", "acme", tenant_id)]
        return []

    return responder


def _write_backend(
    responder: Callable[[str, Any], list[Any]],
) -> tuple[PostgresBackend, FakeConnection]:
    conn = FakeConnection(responder=responder)
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)
    return backend, conn


def _write_statement(conn: FakeConnection, marker: str) -> tuple[str, Any]:
    for sql, params in conn.executed:
        if marker in " ".join(sql.split()):
            return " ".join(sql.split()), params
    raise AssertionError(f"no executed statement contains {marker!r}: {conn.executed!r}")


@pytest.mark.l4("C-c0d003ce", "C-be5b17eb", "C-1b7a83e9")
def test_pg_get_tenant_tenancy() -> None:
    created = datetime(2026, 1, 2, 3, 4, 5)
    row = _tenant_row("t1", "Tenant one", True, created, created)

    def responder(sql: str, params: Any) -> list[Any]:
        return [row] if params == ("t1",) else []

    conn = FakeConnection(responder=responder)
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)

    assert backend.get_tenant("t1") == Tenant(
        id="t1",
        name="Tenant one",
        is_active=True,
        created_at=created,
        updated_at=created,
    )
    assert backend.get_tenant("missing") is None
    select_sql, select_params = conn.executed[0]
    assert " ".join(select_sql.split()) == (
        "SELECT id, name, is_active, created_at, updated_at FROM tenants WHERE id = %s"
    )
    assert select_params == ("t1",)


@pytest.mark.l4("C-c0d003ce", "C-be5b17eb", "C-1b7a83e9")
def test_pg_list_tenants_tenancy() -> None:
    first = _tenant_row("alpha", "Alpha", True, datetime(2026, 1, 1), datetime(2026, 1, 1))
    second = _tenant_row("beta", "Beta", False, datetime(2026, 1, 2), datetime(2026, 1, 3))

    def responder(sql: str, params: Any) -> list[Any]:
        return [first, second] if "ORDER BY id" in sql else []

    conn = FakeConnection(responder=responder)
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)

    tenants = backend.list_tenants()

    assert [tenant.id for tenant in tenants] == ["alpha", "beta"]
    assert [tenant.is_active for tenant in tenants] == [True, False]
    select_sql, select_params = conn.executed[0]
    assert " ".join(select_sql.split()) == (
        "SELECT id, name, is_active, created_at, updated_at FROM tenants ORDER BY id"
    )
    assert select_params is None


@pytest.mark.l4("C-f55a34a6", "C-be5b17eb", "C-1b7a83e9")
def test_pg_create_tenant_tenancy() -> None:
    created = datetime(2026, 1, 2, 3, 4, 5)
    row = _tenant_row("acme", "Acme Corp", True, created, created)

    def responder(sql: str, params: Any) -> list[Any]:
        return [row] if "FROM tenants WHERE id = %s" in sql else []

    conn = FakeConnection(responder=responder)
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)

    tenant = backend.create_tenant("acme", "Acme Corp")

    assert tenant == Tenant(
        id="acme",
        name="Acme Corp",
        is_active=True,
        created_at=created,
        updated_at=created,
    )
    insert_sql, insert_params = conn.executed[0]
    assert " ".join(insert_sql.split()) == (
        "INSERT INTO tenants (id, name, is_active, created_at, updated_at) "
        "VALUES (%s, %s, TRUE, %s, %s) ON CONFLICT (id) DO NOTHING"
    )
    tenant_param, name_param, first_now, second_now = insert_params
    assert (tenant_param, name_param) == ("acme", "Acme Corp")
    assert first_now == second_now
    assert isinstance(first_now, datetime)
    assert first_now.tzinfo is None
    select_sql, select_params = conn.executed[1]
    assert " ".join(select_sql.split()) == (
        "SELECT id, name, is_active, created_at, updated_at FROM tenants WHERE id = %s"
    )
    assert select_params == ("acme",)


@pytest.mark.l4("C-c0d003ce", "C-edb554ee", "C-1b7a83e9")
def test_pg_set_tenant_active_tenancy() -> None:
    created = datetime(2026, 1, 1)
    row = _tenant_row("global", "Global", True, created, created)
    conn = FakeConnection(responder=lambda sql, params: [row])
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)

    with pytest.raises(ProtectedTenantError):
        backend.set_tenant_active("global", False)

    assert not [sql for sql, _ in conn.executed if sql.lstrip().startswith("UPDATE tenants")]


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


@pytest.mark.l4("C-3810642f", "C-1b7a83e9")
def test_pg_archive_memory_tenancy() -> None:
    backend, conn = _write_backend(_write_responder())
    _assert_tenant_parameter(backend.archive_memory, keyword_only=False, default=None)

    backend.archive_memory("m1", tenant_id="t1")

    update_sql, update_params = _write_statement(conn, "UPDATE memories SET is_archived")
    assert update_params[-1] == "m1"
    assert conn.commits == 1


@pytest.mark.l4("C-3810642f", "C-1b7a83e9")
def test_pg_supersede_memory_tenancy() -> None:
    backend, conn = _write_backend(_write_responder())
    _assert_tenant_parameter(backend.supersede_memory, keyword_only=False, default=None)

    backend.supersede_memory("m1", "m2", tenant_id="t1")

    update_sql, update_params = _write_statement(conn, "UPDATE memories SET superseded_by")
    assert update_params[0] == "m2"
    assert update_params[-1] == "m1"
    assert conn.commits == 1


@pytest.mark.l4("C-3810642f", "C-1b7a83e9")
def test_pg_apply_feedback_tenancy() -> None:
    responder = _write_responder()
    base = responder

    def answering(sql: str, params: Any) -> list[Any]:
        if "UPDATE memories SET" in sql:
            return [{"id": "m1"}]
        return base(sql, params)

    backend, conn = _write_backend(answering)
    _assert_tenant_parameter(backend.apply_feedback, keyword_only=False, default=None)

    backend.apply_feedback("m1", True, False, tenant_id="t1")

    update_sql, _update_params = _write_statement(conn, "UPDATE memories SET usefulness_score")
    assert conn.commits == 1


@pytest.mark.l4("C-44a91f81", "C-1b7a83e9")
def test_pg_update_memory_tenancy() -> None:
    backend, conn = _write_backend(_write_responder())

    backend.update_memory("m1", content="changed", tenant_id="t1")

    update_sql, update_params = _write_statement(conn, "UPDATE memories SET")
    assert update_params[-1] == "m1"
    assert conn.commits == 1

    with pytest.raises(TenantImmutableError):
        backend.update_memory("m1", tenant_id="global")


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


@pytest.mark.l4("C-588818fc")
def test_protocol_declares_tenant_read_signatures() -> None:
    _assert_read_surface_complete()


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_memory_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.get_memory, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.get_memory("m1", tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_search_tenancy() -> None:
    backend, conn = _read_backend()
    _assert_tenant_parameter(backend.search, keyword_only=True, default=None)

    backend.search(SearchRequest(query="Alice"), tenant_id="t1")
    scoped = [
        (sql, params) for sql, params in _normalised_statements(conn) if "content_tsv @@" in sql
    ]
    assert scoped
    for sql, params in scoped:
        assert "tenant_id = %s" in sql, sql
        assert "t1" in params, params

    conn.executed.clear()
    backend.search(SearchRequest(query="Alice"))
    unscoped = [
        (sql, params) for sql, params in _normalised_statements(conn) if "content_tsv @@" in sql
    ]
    assert unscoped
    for sql, _params in unscoped:
        assert "tenant_id =" not in sql, sql


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_search_around_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.search_around, keyword_only=False, default=None)
    _assert_read_tenancy(
        lambda b, tenant: b.search_around(["m1"], SearchAroundSpec(), tenant_id=tenant)
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_links_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.get_links, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.get_links("m1", tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_annotating_notes_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.get_annotating_notes, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.get_annotating_notes("m1", 3, tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_annotating_descriptions_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.get_annotating_descriptions, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.get_annotating_descriptions("m1", 3, tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_find_image_file_record_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.find_image_file_record, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.find_image_file_record("/x.png", tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_anchor_candidates_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.anchor_candidates, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.anchor_candidates("Alice", tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_list_image_file_records_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.list_image_file_records, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.list_image_file_records(tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_list_notes_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.list_notes, keyword_only=True, default=None)
    _assert_read_tenancy(lambda b, tenant: b.list_notes(tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_list_summaries_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.list_summaries, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.list_summaries(tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_session_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.get_session, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.get_session("s1", tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_stats_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.get_stats, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.get_stats(tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_memory_exists_with_content_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.memory_exists_with_content, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.memory_exists_with_content("Alice", tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_flagged_memories_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.get_flagged_memories, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.get_flagged_memories(tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_never_accessed_stale_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.get_never_accessed_stale, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.get_never_accessed_stale(tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_high_staleness_useful_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.get_high_staleness_useful, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.get_high_staleness_useful(tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_anomaly_high_staleness_useful_ids_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(
        backend.get_anomaly_high_staleness_useful_ids, keyword_only=False, default=None
    )
    _assert_read_tenancy(
        lambda b, tenant: b.get_anomaly_high_staleness_useful_ids(5.0, 3.0, tenant_id=tenant)
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_anomaly_never_accessed_ids_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(
        backend.get_anomaly_never_accessed_ids, keyword_only=False, default=None
    )
    _assert_read_tenancy(
        lambda b, tenant: b.get_anomaly_never_accessed_ids(
            "2020-01-01T00:00:00+00:00", tenant_id=tenant
        )
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_anomaly_flagged_ids_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.get_anomaly_flagged_ids, keyword_only=False, default=None)
    _assert_read_tenancy(lambda b, tenant: b.get_anomaly_flagged_ids(tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_list_active_memory_ids_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.list_active_memory_ids, keyword_only=True, default=None)
    _assert_read_tenancy(lambda b, tenant: b.list_active_memory_ids(tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_stale_archivable_ids_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.get_stale_archivable_ids, keyword_only=False, default=None)
    _assert_read_tenancy(
        lambda b, tenant: b.get_stale_archivable_ids(
            5.0, "2020-01-01T00:00:00+00:00", tenant_id=tenant
        )
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_rehabilitable_rows_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.get_rehabilitable_rows, keyword_only=False, default=None)
    _assert_read_tenancy(
        lambda b, tenant: b.get_rehabilitable_rows("2020-01-01T00:00:00+00:00", tenant_id=tenant)
    )


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_get_existing_relates_to_pairs_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(
        backend.get_existing_relates_to_pairs, keyword_only=False, default=None
    )
    _assert_read_tenancy(lambda b, tenant: b.get_existing_relates_to_pairs(tenant_id=tenant))


@pytest.mark.l4("C-c6d483c5", "C-da381c66")
def test_pg_list_memories_tenancy() -> None:
    backend, _conn = _read_backend()
    _assert_tenant_parameter(backend.list_memories, keyword_only=True, default=None)
    _assert_read_tenancy(lambda b, tenant: b.list_memories(tenant_id=tenant))
    _assert_read_tenancy(
        lambda b, tenant: b.list_memories(MemoryFilter(), tenant_id=tenant, limit=0)
    )
