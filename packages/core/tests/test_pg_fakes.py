"""Self-tests for the Postgres test seam (``pg_fakes``).

Every test here traces R5.1: the fake connection records statements and
commits/rollbacks, the fake cursor reads responder rows exactly as the backend
does, and the fake pool yields one connection per checkout.
"""

from __future__ import annotations

import pytest

from packages.core.tests.pg_fakes import FakeConnection, FakeCursor, FakePool

_CRITERION = "C-0a8c52fb"


@pytest.mark.l4(_CRITERION)
def test_fake_connection_execute_records_sql_and_params_and_returns_cursor() -> None:
    conn = FakeConnection()

    cursor = conn.execute("SELECT * FROM memories WHERE id = %s", ("m1",))

    assert isinstance(cursor, FakeCursor)
    assert conn.executed == [("SELECT * FROM memories WHERE id = %s", ("m1",))]


@pytest.mark.l4(_CRITERION)
def test_fake_connection_default_responder_returns_no_rows_and_armed_responder_does() -> None:
    default = FakeConnection()
    assert default.execute("SELECT id FROM memories").fetchall() == []

    rows = [{"id": "m1"}, {"id": "m2"}]
    armed = FakeConnection(responder=lambda sql, params: rows)
    assert armed.execute("SELECT id FROM memories").fetchall() == rows


@pytest.mark.l4(_CRITERION)
def test_fake_connection_responder_rows_are_read_exactly_as_the_backend_reads_them() -> None:
    dict_rows = [{"table_name": "memories", "columns": ["id"]}]
    conn = FakeConnection(responder=lambda sql, params: dict_rows)
    cursor = conn.cursor(row_factory=object())
    cursor.execute("SELECT table_name, columns FROM information_schema.columns")

    assert cursor.fetchall() == dict_rows

    tuple_conn = FakeConnection(responder=lambda sql, params: [(7,)])
    first_row = tuple_conn.execute("SELECT count(*) FROM memories").fetchone()
    assert first_row is not None
    assert first_row[0] == 7


@pytest.mark.l4(_CRITERION)
def test_fake_connection_counts_commits_and_rollbacks() -> None:
    conn = FakeConnection()

    conn.commit()
    conn.commit()
    conn.rollback()

    assert conn.commits == 2
    assert conn.rollbacks == 1


@pytest.mark.l4(_CRITERION)
def test_fake_connection_fail_on_raises_after_recording_the_statement() -> None:
    sql = "ALTER TABLE memories ADD COLUMN tenant_id TEXT"
    conn = FakeConnection(fail_on=lambda statement: statement.startswith("ALTER TABLE memories"))

    raised: str | None = None
    try:
        conn.execute(sql)
    except RuntimeError as exc:
        raised = str(exc)

    assert raised == f"fake failure: {sql}"
    assert conn.executed == [(sql, None)]


@pytest.mark.l4(_CRITERION)
def test_fake_cursor_execute_records_in_owning_connection_and_ignores_row_factory() -> None:
    rows = [("x", "y")]
    conn = FakeConnection(responder=lambda sql, params: rows)
    cursor = conn.cursor(row_factory=object())

    cursor.execute("SELECT 1")

    assert conn.executed == [("SELECT 1", None)]
    assert cursor.fetchall() == rows


@pytest.mark.l4(_CRITERION)
def test_fake_cursor_executemany_records_one_entry_per_parameter_set() -> None:
    conn = FakeConnection()
    cursor = conn.cursor()
    sql = "INSERT INTO memories (id) VALUES (%s)"

    cursor.executemany(sql, [("a",), ("b",), ("c",)])

    assert conn.executed == [(sql, ("a",)), (sql, ("b",)), (sql, ("c",))]


@pytest.mark.l4(_CRITERION)
def test_fake_cursor_reads_rows_and_is_a_context_manager() -> None:
    rows = [{"n": 1}, {"n": 2}]
    conn = FakeConnection(responder=lambda sql, params: rows)

    with conn.execute("SELECT n FROM numbers") as cursor:
        assert cursor.fetchone() == {"n": 1}
        assert cursor.fetchall() == [{"n": 2}]
        assert cursor.rowcount == 2

    assert FakeConnection().execute("SELECT n FROM numbers").fetchone() is None


@pytest.mark.l4(_CRITERION)
def test_fake_pool_yields_given_connection_and_counts_checkouts() -> None:
    conn = FakeConnection()
    pool = FakePool(conn)

    with pool.connection() as yielded:
        assert yielded is conn
    with pool.connection() as yielded_again:
        assert yielded_again is conn

    assert pool.connections == [conn, conn]
    assert pool.checkouts == 2
    assert conn.rollbacks == 0


@pytest.mark.l4(_CRITERION)
def test_fake_pool_factory_makes_a_new_connection_per_checkout() -> None:
    first = FakeConnection()
    second = FakeConnection()
    pending = [first, second]
    pool = FakePool(lambda: pending.pop(0))

    with pool.connection() as yielded_first:
        assert yielded_first is first
    with pool.connection() as yielded_second:
        assert yielded_second is second

    assert first is not second
    assert pool.connections == [first, second]
    assert pool.checkouts == 2


@pytest.mark.l4(_CRITERION)
def test_fake_pool_rolls_back_and_reraises_on_exception() -> None:
    conn = FakeConnection()
    pool = FakePool(conn)

    raised: str | None = None
    try:
        with pool.connection():
            raise ValueError("boom")
    except ValueError as exc:
        raised = str(exc)

    assert raised == "boom"
    assert conn.rollbacks == 1
    assert conn.commits == 0
    assert pool.checkouts == 1


@pytest.mark.l4(_CRITERION)
def test_fake_pool_close_does_nothing_and_the_pool_still_yields() -> None:
    conn = FakeConnection()
    pool = FakePool(conn)

    pool.close()

    with pool.connection() as yielded:
        assert yielded is conn
    assert pool.checkouts == 1
