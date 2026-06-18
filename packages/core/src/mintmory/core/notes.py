"""
Personal notes — user-authored "remember this" memory capture, anchor resolution, and listing.

A note is a :class:`~mintmory.core.types.MemoryRecord` with ``is_note=True``,
``source=USER``, and ``verified=True``.  The single load-bearing predicate
throughout the system is ``is_note``; do not branch on ``source``/``verified``.

Public API:
    :func:`create_note`  — capture a new user note (with optional anchor).
    :func:`notes_list`   — list notes, newest-first, with optional filters.

Internal:
    :func:`_resolve_anchor` — conservative dominance test → ANNOTATES link or
                              topic fold; always stores ``metadata['anchor']``.

No LLM, no network.  Only ``StorageAdapter``, ``types``, ``config.NoteSettings``,
and ``entities.extract_entities`` are imported.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from mintmory.core.entities import extract_entities
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    LinkSource,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
    NoteResult,
)

if TYPE_CHECKING:
    from mintmory.core.config import NoteSettings
    from mintmory.core.storage import StorageAdapter


# ---------------------------------------------------------------------------
# Internal anchor resolution
# ---------------------------------------------------------------------------


def _resolve_anchor(
    adapter: StorageAdapter,
    note_id: str,
    about: str,
    settings: NoteSettings,
) -> tuple[str | None, list[str]]:
    """Resolve an ``about`` phrase.

    Returns ``(anchor_memory_id_or_None, entity_ids_to_fold_in)``.

    Side effect: if a dominant candidate is found, an ANNOTATES link is added
    from the note to that candidate (``note_id`` → ``candidate.id``).  No link
    is created for the topic-fold path.

    Args:
        adapter:  the storage adapter (must already be initialised).
        note_id:  the ID of the note that was just persisted.
        about:    the free-text anchor phrase supplied by the caller.
        settings: :class:`~mintmory.core.config.NoteSettings` (carries
                  ``anchor_min_dominance``).

    Returns:
        A 2-tuple ``(anchor_memory_id | None, [entity_id, ...])``.  When a hard
        link is created ``anchor_memory_id`` is set and ``entity_ids`` is the
        anchored item's own entity list (to fold into the note).  In the
        topic-fold path ``anchor_memory_id`` is ``None`` and ``entity_ids``
        comes from :func:`~mintmory.core.entities.extract_entities` over the
        phrase.
    """
    # ------------------------------------------------------------------
    # Step 1: side-effect-free candidate lookup (no QuerySession, no bumps).
    # ------------------------------------------------------------------
    candidates: list[tuple[float, MemoryRecord]] = adapter._anchor_candidates(about, limit=5)

    # Exclude the just-created note and other notes / archived rows.
    candidates = [
        (score, mem)
        for score, mem in candidates
        if mem.id != note_id and not mem.is_note and not mem.is_archived
    ]

    # ------------------------------------------------------------------
    # Step 2: dominance test.
    # ------------------------------------------------------------------
    if candidates:
        total = sum(s for s, _ in candidates)
        if total > 0.0:
            top_score, top_mem = candidates[0]
            top_share = top_score / total

            is_dominant = top_share >= settings.anchor_min_dominance and (
                len(candidates) == 1 or top_score > candidates[1][0]
            )
            if is_dominant:
                # Hard link: note → item.
                link = ConceptLink(
                    source_memory_id=note_id,
                    target_memory_id=top_mem.id,
                    link_type=ConceptLinkType.ANNOTATES,
                    entity=about,
                    source=LinkSource.USER,
                    strength=1.0,
                    confidence=top_share,
                )
                adapter.add_link(link)
                return top_mem.id, list(top_mem.entity_ids)

    # ------------------------------------------------------------------
    # Step 3: fallback to topic anchor.
    # ------------------------------------------------------------------
    phrase_entities = extract_entities(about)
    return None, phrase_entities


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_note(
    adapter: StorageAdapter,
    content: str,
    about: str | None = None,
    when: datetime | None = None,
    until: datetime | None = None,
    category: MemoryCategory | None = None,
    settings: NoteSettings | None = None,
) -> NoteResult:
    """Create a user-authored note (the ONE capture primitive).

    A note is a :class:`~mintmory.core.types.MemoryRecord` with
    ``is_note=True``, ``source=USER``, ``verified=True``.

    Args:
        adapter:  initialised :class:`~mintmory.core.storage.StorageAdapter`.
        content:  the note text (1..10_000 chars).
        about:    optional free-text "what this is about" anchor phrase.
                  Resolved conservatively (see ``_resolve_anchor``): a
                  confident/dominant match becomes an ANNOTATES hard-link;
                  otherwise the phrase's entities are folded into the note's
                  ``entity_ids`` (topic anchor) and the raw phrase is stashed
                  in ``metadata['anchor']``.
        when:     optional datetime already parsed by the transport (the agent
                  converts natural language to ISO).  Stored in ``valid_from``.
        until:    optional deadline datetime.  Stored in ``valid_until``.
        category: optional :class:`~mintmory.core.types.MemoryCategory`
                  override.  Default: ``TEMPORAL`` when ``when`` is given,
                  else ``EPISODIC``.
        settings: :class:`~mintmory.core.config.NoteSettings` (anchor
                  dominance threshold etc.).  Defaults to ``NoteSettings()``
                  (env-driven).

    Returns:
        :class:`~mintmory.core.types.NoteResult` describing what was created
        and what it anchored to.
    """
    # Step 1: resolve settings.
    if settings is None:
        from mintmory.core.config import NoteSettings

        settings = NoteSettings()

    # Step 2: default category.
    resolved_category = category or (
        MemoryCategory.TEMPORAL if when is not None else MemoryCategory.EPISODIC
    )

    # Step 3: build and persist the note.
    # metadata['anchor'] is stashed after anchor resolution, so we start empty.
    note = adapter.add_memory(
        record=MemoryRecord(
            content=content,
            category=resolved_category,
            source=MemorySource.USER,
            verified=True,
            is_note=True,
            valid_from=when,
            valid_until=until,
        )
    )

    # Step 4: anchor resolution (only when an ``about`` phrase is given).
    anchor_kind: str
    anchor_memory_id: str | None = None
    anchor_entities: list[str] = []
    anchor_phrase: str | None = about

    if about is not None:
        anchor_memory_id, anchor_entities = _resolve_anchor(adapter, note.id, about, settings)
        anchor_kind = "memory" if anchor_memory_id is not None else "topic"

        # Single follow-up update: fold anchor entities into note's entity_ids
        # and stash the raw phrase (and optional anchor_memory_id) in metadata.
        merged_entities = list(
            dict.fromkeys(list(note.entity_ids) + anchor_entities)  # dedup, order-stable
        )
        updated_metadata = dict(note.metadata)
        updated_metadata["anchor"] = about
        if anchor_memory_id is not None:
            updated_metadata["anchor_memory_id"] = anchor_memory_id

        note = adapter.update_memory(
            note.id,
            entity_ids=merged_entities,
            metadata=updated_metadata,
        )
    else:
        anchor_kind = "none"

    return NoteResult(
        note=note,
        anchor_kind=anchor_kind,  # type: ignore[arg-type]
        anchor_memory_id=anchor_memory_id,
        anchor_entities=anchor_entities,
        anchor_phrase=anchor_phrase,
    )


def notes_list(
    adapter: StorageAdapter,
    about: str | None = None,
    upcoming: bool = False,
    overdue: bool = False,
    limit: int = 50,
    now: datetime | None = None,
) -> list[MemoryRecord]:
    """List notes (``is_note=1``), newest-first by default.

    Filters (all optional, combinable):

    * ``about`` — only notes whose ``entity_ids`` contain ``about``
      (case-insensitive) OR whose ``metadata['anchor']`` contains it
      (case-insensitive substring).
    * ``upcoming`` — only notes with ``valid_from > now``, sorted
      soonest-first.
    * ``overdue`` — only notes with ``valid_from < now`` and not archived,
      sorted most-overdue-first (ascending ``valid_from``).
    * ``limit`` — row cap.

    ``upcoming`` and ``overdue`` are mutually-exclusive temporal views; if
    both are ``True``, raises :class:`ValueError` (transports surface it as a
    4xx / ``BadParameter``).

    Archived notes are excluded from all three views by default (the storage
    layer handles this).

    Args:
        adapter:  initialised :class:`~mintmory.core.storage.StorageAdapter`.
        about:    optional filter term.
        upcoming: return only future-dated notes, soonest first.
        overdue:  return only past-due notes, most-overdue first.
        limit:    maximum rows to return.
        now:      override for "now" (used in tests; defaults to UTC wall-clock
                  inside ``list_notes``).

    Returns:
        A list of :class:`~mintmory.core.types.MemoryRecord` rows where
        ``is_note=True``.

    Raises:
        ValueError: when both ``upcoming`` and ``overdue`` are ``True``.
    """
    if upcoming and overdue:
        raise ValueError(
            "'upcoming' and 'overdue' are mutually exclusive — set at most one to True."
        )

    # Translate 'about' into the two storage-layer filter params.
    # The storage method post-filters entity membership and anchor substring.
    entity_filter: str | None = about
    anchor_substr: str | None = about

    return adapter.list_notes(
        entity=entity_filter,
        anchor_substr=anchor_substr,
        upcoming=upcoming,
        overdue=overdue,
        include_archived=False,
        limit=limit,
        now=now,
    )
