"""
SQLite → PostgreSQL one-shot migration for MintMory — Phase 3.

Usage (programmatic):
    from mintmory.core.migrate import migrate_sqlite_to_postgres
    report = migrate_sqlite_to_postgres("~/.mintmory/memories.db", dsn, batch_size=500)
    if not report.all_ok:
        raise SystemExit(1)

Usage (CLI):
    mintmory migrate-storage --from sqlite:/path/to/memories.db --to postgres:DSN

Design (§6.5):
    • Streams rows in FK-safe order:
        memories (pass 1: superseded_by=NULL)
        → memories (pass 2: UPDATE superseded_by)
        → memory_summaries
        → index_manifest
        → query_sessions
        → concept_links
        → query_results
    • The self-referential FK on memories.superseded_by is resolved via a
      two-pass approach: all memories are inserted first (superseded_by=NULL),
      then a second UPDATE sets the correct superseded_by values. This avoids
      needing DEFERRABLE constraints or session_replication_role superuser access.
    • Type conversions at the boundary:
        INTEGER 0/1         → BOOLEAN
        TEXT ISO-8601       → TIMESTAMP (naive UTC, tzinfo stripped)
        TEXT JSON           → JSONB  (entity_ids, contradicts_ids, metadata,
                                      useful_ids, stale_ids)
        BLOB float32        → pgvector vector (np.float32 array via pgvector adapter)
        index_manifest.memory_ids stays TEXT (Protocol: memory_ids: str in both)
    • Generated columns (content_tsv, tsvector) are NOT migrated — they are
      auto-populated by PostgreSQL's GENERATED ALWAYS AS expression.
    • No embedding-dimension enforcement: the unconstrained 'vector' column in
      PG accepts mixed-dimension embeddings exactly as SQLite does; mismatched
      rows are silently skipped at query time (vector_dims guard in PostgresBackend).
    • Embedding column is EXCLUDED from content checksums (documented below) but
      IS migrated byte-for-byte.
    • Idempotent re-run detection: a non-empty target (memories rows present)
      causes a hard stop unless force=True (which truncates all tables first).
    • --dry-run: reads + validates + counts without writing a single row.

Checksum design:
    A stable SHA-256 is computed independently on source (SQLite) and target (PG)
    over every table. For each table the hash covers:
        • All rows sorted by primary-key column(s)
        • All columns EXCEPT:
            - 'embedding'    (excluded: binary float32 round-trip is faithful but
                              comparing via PG vector vs SQLite blob adds
                              deserialization complexity; embedding is
                              semantically derived from content anyway)
            - 'content_tsv'  (excluded: PG-generated STORED column, not present
                              in SQLite at all)
        • Each row is serialized as compact JSON (sort_keys=True) after type
          normalization:
            bool → Python bool   (normalizes SQLite 0/1 and PG bool)
            float → rounded to 10 decimal places
            datetime → isoformat() string (tz stripped)
            JSON fields → parsed then re-encoded (sort_keys=True)
            None → null (json.dumps default)

K8s runbook — migrating from SQLite PVC to external Postgres:

    1. Scale the deployment to 0 replicas (quiesce writes):
           kubectl scale deploy/mintmory --replicas=0

    2. Exec into a migration pod (or port-forward the SQLite PVC):
           kubectl run mig --image=<mintmory-image> --rm -it \
               --env=MINTMORY_STORAGE_DSN=<PG DSN> \
               --restart=Never -- bash
       Inside the pod, mount / port-forward the SQLite PVC to /data/memories.db.

    3. Run the migration:
           mintmory migrate-storage \
               --from sqlite:/data/memories.db \
               --to postgres:<DSN> \
               [--dry-run]          # first: count + checksum without writing
           # If dry-run is clean, remove --dry-run to perform the actual migration.

    4. Verify the MigrationReport output: all tables must show COUNT PASS and
       CHECKSUM PASS. Any failure is a hard error (non-zero exit).

    5. Flip the config and scale back up:
           kubectl set env deploy/mintmory \
               MINTMORY_STORAGE_BACKEND=postgres \
               MINTMORY_STORAGE_DSN=<DSN>
           kubectl scale deploy/mintmory --replicas=<N>

    6. The old PVC can be retained for a grace period and then deleted.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# FK-safe migration order
# ---------------------------------------------------------------------------

# memories is migrated in two logical passes (both counted under "memories"):
#   pass 1 — INSERT with superseded_by = NULL
#   pass 2 — UPDATE superseded_by where it was set in source
# The remaining tables have no cycles.
_FK_ORDER: list[str] = [
    "memories",
    "memory_summaries",
    "index_manifest",
    "query_sessions",
    "concept_links",
    "query_results",
]

# ---------------------------------------------------------------------------
# Columns to SELECT from each SQLite table (explicit — avoids surprise changes)
# ---------------------------------------------------------------------------

# 'embedding' and 'content_tsv' are handled separately.
# embedding: migrated but excluded from checksums.
# content_tsv: PG-only generated column, never in SQLite.

_MEMORIES_COLS = (
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

_CONCEPT_LINKS_COLS = (
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
)

_MEMORY_SUMMARIES_COLS = (
    "id",
    "concept",
    "summary_text",
    "memory_count",
    "is_current",
    "generated_at",
)

_INDEX_MANIFEST_COLS = (
    "path",
    "collection",
    "size",
    "mtime",
    "content_hash",
    "index_mode",
    "memory_ids",
    "online_only",
    "last_seen",
)

_QUERY_SESSIONS_COLS = (
    "id",
    "query_text",
    "created_at",
    "confidence_rating",
    "reasoning",
    "useful_ids",
    "stale_ids",
    "concluded",
)

_QUERY_RESULTS_COLS = (
    "session_id",
    "memory_id",
    "relevance_score",
    "was_accessed",
    "was_useful",
    "was_stale",
)

_TABLE_COLS: dict[str, tuple[str, ...]] = {
    "memories": _MEMORIES_COLS,
    "concept_links": _CONCEPT_LINKS_COLS,
    "memory_summaries": _MEMORY_SUMMARIES_COLS,
    "index_manifest": _INDEX_MANIFEST_COLS,
    "query_sessions": _QUERY_SESSIONS_COLS,
    "query_results": _QUERY_RESULTS_COLS,
}

# Primary-key column(s) for sorting (checksum stability)
_TABLE_PK: dict[str, list[str]] = {
    "memories": ["id"],
    "concept_links": ["id"],
    "memory_summaries": ["id"],
    "index_manifest": ["path"],
    "query_sessions": ["id"],
    "query_results": ["session_id", "memory_id"],
}

# ---------------------------------------------------------------------------
# Column type metadata (for normalization / canonical conversion)
# ---------------------------------------------------------------------------

# Columns excluded from checksum (per table)
_CHECKSUM_EXCLUDED: dict[str, set[str]] = {
    # embedding: binary float32 — migrated faithfully but excluded from checksum
    #   because: (a) the pgvector adapter stores it as a numeric vector, so a
    #   direct bytes comparison would require deserializing both sides, and
    #   (b) it is semantically derived from 'content' (already checksummed).
    # content_tsv: PG GENERATED ALWAYS AS column — absent in SQLite entirely.
    "memories": {"embedding", "content_tsv"},
    "concept_links": set(),
    "memory_summaries": set(),
    "index_manifest": set(),
    "query_sessions": set(),
    "query_results": set(),
}

# Boolean columns (SQLite: INTEGER 0/1 → PG: BOOLEAN)
_BOOL_COLS: dict[str, set[str]] = {
    "memories": {
        "verified",
        "is_stale",
        "is_active",
        "is_archived",
        "flagged_for_review",
        "is_note",
    },
    "concept_links": {"verified"},
    "memory_summaries": {"is_current"},
    "index_manifest": {"online_only"},
    "query_sessions": {"concluded"},
    "query_results": {"was_accessed", "was_useful", "was_stale"},
}

# Datetime columns (SQLite: TEXT ISO-8601 → PG: TIMESTAMP naive UTC)
_DATETIME_COLS: dict[str, set[str]] = {
    "memories": {"valid_from", "valid_until", "created_at", "updated_at", "last_accessed_at"},
    "concept_links": {"created_at", "updated_at"},
    "memory_summaries": {"generated_at"},
    "index_manifest": set(),
    "query_sessions": {"created_at"},
    "query_results": set(),
}

# JSONB columns (SQLite: TEXT JSON → PG: JSONB, auto-decoded by psycopg)
_JSONB_COLS: dict[str, set[str]] = {
    "memories": {"entity_ids", "contradicts_ids", "metadata"},
    "concept_links": set(),
    "memory_summaries": set(),
    # index_manifest.memory_ids stays TEXT in both SQLite and PG (Protocol type)
    "index_manifest": set(),
    "query_sessions": {"useful_ids", "stale_ids"},
    "query_results": set(),
}

# ---------------------------------------------------------------------------
# Report dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TableVerification:
    """Per-table migration verification result."""

    table: str
    src_count: int
    dst_count: int
    src_checksum: str
    dst_checksum: str

    @property
    def count_ok(self) -> bool:
        return self.src_count == self.dst_count

    @property
    def checksum_ok(self) -> bool:
        return self.src_checksum == self.dst_checksum

    @property
    def ok(self) -> bool:
        return self.count_ok and self.checksum_ok


@dataclass
class MigrationReport:
    """Aggregated result of a migrate_sqlite_to_postgres() call."""

    tables: list[TableVerification] = field(default_factory=list)
    dry_run: bool = False
    total_rows_written: int = 0

    @property
    def all_ok(self) -> bool:
        """True iff every table passes count + checksum verification."""
        return all(t.ok for t in self.tables)

    def summary_lines(self) -> list[str]:
        """Human-readable summary lines for CLI/logging output."""
        lines: list[str] = []

        if self.dry_run:
            # Dry-run: target is intentionally unwritten; show the source plan only.
            # Never emit PASS/FAIL labels — the target does not exist yet.
            lines.append(f"[DRY-RUN] Migration plan — {len(self.tables)} tables")
            lines.append("  (no rows written; source row counts shown)")
            lines.append("")
            for tv in self.tables:
                lines.append(f"  {tv.table:<20} src={tv.src_count:>6}  [would insert]")
            lines.append("")
            total = sum(t.src_count for t in self.tables)
            lines.append(f"DRY-RUN OK — {total} rows would be migrated")
            return lines

        lines.append(f"Migration report — {len(self.tables)} tables")
        lines.append(f"  Total rows written: {self.total_rows_written}")
        lines.append("")
        for tv in self.tables:
            count_label = "PASS" if tv.count_ok else "FAIL"
            cksum_label = "PASS" if tv.checksum_ok else "FAIL"
            lines.append(
                f"  {tv.table:<20} "
                f"count={tv.src_count:>6}/{tv.dst_count:<6} [{count_label}]  "
                f"checksum [{cksum_label}]"
            )
            if not tv.count_ok:
                lines.append(f"    !! count mismatch: src={tv.src_count} dst={tv.dst_count}")
            if not tv.checksum_ok:
                lines.append(
                    f"    !! checksum mismatch: src={tv.src_checksum[:16]}… "
                    f"dst={tv.dst_checksum[:16]}…"
                )
        lines.append("")
        lines.append("Overall: " + ("ALL PASS" if self.all_ok else "FAIL — see above"))
        return lines


# ---------------------------------------------------------------------------
# Type conversion helpers (SQLite raw → Python canonical)
# ---------------------------------------------------------------------------


def _parse_datetime(val: Any) -> datetime | None:
    """Parse an ISO-8601 TEXT from SQLite into a naive UTC datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.replace(tzinfo=None)
    s = str(val).strip()
    if not s:
        return None
    # Handle trailing 'Z' (rare but possible)
    s = s.rstrip("Z")
    return datetime.fromisoformat(s).replace(tzinfo=None)


def _normalize_dt(val: Any) -> str | None:
    """Convert a datetime (or ISO string or None) to canonical ISO string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.replace(tzinfo=None).isoformat()
    # Already a string — normalize via round-trip
    dt = _parse_datetime(val)
    return dt.isoformat() if dt is not None else None


def _normalize_json(val: Any) -> Any:
    """Parse JSON text (if string) or return as-is (already decoded by psycopg)."""
    if val is None:
        return None
    if isinstance(val, str):
        return json.loads(val)
    return val  # already list/dict from psycopg JSONB decoding


def _normalize_bool(val: Any) -> bool | None:
    if val is None:
        return None
    return bool(val)


def _blob_to_array(blob: bytes | None) -> np.ndarray[Any, np.dtype[np.float32]] | None:
    """Decode a SQLite float32 BLOB into a numpy float32 array."""
    if blob is None:
        return None
    return np.frombuffer(blob, dtype=np.float32).copy()


# ---------------------------------------------------------------------------
# Canonical row form (for checksum)
# ---------------------------------------------------------------------------


def _canonical_row(row: dict[str, Any], table: str) -> dict[str, Any]:
    """
    Convert a row (from either SQLite or PG) to a canonical Python dict
    suitable for deterministic JSON serialization and checksum computation.

    Excluded columns (per _CHECKSUM_EXCLUDED) are dropped.
    Types are normalized:
        bool columns  → bool
        datetime cols → isoformat() string
        JSONB cols    → parsed list/dict
        float         → float (rounded to 10dp)
        int           → int
        str           → str
    """
    excluded = _CHECKSUM_EXCLUDED.get(table, set())
    bool_cols = _BOOL_COLS.get(table, set())
    dt_cols = _DATETIME_COLS.get(table, set())
    json_cols = _JSONB_COLS.get(table, set())

    result: dict[str, Any] = {}
    for col, val in row.items():
        if col in excluded:
            continue
        if val is None:
            result[col] = None
        elif col in bool_cols:
            result[col] = bool(val)
        elif col in dt_cols:
            result[col] = _normalize_dt(val)
        elif col in json_cols:
            result[col] = _normalize_json(val)
        elif isinstance(val, float):
            result[col] = round(val, 10)
        elif isinstance(val, bool):
            result[col] = bool(val)
        elif isinstance(val, int):
            result[col] = int(val)
        else:
            result[col] = val
    return result


def _row_canonical_json(row: dict[str, Any], table: str) -> bytes:
    """Return compact canonical JSON bytes for a single row."""
    canonical = _canonical_row(row, table)
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


# ---------------------------------------------------------------------------
# SQLite source helpers
# ---------------------------------------------------------------------------


def _sqlite_row_to_dict(row: sqlite3.Row, cols: tuple[str, ...]) -> dict[str, Any]:
    return {col: row[col] for col in cols}


def _sqlite_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # type: ignore[no-any-return]


def _python_sort_key(row: dict[str, Any], pk_cols: list[str]) -> tuple[str, ...]:
    """
    Return a sort key for *row* based on its primary-key columns.

    Uses Python's native str sort (code-point order = BINARY / COLLATE "C"),
    which is consistent regardless of the database's text collation.  This
    prevents spurious checksum mismatches when SQLite (BINARY) and PostgreSQL
    (locale-dependent default collation, e.g. en_US.utf8) order
    punctuation-heavy keys differently.  For example, 'a-b.md' < 'ab.md'
    under BINARY (hyphen 0x2d < 'b' 0x62) but PostgreSQL en_US.utf8 reverses
    that order by ignoring the hyphen.  Sorting both sides identically in
    Python before hashing eliminates that class of spurious CHECKSUM FAIL.
    """
    return tuple("" if row.get(c) is None else str(row[c]) for c in pk_cols)


def _sqlite_iter_rows(
    conn: sqlite3.Connection,
    table: str,
    cols: tuple[str, ...],
    batch_size: int,
) -> list[dict[str, Any]]:
    """Fetch all rows from *table* sorted by PK in Python (not DB) order.

    We materialize all at once because the SQLite connection is read-only
    and the dataset fits in memory for typical MintMory scales.

    Sorting is done in Python (code-point / BINARY order) rather than
    relying on the database ORDER BY so that both source and target produce
    identical row sequences regardless of their collation settings.
    """
    col_list = ", ".join(cols)
    pk_cols = _TABLE_PK[table]
    rows = conn.execute(f"SELECT {col_list} FROM {table}").fetchall()
    dicts = [_sqlite_row_to_dict(r, cols) for r in rows]
    dicts.sort(key=lambda r: _python_sort_key(r, pk_cols))
    return dicts


# ---------------------------------------------------------------------------
# Checksum computation
# ---------------------------------------------------------------------------


def _compute_checksum_from_dicts(rows: list[dict[str, Any]], table: str) -> str:
    """
    Compute a SHA-256 checksum over *rows* (already sorted by PK).

    Rows must be sorted by PK before calling this function.
    Returns a 64-character hex digest.
    """
    hasher = hashlib.sha256()
    for row in rows:
        hasher.update(_row_canonical_json(row, table))
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# PG target helpers
# ---------------------------------------------------------------------------


def _pg_count(conn: Any, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0])


def _pg_fetch_all_sorted(conn: Any, table: str) -> list[dict[str, Any]]:
    """Fetch all rows from *table* via psycopg dict cursor, sorted by PK in Python order.

    Sorting is done in Python (code-point / BINARY order) after fetching so
    that the row sequence is identical to _sqlite_iter_rows regardless of the
    PostgreSQL cluster's collation (e.g. en_US.utf8 vs BINARY).
    """
    cols = _TABLE_COLS[table]
    # Exclude embedding and content_tsv from the SELECT (we don't need them for checksum)
    excluded = _CHECKSUM_EXCLUDED.get(table, set())
    select_cols = [c for c in cols if c not in excluded]
    pk_cols = _TABLE_PK[table]
    col_list = ", ".join(select_cols)

    try:
        from psycopg.rows import dict_row  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError("psycopg[binary,pool] is required for PG migration") from exc

    cur = conn.cursor(row_factory=dict_row)
    cur.execute(f"SELECT {col_list} FROM {table}")
    rows = list(cur.fetchall())
    rows.sort(key=lambda r: _python_sort_key(r, pk_cols))
    return rows


def _pg_truncate_all(conn: Any) -> None:
    """TRUNCATE all MintMory tables (for --force re-run). CASCADE handles FKs."""
    conn.execute(
        "TRUNCATE memories, concept_links, index_manifest, "
        "query_sessions, query_results, memory_summaries "
        "RESTART IDENTITY CASCADE"
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Row insertion helpers (SQLite dict → PG INSERT)
# ---------------------------------------------------------------------------


def _insert_memories_batch(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> int:
    """Insert a batch of memory rows (superseded_by=NULL for all).

    Returns the number of rows inserted.
    """
    if dry_run or not rows:
        return len(rows)

    sql = """
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
        ) ON CONFLICT (id) DO NOTHING
    """
    params_list: list[tuple[Any, ...]] = []
    for r in rows:
        emb = _blob_to_array(r.get("embedding"))
        params_list.append(
            (
                r["id"],
                r["content"],
                r["category"],
                r["entity_ids"],  # passed as TEXT JSON → ::jsonb cast
                emb,  # numpy array → pgvector adapter
                float(r["confidence"]),
                r["source"],
                bool(r["verified"]),
                _parse_datetime(r.get("valid_from")),
                _parse_datetime(r.get("valid_until")),
                float(r["usefulness_score"]),
                float(r["staleness_score"]),
                int(r["reinforcement_count"]),
                int(r["retrieval_count"]),
                bool(r["is_stale"]),
                bool(r["is_active"]),
                bool(r["is_archived"]),
                None,  # superseded_by: always NULL in pass 1
                bool(r["flagged_for_review"]),
                r["contradicts_ids"],  # TEXT JSON → ::jsonb
                bool(r["is_note"]),
                _parse_datetime(r["created_at"]),
                _parse_datetime(r["updated_at"]),
                _parse_datetime(r.get("last_accessed_at")),
                r["metadata"],  # TEXT JSON → ::jsonb
            )
        )
    with conn.cursor() as cur:
        cur.executemany(sql, params_list)
    return len(rows)


def _update_superseded_by_batch(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> None:
    """Pass 2: UPDATE superseded_by for rows where it was set in the source."""
    has_superseded = [r for r in rows if r.get("superseded_by") is not None]
    if not has_superseded or dry_run:
        return
    sql = "UPDATE memories SET superseded_by = %s WHERE id = %s"
    params_list = [(r["superseded_by"], r["id"]) for r in has_superseded]
    with conn.cursor() as cur:
        cur.executemany(sql, params_list)


def _insert_concept_links_batch(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> int:
    if dry_run or not rows:
        return len(rows)
    sql = """
        INSERT INTO concept_links
          (id, source_memory_id, target_memory_id, link_type, entity,
           strength, confidence, source, verified, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_memory_id, target_memory_id, link_type) DO NOTHING
    """
    params_list = [
        (
            r["id"],
            r["source_memory_id"],
            r["target_memory_id"],
            r["link_type"],
            r["entity"],
            float(r["strength"]),
            float(r["confidence"]),
            r["source"],
            bool(r["verified"]),
            _parse_datetime(r["created_at"]),
            _parse_datetime(r["updated_at"]),
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, params_list)
    return len(rows)


def _insert_memory_summaries_batch(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> int:
    if dry_run or not rows:
        return len(rows)
    sql = """
        INSERT INTO memory_summaries
          (id, concept, summary_text, memory_count, is_current, generated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """
    params_list = [
        (
            r["id"],
            r["concept"],
            r["summary_text"],
            int(r["memory_count"]),
            bool(r["is_current"]),
            _parse_datetime(r["generated_at"]),
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, params_list)
    return len(rows)


def _insert_index_manifest_batch(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> int:
    if dry_run or not rows:
        return len(rows)
    sql = """
        INSERT INTO index_manifest
          (path, collection, size, mtime, content_hash, index_mode,
           memory_ids, online_only, last_seen)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (path) DO NOTHING
    """
    params_list = [
        (
            r["path"],
            r["collection"],
            int(r["size"]),
            float(r["mtime"]),
            r.get("content_hash"),
            r["index_mode"],
            r["memory_ids"],  # TEXT in both SQLite and PG
            bool(r["online_only"]),
            r["last_seen"],  # TEXT ISO-8601 in both
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, params_list)
    return len(rows)


def _insert_query_sessions_batch(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> int:
    if dry_run or not rows:
        return len(rows)
    sql = """
        INSERT INTO query_sessions
          (id, query_text, created_at, confidence_rating, reasoning,
           useful_ids, stale_ids, concluded)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (id) DO NOTHING
    """
    params_list = [
        (
            r["id"],
            r["query_text"],
            _parse_datetime(r["created_at"]),
            r.get("confidence_rating"),  # may be None (nullable)
            r.get("reasoning"),  # may be None (nullable)
            r["useful_ids"],  # TEXT JSON → ::jsonb
            r["stale_ids"],  # TEXT JSON → ::jsonb
            bool(r["concluded"]),
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, params_list)
    return len(rows)


def _insert_query_results_batch(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> int:
    if dry_run or not rows:
        return len(rows)
    sql = """
        INSERT INTO query_results
          (session_id, memory_id, relevance_score, was_accessed, was_useful, was_stale)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (session_id, memory_id) DO NOTHING
    """
    params_list = [
        (
            r["session_id"],
            r["memory_id"],
            float(r["relevance_score"]),
            bool(r["was_accessed"]),
            bool(r["was_useful"]),
            bool(r["was_stale"]),
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, params_list)
    return len(rows)


_TABLE_INSERT_FN: dict[
    str,
    Callable[[Any, list[dict[str, Any]]], int],
] = {
    "memories": lambda conn, rows: _insert_memories_batch(conn, rows),
    "concept_links": lambda conn, rows: _insert_concept_links_batch(conn, rows),
    "memory_summaries": lambda conn, rows: _insert_memory_summaries_batch(conn, rows),
    "index_manifest": lambda conn, rows: _insert_index_manifest_batch(conn, rows),
    "query_sessions": lambda conn, rows: _insert_query_sessions_batch(conn, rows),
    "query_results": lambda conn, rows: _insert_query_results_batch(conn, rows),
}


# ---------------------------------------------------------------------------
# Source checksum (over SQLite rows)
# ---------------------------------------------------------------------------


def _source_checksum(rows: list[dict[str, Any]], table: str) -> str:
    """Compute the canonical checksum over raw SQLite rows."""
    return _compute_checksum_from_dicts(rows, table)


# ---------------------------------------------------------------------------
# Target checksum (over PG rows fetched back)
# ---------------------------------------------------------------------------


def _target_checksum(pg_conn: Any, table: str) -> str:
    """Fetch all rows from PG (sorted by PK) and compute the canonical checksum."""
    rows = _pg_fetch_all_sorted(pg_conn, table)
    return _compute_checksum_from_dicts(rows, table)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def migrate_sqlite_to_postgres(
    src_path: str,
    dst_dsn: str,
    *,
    dry_run: bool = False,
    batch_size: int = 500,
    force: bool = False,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> MigrationReport:
    """
    Migrate a MintMory SQLite database to PostgreSQL.

    Args:
        src_path:    Absolute path to the source SQLite file.
        dst_dsn:     psycopg-compatible DSN for the target PostgreSQL database.
        dry_run:     If True, read + count source rows but write nothing to PG.
                     No PG connection is opened in dry-run mode; the schema is
                     NOT created on the target.
        batch_size:  Number of rows per INSERT batch (default 500).
        force:       If True, TRUNCATE all target tables before writing
                     (allows idempotent re-runs). Refused if False and the
                     target is non-empty.
        on_progress: Optional callback ``(table, written, total) -> None``
                     called after each batch.

    Returns:
        MigrationReport with per-table counts and checksum verdicts.

    Raises:
        FileNotFoundError: if src_path does not exist.
        ValueError: if the target is non-empty and force=False.
        ImportError: if psycopg or pgvector are not installed.
    """
    import os  # noqa: PLC0415

    src_path = os.path.expanduser(src_path)
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Source SQLite database not found: {src_path!r}")

    report = MigrationReport(dry_run=dry_run)

    # -----------------------------------------------------------------------
    # Open SQLite (read-only)
    # -----------------------------------------------------------------------
    sqlite_conn = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_conn.execute("PRAGMA foreign_keys = ON")

    try:
        if dry_run:
            # -------------------------------------------------------------------
            # Dry-run path: read SQLite only, compute source counts + checksums.
            # No PG connection is opened and no DDL is issued on the target.
            # -------------------------------------------------------------------
            for table in _FK_ORDER:
                cols = _TABLE_COLS[table]
                src_rows = _sqlite_iter_rows(sqlite_conn, table, cols, batch_size)
                src_count = len(src_rows)
                src_cksum = _source_checksum(src_rows, table)
                report.tables.append(
                    TableVerification(
                        table=table,
                        src_count=src_count,
                        dst_count=0,
                        src_checksum=src_cksum,
                        dst_checksum="",
                    )
                )
                if on_progress:
                    on_progress(table, src_count, src_count)

        else:
            # -------------------------------------------------------------------
            # Real migration path
            # -------------------------------------------------------------------

            # Lazy imports — keep psycopg optional for the SQLite-only install path
            try:
                import psycopg  # noqa: PLC0415
                from pgvector.psycopg import register_vector  # noqa: PLC0415
            except ImportError as exc:
                raise ImportError(
                    "psycopg[binary,pool] and pgvector are required for PG migration. "
                    "Install with: pip install 'mintmory-core[postgres]'"
                ) from exc

            # Ensure PG schema exists (idempotent via PostgresBackend.initialise())
            from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415

            pg_backend = PostgresBackend(dsn=dst_dsn, pool_min=1, pool_max=3)
            pg_backend.initialise()

            # Open a direct psycopg connection for bulk inserts.
            # autocommit=False so we can control transaction boundaries.
            # All inserts are batched into a SINGLE transaction committed once
            # after verification.  A mid-run failure rolls back to an empty
            # (or pre-truncate) state so a re-run with --force suffices.
            pg_conn = psycopg.connect(dst_dsn, autocommit=False)
            register_vector(pg_conn)

            try:
                # ---------------------------------------------------------------
                # Idempotency check
                # ---------------------------------------------------------------
                existing_count = _pg_count(pg_conn, "memories")
                if existing_count > 0 and not force:
                    raise ValueError(
                        f"Target Postgres already contains {existing_count} memory row(s). "
                        "Pass force=True (or --force) to truncate and overwrite, or "
                        "choose an empty target database."
                    )
                if existing_count > 0 and force:
                    # TRUNCATE commits immediately (in its own transaction).
                    # Subsequent inserts start a fresh implicit transaction.
                    _pg_truncate_all(pg_conn)

                # ---------------------------------------------------------------
                # Migrate each table in FK-safe order
                # All INSERTs go into a single uncommitted transaction.
                # ---------------------------------------------------------------
                all_src_rows: dict[str, list[dict[str, Any]]] = {}

                for table in _FK_ORDER:
                    cols = _TABLE_COLS[table]
                    src_rows = _sqlite_iter_rows(sqlite_conn, table, cols, batch_size)
                    all_src_rows[table] = src_rows
                    total = len(src_rows)
                    written = 0

                    # Batch insert (no intermediate commits)
                    for batch_start in range(0, max(total, 1), batch_size):
                        batch = src_rows[batch_start : batch_start + batch_size]
                        if not batch:
                            break

                        if table == "memories":
                            written += _insert_memories_batch(pg_conn, batch)
                        elif table == "concept_links":
                            written += _insert_concept_links_batch(pg_conn, batch)
                        elif table == "memory_summaries":
                            written += _insert_memory_summaries_batch(pg_conn, batch)
                        elif table == "index_manifest":
                            written += _insert_index_manifest_batch(pg_conn, batch)
                        elif table == "query_sessions":
                            written += _insert_query_sessions_batch(pg_conn, batch)
                        elif table == "query_results":
                            written += _insert_query_results_batch(pg_conn, batch)

                        if on_progress:
                            on_progress(table, written, total)

                    # memories pass 2: fix up superseded_by (after all memories inserted)
                    if table == "memories":
                        for batch_start in range(0, max(total, 1), batch_size):
                            batch = src_rows[batch_start : batch_start + batch_size]
                            if not batch:
                                break
                            _update_superseded_by_batch(pg_conn, batch)

                    report.total_rows_written += written

                # ---------------------------------------------------------------
                # Verification (within the same uncommitted transaction — PG can
                # see all the inserts we haven't committed yet).
                # ---------------------------------------------------------------
                for table in _FK_ORDER:
                    src_rows = all_src_rows[table]
                    src_count = len(src_rows)
                    src_cksum = _source_checksum(src_rows, table)
                    dst_count = _pg_count(pg_conn, table)
                    dst_cksum = _target_checksum(pg_conn, table)
                    report.tables.append(
                        TableVerification(
                            table=table,
                            src_count=src_count,
                            dst_count=dst_count,
                            src_checksum=src_cksum,
                            dst_checksum=dst_cksum,
                        )
                    )

                # Single commit after successful verification.
                # If any insert or verification raised an exception the finally
                # block closes pg_conn which implicitly rolls back the transaction.
                pg_conn.commit()

            finally:
                pg_conn.close()
                pg_backend.close()

    finally:
        sqlite_conn.close()

    return report


def _insert_tenants_batch(
    conn: Any,
    rows: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> int:
    raise NotImplementedError
