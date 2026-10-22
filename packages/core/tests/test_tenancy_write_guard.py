"""RED tests for task 2 — the SQLite write guard (requirement 1).

They trace requirement 1.1 (``_assert_tenant_writable`` accepts an active
tenant and raises ``TenantNotFoundError`` / ``TenantInactiveError``), 1.2 (every
public write calls the guard for the tenant of the row/argument it writes,
before writing anything), 1.3 (the guard rejects a missing/inactive tenant on a
fresh database and on one migrated from ``pre_tenancy_schema.sql``, where the
``memories`` table has no tenant foreign key), 1.4 (``_bump_retrieval`` only
bumps active tenants), 1.5 (reads stay unguarded), 1.6 (guard and write share
one locked transaction) and 1.7 (existence/guard-before-SQL ordering).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    MemoryCategory,
    MemoryRecord,
    MemorySummary,
    QueryResult,
    QuerySession,
    TenantInactiveError,
    TenantNotFoundError,
)
from pydantic import ValidationError

PRE_TENANCY_SCHEMA = Path(__file__).parent / "fixtures" / "pre_tenancy_schema.sql"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count(store: SqliteBackend, table: str) -> int:
    row = store.connect().execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    assert row is not None
    return int(row[0])


def _create_tenant(store: SqliteBackend, tenant_id: str, *, active: bool = True) -> None:
    store.create_tenant(tenant_id)
    if not active:
        store.set_tenant_active(tenant_id, False)


def _add_memory(
    store: SqliteBackend, tenant_id: str = "global", content: str = "a fact"
) -> MemoryRecord:
    return store.add_memory(
        MemoryRecord(content=content, category=MemoryCategory.FACT, tenant_id=tenant_id)
    )


def _insert_memory_row(
    store: SqliteBackend, memory_id: str, tenant_id: str, content: str = "raw fact"
) -> None:
    """Raw insert, bypassing the guard: the migrated schema has no tenant FK."""
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO memories (id, content, category, created_at, updated_at, tenant_id) "
            "VALUES (?, ?, 'fact', '2026-01-01T00:00:00', '2026-01-01T00:00:00', ?)",
            (memory_id, content, tenant_id),
        )


def _insert_session_row(store: SqliteBackend, session_id: str, tenant_id: str) -> None:
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO query_sessions (id, query_text, created_at, tenant_id) "
            "VALUES (?, 'raw query', '2026-01-01T00:00:00', ?)",
            (session_id, tenant_id),
        )


def _raised(call: Callable[[], object]) -> BaseException | None:
    """Run ``call`` and return whatever it raised (``None`` when it succeeded)."""
    try:
        call()
    except BaseException as exc:
        return exc
    return None


def _expect(exc: BaseException | None, kind: type[BaseException], tenant_id: str) -> None:
    assert isinstance(exc, kind), f"expected {kind.__name__}, got {exc!r}"
    assert getattr(exc, "tenant_id", None) == tenant_id


# ---------------------------------------------------------------------------
# Requirement 1.1 — _assert_tenant_writable
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-5419350d")
def test_assert_tenant_writable_accepts_active_tenants(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    conn = store.connect()

    assert _raised(lambda: store._assert_tenant_writable(conn, "global")) is None
    assert _raised(lambda: store._assert_tenant_writable(conn, "t1")) is None


@pytest.mark.l4("C-5419350d")
def test_assert_tenant_writable_rejects_missing_and_inactive(store: SqliteBackend) -> None:
    _create_tenant(store, "t1", active=False)
    conn = store.connect()

    with pytest.raises(TenantNotFoundError) as missing:
        store._assert_tenant_writable(conn, "nope")
    assert missing.value.tenant_id == "nope"

    with pytest.raises(TenantInactiveError) as inactive:
        store._assert_tenant_writable(conn, "t1")
    assert inactive.value.tenant_id == "t1"


# ---------------------------------------------------------------------------
# Requirement 1.2 + 1.3 — add_memory builds the record, then guards it
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2812d3f2", "C-0ff47353")
def test_add_memory_guard_from_record_rejects_inactive_and_missing(
    store: SqliteBackend,
) -> None:
    _create_tenant(store, "t1", active=False)
    before = _count(store, "memories")

    inactive = _raised(
        lambda: store.add_memory(
            MemoryRecord(content="blocked", category=MemoryCategory.FACT, tenant_id="t1")
        )
    )
    _expect(inactive, TenantInactiveError, "t1")
    assert _count(store, "memories") == before

    missing = _raised(
        lambda: store.add_memory(
            MemoryRecord(content="blocked", category=MemoryCategory.FACT, tenant_id="nope")
        )
    )
    _expect(missing, TenantNotFoundError, "nope")
    assert _count(store, "memories") == before


@pytest.mark.l4("C-2812d3f2")
def test_add_memory_builds_the_record_from_fields_before_guarding(
    store: SqliteBackend,
) -> None:
    _create_tenant(store, "t1", active=False)

    inactive = _raised(lambda: store.add_memory(content="blocked", category="fact", tenant_id="t1"))
    _expect(inactive, TenantInactiveError, "t1")

    with pytest.raises(ValidationError):
        store.add_memory(content="invalid", category="fact", tenant_id="Not Valid!")

    default = store.add_memory(content="allowed", category="fact")
    assert default.tenant_id == "global"


# ---------------------------------------------------------------------------
# Requirement 1.2 + 1.3 — migration from pre_tenancy_schema.sql
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-0ff47353", "C-2812d3f2")
def test_add_memory_guard_holds_on_a_migrated_database(
    legacy_store: SqliteBackend,
) -> None:
    _create_tenant(legacy_store, "t1", active=False)
    before = _count(legacy_store, "memories")

    inactive = _raised(
        lambda: legacy_store.add_memory(
            MemoryRecord(content="blocked", category=MemoryCategory.FACT, tenant_id="t1")
        )
    )
    _expect(inactive, TenantInactiveError, "t1")
    assert _count(legacy_store, "memories") == before

    missing = _raised(
        lambda: legacy_store.add_memory(
            MemoryRecord(content="blocked", category=MemoryCategory.FACT, tenant_id="nope")
        )
    )
    _expect(missing, TenantNotFoundError, "nope")
    assert _count(legacy_store, "memories") == before

    # The migrated memories table has no FK on tenant_id: this raw ghost row is
    # what proves the guard (not the FK) turned the two writes above away.
    _insert_memory_row(legacy_store, "raw-ghost", "ghost")
    assert legacy_store.get_memory("raw-ghost") is not None


# ---------------------------------------------------------------------------
# Requirement 1.2 — stored-row writes guard the stored tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2812d3f2")
def test_update_memory_rejects_inactive_stored_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    memory = _add_memory(store, "t1", content="original")
    store.set_tenant_active("t1", False)

    exc = _raised(lambda: store.update_memory(memory.id, content="changed"))
    _expect(exc, TenantInactiveError, "t1")

    fetched = store.get_memory(memory.id)
    assert fetched is not None
    assert fetched.content == "original"


@pytest.mark.l4("C-2812d3f2")
def test_update_memory_rejects_missing_stored_tenant(legacy_store: SqliteBackend) -> None:
    _insert_memory_row(legacy_store, "ghost-memory", "ghost", content="original")

    exc = _raised(lambda: legacy_store.update_memory("ghost-memory", content="changed"))
    _expect(exc, TenantNotFoundError, "ghost")

    fetched = legacy_store.get_memory("ghost-memory")
    assert fetched is not None
    assert fetched.content == "original"


@pytest.mark.l4("C-2812d3f2")
def test_archive_memory_rejects_inactive_stored_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    memory = _add_memory(store, "t1")
    store.set_tenant_active("t1", False)

    exc = _raised(lambda: store.archive_memory(memory.id))
    _expect(exc, TenantInactiveError, "t1")

    fetched = store.get_memory(memory.id)
    assert fetched is not None
    assert fetched.is_active is True
    assert fetched.is_archived is False


@pytest.mark.l4("C-2812d3f2")
def test_archive_memory_rejects_missing_stored_tenant(legacy_store: SqliteBackend) -> None:
    _insert_memory_row(legacy_store, "ghost-memory", "ghost")

    exc = _raised(lambda: legacy_store.archive_memory("ghost-memory"))
    _expect(exc, TenantNotFoundError, "ghost")

    fetched = legacy_store.get_memory("ghost-memory")
    assert fetched is not None
    assert fetched.is_active is True
    assert fetched.is_archived is False


@pytest.mark.l4("C-2812d3f2")
def test_supersede_memory_rejects_inactive_stored_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    old = _add_memory(store, "t1", content="old")
    new = _add_memory(store, "t1", content="new")
    store.set_tenant_active("t1", False)

    exc = _raised(lambda: store.supersede_memory(old.id, new.id))
    _expect(exc, TenantInactiveError, "t1")

    fetched = store.get_memory(old.id)
    assert fetched is not None
    assert fetched.is_active is True
    assert fetched.superseded_by is None


@pytest.mark.l4("C-2812d3f2")
def test_supersede_memory_rejects_missing_stored_tenant(legacy_store: SqliteBackend) -> None:
    _insert_memory_row(legacy_store, "ghost-old", "ghost")
    _insert_memory_row(legacy_store, "ghost-new", "ghost")

    exc = _raised(lambda: legacy_store.supersede_memory("ghost-old", "ghost-new"))
    _expect(exc, TenantNotFoundError, "ghost")

    fetched = legacy_store.get_memory("ghost-old")
    assert fetched is not None
    assert fetched.is_active is True
    assert fetched.superseded_by is None


@pytest.mark.l4("C-2812d3f2")
def test_apply_feedback_rejects_inactive_stored_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    memory = _add_memory(store, "t1")
    store.set_tenant_active("t1", False)

    exc = _raised(lambda: store.apply_feedback(memory.id, useful=True, stale=False))
    _expect(exc, TenantInactiveError, "t1")

    fetched = store.get_memory(memory.id)
    assert fetched is not None
    assert fetched.usefulness_score == 0.0
    assert fetched.reinforcement_count == 0


@pytest.mark.l4("C-2812d3f2")
def test_apply_feedback_rejects_missing_stored_tenant(legacy_store: SqliteBackend) -> None:
    _insert_memory_row(legacy_store, "ghost-memory", "ghost")

    exc = _raised(lambda: legacy_store.apply_feedback("ghost-memory", useful=True, stale=False))
    _expect(exc, TenantNotFoundError, "ghost")

    fetched = legacy_store.get_memory("ghost-memory")
    assert fetched is not None
    assert fetched.usefulness_score == 0.0
    assert fetched.reinforcement_count == 0


@pytest.mark.l4("C-2812d3f2")
def test_update_session_feedback_rejects_inactive_stored_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    session = QuerySession(query_text="q", tenant_id="t1")
    store.create_session(session)
    store.set_tenant_active("t1", False)

    exc = _raised(lambda: store.update_session_feedback(session.id, 5, "reason", [], []))
    _expect(exc, TenantInactiveError, "t1")

    fetched = store.get_session(session.id)
    assert fetched is not None
    assert fetched.confidence_rating is None
    assert fetched.concluded is False


@pytest.mark.l4("C-2812d3f2")
def test_update_session_feedback_rejects_missing_stored_tenant(
    legacy_store: SqliteBackend,
) -> None:
    _insert_session_row(legacy_store, "ghost-session", "ghost")

    exc = _raised(
        lambda: legacy_store.update_session_feedback("ghost-session", 5, "reason", [], [])
    )
    _expect(exc, TenantNotFoundError, "ghost")

    fetched = legacy_store.get_session("ghost-session")
    assert fetched is not None
    assert fetched.confidence_rating is None
    assert fetched.concluded is False


@pytest.mark.l4("C-2812d3f2")
def test_mark_session_concluded_rejects_inactive_stored_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    session = QuerySession(query_text="q", tenant_id="t1")
    store.create_session(session)
    store.set_tenant_active("t1", False)

    exc = _raised(lambda: store.mark_session_concluded(session.id))
    _expect(exc, TenantInactiveError, "t1")

    fetched = store.get_session(session.id)
    assert fetched is not None
    assert fetched.concluded is False


@pytest.mark.l4("C-2812d3f2")
def test_mark_session_concluded_rejects_missing_stored_tenant(
    legacy_store: SqliteBackend,
) -> None:
    _insert_session_row(legacy_store, "ghost-session", "ghost")

    exc = _raised(lambda: legacy_store.mark_session_concluded("ghost-session"))
    _expect(exc, TenantNotFoundError, "ghost")

    fetched = legacy_store.get_session("ghost-session")
    assert fetched is not None
    assert fetched.concluded is False


# ---------------------------------------------------------------------------
# Requirement 1.2 — writes guard the tenant carried by their argument/record
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2812d3f2")
def test_add_link_rejects_inactive_link_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    first = _add_memory(store, "t1", content="first")
    second = _add_memory(store, "t1", content="second")
    store.set_tenant_active("t1", False)
    before = _count(store, "concept_links")

    link = ConceptLink(
        source_memory_id=first.id,
        target_memory_id=second.id,
        link_type=ConceptLinkType.RELATES_TO,
        tenant_id="t1",
    )
    exc = _raised(lambda: store.add_link(link))
    _expect(exc, TenantInactiveError, "t1")
    assert _count(store, "concept_links") == before


@pytest.mark.l4("C-2812d3f2")
def test_add_link_rejects_missing_link_tenant(legacy_store: SqliteBackend) -> None:
    _insert_memory_row(legacy_store, "ghost-first", "ghost")
    _insert_memory_row(legacy_store, "ghost-second", "ghost")
    before = _count(legacy_store, "concept_links")

    link = ConceptLink(
        source_memory_id="ghost-first",
        target_memory_id="ghost-second",
        link_type=ConceptLinkType.RELATES_TO,
        tenant_id="ghost",
    )
    exc = _raised(lambda: legacy_store.add_link(link))
    _expect(exc, TenantNotFoundError, "ghost")
    assert _count(legacy_store, "concept_links") == before


@pytest.mark.l4("C-2812d3f2")
def test_create_session_rejects_inactive_and_missing_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1", active=False)
    before = _count(store, "query_sessions")

    inactive = _raised(lambda: store.create_session(QuerySession(query_text="q", tenant_id="t1")))
    _expect(inactive, TenantInactiveError, "t1")
    assert _count(store, "query_sessions") == before

    missing = _raised(lambda: store.create_session(QuerySession(query_text="q", tenant_id="nope")))
    _expect(missing, TenantNotFoundError, "nope")
    assert _count(store, "query_sessions") == before


@pytest.mark.l4("C-2812d3f2")
def test_record_query_results_rejects_inactive_result_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    memory = _add_memory(store, "t1")
    session = QuerySession(query_text="q", tenant_id="t1")
    store.create_session(session)
    store.set_tenant_active("t1", False)
    before = _count(store, "query_results")

    result = QueryResult(
        session_id=session.id,
        memory_id=memory.id,
        relevance_score=1.0,
        tenant_id="t1",
    )
    exc = _raised(lambda: store.record_query_results([result]))
    _expect(exc, TenantInactiveError, "t1")
    assert _count(store, "query_results") == before


@pytest.mark.l4("C-2812d3f2")
def test_record_query_results_rejects_missing_result_tenant(
    legacy_store: SqliteBackend,
) -> None:
    _insert_memory_row(legacy_store, "ghost-memory", "ghost")
    _insert_session_row(legacy_store, "ghost-session", "ghost")
    before = _count(legacy_store, "query_results")

    result = QueryResult(
        session_id="ghost-session",
        memory_id="ghost-memory",
        relevance_score=1.0,
        tenant_id="ghost",
    )
    exc = _raised(lambda: legacy_store.record_query_results([result]))
    _expect(exc, TenantNotFoundError, "ghost")
    assert _count(legacy_store, "query_results") == before


@pytest.mark.l4("C-2812d3f2")
def test_upsert_summary_rejects_inactive_and_missing_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1", active=False)
    before = _count(store, "memory_summaries")

    inactive = _raised(
        lambda: store.upsert_summary(
            MemorySummary(concept="concept", summary_text="text", memory_count=1, tenant_id="t1")
        )
    )
    _expect(inactive, TenantInactiveError, "t1")
    assert _count(store, "memory_summaries") == before

    missing = _raised(
        lambda: store.upsert_summary(
            MemorySummary(concept="concept", summary_text="text", memory_count=1, tenant_id="nope")
        )
    )
    _expect(missing, TenantNotFoundError, "nope")
    assert _count(store, "memory_summaries") == before


@pytest.mark.l4("C-2812d3f2")
def test_manifest_upsert_rejects_inactive_and_missing_tenant(store: SqliteBackend) -> None:
    _create_tenant(store, "t1", active=False)
    before = _count(store, "index_manifest")

    def upsert(tenant_id: str) -> None:
        store.manifest_upsert(
            "/notes/a.md",
            "notes",
            size=1,
            mtime=1.0,
            online_only=False,
            index_mode="metadata",
            memory_ids=[],
            tenant_id=tenant_id,
        )

    inactive = _raised(lambda: upsert("t1"))
    _expect(inactive, TenantInactiveError, "t1")
    assert _count(store, "index_manifest") == before

    missing = _raised(lambda: upsert("nope"))
    _expect(missing, TenantNotFoundError, "nope")
    assert _count(store, "index_manifest") == before


@pytest.mark.l4("C-2812d3f2")
def test_manifest_delete_rejects_inactive_tenant_without_deleting(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    store.manifest_upsert(
        "/notes/a.md",
        "notes",
        size=1,
        mtime=1.0,
        online_only=False,
        index_mode="metadata",
        memory_ids=[],
        tenant_id="t1",
    )
    store.set_tenant_active("t1", False)
    before = _count(store, "index_manifest")

    exc = _raised(lambda: store.manifest_delete("/notes/a.md", tenant_id="t1"))
    _expect(exc, TenantInactiveError, "t1")
    assert _count(store, "index_manifest") == before


@pytest.mark.l4("C-2812d3f2")
def test_manifest_delete_rejects_missing_tenant(store: SqliteBackend) -> None:
    exc = _raised(lambda: store.manifest_delete("/notes/a.md", tenant_id="nope"))
    _expect(exc, TenantNotFoundError, "nope")


# ---------------------------------------------------------------------------
# Requirement 1.4 — _bump_retrieval only touches active tenants
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-16655ef4")
def test_bump_retrieval_skips_inactive_tenant_rows(store: SqliteBackend) -> None:
    _create_tenant(store, "active")
    _create_tenant(store, "inactive")
    active = _add_memory(store, "active", content="active row")
    inactive = _add_memory(store, "inactive", content="inactive row")
    store.set_tenant_active("inactive", False)

    store._bump_retrieval([active.id, inactive.id], datetime(2026, 1, 1, 12, 0, 0))

    bumped = store.get_memory(active.id)
    skipped = store.get_memory(inactive.id)
    assert bumped is not None
    assert skipped is not None
    assert bumped.retrieval_count == 1
    assert skipped.retrieval_count == 0
    assert skipped.last_accessed_at is None


# ---------------------------------------------------------------------------
# Requirement 1.5 — reads of an inactive tenant stay unguarded
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-eded8e54", "C-0ff47353")
def test_reads_of_inactive_tenant_rows_are_not_guarded(store: SqliteBackend) -> None:
    _create_tenant(store, "t1")
    memory = _add_memory(store, "t1", content="read me")
    store.set_tenant_active("t1", False)

    fetched = store.get_memory(memory.id)
    assert fetched is not None
    assert fetched.content == "read me"

    blocked = _raised(
        lambda: store.add_memory(
            MemoryRecord(content="blocked", category=MemoryCategory.FACT, tenant_id="t1")
        )
    )
    _expect(blocked, TenantInactiveError, "t1")


# ---------------------------------------------------------------------------
# Requirement 1.6 — guard and write share one locked transaction
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-1d1a6032")
def test_guard_and_write_share_one_locked_transaction(
    store: SqliteBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_tenant(store, "t1")
    first = _add_memory(store, "t1", content="first")
    second = _add_memory(store, "t1", content="second")
    link = ConceptLink(
        source_memory_id=first.id,
        target_memory_id=second.id,
        link_type=ConceptLinkType.RELATES_TO,
        tenant_id="t1",
    )
    observed: list[tuple[int, bool]] = []
    real = SqliteBackend._assert_tenant_writable

    def spy(self: SqliteBackend, conn: sqlite3.Connection, tenant_id: str) -> None:
        is_owned = getattr(self._tx_lock, "_is_owned", lambda: False)
        observed.append((self._tx_depth, bool(is_owned())))
        real(self, conn, tenant_id)

    monkeypatch.setattr(SqliteBackend, "_assert_tenant_writable", spy)

    store.add_memory(MemoryRecord(content="third", category=MemoryCategory.FACT, tenant_id="t1"))
    store.update_memory(first.id, content="first updated")
    store.add_link(link)

    assert observed == [(1, True), (1, True), (1, True)]


# ---------------------------------------------------------------------------
# Requirement 1.7 — first failure wins: existence, then guard, then SQL
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-b08b76d6")
def test_guard_runs_before_the_sql_write_on_a_duplicate_key(store: SqliteBackend) -> None:
    original = store.add_memory(
        MemoryRecord(id="dup", content="first", category=MemoryCategory.FACT, tenant_id="global")
    )
    assert original.content == "first"

    missing = _raised(
        lambda: store.add_memory(
            MemoryRecord(id="dup", content="second", category=MemoryCategory.FACT, tenant_id="nope")
        )
    )
    _expect(missing, TenantNotFoundError, "nope")

    _create_tenant(store, "t1", active=False)
    inactive = _raised(
        lambda: store.add_memory(
            MemoryRecord(id="dup", content="third", category=MemoryCategory.FACT, tenant_id="t1")
        )
    )
    _expect(inactive, TenantInactiveError, "t1")

    fetched = store.get_memory("dup")
    assert fetched is not None
    assert fetched.content == "first"


@pytest.mark.l4("C-b08b76d6", "C-2812d3f2")
def test_missing_rows_keep_their_missing_row_outcome(store: SqliteBackend) -> None:
    assert _raised(lambda: store.archive_memory("missing-memory")) is None
    assert _raised(lambda: store.mark_session_concluded("missing-session")) is None
    assert (
        _raised(lambda: store.update_session_feedback("missing-session", None, None, [], []))
        is None
    )

    _create_tenant(store, "t1")
    memory = _add_memory(store, "t1")
    store.set_tenant_active("t1", False)

    guarded = _raised(lambda: store.archive_memory(memory.id))
    _expect(guarded, TenantInactiveError, "t1")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> SqliteBackend:
    backend = SqliteBackend(tmp_path / "mintmory.db")
    backend.initialise()
    return backend


@pytest.fixture
def legacy_store(tmp_path: Path) -> SqliteBackend:
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(PRE_TENANCY_SCHEMA.read_text())
        conn.commit()
    finally:
        conn.close()
    backend = SqliteBackend(path)
    backend.initialise()
    return backend
