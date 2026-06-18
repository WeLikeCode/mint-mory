"""
M1 Gate: Schema compliance tests.

These tests are the FIRST gate in the CI pipeline. They verify that:
  1. schema.sql can be executed without error
  2. Every table, column, and index documented in schema.sql exists in the DB
  3. Every ConceptLinkType enum value appears in the schema.sql CHECK constraint
  4. Foreign key constraints are active

These tests run against an in-memory SQLite database (:memory:) and have
NO external dependencies. They must pass before any implementation code is
written (TDD gate for M1).

CRITICAL INVARIANT (AGENTS.md §4):
  If you add a new ConceptLinkType value to types.py, this test will FAIL
  until you also add it to the CHECK constraint in schema.sql.
"""

import sqlite3
from pathlib import Path

import pytest
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import ConceptLinkType, MemoryCategory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db() -> StorageAdapter:
    adapter = StorageAdapter(":memory:")
    adapter.initialise()
    return adapter


@pytest.fixture()
def conn(db: StorageAdapter) -> sqlite3.Connection:
    return db.connect()


@pytest.fixture()
def schema_sql() -> str:
    path = Path(__file__).parent.parent / "src" / "mintmory" / "core" / "schema.sql"
    return path.read_text()


# ---------------------------------------------------------------------------
# Table existence
# ---------------------------------------------------------------------------


REQUIRED_TABLES = {
    "memories",
    "concept_links",
    "memory_summaries",
    "query_sessions",
    "query_results",
    "memories_fts",  # FTS5 virtual table
}


def test_all_required_tables_exist(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'shadow') OR "
        "(type='table' AND name LIKE '%_fts%')"
    ).fetchall()
    existing = {row["name"] for row in rows}
    for table in REQUIRED_TABLES - {"memories_fts"}:
        assert table in existing, f"Table '{table}' missing from schema"


def test_fts5_virtual_table_exists(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='memories_fts'"
    ).fetchone()
    assert row is not None, "FTS5 virtual table 'memories_fts' is missing"


def test_memories_trigram_is_not_in_core_schema(conn: sqlite3.Connection) -> None:
    # memories_trigram is created best-effort at runtime by StorageAdapter, NOT
    # in schema.sql. It must therefore stay out of REQUIRED_TABLES so the M1
    # schema gate does not depend on trigram tokenizer availability.
    assert "memories_trigram" not in REQUIRED_TABLES


def test_memories_trigram_is_creatable(conn: sqlite3.Connection) -> None:
    # The trigram fts5 virtual table must be creatable in this environment
    # (sanity check that the tokenizer is available), but is intentionally not
    # part of the core schema.sql.
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS _probe_trigram USING fts5(content, tokenize='trigram')"
    )
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='_probe_trigram'"
    ).fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# Column existence — memories table
# ---------------------------------------------------------------------------


REQUIRED_MEMORIES_COLUMNS = {
    "id",
    "content",
    "category",
    "entity_ids",
    "embedding",
    "confidence",
    "source",
    "verified",
    "valid_from",
    "valid_until",
    "usefulness_score",
    "staleness_score",
    "reinforcement_count",
    "retrieval_count",
    "is_stale",
    "is_active",
    "is_archived",
    "superseded_by",
    "flagged_for_review",
    "contradicts_ids",
    "is_note",
    "created_at",
    "updated_at",
    "last_accessed_at",
    "metadata",
}


def test_memories_columns_exist(conn: sqlite3.Connection) -> None:
    info = conn.execute("PRAGMA table_info(memories)").fetchall()
    existing = {row["name"] for row in info}
    missing = REQUIRED_MEMORIES_COLUMNS - existing
    assert not missing, f"memories table missing columns: {missing}"


# ---------------------------------------------------------------------------
# Column existence — concept_links table
# ---------------------------------------------------------------------------


REQUIRED_LINKS_COLUMNS = {
    "id",
    "source_memory_id",
    "target_memory_id",
    "link_type",
    "entity",
    "strength",
    "confidence",
    "source",
    "verified",
    "created_at",
    "updated_at",
}


def test_concept_links_columns_exist(conn: sqlite3.Connection) -> None:
    info = conn.execute("PRAGMA table_info(concept_links)").fetchall()
    existing = {row["name"] for row in info}
    missing = REQUIRED_LINKS_COLUMNS - existing
    assert not missing, f"concept_links table missing columns: {missing}"


# ---------------------------------------------------------------------------
# Column existence — query_sessions table
# ---------------------------------------------------------------------------


REQUIRED_SESSIONS_COLUMNS = {
    "id",
    "query_text",
    "created_at",
    "confidence_rating",
    "reasoning",
    "useful_ids",
    "stale_ids",
    "concluded",
}


def test_query_sessions_columns_exist(conn: sqlite3.Connection) -> None:
    info = conn.execute("PRAGMA table_info(query_sessions)").fetchall()
    existing = {row["name"] for row in info}
    missing = REQUIRED_SESSIONS_COLUMNS - existing
    assert not missing, f"query_sessions table missing columns: {missing}"


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------


REQUIRED_INDEXES = {
    "idx_memories_active",
    "idx_memories_stale",
    "idx_memories_category",
    "idx_memories_flagged",
    "idx_memories_usefulness",
    "idx_memories_note",
    "idx_links_source",
    "idx_links_target",
    "idx_links_type_strength",
    "idx_links_entity",
    "idx_sessions_concluded",
    "idx_results_session",
    "idx_results_memory",
}


def test_all_required_indexes_exist(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    existing = {row["name"] for row in rows}
    missing = REQUIRED_INDEXES - existing
    assert not missing, f"Missing indexes: {missing}"


# ---------------------------------------------------------------------------
# FTS5 triggers
# ---------------------------------------------------------------------------


REQUIRED_TRIGGERS = {
    "memories_fts_insert",
    "memories_fts_update",
    "memories_fts_delete",
}


def test_fts5_triggers_exist(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
    existing = {row["name"] for row in rows}
    missing = REQUIRED_TRIGGERS - existing
    assert not missing, f"Missing FTS5 triggers: {missing}"


# ---------------------------------------------------------------------------
# Enum ↔ CHECK constraint parity
# (CRITICAL: adding a ConceptLinkType in types.py without updating schema.sql
#  will fail this test)
# ---------------------------------------------------------------------------


def test_all_concept_link_types_in_schema(schema_sql: str) -> None:
    for link_type in ConceptLinkType:
        assert link_type.value in schema_sql, (
            f"ConceptLinkType.{link_type.name} ('{link_type.value}') is not in "
            f"the schema.sql CHECK constraint. Add it to concept_links.link_type CHECK."
        )


def test_all_memory_categories_in_schema(schema_sql: str) -> None:
    for category in MemoryCategory:
        assert category.value in schema_sql, (
            f"MemoryCategory.{category.name} ('{category.value}') is not in "
            f"the schema.sql CHECK constraint. Add it to memories.category CHECK."
        )


# ---------------------------------------------------------------------------
# Foreign key enforcement
# ---------------------------------------------------------------------------


def test_foreign_keys_are_enforced(conn: sqlite3.Connection) -> None:
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1, "PRAGMA foreign_keys must be ON — see AGENTS.md §4"


def test_foreign_key_violation_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("""
            INSERT INTO concept_links
            (id, source_memory_id, target_memory_id, link_type, strength,
             confidence, source, verified, created_at, updated_at)
            VALUES
            ('test-link', 'nonexistent-src', 'nonexistent-tgt',
             'relates_to', 0.5, 0.5, 'dreaming', 0,
             '2026-06-15T00:00:00Z', '2026-06-15T00:00:00Z')
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# is_note column — personal-notes migration (design §1d, §1f)
# ---------------------------------------------------------------------------


def test_is_note_column_exists_in_fresh_db(conn: sqlite3.Connection) -> None:
    """Fresh :memory: DB created from schema.sql must already have is_note."""
    info = conn.execute("PRAGMA table_info(memories)").fetchall()
    col_names = {row["name"] for row in info}
    assert "is_note" in col_names, "is_note column missing from memories table"


def test_is_note_column_default_zero(conn: sqlite3.Connection) -> None:
    """is_note column must default to 0 for every new row."""
    import uuid

    now = "2026-06-18T00:00:00"
    conn.execute(
        """
        INSERT INTO memories
        (id, content, category, entity_ids, confidence, source, verified,
         usefulness_score, staleness_score, reinforcement_count, retrieval_count,
         is_stale, is_active, is_archived, flagged_for_review, contradicts_ids,
         created_at, updated_at, metadata)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            "test note default",
            "fact",
            "[]",
            1.0,
            "agent",
            0,
            0.0,
            0.0,
            0,
            0,
            0,
            1,
            0,
            0,
            "[]",
            now,
            now,
            "{}",
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT is_note FROM memories WHERE content = 'test note default'"
    ).fetchone()
    assert row is not None
    assert row["is_note"] == 0


def test_is_note_index_exists(conn: sqlite3.Connection) -> None:
    """idx_memories_note partial index must exist."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_memories_note'"
    ).fetchone()
    assert row is not None, "idx_memories_note partial index missing"


def test_annotates_link_type_accepted_in_fresh_db(
    conn: sqlite3.Connection, db: StorageAdapter
) -> None:
    """A fresh DB must accept an 'annotates' link in concept_links CHECK constraint."""
    import uuid

    now = "2026-06-18T00:00:00"
    # Insert two memories to satisfy FK constraints
    for i in range(2):
        conn.execute(
            """
            INSERT INTO memories
            (id, content, category, entity_ids, confidence, source, verified,
             usefulness_score, staleness_score, reinforcement_count, retrieval_count,
             is_stale, is_active, is_archived, flagged_for_review, contradicts_ids,
             is_note, created_at, updated_at, metadata)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                f"mem-annotates-{i}",
                f"annotates test memory {i}",
                "fact",
                "[]",
                1.0,
                "agent",
                0,
                0.0,
                0.0,
                0,
                0,
                0,
                1,
                0,
                0,
                "[]",
                0,
                now,
                now,
                "{}",
            ),
        )
    conn.commit()
    # Insert an annotates link — must NOT raise IntegrityError
    link_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO concept_links
        (id, source_memory_id, target_memory_id, link_type, strength,
         confidence, source, verified, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (link_id, "mem-annotates-0", "mem-annotates-1", "annotates", 1.0, 1.0, "user", 0, now, now),
    )
    conn.commit()
    row = conn.execute("SELECT link_type FROM concept_links WHERE id = ?", (link_id,)).fetchone()
    assert row is not None
    assert row["link_type"] == "annotates"


def test_ensure_is_note_column_idempotent() -> None:
    """Calling initialise() twice must be a no-op (second call does not crash)."""
    s = StorageAdapter(":memory:")
    s.initialise()
    s.initialise()  # second call — must not raise


def test_ensure_is_note_column_backfills_old_db(tmp_path: Path) -> None:
    """_ensure_is_note_column adds is_note to a DB that genuinely lacks it.

    Builds a real legacy state by physically DROPping the column (and its partial
    index, which references it) from a fresh DB + an existing row, then verifies the
    migration re-adds the column and the pre-existing row reads back as a non-note.
    """
    db_path = tmp_path / "legacy.db"
    s = StorageAdapter(str(db_path))
    s.initialise()
    mid = s.add_memory(content="pre-notes legacy memory", category="fact").id
    conn = s.connect()

    # Simulate a DB created BEFORE personal-notes: remove the column for real.
    conn.executescript(
        "DROP INDEX IF EXISTS idx_memories_note; ALTER TABLE memories DROP COLUMN is_note;"
    )
    conn.commit()
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(memories)").fetchall()}
    assert "is_note" not in cols  # legacy state confirmed — the migration has real work

    # Backfill via the migration under test.
    s._ensure_is_note_column(conn)
    cols2 = {row["name"] for row in conn.execute("PRAGMA table_info(memories)").fetchall()}
    assert "is_note" in cols2
    # Idempotent: a second call is a no-op (does not raise).
    s._ensure_is_note_column(conn)
    # The pre-existing row reads back as a non-note (column default 0).
    fetched = s.get_memory(mid)
    assert fetched is not None
    assert fetched.is_note is False
    s.close()


# ---------------------------------------------------------------------------
# is_note column — MemoryRecord round-trip (design §1a, §1g)
# ---------------------------------------------------------------------------


def test_is_note_round_trip_add_get(db: StorageAdapter) -> None:
    """MemoryRecord with is_note=True round-trips through add_memory / get_memory."""
    from mintmory.core.types import MemoryRecord, MemorySource  # noqa: PLC0415

    record = MemoryRecord(
        content="Round-trip note check",
        category=MemoryCategory.EPISODIC,
        source=MemorySource.USER,
        verified=True,
        is_note=True,
    )
    db.add_memory(record=record)
    fetched = db.get_memory(record.id)
    assert fetched is not None
    assert fetched.is_note is True


def test_is_note_false_by_default_in_add(db: StorageAdapter) -> None:
    """is_note defaults to False for every existing construction site."""
    record = db.add_memory(content="A normal memory", category="fact")
    assert record.is_note is False
    fetched = db.get_memory(record.id)
    assert fetched is not None
    assert fetched.is_note is False


def test_is_note_round_trip_update_memory(db: StorageAdapter) -> None:
    """is_note flag survives an update_memory call that changes another field."""
    from mintmory.core.types import MemoryRecord, MemorySource  # noqa: PLC0415

    note = MemoryRecord(
        content="Note to update",
        category=MemoryCategory.EPISODIC,
        source=MemorySource.USER,
        verified=True,
        is_note=True,
    )
    db.add_memory(record=note)
    updated = db.update_memory(note.id, confidence=0.9)
    assert updated.is_note is True


def test_annotates_not_in_symmetric_link_types() -> None:
    """ANNOTATES must NOT be in SYMMETRIC_LINK_TYPES (design §1b, §9)."""
    from mintmory.core.types import SYMMETRIC_LINK_TYPES, ConceptLinkType  # noqa: PLC0415

    assert ConceptLinkType.ANNOTATES not in SYMMETRIC_LINK_TYPES


# ---------------------------------------------------------------------------
# WAL mode
# ---------------------------------------------------------------------------


def test_wal_mode_is_set(conn: sqlite3.Connection) -> None:
    row = conn.execute("PRAGMA journal_mode").fetchone()
    # :memory: databases always return 'memory' — this is expected in tests
    # For file-based DBs, this will be 'wal'
    assert row[0] in ("wal", "memory"), f"Expected WAL or memory mode, got: {row[0]}"


# ---------------------------------------------------------------------------
# Score cap invariant
# ---------------------------------------------------------------------------


def test_usefulness_score_check_constraint(conn: sqlite3.Connection) -> None:
    """usefulness_score > 10.0 must be rejected by the DB CHECK constraint."""
    import uuid

    now = "2026-06-15T00:00:00Z"
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO memories
            (id, content, category, entity_ids, confidence, source, verified,
             usefulness_score, staleness_score, reinforcement_count, retrieval_count,
             is_stale, is_active, is_archived, flagged_for_review, contradicts_ids,
             created_at, updated_at, metadata)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
            (
                str(uuid.uuid4()),
                "test memory",
                "fact",
                "[]",
                1.0,
                "agent",
                0,
                11.0,  # INVALID — above cap
                0.0,
                0,
                0,
                0,
                1,
                0,
                0,
                "[]",
                now,
                now,
                "{}",
            ),
        )
        conn.commit()
