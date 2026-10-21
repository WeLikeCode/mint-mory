"""RED tests for task 1 — Postgres connection binding and ``transaction()``.

They trace requirements 4.1–4.5 with the fake pool of ``pg_fakes`` and 5.5's
rewrite of the Postgres transaction test: one bound connection per transaction,
one commit at the outermost exit, rollback left to the pool, a nested block
joining the outer one, reads and search phases on the same connection, and a
plain thread taking its own connection.  The pre-existing
``test_pg_transaction_tenancy`` still asserts the interim stub, which red may
not edit, so the replacement behaviour is pinned here under new names.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

import pytest
from mintmory.core.storage_postgres import PostgresBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    InvalidTenantIdError,
    MemoryCategory,
    MemoryRecord,
    MemorySummary,
    ProtectedTenantError,
    QueryResult,
    QuerySession,
    SearchRequest,
    TenancyNotSupportedError,
    Tenant,
    TenantInactiveError,
    TenantNotFoundError,
)

from packages.core.tests.pg_fakes import FakeConnection, FakePool


def _active(sql: str, params: Any) -> list[Any]:
    """The fake write guard: every tenant is active, every other query is empty."""
    if sql.lstrip().startswith("SELECT is_active FROM tenants"):
        return [{"is_active": True}]
    return []


def _backend(pool: FakePool) -> PostgresBackend:
    backend = PostgresBackend("postgresql://unused")
    backend._pool = pool
    return backend


def _record(content: str) -> MemoryRecord:
    return MemoryRecord(content=content, category=MemoryCategory.FACT)


@contextmanager
def _transaction(backend: PostgresBackend) -> Iterator[Any]:
    """Open the backend transaction, failing an assertion on the interim stub."""
    try:
        with backend.transaction() as conn:
            yield conn
    except TenancyNotSupportedError as exc:
        if getattr(exc, "operation", None) == "transaction":
            pytest.fail(f"transaction() must be re-entrant, not the interim stub: {exc}")
        raise


@pytest.mark.l4("C-f97c4a2c", "C-ae2a0704", "C-1b7a83e9")
def test_pg_transaction_commits_two_writes_once() -> None:
    conn = FakeConnection(responder=_active)
    pool = FakePool(conn)
    backend = _backend(pool)

    with _transaction(backend):
        backend.add_memory(_record("first fact"))
        backend.add_memory(_record("second fact"))
        assert conn.commits == 0, "a bound write must not commit inside the block"

    inserts = [sql for sql, _ in conn.executed if sql.lstrip().startswith("INSERT INTO memories")]
    assert len(inserts) == 2
    assert conn.commits == 1, "leaving the outermost block commits exactly once"
    assert pool.checkouts == 1


@pytest.mark.l4("C-f97c4a2c", "C-68061c64", "C-ae2a0704")
def test_pg_transaction_rolls_back_once_and_reraises() -> None:
    conn = FakeConnection(responder=_active)
    backend = _backend(FakePool(conn))

    with pytest.raises(RuntimeError, match="compose failed"), _transaction(backend):
        backend.add_memory(_record("rolled back"))
        raise RuntimeError("compose failed")

    assert conn.commits == 0
    assert conn.rollbacks == 1, "the pool rolls back once, the backend never does"


@pytest.mark.l4("C-f97c4a2c", "C-ae2a0704")
def test_pg_nested_transaction_joins_the_outer_block() -> None:
    conn = FakeConnection(responder=_active)
    pool = FakePool(conn)
    backend = _backend(pool)

    with _transaction(backend):
        with _transaction(backend) as inner:
            assert inner is conn
            backend.add_memory(_record("nested fact"))
            assert conn.commits == 0
        assert conn.commits == 0, "a nested exit must not commit"

    assert conn.commits == 1
    assert pool.checkouts == 1


@pytest.mark.l4("C-fd67032b", "C-ae2a0704")
def test_pg_get_memory_inside_transaction_uses_the_bound_connection() -> None:
    conn = FakeConnection(responder=_active)
    pool = FakePool(conn)
    backend = _backend(pool)

    with _transaction(backend):
        record = backend.add_memory(_record("read after write"))
        assert backend.get_memory(record.id) is None
        assert pool.checkouts == 1, "a read inside the block must not take another connection"

        statements = [sql for sql, _ in conn.executed]
        insert_at = max(
            index
            for index, sql in enumerate(statements)
            if sql.lstrip().startswith("INSERT INTO memories")
        )
        select_at = next(
            index
            for index, sql in enumerate(statements)
            if sql.startswith("SELECT") and "FROM memories WHERE id = %s" in sql
        )
        assert select_at > insert_at, "the read follows the insert on the same connection"

    assert conn.commits == 1


@pytest.mark.l4("C-fd67032b", "C-68061c64")
def test_pg_search_phases_inside_transaction_use_the_bound_connection() -> None:
    conn = FakeConnection(responder=_active)
    pool = FakePool(conn)
    backend = _backend(pool)

    with _transaction(backend):
        response = backend.search(SearchRequest(query="alice"))
        assert pool.checkouts == 1, "every search phase runs on the bound connection"
        statements = [sql for sql, _ in conn.executed]
        assert any("ts_rank(content_tsv" in sql for sql in statements)
        assert any(sql.lstrip().startswith("INSERT INTO query_sessions") for sql in statements)
        assert response.memories == []

    assert conn.commits == 1


@pytest.mark.l4("C-0940d0a8", "C-ae2a0704")
def test_pg_add_memory_from_thread_gets_its_own_connection() -> None:
    pool = FakePool(lambda: FakeConnection(responder=_active))
    backend = _backend(pool)
    finished = threading.Event()
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            backend.add_memory(_record("thread fact"))
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)
        finally:
            finished.set()

    with _transaction(backend):
        backend.add_memory(_record("main fact"))
        thread = threading.Thread(target=writer)
        thread.start()
        assert finished.wait(5), "the thread's write did not finish"
        thread.join(5)
        assert not thread.is_alive()
        assert errors == []
        assert len(pool.connections) == 2
        assert pool.connections[1].commits == 1
        assert pool.connections[0].commits == 0

    assert pool.connections[0].commits == 1


@pytest.mark.l4("C-f97c4a2c", "C-0940d0a8")
def test_pg_tx_conn_is_a_per_instance_context_var() -> None:
    first = PostgresBackend("postgresql://unused")
    second = PostgresBackend("postgresql://unused")

    first_var = getattr(first, "_tx_conn", None)
    second_var = getattr(second, "_tx_conn", None)

    assert isinstance(first_var, ContextVar)
    assert first_var.get() is None, "the default binding is empty"
    assert second_var is not first_var, "each backend owns its binding"


@pytest.mark.l4("C-1b7a83e9", "C-f97c4a2c")
def test_pg_transaction_no_longer_raises_tenancy_not_supported() -> None:
    conn = FakeConnection(responder=_active)
    backend = _backend(FakePool(conn))

    try:
        with backend.transaction() as yielded:
            assert yielded is conn
    except TenancyNotSupportedError as exc:
        pytest.fail(f"transaction() must replace the interim stub: {exc}")

    assert conn.commits == 1


# ---------------------------------------------------------------------------
# Task 2 — the tenant directory (R1.1-R1.3, R5.4, R5.7)
# ---------------------------------------------------------------------------


def _tenant_row(
    tenant_id: str,
    name: str,
    is_active: bool,
    created_at: datetime,
    updated_at: datetime,
) -> dict[str, Any]:
    return {
        "id": tenant_id,
        "name": name,
        "is_active": is_active,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _create_tenant(backend: PostgresBackend, tenant_id: str, name: str = "") -> Tenant:
    """Call create_tenant, turning the interim stub into a plain assertion failure."""
    try:
        return backend.create_tenant(tenant_id, name)
    except TenancyNotSupportedError as exc:
        pytest.fail(f"create_tenant must replace the interim stub: {exc}")


def _set_tenant_active(backend: PostgresBackend, tenant_id: str, active: bool) -> Tenant:
    """Call set_tenant_active, turning the interim stub into an assertion failure."""
    try:
        return backend.set_tenant_active(tenant_id, active)
    except TenancyNotSupportedError as exc:
        pytest.fail(f"set_tenant_active must replace the interim stub: {exc}")


def _naive_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.mark.l4("C-f55a34a6", "C-be5b17eb", "C-1b7a83e9")
def test_pg_create_tenant_inserts_then_selects_and_returns_row() -> None:
    created = datetime(2026, 1, 2, 3, 4, 5)
    row = _tenant_row("acme", "Acme Corp", True, created, created)

    def responder(sql: str, params: Any) -> list[Any]:
        if "FROM tenants WHERE id = %s" in sql:
            return [row]
        return []

    conn = FakeConnection(responder=responder)
    backend = _backend(FakePool(conn))
    before = _naive_utc()

    tenant = _create_tenant(backend, "acme", "Acme Corp")

    after = _naive_utc()
    assert tenant == Tenant(
        id="acme",
        name="Acme Corp",
        is_active=True,
        created_at=created,
        updated_at=created,
    )
    statements = [(" ".join(sql.split()), params) for sql, params in conn.executed]
    assert len(statements) == 2, statements
    insert_sql, insert_params = statements[0]
    assert insert_sql == (
        "INSERT INTO tenants (id, name, is_active, created_at, updated_at) "
        "VALUES (%s, %s, TRUE, %s, %s) ON CONFLICT (id) DO NOTHING"
    )
    tenant_param, name_param, first_now, second_now = insert_params
    assert (tenant_param, name_param) == ("acme", "Acme Corp")
    assert first_now == second_now
    assert isinstance(first_now, datetime)
    assert first_now.tzinfo is None, "the TIMESTAMP columns take a naive UTC datetime"
    assert before <= first_now <= after
    select_sql, select_params = statements[1]
    assert select_sql == (
        "SELECT id, name, is_active, created_at, updated_at FROM tenants WHERE id = %s"
    )
    assert select_params == ("acme",)


@pytest.mark.l4("C-f55a34a6", "C-be5b17eb")
def test_pg_create_tenant_returns_the_existing_row_on_conflict() -> None:
    existing = datetime(2025, 6, 7, 8, 9, 10)
    row = _tenant_row("acme", "First name", False, existing, existing)

    def responder(sql: str, params: Any) -> list[Any]:
        if "FROM tenants WHERE id = %s" in sql:
            return [row]
        return []

    conn = FakeConnection(responder=responder)
    backend = _backend(FakePool(conn))

    tenant = _create_tenant(backend, "acme", "Second name")

    assert tenant == Tenant(
        id="acme",
        name="First name",
        is_active=False,
        created_at=existing,
        updated_at=existing,
    )
    insert_sql = " ".join(conn.executed[0][0].split())
    assert "ON CONFLICT (id) DO NOTHING" in insert_sql


@pytest.mark.l4("C-c0d003ce", "C-be5b17eb", "C-1b7a83e9")
def test_pg_get_tenant_selects_and_maps_the_row() -> None:
    created = datetime(2026, 2, 3, 4, 5, 6)
    row = _tenant_row("t1", "Tenant one", True, created, created)

    def responder(sql: str, params: Any) -> list[Any]:
        if params == ("t1",):
            return [row]
        return []

    conn = FakeConnection(responder=responder)
    backend = _backend(FakePool(conn))

    tenant = backend.get_tenant("t1")

    assert tenant == Tenant(
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
def test_pg_list_tenants_reads_every_row_ordered_by_id() -> None:
    first = _tenant_row("alpha", "Alpha", True, datetime(2026, 1, 1), datetime(2026, 1, 1))
    second = _tenant_row("beta", "Beta", False, datetime(2026, 1, 2), datetime(2026, 1, 3))

    def responder(sql: str, params: Any) -> list[Any]:
        if "ORDER BY id" in sql:
            return [first, second]
        return []

    conn = FakeConnection(responder=responder)
    backend = _backend(FakePool(conn))

    tenants = backend.list_tenants()

    assert [tenant.id for tenant in tenants] == ["alpha", "beta"]
    assert tenants[0].name == "Alpha"
    assert tenants[0].is_active is True
    assert tenants[1].is_active is False
    assert tenants[1].updated_at == datetime(2026, 1, 3)
    select_sql, select_params = conn.executed[0]
    assert " ".join(select_sql.split()) == (
        "SELECT id, name, is_active, created_at, updated_at FROM tenants ORDER BY id"
    )
    assert select_params is None


@pytest.mark.l4("C-c0d003ce", "C-be5b17eb", "C-edb554ee")
def test_pg_set_tenant_active_updates_flag_and_returns_updated_row() -> None:
    created = datetime(2026, 1, 1, 8, 0, 0)
    state: dict[str, Any] = {"active": False, "updated": created}

    def responder(sql: str, params: Any) -> list[Any]:
        normalised = " ".join(sql.split())
        if normalised.startswith("UPDATE tenants"):
            state["active"] = bool(params[0])
            state["updated"] = params[1]
            return [_tenant_row("t1", "Acme", state["active"], created, state["updated"])]
        if "FROM tenants WHERE id = %s" in normalised:
            return [_tenant_row("t1", "Acme", state["active"], created, state["updated"])]
        return []

    conn = FakeConnection(responder=responder)
    backend = _backend(FakePool(conn))
    before = _naive_utc()

    tenant = _set_tenant_active(backend, "t1", True)

    after = _naive_utc()
    assert tenant.is_active is True
    assert tenant.created_at == created
    assert tenant.updated_at.tzinfo is None
    assert before <= tenant.updated_at <= after
    update = next(
        (sql, params) for sql, params in conn.executed if sql.lstrip().startswith("UPDATE tenants")
    )
    update_sql = " ".join(update[0].split())
    assert update_sql == "UPDATE tenants SET is_active = %s, updated_at = %s WHERE id = %s"
    active_param, updated_param, tenant_param = update[1]
    assert active_param is True
    assert tenant_param == "t1"
    assert isinstance(updated_param, datetime)
    assert updated_param.tzinfo is None
    assert before <= updated_param <= after


@pytest.mark.l4("C-c0d003ce", "C-3f98f2b5")
def test_pg_set_tenant_active_unknown_id_raises_not_found() -> None:
    conn = FakeConnection(responder=lambda sql, params: [])
    backend = _backend(FakePool(conn))

    with pytest.raises(TenantNotFoundError):
        _set_tenant_active(backend, "nope", False)

    assert not [sql for sql, _ in conn.executed if sql.lstrip().startswith("UPDATE tenants")]


@pytest.mark.l4("C-c0d003ce", "C-3f98f2b5", "C-edb554ee")
def test_pg_set_tenant_active_cannot_deactivate_global() -> None:
    created = datetime(2026, 1, 1)
    row = _tenant_row("global", "Global", True, created, created)
    conn = FakeConnection(responder=lambda sql, params: [row])
    backend = _backend(FakePool(conn))

    with pytest.raises(ProtectedTenantError):
        _set_tenant_active(backend, "global", False)

    assert not [sql for sql, _ in conn.executed if sql.lstrip().startswith("UPDATE tenants")]


@pytest.mark.l4("C-c0d003ce", "C-3f98f2b5")
def test_pg_set_tenant_active_global_true_returns_unchanged() -> None:
    created = datetime(2026, 1, 1)
    row = _tenant_row("global", "Global", True, created, created)
    conn = FakeConnection(responder=lambda sql, params: [row])
    backend = _backend(FakePool(conn))

    tenant = _set_tenant_active(backend, "global", True)

    assert tenant == Tenant(
        id="global",
        name="Global",
        is_active=True,
        created_at=created,
        updated_at=created,
    )
    assert not [sql for sql, _ in conn.executed if sql.lstrip().startswith("UPDATE tenants")]


@pytest.mark.l4("C-f55a34a6", "C-3f98f2b5")
def test_pg_create_tenant_validates_the_id_before_any_sql() -> None:
    conn = FakeConnection()
    backend = _backend(FakePool(conn))

    try:
        _create_tenant(backend, "Bad")
    except InvalidTenantIdError:
        pass
    else:
        pytest.fail("create_tenant must reject an invalid tenant id")

    assert conn.executed == [], "the id is validated before any SQL statement"


@pytest.mark.l4("C-edb554ee", "C-c0d003ce")
def test_pg_tenant_directory_has_no_synthetic_global() -> None:
    created = datetime(2026, 3, 4, 5, 6, 7)
    row = _tenant_row("t1", "Tenant one", True, created, created)

    def responder(sql: str, params: Any) -> list[Any]:
        normalised = " ".join(sql.split())
        if "ORDER BY id" in normalised:
            return [row]
        if params == ("t1",):
            return [row]
        return []

    conn = FakeConnection(responder=responder)
    backend = _backend(FakePool(conn))

    assert backend.get_tenant("global") is None, "the synthetic global tenant is gone"
    assert backend.get_tenant("t1") == Tenant(
        id="t1",
        name="Tenant one",
        is_active=True,
        created_at=created,
        updated_at=created,
    )
    assert backend.list_tenants() == [
        Tenant(
            id="t1",
            name="Tenant one",
            is_active=True,
            created_at=created,
            updated_at=created,
        )
    ]


# ---------------------------------------------------------------------------
# Task 3 — the write guard (R2.1-R2.4, R5.1, R5.3, R5.6)
# ---------------------------------------------------------------------------

_GUARDED_WRITES: tuple[str, ...] = (
    "add_memory",
    "update_memory",
    "archive_memory",
    "supersede_memory",
    "apply_feedback",
    "add_link",
    "create_session",
    "record_query_results",
    "update_session_feedback",
    "mark_session_concluded",
    "upsert_summary",
    "manifest_upsert",
    "manifest_delete",
)

_WRITE_PREFIXES: tuple[str, ...] = ("INSERT", "UPDATE", "DELETE")


def _memory_row(memory_id: str, tenant_id: str) -> dict[str, Any]:
    stamp = datetime(2026, 1, 1)
    return {
        "id": memory_id,
        "content": f"content {memory_id}",
        "category": "fact",
        "entity_ids": [],
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


def _session_row(session_id: str, tenant_id: str) -> dict[str, Any]:
    return {
        "id": session_id,
        "query_text": "who?",
        "created_at": datetime(2026, 1, 1),
        "confidence_rating": None,
        "reasoning": None,
        "useful_ids": [],
        "stale_ids": [],
        "concluded": False,
        "tenant_id": tenant_id,
    }


def _summary_row(summary_id: str, concept: str, tenant_id: str) -> dict[str, Any]:
    return {
        "id": summary_id,
        "concept": concept,
        "summary_text": "summary",
        "memory_count": 1,
        "is_current": True,
        "generated_at": datetime(2026, 1, 1),
        "tenant_id": tenant_id,
    }


def _guard_responder(guard_rows: list[Any]) -> Callable[[str, Any], list[Any]]:
    """Answer the guard with *guard_rows* and every other lookup with tenant t1."""

    def responder(sql: str, params: Any) -> list[Any]:
        normalised = " ".join(sql.split())
        if normalised.startswith("SELECT is_active FROM tenants"):
            return guard_rows
        if normalised.startswith("SELECT tenant_id FROM memories WHERE id = %s"):
            return [{"tenant_id": "t1"}]
        if "FROM memories WHERE id = %s" in normalised:
            return [_memory_row(str(params[0]), "t1")]
        if normalised.startswith("SELECT tenant_id FROM query_sessions WHERE id = %s"):
            return [{"tenant_id": "t1"}]
        if "FROM query_sessions WHERE id = %s" in normalised:
            return [_session_row(str(params[0]), "t1")]
        if "FROM memory_summaries" in normalised:
            return [_summary_row("summary-1", "acme", "t1")]
        return []

    return responder


def _write_calls(backend: PostgresBackend) -> dict[str, Callable[[], object]]:
    record = MemoryRecord(content="guarded fact", category=MemoryCategory.FACT, tenant_id="t1")
    link = ConceptLink(
        source_memory_id="a1",
        target_memory_id="a2",
        link_type=ConceptLinkType.RELATES_TO,
        tenant_id="t1",
    )
    session = QuerySession(query_text="who?", tenant_id="t1")
    result = QueryResult(session_id="s1", memory_id="a1", relevance_score=1.0, tenant_id="t1")
    summary = MemorySummary(concept="acme", summary_text="summary", memory_count=1, tenant_id="t1")
    return {
        "add_memory": lambda: backend.add_memory(record),
        "update_memory": lambda: backend.update_memory("a1", content="changed"),
        "archive_memory": lambda: backend.archive_memory("a1", tenant_id="t1"),
        "supersede_memory": lambda: backend.supersede_memory("a1", "a2", tenant_id="t1"),
        "apply_feedback": lambda: backend.apply_feedback("a1", True, False, tenant_id="t1"),
        "add_link": lambda: backend.add_link(link),
        "create_session": lambda: backend.create_session(session),
        "record_query_results": lambda: backend.record_query_results([result]),
        "update_session_feedback": lambda: backend.update_session_feedback("s1", 5, "r", [], []),
        "mark_session_concluded": lambda: backend.mark_session_concluded("s1"),
        "upsert_summary": lambda: backend.upsert_summary(summary),
        "manifest_upsert": lambda: backend.manifest_upsert(
            "/a",
            "default",
            size=1,
            mtime=0.0,
            online_only=False,
            index_mode="content",
            memory_ids=[],
            tenant_id="t1",
        ),
        "manifest_delete": lambda: backend.manifest_delete("/a", tenant_id="t1"),
    }


def _guard_index(conn: FakeConnection) -> int:
    for index, (sql, _params) in enumerate(conn.executed):
        if sql.lstrip().startswith("SELECT is_active FROM tenants"):
            return index
    raise AssertionError("the write never ran the tenant guard")


def _writes_after_guard(conn: FakeConnection, guard_at: int) -> list[str]:
    return [
        sql
        for sql, _params in conn.executed[guard_at + 1 :]
        if sql.lstrip().upper().startswith(_WRITE_PREFIXES)
    ]


def _run_write(call: Callable[[], object]) -> None:
    """Run a write, turning the interim stub into a plain assertion failure."""
    try:
        call()
    except TenancyNotSupportedError as exc:
        pytest.fail(f"the write must replace the interim stub: {exc}")


@pytest.mark.l4("C-9e1dc670", "C-4f87b6ae", "C-15dbdabf")
@pytest.mark.parametrize("method", _GUARDED_WRITES)
def test_pg_guarded_write_missing_tenant_writes_nothing(method: str) -> None:
    conn = FakeConnection(responder=_guard_responder([]))
    backend = _backend(FakePool(conn))

    with pytest.raises(TenantNotFoundError):
        _run_write(_write_calls(backend)[method])

    guard_at = _guard_index(conn)
    assert _writes_after_guard(conn, guard_at) == []


@pytest.mark.l4("C-9e1dc670", "C-4f87b6ae", "C-15dbdabf")
@pytest.mark.parametrize("method", _GUARDED_WRITES)
def test_pg_guarded_write_inactive_tenant_writes_nothing(method: str) -> None:
    conn = FakeConnection(responder=_guard_responder([{"is_active": False}]))
    backend = _backend(FakePool(conn))

    with pytest.raises(TenantInactiveError):
        _run_write(_write_calls(backend)[method])

    guard_at = _guard_index(conn)
    assert _writes_after_guard(conn, guard_at) == []


@pytest.mark.l4("C-9e1dc670")
def test_pg_assert_tenant_writable_selects_on_the_given_connection() -> None:
    missing = FakeConnection(responder=lambda sql, params: [])
    backend = PostgresBackend("postgresql://unused")

    with pytest.raises(TenantNotFoundError) as missing_error:
        backend._assert_tenant_writable(missing, "nope")
    assert missing_error.value.tenant_id == "nope"
    assert [(" ".join(sql.split()), params) for sql, params in missing.executed] == [
        ("SELECT is_active FROM tenants WHERE id = %s", ("nope",))
    ]

    inactive = FakeConnection(responder=lambda sql, params: [{"is_active": False}])
    with pytest.raises(TenantInactiveError) as inactive_error:
        backend._assert_tenant_writable(inactive, "t1")
    assert inactive_error.value.tenant_id == "t1"
    assert [(" ".join(sql.split()), params) for sql, params in inactive.executed] == [
        ("SELECT is_active FROM tenants WHERE id = %s", ("t1",))
    ]


@pytest.mark.l4("C-d09bf668")
def test_pg_write_lookup_helpers_read_single_column_rows() -> None:
    def responder(sql: str, params: Any) -> list[Any]:
        normalised = " ".join(sql.split())
        if normalised == "SELECT tenant_id FROM memories WHERE id = %s":
            return [{"tenant_id": "t1"}] if params == ("a1",) else []
        if normalised == "SELECT tenant_id FROM query_sessions WHERE id = %s":
            return [{"tenant_id": "t1"}] if params == ("s1",) else []
        if normalised == "SELECT id FROM memory_summaries WHERE tenant_id = %s AND concept = %s":
            return [{"id": "summary-1"}] if params == ("t1", "acme") else []
        return []

    conn = FakeConnection(responder=responder)
    backend = PostgresBackend("postgresql://unused")

    assert backend._stored_tenant(conn, "a1") == "t1"
    assert backend._stored_tenant(conn, "missing") is None
    assert backend._session_tenant(conn, "s1") == "t1"
    assert backend._session_tenant(conn, "missing") is None
    assert backend._summary_id(conn, "t1", "acme") == "summary-1"
    assert backend._summary_id(conn, "t1", "missing") is None


@pytest.mark.l4("C-f0e033f2", "C-4f87b6ae")
def test_pg_tenant_deactivated_after_the_guard_still_writes() -> None:
    state = {"active": True}

    def responder(sql: str, params: Any) -> list[Any]:
        if sql.lstrip().startswith("SELECT is_active FROM tenants"):
            answer = [{"is_active": state["active"]}]
            state["active"] = False
            return answer
        return []

    conn = FakeConnection(responder=responder)
    backend = _backend(FakePool(conn))

    _run_write(lambda: backend.add_memory(_record("written after deactivation")))

    assert state["active"] is False
    assert any(sql.lstrip().startswith("INSERT INTO memories") for sql, _params in conn.executed)
    assert conn.commits == 1


@pytest.mark.l4("C-98cd17f1")
def test_pg_bump_retrieval_only_updates_active_tenants() -> None:
    conn = FakeConnection()
    backend = _backend(FakePool(conn))
    now = datetime(2026, 4, 5, 6, 7, 8)

    backend._bump_retrieval(["a1"], now)

    update_sql, update_params = next(
        (sql, params)
        for sql, params in conn.executed
        if sql.lstrip().startswith("UPDATE memories SET retrieval_count")
    )
    assert "tenant_id IN (SELECT id FROM tenants WHERE is_active)" in " ".join(update_sql.split())
    assert update_params == [now, "a1"]


@pytest.mark.l4("C-d07310eb", "C-1b7a83e9")
@pytest.mark.parametrize(
    ("method", "table"),
    (
        ("add_memory", "memories"),
        ("add_link", "concept_links"),
        ("upsert_summary", "memory_summaries"),
        ("manifest_upsert", "index_manifest"),
    ),
)
def test_pg_active_tenant_write_inserts_t1_and_commits_once(method: str, table: str) -> None:
    conn = FakeConnection(responder=_guard_responder([{"is_active": True}]))
    backend = _backend(FakePool(conn))

    _run_write(_write_calls(backend)[method])

    insert_sql, insert_params = next(
        (sql, params)
        for sql, params in conn.executed
        if sql.lstrip().upper().startswith(f"INSERT INTO {table.upper()}")
    )
    assert "t1" in insert_params, insert_sql
    assert conn.commits == 1
