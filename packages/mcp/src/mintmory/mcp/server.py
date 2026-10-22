"""
MintMory MCP Server — M4 implementation target.

Three transports from one codebase (Serena MCP pattern):
  stdio:   mintmory-mcp  (default, for Claude Code / agent use)
  SSE:     mintmory-mcp --transport sse --port 8081
  HTTP:    mintmory-api  (separate package, full REST + OpenAPI)

Tools exposed (mapped 1:1 to HTTP endpoints in openapi/mintmory.yaml):
  memory_add         → POST /memories
  memory_get         → GET  /memories/{id}
  memory_archive     → DELETE /memories/{id}
  memory_search      → POST /memories/search
  memory_stats       → GET  /stats
  memory_dream       → POST /dream
  session_feedback   → POST /sessions/{id}/feedback
  summary_list       → GET  /summaries
  summary_get        → GET  /summaries/{concept}
  summary_jobs       → GET  /summaries/jobs
  summary_put        → PUT  /summaries/{concept}
  image_jobs         → GET  /images/jobs
  image_caption_put  → PUT  /images/{file_id}
  vision_run         → POST /images/caption-run

Implementation note: all tool handlers are thin wrappers over mintmory.core.
Every tool returns a JSON-safe dict (or list of dicts) produced via
``model.model_dump(mode="json")`` so the MCP layer can serialise it directly.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Any, Final, Literal

# FastMCP import — raises ImportError if mintmory-mcp not installed
try:
    from fastmcp import FastMCP
except ImportError as e:
    raise ImportError("fastmcp is not installed. Run: uv sync --package mintmory-mcp") from e

from mintmory.core import notes as notes_mod
from mintmory.core import session as session_mod
from mintmory.core.cochange import (
    COCHANGE_SQLITE_ONLY_MESSAGE,
    changed_with,
    documents_timeline,
)
from mintmory.core.config import LLMProvider, McpSettings, load_settings
from mintmory.core.dreaming import run_dream
from mintmory.core.llm import build_dreaming_engine
from mintmory.core.ports import StorageBackend
from mintmory.core.storage import SqliteBackend
from mintmory.core.storage_factory import build_storage
from mintmory.core.telemetry import init_telemetry
from mintmory.core.transfer import copy_between_tenants
from mintmory.core.types import (
    TENANT_GLOBAL,
    CaptionRunReport,
    ConceptLinkType,
    DreamIntensity,
    MemoryCategory,
    MemoryFilter,
    MemoryRecord,
    MemorySource,
    ScopeRequiredError,
    SearchAroundSpec,
    SearchRequest,
    TenantError,
    TenantNotFoundError,
    validate_tenant_id,
)
from mintmory.mcp._schema import build_schema
from mintmory.mcp.concise import concise_memory_get, concise_search_response

# ---------------------------------------------------------------------------
# Server initialisation
# ---------------------------------------------------------------------------

mcp: FastMCP[Any] = FastMCP(
    name="mintmory",
    version="0.1.0",
    instructions=(
        "MintMory: typed memory system for LLM agents (8 categories: fact, skill, "
        "preference, identity, context, episodic, temporal, relationship; "
        "12 ConceptLink types including annotates). "
        'BROWSING: use memory_search with verbosity="concise" for id+snippet results '
        'when scanning many memories; switch to verbosity="full" (default) only when '
        "you need complete body/metadata. "
        "GRAPH: use search_around to traverse the memory graph via typed relationships. "
        "FEEDBACK: call session_feedback after each query session to update usefulness scores. "
        "CONSOLIDATION: call memory_dream periodically to link concepts and resolve "
        "contradictions. "
        "NOTES: use memory_note for explicit user 'remember this' requests — exempt from "
        "auto-archival and win contradictions over inferred memories. "
        "SUMMARIES: call summary_jobs to get concepts needing synthesis, write each summary, "
        "send it back with summary_put — no separate LLM backend required. "
        "IMAGES: call image_jobs to get images needing a description, write a combined "
        "description, send it back with image_caption_put — no vision backend needed. "
        "If MINTMORY_VISION_PROVIDER=llm is configured, call vision_run to auto-caption instead. "
        "TENANCY: this server is bound to one tenant scope for its lifetime "
        "(see mintmory://capabilities); the global scope reads every tenant and "
        "writes the global tenant, a named scope reads and writes only its tenant. "
        "tenant_create and tenant_list manage the tenant directory."
    ),
)

TOOL_TENANT_SCOPE: Final[dict[str, str]] = {
    "memory_add": "create",
    "memory_get": "read",
    "memory_search": "read",
    "memory_dream": "dream",
    "memory_stats": "read",
    "session_feedback": "modify",
    "memory_archive": "modify",
    "summary_list": "read",
    "summary_get": "read",
    "summary_jobs": "create",
    "summary_put": "create",
    "memory_note": "create",
    "notes_list": "read",
    "docs_changed_with": "read",
    "docs_timeline": "read",
    "image_jobs": "create",
    "image_caption_put": "create",
    "vision_run": "create",
    "tenant_create": "directory",
    "tenant_list": "directory",
    "tenant_copy": "copy",
}

_store: StorageBackend | None = None
_store_lock = threading.Lock()
_scope_tenant: str = TENANT_GLOBAL


def _get_store() -> StorageBackend:
    global _store
    if _store is None:
        # Concurrent tool calls run in worker threads: build the adapter once so
        # two callers never race two backends against the same database file.
        with _store_lock:
            if _store is None:
                # build_storage() resolves path / creates parent dir / no embedder (MCP local)
                store = build_storage()
                store.initialise()
                _store = store
    return _store


def _effective_tenant() -> str | None:
    """Read scope: ``None`` for the global scope, the tenant id otherwise."""
    return None if _scope_tenant == TENANT_GLOBAL else _scope_tenant


def _bootstrap_scope(scope: str) -> None:
    """Validate and resolve the process-wide tenant scope once at startup."""
    global _scope_tenant
    validate_tenant_id(scope)
    store = _get_store()
    if scope != TENANT_GLOBAL:
        tenant = store.get_tenant(scope)
        if tenant is None:
            raise TenantNotFoundError(scope)
        if not tenant.is_active:
            print(
                f"mintmory-mcp: warning: tenant {scope!r} is inactive; this server is read-only",
                file=sys.stderr,
            )
    _scope_tenant = scope


# ---------------------------------------------------------------------------
# Resources — read-on-demand structured data (MM-40)
# ---------------------------------------------------------------------------


@mcp.resource("mintmory://schema")
def mintmory_schema() -> dict[str, Any]:
    """Memory taxonomy: all MemoryCategory / ConceptLinkType / MemorySource values
    with one-line descriptions, plus the MemoryRecord field list. Zero PII."""
    return build_schema()


@mcp.resource("mintmory://capabilities")
def mintmory_capabilities() -> dict[str, Any]:
    """Active configuration summary (providers, flags). Never includes api_key or
    absolute DB paths. Returns a safe minimal dict on settings-load failure."""
    try:
        settings = load_settings()
        llm_enabled = settings.llm.provider is not LLMProvider.NONE
        return {
            "embedding_provider": settings.embed.provider.value,
            "llm_provider": settings.llm.provider.value,
            "llm_enabled": llm_enabled,
            "llm_model": settings.llm.model,
            "vision_provider": settings.vision.provider.value,
            "dreaming_llm_steps": llm_enabled,
            "tenant_scope": _scope_tenant,
            "tenant_scoped": _scope_tenant != TENANT_GLOBAL,
        }
    except Exception:  # noqa: BLE001
        return {
            "error": "settings unavailable",
            "tenant_scope": _scope_tenant,
            "tenant_scoped": _scope_tenant != TENANT_GLOBAL,
        }


# ---------------------------------------------------------------------------
# Prompts — pre-authored agent-policy templates (MM-40)
# ---------------------------------------------------------------------------


@mcp.prompt()
def mintmory_recall_before_task(intent: str, link_types: str = "") -> str:
    """Guidance to search memory before acting on a task, then close the loop.

    Args:
        intent: What you are about to work on (used as the search query).
        link_types: Optional comma-separated ConceptLinkType values for graph
            traversal, e.g. "relates_to,contradicts". Leave empty for no graph hop.
    """
    lt_clause = ""
    if link_types.strip():
        lt_clause = f", search_around_link_types={link_types.strip().split(',')!r}"
    return (
        f"Before acting on: {intent!r}\n\n"
        "1. RECALL FIRST — call memory_search:\n"
        f'   memory_search(query="{intent}"{lt_clause})\n'
        "   KEEP the returned session_id — you will need it in step 3.\n\n"
        "2. ACT — use the retrieved memories to inform your work.\n\n"
        "3. CLOSE THE LOOP — after finishing, call session_feedback:\n"
        "   session_feedback(\n"
        "       session_id=<session_id from step 1>,\n"
        "       useful_ids=[<ids of memories that helped>],\n"
        "       stale_ids=[<ids of memories that were wrong or outdated>],\n"
        "       confidence_rating=1..5,\n"
        "       reasoning='<one sentence explanation>',\n"
        "   )\n"
        "   This self-assessment lets MintMory improve without human intervention.\n\n"
        "Source policy: hermes-onboarding.md §STEP 5 (recall→feedback discipline)."
    )


@mcp.prompt()
def mintmory_onboard(db_path: str = "", llm_enabled: bool = False) -> str:
    """MintMory onboarding policy (Part 1). Renders the adoption checklist as a prompt.

    Args:
        db_path: Optional path to the MintMory database (shown in the YAML snippet).
        llm_enabled: When True, includes LLM-tier configuration guidance.
    """
    db_line = f"MINTMORY_DB: {db_path}" if db_path else "MINTMORY_DB: ~/.mintmory/memories.db"
    llm_section = ""
    if llm_enabled:
        llm_section = (
            "\n      MINTMORY_LLM_PROVIDER: openai\n"
            "      MINTMORY_LLM_BASE_URL: http://localhost:8789/v1\n"
            "      MINTMORY_LLM_MODEL: MiniMax-M2.7"
        )
    return (
        "## MintMory Onboarding — adopt this memory policy\n\n"
        "MintMory is a local, typed, graph-linked memory system. Taxonomy reference:\n"
        "  mintmory://schema  (read with your MCP client to see all 8 categories +\n"
        "                      12 link types with descriptions)\n\n"
        "### Register the MCP server\n\n"
        "Add this block to your MCP configuration (command: uv run mintmory-mcp):\n\n"
        "    mintmory:\n"
        "      command: uv\n"
        "      args: [run, --project, /path/to/MintMory, mintmory-mcp]\n"
        "      enabled: true\n"
        "      env:\n"
        f"        {db_line}\n"
        "        MINTMORY_EMBED_PROVIDER: hashing"
        f"{llm_section}\n\n"
        "### Memory policy — apply every task\n\n"
        "  • RECALL FIRST: memory_search(query=<intent>) before acting.\n"
        "    Pass search_around_link_types=['relates_to'] for related items.\n"
        "    KEEP the returned session_id.\n\n"
        "  • WRITE durable knowledge: memory_add(content, category) where category\n"
        "    is one of: identity | preference | skill | context | fact |\n"
        "    episodic | temporal | relationship. One idea per memory.\n\n"
        "  • CLOSE THE LOOP: session_feedback(session_id, useful_ids=[...],\n"
        "    stale_ids=[...], confidence_rating=1..5). MintMory self-improves.\n\n"
        "  • CONSOLIDATE: memory_dream(intensity='full') when idle, to build\n"
        "    links + summaries and resolve contradictions.\n\n"
        "  • NOTES: use memory_note only when the user EXPLICITLY asks you to\n"
        "    remember something ('remember that...', 'note that...').\n\n"
        "  • BULK LOAD: mintmory ingest <paths...> --category <cat>\n"
        "    (chunks + dedups automatically; never script add-per-file).\n\n"
        "### Health check\n\n"
        "  mintmory doctor   # exit 0 = healthy\n\n"
        "Source policy: hermes-onboarding.md Part 1."
    )


@mcp.prompt()
def mintmory_session_closeout(session_id: str, useful_ids: str = "", stale_ids: str = "") -> str:
    """Guidance to submit session feedback and close the memory feedback loop.

    Args:
        session_id: The QuerySession id returned by memory_search.
        useful_ids: Comma-separated memory ids the agent found helpful.
        stale_ids: Comma-separated memory ids the agent found stale or incorrect.
    """
    useful_list = [i.strip() for i in useful_ids.split(",") if i.strip()]
    stale_list = [i.strip() for i in stale_ids.split(",") if i.strip()]
    return (
        "## Close the memory feedback loop\n\n"
        f"Session id: {session_id}\n\n"
        "Call session_feedback to record your passive self-assessment:\n\n"
        "    session_feedback(\n"
        f"        session_id={session_id!r},\n"
        f"        useful_ids={useful_list!r},\n"
        f"        stale_ids={stale_list!r},\n"
        "        confidence_rating=1..5,   # your overall confidence\n"
        "        reasoning='<one sentence>',\n"
        "    )\n\n"
        "This updates usefulness/staleness scores so MintMory self-improves.\n"
        "If you found no relevant memories, submit with empty lists — still call it.\n"
        "A session can only receive feedback once (returns conflict error if repeated)."
    )


@mcp.prompt()
def mintmory_what_cochanged_with(path: str) -> str:
    """Find documents that co-changed with a file, and how to read the result."""
    return (
        f"To find documents that co-changed with {path!r}:\n\n"
        f"1. Call docs_changed_with(path={path!r})\n\n"
        "2. Read each peer result:\n"
        "   • `strength` (0.0–1.0): proximity score — higher = stronger co-change signal.\n"
        "   • `observed_at`: ISO timestamp of when the co-change was observed.\n"
        "   • `kind`: changeset kind — `cold_full_index` means co-location (same folder,\n"
        "     same indexing run), `incremental` means a later re-index caught both files.\n"
        '     `kind` may be empty ("") for legacy rows.\n\n'
        "HONESTY CAVEAT: this is OBSERVED co-change — files that were indexed in the\n"
        "same time window with high folder + content proximity. It is NOT a version-\n"
        "controlled commit. `cold_full_index` peers may simply be co-located in the\n"
        "same directory, not actually co-edited.\n\n"
        f"3. If the result is empty, {path!r} may not be indexed or may not belong\n"
        "   to any change-set. Run:\n"
        "     mintmory index-tree <root> --cochange\n"
        "   to (re-)build co-change data for the corpus.\n\n"
        "4. For document recency (which files are newest), call docs_timeline with\n"
        "   an optional `since` window (e.g. since='30d') or `from_date`/`to_date`.\n\n"
        "This prompt is read-only: it suggests no write or store-altering operations."
    )


# ---------------------------------------------------------------------------
# Tools — thin wrappers over mintmory.core
# ---------------------------------------------------------------------------


@mcp.tool()
def memory_add(
    content: str,
    category: str,
    source: str = "agent",
    confidence: float = 1.0,
    verified: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Add a new memory to the store.

    Args:
        content: The memory text (1–10000 chars).
        category: One of: identity, preference, skill, context, fact,
                  episodic, temporal, relationship.
        source: Origin of this memory: user, agent, document, inference.
        confidence: How reliable this memory is (0.0–1.0).
        verified: Whether this has been explicitly confirmed.
        metadata: Optional JSON metadata dict.

    Returns:
        The stored MemoryRecord as a dict.
    """
    store = _get_store()
    record = MemoryRecord(
        content=content,
        category=MemoryCategory(category),
        source=MemorySource(source),
        confidence=confidence,
        verified=verified,
        metadata=metadata or {},
        tenant_id=_scope_tenant,
    )
    stored = store.add_memory(record=record)
    result: dict[str, Any] = stored.model_dump(mode="json")
    return result


@mcp.tool()
def memory_get(
    memory_id: str,
    verbosity: Literal["full", "concise"] = "full",
) -> dict[str, Any] | None:
    """Retrieve a single memory by its ID. Returns None if not found.

    Pass verbosity="concise" for a compact {id, category, content} projection
    when you only need the body; use the default "full" for all fields.
    """
    store = _get_store()
    record = store.get_memory(memory_id, tenant_id=_effective_tenant())
    if record is None:
        return None
    result: dict[str, Any] = record.model_dump(mode="json")
    if verbosity == "concise":
        return concise_memory_get(result)
    return result


@mcp.tool()
def memory_search(
    query: str,
    limit: int = 10,
    category: str | None = None,
    entity: str | None = None,
    search_around_link_types: list[str] | None = None,
    search_around_depth: int = 1,
    exclude_stale: bool = True,
    verbosity: Literal["full", "concise"] = "full",
) -> dict[str, Any]:
    """
    Search memories using hybrid FTS5 + vector similarity.

    Optionally traverses the concept graph (search_around) to find
    memories linked to the direct results via typed relationships.

    This implements the 'search in search OR scoped by relationships'
    requirement: results include both the direct matches AND memories
    reachable via the specified link types.

    Args:
        query: Natural language search query.
        limit: Max results to return (1–100).
        category: Filter by memory category.
        entity: Filter by entity appearing in entity_ids.
        search_around_link_types: Graph traversal link types, e.g.
            ['contradicts', 'relates_to']. Empty = all types.
        search_around_depth: How many hops to traverse (1–3).
        exclude_stale: Whether to exclude stale memories.
        verbosity: "full" (default) returns the complete SearchResponse with
            full MemoryRecord objects; "concise" returns a compact projection
            {id, category, snippet, is_note} per hit — use it for browsing/
            scanning; call memory_get with verbosity="full" when you need the body.

    Returns:
        SearchResponse dict with session_id, memories, total_found,
        and search_around_ids (IDs added via graph traversal).
    """
    store = _get_store()

    memory_filter = MemoryFilter(
        category=MemoryCategory(category) if category is not None else None,
        entity=entity,
        exclude_stale=exclude_stale,
    )

    search_around: SearchAroundSpec | None = None
    if search_around_link_types is not None:
        search_around = SearchAroundSpec(
            link_types=[ConceptLinkType(lt) for lt in search_around_link_types],
            depth=search_around_depth,
        )

    request = SearchRequest(
        query=query,
        limit=limit,
        filter=memory_filter,
        search_around=search_around,
    )
    response = store.search(request, tenant_id=_effective_tenant())
    result: dict[str, Any] = response.model_dump(mode="json")
    if verbosity == "concise":
        return concise_search_response(result)
    return result


@mcp.tool()
def memory_dream(intensity: str = "light") -> dict[str, Any]:
    """
    Run the dreaming consolidation process.

    Light: anomaly detection + concept linking + summary generation.
    Full: light + contradiction resolution + archival + rehabilitation.

    LLM-backed steps follow the configured tier; see docs/agent-history-mcp.md
    (LLM/config section). With MINTMORY_LLM_PROVIDER=none (default) only the
    structural steps run (summaries and contradiction resolution are skipped).

    Returns a DreamReport with counts of changes made.
    """
    store = _get_store()
    settings = load_settings()
    report = run_dream(
        store,
        intensity=DreamIntensity(intensity),
        tenant_id=_effective_tenant(),
        engine_factory=lambda tenant_id: build_dreaming_engine(
            store,
            settings.llm,
            link_settings=settings.link,
            summary_settings=settings.summary,
            tenant_id=tenant_id,
        ),
    )
    result: dict[str, Any] = report.model_dump(mode="json")
    return result


@mcp.tool()
def memory_stats() -> dict[str, Any]:
    """Return memory health statistics."""
    store = _get_store()
    result: dict[str, Any] = store.get_stats(tenant_id=_effective_tenant()).model_dump(mode="json")
    return result


@mcp.tool()
def session_feedback(
    session_id: str,
    useful_ids: list[str] | None = None,
    stale_ids: list[str] | None = None,
    confidence_rating: int | None = None,
    reasoning: str | None = None,
) -> dict[str, Any]:
    """
    Record LLM passive self-assessment for a completed query session.

    Increments ``usefulness_score`` / ``reinforcement_count`` for memories in
    ``useful_ids`` and ``staleness_score`` for memories in ``stale_ids``, then
    marks the session concluded. Returns the updated QuerySession as a dict.

    If the session does not exist or feedback was already submitted, returns an
    error dict ``{"error": "conflict", "message": ...}`` instead of raising.

    Args:
        session_id: The QuerySession id returned by memory_search.
        useful_ids: Memory ids the agent found helpful.
        stale_ids: Memory ids the agent found stale or incorrect.
        confidence_rating: Self-assessed confidence (1–5).
        reasoning: Optional free-text explanation.
    """
    store = _get_store()
    try:
        updated = session_mod.apply_feedback(
            store,
            session_id,
            useful_ids or [],
            stale_ids or [],
            confidence_rating,
            reasoning,
            tenant_id=_effective_tenant(),
        )
    except ValueError as exc:
        return {"error": "conflict", "message": str(exc)}
    result: dict[str, Any] = updated.model_dump(mode="json")
    return result


@mcp.tool()
def memory_archive(memory_id: str) -> dict[str, Any]:
    """Soft-delete a memory (sets is_archived=True, is_active=False)."""
    store = _get_store()
    try:
        store.archive_memory(memory_id, tenant_id=_effective_tenant())
    except KeyError as exc:
        return {"error": "not_found", "message": str(exc)}
    return {"id": memory_id, "archived": True}


@mcp.tool()
def summary_list() -> list[dict[str, Any]]:
    """List all concept summaries generated by the dreaming process."""
    store = _get_store()
    return [
        summary.model_dump(mode="json")
        for summary in store.list_summaries(tenant_id=_effective_tenant())
    ]


@mcp.tool()
def summary_get(concept: str) -> dict[str, Any] | None:
    """Get the summary for a specific concept. Returns None if not found."""
    store = _get_store()
    summary = store.get_summary(concept, _scope_tenant)
    if summary is None:
        return None
    result: dict[str, Any] = summary.model_dump(mode="json")
    return result


@mcp.tool()
def summary_jobs(include_all: bool = False, limit: int = 0) -> list[dict[str, Any]]:
    """List concept-summary jobs for YOU (the agent) to write (agent-supplied L3).

    MintMory does NOT call an LLM for these — you are the LLM. Each job carries the
    concept, the contributing memories' content, the current active memory_count,
    and the existing summary (if any) so you can refine it. Write a concise
    synthesis per concept and send it back with summary_put.

    Args:
        include_all: when False (default), only concepts that NEED a (re)summary
            are returned (no current summary, or the memory_count drifted). When
            True, every qualifying concept is returned.
        limit: max jobs to return (0 = no cap). Applied AFTER selection, in the
            engine's deterministic concept order.

    Returns:
        A list of SummaryJob dicts.
    """
    store = _get_store()
    settings = load_settings()
    engine = build_dreaming_engine(
        store,
        settings.llm,
        link_settings=settings.link,
        summary_settings=settings.summary,
        tenant_id=_scope_tenant,
    )
    jobs = engine.collect_summary_jobs(include_all=include_all)
    if limit > 0:
        jobs = jobs[:limit]
    return [job.model_dump(mode="json") for job in jobs]


@mcp.tool()
def summary_put(concept: str, summary_text: str) -> dict[str, Any]:
    """Store YOUR summary text for a concept (agent-supplied L3 summary).

    Persists summary_text verbatim as the concept's MemorySummary (memory_count
    is recomputed server-side from the current active memories). Idempotent:
    calling again for the same concept overwrites it. No LLM/backend is required.

    Args:
        concept: the concept/entity name (use a concept from summary_jobs).
        summary_text: the synthesis YOU wrote for this concept.

    Returns:
        The stored MemorySummary as a dict.
    """
    store = _get_store()
    settings = load_settings()
    engine = build_dreaming_engine(
        store,
        settings.llm,
        link_settings=settings.link,
        summary_settings=settings.summary,
        tenant_id=_scope_tenant,
    )
    result: dict[str, Any] = engine.apply_summary(concept, summary_text).model_dump(mode="json")
    return result


@mcp.tool()
def memory_note(
    content: str,
    about: str | None = None,
    when: str | None = None,
    until: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Capture a user-authored note ("remember this about X").

    CALL THIS ONLY when the user EXPLICITLY asks you to remember something
    ("remember that...", "note that...", "don't forget..."). For facts you merely
    inferred or extracted, use memory_add instead — notes are higher-authority and
    are exempt from auto-archival.

    Args:
        content:  the thing to remember (1..10000 chars).
        about:    optional subject ("about my Tokyo trip"); anchored conservatively
                  to an existing memory if there's a confident match, else to its
                  topic (entities).
        when:     optional ISO-8601 date this note is salient ("2026-07-01"). YOU
                  convert natural language to ISO; MintMory does no date parsing.
        until:    optional ISO-8601 deadline.
        category: optional override; default temporal when `when` is set, else episodic.

    Returns:
        NoteResult dict: the stored note plus what it anchored to (anchor_kind:
        memory|topic|none, anchor_memory_id, anchor_entities, anchor_phrase).
    """
    from datetime import datetime

    store = _get_store()

    parsed_when: datetime | None = None
    if when is not None:
        try:
            parsed_when = datetime.fromisoformat(when)
        except ValueError:
            return {
                "error": "bad_request",
                "message": f"Invalid ISO-8601 date for 'when': {when!r}",
            }

    parsed_until: datetime | None = None
    if until is not None:
        try:
            parsed_until = datetime.fromisoformat(until)
        except ValueError:
            return {
                "error": "bad_request",
                "message": f"Invalid ISO-8601 date for 'until': {until!r}",
            }

    parsed_category: MemoryCategory | None = None
    if category is not None:
        try:
            parsed_category = MemoryCategory(category)
        except ValueError:
            return {
                "error": "bad_request",
                "message": f"Invalid category: {category!r}",
            }

    note_result = notes_mod.create_note(
        store,
        content=content,
        about=about,
        when=parsed_when,
        until=parsed_until,
        category=parsed_category,
        tenant_id=_scope_tenant,
    )
    result: dict[str, Any] = note_result.model_dump(mode="json")
    return result


@mcp.tool()
def notes_list(
    about: str | None = None,
    upcoming: bool = False,
    overdue: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]] | dict[str, Any]:
    """List user-authored notes (is_note=true), newest-first.

    about:    filter to notes whose subject/entities mention this term.
    upcoming: only future-dated notes (valid_from in the future), soonest first.
    overdue:  only past-due notes (valid_from in the past), not archived.
    Returns a list of MemoryRecord dicts, each with is_note=true.
    """
    store = _get_store()
    try:
        records = notes_mod.notes_list(
            store,
            about=about,
            upcoming=upcoming,
            overdue=overdue,
            limit=limit,
            tenant_id=_effective_tenant(),
        )
    except ValueError as exc:
        return {"error": "bad_request", "message": str(exc)}
    return [m.model_dump(mode="json") for m in records]


# ---------------------------------------------------------------------------
# Co-change / document recency tools (MM-41)
# ---------------------------------------------------------------------------

_DOCS_TIMELINE_MAX = 200  # hard cap so a single MCP call cannot pull the whole corpus


@mcp.tool()
def docs_changed_with(path: str) -> list[dict[str, Any]] | dict[str, str]:
    """Documents observed to co-change with <path> (same index-tree change-set).

    Returns [{path, strength, observed_at, kind}] — each peer in the same observed
    change-set as <path>. Empty if <path> is not indexed or not part of a change-set.

    OBSERVED co-change means the files were indexed in the same time window with
    high folder/content proximity — NOT a version-controlled commit. `kind` may be
    empty ("") for legacy rows that predate changeset_kind labelling.

    To populate this data: run `mintmory index-tree <root> --cochange` first.
    Read-only. Only source='document' records are ever returned.
    SQLite-only: on another storage backend returns {"error": "not_implemented",
    "message": ...}.
    """
    store = _get_store()
    if not isinstance(store, SqliteBackend):
        return {"error": "not_implemented", "message": COCHANGE_SQLITE_ONLY_MESSAGE}
    return changed_with(store, path, tenant_id=_effective_tenant())


@mcp.tool()
def docs_timeline(
    since: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    collection: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]] | dict[str, str]:
    """Indexed documents newest-first by file modified-time (valid_from).

    Returns [{date, collection, path, title, valid_from}]. Use `since='30d'` for a
    rolling window, or `from_date`/`to_date` (ISO 8601) for a fixed range.
    Optional `collection` filter. `limit` is capped at 200 for token safety.

    A malformed `since`/date value returns {"error": "bad_request", "detail": ...}
    instead of raising. Read-only. Only source='document' records appear.
    SQLite-only: on another storage backend returns {"error": "not_implemented",
    "message": ...}.
    """
    capped = max(1, min(limit, _DOCS_TIMELINE_MAX))
    store = _get_store()
    if not isinstance(store, SqliteBackend):
        return {"error": "not_implemented", "message": COCHANGE_SQLITE_ONLY_MESSAGE}
    try:
        return documents_timeline(
            store,
            since=since,
            from_iso=from_date,
            to_iso=to_date,
            collection=collection,
            limit=capped,
            tenant_id=_effective_tenant(),
        )
    except ValueError as exc:  # bad `since`/date grammar
        return {"error": "bad_request", "detail": str(exc)}


# ---------------------------------------------------------------------------
# Image-understanding tools (agent-supplied vision, G5)
# ---------------------------------------------------------------------------


@mcp.tool()
def image_jobs(
    include_all: bool = False, include_bytes: bool = False, limit: int = 0
) -> list[dict[str, Any]]:
    """List indexed images for YOU (the agent) to describe (agent-supplied vision).

    MintMory does NOT call a vision model for these — you are the vision-capable
    model. Each job carries the image file-record id, its path/rel/mime/size, the
    online_only flag, and EITHER an inline base64 ``image_b64`` (when the file is
    online-only or include_bytes=True and within the size cap) OR ``image_b64:
    null`` meaning you should read the file at ``path``. Write ONE combined
    description per image (what it depicts + any legible text) and send it back
    with image_caption_put.

    Args:
        include_all: when False (default), only raster images that still NEED a
            description are returned; when True, every raster image file-record.
        include_bytes: force-embed base64 even for local files (use when you run
            on a different host than the MintMory DB and cannot read ``path``).
        limit: max jobs (0 = no cap), applied after selection.

    Returns:
        A list of ImageJob dicts.
    """
    store = _get_store()
    settings = load_settings()
    from mintmory.core import vision as vision_mod  # lazy: optional dependency group

    jobs = vision_mod.image_jobs(
        store,
        include_all=include_all,
        include_bytes=include_bytes,
        limit=limit,
        settings=settings.vision,
        tenant_id=_scope_tenant,
    )
    return [j.model_dump(mode="json") for j in jobs]


@mcp.tool()
def image_caption_put(file_id_or_path: str, description: str) -> dict[str, Any]:
    """Store YOUR description for one indexed image (agent-supplied vision).

    Persists ``description`` (your combined "what it depicts + legible text" blob)
    as a context memory ANNOTATES-linked to the image file-record. Idempotent:
    re-putting replaces the prior description (the image then drops out of the
    default image_jobs work-list). No vision backend is required.

    Args:
        file_id_or_path: the ImageJob ``file_id`` (preferred) or the image path.
        description: your one-blob description (non-empty).

    Returns:
        An ImageDescription dict (the stored record + linkage facts), or an error
        dict with ``error`` and ``message`` keys on failure.
    """
    if not description.strip():
        return {"error": "bad_request", "message": "description must be non-empty"}
    store = _get_store()
    settings = load_settings()
    from mintmory.core import vision as vision_mod  # lazy: optional dependency group

    try:
        result = vision_mod.image_caption_put(
            store,
            file_id_or_path,
            description,
            settings=settings.vision,
            tenant_id=_scope_tenant,
        )
    except KeyError as exc:
        return {"error": "not_found", "message": str(exc)}
    return result.model_dump(mode="json")


@mcp.tool()
def vision_run(limit: int = 0, budget_mb: float = 0.0, include_all: bool = False) -> dict[str, Any]:
    """Caption already-indexed pending images with the configured SERVER-SIDE vision
    provider (MINTMORY_VISION_PROVIDER=llm). Unlike image_jobs/image_caption_put
    (where YOU, the agent, describe), this calls a configured vision MODEL server-side
    and persists each description. With provider=agent it is a no-op (returns
    provider='agent', described=0) — use the image_jobs loop instead. Per-image
    failures are skipped and counted. Returns a CaptionRunReport dict.

    Args:
        limit: max images to caption (0 = no cap).
        budget_mb: download budget MB for online-only images (0 = settings default).
        include_all: re-caption all raster images vs only pending (default).
    """
    store = _get_store()
    settings = load_settings()
    from mintmory.core import vision as vision_mod  # lazy: optional dependency group

    try:
        captioner = vision_mod.captioner_from_settings(settings.vision)
    except NotImplementedError as exc:
        return {"error": "not_implemented", "message": str(exc)}
    if captioner is None:
        return CaptionRunReport(provider="agent").model_dump(mode="json")
    budget = int(budget_mb * 1024 * 1024) if budget_mb > 0 else None
    report = vision_mod.caption_pending_images(
        store,
        captioner=captioner,
        limit=limit,
        budget=budget,
        include_all=include_all,
        settings=settings.vision,
        tenant_id=_scope_tenant,
    )
    return report.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Tenant directory tools
# ---------------------------------------------------------------------------


@mcp.tool()
def tenant_create(tenant_id: str, name: str = "") -> dict[str, Any]:
    """Create a tenant idempotently.

    Available in every scope; creating a tenant never changes this process's
    scope. An existing id returns the existing tenant unchanged.

    Args:
        tenant_id: The tenant id to create (lowercase, validated).
        name: Optional human-readable tenant name.

    Returns:
        The stored Tenant as a dict.
    """
    store = _get_store()
    result: dict[str, Any] = store.create_tenant(tenant_id, name).model_dump(mode="json")
    return result


@mcp.tool()
def tenant_list() -> list[dict[str, Any]]:
    """List every tenant in the tenant directory (no memory data).

    Available in every scope.
    """
    store = _get_store()
    return [tenant.model_dump(mode="json") for tenant in store.list_tenants()]


@mcp.tool()
def tenant_copy(
    source_tenant: str,
    dest_tenant: str,
    memory_ids: list[str] | None = None,
    filter: dict[str, Any] | None = None,
    all_active: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Copy memories, their notes and their links between two tenants.

    Global scope only: a named-scope server refuses this before reading
    anything. The source is never modified. Returns a CopyReport as a dict.

    Args:
        source_tenant: Tenant to copy from.
        dest_tenant: Tenant to copy into.
        memory_ids: Explicit source memory ids to copy.
        filter: MemoryFilter fields selecting the source records.
        all_active: Copy every active, non-archived source memory.
        force: Copy records whose content already exists in the destination.
    """
    if _scope_tenant != TENANT_GLOBAL:
        raise ScopeRequiredError("tenant_copy", _scope_tenant)
    if filter is not None:
        unknown = set(filter) - set(MemoryFilter.model_fields)
        if unknown:
            raise ValueError(f"unknown filter key(s): {sorted(unknown)}")
        parsed_filter: MemoryFilter | None = MemoryFilter.model_validate(filter)
    else:
        parsed_filter = None
    return copy_between_tenants(
        _get_store(),
        source_tenant=source_tenant,
        dest_tenant=dest_tenant,
        memory_ids=memory_ids,
        filter=parsed_filter,
        all_active=all_active,
        force=force,
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="MintMory MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport to use (default: stdio)",
    )
    parser.add_argument("--port", type=int, default=8081, help="Port for SSE transport")
    parser.add_argument("--db", default=None, help="Path to SQLite database file")
    parser.add_argument(
        "--tenant",
        default=None,
        help="Tenant scope for this process (default: MINTMORY_MCP_TENANT or global)",
    )
    args = parser.parse_args()

    if args.db:
        os.environ["MINTMORY_DB"] = args.db

    scope = args.tenant or McpSettings().tenant or TENANT_GLOBAL
    try:
        _bootstrap_scope(scope)
    except TenantError as exc:
        print(f"mintmory-mcp: error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    # Initialise OTel exactly once, before the server starts handling requests.
    # Mirrors packages/api/src/mintmory/api/app.py's lifespan: no-op (returns
    # False) when MINTMORY_OTEL_ENABLED is unset/false or the optional
    # opentelemetry SDK is not installed — safe to call unconditionally.
    # No settings are passed: main() must not validate unrelated config, and
    # init_telemetry() builds OTelSettings() itself.
    init_telemetry(default_service_name="mintmory-mcp")

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse", port=args.port)


if __name__ == "__main__":
    main()
