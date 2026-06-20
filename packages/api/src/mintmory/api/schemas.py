"""
Thin request-body models for the MintMory HTTP API.

These mirror the ``*Create`` / ``*Update`` / request schemas in
``docs/openapi/mintmory.yaml``. They exist only at the transport boundary:
each route validates the incoming JSON against one of these models and then
forwards the data into the frozen ``mintmory.core`` service layer (which owns
all domain logic and returns the canonical ``types.py`` models that are sent
back to the client).

Response models are the core ``types.py`` models directly (``MemoryRecord``,
``SearchResponse``, ``ConceptLink``, ``DreamReport``, ``QuerySession`` ...), so
they are not redefined here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mintmory.core.types import (
    ConceptLinkType,
    DreamIntensity,
    MemoryCategory,
    MemorySource,
)
from pydantic import BaseModel, Field, model_validator


class MemoryCreate(BaseModel):
    """Request body for ``POST /memories`` (OpenAPI ``MemoryCreate``).

    Only ``content`` and ``category`` are required; every other field has a
    server-side default supplied by ``MemoryRecord``.
    """

    content: str = Field(..., min_length=1, max_length=10_000)
    category: MemoryCategory
    source: MemorySource = MemorySource.AGENT
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    verified: bool = False
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryUpdate(BaseModel):
    """Request body for ``PATCH /memories/{id}`` (OpenAPI ``MemoryUpdate``).

    All fields are optional but at least one must be present
    (``minProperties: 1`` in the spec).
    """

    content: str | None = Field(default=None, min_length=1, max_length=10_000)
    category: MemoryCategory | None = None
    verified: bool | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> MemoryUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class ConceptLinkCreate(BaseModel):
    """Request body for ``POST /memories/{id}/links`` (OpenAPI ``ConceptLinkCreate``).

    The path memory is the ``source_memory_id``; ``source`` is forced to
    ``user`` by the route.
    """

    target_memory_id: str
    link_type: ConceptLinkType
    entity: str = ""
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class DreamRequest(BaseModel):
    """Request body for ``POST /dream`` (OpenAPI ``DreamRequest``)."""

    intensity: DreamIntensity


class SessionFeedback(BaseModel):
    """Request body for ``POST /sessions/{id}/feedback`` (OpenAPI ``SessionFeedback``)."""

    confidence_rating: int = Field(..., ge=1, le=5)
    useful_ids: list[str]
    stale_ids: list[str]
    reasoning: str | None = None


class NoteCreate(BaseModel):
    """Request body for ``POST /notes`` (OpenAPI ``NoteCreate``).

    Only ``content`` is required. ``when``/``until`` are ISO-8601 datetimes the
    client/agent has already parsed from natural language (MintMory does no date
    parsing). ``category`` defaults server-side to ``temporal`` when ``when`` is
    set, otherwise ``episodic``.
    """

    content: str = Field(..., min_length=1, max_length=10_000)
    about: str | None = None
    when: datetime | None = None
    until: datetime | None = None
    category: MemoryCategory | None = None


class SummaryPut(BaseModel):
    """Request body for ``PUT /summaries/{concept}`` (agent-supplied L3 summary)."""

    summary_text: str = Field(..., min_length=1)


class ImageCaptionPut(BaseModel):
    """Request body for ``PUT /images/{file_id}`` (agent-supplied image description)."""

    description: str = Field(..., min_length=1)


class CaptionRunRequest(BaseModel):
    """Request body for ``POST /images/caption-run`` (server-side auto-caption).

    Triggers the configured server-side vision provider (``MINTMORY_VISION_PROVIDER=llm``)
    to caption already-indexed pending raster images in place, without re-walking the
    tree. With provider=agent (the default) the route is a no-op and returns
    ``provider='agent'`` with all-zero counts.
    """

    limit: int = Field(default=0, ge=0, description="Max images to caption (0 = no cap).")
    budget_mb: float = Field(
        default=0.0,
        ge=0.0,
        description=("Download budget MB for online-only images (0 = use settings default)."),
    )
    include_all: bool = Field(
        default=False,
        description="Re-caption all raster images vs only pending (default).",
    )
