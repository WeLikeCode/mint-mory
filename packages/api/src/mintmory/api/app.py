"""
MintMory FastAPI application — M6 implementation target.

All routes conform to docs/openapi/mintmory.yaml. This REST surface is a thin
transport over the frozen ``mintmory.core`` service layer: every route validates
its request, calls one or more core functions, and serialises the canonical
``types.py`` models back to the client. No domain logic lives here.

Run: uvicorn mintmory.api.app:app --port 8080
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from mintmory.api.schemas import (
    ConceptLinkCreate,
    DreamRequest,
    ImageCaptionPut,
    MemoryCreate,
    MemoryUpdate,
    NoteCreate,
    SessionFeedback,
    SummaryPut,
)
from mintmory.core import session as session_module
from mintmory.core.config import load_settings
from mintmory.core.dreaming import DreamingEngine
from mintmory.core.llm import build_dreaming_engine
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import (
    SYMMETRIC_LINK_TYPES,
    ConceptLink,
    ConceptLinkType,
    DreamIntensity,
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

_store: StorageAdapter | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _store
    db_path = os.environ.get("MINTMORY_DB", str(Path.home() / ".mintmory" / "memories.db"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _store = StorageAdapter(db_path)
    _store.initialise()
    yield
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


def get_store() -> StorageAdapter:
    if _store is None:
        raise RuntimeError("Storage not initialised — lifespan not run")
    return _store


# ---------------------------------------------------------------------------
# Memories
# ---------------------------------------------------------------------------


@app.post("/memories", response_model=MemoryRecord, status_code=201, tags=["Memories"])
async def add_memory(body: MemoryCreate) -> MemoryRecord:
    """Add a new memory. See POST /memories in openapi/mintmory.yaml."""
    return get_store().add_memory(**body.model_dump())


@app.get("/memories/{memory_id}", response_model=MemoryRecord, tags=["Memories"])
async def get_memory(memory_id: str) -> MemoryRecord:
    result = get_store().get_memory(memory_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")
    return result


@app.patch("/memories/{memory_id}", response_model=MemoryRecord, tags=["Memories"])
async def update_memory(memory_id: str, body: MemoryUpdate) -> MemoryRecord:
    """Partial update. Only fields present in the body are changed."""
    store = get_store()
    if store.get_memory(memory_id) is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")
    updates = body.model_dump(exclude_unset=True)
    return store.update_memory(memory_id, **updates)


@app.delete("/memories/{memory_id}", status_code=204, tags=["Memories"])
async def archive_memory(memory_id: str) -> None:
    store = get_store()
    if store.get_memory(memory_id) is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")
    store.archive_memory(memory_id)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@app.post("/memories/search", response_model=SearchResponse, tags=["Search"])
async def search_memories(request: SearchRequest) -> SearchResponse:
    return get_store().search(request)


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
    if store.get_memory(memory_id) is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")
    links = store.get_links(memory_id, link_type=link_type)
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
    if store.get_memory(memory_id) is None:
        raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")
    if store.get_memory(body.target_memory_id) is None:
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
    created = store.add_link(link)

    if body.link_type in SYMMETRIC_LINK_TYPES:
        store.add_link(
            ConceptLink(
                source_memory_id=body.target_memory_id,
                target_memory_id=memory_id,
                link_type=body.link_type,
                entity=body.entity,
                strength=body.strength,
                confidence=body.confidence,
                source=LinkSource.USER,
            )
        )

    return created


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


@app.post("/notes", response_model=NoteResult, status_code=201, tags=["Notes"])
async def create_note(body: NoteCreate) -> NoteResult:
    """Create a user-authored note (``is_note=true``). See core.notes.create_note."""
    from mintmory.core import notes as notes_mod

    return notes_mod.create_note(
        get_store(),
        content=body.content,
        about=body.about,
        when=body.when,
        until=body.until,
        category=body.category,
    )


@app.get("/notes", response_model=list[MemoryRecord], tags=["Notes"])
async def list_notes(
    about: Annotated[str | None, Query()] = None,
    upcoming: Annotated[bool, Query()] = False,
    overdue: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[MemoryRecord]:
    """List user-authored notes. ``upcoming``/``overdue`` are mutually exclusive (422 if both)."""
    from mintmory.core import notes as notes_mod

    try:
        return notes_mod.notes_list(
            get_store(), about=about, upcoming=upcoming, overdue=overdue, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@app.get("/stats", response_model=MemoryStats, tags=["Stats"])
async def get_stats() -> MemoryStats:
    return get_store().get_stats()


# ---------------------------------------------------------------------------
# Dream
# ---------------------------------------------------------------------------


@app.post("/dream", response_model=DreamReport, tags=["Dream"])
async def run_dream(body: DreamRequest) -> DreamReport:
    engine = DreamingEngine(get_store())
    if body.intensity is DreamIntensity.FULL:
        return engine.run_full()
    return engine.run_light()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@app.get("/sessions/{session_id}", response_model=QuerySession, tags=["Sessions"])
async def get_session(session_id: str) -> QuerySession:
    result = get_store().get_session(session_id)
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
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    try:
        return session_module.apply_feedback(
            store,
            session_id,
            useful_ids=body.useful_ids,
            stale_ids=body.stale_ids,
            confidence_rating=body.confidence_rating,
            reasoning=body.reasoning,
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
    summaries: list[MemorySummary] = get_store().list_summaries()
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
    engine = build_dreaming_engine(
        get_store(),
        settings.llm,
        link_settings=settings.link,
        summary_settings=settings.summary,
    )
    jobs = engine.collect_summary_jobs(include_all=include_all)
    if limit > 0:
        jobs = jobs[:limit]
    return jobs


@app.get("/summaries/{concept}", response_model=MemorySummary, tags=["Summaries"])
async def get_summary(concept: str) -> MemorySummary:
    result = get_store().get_summary(concept)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No summary for concept '{concept}'")
    return result


@app.put("/summaries/{concept}", response_model=MemorySummary, tags=["Summaries"])
async def put_summary(concept: str, body: SummaryPut) -> MemorySummary:
    """Store an agent-supplied summary for ``concept`` (idempotent upsert)."""
    settings = load_settings()
    engine = build_dreaming_engine(
        get_store(),
        settings.llm,
        link_settings=settings.link,
        summary_settings=settings.summary,
    )
    return engine.apply_summary(concept, body.summary_text)


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
    from mintmory.core import vision as vision_mod

    settings = load_settings()
    return vision_mod.image_jobs(
        get_store(),
        include_all=include_all,
        include_bytes=include_bytes,
        limit=limit,
        settings=settings.vision,
    )


@app.put("/images/{file_id}", response_model=ImageDescription, tags=["Images"])
async def put_image_caption(file_id: str, body: ImageCaptionPut) -> ImageDescription:
    """Store an agent-supplied description for the image file-record ``file_id``.

    Persists the description as a context memory ANNOTATES-linked to the image
    file-record. Idempotent: re-putting replaces the prior description (the image
    then drops out of the default ``GET /images/jobs`` work-list). No vision backend
    is required. Returns the stored ``ImageDescription`` with linkage facts.
    """
    from mintmory.core import vision as vision_mod

    settings = load_settings()
    try:
        return vision_mod.image_caption_put(
            get_store(), file_id, body.description, settings=settings.vision
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def main() -> None:
    import uvicorn

    uvicorn.run("mintmory.api.app:app", host="0.0.0.0", port=8080, reload=True)


if __name__ == "__main__":
    main()
