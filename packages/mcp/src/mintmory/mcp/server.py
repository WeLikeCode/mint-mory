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
from pathlib import Path
from typing import Any, Literal

# FastMCP import — raises ImportError if mintmory-mcp not installed
try:
    from fastmcp import FastMCP
except ImportError as e:
    raise ImportError("fastmcp is not installed. Run: uv sync --package mintmory-mcp") from e

from mintmory.core import notes as notes_mod
from mintmory.core import session as session_mod
from mintmory.core.config import load_settings
from mintmory.core.llm import build_dreaming_engine
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import (
    CaptionRunReport,
    ConceptLinkType,
    DreamIntensity,
    MemoryCategory,
    MemoryFilter,
    MemoryRecord,
    MemorySource,
    SearchAroundSpec,
    SearchRequest,
)
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
        "If MINTMORY_VISION_PROVIDER=llm is configured, call vision_run to auto-caption instead."
    ),
)

_store: StorageAdapter | None = None


def _get_store() -> StorageAdapter:
    global _store
    if _store is None:
        db_path = os.environ.get("MINTMORY_DB", str(Path.home() / ".mintmory" / "memories.db"))
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _store = StorageAdapter(db_path)
        _store.initialise()
    return _store


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
    record = store.get_memory(memory_id)
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
    response = store.search(request)
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
    engine = build_dreaming_engine(
        store,
        settings.llm,
        link_settings=settings.link,
        summary_settings=settings.summary,
    )
    if DreamIntensity(intensity) is DreamIntensity.FULL:
        report = engine.run_full()
    else:
        report = engine.run_light()
    result: dict[str, Any] = report.model_dump(mode="json")
    return result


@mcp.tool()
def memory_stats() -> dict[str, Any]:
    """Return memory health statistics."""
    store = _get_store()
    result: dict[str, Any] = store.get_stats().model_dump(mode="json")
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
        )
    except ValueError as exc:
        return {"error": "conflict", "message": str(exc)}
    result: dict[str, Any] = updated.model_dump(mode="json")
    return result


@mcp.tool()
def memory_archive(memory_id: str) -> dict[str, Any]:
    """Soft-delete a memory (sets is_archived=True, is_active=False)."""
    store = _get_store()
    store.archive_memory(memory_id)
    return {"id": memory_id, "archived": True}


@mcp.tool()
def summary_list() -> list[dict[str, Any]]:
    """List all concept summaries generated by the dreaming process."""
    store = _get_store()
    return [summary.model_dump(mode="json") for summary in store.list_summaries()]


@mcp.tool()
def summary_get(concept: str) -> dict[str, Any] | None:
    """Get the summary for a specific concept. Returns None if not found."""
    store = _get_store()
    summary = store.get_summary(concept)
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
        store, settings.llm, link_settings=settings.link, summary_settings=settings.summary
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
        store, settings.llm, link_settings=settings.link, summary_settings=settings.summary
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
        )
    except ValueError as exc:
        return {"error": "bad_request", "message": str(exc)}
    return [m.model_dump(mode="json") for m in records]


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
            store, file_id_or_path, description, settings=settings.vision
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
    )
    return report.model_dump(mode="json")


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
    args = parser.parse_args()

    if args.db:
        os.environ["MINTMORY_DB"] = args.db

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse", port=args.port)


if __name__ == "__main__":
    main()
