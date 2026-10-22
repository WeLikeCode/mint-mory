"""Test doubles for the Postgres backend.

FakeConnection records every executed statement with its parameters and
serves the rows its responder returns; FakePool yields one connection per
checkout and rolls it back when the body raises.  See requirement 5.1; the
later Postgres units reuse this seam.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any


def _no_rows(sql: str, params: Any) -> list[Any]:
    return []


class FakeCursor:
    """Fake psycopg cursor whose rows come from the owning connection."""

    def __init__(self, connection: FakeConnection | None = None, row_factory: Any = None) -> None:
        self.connection = connection
        self.row_factory = row_factory
        self.rowcount = 0
        self._rows: list[Any] = []
        self._position = 0

    def execute(self, sql: str, params: Any = None) -> FakeCursor:
        if self.connection is not None:
            self.connection.executed.append((sql, params))
            fail_on = self.connection.fail_on
            if fail_on is not None and fail_on(sql):
                raise RuntimeError(f"fake failure: {sql}")
            self._load(list(self.connection.responder(sql, params)))
        return self

    def executemany(self, sql: str, params_seq: Any) -> None:
        if self.connection is not None:
            fail_on = self.connection.fail_on
            for params in params_seq:
                self.connection.executed.append((sql, params))
                if fail_on is not None and fail_on(sql):
                    raise RuntimeError(f"fake failure: {sql}")
        return None

    def fetchone(self) -> Any:
        if self._position >= len(self._rows):
            return None
        row = self._rows[self._position]
        self._position += 1
        return row

    def fetchall(self) -> list[Any]:
        rows = list(self._rows[self._position :])
        self._position = len(self._rows)
        return rows

    def _load(self, rows: list[Any]) -> None:
        self._rows = rows
        self._position = 0
        self.rowcount = len(rows)

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeConnection:
    """Fake psycopg connection recording every statement and transaction step."""

    def __init__(
        self,
        responder: Callable[[str, Any], list[Any]] | None = None,
        fail_on: Callable[[str], bool] | None = None,
    ) -> None:
        self.responder = responder if responder is not None else _no_rows
        self.fail_on = fail_on
        self.executed: list[tuple[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql: str, params: Any = None) -> FakeCursor:
        cursor = self.cursor()
        cursor.execute(sql, params)
        return cursor

    def cursor(self, row_factory: Any = None) -> FakeCursor:
        return FakeCursor(self, row_factory)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakePool:
    """Fake psycopg pool handing out a fixed connection or factory-made ones."""

    def __init__(self, source: FakeConnection | Callable[[], FakeConnection]) -> None:
        self.source = source
        self.connections: list[FakeConnection] = []
        self.checkouts = 0

    @contextmanager
    def connection(self) -> Iterator[FakeConnection]:
        conn = self.source if isinstance(self.source, FakeConnection) else self.source()
        self.connections.append(conn)
        self.checkouts += 1
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise

    def close(self) -> None:
        return None
