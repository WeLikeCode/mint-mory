"""
Storage port for MintMory — backend-agnostic Protocol and shared data types.

``StorageBackend`` is a ``@runtime_checkable`` structural Protocol covering every
domain method the REST API, MCP server, and CLI need from a storage backend.

Deliberately excluded from the Protocol (SQLite-only, stay on ``SqliteBackend``):
  - ``connect()`` — returns a raw ``sqlite3.Connection``

``transaction()`` IS on the Protocol: callers (the cross-tenant copy) must be
able to compose many public writes into one atomic unit on any backend, but they
MUST NOT use the yielded value — it is backend-specific (a raw
``sqlite3.Connection`` on SQLite). The history DB, cochange module, and the
``history scrub`` CLI sub-command keep working unchanged; they are explicitly
typed to ``SqliteBackend`` and documented as SQLite-by-design.

``ManifestEntry`` replaces the ``sqlite3.Row`` that ``manifest_get`` used to return.
It is a ``TypedDict`` so callers can keep ``row["key"]`` access unchanged while mypy
can verify every field access.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from typing_extensions import TypedDict

if TYPE_CHECKING:
    import numpy as np
    from mintmory.core.embedder import EmbedderProtocol
    from mintmory.core.types import (
        ConceptLink,
        ConceptLinkType,
        MemoryRecord,
        MemoryStats,
        MemorySummary,
        QueryResult,
        QuerySession,
        SearchAroundSpec,
        SearchRequest,
        SearchResponse,
        Tenant,
    )


# ---------------------------------------------------------------------------
# ManifestEntry — replaces sqlite3.Row in manifest_get's return type
# ---------------------------------------------------------------------------


class ManifestEntry(TypedDict):
    """Typed view of an ``index_manifest`` row. Mapping-compatible (key access works)."""

    path: str
    collection: str
    size: int
    mtime: float
    content_hash: str | None
    index_mode: str
    memory_ids: str  # JSON-encoded list[str]
    online_only: int  # INTEGER bool (0 or 1)
    last_seen: str  # ISO-8601 timestamp
    tenant_id: str


# ---------------------------------------------------------------------------
# StorageBackend Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class StorageBackend(Protocol):
    """
    Structural protocol for MintMory persistence backends.

    Satisfied structurally (no inheritance required) by ``SqliteBackend`` and,
    in future phases, by ``PostgresBackend``.  Mocks only need to implement the
    methods they exercise — ``isinstance(obj, StorageBackend)`` checks method
    presence only (``@runtime_checkable``), not signatures.
    """

    # ------------------------------------------------------------------
    # Attributes (structural — implementations must carry these)
    # ------------------------------------------------------------------
    embedder: EmbedderProtocol | None  # may be None for API/MCP (no-embedder asymmetry)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialise(self) -> None:
        """Create all tables / indexes / FTS triggers. Idempotent."""
        ...

    def close(self) -> None:
        """Release the underlying connection / pool."""
        ...

    def ping(self) -> bool:
        """Cheap reachability check — SELECT 1. Returns True on success, never raises."""
        ...

    def transaction(self) -> AbstractContextManager[object]:
        """Compose the calls made inside the block into one atomic unit.

        The outermost entry commits on a clean exit and rolls back + re-raises
        on an exception; a nested entry joins the outer block. Protocol callers
        MUST NOT use the yielded value — it is backend-specific (on SQLite it is
        a raw ``sqlite3.Connection``).
        """
        ...

    # ------------------------------------------------------------------
    # MemoryRecord CRUD
    # ------------------------------------------------------------------

    def add_memory(
        self,
        record: MemoryRecord | None = None,
        **fields: Any,
    ) -> MemoryRecord:
        """Insert a new memory and return the stored record."""
        ...

    def get_memory(self, memory_id: str, tenant_id: str | None = None) -> MemoryRecord | None:
        """Fetch a single memory by ID. Returns None if not found."""
        ...

    def update_memory(self, memory_id: str, **fields: object) -> MemoryRecord:
        """Partial update — only provided fields are changed."""
        ...

    def archive_memory(self, memory_id: str, tenant_id: str | None = None) -> None:
        """Soft delete: set is_archived=1, is_active=0."""
        ...

    def supersede_memory(self, memory_id: str, by_id: str, tenant_id: str | None = None) -> None:
        """Mark memory_id superseded by by_id."""
        ...

    # ------------------------------------------------------------------
    # Index manifest
    # ------------------------------------------------------------------

    def manifest_get(self, path: str, *, tenant_id: str = "global") -> ManifestEntry | None:
        """Return the manifest row for ``(tenant_id, path)``, or None."""
        ...

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
        ...

    def manifest_paths(self, collection: str, *, tenant_id: str = "global") -> set[str]:
        """All paths currently tracked under ``collection`` for ``tenant_id``."""
        ...

    def manifest_delete(self, path: str, *, tenant_id: str = "global") -> None:
        """Drop the ``(tenant_id, path)`` manifest row."""
        ...

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def apply_feedback(
        self, memory_id: str, useful: bool, stale: bool, tenant_id: str | None = None
    ) -> None:
        """Per-memory feedback primitive."""
        ...

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        request: SearchRequest,
        query_embedding: np.ndarray | None = None,
    ) -> SearchResponse:
        """Hybrid search pipeline: FTS5 + vector + RRF."""
        ...

    def search_around(
        self,
        anchor_ids: list[str],
        spec: SearchAroundSpec,
    ) -> list[str]:
        """Graph traversal from anchor_ids via concept_links."""
        ...

    def get_annotating_notes(
        self, memory_id: str, cap: int, tenant_id: str | None = None
    ) -> list[MemoryRecord]:
        """Return up to cap notes that ANNOTATE memory_id."""
        ...

    def get_annotating_descriptions(
        self, memory_id: str, cap: int, tenant_id: str | None = None
    ) -> list[MemoryRecord]:
        """Return up to cap active image_description memories ANNOTATING memory_id."""
        ...

    def find_image_file_record(
        self, path_or_rel: str, tenant_id: str | None = None
    ) -> MemoryRecord | None:
        """Find the most recent ACTIVE file-record matching path_or_rel."""
        ...

    def anchor_candidates(self, about: str, limit: int = 5) -> list[tuple[float, MemoryRecord]]:
        """Side-effect-free candidate lookup for note anchoring.

        Returns (normalised_score, record) pairs sorted best-first.
        Does NOT create a QuerySession, does NOT record query_results, does NOT
        bump retrieval counters.
        """
        ...

    def list_image_file_records(self, tenant_id: str | None = None) -> list[MemoryRecord]:
        """Return all active, non-archived memories with 'ext' metadata but no 'kind' tag.

        Verbatim SQL:
            SELECT * FROM memories WHERE is_archived = 0
            AND json_extract(metadata, '$.kind') IS NULL
            AND json_extract(metadata, '$.ext') IS NOT NULL
            ORDER BY json_extract(metadata, '$.rel'), id
        """
        ...

    def vector_search_available(self) -> bool:
        """Return True iff an embedder is configured AND the vec extension loaded."""
        ...

    def memory_exists_with_content(self, content: str, tenant_id: str | None = None) -> bool:
        """Return True if any memory with the exact content already exists.

        Verbatim SQL: SELECT 1 FROM memories WHERE content = ? LIMIT 1
        Used by the ingest command for dedup checks.
        """
        ...

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
        """SQL backing for notes_list."""
        ...

    # ------------------------------------------------------------------
    # ConceptLink
    # ------------------------------------------------------------------

    def add_link(self, link: ConceptLink) -> ConceptLink:
        """INSERT OR IGNORE on UNIQUE (source, target, link_type)."""
        ...

    def get_links(
        self,
        memory_id: str,
        link_type: ConceptLinkType | None = None,
        tenant_id: str | None = None,
    ) -> list[ConceptLink]:
        """Return all links where memory_id is source OR target."""
        ...

    # ------------------------------------------------------------------
    # QuerySession
    # ------------------------------------------------------------------

    def create_session(self, session: QuerySession) -> QuerySession:
        """Persist a new QuerySession and return it."""
        ...

    def get_session(self, session_id: str, tenant_id: str | None = None) -> QuerySession | None:
        """Fetch a session by ID. Returns None if not found."""
        ...

    def record_query_results(self, results: list[QueryResult]) -> None:
        """Persist query_results rows."""
        ...

    def update_session_feedback(
        self,
        session_id: str,
        confidence_rating: int | None,
        reasoning: str | None,
        useful_ids: list[str],
        stale_ids: list[str],
    ) -> None:
        """Update query_sessions + query_results in one transaction.

        Verbatim SQL (preserving Phase-0 transaction boundary):
            UPDATE query_sessions SET confidence_rating=?, reasoning=?,
                useful_ids=?, stale_ids=?, concluded=1 WHERE id=?
            UPDATE query_results SET was_useful=?, was_stale=?
                WHERE session_id=? AND memory_id=?   (one row per affected memory)
        """
        ...

    def mark_session_concluded(self, session_id: str) -> None:
        """Mark a session concluded with no feedback (idempotent, no-feedback path).

        Verbatim SQL: UPDATE query_sessions SET concluded = 1 WHERE id = ?
        """
        ...

    # ------------------------------------------------------------------
    # MemorySummary
    # ------------------------------------------------------------------

    def upsert_summary(self, summary: MemorySummary) -> MemorySummary:
        """INSERT OR REPLACE keyed on the UNIQUE concept column."""
        ...

    def get_summary(self, concept: str, tenant_id: str = "global") -> MemorySummary | None:
        """Fetch a summary by ``(tenant_id, concept)``. Returns None if not found."""
        ...

    def list_summaries(self, tenant_id: str | None = None) -> list[MemorySummary]:
        """Return all summaries ordered by concept."""
        ...

    # ------------------------------------------------------------------
    # Tenant directory
    # ------------------------------------------------------------------

    def create_tenant(self, tenant_id: str, name: str = "") -> Tenant:
        """Create a tenant idempotently; an existing id is returned unchanged."""
        ...

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Return the tenant row, or None for an unknown/invalid id."""
        ...

    def list_tenants(self) -> list[Tenant]:
        """Every tenant (active and inactive), ordered by id ascending."""
        ...

    def set_tenant_active(self, tenant_id: str, active: bool) -> Tenant:
        """Activate/deactivate a tenant; ``global`` cannot be deactivated."""
        ...

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self, tenant_id: str | None = None) -> MemoryStats:
        """Return aggregate statistics."""
        ...

    # ------------------------------------------------------------------
    # Dreaming helpers (absorbed from dreaming.py's raw connect() sites)
    # ------------------------------------------------------------------

    def get_flagged_memories(self) -> list[MemoryRecord]:
        """Return all memories where flagged_for_review = 1."""
        ...

    def get_never_accessed_stale(
        self, days_old: int = 7, min_staleness: float = 3.0
    ) -> list[MemoryRecord]:
        """Anomaly detection: never retrieved + staleness_score >= min_staleness."""
        ...

    def get_high_staleness_useful(
        self, min_staleness: float = 5.0, min_usefulness: float = 3.0
    ) -> list[MemoryRecord]:
        """Anomaly detection: stale but still useful."""
        ...

    def get_anomaly_high_staleness_useful_ids(
        self, min_staleness: float, min_usefulness: float
    ) -> list[str]:
        """IDs of high-staleness + still-useful memories (anomaly step 1a).

        Verbatim SQL:
            SELECT id FROM memories
            WHERE staleness_score >= ? AND usefulness_score >= ?
            AND is_archived = 0 AND is_note = 0
            ORDER BY id
        """
        ...

    def get_anomaly_never_accessed_ids(self, cutoff_iso: str) -> list[str]:
        """IDs of never-retrieved memories created before cutoff (anomaly step 1b).

        Verbatim SQL:
            SELECT id FROM memories
            WHERE retrieval_count = 0 AND created_at < ?
            AND is_active = 1 AND is_archived = 0 AND is_note = 0
            ORDER BY id
        """
        ...

    def get_anomaly_flagged_ids(self) -> list[str]:
        """IDs of flagged_for_review memories (anomaly step 1c).

        Verbatim SQL:
            SELECT id FROM memories WHERE flagged_for_review = 1 ORDER BY id
        """
        ...

    def list_active_memory_ids(self, *, ordered: bool = False) -> list[str]:
        """IDs of all active, non-archived memories.

        Verbatim SQL (ordered=False):
            SELECT id FROM memories WHERE is_active = 1 AND is_archived = 0
        With ordered=True appends: ORDER BY id
        """
        ...

    def get_stale_archivable_ids(self, min_staleness: float, cutoff_iso: str) -> list[str]:
        """IDs of memories eligible for staleness archival (dreaming step 5).

        Verbatim SQL:
            SELECT id FROM memories
            WHERE is_stale = 1 AND staleness_score >= ? AND is_archived = 0
            AND is_note = 0
            AND (last_accessed_at IS NULL OR last_accessed_at < ?)
            ORDER BY id
        """
        ...

    def get_rehabilitable_rows(self, cutoff_iso: str) -> list[tuple[str, float]]:
        """(id, staleness_score) pairs eligible for rehabilitation (dreaming step 6).

        Verbatim SQL:
            SELECT id, staleness_score FROM memories
            WHERE is_stale = 1 AND usefulness_score > staleness_score
            AND is_archived = 0
            AND last_accessed_at IS NOT NULL AND last_accessed_at >= ?
            ORDER BY id
        """
        ...

    def get_existing_relates_to_pairs(self) -> set[frozenset[str]]:
        """Return the set of existing RELATES_TO link pairs (order-insensitive).

        Used by create_concept_links() to pre-check which pairs exist so the
        new-link count is accurate even with INSERT OR IGNORE semantics.

        Verbatim SQL:
            SELECT source_memory_id, target_memory_id
            FROM concept_links WHERE link_type = ?
        """
        ...
