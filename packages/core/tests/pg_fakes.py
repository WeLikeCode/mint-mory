"""Test doubles for the Postgres backend.

RED-step stubs: this module exposes the R5.1 surface, but every operation
records nothing and returns the zero value.  The real fakes arrive with the
green step.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any


class FakeCursor:
    """Zero-value stub of a psycopg cursor."""

    def __init__(self, connection: FakeConnection | None = None, row_factory: Any = None) -> None:
        self.connection = connection
        self.row_factory = row_factory

    def execute(self, sql: str, params: Any = None) -> None:
        return None

    def executemany(self, sql: str, params_seq: Any) -> None:
        return None

    def fetchone(self) -> Any:
        return None

    def fetchall(self) -> list[Any]:
        return []

    @property
    def rowcount(self) -> int:
        return 0

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeConnection:
    """Zero-value stub of a psycopg connection."""

    def __init__(
        self,
        responder: Callable[[str, Any], list[Any]] | None = None,
        fail_on: Callable[[str], bool] | None = None,
    ) -> None:
        self.responder = responder
        self.fail_on = fail_on
        self.executed: list[tuple[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql: str, params: Any = None) -> FakeCursor:
        return FakeCursor(self)

    def cursor(self, row_factory: Any = None) -> FakeCursor:
        return FakeCursor(self, row_factory)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class FakePool:
    """Zero-value stub of a psycopg connection pool."""

    def __init__(self, source: FakeConnection | Callable[[], FakeConnection]) -> None:
        self.source = source
        self.connections: list[FakeConnection] = []
        self.checkouts = 0

    @contextmanager
    def connection(self) -> Iterator[Any]:
        yield None

    def close(self) -> None:
        return None
