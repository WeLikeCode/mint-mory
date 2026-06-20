"""
MintMory Core Types — Palantir Ontology-Inspired Memory Schema

Design principles (from PALANTIR.md):
  - Object types → MemoryRecord (instances), ConceptLink (relationships), QuerySession (audit)
  - Link types → ConceptLinkType (12 typed, orthogonal relationship categories)
  - Properties → typed fields on each object (Pydantic-enforced)
  - Action types → exposed as MCP tools / API endpoints / CLI commands
  - Decision lineage → QuerySession captures who queried what, when, and what was useful

Source of truth for the HTTP API (openapi/mintmory.yaml) and SQLite schema
(schema.sql) — all three must stay in sync. schema.sql is generated from
these models; openapi.yaml references these models as JSON Schema.

Correction vs FEATURES.md draft (widemem audit finding):
  CONTRADICTION_DETECTION_PROMPT uses {has_conflict, conflicts[...]} not
  {is_contradiction, contradicts_memory_ids}. ConflictCheckResult reflects
  the actual widemem schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enumerations — Object Types and Link Types (Palantir Ontology terminology)
# ---------------------------------------------------------------------------


class MemoryCategory(str, Enum):
    """
    Object types in the memory ontology. Maps Palantir 'object type' concept
    to memory categories (from TYPED_SCHEMA.md, sourced from MoPA, AgentKB,
    Recall-and-Reflect, MemFree, Memento arxiv papers).
    """

    IDENTITY = "identity"  # Persistent facts about the user/agent
    PREFERENCE = "preference"  # Stated or inferred preferences
    SKILL = "skill"  # How to do something; procedures, tools, recipes
    CONTEXT = "context"  # Current working context, active project state
    FACT = "fact"  # World-state facts, configuration values, URLs
    EPISODIC = "episodic"  # Something that happened in a specific session
    TEMPORAL = "temporal"  # Time-bounded fact with explicit validity window
    RELATIONSHIP = "relationship"  # A typed link between two entities (stored as ConceptLink)


class ConceptLinkType(str, Enum):
    """
    Link types in the memory ontology — 12 orthogonal, non-hierarchical types.
    Maps Palantir 'link type' concept to typed memory relationships.

    Sourced from TYPED_SCHEMA.md which synthesises:
      KGFoller (2310.13589), AgentKB (2312.06066), Recall-and-Reflect (2311.03363),
      StructGPT (2305.09857), Memento (2310.08721), MemFree (2401.00089).

    Each type has a defined inverse (noted in comments).
    """

    RELATES_TO = "relates_to"  # General connection, no specific direction (symmetric)
    CONTRADICTS = "contradicts"  # Cannot both be true (symmetric)
    REFINES = "refines"  # B adds specificity to A; inverse: generalizes
    SUPERSEDES = "supersedes"  # B replaces A completely; inverse: precedes
    ENABLES = "enables"  # A made B possible; inverse: enabled_by
    DEPENDS_ON = "depends_on"  # A requires B; inverse: supports
    SIMILAR_TO = "similar_to"  # A is like B (symmetric)
    PART_OF = "part_of"  # A is contained in B; inverse: contains
    USES = "uses"  # A actively uses B; inverse: used_by
    BEFORE = "before"  # A occurred before B (temporal); inverse: after
    VALID_UNTIL = "valid_until"  # A is true until time T (encoded in target metadata)
    ANNOTATES = "annotates"  # A (a note) annotates B (the item it is about); inverse: annotated_by


SYMMETRIC_LINK_TYPES: frozenset[ConceptLinkType] = frozenset(
    {
        ConceptLinkType.RELATES_TO,
        ConceptLinkType.CONTRADICTS,
        ConceptLinkType.SIMILAR_TO,
    }
)


class LinkSource(str, Enum):
    EXTRACTION = "extraction"  # Detected during entity extraction
    INFERENCE = "inference"  # Inferred by LLM during add
    DREAMING = "dreaming"  # Created during dreaming consolidation
    USER = "user"  # Explicitly provided by user


class MemorySource(str, Enum):
    USER = "user"
    AGENT = "agent"
    DOCUMENT = "document"
    INFERENCE = "inference"


class DreamIntensity(str, Enum):
    LIGHT = "light"  # anomaly detection + concept linking + summary updates
    FULL = "full"  # light + contradiction resolution + archival + rehabilitation


# ---------------------------------------------------------------------------
# Core Object Types
# ---------------------------------------------------------------------------


class MemoryRecord(BaseModel):
    """
    Primary memory object. Palantir 'Object instance' equivalent.

    ID format: ULID (sortable, collision-resistant, base32).
    All timestamps stored as ISO-8601 UTC strings in SQLite; parsed as datetime here.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str = Field(..., min_length=1, max_length=10_000)
    category: MemoryCategory
    entity_ids: list[str] = Field(default_factory=list)  # regex-extracted entities

    # Palantir 'Property' fields — confidence and provenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: MemorySource = MemorySource.AGENT
    verified: bool = False
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    # Session feedback scores (updated by QuerySession → QueryFeedback cycle)
    # These implement the 7-factor importance model from arxiv 2606.12945
    usefulness_score: float = Field(default=0.0, ge=0.0, le=10.0)
    staleness_score: float = Field(default=0.0, ge=0.0, le=10.0)
    reinforcement_count: int = Field(default=0, ge=0)
    retrieval_count: int = Field(default=0, ge=0)

    # State flags
    is_stale: bool = False
    is_active: bool = True
    is_archived: bool = False
    superseded_by: str | None = None  # ID of replacing memory
    flagged_for_review: bool = False  # contradiction detected at add time
    contradicts_ids: list[str] = Field(default_factory=list)
    is_note: bool = False  # user-authored "remember this" note (overlay flag)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed_at: datetime | None = None

    # Extensible metadata (e.g. project_id, session_id, custom tags)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("entity_ids", "contradicts_ids", mode="before")
    @classmethod
    def parse_json_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            import json

            return list(json.loads(v))
        return v or []

    def effective_score(
        self,
        base_relevance: float,
        usefulness_weight: float = 0.3,
        staleness_weight: float = 0.2,
        decay_rate: float = 0.01,
        now: datetime | None = None,
    ) -> float:
        """
        Composite retrieval rank. See FEATURES.md scoring section.
        effective_score = base_relevance
                        + usefulness_score * USEFULNESS_WEIGHT
                        - staleness_score * STALENESS_WEIGHT
                        + recency_bonus (exponential decay)
        """
        import math

        _now = now or datetime.utcnow()
        days_since_access = 0.0
        if self.last_accessed_at:
            days_since_access = (_now - self.last_accessed_at).total_seconds() / 86_400
        recency_bonus = 0.1 * math.exp(-decay_rate * days_since_access)

        return (
            base_relevance
            + self.usefulness_score * usefulness_weight
            - self.staleness_score * staleness_weight
            + recency_bonus
        )


class ConceptLink(BaseModel):
    """
    Typed edge between two MemoryRecord vertices.
    Palantir 'Link Type' equivalent — object-backed (the link itself carries metadata).

    The LNAD (Linked Node Attribute Data) graph is formed by:
      vertices = MemoryRecord instances
      edges    = ConceptLink instances
      joining  = MemoryConceptLink association (many-to-many when one link involves N memories)
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_memory_id: str
    target_memory_id: str
    link_type: ConceptLinkType
    entity: str = ""  # shared entity that triggered this link (may be empty for user-created links)

    # Palantir 'Object-backed link' metadata
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: LinkSource = LinkSource.DREAMING
    verified: bool = False

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MemorySummary(BaseModel):
    """
    LLM-generated synthesis of all memories sharing a concept/entity.
    Created during dreaming Step 3 (summary generation).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    concept: str  # the entity or concept name
    summary_text: str
    memory_count: int
    is_current: bool = True  # false if any linked memory became stale
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Query Session — Palantir 'Decision Lineage' equivalent
# ---------------------------------------------------------------------------


class QueryResult(BaseModel):
    """One retrieved memory within a QuerySession."""

    session_id: str
    memory_id: str
    relevance_score: float
    was_accessed: bool = False  # LLM used it in the answer
    was_useful: bool = False  # marked useful in QueryFeedback
    was_stale: bool = False  # marked stale in QueryFeedback


class QuerySession(BaseModel):
    """
    Audit record for every memory query. Implements 'Decision Lineage':
    who queried, what was retrieved, what was actually useful.

    The passive self-assessment (QueryFeedback) is produced automatically
    by the LLM after the session concludes — no user involvement required.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query_text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Post-session LLM assessment (set when feedback is recorded)
    confidence_rating: int | None = Field(default=None, ge=1, le=5)
    reasoning: str | None = None
    useful_ids: list[str] = Field(default_factory=list)
    stale_ids: list[str] = Field(default_factory=list)
    concluded: bool = False

    @field_validator("useful_ids", "stale_ids", mode="before")
    @classmethod
    def parse_json_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            import json

            return list(json.loads(v))
        return v or []


# ---------------------------------------------------------------------------
# Conflict detection — uses widemem's ACTUAL schema (NOT the research draft)
# RESEARCH.md had the wrong field names; this is the verified schema from
# widemem/retrieval/prompts.py:14-25 (confirmed by the OPUS audit).
# ---------------------------------------------------------------------------


class ConflictDetail(BaseModel):
    """One conflict detected between new fact and an existing memory."""

    new_fact: str
    existing_memory_id: str
    existing_content: str
    type: Literal["contradiction", "ambiguity"]
    question: str | None = None  # only for ambiguity


class ConflictCheckResult(BaseModel):
    """Output of CONTRADICTION_DETECTION_PROMPT (widemem verified schema)."""

    has_conflict: bool
    conflicts: list[ConflictDetail] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dreaming process types
# ---------------------------------------------------------------------------


class AnomalyReport(BaseModel):
    """Output of dreaming Step 1: anomaly detection."""

    high_staleness_useful: list[str] = Field(default_factory=list)  # memory IDs
    never_accessed: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)  # memory IDs flagged_for_review


class BatchResolutionAction(BaseModel):
    """One resolution action for a flagged memory (widemem BatchConflictResolver pattern)."""

    action: Literal["ADD", "UPDATE", "DELETE", "NONE"]
    target_id: str | None = None  # for UPDATE and DELETE
    reason: str = ""


class DreamReport(BaseModel):
    """Summary returned after a dreaming run."""

    intensity: DreamIntensity
    duration_ms: float
    new_links: int = 0
    new_summaries: int = 0
    contradictions_resolved: int = 0
    memories_archived: int = 0
    memories_rehabilitated: int = 0
    anomalies: AnomalyReport | None = None


class SummaryJob(BaseModel):
    """A single concept the active agent should summarise (agent-supplied L3).

    Produced by ``DreamingEngine.collect_summary_jobs`` and exposed over the
    transports. The agent writes ``summary_text`` itself (it IS an LLM) and sends
    it back via the apply path — MintMory calls no LLM for this flow.
    """

    concept: str  # the entity/concept name (matches MemorySummary.concept)
    memory_ids: list[str]  # contributing memory ids (scan order, capped to max_contents)
    contents: list[str]  # the memories' content, truncated/capped per summary settings
    memory_count: int  # active non-archived memory count for the concept (pre-cap)
    current_summary: str | None = None  # existing summary_text, if any, so the agent can refine


# ---------------------------------------------------------------------------
# Image understanding types (G5 — agent-supplied vision)
# ---------------------------------------------------------------------------


class ImageJob(BaseModel):
    """One indexed image the active agent should describe (agent-supplied vision).

    Produced by ``vision.image_jobs`` and exposed over the transports. Mirrors
    ``SummaryJob``: a pure data carrier (NOT persisted) describing one unit of
    work. ``image_b64`` is populated (hybrid bytes) only when the file is
    online-only OR ``include_bytes=True`` AND the file is within the size cap;
    otherwise it is ``None`` and the agent reads the file at ``path``.
    """

    file_id: str  # the image FILE-RECORD memory id (what the description ANNOTATES)
    path: str  # absolute source path (str), from the file-record metadata
    rel: str  # POSIX path relative to the walk root, from the file-record metadata
    mime: str  # best-effort MIME from the suffix, e.g. "image/png"
    size: int  # on-disk byte size, from the file-record metadata
    online_only: bool  # cloud placeholder (not downloaded locally)
    image_b64: str | None = None  # base64 payload (hybrid rule §5); None => use path
    current_description: str | None = None  # existing image_description text, if any
    oversized: bool = False  # True when image_b64 omitted because size > cap


class ImageDescription(BaseModel):
    """The stored description of one image (the result of ``image_caption_put``).

    Wraps the created/updated ``image_description`` MemoryRecord plus the linkage
    facts, mirroring ``NoteResult``'s shape (record + what-it-anchored-to).
    """

    record: MemoryRecord  # the image_description memory (category=context, is_note=False)
    file_id: str  # the image file-record this description ANNOTATES
    source_image: str  # the image's absolute path (== file-record metadata["path"])
    replaced_description_id: str | None = None  # prior description archived on re-put, if any


# ---------------------------------------------------------------------------
# Vision run types (automated llm captioner — add-llm-vision-provider)
# ---------------------------------------------------------------------------


class CaptionRunItem(BaseModel):
    """One image processed by a caption run (audit detail)."""

    file_id: str
    rel: str
    status: str  # "described" | "skipped" | "failed"
    note: str = ""  # description id / "oversized" / "budget" / the VisionError text


class CaptionRunReport(BaseModel):
    """Result of caption_pending_images / vision-run / POST /images/caption-run."""

    described: int = 0
    skipped: int = 0  # oversized or budget-exhausted
    failed: int = 0  # VisionError / unreadable
    budget_hit: bool = False
    provider: str = "llm"  # "agent" when no captioner was configured (no-op run)
    items: list[CaptionRunItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Embedding provider types (pluggable — local default, API as override)
# ---------------------------------------------------------------------------


class EmbeddingProvider(str, Enum):
    LOCAL = "local"  # sentence-transformers/all-MiniLM-L6-v2 (default)
    OPENAI = "openai"  # text-embedding-3-small
    ANTHROPIC = "anthropic"  # future


# ---------------------------------------------------------------------------
# Search / ObjectSet query types (Palantir ObjectSet API-inspired)
# ---------------------------------------------------------------------------


class SearchAroundSpec(BaseModel):
    """
    Graph traversal spec for search-around queries.
    Implements 'search in search OR scoped by relationships':
      Phase 1: find anchor memories matching the text query
      Phase 2: traverse concept_links from anchors using link_types filter
      Result: anchor memories UNION traversed memories (OR semantics)
    """

    link_types: list[ConceptLinkType] = Field(default_factory=list)  # empty = all types
    depth: int = Field(default=1, ge=1, le=3)  # graph traversal depth
    min_strength: float = Field(default=0.0, ge=0.0, le=1.0)


class MemoryFilter(BaseModel):
    """Structured filter applied after search. Palantir ObjectSet filter equivalent."""

    category: MemoryCategory | None = None
    source: MemorySource | None = None
    verified_only: bool = False
    active_only: bool = True
    exclude_stale: bool = True
    entity: str | None = None  # filter by entity appearing in entity_ids
    min_usefulness: float | None = None
    max_staleness: float | None = None


class SearchRequest(BaseModel):
    """
    Primary search request model. Serialised as JSON over HTTP and MCP.
    The SDK fluent builder (ObjectSet-style) serialises to this.

    Example (search-around OR semantics):
      SearchRequest(
          query="parking integration",
          search_around=SearchAroundSpec(link_types=[ConceptLinkType.CONTRADICTS]),
          filter=MemoryFilter(category=MemoryCategory.FACT),
          limit=10,
      )
    """

    query: str = Field(..., min_length=1)
    search_around: SearchAroundSpec | None = None
    filter: MemoryFilter | None = None
    limit: int = Field(default=10, ge=1, le=100)
    include_archived: bool = False


class SearchResponse(BaseModel):
    """Response from a memory search."""

    session_id: str  # QuerySession ID (used to submit feedback later)
    memories: list[MemoryRecord]
    total_found: int
    search_around_ids: list[str] = Field(default_factory=list)  # IDs added via graph traversal
    notes_on_results: dict[str, list[MemoryRecord]] = Field(default_factory=dict)
    # mapping {result_memory_id: [annotating note records]}, populated by the
    # ANNOTATES reverse-traversal auto-include (see design §5b). Default empty = today.


class NoteResult(BaseModel):
    """Outcome of create_note (what the note anchored to)."""

    note: MemoryRecord
    anchor_kind: Literal["memory", "topic", "none"]
    anchor_memory_id: str | None = None  # set when anchor_kind == "memory"
    anchor_entities: list[str] = Field(default_factory=list)  # entities folded in (topic/memory)
    anchor_phrase: str | None = None  # the raw ``about`` text, if any


# ---------------------------------------------------------------------------
# Stats / health
# ---------------------------------------------------------------------------


class MemoryStats(BaseModel):
    """Output of memory:stats tool / GET /stats endpoint."""

    total_memories: int
    active: int
    stale: int
    archived: int
    concept_links: int
    memory_summaries: int
    avg_usefulness_score: float
    avg_staleness_score: float
    top_concepts: list[tuple[str, int]] = Field(default_factory=list)  # (concept, count)
