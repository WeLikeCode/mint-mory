"""
Round-trip migration tests for migrate_sqlite_to_postgres().

Suite structure
---------------
1. Pure-logic tests (always run — no PG needed):
   - Type conversion helpers (_parse_datetime, _blob_to_array, _canonical_row)
   - Checksum determinism
   - Idempotency: ValueError when target is non-empty and force=False

2. PG round-trip tests (gated on MINTMORY_TEST_PG_DSN env var):
   - Build a rich SQLite DB via SqliteBackend (all tables populated)
   - migrate_sqlite_to_postgres() → MigrationReport.all_ok
   - PostgresBackend read-parity: get_memory, search, get_links, list_notes,
     get_summary, manifest_get, get_session round-trip
   - Idempotency: second run without --force raises ValueError (no duplication)
   - Idempotency: with --force re-runs successfully and re-verifies
   - --dry-run: target row counts unchanged after dry_run=True

MINTMORY_TEST_PG_DSN must point to a disposable Postgres 16 + pgvector DB.
The fixture resets the target (TRUNCATE CASCADE) before each test group.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest
from mintmory.core.embedder import HashingEmbedder
from mintmory.core.migrate import (
    MigrationReport,
    TableVerification,
    _blob_to_array,
    _canonical_row,
    _compute_checksum_from_dicts,
    _parse_datetime,
    _python_sort_key,
    _source_checksum,
)
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    LinkSource,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
    MemorySummary,
    QueryResult,
    QuerySession,
    SearchRequest,
)

# ---------------------------------------------------------------------------
# PG availability guard
# ---------------------------------------------------------------------------

_DSN = os.environ.get("MINTMORY_TEST_PG_DSN", "")
_PG_AVAILABLE = bool(_DSN)
_SKIP_PG = pytest.mark.skipif(not _PG_AVAILABLE, reason="MINTMORY_TEST_PG_DSN not set")

# ---------------------------------------------------------------------------
# Shared fixture: rich SQLite database
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _build_rich_sqlite(db_path: str) -> RichFixtureData:
    """
    Populate a SQLite DB with a representative set of rows covering every table:
      - memories: multiple categories, archived/superseded, is_note, embeddings
      - concept_links: symmetric (RELATES_TO) and asymmetric (ANNOTATES)
      - query_sessions + query_results
      - index_manifest
      - memory_summaries
    Returns a RichFixtureData with IDs for later assertion.
    """
    emb = HashingEmbedder(dim=64)
    store = SqliteBackend(db_path, embedder=emb)
    store.initialise()

    # ---- memories: various categories ----
    m_fact = store.add_memory(content="Python uses indentation for blocks", category="fact")
    m_pref = store.add_memory(content="User prefers dark mode in editors", category="preference")
    m_skill = store.add_memory(
        content="Pytest fixture scoping: session > module > function", category="skill"
    )
    m_ctx = store.add_memory(
        content="Current project is MintMory storage migration", category="context"
    )
    m_id = store.add_memory(content="I am an AI assistant helping engineers", category="identity")
    m_rel = store.add_memory(
        content="Alice collaborates with Bob on core module", category="relationship"
    )
    m_temp = store.add_memory(
        content="Deploy window opens 2026-07-10T10:00:00", category="temporal"
    )
    m_ep = store.add_memory(content="Discussed migration design on Monday", category="episodic")

    # archived + superseded
    m_old = store.add_memory(content="Old preference: light mode", category="preference")
    store.archive_memory(m_old.id)
    m_new_pref = store.add_memory(
        content="Updated preference: dark mode (confirmed)", category="preference"
    )
    store.supersede_memory(m_old.id, by_id=m_new_pref.id)

    # is_note
    m_note = store.add_memory(
        record=MemoryRecord(
            content="Note: revisit the chunking strategy next sprint",
            category=MemoryCategory.EPISODIC,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
        )
    )

    # flagged_for_review
    m_flagged = store.add_memory(
        content="Possibly stale: old k8s namespace config",
        category="context",
        flagged_for_review=True,
    )

    # contradicts_ids
    m_contradict = store.add_memory(
        content="Postgres is the preferred DB",
        category="fact",
        contradicts_ids=[m_fact.id],
    )

    # ---- concept_links ----
    lnk_relates = ConceptLink(
        source_memory_id=m_fact.id,
        target_memory_id=m_skill.id,
        link_type=ConceptLinkType.RELATES_TO,
        entity="python",
        source=LinkSource.DREAMING,
        strength=0.8,
        confidence=0.9,
    )
    store.add_link(lnk_relates)

    lnk_annotates = ConceptLink(
        source_memory_id=m_note.id,
        target_memory_id=m_ctx.id,
        link_type=ConceptLinkType.ANNOTATES,
        entity="mintmory",
        source=LinkSource.USER,
        strength=1.0,
        confidence=1.0,
    )
    store.add_link(lnk_annotates)

    lnk_contradict_link = ConceptLink(
        source_memory_id=m_contradict.id,
        target_memory_id=m_fact.id,
        link_type=ConceptLinkType.CONTRADICTS,
        entity="database",
        source=LinkSource.INFERENCE,
        strength=0.6,
        confidence=0.7,
    )
    store.add_link(lnk_contradict_link)

    # ---- query_sessions + query_results ----
    session = QuerySession(
        query_text="What does the user prefer for editors?",
        created_at=_utcnow(),
    )
    store.create_session(session)
    results = [
        QueryResult(
            session_id=session.id,
            memory_id=m_pref.id,
            relevance_score=0.95,
            was_accessed=True,
            was_useful=True,
            was_stale=False,
        ),
        QueryResult(
            session_id=session.id,
            memory_id=m_fact.id,
            relevance_score=0.4,
            was_accessed=False,
            was_useful=False,
            was_stale=False,
        ),
    ]
    store.record_query_results(results)

    # ---- index_manifest ----
    store.manifest_upsert(
        path="/docs/design.md",
        collection="local:docs",
        size=4096,
        mtime=1720000000.0,
        online_only=False,
        index_mode="content",
        memory_ids=[m_fact.id, m_ctx.id],
        content_hash="abc123",
    )
    store.manifest_upsert(
        path="/docs/roadmap.md",
        collection="local:docs",
        size=2048,
        mtime=1720001000.0,
        online_only=False,
        index_mode="metadata",
        memory_ids=[m_ctx.id],
        content_hash="def456",
    )

    # ---- memory_summaries ----
    summary = MemorySummary(
        concept="python",
        summary_text="Python is the primary language; indentation is idiomatic.",
        memory_count=2,
        is_current=True,
        generated_at=_utcnow(),
    )
    store.upsert_summary(summary)

    summary2 = MemorySummary(
        concept="postgres",
        summary_text="Postgres is the target HA backend for MintMory.",
        memory_count=1,
        is_current=True,
        generated_at=_utcnow(),
    )
    store.upsert_summary(summary2)

    store.close()

    return RichFixtureData(
        memory_ids=[
            m_fact.id,
            m_pref.id,
            m_skill.id,
            m_ctx.id,
            m_id.id,
            m_rel.id,
            m_temp.id,
            m_ep.id,
            m_old.id,
            m_new_pref.id,
            m_note.id,
            m_flagged.id,
            m_contradict.id,
        ],
        note_id=m_note.id,
        session_id=session.id,
        concepts=["python", "postgres"],
        manifest_paths=["/docs/design.md", "/docs/roadmap.md"],
        sampled_ids=[m_fact.id, m_pref.id, m_note.id],
        search_content="Python indentation",
        search_expected_id=m_fact.id,
    )


class RichFixtureData:
    """Holds IDs and expected values from the rich SQLite fixture."""

    def __init__(
        self,
        memory_ids: list[str],
        note_id: str,
        session_id: str,
        concepts: list[str],
        manifest_paths: list[str],
        sampled_ids: list[str],
        search_content: str,
        search_expected_id: str,
    ) -> None:
        self.memory_ids = memory_ids
        self.note_id = note_id
        self.session_id = session_id
        self.concepts = concepts
        self.manifest_paths = manifest_paths
        self.sampled_ids = sampled_ids
        self.search_content = search_content
        self.search_expected_id = search_expected_id


# ===========================================================================
# SECTION 1 — Pure-logic tests (always run)
# ===========================================================================


class TestParseDateTime:
    """_parse_datetime handles the formats SQLite actually produces."""

    def test_none_returns_none(self) -> None:
        assert _parse_datetime(None) is None

    def test_iso_no_microseconds(self) -> None:
        dt = _parse_datetime("2026-07-06T10:30:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.second == 0
        assert dt.tzinfo is None

    def test_iso_with_microseconds(self) -> None:
        dt = _parse_datetime("2026-07-06T10:30:00.123456")
        assert dt is not None
        assert dt.microsecond == 123456

    def test_iso_trailing_z(self) -> None:
        dt = _parse_datetime("2026-07-06T10:30:00Z")
        assert dt is not None
        assert dt.tzinfo is None  # stripped

    def test_datetime_object_stripped(self) -> None:

        dt_aware = datetime(2026, 7, 6, 10, 30, 0, tzinfo=UTC)
        result = _parse_datetime(dt_aware)
        assert result is not None
        assert result.tzinfo is None


class TestBlobToArray:
    """_blob_to_array decodes float32 BLOBs correctly."""

    def test_none_returns_none(self) -> None:
        assert _blob_to_array(None) is None

    def test_round_trip(self) -> None:
        arr = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        blob = arr.tobytes()
        result = _blob_to_array(blob)
        assert result is not None
        np.testing.assert_array_equal(result, arr)

    def test_dtype_is_float32(self) -> None:
        arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        result = _blob_to_array(arr.tobytes())
        assert result is not None
        assert result.dtype == np.float32


class TestCanonicalRow:
    """_canonical_row normalizes rows to a stable canonical form."""

    def _mem_row_sqlite(self) -> dict[str, Any]:
        """Simulate a raw SQLite row dict for a memories row."""
        return {
            "id": "mem-001",
            "content": "Hello world",
            "category": "fact",
            "entity_ids": '["hello","world"]',  # TEXT JSON in SQLite
            "embedding": None,
            "confidence": 0.9,
            "source": "user",
            "verified": 1,  # INTEGER bool
            "valid_from": None,
            "valid_until": None,
            "usefulness_score": 2.5,
            "staleness_score": 0.0,
            "reinforcement_count": 3,
            "retrieval_count": 7,
            "is_stale": 0,
            "is_active": 1,
            "is_archived": 0,
            "superseded_by": None,
            "flagged_for_review": 0,
            "contradicts_ids": "[]",
            "is_note": 0,
            "created_at": "2026-07-06T10:00:00",
            "updated_at": "2026-07-06T10:00:00.123456",
            "last_accessed_at": None,
            "metadata": "{}",
        }

    def _mem_row_pg(self) -> dict[str, Any]:
        """Simulate a psycopg-decoded row dict for the same row."""
        return {
            "id": "mem-001",
            "content": "Hello world",
            "category": "fact",
            "entity_ids": ["hello", "world"],  # JSONB → list (psycopg auto-decoded)
            "confidence": 0.9,
            "source": "user",
            "verified": True,  # BOOLEAN
            "valid_from": None,
            "valid_until": None,
            "usefulness_score": 2.5,
            "staleness_score": 0.0,
            "reinforcement_count": 3,
            "retrieval_count": 7,
            "is_stale": False,
            "is_active": True,
            "is_archived": False,
            "superseded_by": None,
            "flagged_for_review": False,
            "contradicts_ids": [],
            "is_note": False,
            "created_at": datetime(2026, 7, 6, 10, 0, 0),
            "updated_at": datetime(2026, 7, 6, 10, 0, 0, 123456),
            "last_accessed_at": None,
            "metadata": {},
        }

    def test_sqlite_and_pg_rows_produce_same_canonical(self) -> None:
        src_canonical = _canonical_row(self._mem_row_sqlite(), "memories")
        # For PG, the row has no 'embedding' column in the checksum query,
        # but _canonical_row should still work even if it's absent.
        dst_canonical = _canonical_row(self._mem_row_pg(), "memories")
        assert src_canonical == dst_canonical

    def test_embedding_excluded(self) -> None:
        row = self._mem_row_sqlite()
        row["embedding"] = b"\x00\x01\x02\x03"
        canonical = _canonical_row(row, "memories")
        assert "embedding" not in canonical

    def test_content_tsv_excluded(self) -> None:
        row = self._mem_row_pg()
        row["content_tsv"] = "some:tsvector:data"
        canonical = _canonical_row(row, "memories")
        assert "content_tsv" not in canonical

    def test_bool_cols_normalized_to_bool(self) -> None:
        row = self._mem_row_sqlite()
        canonical = _canonical_row(row, "memories")
        assert canonical["verified"] is True
        assert canonical["is_stale"] is False
        assert canonical["is_active"] is True
        assert canonical["is_archived"] is False

    def test_json_cols_parsed(self) -> None:
        row = self._mem_row_sqlite()
        canonical = _canonical_row(row, "memories")
        assert canonical["entity_ids"] == ["hello", "world"]
        assert canonical["contradicts_ids"] == []
        assert canonical["metadata"] == {}


class TestChecksumDeterminism:
    """Checksum is stable regardless of invocation order / same data."""

    def _make_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "qs-001",
                "query_text": "What is Python?",
                "created_at": "2026-07-06T10:00:00",
                "confidence_rating": None,
                "reasoning": None,
                "useful_ids": "[]",
                "stale_ids": "[]",
                "concluded": 0,
            },
            {
                "id": "qs-002",
                "query_text": "What is Postgres?",
                "created_at": "2026-07-06T11:00:00",
                "confidence_rating": 4,
                "reasoning": "Looked relevant",
                "useful_ids": '["mem-001"]',
                "stale_ids": "[]",
                "concluded": 1,
            },
        ]

    def test_same_rows_same_checksum(self) -> None:
        rows = self._make_rows()
        cksum1 = _source_checksum(rows, "query_sessions")
        cksum2 = _source_checksum(rows, "query_sessions")
        assert cksum1 == cksum2
        assert len(cksum1) == 64  # SHA-256 hex

    def test_different_rows_different_checksum(self) -> None:
        rows1 = self._make_rows()
        rows2 = self._make_rows()
        rows2[0]["query_text"] = "Different query"
        cksum1 = _source_checksum(rows1, "query_sessions")
        cksum2 = _source_checksum(rows2, "query_sessions")
        assert cksum1 != cksum2

    def test_row_order_matters(self) -> None:
        """Checksum is order-dependent (rows are sorted by PK before call)."""
        rows = self._make_rows()
        reversed_rows = list(reversed(rows))
        cksum_fwd = _source_checksum(rows, "query_sessions")
        cksum_rev = _source_checksum(reversed_rows, "query_sessions")
        assert cksum_fwd != cksum_rev


class TestPythonSortKeyCollationStability:
    """_python_sort_key produces consistent ordering regardless of DB collation.

    SQLite uses BINARY collation (code-point order); PostgreSQL defaults to the
    cluster locale (e.g. en_US.utf8) which ignores punctuation in comparisons.
    This diverges for paths like 'a-b.md' vs 'ab.md':
      - BINARY:  'a-b.md' < 'ab.md'  (hyphen 0x2d < 'b' 0x62)
      - en_US:   'ab.md' < 'a-b.md'  (locale treats hyphen as insignificant)

    _python_sort_key always uses code-point order, so both sides sort
    identically and checksums agree regardless of database collation.
    """

    def _manifest_row(self, path: str) -> dict[str, Any]:
        return {
            "path": path,
            "collection": "local",
            "size": 100,
            "mtime": 1.0,
            "content_hash": "abc",
            "index_mode": "content",
            "memory_ids": "[]",
            "online_only": False,
            "last_seen": "2026-01-01",
        }

    def test_hyphen_path_sorts_before_alpha_in_python_order(self) -> None:
        """'a-b.md' < 'ab.md' under Python/BINARY (hyphen 0x2d < 'b' 0x62)."""
        pk_cols = ["path"]
        key_hyphen = _python_sort_key(self._manifest_row("a-b.md"), pk_cols)
        key_alpha = _python_sort_key(self._manifest_row("ab.md"), pk_cols)
        assert key_hyphen < key_alpha, "Expected 'a-b.md' < 'ab.md' under Python code-point sort"

    def test_checksum_stable_with_collation_divergent_paths(self) -> None:
        """Two checksum runs on the same data produce the same digest.

        The paths 'a-b.md' / 'ab.md' diverge under en_US vs BINARY ORDER BY
        but _compute_checksum_from_dicts sorts in Python on both source and
        target, so the checksum is always the same.
        """
        row1 = self._manifest_row("a-b.md")
        row2 = self._manifest_row("ab.md")
        pk_cols = ["path"]

        # Python sort: 'a-b.md' before 'ab.md' (code-point order)
        sorted_rows = sorted([row1, row2], key=lambda r: _python_sort_key(r, pk_cols))
        assert sorted_rows[0]["path"] == "a-b.md"

        # Checksum is deterministic regardless of initial list order
        cksum1 = _compute_checksum_from_dicts(
            sorted([row1, row2], key=lambda r: _python_sort_key(r, pk_cols)),
            "index_manifest",
        )
        cksum2 = _compute_checksum_from_dicts(
            sorted([row2, row1], key=lambda r: _python_sort_key(r, pk_cols)),
            "index_manifest",
        )
        assert cksum1 == cksum2, (
            "Checksum must be identical regardless of input order when Python sort is applied"
        )

    def test_reversed_order_gives_different_checksum(self) -> None:
        """Sanity: different row order → different checksum (order matters)."""
        row1 = self._manifest_row("a-b.md")
        row2 = self._manifest_row("ab.md")
        cksum_fwd = _compute_checksum_from_dicts([row1, row2], "index_manifest")
        cksum_rev = _compute_checksum_from_dicts([row2, row1], "index_manifest")
        assert cksum_fwd != cksum_rev


# ===========================================================================
# SECTION 2 — PG round-trip tests (gated on MINTMORY_TEST_PG_DSN)
# ===========================================================================


@pytest.fixture(scope="module")
def pg_dsn() -> str:
    if not _PG_AVAILABLE:
        pytest.skip("MINTMORY_TEST_PG_DSN not set")
    return _DSN


@pytest.fixture(scope="module")
def rich_sqlite_db(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, RichFixtureData]:
    """Build the rich SQLite fixture DB once for the module."""
    db_path = str(tmp_path_factory.mktemp("sqlite") / "memories.db")
    data = _build_rich_sqlite(db_path)
    return db_path, data


def _reset_pg(dsn: str) -> None:
    """Reset the target PG to a clean state (TRUNCATE CASCADE).

    PostgresBackend.initialise() must run BEFORE register_vector() because
    initialise() issues CREATE EXTENSION IF NOT EXISTS vector.  On a fresh DB
    the vector type does not exist yet, so register_vector() would fail with
    'vector type not found in the database' if called first.
    """
    import psycopg  # noqa: PLC0415

    # Step 1: create the schema + pgvector extension (idempotent).
    from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415
    from pgvector.psycopg import register_vector  # noqa: PLC0415

    pg = PostgresBackend(dsn=dsn, pool_min=1, pool_max=2)
    pg.initialise()
    pg.close()

    # Step 2: now the vector type exists — register_vector is safe to call.
    conn = psycopg.connect(dsn, autocommit=False)
    register_vector(conn)
    try:
        conn.execute(
            "TRUNCATE memories, concept_links, index_manifest, "
            "query_sessions, query_results, memory_summaries "
            "RESTART IDENTITY CASCADE"
        )
        conn.commit()
    finally:
        conn.close()


@_SKIP_PG
class TestMigrationRoundTrip:
    """Full round-trip: migrate → verify report → read via PostgresBackend."""

    def test_migration_report_all_ok(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """migrate_sqlite_to_postgres produces a passing MigrationReport."""
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415

        db_path, _ = rich_sqlite_db
        _reset_pg(pg_dsn)

        report = migrate_sqlite_to_postgres(db_path, pg_dsn, batch_size=10)

        assert isinstance(report, MigrationReport)
        assert report.dry_run is False
        assert report.total_rows_written > 0
        for tv in report.tables:
            assert isinstance(tv, TableVerification)
            assert tv.count_ok, (
                f"Table {tv.table}: count mismatch src={tv.src_count} dst={tv.dst_count}"
            )
            assert tv.checksum_ok, (
                f"Table {tv.table}: checksum mismatch "
                f"src={tv.src_checksum[:16]} dst={tv.dst_checksum[:16]}"
            )
        assert report.all_ok

    def test_pg_get_memory_round_trip(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """Sampled memories read back via PostgresBackend match source fields."""
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415
        from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415

        db_path, data = rich_sqlite_db
        _reset_pg(pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn)

        # Read source via SqliteBackend for field comparison
        emb = HashingEmbedder(dim=64)
        src_store = SqliteBackend(db_path, embedder=emb)
        src_store.initialise()

        pg = PostgresBackend(dsn=pg_dsn, embedder=emb, pool_min=1, pool_max=2)
        pg.initialise()
        try:
            for mid in data.sampled_ids:
                src_mem = src_store.get_memory(mid)
                dst_mem = pg.get_memory(mid)
                assert src_mem is not None
                assert dst_mem is not None, f"Memory {mid!r} not found in PG"
                assert dst_mem.id == src_mem.id
                assert dst_mem.content == src_mem.content
                assert dst_mem.category == src_mem.category
                assert dst_mem.entity_ids == src_mem.entity_ids
                assert dst_mem.confidence == pytest.approx(src_mem.confidence)
                assert dst_mem.source == src_mem.source
                assert dst_mem.verified == src_mem.verified
                assert dst_mem.usefulness_score == pytest.approx(src_mem.usefulness_score)
                assert dst_mem.staleness_score == pytest.approx(src_mem.staleness_score)
                assert dst_mem.reinforcement_count == src_mem.reinforcement_count
                assert dst_mem.retrieval_count == src_mem.retrieval_count
                assert dst_mem.is_stale == src_mem.is_stale
                assert dst_mem.is_active == src_mem.is_active
                assert dst_mem.is_archived == src_mem.is_archived
                assert dst_mem.superseded_by == src_mem.superseded_by
                assert dst_mem.flagged_for_review == src_mem.flagged_for_review
                assert dst_mem.contradicts_ids == src_mem.contradicts_ids
                assert dst_mem.is_note == src_mem.is_note
                assert dst_mem.metadata == src_mem.metadata
        finally:
            src_store.close()
            pg.close()

    def test_embedding_vector_round_trip(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """Migrated embedding vectors are bit-for-bit equal to the source float32 blobs.

        This verifies the blob→pgvector conversion (_blob_to_array + pgvector
        adapter) so that a regression in dtype/endianness/dimension would be
        caught even though embedding is excluded from the content checksum.
        """
        import sqlite3 as _sqlite3  # noqa: PLC0415

        import psycopg  # noqa: PLC0415
        from mintmory.core.migrate import (  # noqa: PLC0415
            _blob_to_array,
            migrate_sqlite_to_postgres,
        )
        from pgvector.psycopg import register_vector  # noqa: PLC0415

        db_path, data = rich_sqlite_db
        _reset_pg(pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn)

        # Read source embedding BLOB from SQLite
        mid = data.sampled_ids[0]  # m_fact (always has an embedding)
        sqlite_conn = _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = sqlite_conn.execute(
                "SELECT embedding FROM memories WHERE id = ?", (mid,)
            ).fetchone()
        finally:
            sqlite_conn.close()

        assert row is not None, f"Memory {mid!r} not found in source SQLite"
        src_emb = _blob_to_array(row[0])
        assert src_emb is not None, f"Memory {mid!r} has no embedding in source"

        # Read back the vector from PG via raw psycopg (not PostgresBackend,
        # which does not expose the raw embedding field).
        pg_conn = psycopg.connect(pg_dsn, autocommit=True)
        register_vector(pg_conn)
        try:
            pg_row = pg_conn.execute(
                "SELECT embedding FROM memories WHERE id = %s", (mid,)
            ).fetchone()
        finally:
            pg_conn.close()

        assert pg_row is not None, f"Memory {mid!r} not found in target PG"
        pg_emb = np.array(pg_row[0], dtype=np.float32)

        assert src_emb.shape == pg_emb.shape, (
            f"Embedding shape mismatch: src={src_emb.shape} pg={pg_emb.shape}"
        )
        max_abs_diff = float(np.max(np.abs(src_emb - pg_emb)))
        assert max_abs_diff == 0.0, (
            f"Embedding round-trip max abs diff = {max_abs_diff:.2e} "
            f"(expected exactly 0.0 — float32 blobs should be preserved bit-for-bit)"
        )

    def test_pg_search_returns_expected(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """search() on PG returns the expected memory for a known query."""
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415
        from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415

        db_path, data = rich_sqlite_db
        _reset_pg(pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn)

        emb = HashingEmbedder(dim=64)
        pg = PostgresBackend(dsn=pg_dsn, embedder=emb, pool_min=1, pool_max=2)
        pg.initialise()
        try:
            resp = pg.search(SearchRequest(query=data.search_content, limit=10))
            found_ids = {m.id for m in resp.memories}
            assert data.search_expected_id in found_ids, (
                f"Expected {data.search_expected_id!r} in search results for "
                f"{data.search_content!r}; got {found_ids}"
            )
        finally:
            pg.close()

    def test_pg_get_links(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """get_links returns links for a memory that has them."""
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415
        from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415

        db_path, data = rich_sqlite_db
        _reset_pg(pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn)

        pg = PostgresBackend(dsn=pg_dsn, pool_min=1, pool_max=2)
        pg.initialise()
        try:
            # m_fact has RELATES_TO and CONTRADICTS links
            fact_id = data.sampled_ids[0]  # m_fact.id
            links = pg.get_links(fact_id)
            assert len(links) > 0
            link_types = {lk.link_type for lk in links}
            has_expected = (
                ConceptLinkType.RELATES_TO in link_types
                or ConceptLinkType.CONTRADICTS in link_types
            )
            assert has_expected
        finally:
            pg.close()

    def test_pg_list_notes(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """list_notes returns the migrated note."""
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415
        from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415

        db_path, data = rich_sqlite_db
        _reset_pg(pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn)

        pg = PostgresBackend(dsn=pg_dsn, pool_min=1, pool_max=2)
        pg.initialise()
        try:
            notes = pg.list_notes()
            note_ids = {n.id for n in notes}
            assert data.note_id in note_ids
            for note in notes:
                assert note.is_note is True
        finally:
            pg.close()

    def test_pg_get_summary(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """get_summary returns migrated summaries."""
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415
        from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415

        db_path, data = rich_sqlite_db
        _reset_pg(pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn)

        pg = PostgresBackend(dsn=pg_dsn, pool_min=1, pool_max=2)
        pg.initialise()
        try:
            for concept in data.concepts:
                summary = pg.get_summary(concept)
                assert summary is not None, f"Summary for {concept!r} not found in PG"
                assert summary.concept == concept
                assert summary.memory_count >= 0
        finally:
            pg.close()

    def test_pg_manifest_get(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """manifest_get returns migrated manifest entries."""
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415
        from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415

        db_path, data = rich_sqlite_db
        _reset_pg(pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn)

        pg = PostgresBackend(dsn=pg_dsn, pool_min=1, pool_max=2)
        pg.initialise()
        try:
            for path in data.manifest_paths:
                entry = pg.manifest_get(path)
                assert entry is not None, f"Manifest entry for {path!r} not found in PG"
                assert entry["path"] == path
                assert entry["collection"] == "local:docs"
        finally:
            pg.close()

    def test_pg_get_session(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """get_session returns the migrated query session."""
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415
        from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415

        db_path, data = rich_sqlite_db
        _reset_pg(pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn)

        pg = PostgresBackend(dsn=pg_dsn, pool_min=1, pool_max=2)
        pg.initialise()
        try:
            session = pg.get_session(data.session_id)
            assert session is not None, f"Session {data.session_id!r} not found in PG"
            assert session.id == data.session_id
            assert "editor" in session.query_text or "prefer" in session.query_text
        finally:
            pg.close()

    def test_superseded_by_round_trip(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """superseded_by FK is correctly migrated (two-pass strategy)."""
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415
        from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415

        db_path, data = rich_sqlite_db
        _reset_pg(pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn)

        # Verify superseded_by via SQLite first
        emb = HashingEmbedder(dim=64)
        src_store = SqliteBackend(db_path, embedder=emb)
        src_store.initialise()
        # m_old is at index 8 in memory_ids
        m_old_id = data.memory_ids[8]
        src_old = src_store.get_memory(m_old_id)
        src_store.close()
        assert src_old is not None
        assert src_old.superseded_by is not None

        pg = PostgresBackend(dsn=pg_dsn, pool_min=1, pool_max=2)
        pg.initialise()
        try:
            dst_old = pg.get_memory(m_old_id)
            assert dst_old is not None
            assert dst_old.superseded_by == src_old.superseded_by
        finally:
            pg.close()


@_SKIP_PG
class TestMigrationIdempotency:
    """Idempotency and --force / --dry-run behavior."""

    def test_second_run_without_force_raises(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """A second migration run on a non-empty target is refused."""
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415

        db_path, _ = rich_sqlite_db
        _reset_pg(pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn)

        with pytest.raises(ValueError, match="force"):
            migrate_sqlite_to_postgres(db_path, pg_dsn, force=False)

    def test_second_run_with_force_succeeds(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """--force truncates the target and re-migrates successfully."""
        import psycopg  # noqa: PLC0415
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415

        db_path, _ = rich_sqlite_db
        _reset_pg(pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn)

        # Record the count before force-re-run
        pg_conn = psycopg.connect(pg_dsn, autocommit=True)
        try:
            row = pg_conn.execute("SELECT COUNT(*) FROM memories").fetchone()
            assert row is not None
            before_count = row[0]
        finally:
            pg_conn.close()

        # Force re-run
        report = migrate_sqlite_to_postgres(db_path, pg_dsn, force=True)
        assert report.all_ok

        # Count must be the same as after the first run (not doubled)
        pg_conn2 = psycopg.connect(pg_dsn, autocommit=True)
        try:
            row2 = pg_conn2.execute("SELECT COUNT(*) FROM memories").fetchone()
            assert row2 is not None
            after_count = row2[0]
        finally:
            pg_conn2.close()
        assert after_count == before_count

    def test_dry_run_writes_nothing(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """--dry-run leaves the target DB completely unchanged."""
        import psycopg  # noqa: PLC0415
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415

        db_path, _ = rich_sqlite_db
        _reset_pg(pg_dsn)

        # Dry run on empty target
        report = migrate_sqlite_to_postgres(db_path, pg_dsn, dry_run=True)
        assert report.dry_run is True

        # Target must still be empty
        pg_conn = psycopg.connect(pg_dsn, autocommit=True)
        try:
            cnt_row = pg_conn.execute("SELECT COUNT(*) FROM memories").fetchone()
            assert cnt_row is not None
            count = cnt_row[0]
        finally:
            pg_conn.close()
        assert count == 0, f"dry_run wrote {count} rows to memories (expected 0)"

    def test_dry_run_reports_src_counts(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """--dry-run reports source counts correctly even without writing."""
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415

        db_path, data = rich_sqlite_db
        _reset_pg(pg_dsn)
        report = migrate_sqlite_to_postgres(db_path, pg_dsn, dry_run=True)

        memories_tv = next(t for t in report.tables if t.table == "memories")
        assert memories_tv.src_count == len(data.memory_ids)
        # dst_count == 0 in dry-run (nothing written)
        assert memories_tv.dst_count == 0

    def test_no_row_duplication_after_force(
        self,
        rich_sqlite_db: tuple[str, RichFixtureData],
        pg_dsn: str,
    ) -> None:
        """After force re-run, row count equals source (no duplication)."""
        import psycopg  # noqa: PLC0415
        from mintmory.core.migrate import migrate_sqlite_to_postgres  # noqa: PLC0415

        db_path, data = rich_sqlite_db
        _reset_pg(pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn)
        migrate_sqlite_to_postgres(db_path, pg_dsn, force=True)

        pg_conn = psycopg.connect(pg_dsn, autocommit=True)
        try:
            final_row = pg_conn.execute("SELECT COUNT(*) FROM memories").fetchone()
            assert final_row is not None
            count = final_row[0]
        finally:
            pg_conn.close()
        assert count == len(data.memory_ids)
