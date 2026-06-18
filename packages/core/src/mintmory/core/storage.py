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
import sqlite3
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from mintmory.core import scoring, telemetry
from mintmory.core.entities import extract_entities
from mintmory.core.types import (
    SYMMETRIC_LINK_TYPES,
    ConceptLink,
    ConceptLinkType,
    MemoryFilter,
    MemoryRecord,
    MemoryStats,
    MemorySummary,
    QueryResult,
    QuerySession,
    SearchAroundSpec,
    SearchRequest,
    SearchResponse,
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


class StorageAdapter:
    """
    SQLite adapter wrapping all MintMory persistence operations.

    Usage:
        store = StorageAdapter("/path/to/mintmory.db")
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

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
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
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

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

    def _vector_search_available(self) -> bool:
        return self.embedder is not None and self._vec_loaded

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
        )

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
            conn.execute(
                "UPDATE memories SET is_archived = 1, is_active = 0, updated_at = ? WHERE id = ?",
                (_iso(_utcnow()), memory_id),
            )

    # ------------------------------------------------------------------
    # Index manifest — per-path state for recurrent tree indexing
    # ------------------------------------------------------------------
    def manifest_get(self, path: str) -> sqlite3.Row | None:
        """Return the manifest row for ``path`` (absolute), or None."""
        row: sqlite3.Row | None = (
            self.connect()
            .execute("SELECT * FROM index_manifest WHERE path = ?", (path,))
            .fetchone()
        )
        return row

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
    ) -> None:
        """Insert or replace the manifest row for ``path``."""
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO index_manifest "
                "(path, collection, size, mtime, content_hash, index_mode, "
                " memory_ids, online_only, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET "
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
                ),
            )

    def manifest_paths(self, collection: str) -> set[str]:
        """All paths currently tracked under ``collection``."""
        rows = (
            self.connect()
            .execute("SELECT path FROM index_manifest WHERE collection = ?", (collection,))
            .fetchall()
        )
        return {row["path"] for row in rows}

    def manifest_delete(self, path: str) -> None:
        """Drop the manifest row for ``path`` (memories are archived separately)."""
        with self.transaction() as conn:
            conn.execute("DELETE FROM index_manifest WHERE path = ?", (path,))

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
        conn = self.connect()
        row = conn.execute(
            "SELECT usefulness_score, staleness_score, reinforcement_count, is_note "
            "FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"memory {memory_id!r} not found")

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

        with self.transaction() as txn:
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
        if not self._vector_search_available():
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
    def search(
        self,
        request: SearchRequest,
        query_embedding: np.ndarray | None = None,
    ) -> SearchResponse:
        """
        Hybrid search pipeline (PLAN.md §3): FTS5 + optional vector phase merged
        with RRF, filtered, scored, sorted, limited; optional graph union; a
        QuerySession + query_results are recorded and retrieval counters bumped.
        """
        # Wider candidate pool than the final limit so filtering + scoring have
        # room to reorder before truncation.
        pool = max(request.limit * 5, 50)

        fts_scores = self._fts_scores(request.query, pool)
        vec_scores = self._vector_scores(request.query, query_embedding, pool)
        trigram_scores = self._trigram_scores(request.query, pool)
        sources = [s for s in (fts_scores, trigram_scores, vec_scores) if s]
        if not sources:
            base_scores = {}
        elif len(sources) == 1:
            base_scores = sources[0]
        else:
            base_scores = scoring.rrf_merge(*sources)

        # Min-max normalise relevance to [0, 1] so it is on a comparable scale to
        # the usefulness/recency modifiers in effective_score. Raw RRF (~0.02) and
        # raw bm25/cosine are tiny/negative, which let the recency bonus (up to
        # 0.1) swamp text relevance and bury strong lexical matches. After
        # normalisation, relevance dominates and usefulness/recency tie-break.
        if base_scores:
            lo = min(base_scores.values())
            span = max(base_scores.values()) - lo
            if span > 0:
                base_scores = {mid: (s - lo) / span for mid, s in base_scores.items()}
            else:
                base_scores = dict.fromkeys(base_scores, 1.0)

        candidate_ids = list(base_scores.keys())
        memories = self._load_memories(candidate_ids)

        filt = request.filter or MemoryFilter()
        now = _utcnow()
        # Lazily resolve note_bonus / auto_include_cap from NoteSettings on first
        # use — import inside the call to avoid circular imports at module load time.
        if self._note_bonus is None:
            from mintmory.core.config import NoteSettings  # noqa: PLC0415

            self._note_bonus = NoteSettings().note_bonus
        if self._auto_include_cap is None:
            from mintmory.core.config import NoteSettings  # noqa: PLC0415

            self._auto_include_cap = NoteSettings().auto_include_cap
        note_bonus = self._note_bonus
        auto_include_cap = self._auto_include_cap

        scored: list[tuple[float, MemoryRecord]] = []
        for mem in memories:
            if not self._passes_filter(mem, filt, request.include_archived):
                continue
            eff = scoring.effective_score(
                base_relevance=base_scores.get(mem.id, 0.0),
                usefulness_score=mem.usefulness_score,
                staleness_score=mem.staleness_score,
                last_accessed_at=mem.last_accessed_at,
                now=now,
                is_note=mem.is_note,
                note_bonus=note_bonus,
            )
            scored.append((eff, mem))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        primary = [mem for _, mem in scored[: request.limit]]

        # Phase 2: graph traversal union (OR semantics — anchors always kept).
        around_ids: list[str] = []
        if request.search_around is not None and primary:
            anchor_ids = [mem.id for mem in primary]
            around_ids = self.search_around(anchor_ids, request.search_around)
            existing = {mem.id for mem in primary}
            for extra in self._load_memories(around_ids):
                if extra.id not in existing:
                    primary.append(extra)
                    existing.add(extra.id)

        # Phase 3: auto-include notes annotating each primary result (reverse
        # ANNOTATES traversal — the result is the target, the note the source).
        # Annotating notes are a SEPARATE channel (notes_on_results); they are NOT
        # added to ``primary``, NOT counted in ``total_found``, NOT recorded as
        # query_results, and do NOT bump retrieval counters (they are context, not
        # direct hits).
        notes_on_results: dict[str, list[MemoryRecord]] = {}
        if auto_include_cap > 0:
            for mem in primary:
                annotating = self.get_annotating_notes(mem.id, auto_include_cap)
                if annotating:
                    notes_on_results[mem.id] = annotating

        # Decision lineage: persist the session + results, bump counters.
        session = QuerySession(query_text=request.query)
        self.create_session(session)
        results = [
            QueryResult(
                session_id=session.id,
                memory_id=mem.id,
                relevance_score=base_scores.get(mem.id, 0.0),
            )
            for mem in primary
        ]
        self.record_query_results(results)
        self._bump_retrieval([mem.id for mem in primary], now)

        return SearchResponse(
            session_id=session.id,
            memories=primary,
            total_found=len(primary),
            search_around_ids=around_ids,
            notes_on_results=notes_on_results,
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

    def _anchor_candidates(self, about: str, limit: int = 5) -> list[tuple[float, MemoryRecord]]:
        """Side-effect-free candidate lookup for note anchoring.

        Reuses the hybrid score sources (FTS5 + trigram + vector) and min-max
        normalisation from ``search()`` but does NOT create a QuerySession, does NOT
        record query_results, and does NOT bump retrieval counters. Returns
        ``(normalised_score, record)`` pairs sorted best-first.
        """
        pool = max(limit * 5, 50)
        fts_scores = self._fts_scores(about, pool)
        vec_scores = self._vector_scores(about, None, pool)
        trigram_scores = self._trigram_scores(about, pool)
        sources = [s for s in (fts_scores, trigram_scores, vec_scores) if s]
        if not sources:
            base_scores: dict[str, float] = {}
        elif len(sources) == 1:
            base_scores = sources[0]
        else:
            base_scores = scoring.rrf_merge(*sources)

        if base_scores:
            lo = min(base_scores.values())
            span = max(base_scores.values()) - lo
            if span > 0:
                base_scores = {mid: (s - lo) / span for mid, s in base_scores.items()}
            else:
                base_scores = dict.fromkeys(base_scores, 1.0)

        candidate_ids = list(base_scores.keys())
        memories = self._load_memories(candidate_ids)
        scored = [(base_scores.get(m.id, 0.0), m) for m in memories]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[:limit]

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
                        Python, mirroring ``_passes_filter``'s entity check).
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

        # Post-filter entity and anchor_substr in Python — consistent with how
        # ``_passes_filter`` handles entity checks.
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
            conn.execute(
                "UPDATE memories SET superseded_by = ?, is_active = 0, is_archived = 1, "
                "updated_at = ? WHERE id = ?",
                (by_id, _iso(_utcnow()), memory_id),
            )

    @staticmethod
    def _passes_filter(mem: MemoryRecord, filt: MemoryFilter, include_archived: bool) -> bool:
        if not include_archived and mem.is_archived:
            return False
        if filt.active_only and not mem.is_active:
            return False
        if filt.exclude_stale and mem.is_stale:
            return False
        if filt.category is not None and mem.category != filt.category:
            return False
        if filt.source is not None and mem.source != filt.source:
            return False
        if filt.verified_only and not mem.verified:
            return False
        if filt.entity is not None and filt.entity.lower() not in {
            e.lower() for e in mem.entity_ids
        }:
            return False
        if filt.min_usefulness is not None and mem.usefulness_score < filt.min_usefulness:
            return False
        if filt.max_staleness is not None and mem.staleness_score > filt.max_staleness:  # noqa: SIM103
            return False
        return True

    def _bump_retrieval(self, ids: list[str], now: datetime) -> None:
        if not ids:
            return
        placeholders = ", ".join("?" for _ in ids)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE memories SET retrieval_count = retrieval_count + 1, "
                f"last_accessed_at = ? WHERE id IN ({placeholders})",
                [_iso(now), *ids],
            )

    @telemetry.traced("mintmory.search_around")
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
            conn.execute(
                "INSERT OR IGNORE INTO concept_links "
                "(id, source_memory_id, target_memory_id, link_type, entity, "
                "strength, confidence, source, verified, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
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
            conn.execute(
                "INSERT INTO query_sessions "
                "(id, query_text, created_at, confidence_rating, reasoning, "
                "useful_ids, stale_ids, concluded) VALUES (?,?,?,?,?,?,?,?)",
                (
                    session.id,
                    session.query_text,
                    _iso(session.created_at),
                    session.confidence_rating,
                    session.reasoning,
                    json.dumps(session.useful_ids),
                    json.dumps(session.stale_ids),
                    _bool(session.concluded),
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
        )

    def record_query_results(self, results: list[QueryResult]) -> None:
        if not results:
            return
        with self.transaction() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO query_results "
                "(session_id, memory_id, relevance_score, was_accessed, "
                "was_useful, was_stale) VALUES (?,?,?,?,?,?)",
                [
                    (
                        r.session_id,
                        r.memory_id,
                        r.relevance_score,
                        _bool(r.was_accessed),
                        _bool(r.was_useful),
                        _bool(r.was_stale),
                    )
                    for r in results
                ],
            )

    # ------------------------------------------------------------------
    # MemorySummary
    # ------------------------------------------------------------------

    def upsert_summary(self, summary: MemorySummary) -> MemorySummary:
        """INSERT OR REPLACE keyed on the UNIQUE ``concept`` column."""
        existing = self.get_summary(summary.concept)
        summary_id = existing.id if existing is not None else summary.id
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO memory_summaries "
                "(id, concept, summary_text, memory_count, is_current, generated_at) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(concept) DO UPDATE SET "
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
                ),
            )
        result = self.get_summary(summary.concept)
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
        )

    def get_summary(self, concept: str) -> MemorySummary | None:
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM memory_summaries WHERE concept = ?", (concept,)
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
