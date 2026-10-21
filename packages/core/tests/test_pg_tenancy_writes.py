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
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import pytest
from mintmory.core.storage_postgres import PostgresBackend
from mintmory.core.types import (
    MemoryCategory,
    MemoryRecord,
    SearchRequest,
    TenancyNotSupportedError,
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
