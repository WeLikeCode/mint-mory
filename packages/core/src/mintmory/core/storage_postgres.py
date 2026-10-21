"""
PostgreSQL storage backend for MintMory — Phase 2.

Implements the full ``StorageBackend`` Protocol against PostgreSQL via
psycopg3 (``psycopg[binary,pool]``) + pgvector + pg_trgm.

Access layer:  raw psycopg3 + hand-written SQL (no SQLAlchemy ORM).
Schema:        ``schema_postgres.sql`` executed under ``pg_advisory_lock`` on
               every ``initialise()`` call (idempotent, N-replica safe).
FTS:           Generated ``tsvector`` column (``to_tsvector('english', content)``)
               with GIN index.  Queries via ``to_tsquery`` prefix terms (``token:*``),
               ranked by ``ts_rank``.
Trigram:       pg_trgm ``word_similarity`` + GIN ``gin_trgm_ops`` index.
Vector:        pgvector unconstrained ``vector`` column + cosine exact scan
               (``embedding <=> %s``); dimension guard ``vector_dims(embedding) = %s``
               skips mismatched rows without raising.
Concurrency:   ``apply_feedback`` is fully atomic server-side (single UPDATE);
               ``update_memory`` excludes counter columns from the write-set unless
               the caller explicitly passes them (design §6.3).
Types:         native JSONB, BOOLEAN, TIMESTAMP (naive UTC — design §8 locked).

Design reference: design.md §2.3, §3.2, §5.1, §6.1–6.5, §8.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from mintmory.core import telemetry
from mintmory.core.entities import extract_entities
from mintmory.core.hybrid_search import collect_scores, fuse_and_rank, fuse_and_search
from mintmory.core.ports import ManifestEntry
from mintmory.core.scoring import (
    STALE_INCREMENT,
    STALENESS_THRESHOLD,
    USEFUL_INCREMENT,
)
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
    TenancyNotSupportedError,
    Tenant,
)

if TYPE_CHECKING:
    from mintmory.core.embedder import EmbedderProtocol

# ---------------------------------------------------------------------------
# Advisory lock ID — prevents N-replica DDL races in initialise()
# ---------------------------------------------------------------------------
_ADVISORY_LOCK_ID = 0x4D494E544D4F5259  # "MINTMORY" hex as int64


# ---------------------------------------------------------------------------
# Explicit memory column list used in SELECT statements
# (must match the columns returned by _row_to_memory)
# ---------------------------------------------------------------------------

_SELECT_MEMORY = (
    "id, content, category, entity_ids, confidence, source, verified, "
    "valid_from, valid_until, usefulness_score, staleness_score, "
    "reinforcement_count, retrieval_count, is_stale, is_active, is_archived, "
    "superseded_by, flagged_for_review, contradicts_ids, is_note, "
    "created_at, updated_at, last_accessed_at, metadata"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    """Naive UTC datetime, matching the model defaults throughout MintMory."""
    return datetime.now(UTC).replace(tzinfo=None)


def _from_pg_dt(dt: datetime | None) -> datetime | None:
    """Strip timezone info from psycopg3 timestamptz so MemoryRecord gets naive UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _sanitise_fts_query_pg(query: str) -> str:
    """
    Build a PostgreSQL ``to_tsquery`` expression from arbitrary user text.

    Mirrors SqliteBackend's ``_sanitise_fts_query`` logic:
    - Tokenise on ``[A-Za-z0-9]+``
    - Each token of length >= 3 → prefix term ``token:*``
    - Short tokens → exact term ``token``
    - Adjacent pairs also emitted as compound prefix term (helps compound words)
    - All terms OR-joined (``|`` in tsquery syntax)

    Returns ``""`` when no tokens qualify; caller skips the FTS phase.
    """
    tokens = re.findall(r"[A-Za-z0-9]+", query)
    if not tokens:
        return ""
    terms: list[str] = []
    for tok in tokens:
        if len(tok) >= 3:
            terms.append(f"{tok.lower()}:*")
        else:
            terms.append(tok.lower())
    for first, second in zip(tokens, tokens[1:], strict=False):
        combo = (first + second).lower()
        if len(combo) >= 4:
            terms.append(f"{combo}:*")
    unique = list(dict.fromkeys(terms))
    return " | ".join(unique)


def _sanitise_trgm_tokens(query: str) -> list[str]:
    """Extract trigram-queryable tokens (length >= 3, lowercase, deduped)."""
    tokens = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", query) if len(t) >= 3]
    return list(dict.fromkeys(tokens))


try:
    from psycopg.rows import dict_row as _dict_row_factory  # noqa: N812
except ImportError:
    _dict_row_factory = None  # type: ignore[assignment]


# Module-level constant: counter columns excluded from update_memory writes unless
# the caller explicitly passes them in **fields.
_COUNTER_COLS: frozenset[str] = frozenset(
    {"usefulness_score", "staleness_score", "reinforcement_count", "retrieval_count"}
)


def _execute_dict(conn: Any, sql: str, params: Any = None) -> Any:
    """
    Execute *sql* on *conn* with ``dict_row`` factory and return the cursor.

    We use ``conn.cursor(row_factory=_dict_row_factory)`` (NOT ``conn.execute()``) to
    avoid the sticky ``conn.row_factory`` problem that arises with
    ``ConnectionPool`` connection reuse.  The cursor is returned after execute;
    call ``.fetchone()`` / ``.fetchall()`` on it.
    """
    cur = (
        conn.cursor(row_factory=_dict_row_factory)
        if _dict_row_factory is not None
        else conn.cursor()
    )
    if params is not None:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    return cur


# ---------------------------------------------------------------------------
# PostgresBackend
# ---------------------------------------------------------------------------


class PostgresBackend:
    """
    PostgreSQL storage backend implementing the ``StorageBackend`` Protocol.

    Lazily imported by ``storage_factory.build_storage()`` when
    ``backend == "postgres"``.  Requires the ``[postgres]`` extra:
        psycopg[binary,pool]>=3.1, pgvector>=0.3.0, alembic>=1.13, sqlalchemy>=2.0

    Construct via ``storage_factory.build_storage(settings, embedder=...)``.
    """

    def __init__(
        self,
        dsn: str,
        embedder: EmbedderProtocol | None = None,
        pool_min: int = 1,
        pool_max: int = 10,
        note_bonus: float | None = None,
        auto_include_cap: int | None = None,
        vector_rrf_weight: float | None = None,
    ) -> None:
        self.dsn = dsn
        self.embedder = embedder
        self._pool_min = pool_min
        self._pool_max = pool_max
        self._pool: Any = None  # psycopg_pool.ConnectionPool, lazy init
        self._vec_available: bool = False
        self._trgm_available: bool = False
        # Lazy-resolved scoring knobs (same pattern as SqliteBackend)
        self._note_bonus: float | None = note_bonus
        self._auto_include_cap: int | None = auto_include_cap
        self._vector_rrf_weight: float | None = vector_rrf_weight

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialise(self) -> None:
        """
        Create pool, install extensions, run DDL under pg_advisory_xact_lock.

        Idempotent — safe to call on every replica startup.

        Design note (§6.4): the design recommends a deploy-time Alembic job for
        schema creation, but the Phase 2 implementation uses runtime DDL under a
        transaction-level advisory lock instead.  Rationale: this dev/Phase-2
        milestone targets a single-replica disposable-PG environment where DDL at
        startup is acceptable.  The advisory lock is ``pg_advisory_xact_lock`` (not
        session-level ``pg_advisory_lock``), so it is automatically released on
        commit or rollback — no manual unlock is needed and no deadlock risk from a
        failed DDL transaction.

        For managed Postgres (RDS/CloudSQL) a DBA must pre-install the ``vector``
        and ``pg_trgm`` extensions; ``_ensure_extensions()`` attempts the install
        and silently continues on privilege error — ``_probe_capabilities()`` will
        then report the extensions as absent so the code degrades gracefully.
        """
        from psycopg_pool import ConnectionPool  # noqa: PLC0415

        if self._pool is None:
            self._pool = ConnectionPool(
                self.dsn,
                min_size=self._pool_min,
                max_size=self._pool_max,
                open=True,
                kwargs={"autocommit": False},
            )

        # Step 1 — try to install extensions (requires superuser or CREATE privilege).
        # Silently ignored on managed Postgres where a DBA pre-installs them.
        self._ensure_extensions()

        # Step 2 — table DDL under a transaction-level advisory lock.
        # pg_advisory_xact_lock() is released automatically on commit OR rollback,
        # so a DDL failure cannot strand a session-level lock and block other replicas.
        with self._pool.connection() as conn:
            self._register_adapters(conn)
            conn.execute(f"SELECT pg_advisory_xact_lock({_ADVISORY_LOCK_ID})")
            self._create_schema(conn)
            conn.commit()

        self._probe_capabilities()

    def _ensure_extensions(self) -> None:
        """Attempt to install ``vector`` and ``pg_trgm`` extensions.

        Requires superuser or ``CREATE`` privilege on the database.  On managed
        Postgres (RDS/CloudSQL) these must be pre-installed by a DBA out-of-band;
        the ``Exception`` is swallowed so ``initialise()`` still succeeds.
        ``_probe_capabilities()`` will then report the extensions as absent and the
        backend degrades gracefully to FTS-only search.
        """
        if self._pool is None:
            return
        try:
            with self._pool.connection() as conn:
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                conn.commit()
        except Exception:  # noqa: BLE001
            # Insufficient privilege — extensions must be pre-installed by a DBA.
            # _probe_capabilities() determines which ones are actually available.
            pass

    def _register_adapters(self, conn: Any) -> None:
        """Register pgvector numpy adapter on *conn* (idempotent per connection)."""
        try:
            from pgvector.psycopg import register_vector  # noqa: PLC0415

            register_vector(conn)
        except Exception:  # noqa: BLE001
            pass

    def _probe_capabilities(self) -> None:
        """Check which optional extensions are installed in this database."""
        if self._pool is None:
            return
        with self._pool.connection() as conn:
            self._register_adapters(conn)
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector'"
                ).fetchone()
                self._vec_available = bool(row and row[0] > 0) and self.embedder is not None
            except Exception:  # noqa: BLE001
                self._vec_available = False
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM pg_extension WHERE extname = 'pg_trgm'"
                ).fetchone()
                self._trgm_available = bool(row and row[0] > 0)
            except Exception:  # noqa: BLE001
                self._trgm_available = False

    def _create_schema(self, conn: Any) -> None:
        """Execute DDL from schema_postgres.sql. All statements are IF NOT EXISTS."""
        ddl = Path(__file__).parent / "schema_postgres.sql"
        conn.execute(ddl.read_text())

    def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    def ping(self) -> bool:
        """Cheap reachability check. Returns True on success, never raises."""
        try:
            if self._pool is None:
                return False
            with self._pool.connection() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001
            return False

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """Interim stub: transaction composition is not available on Postgres yet.

        Raises ``TenancyNotSupportedError`` before yielding (the real
        implementation arrives with ``multi-tenancy-postgres-writes``), so no
        pool access ever happens.
        """
        raise TenancyNotSupportedError("transaction")
        yield  # unreachable — keeps the generator a usable context-manager factory

    # ------------------------------------------------------------------
    # Test-isolation helper (not part of Protocol; called from conftest)
    # ------------------------------------------------------------------

    def _truncate_all(self) -> None:
        """TRUNCATE all tables. NOT for production use — test isolation only."""
        assert self._pool is not None
        with self._pool.connection() as conn:
            conn.execute(
                "TRUNCATE memories, concept_links, index_manifest, "
                "query_sessions, query_results, memory_summaries "
                "RESTART IDENTITY CASCADE"
            )
            conn.commit()

    def _inject_wrong_dim_embedding(self, memory_id: str, dim: int = 8) -> None:
        """Overwrite the stored embedding with a wrong-dimension vector.

        NOT part of the ``StorageBackend`` Protocol — test isolation only.
        Mirrors the raw-BLOB injection path used for ``SqliteBackend`` in the
        mixed-dimension conformance test, allowing ``test_mixed_dimension_embedding_survival``
        to exercise the PG dimension guard (``WHERE vector_dims(embedding) = %s``).
        """
        import numpy as np  # noqa: PLC0415

        assert self._pool is not None
        wrong_dim_emb = np.zeros(dim, dtype=np.float32)
        with self._pool.connection() as conn:
            self._register_adapters(conn)
            conn.execute(
                "UPDATE memories SET embedding = %s WHERE id = %s",
                (wrong_dim_emb, memory_id),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Embedding helpers
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> np.ndarray | None:
        if self.embedder is None:
            return None
        vectors = self.embedder.embed_batch([text])
        return np.asarray(vectors[0], dtype=np.float32) if vectors else None

    def vector_search_available(self) -> bool:
        return self._vec_available and self.embedder is not None

    # ------------------------------------------------------------------
    # Row → MemoryRecord
    # ------------------------------------------------------------------

    def _row_to_memory(self, row: dict[str, Any]) -> MemoryRecord:
        """Convert a psycopg3 dict row → MemoryRecord.

        JSONB columns (entity_ids, contradicts_ids, metadata) are auto-decoded
        by psycopg3 to Python list/dict.  Boolean/TIMESTAMP columns are native
        Python types.  The MemoryRecord validators handle any remaining quirks.
        """
        return MemoryRecord(
            id=row["id"],
            content=row["content"],
            category=row["category"],
            entity_ids=row["entity_ids"] or [],
            confidence=float(row["confidence"]),
            source=row["source"],
            verified=bool(row["verified"]),
            valid_from=_from_pg_dt(row["valid_from"]),
            valid_until=_from_pg_dt(row["valid_until"]),
            usefulness_score=float(row["usefulness_score"]),
            staleness_score=float(row["staleness_score"]),
            reinforcement_count=int(row["reinforcement_count"]),
            retrieval_count=int(row["retrieval_count"]),
            is_stale=bool(row["is_stale"]),
            is_active=bool(row["is_active"]),
            is_archived=bool(row["is_archived"]),
            superseded_by=row["superseded_by"],
            flagged_for_review=bool(row["flagged_for_review"]),
            contradicts_ids=row["contradicts_ids"] or [],
            is_note=bool(row["is_note"]),
            created_at=_from_pg_dt(row["created_at"]) or _utcnow(),
            updated_at=_from_pg_dt(row["updated_at"]) or _utcnow(),
            last_accessed_at=_from_pg_dt(row["last_accessed_at"]),
            metadata=row["metadata"] or {},
        )

    # ------------------------------------------------------------------
    # MemoryRecord CRUD
    # ------------------------------------------------------------------

    @telemetry.counts_added
    @telemetry.traced("mintmory.add_memory")
    def add_memory(
        self,
        record: MemoryRecord | None = None,
        **fields: Any,
    ) -> MemoryRecord:
        if record is None:
            record = MemoryRecord(**fields)
        self._require_global_tenant(record.tenant_id, "add_memory")
        if not record.entity_ids:
            record.entity_ids = extract_entities(record.content)

        embedding = self._embed(record.content)

        assert self._pool is not None
        with self._pool.connection() as conn:
            self._register_adapters(conn)
            conn.execute(
                """
                INSERT INTO memories (
                  id, content, category, entity_ids, embedding,
                  confidence, source, verified, valid_from, valid_until,
                  usefulness_score, staleness_score, reinforcement_count, retrieval_count,
                  is_stale, is_active, is_archived, superseded_by, flagged_for_review,
                  contradicts_ids, is_note, created_at, updated_at, last_accessed_at, metadata
                ) VALUES (
                  %s, %s, %s, %s::jsonb, %s,
                  %s, %s, %s, %s, %s,
                  %s, %s, %s, %s,
                  %s, %s, %s, %s, %s,
                  %s::jsonb, %s, %s, %s, %s, %s::jsonb
                )
                """,
                (
                    record.id,
                    record.content,
                    record.category.value,
                    json.dumps(record.entity_ids),
                    embedding,
                    record.confidence,
                    record.source.value,
                    record.verified,
                    record.valid_from,
                    record.valid_until,
                    record.usefulness_score,
                    record.staleness_score,
                    record.reinforcement_count,
                    record.retrieval_count,
                    record.is_stale,
                    record.is_active,
                    record.is_archived,
                    record.superseded_by,
                    record.flagged_for_review,
                    json.dumps(record.contradicts_ids),
                    record.is_note,
                    record.created_at,
                    record.updated_at,
                    record.last_accessed_at,
                    json.dumps(record.metadata),
                ),
            )
            conn.commit()
        return record

    def get_memory(self, memory_id: str, tenant_id: str | None = None) -> MemoryRecord | None:
        self._require_global_tenant(tenant_id, "get_memory")
        assert self._pool is not None
        with self._pool.connection() as conn:
            row = _execute_dict(
                conn,
                f"SELECT {_SELECT_MEMORY} FROM memories WHERE id = %s",
                (memory_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def update_memory(self, memory_id: str, **fields: object) -> MemoryRecord:
        """
        Partial update — only provided fields are changed.  ``updated_at``
        is always refreshed.  If ``content`` changes, entity extraction re-runs.

        COUNTER SAFETY (design §6.3): ``usefulness_score``, ``staleness_score``,
        ``reinforcement_count``, ``retrieval_count`` are EXCLUDED from the UPDATE
        unless the caller explicitly includes them in ``fields``.
        """
        if "tenant_id" in fields:
            requested_tenant = fields.pop("tenant_id")
            self._require_global_tenant(
                None if requested_tenant is None else str(requested_tenant),
                "update_memory",
            )

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

        embedding: np.ndarray | None = self._embed(updated.content) if content_changed else None

        sets: list[str] = [
            "content = %s",
            "category = %s",
            "entity_ids = %s::jsonb",
            "confidence = %s",
            "source = %s",
            "verified = %s",
            "valid_from = %s",
            "valid_until = %s",
            "is_stale = %s",
            "is_active = %s",
            "is_archived = %s",
            "superseded_by = %s",
            "flagged_for_review = %s",
            "contradicts_ids = %s::jsonb",
            "is_note = %s",
            "updated_at = %s",
            "last_accessed_at = %s",
            "metadata = %s::jsonb",
        ]
        params: list[Any] = [
            updated.content,
            updated.category.value,
            json.dumps(updated.entity_ids),
            updated.confidence,
            updated.source.value,
            updated.verified,
            updated.valid_from,
            updated.valid_until,
            updated.is_stale,
            updated.is_active,
            updated.is_archived,
            updated.superseded_by,
            updated.flagged_for_review,
            json.dumps(updated.contradicts_ids),
            updated.is_note,
            updated.updated_at,
            updated.last_accessed_at,
            json.dumps(updated.metadata),
        ]

        # Include counter columns only when explicitly provided by caller
        for col in sorted(_COUNTER_COLS):
            if col in fields:
                sets.append(f"{col} = %s")
                params.append(getattr(updated, col))

        if content_changed:
            sets.append("embedding = %s")
            params.append(embedding)

        params.append(memory_id)
        sql = f"UPDATE memories SET {', '.join(sets)} WHERE id = %s"

        assert self._pool is not None
        with self._pool.connection() as conn:
            self._register_adapters(conn)
            conn.execute(sql, params)
            conn.commit()

        result = self.get_memory(memory_id)
        assert result is not None
        return result

    def archive_memory(self, memory_id: str, tenant_id: str | None = None) -> None:
        self._require_global_tenant(tenant_id, "archive_memory")
        assert self._pool is not None
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE memories SET is_archived = TRUE, is_active = FALSE, "
                "updated_at = %s WHERE id = %s",
                (_utcnow(), memory_id),
            )
            conn.commit()

    def supersede_memory(self, memory_id: str, by_id: str, tenant_id: str | None = None) -> None:
        self._require_global_tenant(tenant_id, "supersede_memory")
        assert self._pool is not None
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE memories SET superseded_by = %s, is_active = FALSE, "
                "is_archived = TRUE, updated_at = %s WHERE id = %s",
                (by_id, _utcnow(), memory_id),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Index manifest
    # ------------------------------------------------------------------

    def manifest_get(self, path: str, *, tenant_id: str = "global") -> ManifestEntry | None:
        self._require_global_tenant(tenant_id, "manifest_get")
        assert self._pool is not None
        with self._pool.connection() as conn:
            row = _execute_dict(
                conn,
                "SELECT path, collection, size, mtime, content_hash, index_mode, "
                "memory_ids, online_only, last_seen "
                "FROM index_manifest WHERE path = %s",
                (path,),
            ).fetchone()
        if row is None:
            return None
        return ManifestEntry(
            path=row["path"],
            collection=row["collection"],
            size=int(row["size"]),
            mtime=float(row["mtime"]),
            content_hash=row["content_hash"],
            index_mode=row["index_mode"],
            memory_ids=row["memory_ids"],  # TEXT → string (matches Protocol)
            online_only=int(bool(row["online_only"])),
            last_seen=str(row["last_seen"]) if row["last_seen"] else "",
            tenant_id="global",
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
        self._require_global_tenant(tenant_id, "manifest_upsert")
        assert self._pool is not None
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO index_manifest
                  (path, collection, size, mtime, content_hash, index_mode,
                   memory_ids, online_only, last_seen)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(path) DO UPDATE SET
                  collection   = EXCLUDED.collection,
                  size         = EXCLUDED.size,
                  mtime        = EXCLUDED.mtime,
                  content_hash = EXCLUDED.content_hash,
                  index_mode   = EXCLUDED.index_mode,
                  memory_ids   = EXCLUDED.memory_ids,
                  online_only  = EXCLUDED.online_only,
                  last_seen    = EXCLUDED.last_seen
                """,
                (
                    path,
                    collection,
                    size,
                    mtime,
                    content_hash,
                    index_mode,
                    json.dumps(memory_ids),
                    online_only,
                    _utcnow().isoformat(),
                ),
            )
            conn.commit()

    def manifest_paths(self, collection: str, *, tenant_id: str = "global") -> set[str]:
        self._require_global_tenant(tenant_id, "manifest_paths")
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT path FROM index_manifest WHERE collection = %s", (collection,)
            ).fetchall()
        return {row[0] for row in rows}

    def manifest_delete(self, path: str, *, tenant_id: str = "global") -> None:
        self._require_global_tenant(tenant_id, "manifest_delete")
        assert self._pool is not None
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM index_manifest WHERE path = %s", (path,))
            conn.commit()

    # ------------------------------------------------------------------
    # Feedback — ATOMIC server-side (design §6.3)
    # ------------------------------------------------------------------

    def apply_feedback(
        self, memory_id: str, useful: bool, stale: bool, tenant_id: str | None = None
    ) -> None:
        """
        Atomic server-side feedback (single UPDATE, no read-modify-write).

        Notes (is_note=TRUE): stale vote sets flagged_for_review only.
        Non-notes: stale vote increments staleness_score; exceeding
        STALENESS_THRESHOLD triggers is_stale.
        """
        self._require_global_tenant(tenant_id, "apply_feedback")
        assert self._pool is not None
        with self._pool.connection() as conn:
            result = conn.execute(
                """
                UPDATE memories SET
                  usefulness_score = CASE WHEN %(useful)s
                    THEN LEAST(10.0, usefulness_score + %(ui)s)
                    ELSE usefulness_score END,
                  reinforcement_count = CASE WHEN %(useful)s
                    THEN reinforcement_count + 1
                    ELSE reinforcement_count END,
                  staleness_score = CASE WHEN %(stale)s AND NOT is_note
                    THEN LEAST(10.0, staleness_score + %(si)s)
                    ELSE staleness_score END,
                  is_stale = CASE WHEN %(stale)s AND NOT is_note
                    THEN (LEAST(10.0, staleness_score + %(si)s) >= %(thresh)s)
                    ELSE is_stale END,
                  flagged_for_review = CASE WHEN %(stale)s AND is_note
                    THEN TRUE
                    ELSE flagged_for_review END,
                  updated_at = %(now)s
                WHERE id = %(id)s
                RETURNING id
                """,
                {
                    "useful": useful,
                    "stale": stale,
                    "ui": USEFUL_INCREMENT,
                    "si": STALE_INCREMENT,
                    "thresh": STALENESS_THRESHOLD,
                    "now": _utcnow(),
                    "id": memory_id,
                },
            ).fetchone()
            if result is None:
                conn.rollback()
                raise KeyError(f"memory {memory_id!r} not found")
            conn.commit()

    # ------------------------------------------------------------------
    # Score providers (backend-specific; called from search / anchor_candidates)
    # ------------------------------------------------------------------

    def _fts_scores(self, query: str, limit: int) -> dict[str, float]:
        """tsvector FTS: ts_rank on the generated ``content_tsv`` column."""
        tsquery = _sanitise_fts_query_pg(query)
        if not tsquery:
            return {}
        assert self._pool is not None
        try:
            with self._pool.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT id, ts_rank(content_tsv, to_tsquery('english', %s)) AS rank
                    FROM memories
                    WHERE content_tsv @@ to_tsquery('english', %s)
                    ORDER BY rank DESC
                    LIMIT %s
                    """,
                    (tsquery, tsquery, limit),
                ).fetchall()
            return {row[0]: float(row[1]) for row in rows}
        except Exception:  # noqa: BLE001
            return {}

    def _trigram_scores(self, query: str, limit: int) -> dict[str, float]:
        """
        pg_trgm scoring: two strategies combined via GREATEST.

        **Multi-word / exact-match queries** (any query):
          ``similarity(full_query, content)`` — computes the trigram overlap of
          the WHOLE query string against the WHOLE content.  A memory with the
          exact same content scores 1.0; near-duplicates score 0.7-0.9; memories
          that only share one word score 0.1-0.3.  This is the primary signal.

        **Infix / substring queries** (short single tokens, e.g. "wall"):
          ``word_similarity(token, content)`` — checks whether *token* is a
          substring of content (e.g. "wall" in "firewall").  High score when the
          short token appears as a word-boundary within the document.

        Only per-token word_similarity is added when the token is NOT already
        present as a whole in the full-query similarity (i.e. when the query is
        short enough that individual token matching adds signal).
        """
        if not self._trgm_available:
            return {}
        tokens = _sanitise_trgm_tokens(query)
        full_q = query.strip().lower()
        if not tokens and len(full_q) < 3:
            return {}
        assert self._pool is not None
        try:
            with self._pool.connection() as conn:
                score_exprs: list[str] = []
                where_clauses: list[str] = []
                params: list[Any] = []

                # 1. Full-query string similarity (primary — most discriminating)
                if len(full_q) >= 3:
                    score_exprs.append("similarity(%s, content)")
                    where_clauses.append("similarity(%s, content) > 0.05")
                    params.extend([full_q, full_q])

                # 2. Per-token infix matching (for short single-word substring queries)
                # Only add when query has few tokens to avoid inflating common words
                # (e.g. "kubernetes" in a k8s corpus would tie all k8s memories at 1.0).
                if len(tokens) <= 2:
                    for tok in tokens:
                        score_exprs.append("word_similarity(%s, content)")
                        where_clauses.append("word_similarity(%s, content) > 0.1")
                        params.extend([tok, tok])

                if not score_exprs:
                    return {}

                sql = (
                    f"SELECT id, GREATEST({', '.join(score_exprs)}) AS sim "
                    f"FROM memories "
                    f"WHERE {' OR '.join(where_clauses)} "
                    f"ORDER BY sim DESC "
                    f"LIMIT %s"
                )
                params.append(limit)
                rows = conn.execute(sql, params).fetchall()
            return {row[0]: float(row[1]) for row in rows}
        except Exception:  # noqa: BLE001
            return {}

    def _vector_scores(
        self,
        query: str,
        query_embedding: np.ndarray | None,
        limit: int,
    ) -> dict[str, float]:
        """
        pgvector cosine exact scan.

        Dimension guard: ``WHERE vector_dims(embedding) = %s`` skips
        mismatched-dimension rows silently (design §6.2).
        Returns ``{id: -distance}`` (higher = better match).
        """
        if not self.vector_search_available():
            return {}
        emb: np.ndarray | None
        if query_embedding is not None:
            emb = np.asarray(query_embedding, dtype=np.float32)
        else:
            emb = self._embed(query)
        if emb is None:
            return {}
        assert self._pool is not None
        try:
            with self._pool.connection() as conn:
                self._register_adapters(conn)
                rows = conn.execute(
                    """
                    SELECT id, (embedding <=> %s) AS dist
                    FROM memories
                    WHERE embedding IS NOT NULL
                      AND vector_dims(embedding) = %s
                    ORDER BY dist ASC
                    LIMIT %s
                    """,
                    (emb, int(emb.shape[0]), limit),
                ).fetchall()
            return {row[0]: -float(row[1]) for row in rows}
        except Exception:  # noqa: BLE001
            return {}

    # ------------------------------------------------------------------
    # Internal data-access callables (passed to hybrid_search pipeline)
    # ------------------------------------------------------------------

    def _load_memories(self, ids: list[str]) -> list[MemoryRecord]:
        if not ids:
            return []
        assert self._pool is not None
        placeholders = ", ".join("%s" for _ in ids)
        with self._pool.connection() as conn:
            rows = _execute_dict(
                conn,
                f"SELECT {_SELECT_MEMORY} FROM memories WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def _bump_retrieval(self, ids: list[str], now: datetime) -> None:
        if not ids:
            return
        assert self._pool is not None
        placeholders = ", ".join("%s" for _ in ids)
        with self._pool.connection() as conn:
            conn.execute(
                f"UPDATE memories SET retrieval_count = retrieval_count + 1, "
                f"last_accessed_at = %s WHERE id IN ({placeholders})",
                [now, *ids],
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Lazy config resolvers
    # ------------------------------------------------------------------

    def _resolve_vector_rrf_weight(self) -> float:
        if self._vector_rrf_weight is None:
            from mintmory.core.config import SearchSettings  # noqa: PLC0415

            self._vector_rrf_weight = SearchSettings().vector_rrf_weight
        return self._vector_rrf_weight

    def _resolve_note_bonus(self) -> float:
        if self._note_bonus is None:
            from mintmory.core.config import NoteSettings  # noqa: PLC0415

            self._note_bonus = NoteSettings().note_bonus
        return self._note_bonus

    def _resolve_auto_include_cap(self) -> int:
        if self._auto_include_cap is None:
            from mintmory.core.config import NoteSettings  # noqa: PLC0415

            self._auto_include_cap = NoteSettings().auto_include_cap
        return self._auto_include_cap

    # ------------------------------------------------------------------
    # Search (delegates to shared hybrid_search pipeline)
    # ------------------------------------------------------------------

    @telemetry.traced("mintmory.search")
    @telemetry.timed_phase("total")
    def search(
        self,
        request: SearchRequest,
        query_embedding: np.ndarray | None = None,
        *,
        tenant_id: str | None = None,
    ) -> SearchResponse:
        """Hybrid search: FTS + trigram + vector via shared fuse_and_search."""
        self._require_global_tenant(tenant_id, "search")
        pool_size = max(request.limit * 5, 50)
        fts_scores, trigram_scores, vec_scores = collect_scores(
            fts_fn=lambda: self._fts_scores(request.query, pool_size),
            trigram_fn=lambda: self._trigram_scores(request.query, pool_size),
            vector_fn=lambda: self._vector_scores(request.query, query_embedding, pool_size),
        )
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
            note_bonus=self._resolve_note_bonus(),
            auto_include_cap=self._resolve_auto_include_cap(),
            now=_utcnow(),
        )

    @telemetry.traced("mintmory.search_around")
    @telemetry.timed_phase("graph")
    def search_around(
        self,
        anchor_ids: list[str],
        spec: SearchAroundSpec,
        tenant_id: str | None = None,
    ) -> list[str]:
        """BFS over concept_links up to spec.depth (mirrors SqliteBackend logic)."""
        self._require_global_tenant(tenant_id, "search_around")
        if not anchor_ids:
            return []
        assert self._pool is not None
        sym_values = {lt.value for lt in SYMMETRIC_LINK_TYPES}
        type_filter: set[str] | None = (
            {lt.value for lt in spec.link_types} if spec.link_types else None
        )

        visited: set[str] = set(anchor_ids)
        frontier: set[str] = set(anchor_ids)
        result: set[str] = set()
        anchor_set = set(anchor_ids)

        for _ in range(spec.depth):
            if not frontier:
                break
            placeholders = ", ".join("%s" for _ in frontier)
            params_list: list[Any] = [spec.min_strength, *frontier, *frontier]
            sql = (
                f"SELECT source_memory_id, target_memory_id, link_type "
                f"FROM concept_links "
                f"WHERE strength >= %s AND "
                f"(source_memory_id IN ({placeholders}) "
                f" OR target_memory_id IN ({placeholders}))"
            )
            with self._pool.connection() as conn:
                rows = conn.execute(sql, params_list).fetchall()

            next_frontier: set[str] = set()
            for row in rows:
                src, tgt, ltype = row[0], row[1], row[2]
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

    def get_annotating_notes(
        self, memory_id: str, cap: int, tenant_id: str | None = None
    ) -> list[MemoryRecord]:
        self._require_global_tenant(tenant_id, "get_annotating_notes")
        if cap <= 0:
            return []
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = _execute_dict(
                conn,
                """
                SELECT m.id, m.content, m.category, m.entity_ids, m.confidence,
                  m.source, m.verified, m.valid_from, m.valid_until,
                  m.usefulness_score, m.staleness_score, m.reinforcement_count,
                  m.retrieval_count, m.is_stale, m.is_active, m.is_archived,
                  m.superseded_by, m.flagged_for_review, m.contradicts_ids, m.is_note,
                  m.created_at, m.updated_at, m.last_accessed_at, m.metadata
                FROM concept_links l
                JOIN memories m ON m.id = l.source_memory_id
                WHERE l.target_memory_id = %s AND l.link_type = %s
                  AND m.is_note = TRUE AND m.is_archived = FALSE
                ORDER BY l.strength DESC, m.created_at DESC
                LIMIT %s
                """,
                (memory_id, ConceptLinkType.ANNOTATES.value, cap),
            ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def get_annotating_descriptions(
        self, memory_id: str, cap: int, tenant_id: str | None = None
    ) -> list[MemoryRecord]:
        self._require_global_tenant(tenant_id, "get_annotating_descriptions")
        if cap <= 0:
            return []
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = _execute_dict(
                conn,
                """
                SELECT m.id, m.content, m.category, m.entity_ids, m.confidence,
                  m.source, m.verified, m.valid_from, m.valid_until,
                  m.usefulness_score, m.staleness_score, m.reinforcement_count,
                  m.retrieval_count, m.is_stale, m.is_active, m.is_archived,
                  m.superseded_by, m.flagged_for_review, m.contradicts_ids, m.is_note,
                  m.created_at, m.updated_at, m.last_accessed_at, m.metadata
                FROM concept_links l
                JOIN memories m ON m.id = l.source_memory_id
                WHERE l.target_memory_id = %s AND l.link_type = %s
                  AND m.is_note = FALSE AND m.is_archived = FALSE
                  AND (m.metadata->>'kind') = 'image_description'
                ORDER BY m.created_at DESC
                LIMIT %s
                """,
                (memory_id, ConceptLinkType.ANNOTATES.value, cap),
            ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def find_image_file_record(
        self, path_or_rel: str, tenant_id: str | None = None
    ) -> MemoryRecord | None:
        self._require_global_tenant(tenant_id, "find_image_file_record")
        assert self._pool is not None
        with self._pool.connection() as conn:
            row = _execute_dict(
                conn,
                f"""
                SELECT {_SELECT_MEMORY} FROM memories
                WHERE is_archived = FALSE
                  AND (metadata->>'kind') IS NULL
                  AND (metadata->>'path' = %s OR metadata->>'rel' = %s)
                  AND lower(metadata->>'ext') IN (
                      '.jpg','.jpeg','.png','.gif','.webp','.bmp','.svg'
                  )
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (path_or_rel, path_or_rel),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def anchor_candidates(
        self, about: str, limit: int = 5, tenant_id: str | None = None
    ) -> list[tuple[float, MemoryRecord]]:
        """Side-effect-free candidate lookup for note anchoring."""
        self._require_global_tenant(tenant_id, "anchor_candidates")
        pool_size = max(limit * 5, 50)
        return fuse_and_rank(
            fts_scores=self._fts_scores(about, pool_size),
            trigram_scores=self._trigram_scores(about, pool_size),
            vector_scores=self._vector_scores(about, None, pool_size),
            vector_rrf_weight=self._resolve_vector_rrf_weight(),
            load_memories_fn=self._load_memories,
            limit=limit,
        )

    def list_image_file_records(self, tenant_id: str | None = None) -> list[MemoryRecord]:
        self._require_global_tenant(tenant_id, "list_image_file_records")
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = _execute_dict(
                conn,
                f"""
                SELECT {_SELECT_MEMORY} FROM memories
                WHERE is_archived = FALSE
                  AND (metadata->>'kind') IS NULL
                  AND (metadata->>'ext') IS NOT NULL
                ORDER BY metadata->>'rel', id
                """,
            ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def memory_exists_with_content(self, content: str, tenant_id: str | None = None) -> bool:
        self._require_global_tenant(tenant_id, "memory_exists_with_content")
        assert self._pool is not None
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM memories WHERE content = %s LIMIT 1", (content,)
            ).fetchone()
        return row is not None

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
        tenant_id: str | None = None,
    ) -> list[MemoryRecord]:
        self._require_global_tenant(tenant_id, "list_notes")
        effective_now = now or _utcnow()
        assert self._pool is not None
        params: list[Any] = []
        sql = f"SELECT {_SELECT_MEMORY} FROM memories WHERE is_note = TRUE"

        if upcoming:
            sql += " AND valid_from > %s ORDER BY valid_from ASC"
            params.append(effective_now)
        elif overdue:
            sql += (
                " AND valid_from IS NOT NULL AND valid_from < %s "
                "AND is_archived = FALSE ORDER BY valid_from ASC"
            )
            params.append(effective_now)
        else:
            if not include_archived:
                sql += " AND is_archived = FALSE"
            sql += " ORDER BY created_at DESC"

        sql += " LIMIT %s"
        params.append(limit)

        with self._pool.connection() as conn:
            rows = _execute_dict(conn, sql, params).fetchall()
        records = [self._row_to_memory(r) for r in rows]

        # Post-filter in Python (same approach as SqliteBackend)
        if entity is not None:
            entity_lower = entity.lower()
            records = [r for r in records if entity_lower in {e.lower() for e in r.entity_ids}]
        if anchor_substr is not None:
            anchor_lower = anchor_substr.lower()
            records = [
                r for r in records if anchor_lower in str(r.metadata.get("anchor", "")).lower()
            ]
        return records

    def list_memories(
        self,
        filter: MemoryFilter | None = None,
        *,
        tenant_id: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryRecord]:
        self._require_global_tenant(tenant_id, "list_memories")
        raise TenancyNotSupportedError("list_memories")

    # ------------------------------------------------------------------
    # ConceptLink
    # ------------------------------------------------------------------

    def add_link(self, link: ConceptLink) -> ConceptLink:
        self._require_global_tenant(link.tenant_id, "add_link")
        assert self._pool is not None
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO concept_links
                  (id, source_memory_id, target_memory_id, link_type, entity,
                   strength, confidence, source, verified, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_memory_id, target_memory_id, link_type)
                DO NOTHING
                """,
                (
                    link.id,
                    link.source_memory_id,
                    link.target_memory_id,
                    link.link_type.value,
                    link.entity,
                    link.strength,
                    link.confidence,
                    link.source.value,
                    link.verified,
                    link.created_at,
                    link.updated_at,
                ),
            )
            conn.commit()
        return link

    def get_links(
        self,
        memory_id: str,
        link_type: ConceptLinkType | None = None,
        tenant_id: str | None = None,
    ) -> list[ConceptLink]:
        self._require_global_tenant(tenant_id, "get_links")
        assert self._pool is not None
        sql = (
            "SELECT id, source_memory_id, target_memory_id, link_type, entity, "
            "strength, confidence, source, verified, created_at, updated_at "
            "FROM concept_links "
            "WHERE (source_memory_id = %s OR target_memory_id = %s)"
        )
        params: list[Any] = [memory_id, memory_id]
        if link_type is not None:
            sql += " AND link_type = %s"
            params.append(link_type.value)
        with self._pool.connection() as conn:
            rows = _execute_dict(conn, sql, params).fetchall()
        return [self._row_to_link(r) for r in rows]

    def _row_to_link(self, row: dict[str, Any]) -> ConceptLink:
        return ConceptLink(
            id=row["id"],
            source_memory_id=row["source_memory_id"],
            target_memory_id=row["target_memory_id"],
            link_type=row["link_type"],
            entity=row["entity"],
            strength=float(row["strength"]),
            confidence=float(row["confidence"]),
            source=row["source"],
            verified=bool(row["verified"]),
            created_at=_from_pg_dt(row["created_at"]) or _utcnow(),
            updated_at=_from_pg_dt(row["updated_at"]) or _utcnow(),
        )

    # ------------------------------------------------------------------
    # QuerySession
    # ------------------------------------------------------------------

    def create_session(self, session: QuerySession) -> QuerySession:
        self._require_global_tenant(session.tenant_id, "create_session")
        assert self._pool is not None
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO query_sessions
                  (id, query_text, created_at, confidence_rating, reasoning,
                   useful_ids, stale_ids, concluded)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                """,
                (
                    session.id,
                    session.query_text,
                    session.created_at,
                    session.confidence_rating,
                    session.reasoning,
                    json.dumps(session.useful_ids),
                    json.dumps(session.stale_ids),
                    session.concluded,
                ),
            )
            conn.commit()
        return session

    def get_session(self, session_id: str, tenant_id: str | None = None) -> QuerySession | None:
        self._require_global_tenant(tenant_id, "get_session")
        assert self._pool is not None
        with self._pool.connection() as conn:
            row = _execute_dict(
                conn,
                "SELECT id, query_text, created_at, confidence_rating, reasoning, "
                "useful_ids, stale_ids, concluded "
                "FROM query_sessions WHERE id = %s",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return QuerySession(
            id=row["id"],
            query_text=row["query_text"],
            created_at=_from_pg_dt(row["created_at"]) or _utcnow(),
            confidence_rating=row["confidence_rating"],
            reasoning=row["reasoning"],
            useful_ids=row["useful_ids"] or [],  # JSONB → list (auto-decoded)
            stale_ids=row["stale_ids"] or [],
            concluded=bool(row["concluded"]),
        )

    def record_query_results(self, results: list[QueryResult]) -> None:
        if not results:
            return
        for result in results:
            self._require_global_tenant(result.tenant_id, "record_query_results")
        assert self._pool is not None
        sql = """
            INSERT INTO query_results
              (session_id, memory_id, relevance_score,
               was_accessed, was_useful, was_stale)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id, memory_id) DO UPDATE SET
              relevance_score = EXCLUDED.relevance_score,
              was_accessed    = EXCLUDED.was_accessed,
              was_useful      = EXCLUDED.was_useful,
              was_stale       = EXCLUDED.was_stale
        """
        rows = [
            (
                r.session_id,
                r.memory_id,
                r.relevance_score,
                r.was_accessed,
                r.was_useful,
                r.was_stale,
            )
            for r in results
        ]
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
            conn.commit()

    def update_session_feedback(
        self,
        session_id: str,
        confidence_rating: int | None,
        reasoning: str | None,
        useful_ids: list[str],
        stale_ids: list[str],
    ) -> None:
        useful_set = set(useful_ids)
        stale_set = set(stale_ids)
        assert self._pool is not None
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE query_sessions SET
                  confidence_rating = %s, reasoning = %s,
                  useful_ids = %s::jsonb, stale_ids = %s::jsonb, concluded = TRUE
                WHERE id = %s
                """,
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
                    """
                    UPDATE query_results SET was_useful = %s, was_stale = %s
                    WHERE session_id = %s AND memory_id = %s
                    """,
                    (
                        memory_id in useful_set,
                        memory_id in stale_set,
                        session_id,
                        memory_id,
                    ),
                )
            conn.commit()

    def mark_session_concluded(self, session_id: str) -> None:
        assert self._pool is not None
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE query_sessions SET concluded = TRUE WHERE id = %s",
                (session_id,),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # MemorySummary
    # ------------------------------------------------------------------

    def upsert_summary(self, summary: MemorySummary) -> MemorySummary:
        self._require_global_tenant(summary.tenant_id, "upsert_summary")
        existing = self.get_summary(summary.concept)
        summary_id = existing.id if existing is not None else summary.id
        assert self._pool is not None
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO memory_summaries
                  (id, concept, summary_text, memory_count, is_current, generated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(concept) DO UPDATE SET
                  summary_text = EXCLUDED.summary_text,
                  memory_count = EXCLUDED.memory_count,
                  is_current   = EXCLUDED.is_current,
                  generated_at = EXCLUDED.generated_at
                """,
                (
                    summary_id,
                    summary.concept,
                    summary.summary_text,
                    summary.memory_count,
                    summary.is_current,
                    summary.generated_at,
                ),
            )
            conn.commit()
        result = self.get_summary(summary.concept)
        assert result is not None
        return result

    def get_summary(self, concept: str, tenant_id: str = "global") -> MemorySummary | None:
        self._require_global_tenant(tenant_id, "get_summary")
        assert self._pool is not None
        with self._pool.connection() as conn:
            row = _execute_dict(
                conn,
                "SELECT id, concept, summary_text, memory_count, is_current, generated_at "
                "FROM memory_summaries WHERE concept = %s",
                (concept,),
            ).fetchone()
        if row is None:
            return None
        return MemorySummary(
            id=row["id"],
            concept=row["concept"],
            summary_text=row["summary_text"],
            memory_count=int(row["memory_count"]),
            is_current=bool(row["is_current"]),
            generated_at=_from_pg_dt(row["generated_at"]) or _utcnow(),
        )

    def list_summaries(self, tenant_id: str | None = None) -> list[MemorySummary]:
        self._require_global_tenant(tenant_id, "list_summaries")
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = _execute_dict(
                conn,
                "SELECT id, concept, summary_text, memory_count, is_current, generated_at "
                "FROM memory_summaries ORDER BY concept",
            ).fetchall()
        return [
            MemorySummary(
                id=r["id"],
                concept=r["concept"],
                summary_text=r["summary_text"],
                memory_count=int(r["memory_count"]),
                is_current=bool(r["is_current"]),
                generated_at=_from_pg_dt(r["generated_at"]) or _utcnow(),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self, tenant_id: str | None = None) -> MemoryStats:
        self._require_global_tenant(tenant_id, "get_stats")
        assert self._pool is not None
        with self._pool.connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE is_active = TRUE AND is_archived = FALSE"
            ).fetchone()[0]
            stale = conn.execute("SELECT COUNT(*) FROM memories WHERE is_stale = TRUE").fetchone()[
                0
            ]
            archived = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE is_archived = TRUE"
            ).fetchone()[0]
            links = conn.execute("SELECT COUNT(*) FROM concept_links").fetchone()[0]
            summaries = conn.execute("SELECT COUNT(*) FROM memory_summaries").fetchone()[0]
            avg_row = conn.execute(
                "SELECT AVG(usefulness_score), AVG(staleness_score) "
                "FROM memories WHERE is_active = TRUE AND is_archived = FALSE"
            ).fetchone()
            avg_use = float(avg_row[0]) if avg_row and avg_row[0] is not None else 0.0
            avg_stale = float(avg_row[1]) if avg_row and avg_row[1] is not None else 0.0
            entity_rows = conn.execute(
                "SELECT entity_ids FROM memories WHERE is_active = TRUE AND is_archived = FALSE"
            ).fetchall()

        counter: Counter[str] = Counter()
        for row in entity_rows:
            for entity in row[0] or []:
                counter[entity] += 1
        top_concepts = counter.most_common(20)

        return MemoryStats(
            total_memories=int(total),
            active=int(active),
            stale=int(stale),
            archived=int(archived),
            concept_links=int(links),
            memory_summaries=int(summaries),
            avg_usefulness_score=avg_use,
            avg_staleness_score=avg_stale,
            top_concepts=top_concepts,
        )

    # ------------------------------------------------------------------
    # Dreaming helpers (absorbed from dreaming.py's raw connect() sites)
    # ------------------------------------------------------------------

    def get_flagged_memories(self, tenant_id: str | None = None) -> list[MemoryRecord]:
        self._require_global_tenant(tenant_id, "get_flagged_memories")
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = _execute_dict(
                conn,
                f"SELECT {_SELECT_MEMORY} FROM memories WHERE flagged_for_review = TRUE",
            ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def get_never_accessed_stale(
        self, days_old: int = 7, min_staleness: float = 3.0, tenant_id: str | None = None
    ) -> list[MemoryRecord]:
        self._require_global_tenant(tenant_id, "get_never_accessed_stale")
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = _execute_dict(
                conn,
                f"SELECT {_SELECT_MEMORY} FROM memories "
                f"WHERE last_accessed_at IS NULL "
                f"  AND staleness_score >= %s "
                f"  AND is_archived = FALSE "
                f"  AND is_note = FALSE",
                (min_staleness,),
            ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def get_high_staleness_useful(
        self,
        min_staleness: float = 5.0,
        min_usefulness: float = 3.0,
        tenant_id: str | None = None,
    ) -> list[MemoryRecord]:
        self._require_global_tenant(tenant_id, "get_high_staleness_useful")
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = _execute_dict(
                conn,
                f"SELECT {_SELECT_MEMORY} FROM memories "
                f"WHERE staleness_score >= %s "
                f"  AND usefulness_score >= %s "
                f"  AND is_archived = FALSE "
                f"  AND is_note = FALSE",
                (min_staleness, min_usefulness),
            ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def get_anomaly_high_staleness_useful_ids(
        self, min_staleness: float, min_usefulness: float, tenant_id: str | None = None
    ) -> list[str]:
        self._require_global_tenant(tenant_id, "get_anomaly_high_staleness_useful_ids")
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id FROM memories "
                "WHERE staleness_score >= %s AND usefulness_score >= %s "
                "  AND is_archived = FALSE AND is_note = FALSE "
                "ORDER BY id",
                (min_staleness, min_usefulness),
            ).fetchall()
        return [r[0] for r in rows]

    def get_anomaly_never_accessed_ids(
        self, cutoff_iso: str, tenant_id: str | None = None
    ) -> list[str]:
        self._require_global_tenant(tenant_id, "get_anomaly_never_accessed_ids")
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id FROM memories "
                "WHERE retrieval_count = 0 AND created_at < %s "
                "  AND is_active = TRUE AND is_archived = FALSE AND is_note = FALSE "
                "ORDER BY id",
                (cutoff_iso,),
            ).fetchall()
        return [r[0] for r in rows]

    def get_anomaly_flagged_ids(self, tenant_id: str | None = None) -> list[str]:
        self._require_global_tenant(tenant_id, "get_anomaly_flagged_ids")
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id FROM memories WHERE flagged_for_review = TRUE ORDER BY id"
            ).fetchall()
        return [r[0] for r in rows]

    def list_active_memory_ids(
        self, *, ordered: bool = False, tenant_id: str | None = None
    ) -> list[str]:
        self._require_global_tenant(tenant_id, "list_active_memory_ids")
        assert self._pool is not None
        sql = "SELECT id FROM memories WHERE is_active = TRUE AND is_archived = FALSE"
        if ordered:
            sql += " ORDER BY id"
        with self._pool.connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [r[0] for r in rows]

    def get_stale_archivable_ids(
        self, min_staleness: float, cutoff_iso: str, tenant_id: str | None = None
    ) -> list[str]:
        self._require_global_tenant(tenant_id, "get_stale_archivable_ids")
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id FROM memories "
                "WHERE is_stale = TRUE AND staleness_score >= %s AND is_archived = FALSE "
                "  AND is_note = FALSE "
                "  AND (last_accessed_at IS NULL OR last_accessed_at < %s) "
                "ORDER BY id",
                (min_staleness, cutoff_iso),
            ).fetchall()
        return [r[0] for r in rows]

    def get_rehabilitable_rows(
        self, cutoff_iso: str, tenant_id: str | None = None
    ) -> list[tuple[str, float]]:
        self._require_global_tenant(tenant_id, "get_rehabilitable_rows")
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT id, staleness_score FROM memories "
                "WHERE is_stale = TRUE AND usefulness_score > staleness_score "
                "  AND is_archived = FALSE "
                "  AND last_accessed_at IS NOT NULL AND last_accessed_at >= %s "
                "ORDER BY id",
                (cutoff_iso,),
            ).fetchall()
        return [(r[0], float(r[1])) for r in rows]

    def get_existing_relates_to_pairs(self, tenant_id: str | None = None) -> set[frozenset[str]]:
        self._require_global_tenant(tenant_id, "get_existing_relates_to_pairs")
        assert self._pool is not None
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT source_memory_id, target_memory_id FROM concept_links WHERE link_type = %s",
                (ConceptLinkType.RELATES_TO.value,),
            ).fetchall()
        return {frozenset({r[0], r[1]}) for r in rows}

    @staticmethod
    def _require_global_tenant(tenant_id: str | None, operation: str) -> None:
        if tenant_id is not None and tenant_id != "global":
            raise TenancyNotSupportedError(operation)

    @staticmethod
    def _interim_global_tenant() -> Tenant:
        sentinel = datetime(1970, 1, 1)
        return Tenant(
            id="global",
            name="Global (default) tenant",
            is_active=True,
            created_at=sentinel,
            updated_at=sentinel,
        )

    def create_tenant(self, tenant_id: str, name: str = "") -> Tenant:
        raise TenancyNotSupportedError("create_tenant")

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        if tenant_id == "global":
            return self._interim_global_tenant()
        return None

    def list_tenants(self) -> list[Tenant]:
        return [self._interim_global_tenant()]

    def set_tenant_active(self, tenant_id: str, active: bool) -> Tenant:
        raise TenancyNotSupportedError("set_tenant_active")

    def _ensure_tenant_columns(self, conn: Any) -> None:
        raise NotImplementedError


def plan_pg_tenant_migration(
    columns: dict[str, set[str]],
    uniques: dict[str, list[tuple[str, tuple[str, ...]]]],
    primary_keys: dict[str, tuple[str, tuple[str, ...]]],
    indexes: set[str],
) -> list[str]:
    raise NotImplementedError


def pg_catalog_snapshot(
    column_rows: list[dict[str, Any]],
    constraint_rows: list[dict[str, Any]],
    index_rows: list[dict[str, Any]],
) -> tuple[
    dict[str, set[str]],
    dict[str, list[tuple[str, tuple[str, ...]]]],
    dict[str, tuple[str, tuple[str, ...]]],
    set[str],
]:
    raise NotImplementedError
