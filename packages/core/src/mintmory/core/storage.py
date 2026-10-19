"""
SQLite storage adapter — the only persistence layer in MintMory.

Responsibilities:
  - Open / create the database from schema.sql
  - CRUD for MemoryRecord, ConceptLink, QuerySession, MemorySummary, QueryResult
  - FTS5 full-text search (via memories_fts virtual table)
  - Vector similarity search (via sqlite-vec, best-effort/optional)
  - Search-around graph traversal (SQL CTEs, depth 1-3)
  - Schema compliance: every public method validated by tests/test_schema.py

Threading: one StorageAdapter per thread / asyncio task that needs SQLite.
For async use, wrap calls in asyncio.to_thread().
WAL mode allows concurrent readers + one writer without blocking.

Implementation note — connection setup (invariant from AGENTS.md §4):
  PRAGMA foreign_keys = ON  must be set on every new connection.
  PRAGMA journal_mode = WAL is set once at schema creation time.

Embeddings are optional (PLAN.md §2). If no embedder is configured, the
``embedding`` column is stored NULL and search degrades to FTS-only. The
sqlite-vec extension is loaded best-effort; vector search only runs when both
an embedder is configured AND the extension loaded successfully.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from mintmory.core import scoring, telemetry
from mintmory.core.entities import extract_entities
from mintmory.core.hybrid_search import collect_scores, fuse_and_search
from mintmory.core.ports import ManifestEntry
from mintmory.core.types import (
    SYMMETRIC_LINK_TYPES,
    TENANT_GLOBAL,
    ConceptLink,
    ConceptLinkType,
    MemoryRecord,
    MemoryStats,
    MemorySummary,
    ProtectedTenantError,
    QueryResult,
    QuerySession,
    SearchAroundSpec,
    SearchRequest,
    SearchResponse,
    Tenant,
    TenantInactiveError,
    TenantMigrationError,
    TenantNotFoundError,
    validate_tenant_id,
)

if TYPE_CHECKING:
    from mintmory.core.embedder import EmbedderProtocol


# Column order for the memories table — kept in one place so INSERT and row
# deserialisation stay in sync.  ``is_note`` is appended after
# ``contradicts_ids`` (same position as in schema.sql §1d) so a fresh-create
# and a migrated DB have identical logical column order.
_MEMORY_COLUMNS: tuple[str, ...] = (
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
    "tenant_id",
)


# Tables that carry a ``tenant_id`` column.  Order is the fresh-DDL order.
_TENANT_TABLES: tuple[str, ...] = (
    "memories",
    "concept_links",
    "memory_summaries",
    "index_manifest",
    "query_sessions",
    "query_results",
)

# Fresh DDL of the three tables the migration rebuilds (kept in lockstep with
# schema.sql; the R3.6 test compares a migrated database against a fresh one).
_TENANT_REBUILD_DDL: dict[str, str] = {
    "concept_links": """
        CREATE TABLE concept_links__tenant_new (
            id                  TEXT PRIMARY KEY,
            source_memory_id    TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            target_memory_id    TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            link_type           TEXT NOT NULL CHECK (link_type IN (
                                    'relates_to','contradicts','refines','supersedes',
                                    'enables','depends_on','similar_to','part_of',
                                    'uses','before','valid_until','annotates'
                                )),
            entity              TEXT NOT NULL DEFAULT '',
            strength            REAL NOT NULL DEFAULT 0.5
                                    CHECK (strength >= 0.0 AND strength <= 1.0),
            confidence          REAL NOT NULL DEFAULT 0.5
                                    CHECK (confidence >= 0.0 AND confidence <= 1.0),
            source              TEXT NOT NULL DEFAULT 'dreaming'
                                    CHECK (source IN ('extraction','inference','dreaming','user')),
            verified            INTEGER NOT NULL DEFAULT 0,
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL,
            tenant_id           TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id),
            UNIQUE (tenant_id, source_memory_id, target_memory_id, link_type)
        )
    """,
    "memory_summaries": """
        CREATE TABLE memory_summaries__tenant_new (
            id              TEXT PRIMARY KEY,
            concept         TEXT NOT NULL,
            summary_text    TEXT NOT NULL,
            memory_count    INTEGER NOT NULL DEFAULT 0,
            is_current      INTEGER NOT NULL DEFAULT 1,
            generated_at    TEXT NOT NULL,
            tenant_id       TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id),
            UNIQUE (tenant_id, concept)
        )
    """,
    "index_manifest": """
        CREATE TABLE index_manifest__tenant_new (
            path          TEXT NOT NULL,
            collection    TEXT NOT NULL,
            size          INTEGER NOT NULL,
            mtime         REAL NOT NULL,
            content_hash  TEXT,
            index_mode    TEXT NOT NULL DEFAULT 'metadata'
                              CHECK (index_mode IN ('metadata','content','vision')),
            memory_ids    TEXT NOT NULL DEFAULT '[]',
            online_only   INTEGER NOT NULL DEFAULT 0,
            last_seen     TEXT NOT NULL,
            tenant_id     TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id),
            PRIMARY KEY (tenant_id, path)
        )
    """,
}

_TENANT_REBUILD_COLUMNS: dict[str, tuple[str, ...]] = {
    "concept_links": (
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
        "tenant_id",
    ),
    "memory_summaries": (
        "id",
        "concept",
        "summary_text",
        "memory_count",
        "is_current",
        "generated_at",
        "tenant_id",
    ),
    "index_manifest": (
        "path",
        "collection",
        "size",
        "mtime",
        "content_hash",
        "index_mode",
        "memory_ids",
        "online_only",
        "last_seen",
        "tenant_id",
    ),
}

_TENANT_REBUILD_INDEXES: dict[str, tuple[str, ...]] = {
    "concept_links": (
        "CREATE INDEX IF NOT EXISTS idx_links_source ON concept_links(source_memory_id, link_type)",
        "CREATE INDEX IF NOT EXISTS idx_links_target ON concept_links(target_memory_id, link_type)",
        "CREATE INDEX IF NOT EXISTS idx_links_type_strength "
        "ON concept_links(link_type, strength DESC)",
        "CREATE INDEX IF NOT EXISTS idx_links_entity ON concept_links(entity) WHERE entity != ''",
    ),
    "memory_summaries": (),
    "index_manifest": (
        "CREATE INDEX IF NOT EXISTS idx_manifest_collection ON index_manifest(collection)",
    ),
}

# Missing tenant indexes, in the order required by R3.2(c).
_TENANT_INDEX_DDL: tuple[tuple[str, str], ...] = (
    (
        "idx_memories_tenant",
        "CREATE INDEX IF NOT EXISTS idx_memories_tenant "
        "ON memories(tenant_id, is_active, is_archived)",
    ),
    (
        "idx_links_tenant",
        "CREATE INDEX IF NOT EXISTS idx_links_tenant "
        "ON concept_links(tenant_id, source_memory_id, link_type)",
    ),
    (
        "idx_sessions_tenant",
        "CREATE INDEX IF NOT EXISTS idx_sessions_tenant "
        "ON query_sessions(tenant_id, concluded, created_at)",
    ),
)


def _utcnow() -> datetime:
    """Naive UTC datetime, matching the model defaults (``datetime.utcnow``)."""
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(dt: datetime | None) -> str | None:
    """Serialise a datetime to an ISO-8601 string (None passes through)."""
    if dt is None:
        return None
    return dt.isoformat()


def _bool(value: object) -> int:
    return 1 if value else 0


def _busy_timeout_ms() -> int:
    """SQLite ``busy_timeout`` in ms — how long a writer waits for a lock before
    raising ``database is locked``. Default 5000ms makes concurrent writers (many
    agents sharing one .db) queue instead of erroring. Override via
    ``MINTMORY_SQLITE_BUSY_TIMEOUT_MS`` (0 = fail immediately, the old behaviour)."""
    try:
        return max(0, int(os.environ.get("MINTMORY_SQLITE_BUSY_TIMEOUT_MS", "5000")))
    except ValueError:
        return 5000


def _sanitise_fts_query(query: str) -> str:
    """
    Turn arbitrary user text into a safe FTS5 MATCH expression.

    FTS5 has its own query syntax (``"`` , ``*`` , ``AND/OR/NOT`` , ``(`` ,
    ``-`` ...). Passing raw user text straight into MATCH can raise
    ``sqlite3.OperationalError: fts5: syntax error``. We tokenise on
    non-alphanumeric characters, wrap each token in double quotes, then OR them
    together so any term may match. Empty / non-alphanumeric input yields an
    empty string (caller treats that as "no FTS phase").

    Tokens of length >= 3 become **prefix** queries (``"video"*``) so a search
    for ``video`` also matches compound/longer tokens like ``videowall`` —
    whole-token FTS otherwise misses partial words. Short tokens stay exact to
    avoid matching almost everything (``"a"*``).

    Adjacent tokens are also OR'd in concatenated (``video wall`` -> ``videowall*``)
    so a space-split compound still matches a single stored token (and vice versa,
    e.g. ``log in`` -> ``login``).
    """
    import re

    tokens = re.findall(r"[A-Za-z0-9]+", query)
    if not tokens:
        return ""
    terms = [f'"{tok}"*' if len(tok) >= 3 else f'"{tok}"' for tok in tokens]
    for first, second in zip(tokens, tokens[1:], strict=False):
        combo = (first + second).lower()
        if len(combo) >= 4:
            terms.append(f'"{combo}"*')
    return " OR ".join(dict.fromkeys(terms))  # dedup, preserve order


def _trigram_match_expr(query: str) -> str:
    """
    Build an FTS5 trigram MATCH expression from arbitrary user text.

    Tokenise on ``[A-Za-z0-9]+``, keep tokens of length >= 3 (the trigram
    tokenizer needs at least three characters to produce any token), lowercase,
    dedup preserving order, wrap each in double quotes, and OR them together.
    No prefix ``*`` — substring matching is inherent to the trigram tokenizer.
    Returns ``""`` when no token qualifies (caller skips the trigram phase).
    """
    import re

    tokens = [tok.lower() for tok in re.findall(r"[A-Za-z0-9]+", query) if len(tok) >= 3]
    if not tokens:
        return ""
    terms = [f'"{tok}"' for tok in dict.fromkeys(tokens)]
    return " OR ".join(terms)


class SqliteBackend:
    """
    SQLite backend wrapping all MintMory persistence operations.

    Implements ``StorageBackend`` structurally (no inheritance required).
    ``connect()`` and ``transaction()`` are intentionally NOT on the port —
    they are SQLite-only surfaces used by cochange, history, and the CLI
    ``history scrub`` command (all SQLite-by-design).

    Usage:
        store = SqliteBackend("/path/to/mintmory.db")
        store.initialise()            # idempotent, creates schema if needed
        store.add_memory(content="...", category="fact")
        results = store.search(SearchRequest(query="parking"))
    """

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        embedder: EmbedderProtocol | None = None,
        enable_trigram: bool = True,
        note_bonus: float | None = None,
        auto_include_cap: int | None = None,
        vector_rrf_weight: float | None = None,
        busy_timeout_ms: int | None = None,
    ) -> None:
        self.db_path = str(db_path)
        self.embedder = embedder
        self._conn: sqlite3.Connection | None = None
        self._vec_loaded: bool = False
        self._enable_trigram: bool = enable_trigram
        self._trigram_loaded: bool = False
        # Personal-notes scoring knobs. ``None`` means "resolve lazily from
        # NoteSettings on first use" — keeps the constructor fast and avoids a
        # circular import at module load time.
        self._note_bonus: float | None = note_bonus
        self._auto_include_cap: int | None = auto_include_cap
        # Weighted RRF fusion knob. ``None`` means "resolve lazily from
        # SearchSettings on first use" — keeps the constructor fast and avoids a
        # circular import at module load time.
        self._vector_rrf_weight: float | None = vector_rrf_weight
        # busy_timeout_ms: explicit override (from factory/settings). None means
        # "read from MINTMORY_SQLITE_BUSY_TIMEOUT_MS env var" (legacy path).
        self._busy_timeout_ms_override: int | None = busy_timeout_ms
        # Re-entrant transaction scope (multi-tenancy-writes task 1). The RLock
        # makes ``transaction()`` re-entrant in one thread and serialises writers
        # from different threads on the shared connection; ``_tx_depth`` lets a
        # nested block join the outermost block instead of committing early.
        self._tx_lock = threading.RLock()
        self._tx_depth = 0

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            # Concurrent-writer safety (multi-agent): wait for a lock instead of
            # immediately raising "database is locked". WAL already lets readers
            # run during a write; this makes competing writers queue.
            timeout = (
                self._busy_timeout_ms_override
                if self._busy_timeout_ms_override is not None
                else _busy_timeout_ms()
            )
            self._conn.execute(f"PRAGMA busy_timeout = {timeout}")
            self._load_vec_extension(self._conn)
        return self._conn

    def _load_vec_extension(self, conn: sqlite3.Connection) -> None:
        """Best-effort load of the sqlite-vec loadable extension (PLAN.md §2)."""
        try:
            conn.enable_load_extension(True)
            import sqlite_vec

            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            self._vec_loaded = True
        except Exception:
            self._vec_loaded = False

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Re-entrant transaction scope over the shared connection.

        The outermost entry commits on a clean exit and rolls back + re-raises
        on any exception; a nested entry joins the outer block and neither
        commits nor rolls back (if the caller catches a nested exception, the
        outermost block commits the statements that succeeded — no savepoints).
        The lock also keeps a second thread's write from interleaving with this
        thread's uncommitted work on the shared connection.
        """
        with self._tx_lock:
            conn = self.connect()
            self._tx_depth += 1
            try:
                yield conn
            except BaseException:
                self._tx_depth -= 1
                if self._tx_depth == 0:
                    conn.rollback()
                raise
            else:
                self._tx_depth -= 1
                if self._tx_depth == 0:
                    conn.commit()

    def initialise(self) -> None:
        """
        Create all tables, indexes, and FTS5 triggers from schema.sql.
        Idempotent — safe to call on every startup.
        """
        schema_path = Path(__file__).parent / "schema.sql"
        ddl = schema_path.read_text()
        conn = self.connect()
        conn.executescript(ddl)
        conn.commit()
        self._ensure_trigram(conn)
        self._ensure_is_note_column(conn)
        self._ensure_index_mode_vision(conn)
        self._ensure_tenant_columns(conn)

    def _ensure_trigram(self, conn: sqlite3.Connection) -> None:
        """
        Best-effort creation of the ``memories_trigram`` FTS5 substring index.

        Uses the ``trigram`` tokenizer, which enables substring matching (e.g.
        ``wall`` matches ``firewall``). The whole body is wrapped in
        ``try/except sqlite3.OperationalError`` so a SQLite build without trigram
        support degrades gracefully (search falls back to FTS + vector). When
        ``enable_trigram`` is False this is a no-op.

        The table is **standalone** (it stores its own copy of the content) with
        rowid-based delete triggers. An earlier design used an external-content
        table (``content='memories'``) whose ``'delete'`` command corrupts the
        index after a ``'rebuild'`` backfill ("database disk image is malformed"
        on the next UPDATE). We migrate any such legacy table away.
        """
        if not self._enable_trigram:
            self._trigram_loaded = False
            return
        try:
            legacy = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='memories_trigram'"
            ).fetchone()
            if legacy is not None and "content=" in (legacy["sql"] or "").replace(" ", "").lower():
                conn.executescript(
                    "DROP TRIGGER IF EXISTS memories_trigram_insert;"
                    "DROP TRIGGER IF EXISTS memories_trigram_update;"
                    "DROP TRIGGER IF EXISTS memories_trigram_delete;"
                    "DROP TABLE IF EXISTS memories_trigram;"
                )
            conn.executescript(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_trigram
                USING fts5(content, tokenize='trigram');

                CREATE TRIGGER IF NOT EXISTS memories_trigram_insert AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_trigram(rowid, content) VALUES (new.rowid, new.content);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_trigram_update AFTER UPDATE ON memories BEGIN
                    DELETE FROM memories_trigram WHERE rowid = old.rowid;
                    INSERT INTO memories_trigram(rowid, content) VALUES (new.rowid, new.content);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_trigram_delete AFTER DELETE ON memories BEGIN
                    DELETE FROM memories_trigram WHERE rowid = old.rowid;
                END;
                """
            )
            trigram_count = conn.execute("SELECT count(*) AS c FROM memories_trigram").fetchone()[
                "c"
            ]
            memory_count = conn.execute("SELECT count(*) AS c FROM memories").fetchone()["c"]
            if trigram_count == 0 and memory_count > 0:
                conn.execute(
                    "INSERT INTO memories_trigram(rowid, content) "
                    "SELECT rowid, content FROM memories"
                )
            conn.commit()
            self._trigram_loaded = True
        except sqlite3.OperationalError:
            self._trigram_loaded = False

    def _ensure_is_note_column(self, conn: sqlite3.Connection) -> None:
        """Best-effort, idempotent ALTER TABLE adding ``memories.is_note``.

        Fresh databases already have the column from schema.sql; this backfills it
        on pre-existing databases created before personal-notes. Uses the same
        PRAGMA table_info introspection + try/except pattern as the trigram
        migration: a failure (locked/old SQLite) degrades to "no notes" rather than
        crashing startup. Every pre-existing row gets ``is_note = 0`` (the column
        default), i.e. all existing memories remain non-notes. Idempotent: the
        PRAGMA check makes a re-run a no-op.
        """
        try:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(memories)").fetchall()}
            if "is_note" not in cols:
                conn.execute("ALTER TABLE memories ADD COLUMN is_note INTEGER NOT NULL DEFAULT 0")
                conn.commit()
        except sqlite3.OperationalError:
            pass

    def _ensure_index_mode_vision(self, conn: sqlite3.Connection) -> None:
        """Best-effort, idempotent widening of index_manifest.index_mode to allow 'vision'.

        Fresh DBs already allow it from schema.sql (CHECK includes 'vision').  On a
        pre-existing DB whose CHECK only allows ('metadata','content'), rebuild the
        table with the wider CHECK: CREATE new → INSERT SELECT → DROP old → RENAME.
        Detects the need by inspecting the stored CREATE sql for the table; a re-run
        after migration is a no-op.  Any sqlite3.OperationalError degrades gracefully
        — callers still write 'metadata'/'content', which remain legal either way.
        """
        try:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='index_manifest'"
            ).fetchone()
            if row is None:
                # Table does not exist yet — schema.sql will create it with 'vision'.
                return
            stored_sql: str = row["sql"] or ""
            # Migrate only when the stored DDL has the old two-value CHECK and lacks 'vision'.
            if "'vision'" in stored_sql or '"vision"' in stored_sql:
                return  # already wide — no-op
            if "'metadata'" not in stored_sql and '"metadata"' not in stored_sql:
                return  # unexpected DDL shape — leave untouched
            # Rebuild: create a shadow table with the wider CHECK, copy all rows,
            # drop the old table, rename the shadow.
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS index_manifest_new (
                    path          TEXT NOT NULL,
                    collection    TEXT NOT NULL,
                    size          INTEGER NOT NULL,
                    mtime         REAL NOT NULL,
                    content_hash  TEXT,
                    index_mode    TEXT NOT NULL DEFAULT 'metadata'
                                      CHECK (index_mode IN ('metadata','content','vision')),
                    memory_ids    TEXT NOT NULL DEFAULT '[]',
                    online_only   INTEGER NOT NULL DEFAULT 0,
                    last_seen     TEXT NOT NULL,
                    tenant_id     TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id),
                    PRIMARY KEY (tenant_id, path)
                );
                INSERT OR IGNORE INTO index_manifest_new
                    SELECT path, collection, size, mtime, content_hash,
                           index_mode, memory_ids, online_only, last_seen, 'global'
                    FROM index_manifest;
                DROP TABLE index_manifest;
                ALTER TABLE index_manifest_new RENAME TO index_manifest;
                CREATE INDEX IF NOT EXISTS idx_manifest_collection
                    ON index_manifest(collection);
                """
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass  # degrade gracefully — 'metadata'/'content' writes remain valid

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> bytes | None:
        """Compute an embedding blob for ``text`` iff an embedder is configured."""
        if self.embedder is None:
            return None
        vectors = self.embedder.embed_batch([text])
        if not vectors:
            return None
        vec = np.asarray(vectors[0], dtype=np.float32)
        return vec.tobytes()

    def vector_search_available(self) -> bool:
        """Return True iff an embedder is configured AND the sqlite-vec extension loaded."""
        return self.embedder is not None and self._vec_loaded

    # Back-compat shim (one-release); callers should use vector_search_available().
    _vector_search_available = vector_search_available

    # ------------------------------------------------------------------
    # MemoryRecord CRUD
    # ------------------------------------------------------------------

    def _memory_row_values(self, record: MemoryRecord, embedding: bytes | None) -> tuple[Any, ...]:
        return (
            record.id,
            record.content,
            record.category.value,
            json.dumps(record.entity_ids),
            embedding,
            record.confidence,
            record.source.value,
            _bool(record.verified),
            _iso(record.valid_from),
            _iso(record.valid_until),
            record.usefulness_score,
            record.staleness_score,
            record.reinforcement_count,
            record.retrieval_count,
            _bool(record.is_stale),
            _bool(record.is_active),
            _bool(record.is_archived),
            record.superseded_by,
            _bool(record.flagged_for_review),
            json.dumps(record.contradicts_ids),
            _bool(record.is_note),  # appended after contradicts_ids — lockstep with _MEMORY_COLUMNS
            _iso(record.created_at),
            _iso(record.updated_at),
            _iso(record.last_accessed_at),
            json.dumps(record.metadata),
            record.tenant_id,
        )

    @telemetry.counts_added
    @telemetry.traced("mintmory.add_memory")
    def add_memory(
        self,
        record: MemoryRecord | None = None,
        **fields: Any,
    ) -> MemoryRecord:
        """
        Insert a new memory and return the stored record (round-trip fidelity).

        If ``record`` is None, builds ``MemoryRecord(**fields)`` (Pydantic coerces
        raw string ``category``/``source`` into enum members). Entity extraction
        runs over the content and populates ``entity_ids`` when the caller did not
        supply a non-empty list. An embedding is computed + stored iff an embedder
        is configured.
        """
        if record is None:
            record = MemoryRecord(**fields)

        if not record.entity_ids:
            record.entity_ids = extract_entities(record.content)

        embedding = self._embed(record.content)
        values = self._memory_row_values(record, embedding)
        placeholders = ", ".join("?" for _ in _MEMORY_COLUMNS)
        columns = ", ".join(_MEMORY_COLUMNS)

        with self.transaction() as conn:
            self._assert_tenant_writable(conn, record.tenant_id)
            conn.execute(
                f"INSERT INTO memories ({columns}) VALUES ({placeholders})",
                values,
            )
        return record

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            content=row["content"],
            category=row["category"],
            entity_ids=row["entity_ids"],
            confidence=row["confidence"],
            source=row["source"],
            verified=bool(row["verified"]),
            valid_from=row["valid_from"],
            valid_until=row["valid_until"],
            usefulness_score=row["usefulness_score"],
            staleness_score=row["staleness_score"],
            reinforcement_count=row["reinforcement_count"],
            retrieval_count=row["retrieval_count"],
            is_stale=bool(row["is_stale"]),
            is_active=bool(row["is_active"]),
            is_archived=bool(row["is_archived"]),
            superseded_by=row["superseded_by"],
            flagged_for_review=bool(row["flagged_for_review"]),
            contradicts_ids=row["contradicts_ids"],
            is_note=bool(row["is_note"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_accessed_at=row["last_accessed_at"],
            metadata=json.loads(row["metadata"]),
            tenant_id=row["tenant_id"],
        )

    def get_memory(self, memory_id: str) -> MemoryRecord | None:
        """Fetch a single memory by ID. Returns None if not found."""
        conn = self.connect()
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def update_memory(self, memory_id: str, **fields: object) -> MemoryRecord:
        """
        Partial update — only provided fields are changed. ``updated_at`` is
        always refreshed. If ``content`` changes, entity extraction re-runs (and
        the embedding is recomputed when an embedder is configured) unless the
        caller explicitly supplies ``entity_ids``.
        """
        existing = self.get_memory(memory_id)
        if existing is None:
            raise KeyError(f"memory {memory_id!r} not found")

        data = existing.model_dump()
        data.update(fields)
        updated = MemoryRecord(**data)
        updated.updated_at = _utcnow()

        content_changed = "content" in fields and fields["content"] != existing.content
        if content_changed and "entity_ids" not in fields:
            updated.entity_ids = extract_entities(updated.content)

        embedding = self._embed(updated.content) if content_changed else None
        sets = [
            "content = ?",
            "category = ?",
            "entity_ids = ?",
            "confidence = ?",
            "source = ?",
            "verified = ?",
            "valid_from = ?",
            "valid_until = ?",
            "usefulness_score = ?",
            "staleness_score = ?",
            "reinforcement_count = ?",
            "retrieval_count = ?",
            "is_stale = ?",
            "is_active = ?",
            "is_archived = ?",
            "superseded_by = ?",
            "flagged_for_review = ?",
            "contradicts_ids = ?",
            "is_note = ?",  # appended after contradicts_ids — lockstep with _MEMORY_COLUMNS
            "updated_at = ?",
            "last_accessed_at = ?",
            "metadata = ?",
        ]
        params: list[Any] = [
            updated.content,
            updated.category.value,
            json.dumps(updated.entity_ids),
            updated.confidence,
            updated.source.value,
            _bool(updated.verified),
            _iso(updated.valid_from),
            _iso(updated.valid_until),
            updated.usefulness_score,
            updated.staleness_score,
            updated.reinforcement_count,
            updated.retrieval_count,
            _bool(updated.is_stale),
            _bool(updated.is_active),
            _bool(updated.is_archived),
            updated.superseded_by,
            _bool(updated.flagged_for_review),
            json.dumps(updated.contradicts_ids),
            _bool(updated.is_note),
            _iso(updated.updated_at),
            _iso(updated.last_accessed_at),
            json.dumps(updated.metadata),
        ]
        if content_changed:
            sets.append("embedding = ?")
            params.append(embedding)
        params.append(memory_id)

        with self.transaction() as conn:
            stored_tenant = self._stored_tenant(conn, memory_id)
            if stored_tenant is not None:
                self._assert_tenant_writable(conn, stored_tenant)
            conn.execute(
                f"UPDATE memories SET {', '.join(sets)} WHERE id = ?",
                params,
            )
        result = self.get_memory(memory_id)
        assert result is not None  # just updated
        return result

    def archive_memory(self, memory_id: str) -> None:
        """Soft delete: set is_archived=1, is_active=0, refresh updated_at."""
        with self.transaction() as conn:
            stored_tenant = self._stored_tenant(conn, memory_id)
            if stored_tenant is not None:
                self._assert_tenant_writable(conn, stored_tenant)
                conn.execute(
                    "UPDATE memories SET is_archived = 1, is_active = 0, updated_at = ? "
                    "WHERE id = ?",
                    (_iso(_utcnow()), memory_id),
                )

    # ------------------------------------------------------------------
    # Index manifest — per-path state for recurrent tree indexing
    # ------------------------------------------------------------------
    def manifest_get(self, path: str, *, tenant_id: str = "global") -> ManifestEntry | None:
        """Return the manifest row for ``(tenant_id, path)`` (absolute), or None."""
        row: sqlite3.Row | None = (
            self.connect()
            .execute(
                "SELECT * FROM index_manifest WHERE tenant_id = ? AND path = ?",
                (tenant_id, path),
            )
            .fetchone()
        )
        if row is None:
            return None
        return ManifestEntry(
            path=row["path"],
            collection=row["collection"],
            size=row["size"],
            mtime=row["mtime"],
            content_hash=row["content_hash"],
            index_mode=row["index_mode"],
            memory_ids=row["memory_ids"],
            online_only=row["online_only"],
            last_seen=row["last_seen"],
            tenant_id=row["tenant_id"],
        )

    def manifest_upsert(
        self,
        path: str,
        collection: str,
        *,
        size: int,
        mtime: float,
        online_only: bool,
        index_mode: str,
        memory_ids: list[str],
        content_hash: str | None = None,
        tenant_id: str = "global",
    ) -> None:
        """Insert or replace the manifest row for ``(tenant_id, path)``."""
        with self.transaction() as conn:
            self._assert_tenant_writable(conn, tenant_id)
            conn.execute(
                "INSERT INTO index_manifest "
                "(path, collection, size, mtime, content_hash, index_mode, "
                " memory_ids, online_only, last_seen, tenant_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(tenant_id, path) DO UPDATE SET "
                "collection=excluded.collection, size=excluded.size, mtime=excluded.mtime, "
                "content_hash=excluded.content_hash, index_mode=excluded.index_mode, "
                "memory_ids=excluded.memory_ids, online_only=excluded.online_only, "
                "last_seen=excluded.last_seen",
                (
                    path,
                    collection,
                    size,
                    mtime,
                    content_hash,
                    index_mode,
                    json.dumps(memory_ids),
                    _bool(online_only),
                    _iso(_utcnow()),
                    tenant_id,
                ),
            )

    def manifest_paths(self, collection: str, *, tenant_id: str = "global") -> set[str]:
        """All paths currently tracked under ``collection`` for ``tenant_id``."""
        rows = (
            self.connect()
            .execute(
                "SELECT path FROM index_manifest WHERE tenant_id = ? AND collection = ?",
                (tenant_id, collection),
            )
            .fetchall()
        )
        return {row["path"] for row in rows}

    def manifest_delete(self, path: str, *, tenant_id: str = "global") -> None:
        """Drop the ``(tenant_id, path)`` manifest row (memories are archived separately)."""
        with self.transaction() as conn:
            self._assert_tenant_writable(conn, tenant_id)
            conn.execute(
                "DELETE FROM index_manifest WHERE tenant_id = ? AND path = ?",
                (tenant_id, path),
            )

    def apply_feedback(self, memory_id: str, useful: bool, stale: bool) -> None:
        """Per-memory feedback primitive (PLAN.md §1b).

        useful -> usefulness_score += USEFUL_INCREMENT (cap 10), reinforcement_count += 1.
        stale  -> staleness_score  += STALE_INCREMENT  (cap 10).
                  **Exception**: when the row is a note (is_note=1) a stale vote
                  sets ``flagged_for_review = 1`` instead of incrementing
                  staleness_score/is_stale — the note is contested and needs human
                  review. The useful path is unchanged for notes (they can still be
                  reinforced). Non-note stale handling is byte-identical to today.
        Sets is_stale=1 when staleness_score >= STALENESS_THRESHOLD (7.0).
        Always refreshes updated_at. Clamping via scoring.increment_*.
        """
        with self.transaction() as txn:
            row = txn.execute(
                "SELECT usefulness_score, staleness_score, reinforcement_count, is_note, "
                "tenant_id FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"memory {memory_id!r} not found")
            self._assert_tenant_writable(txn, row["tenant_id"])

            usefulness = row["usefulness_score"]
            staleness = row["staleness_score"]
            reinforcement = row["reinforcement_count"]
            note = bool(row["is_note"])

            if useful:
                usefulness = scoring.increment_usefulness(usefulness, scoring.USEFUL_INCREMENT)
                reinforcement += 1

            flag = 0
            if stale:
                if note:
                    # A contested note is flagged for human review; staleness unchanged.
                    flag = 1
                else:
                    staleness = scoring.increment_staleness(staleness, scoring.STALE_INCREMENT)

            is_stale = 1 if staleness >= scoring.STALENESS_THRESHOLD else 0

            txn.execute(
                "UPDATE memories SET usefulness_score = ?, staleness_score = ?, "
                "reinforcement_count = ?, is_stale = ?, updated_at = ?, "
                "flagged_for_review = CASE WHEN ? = 1 THEN 1 ELSE flagged_for_review END "
                "WHERE id = ?",
                (
                    usefulness,
                    staleness,
                    reinforcement,
                    is_stale,
                    _iso(_utcnow()),
                    flag,
                    memory_id,
                ),
            )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _resolve_vector_rrf_weight(self) -> float:
        """Lazily resolve the vector RRF weight from SearchSettings on first use.

        Mirrors the ``_note_bonus`` / ``_auto_include_cap`` lazy-resolve idiom:
        import inside the method to avoid a circular import at module load time.
        """
        if self._vector_rrf_weight is None:
            from mintmory.core.config import SearchSettings  # noqa: PLC0415

            self._vector_rrf_weight = SearchSettings().vector_rrf_weight
        return self._vector_rrf_weight

    def _fts_scores(self, query: str, limit: int) -> dict[str, float]:
        """Run FTS5 MATCH and return {memory_id: bm25-derived score (higher=better)}."""
        match_expr = _sanitise_fts_query(query)
        if not match_expr:
            return {}
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT m.id AS id, bm25(memories_fts) AS rank "
                "FROM memories_fts "
                "JOIN memories m ON m.rowid = memories_fts.rowid "
                "WHERE memories_fts MATCH ? "
                "ORDER BY rank "
                "LIMIT ?",
                (match_expr, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        # bm25 returns lower = more relevant; negate so higher = better.
        return {row["id"]: -float(row["rank"]) for row in rows}

    def _trigram_scores(self, query: str, limit: int) -> dict[str, float]:
        """Run the trigram FTS5 MATCH and return {memory_id: score (higher=better)}."""
        if not self._trigram_loaded:
            return {}
        match_expr = _trigram_match_expr(query)
        if not match_expr:
            return {}
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT m.id AS id, bm25(memories_trigram) AS rank "
                "FROM memories_trigram "
                "JOIN memories m ON m.rowid = memories_trigram.rowid "
                "WHERE memories_trigram MATCH ? "
                "ORDER BY rank "
                "LIMIT ?",
                (match_expr, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        # bm25 returns lower = more relevant; negate so higher = better.
        return {row["id"]: -float(row["rank"]) for row in rows}

    def _vector_scores(
        self, query: str, query_embedding: np.ndarray | None, limit: int
    ) -> dict[str, float]:
        """Vector phase of hybrid search: brute-force cosine over stored embeddings.

        Returns {memory_id: -distance} (higher = better); {} when no embedder /
        sqlite-vec / embedding is available. NULL distances (mixed-dimension
        embeddings) are skipped. Isolated behind this method so an ANN backend can
        replace the scan later without touching search()/fusion (see ADR-0006).
        """
        if not self.vector_search_available():
            return {}
        blob: bytes | None
        if query_embedding is not None:
            blob = np.asarray(query_embedding, dtype=np.float32).tobytes()
        else:
            blob = self._embed(query)
        if blob is None:
            return {}
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT id, vec_distance_cosine(embedding, ?) AS dist "
                "FROM memories WHERE embedding IS NOT NULL "
                "ORDER BY dist ASC LIMIT ?",
                (blob, limit),
            ).fetchall()
            # dist is NULL when a stored embedding has a different
            # dimension than the query (mixed embedders in one DB) —
            # skip those rows rather than crashing on float(None); they
            # still contribute via FTS.
            return {row["id"]: -float(row["dist"]) for row in rows if row["dist"] is not None}
        except sqlite3.OperationalError:
            return {}

    @telemetry.traced("mintmory.search")
    @telemetry.timed_phase("total")
    def search(
        self,
        request: SearchRequest,
        query_embedding: np.ndarray | None = None,
    ) -> SearchResponse:
        """
        Hybrid search pipeline (PLAN.md §3): FTS5 + optional vector phase merged
        with RRF, filtered, scored, sorted, limited; optional graph union; a
        QuerySession + query_results are recorded and retrieval counters bumped.

        Fusion/scoring/session logic lives in ``hybrid_search.fuse_and_search``
        so it is shared identically with PostgresBackend.
        """
        # Wider candidate pool than the final limit so filtering + scoring have
        # room to reorder before truncation.
        pool = max(request.limit * 5, 50)

        fts_scores, trigram_scores, vec_scores = collect_scores(
            fts_fn=lambda: self._fts_scores(request.query, pool),
            trigram_fn=lambda: self._trigram_scores(request.query, pool),
            vector_fn=lambda: self._vector_scores(request.query, query_embedding, pool),
        )

        # Lazily resolve note_bonus / auto_include_cap from NoteSettings on first
        # use — import inside the call to avoid circular imports at module load time.
        if self._note_bonus is None:
            from mintmory.core.config import NoteSettings  # noqa: PLC0415

            self._note_bonus = NoteSettings().note_bonus
        if self._auto_include_cap is None:
            from mintmory.core.config import NoteSettings  # noqa: PLC0415

            self._auto_include_cap = NoteSettings().auto_include_cap

        return fuse_and_search(
            request=request,
            fts_scores=fts_scores,
            trigram_scores=trigram_scores,
            vector_scores=vec_scores,
            vector_rrf_weight=self._resolve_vector_rrf_weight(),
            load_memories_fn=self._load_memories,
            bump_retrieval_fn=self._bump_retrieval,
            create_session_fn=self.create_session,
            record_query_results_fn=self.record_query_results,
            get_annotating_notes_fn=self.get_annotating_notes,
            search_around_fn=self.search_around,
            note_bonus=self._note_bonus,
            auto_include_cap=self._auto_include_cap,
            now=_utcnow(),
        )

    def _load_memories(self, ids: list[str]) -> list[MemoryRecord]:
        if not ids:
            return []
        conn = self.connect()
        placeholders = ", ".join("?" for _ in ids)
        rows = conn.execute(f"SELECT * FROM memories WHERE id IN ({placeholders})", ids).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def get_annotating_notes(self, memory_id: str, cap: int) -> list[MemoryRecord]:
        """Return up to ``cap`` notes that ANNOTATE ``memory_id``.

        Performs a reverse traversal of the asymmetric ANNOTATES edge: the note is
        the ``source_memory_id``, ``memory_id`` the ``target_memory_id``. Notes are
        ordered by link strength DESC then created_at DESC. Archived notes are
        excluded. ``cap == 0`` returns [] immediately.
        """
        if cap <= 0:
            return []
        conn = self.connect()
        rows = conn.execute(
            "SELECT m.* FROM concept_links l "
            "JOIN memories m ON m.id = l.source_memory_id "
            "WHERE l.target_memory_id = ? AND l.link_type = ? "
            "AND m.is_note = 1 AND m.is_archived = 0 "
            "ORDER BY l.strength DESC, m.created_at DESC "
            "LIMIT ?",
            (memory_id, ConceptLinkType.ANNOTATES.value, cap),
        ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def get_annotating_descriptions(self, memory_id: str, cap: int) -> list[MemoryRecord]:
        """Return up to ``cap`` ACTIVE image_description memories that ANNOTATE ``memory_id``.

        Performs a reverse traversal of the ANNOTATES edge (MM-16 pattern): the
        description is the ``source_memory_id``, ``memory_id`` the
        ``target_memory_id``.  Filters ``m.is_note = 0`` AND ``m.is_archived = 0``
        AND ``json_extract(m.metadata, '$.kind') = 'image_description'``.  Ordered
        by created_at DESC.  ``cap <= 0`` returns [].

        This is the description analogue of ``get_annotating_notes`` and does NOT
        overlap it: notes filter ``is_note = 1``; descriptions filter ``is_note = 0``
        with an explicit ``kind`` predicate.
        """
        if cap <= 0:
            return []
        conn = self.connect()
        rows = conn.execute(
            "SELECT m.* FROM concept_links l "
            "JOIN memories m ON m.id = l.source_memory_id "
            "WHERE l.target_memory_id = ? AND l.link_type = ? "
            "AND m.is_note = 0 AND m.is_archived = 0 "
            "AND json_extract(m.metadata, '$.kind') = 'image_description' "
            "ORDER BY m.created_at DESC "
            "LIMIT ?",
            (memory_id, ConceptLinkType.ANNOTATES.value, cap),
        ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def find_image_file_record(self, path_or_rel: str) -> MemoryRecord | None:
        """Find the most recent ACTIVE file-record matching ``path_or_rel`` (path or rel).

        A file-record is distinguished from an image_description by the absence of a
        ``kind`` key (or its value not being ``'image_description'``).  Matches on
        ``metadata['path']`` first; falls back to ``metadata['rel']``.  Returns
        ``None`` when no matching active record is found.

        Used by ``image_caption_put`` to resolve a path argument to the file-record
        it should ANNOTATE (§8c of the design contract).
        """
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM memories "
            "WHERE is_archived = 0 "
            "AND (json_extract(metadata, '$.path') = ? OR json_extract(metadata, '$.rel') = ?) "
            "AND json_extract(metadata, '$.kind') IS NULL "
            # §8c: match an IMAGE file-record (ext in the image set), so LIMIT 1
            # picks the most-recent image rather than any same-path record.
            "AND lower(json_extract(metadata, '$.ext')) IN "
            "('.jpg','.jpeg','.png','.gif','.webp','.bmp','.svg') "
            "ORDER BY created_at DESC LIMIT 1",
            (path_or_rel, path_or_rel),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def anchor_candidates(self, about: str, limit: int = 5) -> list[tuple[float, MemoryRecord]]:
        """Side-effect-free candidate lookup for note anchoring.

        Reuses the hybrid score sources (FTS5 + trigram + vector) and min-max
        normalisation from ``search()`` but does NOT create a QuerySession, does NOT
        record query_results, and does NOT bump retrieval counters. Returns
        ``(normalised_score, record)`` pairs sorted best-first.
        """
        from mintmory.core.hybrid_search import fuse_and_rank  # noqa: PLC0415

        pool = max(limit * 5, 50)
        fts_scores = self._fts_scores(about, pool)
        vec_scores = self._vector_scores(about, None, pool)
        trigram_scores = self._trigram_scores(about, pool)

        return fuse_and_rank(
            fts_scores=fts_scores,
            trigram_scores=trigram_scores,
            vector_scores=vec_scores,
            vector_rrf_weight=self._resolve_vector_rrf_weight(),
            load_memories_fn=self._load_memories,
            limit=limit,
        )

    def list_notes(
        self,
        *,
        entity: str | None = None,
        anchor_substr: str | None = None,
        upcoming: bool = False,
        overdue: bool = False,
        include_archived: bool = False,
        limit: int = 50,
        now: datetime | None = None,
    ) -> list[MemoryRecord]:
        """SQL backing for ``notes_list`` (design §5c). Always filters is_note = 1.

        entity:         case-insensitive membership in entity_ids (post-filter in
                        Python, same predicate as ``hybrid_search._passes_filter``).
        anchor_substr:  case-insensitive substring of metadata['anchor'] (post-filter).
        upcoming:       WHERE valid_from > now ORDER BY valid_from ASC (soonest first).
        overdue:        WHERE valid_from IS NOT NULL AND valid_from < now
                        AND is_archived = 0 ORDER BY valid_from ASC (most overdue first).
        neither:        ORDER BY created_at DESC; exclude archived unless include_archived.
        ``upcoming`` and ``overdue`` both True is rejected at the ``notes_list`` layer
        before reaching here, but this method handles the constraint defensively.
        """
        effective_now = now or _utcnow()
        now_iso = _iso(effective_now)

        conn = self.connect()
        sql = "SELECT * FROM memories WHERE is_note = 1"
        params: list[Any] = []

        if upcoming:
            sql += " AND valid_from > ?"
            params.append(now_iso)
            sql += " ORDER BY valid_from ASC"
        elif overdue:
            sql += " AND valid_from IS NOT NULL AND valid_from < ? AND is_archived = 0"
            params.append(now_iso)
            sql += " ORDER BY valid_from ASC"
        else:
            if not include_archived:
                sql += " AND is_archived = 0"
            sql += " ORDER BY created_at DESC"

        sql += " LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        records = [self._row_to_memory(row) for row in rows]

        # Post-filter entity and anchor_substr in Python — consistent with
        # ``hybrid_search._passes_filter``'s entity check.
        if entity is not None:
            entity_lower = entity.lower()
            records = [r for r in records if entity_lower in {e.lower() for e in r.entity_ids}]
        if anchor_substr is not None:
            anchor_lower = anchor_substr.lower()
            records = [
                r for r in records if anchor_lower in str(r.metadata.get("anchor", "")).lower()
            ]

        return records

    def supersede_memory(self, memory_id: str, by_id: str) -> None:
        """Mark ``memory_id`` superseded by ``by_id``.

        Sets superseded_by=by_id, is_active=0, is_archived=1 and refreshes
        updated_at. Used by note-authority contradiction resolution (design §6b)
        so the supersede lineage is recorded consistently, matching SUPERSEDES
        semantics. Does NOT add a SUPERSEDES concept_link — that is the caller's
        responsibility when needed.
        """
        with self.transaction() as conn:
            stored_tenant = self._stored_tenant(conn, memory_id)
            if stored_tenant is not None:
                self._assert_tenant_writable(conn, stored_tenant)
                conn.execute(
                    "UPDATE memories SET superseded_by = ?, is_active = 0, is_archived = 1, "
                    "updated_at = ? WHERE id = ?",
                    (by_id, _iso(_utcnow()), memory_id),
                )

    def _bump_retrieval(self, ids: list[str], now: datetime) -> None:
        if not ids:
            return
        placeholders = ", ".join("?" for _ in ids)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE memories SET retrieval_count = retrieval_count + 1, "
                f"last_accessed_at = ? WHERE id IN ({placeholders}) "
                f"AND tenant_id IN (SELECT id FROM tenants WHERE is_active = 1)",
                [_iso(now), *ids],
            )

    @telemetry.traced("mintmory.search_around")
    @telemetry.timed_phase("graph")
    def search_around(
        self,
        anchor_ids: list[str],
        spec: SearchAroundSpec,
    ) -> list[str]:
        """
        Graph traversal from anchor_ids via concept_links (PLAN.md §3).

        Recursive CTE honouring spec.link_types (empty = all), spec.depth (1-3),
        spec.min_strength. Follows source->target always, and for symmetric link
        types also target->source. Anchors are excluded from the result; dedup'd.
        """
        if not anchor_ids:
            return []

        conn = self.connect()
        anchor_set = set(anchor_ids)
        sym_values = {lt.value for lt in SYMMETRIC_LINK_TYPES}
        type_filter: set[str] | None = (
            {lt.value for lt in spec.link_types} if spec.link_types else None
        )

        # BFS over the link graph up to spec.depth, applying min_strength and the
        # optional link-type filter, following the symmetric reverse edge too.
        visited: set[str] = set(anchor_ids)
        frontier: set[str] = set(anchor_ids)
        result: set[str] = set()

        for _ in range(spec.depth):
            if not frontier:
                break
            placeholders = ", ".join("?" for _ in frontier)
            params: list[Any] = list(frontier)
            sql = (
                f"SELECT source_memory_id, target_memory_id, link_type "
                f"FROM concept_links "
                f"WHERE strength >= ? AND "
                f"(source_memory_id IN ({placeholders}) "
                f" OR target_memory_id IN ({placeholders}))"
            )
            params = [spec.min_strength, *frontier, *frontier]
            rows = conn.execute(sql, params).fetchall()

            next_frontier: set[str] = set()
            for row in rows:
                src = row["source_memory_id"]
                tgt = row["target_memory_id"]
                ltype = row["link_type"]
                if type_filter is not None and ltype not in type_filter:
                    continue
                neighbours: list[str] = []
                if src in frontier:
                    neighbours.append(tgt)
                if tgt in frontier and ltype in sym_values:
                    neighbours.append(src)
                for nb in neighbours:
                    if nb not in visited:
                        next_frontier.add(nb)
                    if nb not in anchor_set:
                        result.add(nb)
            visited |= next_frontier
            frontier = next_frontier

        return list(result)

    # ------------------------------------------------------------------
    # ConceptLink
    # ------------------------------------------------------------------

    def add_link(self, link: ConceptLink) -> ConceptLink:
        """INSERT OR IGNORE on UNIQUE (source, target, link_type). Returns the link."""
        with self.transaction() as conn:
            self._assert_tenant_writable(conn, link.tenant_id)
            conn.execute(
                "INSERT OR IGNORE INTO concept_links "
                "(id, source_memory_id, target_memory_id, link_type, entity, "
                "strength, confidence, source, verified, created_at, updated_at, tenant_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    link.id,
                    link.source_memory_id,
                    link.target_memory_id,
                    link.link_type.value,
                    link.entity,
                    link.strength,
                    link.confidence,
                    link.source.value,
                    _bool(link.verified),
                    _iso(link.created_at),
                    _iso(link.updated_at),
                    link.tenant_id,
                ),
            )
        return link

    def _row_to_link(self, row: sqlite3.Row) -> ConceptLink:
        return ConceptLink(
            id=row["id"],
            source_memory_id=row["source_memory_id"],
            target_memory_id=row["target_memory_id"],
            link_type=row["link_type"],
            entity=row["entity"],
            strength=row["strength"],
            confidence=row["confidence"],
            source=row["source"],
            verified=bool(row["verified"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            tenant_id=row["tenant_id"],
        )

    def get_links(
        self,
        memory_id: str,
        link_type: ConceptLinkType | None = None,
    ) -> list[ConceptLink]:
        """Return all links where memory_id is source OR target."""
        conn = self.connect()
        sql = "SELECT * FROM concept_links WHERE (source_memory_id = ? OR target_memory_id = ?)"
        params: list[Any] = [memory_id, memory_id]
        if link_type is not None:
            sql += " AND link_type = ?"
            params.append(link_type.value)
        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_link(row) for row in rows]

    # ------------------------------------------------------------------
    # QuerySession
    # ------------------------------------------------------------------

    def create_session(self, session: QuerySession) -> QuerySession:
        with self.transaction() as conn:
            self._assert_tenant_writable(conn, session.tenant_id)
            conn.execute(
                "INSERT INTO query_sessions "
                "(id, query_text, created_at, confidence_rating, reasoning, "
                "useful_ids, stale_ids, concluded, tenant_id) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    session.id,
                    session.query_text,
                    _iso(session.created_at),
                    session.confidence_rating,
                    session.reasoning,
                    json.dumps(session.useful_ids),
                    json.dumps(session.stale_ids),
                    _bool(session.concluded),
                    session.tenant_id,
                ),
            )
        return session

    def get_session(self, session_id: str) -> QuerySession | None:
        conn = self.connect()
        row = conn.execute("SELECT * FROM query_sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return QuerySession(
            id=row["id"],
            query_text=row["query_text"],
            created_at=row["created_at"],
            confidence_rating=row["confidence_rating"],
            reasoning=row["reasoning"],
            useful_ids=row["useful_ids"],
            stale_ids=row["stale_ids"],
            concluded=bool(row["concluded"]),
            tenant_id=row["tenant_id"],
        )

    def record_query_results(self, results: list[QueryResult]) -> None:
        if not results:
            return
        with self.transaction() as conn:
            for result in results:
                self._assert_tenant_writable(conn, result.tenant_id)
            conn.executemany(
                "INSERT OR REPLACE INTO query_results "
                "(session_id, memory_id, relevance_score, was_accessed, "
                "was_useful, was_stale, tenant_id) VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        r.session_id,
                        r.memory_id,
                        r.relevance_score,
                        _bool(r.was_accessed),
                        _bool(r.was_useful),
                        _bool(r.was_stale),
                        r.tenant_id,
                    )
                    for r in results
                ],
            )

    # ------------------------------------------------------------------
    # MemorySummary
    # ------------------------------------------------------------------

    def upsert_summary(self, summary: MemorySummary) -> MemorySummary:
        """Upsert keyed on the ``(tenant_id, concept)`` unique constraint.

        Keeps the existing id of a ``(tenant_id, concept)`` row so an update does
        not change the summary id.
        """
        existing = self.get_summary(summary.concept, summary.tenant_id)
        summary_id = existing.id if existing is not None else summary.id
        with self.transaction() as conn:
            self._assert_tenant_writable(conn, summary.tenant_id)
            conn.execute(
                "INSERT INTO memory_summaries "
                "(id, concept, summary_text, memory_count, is_current, generated_at, tenant_id) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(tenant_id, concept) DO UPDATE SET "
                "summary_text = excluded.summary_text, "
                "memory_count = excluded.memory_count, "
                "is_current = excluded.is_current, "
                "generated_at = excluded.generated_at",
                (
                    summary_id,
                    summary.concept,
                    summary.summary_text,
                    summary.memory_count,
                    _bool(summary.is_current),
                    _iso(summary.generated_at),
                    summary.tenant_id,
                ),
            )
        result = self.get_summary(summary.concept, summary.tenant_id)
        assert result is not None  # just upserted
        return result

    def _row_to_summary(self, row: sqlite3.Row) -> MemorySummary:
        return MemorySummary(
            id=row["id"],
            concept=row["concept"],
            summary_text=row["summary_text"],
            memory_count=row["memory_count"],
            is_current=bool(row["is_current"]),
            generated_at=row["generated_at"],
            tenant_id=row["tenant_id"],
        )

    def get_summary(self, concept: str, tenant_id: str = "global") -> MemorySummary | None:
        """Fetch the summary for ``(tenant_id, concept)``. Returns None if not found."""
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM memory_summaries WHERE tenant_id = ? AND concept = ?",
            (tenant_id, concept),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_summary(row)

    def list_summaries(self) -> list[MemorySummary]:
        conn = self.connect()
        rows = conn.execute("SELECT * FROM memory_summaries ORDER BY concept").fetchall()
        return [self._row_to_summary(row) for row in rows]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> MemoryStats:
        conn = self.connect()
        total = conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()["c"]
        active = conn.execute(
            "SELECT COUNT(*) AS c FROM memories WHERE is_active = 1 AND is_archived = 0"
        ).fetchone()["c"]
        stale = conn.execute("SELECT COUNT(*) AS c FROM memories WHERE is_stale = 1").fetchone()[
            "c"
        ]
        archived = conn.execute(
            "SELECT COUNT(*) AS c FROM memories WHERE is_archived = 1"
        ).fetchone()["c"]
        links = conn.execute("SELECT COUNT(*) AS c FROM concept_links").fetchone()["c"]
        summaries = conn.execute("SELECT COUNT(*) AS c FROM memory_summaries").fetchone()["c"]

        avg_row = conn.execute(
            "SELECT AVG(usefulness_score) AS u, AVG(staleness_score) AS s "
            "FROM memories WHERE is_active = 1 AND is_archived = 0"
        ).fetchone()
        avg_use = float(avg_row["u"]) if avg_row["u"] is not None else 0.0
        avg_stale = float(avg_row["s"]) if avg_row["s"] is not None else 0.0

        # top_concepts: entity frequency across active (non-archived) memories.
        counter: Counter[str] = Counter()
        for row in conn.execute(
            "SELECT entity_ids FROM memories WHERE is_active = 1 AND is_archived = 0"
        ).fetchall():
            for entity in json.loads(row["entity_ids"]):
                counter[entity] += 1
        top_concepts = counter.most_common(20)

        return MemoryStats(
            total_memories=total,
            active=active,
            stale=stale,
            archived=archived,
            concept_links=links,
            memory_summaries=summaries,
            avg_usefulness_score=avg_use,
            avg_staleness_score=avg_stale,
            top_concepts=top_concepts,
        )

    # ------------------------------------------------------------------
    # Dreaming helpers
    # ------------------------------------------------------------------

    def get_flagged_memories(self) -> list[MemoryRecord]:
        """Return all memories where flagged_for_review = 1."""
        conn = self.connect()
        rows = conn.execute("SELECT * FROM memories WHERE flagged_for_review = 1").fetchall()
        return [self._row_to_memory(row) for row in rows]

    def get_never_accessed_stale(
        self, days_old: int = 7, min_staleness: float = 3.0
    ) -> list[MemoryRecord]:
        """Anomaly detection: never retrieved + staleness_score >= min_staleness.

        Notes (is_note=1) are excluded: a note is never auto-archived by staleness
        (design §5e); surfacing it here would mislead the dreaming anomaly report.
        """
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM memories "
            "WHERE last_accessed_at IS NULL "
            "AND staleness_score >= ? "
            "AND is_archived = 0 "
            "AND is_note = 0",
            (min_staleness,),
        ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def get_high_staleness_useful(
        self, min_staleness: float = 5.0, min_usefulness: float = 3.0
    ) -> list[MemoryRecord]:
        """Anomaly detection: stale but still useful = needs human resolution.

        Notes (is_note=1) are excluded: a stale vote on a note only flags it for
        review (design §5d/§5e); it never increments staleness_score, so it cannot
        appear here by construction — but the guard makes the invariant explicit.
        """
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM memories "
            "WHERE staleness_score >= ? "
            "AND usefulness_score >= ? "
            "AND is_archived = 0 "
            "AND is_note = 0",
            (min_staleness, min_usefulness),
        ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    # ------------------------------------------------------------------
    # Port — absorbed dreaming.py raw-SQL sites (verbatim SQL relocation)
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Cheap DB reachability check (SELECT 1). Returns True on success, never raises."""
        try:
            self.connect().execute("SELECT 1").fetchone()
            return True
        except Exception:  # noqa: BLE001
            return False

    def get_anomaly_high_staleness_useful_ids(
        self, min_staleness: float, min_usefulness: float
    ) -> list[str]:
        """IDs of high-staleness + still-useful memories (anomaly step 1a).

        Verbatim SQL relocated from dreaming.detect_anomalies().
        """
        conn = self.connect()
        rows = conn.execute(
            "SELECT id FROM memories "
            "WHERE staleness_score >= ? AND usefulness_score >= ? "
            "AND is_archived = 0 "
            "AND is_note = 0 "
            "ORDER BY id",
            (min_staleness, min_usefulness),
        ).fetchall()
        return [row["id"] for row in rows]

    def get_anomaly_never_accessed_ids(self, cutoff_iso: str) -> list[str]:
        """IDs of never-retrieved memories created before cutoff (anomaly step 1b).

        Verbatim SQL relocated from dreaming.detect_anomalies().
        """
        conn = self.connect()
        rows = conn.execute(
            "SELECT id FROM memories "
            "WHERE retrieval_count = 0 AND created_at < ? "
            "AND is_active = 1 AND is_archived = 0 "
            "AND is_note = 0 "
            "ORDER BY id",
            (cutoff_iso,),
        ).fetchall()
        return [row["id"] for row in rows]

    def get_anomaly_flagged_ids(self) -> list[str]:
        """IDs of flagged_for_review memories (anomaly step 1c).

        Verbatim SQL relocated from dreaming.detect_anomalies().
        """
        conn = self.connect()
        rows = conn.execute(
            "SELECT id FROM memories WHERE flagged_for_review = 1 ORDER BY id"
        ).fetchall()
        return [row["id"] for row in rows]

    def list_active_memory_ids(self, *, ordered: bool = False) -> list[str]:
        """IDs of all active, non-archived memories.

        Verbatim SQL relocated from dreaming.create_concept_links(),
        _select_summary_concepts(), and _active_count_for_concept().
        ``ordered=True`` appends ``ORDER BY id`` for deterministic iteration.
        """
        conn = self.connect()
        sql = "SELECT id FROM memories WHERE is_active = 1 AND is_archived = 0"
        if ordered:
            sql += " ORDER BY id"
        rows = conn.execute(sql).fetchall()
        return [row["id"] for row in rows]

    def get_stale_archivable_ids(self, min_staleness: float, cutoff_iso: str) -> list[str]:
        """IDs of memories eligible for staleness archival (dreaming step 5).

        Verbatim SQL relocated from dreaming.archive_stale().
        """
        conn = self.connect()
        rows = conn.execute(
            "SELECT id FROM memories "
            "WHERE is_stale = 1 AND staleness_score >= ? AND is_archived = 0 "
            "AND is_note = 0 "
            "AND (last_accessed_at IS NULL OR last_accessed_at < ?) "
            "ORDER BY id",
            (min_staleness, cutoff_iso),
        ).fetchall()
        return [row["id"] for row in rows]

    def get_rehabilitable_rows(self, cutoff_iso: str) -> list[tuple[str, float]]:
        """(id, staleness_score) pairs eligible for rehabilitation (dreaming step 6).

        Verbatim SQL relocated from dreaming.rehabilitate().
        """
        conn = self.connect()
        rows = conn.execute(
            "SELECT id, staleness_score FROM memories "
            "WHERE is_stale = 1 AND usefulness_score > staleness_score "
            "AND is_archived = 0 "
            "AND last_accessed_at IS NOT NULL AND last_accessed_at >= ? "
            "ORDER BY id",
            (cutoff_iso,),
        ).fetchall()
        return [(row["id"], float(row["staleness_score"])) for row in rows]

    # ------------------------------------------------------------------
    # Port — absorbed session.py raw-SQL sites (verbatim SQL, same boundaries)
    # ------------------------------------------------------------------

    def update_session_feedback(
        self,
        session_id: str,
        confidence_rating: int | None,
        reasoning: str | None,
        useful_ids: list[str],
        stale_ids: list[str],
    ) -> None:
        """Update query_sessions + query_results in one transaction.

        Phase-0 boundary preserved verbatim from session.apply_feedback():
        the per-memory apply_feedback() calls each run in their OWN transactions
        (upstream, before this call); this method handles only the session-level
        UPDATE + per-result flag UPDATE, in ONE transaction — matching the single
        ``with adapter.transaction()`` block in the original code.
        Making this entire conclude atomic is deferred to Phase 2.
        """
        useful_set = set(useful_ids)
        stale_set = set(stale_ids)
        with self.transaction() as conn:
            stored_tenant = self._session_tenant(conn, session_id)
            if stored_tenant is not None:
                self._assert_tenant_writable(conn, stored_tenant)
            conn.execute(
                "UPDATE query_sessions SET confidence_rating = ?, reasoning = ?, "
                "useful_ids = ?, stale_ids = ?, concluded = 1 WHERE id = ?",
                (
                    confidence_rating,
                    reasoning,
                    json.dumps(useful_ids),
                    json.dumps(stale_ids),
                    session_id,
                ),
            )
            for memory_id in useful_set | stale_set:
                conn.execute(
                    "UPDATE query_results SET was_useful = ?, was_stale = ? "
                    "WHERE session_id = ? AND memory_id = ?",
                    (
                        1 if memory_id in useful_set else 0,
                        1 if memory_id in stale_set else 0,
                        session_id,
                        memory_id,
                    ),
                )

    def mark_session_concluded(self, session_id: str) -> None:
        """Mark a session concluded with no feedback (idempotent, no-feedback path).

        Verbatim SQL relocated from session.conclude_session().
        """
        with self.transaction() as conn:
            stored_tenant = self._session_tenant(conn, session_id)
            if stored_tenant is not None:
                self._assert_tenant_writable(conn, stored_tenant)
            conn.execute(
                "UPDATE query_sessions SET concluded = 1 WHERE id = ?",
                (session_id,),
            )

    # ------------------------------------------------------------------
    # Port — absorbed vision.py raw-SQL site (verbatim SQL relocation)
    # ------------------------------------------------------------------

    def list_image_file_records(self) -> list[MemoryRecord]:
        """Return all active, non-archived memories with 'ext' metadata but no 'kind' tag.

        Verbatim SQL relocated from vision.image_jobs(). Python post-filtering
        (IMAGE_SUFFIXES, PROPRIETARY, SVG) stays in vision.py.
        """
        conn = self.connect()
        rows = conn.execute(
            "SELECT * FROM memories "
            "WHERE is_archived = 0 "
            "AND json_extract(metadata, '$.kind') IS NULL "
            "AND json_extract(metadata, '$.ext') IS NOT NULL "
            "ORDER BY json_extract(metadata, '$.rel'), id"
        ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    # ------------------------------------------------------------------
    # Port — absorbed cli/main.py ingest dedup (task 2.1a)
    # ------------------------------------------------------------------

    def memory_exists_with_content(self, content: str) -> bool:
        """Return True if any memory with the exact content already exists.

        Verbatim SQL: SELECT 1 FROM memories WHERE content = ? LIMIT 1
        Used by the ingest command for dedup checks; portable across backends.
        """
        conn = self.connect()
        return (
            conn.execute("SELECT 1 FROM memories WHERE content = ? LIMIT 1", (content,)).fetchone()
            is not None
        )

    def get_existing_relates_to_pairs(self) -> set[frozenset[str]]:
        """Return the set of existing RELATES_TO concept-link pairs (order-insensitive).

        Used by create_concept_links() to pre-check which pairs already exist
        so the new-link count is accurate even when add_link is INSERT OR IGNORE.

        Verbatim SQL:
            SELECT source_memory_id, target_memory_id
            FROM concept_links WHERE link_type = ?
        """
        from mintmory.core.types import ConceptLinkType

        conn = self.connect()
        rows = conn.execute(
            "SELECT source_memory_id, target_memory_id FROM concept_links WHERE link_type = ?",
            (ConceptLinkType.RELATES_TO.value,),
        ).fetchall()
        return {frozenset({r["source_memory_id"], r["target_memory_id"]}) for r in rows}

    @staticmethod
    def _unique_index_columns(conn: sqlite3.Connection, table: str) -> list[tuple[str, ...]]:
        """Columns of every unique index on ``table`` (in index order)."""
        result: list[tuple[str, ...]] = []
        for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
            if not index["unique"]:
                continue
            columns = tuple(
                str(row["name"])
                for row in conn.execute(f"PRAGMA index_info({index['name']})").fetchall()
            )
            result.append(columns)
        return result

    @staticmethod
    def _primary_key_columns(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
        """Column names of ``table``'s primary key, in key order."""
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return tuple(
            str(row["name"])
            for row in sorted((row for row in rows if row["pk"]), key=lambda r: r["pk"])
        )

    def _tenant_migration_statements(self, conn: sqlite3.Connection) -> list[str]:
        """Return only the tenant DDL this database still needs, in the required order.

        Plan and execution are separate so tests can inject faults and so the
        plan can be recomputed inside the migration transaction (R3.3).
        """
        table_columns: dict[str, list[str]] = {
            table: [
                str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            for table in _TENANT_TABLES
        }

        statements: list[str] = []
        for table in _TENANT_TABLES:
            if "tenant_id" not in table_columns[table]:
                statements.append(
                    f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'global'"
                )

        rebuilt: set[str] = set()
        if (
            "tenant_id",
            "source_memory_id",
            "target_memory_id",
            "link_type",
        ) not in self._unique_index_columns(conn, "concept_links"):
            rebuilt.add("concept_links")
        if ("tenant_id", "concept") not in self._unique_index_columns(conn, "memory_summaries"):
            rebuilt.add("memory_summaries")
        if self._primary_key_columns(conn, "index_manifest") != ("tenant_id", "path"):
            rebuilt.add("index_manifest")

        for table in _TENANT_TABLES:
            if table not in rebuilt:
                continue
            columns = ", ".join(_TENANT_REBUILD_COLUMNS[table])
            statements.extend(
                (
                    _TENANT_REBUILD_DDL[table].strip(),
                    f"INSERT INTO {table}__tenant_new ({columns}) SELECT {columns} FROM {table}",
                    f"DROP TABLE {table}",
                    f"ALTER TABLE {table}__tenant_new RENAME TO {table}",
                )
            )
            statements.extend(_TENANT_REBUILD_INDEXES[table])

        existing_indexes = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        index_tables = {
            "idx_memories_tenant": "memories",
            "idx_links_tenant": "concept_links",
            "idx_sessions_tenant": "query_sessions",
        }
        for name, ddl in _TENANT_INDEX_DDL:
            if name not in existing_indexes or index_tables[name] in rebuilt:
                statements.append(ddl)
        return statements

    def _ensure_tenant_columns(self, conn: sqlite3.Connection) -> None:
        """Apply the tenant migration atomically, or fail closed (R3.3/R3.4).

        The plan is computed once without a lock (a migrated database never takes
        a write lock at startup) and again inside ``BEGIN IMMEDIATE`` so two
        processes starting together cannot replay a stale plan.
        """
        if not self._tenant_migration_statements(conn):
            return

        # Foreign keys must be off outside the transaction: SQLite ignores the
        # pragma while a transaction is open. They are restored in ``finally``.
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            try:
                conn.execute("BEGIN IMMEDIATE")
                statements = self._tenant_migration_statements(conn)
                for statement in statements:
                    conn.execute(statement)
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise TenantMigrationError(str(exc)) from exc
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    def create_tenant(self, tenant_id: str, name: str = "") -> Tenant:
        """Create a tenant idempotently; an existing id is returned unchanged."""
        validate_tenant_id(tenant_id)
        now = _iso(_utcnow())
        with self.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO tenants "
                "(id, name, is_active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                (tenant_id, name, now, now),
            )
            row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        assert row is not None
        return self._row_to_tenant(row)

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Return the tenant row, or None for an unknown/invalid id."""
        row = self.connect().execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        return None if row is None else self._row_to_tenant(row)

    def list_tenants(self) -> list[Tenant]:
        """Every tenant (active and inactive), ordered by id ascending."""
        rows = self.connect().execute("SELECT * FROM tenants ORDER BY id").fetchall()
        return [self._row_to_tenant(row) for row in rows]

    def set_tenant_active(self, tenant_id: str, active: bool) -> Tenant:
        """Activate/deactivate a tenant; ``global`` cannot be deactivated."""
        existing = self.get_tenant(tenant_id)
        if existing is None:
            raise TenantNotFoundError(tenant_id)
        if tenant_id == TENANT_GLOBAL:
            if not active:
                raise ProtectedTenantError()
            return existing
        with self.transaction() as conn:
            conn.execute(
                "UPDATE tenants SET is_active = ?, updated_at = ? WHERE id = ?",
                (_bool(active), _iso(_utcnow()), tenant_id),
            )
        updated = self.get_tenant(tenant_id)
        assert updated is not None
        return updated

    @staticmethod
    def _row_to_tenant(row: sqlite3.Row) -> Tenant:
        return Tenant(
            id=row["id"],
            name=row["name"],
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _stored_tenant(self, conn: sqlite3.Connection, memory_id: str) -> str | None:
        """Stored tenant of a memory row, or ``None`` when the row is missing."""
        row = conn.execute("SELECT tenant_id FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return None if row is None else str(row["tenant_id"])

    def _session_tenant(self, conn: sqlite3.Connection, session_id: str) -> str | None:
        """Stored tenant of a session row, or ``None`` when the row is missing."""
        row = conn.execute(
            "SELECT tenant_id FROM query_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return None if row is None else str(row["tenant_id"])

    def _assert_tenant_writable(self, conn: sqlite3.Connection, tenant_id: str) -> None:
        """Raise unless ``tenant_id`` exists and is active."""
        row = conn.execute("SELECT is_active FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        if row is None:
            raise TenantNotFoundError(tenant_id)
        if not row["is_active"]:
            raise TenantInactiveError(tenant_id)


# ---------------------------------------------------------------------------
# Back-compat alias — keep for one release so code pinned to the old name
# still imports without modification (e.g., existing test fixtures, scripts).
# History modules and cochange continue to use SqliteBackend explicitly.
# ---------------------------------------------------------------------------
StorageAdapter = SqliteBackend
