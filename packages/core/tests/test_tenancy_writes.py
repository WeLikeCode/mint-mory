"""RED tests for task 1 — the re-entrant ``transaction()``.

They trace requirement 4.1 (``SqliteBackend.transaction`` counts nesting depth
through ``_tx_depth`` and guards writers with a re-entrant ``_tx_lock``),
4.2 (public writes composed inside one outermost block persist together or,
on an exception, not at all — including their FTS5/trigram index rows),
4.3 (a second thread's write waits until the first thread's outermost block
ends) and 4.4 / 4.5 (``StorageBackend`` declares ``transaction()`` and the
ports docstring excludes only ``connect()``; the Postgres interim raises
``TenancyNotSupportedError`` before touching the pool — asserted through the
docstring test tagged with both criterion ids here and through
``test_pg_transaction_tenancy`` in ``test_pg_tenancy.py``).
"""

from __future__ import annotations

import inspect
import threading
from pathlib import Path

import pytest
from mintmory.core import ports
from mintmory.core.ports import StorageBackend
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    MemoryCategory,
    MemoryRecord,
)


def _count(peek: SqliteBackend, table: str) -> int:
    conn = peek.connect()
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    assert row is not None
    return int(row[0])


# ---------------------------------------------------------------------------
# Requirement 4.1 — depth counting and the re-entrant lock
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-7ea843d6")
def test_transaction_outermost_sets_depth_and_locks_reentrantly(
    dbs: tuple[SqliteBackend, SqliteBackend],
) -> None:
    store, _ = dbs
    lock = getattr(store, "_tx_lock", None)
    assert lock is not None, "SqliteBackend.__init__ must create _tx_lock"
    assert lock.acquire(blocking=False)
    assert lock.acquire(blocking=False), "the transaction lock must be re-entrant"
    lock.release()
    lock.release()

    with store.transaction():
        assert getattr(store, "_tx_depth", None) == 1
        with store.transaction():
            assert getattr(store, "_tx_depth", None) == 2
        assert getattr(store, "_tx_depth", None) == 1


@pytest.mark.l4("C-7ea843d6", "C-95cabe80")
def test_nested_transactions_commit_once(dbs: tuple[SqliteBackend, SqliteBackend]) -> None:
    store, peek = dbs
    with store.transaction():
        with store.transaction():
            store.add_memory(MemoryRecord(content="parking rules", category=MemoryCategory.FACT))
        assert _count(peek, "memories") == 0, "a nested exit must not commit"
    assert _count(peek, "memories") == 1


# ---------------------------------------------------------------------------
# Requirement 4.2 — public writes compose into one atomic unit
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-95cabe80")
def test_composed_writes_roll_back_together(dbs: tuple[SqliteBackend, SqliteBackend]) -> None:
    store, peek = dbs
    with pytest.raises(RuntimeError), store.transaction():
        first = store.add_memory(
            MemoryRecord(content="tower parking rules", category=MemoryCategory.FACT)
        )
        second = store.add_memory(
            MemoryRecord(content="firewall maintenance", category=MemoryCategory.FACT)
        )
        store.add_link(
            ConceptLink(
                source_memory_id=first.id,
                target_memory_id=second.id,
                link_type=ConceptLinkType.RELATES_TO,
            )
        )
        raise RuntimeError("compose rolls back")

    assert _count(peek, "memories") == 0
    assert _count(peek, "concept_links") == 0
    conn = peek.connect()
    fts_hits = conn.execute(
        "SELECT COUNT(*) FROM memories_fts WHERE memories_fts MATCH 'tower'"
    ).fetchone()
    assert fts_hits is not None
    assert int(fts_hits[0]) == 0
    trigram = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memories_trigram'"
    ).fetchone()
    if trigram is not None:
        trigram_hits = conn.execute(
            "SELECT COUNT(*) FROM memories_trigram WHERE memories_trigram MATCH 'wall'"
        ).fetchone()
        assert trigram_hits is not None
        assert int(trigram_hits[0]) == 0


@pytest.mark.l4("C-95cabe80")
def test_nested_exception_caught_inside_outer_commits_survivors(
    dbs: tuple[SqliteBackend, SqliteBackend],
) -> None:
    store, peek = dbs
    with store.transaction():
        store.add_memory(MemoryRecord(content="first fact", category=MemoryCategory.FACT))
        try:
            with store.transaction():
                store.add_memory(MemoryRecord(content="nested fact", category=MemoryCategory.FACT))
                raise RuntimeError("handled by the outer composition")
        except RuntimeError:
            pass
        store.add_memory(MemoryRecord(content="third fact", category=MemoryCategory.FACT))
        assert _count(peek, "memories") == 0, "the outer block must not commit mid-flight"
    assert _count(peek, "memories") == 3


# ---------------------------------------------------------------------------
# Requirement 4.3 — a second thread waits for the outermost transaction
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-7b243e91")
def test_second_thread_waits_for_outermost_transaction(
    dbs: tuple[SqliteBackend, SqliteBackend],
) -> None:
    store, peek = dbs
    hold = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    errors: list[BaseException] = []

    def holder() -> None:
        try:
            with store.transaction():
                hold.set()
                release.wait(10)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    def writer() -> None:
        try:
            store.add_memory(MemoryRecord(content="late write", category=MemoryCategory.FACT))
            finished.set()
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    first = threading.Thread(target=holder)
    first.start()
    assert hold.wait(5), "the first thread never entered its transaction"
    second = threading.Thread(target=writer)
    second.start()

    finished.wait(2)  # completes at once today; only the lock keeps it until release
    assert _count(peek, "memories") == 0, (
        "the second thread's write must wait for the first thread's outermost transaction"
    )

    release.set()
    assert finished.wait(5), "the second thread's write did not complete within 5 s"
    assert _count(peek, "memories") == 1
    first.join(5)
    second.join(5)
    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []


# ---------------------------------------------------------------------------
# Requirement 4.4 (+ 4.5) — the Protocol and the ports docstring
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2ae7611a")
def test_protocol_declares_transaction_context_manager() -> None:
    assert hasattr(StorageBackend, "transaction"), "StorageBackend must declare transaction()"
    signature = inspect.signature(StorageBackend.transaction)
    assert list(signature.parameters) == ["self"]
    assert "AbstractContextManager" in str(signature.return_annotation)
    method_doc = inspect.getdoc(StorageBackend.transaction) or ""
    assert "must not" in method_doc.lower(), "Protocol callers must not use the yielded value"


def _excluded_note(doc: str) -> str:
    start = doc.find("excluded from the Protocol")
    assert start != -1, "the ports module docstring must keep the exclusion note"
    tail = doc[start:]
    end = tail.find("\n\n")
    return tail if end == -1 else tail[:end]


@pytest.mark.l4("C-2ae7611a", "C-74b68113")
def test_ports_docstring_excludes_only_connect_from_the_protocol() -> None:
    note = _excluded_note(inspect.getdoc(ports) or "")
    assert "connect()" in note, "connect() stays SQLite-only"
    assert "transaction" not in note, "transaction() moved onto the Protocol"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dbs(tmp_path: Path) -> tuple[SqliteBackend, SqliteBackend]:
    path = tmp_path / "mintmory.db"
    store = SqliteBackend(path)
    store.initialise()
    peek = SqliteBackend(path)
    peek.connect()
    return store, peek
