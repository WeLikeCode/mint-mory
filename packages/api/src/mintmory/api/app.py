"""
MintMory FastAPI application — M6 implementation target.

All routes conform to docs/openapi/mintmory.yaml. This REST surface is a thin
transport over the frozen ``mintmory.core`` service layer: every route validates
its request, calls one or more core functions, and serialises the canonical
``types.py`` models back to the client. No domain logic lives here.

Run: uvicorn mintmory.api.app:app --port 8080
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Annotated

import anyio
import anyio.to_thread
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mintmory.api.schemas import (
    CaptionRunRequest,
    ConceptLinkCreate,
    DreamRequest,
    ImageCaptionPut,
    MemoryCreate,
    MemoryUpdate,
    NoteCreate,
    SessionFeedback,
    SummaryPut,
)
from mintmory.api.telemetry_middleware import TelemetryMiddleware
from mintmory.core import session as session_module
from mintmory.core.config import load_settings
from mintmory.core.dreaming import DreamFailedError, DreamingEngine
from mintmory.core.dreaming import run_dream as run_tenant_dreams
from mintmory.core.llm import build_dreaming_engine
from mintmory.core.ports import StorageBackend
from mintmory.core.storage_factory import build_storage
from mintmory.core.telemetry import init_telemetry, shutdown_telemetry
from mintmory.core.types import (
    SYMMETRIC_LINK_TYPES,
    TENANT_GLOBAL,
    CaptionRunReport,
    ConceptLink,
    ConceptLinkType,
    DreamReport,
    ImageDescription,
    ImageJob,
    LinkSource,
    MemoryRecord,
    MemoryStats,
    MemorySummary,
    NoteResult,
    QuerySession,
    SearchRequest,
    SearchResponse,
    SummaryJob,
)

# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

_store: StorageBackend | None = None

# ---------------------------------------------------------------------------
# Thread-offload helper (design §6.3 Phase 2 requirement)
# ---------------------------------------------------------------------------


async def _db[T](call: Callable[[], T]) -> T:
    """Run a blocking storage call in anyio's default worker-thread pool.

    Required for Postgres mode: psycopg3's synchronous pool blocks the event loop,
    serialising concurrent requests and risking liveness-probe stalls on slow queries.
    Running the call in a thread allows other requests (including /healthz) to be
    served concurrently.  SQLite is also acceptable inline, but wrapping it here is
    harmless and keeps the code path uniform.
    """
    return await anyio.to_thread.run_sync(call)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _store
    settings = load_settings()
    # build_storage() resolves path from StorageSettings / MINTMORY_DB / default,
    # creates the parent directory, and returns an uninitialised backend.
    # NO embedder — API-added memories get NULL embeddings (asymmetry vs CLI).
    _store = build_storage(settings.storage)
    _store.initialise()
    init_telemetry(settings.otel, default_service_name="mintmory-api")

    # Startup guard (design §6.3): cap anyio's default thread-limiter to at most
    # pool_max so we never queue more DB threads than the pool can serve.
    # This prevents thread starvation when pool_max < anyio's default (40).
    pool_max = settings.storage.pool_max
    limiter = anyio.to_thread.current_default_thread_limiter()
    if limiter.total_tokens > pool_max:
        limiter.total_tokens = pool_max

    yield
    shutdown_telemetry()
    if _store:
        _store.close()
        _store = None


app = FastAPI(
    title="MintMory Memory API",
    version="0.1.0",
    description=(
        "Palantir-Ontology-inspired typed memory for LLM agents. "
        "See docs/openapi/mintmory.yaml for the full contract."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TelemetryMiddleware)


@app.exception_handler(DreamFailedError)
async def _dream_failed_error(_: Request, exc: DreamFailedError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=500)


def get_store() -> StorageBackend:
    if _store is None:
        raise RuntimeError("Storage not initialised — lifespan not run")
    return _store


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/healthz", tags=["Health"])
async def healthz() -> dict[str, str]:
    """Liveness probe — no DB touch."""
    return {"status": "ok"}


@app.get("/readyz", tags=["Health"])
async def readyz() -> dict[str, str]:
    """Readiness probe — verifies the DB is reachable via a cheap SELECT 1."""
    ok = await _db(lambda: get_store().ping())
    if not ok:
        raise HTTPException(status_code=503, detail="store not ready")
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# Memories
# ---------------------------------------------------------------------------


@app.post("/memories", response_model=MemoryRecord, status_code=201, tags=["Memories"])
async def add_memory(body: MemoryCreate) -> MemoryRecord:
    """Add a new memory. See POST /memories in openapi/mintmory.yaml."""
    data = body.model_dump()
    return await _db(lambda: get_store().add_memory(**data))


@app.get("/memories/{memory_id}", response_model=MemoryRecord, tags=["Memories"])
async def get_memory(memory_id: str) -> MemoryRecord:
    result = await _db(lambda: get_store().get_memory(memory_id))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")
    return result


@app.patch("/memories/{memory_id}", response_model=MemoryRecord, tags=["Memories"])
async def update_memory(memory_id: str, body: MemoryUpdate) -> MemoryRecord:
    """Partial update. Only fields present in the body are changed."""
    store = get_store()
    existing = await _db(lambda: store.get_memory(memory_id))
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")
    updates = body.model_dump(exclude_unset=True)
    return await _db(lambda: store.update_memory(memory_id, **updates))


@app.delete("/memories/{memory_id}", status_code=204, tags=["Memories"])
async def archive_memory(memory_id: str) -> None:
    store = get_store()
    existing = await _db(lambda: store.get_memory(memory_id))
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")
    await _db(lambda: store.archive_memory(memory_id))


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@app.post("/memories/search", response_model=SearchResponse, tags=["Search"])
async def search_memories(request: SearchRequest) -> SearchResponse:
    return await _db(lambda: get_store().search(request))


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


@app.get("/memories/{memory_id}/links", response_model=list[ConceptLink], tags=["Links"])
async def get_links(
    memory_id: str,
    link_type: Annotated[ConceptLinkType | None, Query()] = None,
    min_strength: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
) -> list[ConceptLink]:
    store = get_store()
    existing = await _db(lambda: store.get_memory(memory_id))
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")
    links = await _db(lambda: store.get_links(memory_id, link_type=link_type))
    return [link for link in links if link.strength >= min_strength]


@app.post(
    "/memories/{memory_id}/links",
    response_model=ConceptLink,
    status_code=201,
    tags=["Links"],
)
async def create_link(memory_id: str, body: ConceptLinkCreate) -> ConceptLink:
    """Create a manual ``ConceptLink`` from the path memory to a target memory.

    ``source`` is forced to ``user``. For symmetric link types
    (``relates_to``, ``contradicts``, ``similar_to``) the reverse link is also
    persisted; the forward link is returned.
    """
    store = get_store()
    if await _db(lambda: store.get_memory(memory_id)) is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")
    if await _db(lambda: store.get_memory(body.target_memory_id)) is None:
        raise HTTPException(status_code=404, detail=f"Memory '{body.target_memory_id}' not found")
    if body.target_memory_id == memory_id:
        raise HTTPException(
            status_code=422, detail="target_memory_id must differ from the source memory"
        )

    link = ConceptLink(
        source_memory_id=memory_id,
        target_memory_id=body.target_memory_id,
        link_type=body.link_type,
        entity=body.entity,
        strength=body.strength,
        confidence=body.confidence,
        source=LinkSource.USER,
    )
    created = await _db(lambda: store.add_link(link))

    if body.link_type in SYMMETRIC_LINK_TYPES:
        reverse_link = ConceptLink(
            source_memory_id=body.target_memory_id,
            target_memory_id=memory_id,
            link_type=body.link_type,
            entity=body.entity,
            strength=body.strength,
            confidence=body.confidence,
            source=LinkSource.USER,
        )
        await _db(lambda: store.add_link(reverse_link))

    return created


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


@app.post("/notes", response_model=NoteResult, status_code=201, tags=["Notes"])
async def create_note(body: NoteCreate) -> NoteResult:
    """Create a user-authored note (``is_note=true``). See core.notes.create_note."""
    from mintmory.core import notes as notes_mod  # noqa: PLC0415

    store = get_store()
    content, about, when, until, category = (
        body.content,
        body.about,
        body.when,
        body.until,
        body.category,
    )
    return await _db(
        lambda: notes_mod.create_note(
            store, content=content, about=about, when=when, until=until, category=category
        )
    )


@app.get("/notes", response_model=list[MemoryRecord], tags=["Notes"])
async def list_notes(
    about: Annotated[str | None, Query()] = None,
    upcoming: Annotated[bool, Query()] = False,
    overdue: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[MemoryRecord]:
    """List user-authored notes. ``upcoming``/``overdue`` are mutually exclusive (422 if both)."""
    from mintmory.core import notes as notes_mod  # noqa: PLC0415

    store = get_store()
    try:
        return await _db(
            lambda: notes_mod.notes_list(
                store, about=about, upcoming=upcoming, overdue=overdue, limit=limit
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@app.get("/stats", response_model=MemoryStats, tags=["Stats"])
async def get_stats() -> MemoryStats:
    return await _db(lambda: get_store().get_stats())


# ---------------------------------------------------------------------------
# Dream
# ---------------------------------------------------------------------------


@app.post("/dream", response_model=DreamReport, tags=["Dream"])
async def run_dream(body: DreamRequest) -> DreamReport:
    store = get_store()
    intensity = body.intensity

    def _do_dream() -> DreamReport:
        return run_tenant_dreams(
            store,
            intensity=intensity,
            tenant_id=None,
            engine_factory=lambda tenant_id: DreamingEngine(store, tenant_id=tenant_id),
        )

    return await _db(_do_dream)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@app.get("/sessions/{session_id}", response_model=QuerySession, tags=["Sessions"])
async def get_session(session_id: str) -> QuerySession:
    result = await _db(lambda: get_store().get_session(session_id))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return result


@app.post("/sessions/{session_id}/feedback", response_model=QuerySession, tags=["Sessions"])
async def session_feedback(session_id: str, body: SessionFeedback) -> QuerySession:
    """Apply LLM self-assessment feedback and conclude the session.

    Maps the core ``ValueError`` to 404 (missing session) or 409 (already
    concluded).
    """
    store = get_store()
    existing = await _db(lambda: store.get_session(session_id))
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    useful_ids, stale_ids = body.useful_ids, body.stale_ids
    confidence_rating, reasoning = body.confidence_rating, body.reasoning
    try:
        return await _db(
            lambda: session_module.apply_feedback(
                store,
                session_id,
                useful_ids=useful_ids,
                stale_ids=stale_ids,
                confidence_rating=confidence_rating,
                reasoning=reasoning,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


@app.get("/summaries", response_model=list[MemorySummary], tags=["Summaries"])
async def list_summaries(
    include_stale: Annotated[bool, Query()] = False,
) -> list[MemorySummary]:
    summaries: list[MemorySummary] = await _db(lambda: get_store().list_summaries())
    if include_stale:
        return summaries
    return [summary for summary in summaries if summary.is_current]


@app.get("/summaries/jobs", response_model=list[SummaryJob], tags=["Summaries"])
async def list_summary_jobs(
    include_all: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=0)] = 0,
) -> list[SummaryJob]:
    """Concept-summary jobs for an agent to write (agent-supplied L3).

    ``include_all=false`` (default) returns only concepts needing a (re)summary.
    ``limit=0`` means no cap.
    """
    settings = load_settings()
    store = get_store()

    def _collect() -> list[SummaryJob]:
        engine = build_dreaming_engine(
            store,
            settings.llm,
            link_settings=settings.link,
            summary_settings=settings.summary,
            tenant_id=TENANT_GLOBAL,
        )
        jobs = engine.collect_summary_jobs(include_all=include_all)
        return jobs[:limit] if limit > 0 else jobs

    return await _db(_collect)


@app.get("/summaries/{concept}", response_model=MemorySummary, tags=["Summaries"])
async def get_summary(concept: str) -> MemorySummary:
    result = await _db(lambda: get_store().get_summary(concept))
    if result is None:
        raise HTTPException(status_code=404, detail=f"No summary for concept '{concept}'")
    return result


@app.put("/summaries/{concept}", response_model=MemorySummary, tags=["Summaries"])
async def put_summary(concept: str, body: SummaryPut) -> MemorySummary:
    """Store an agent-supplied summary for ``concept`` (idempotent upsert)."""
    settings = load_settings()
    store = get_store()
    summary_text = body.summary_text

    def _apply() -> MemorySummary:
        engine = build_dreaming_engine(
            store,
            settings.llm,
            link_settings=settings.link,
            summary_settings=settings.summary,
            tenant_id=TENANT_GLOBAL,
        )
        return engine.apply_summary(concept, summary_text)

    return await _db(_apply)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------


@app.get("/images/jobs", response_model=list[ImageJob], tags=["Images"])
async def list_image_jobs(
    include_all: Annotated[bool, Query()] = False,
    include_bytes: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=0)] = 0,
) -> list[ImageJob]:
    """Image-description jobs for an agent (agent-supplied vision).

    Returns the set of raster image file-records the calling agent should describe.
    MintMory does NOT call a vision model — the agent IS the vision-capable model.
    Each job carries path/rel/mime/size, the online_only flag, and either an inline
    base64 ``image_b64`` or ``null`` meaning the agent should read the file at ``path``.
    ``include_all=false`` (default) returns only images that still need a description.
    ``limit=0`` means no cap.
    """
    from mintmory.core import vision as vision_mod  # noqa: PLC0415

    settings = load_settings()
    store = get_store()
    return await _db(
        lambda: vision_mod.image_jobs(
            store,
            include_all=include_all,
            include_bytes=include_bytes,
            limit=limit,
            settings=settings.vision,
        )
    )


@app.put("/images/{file_id}", response_model=ImageDescription, tags=["Images"])
async def put_image_caption(file_id: str, body: ImageCaptionPut) -> ImageDescription:
    """Store an agent-supplied description for the image file-record ``file_id``.

    Persists the description as a context memory ANNOTATES-linked to the image
    file-record. Idempotent: re-putting replaces the prior description (the image
    then drops out of the default ``GET /images/jobs`` work-list). No vision backend
    is required. Returns the stored ``ImageDescription`` with linkage facts.
    """
    from mintmory.core import vision as vision_mod  # noqa: PLC0415

    settings = load_settings()
    store = get_store()
    description = body.description
    try:
        return await _db(
            lambda: vision_mod.image_caption_put(
                store, file_id, description, settings=settings.vision
            )
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/images/caption-run", response_model=CaptionRunReport, tags=["Images"])
async def caption_run(body: CaptionRunRequest) -> CaptionRunReport:
    """Caption already-indexed pending images server-side with the configured vision provider.

    Requires ``MINTMORY_VISION_PROVIDER=llm`` (a reachable OpenAI-compatible vision model)
    to do real work. With provider=agent (the default) this is a no-op: returns a
    ``CaptionRunReport`` with ``provider='agent'`` and all-zero counts — use the
    ``GET /images/jobs`` / ``PUT /images/{file_id}`` agent loop instead.

    Per-image failures (network/timeout/unreadable) are skipped and counted under
    ``failed``; one bad image never aborts the run. Returns a ``CaptionRunReport``
    with per-image audit items.

    Raises 422 when the configured provider is not yet implemented (e.g. ``ocr``).
    """
    from mintmory.core import vision as vision_mod  # noqa: PLC0415

    settings = load_settings()
    try:
        captioner = vision_mod.captioner_from_settings(settings.vision)
    except NotImplementedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if captioner is None:
        return CaptionRunReport(provider="agent")
    store = get_store()
    budget = int(body.budget_mb * 1024 * 1024) if body.budget_mb > 0 else None
    limit_val, include_all_val = body.limit, body.include_all
    return await _db(
        lambda: vision_mod.caption_pending_images(
            store,
            captioner=captioner,
            limit=limit_val,
            budget=budget,
            include_all=include_all_val,
            settings=settings.vision,
        )
    )


def main() -> None:
    import uvicorn

    uvicorn.run("mintmory.api.app:app", host="0.0.0.0", port=8080, reload=True)


if __name__ == "__main__":
    main()
