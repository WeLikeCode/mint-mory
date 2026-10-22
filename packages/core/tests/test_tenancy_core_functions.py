"""RED tests for task 4 — tenant-scoped core functions (requirement 5).

They trace requirement 5.1 (``create_note`` stamps and anchors inside its
tenant), 5.2 (``notes_list`` forwards the tenant), 5.3 (``image_jobs`` lists one
tenant only), 5.4 (``image_caption_put`` / ``caption_pending_images`` stay
inside one tenant), 5.5 (``session.apply_feedback`` validates every id before
the first score change), 5.6 (``cochange`` read queries are tenant-confined)
and 5.8 (multi-step creates stay non-atomic).

The already-implemented paths (5.3/5.4, from task 3) build their fixtures with
raw SQL: their zero-value confirmation zeroes every public storage method, so a
fixture that used ``add_memory`` would fail with an error instead of an
assertion.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from mintmory.core import cochange
from mintmory.core.notes import create_note, notes_list
from mintmory.core.session import apply_feedback
from mintmory.core.storage import SqliteBackend
from mintmory.core.types import (
    ConceptLink,
    ConceptLinkType,
    ImageDescription,
    LinkSource,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
    QuerySession,
    TenantInactiveError,
)
from mintmory.core.vision import (
    ImageInput,
    caption_pending_images,
    image_caption_put,
    image_jobs,
)

_SCHEMA = Path(__file__).resolve().parents[1] / "src/mintmory/core/schema.sql"
_TS = "2026-01-01T00:00:00"


# ---------------------------------------------------------------------------
# Raw-SQL fixtures (independent of the zeroed public storage methods)
# ---------------------------------------------------------------------------


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def _fetch(path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _write(path: Path, sql: str, params: tuple[Any, ...] = ()) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _add_tenant(path: Path, tenant_id: str) -> None:
    _write(
        path,
        "INSERT OR IGNORE INTO tenants (id, name, is_active, created_at, updated_at) "
        "VALUES (?, ?, 1, ?, ?)",
        (tenant_id, tenant_id, _TS, _TS),
    )


def _add_memory(
    path: Path,
    memory_id: str,
    content: str,
    tenant_id: str = "global",
    *,
    category: str = "fact",
    source: str = "agent",
    entity_ids: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
    is_note: int = 0,
    valid_from: str | None = None,
) -> None:
    _write(
        path,
        "INSERT INTO memories (id, content, category, source, entity_ids, tenant_id, "
        "metadata, is_note, valid_from, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            memory_id,
            content,
            category,
            source,
            json.dumps(list(entity_ids)),
            tenant_id,
            json.dumps(metadata or {}),
            is_note,
            valid_from,
            _TS,
            _TS,
        ),
    )


def _add_image(path: Path, memory_id: str, tenant_id: str, image_path: str, rel: str) -> None:
    _add_memory(
        path,
        memory_id,
        f"Image file: {rel}",
        tenant_id,
        category="context",
        source="document",
        metadata={
            "path": image_path,
            "rel": rel,
            "ext": ".png",
            "size": 16,
            "collection": "test",
            "online_only": False,
            "index_mode": "metadata",
        },
    )


# ---------------------------------------------------------------------------
# Storage-backed fixtures (for the not-yet-implemented paths: storage stays
# real in their zero-value run)
# ---------------------------------------------------------------------------


def _store(path: Path) -> SqliteBackend:
    store = SqliteBackend(path)
    store.initialise()
    return store


def _memory(
    store: SqliteBackend,
    content: str,
    tenant_id: str,
    **fields: Any,
) -> MemoryRecord:
    return store.add_memory(
        MemoryRecord(
            content=content,
            category=MemoryCategory.FACT,
            tenant_id=tenant_id,
            **fields,
        )
    )


class _VisionRecordingStore(SqliteBackend):
    """Records the ``tenant_id`` passed by ``image_jobs`` to both selections."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self.tenant_calls: list[tuple[str, str | None]] = []

    def list_image_file_records(self, tenant_id: str | None = None) -> list[MemoryRecord]:
        self.tenant_calls.append(("list_image_file_records", tenant_id))
        return super().list_image_file_records(tenant_id=tenant_id)

    def get_annotating_descriptions(
        self, memory_id: str, cap: int, tenant_id: str | None = None
    ) -> list[MemoryRecord]:
        self.tenant_calls.append(("get_annotating_descriptions", tenant_id))
        return super().get_annotating_descriptions(memory_id, cap, tenant_id=tenant_id)


class _StubCaptioner:
    def describe(self, image: ImageInput) -> ImageDescription:
        return ImageDescription(
            record=MemoryRecord(
                content=f"described {image.file_id}",
                category=MemoryCategory.CONTEXT,
                source=MemorySource.DOCUMENT,
            ),
            file_id=image.file_id,
            source_image=image.path,
        )


class _DeactivatingAnchorStore(SqliteBackend):
    """Deactivates ``t1`` between the note insert and its anchor link."""

    def anchor_candidates(
        self, about: str, limit: int = 5, tenant_id: str | None = None
    ) -> list[tuple[float, MemoryRecord]]:
        candidates = super().anchor_candidates(about, limit, tenant_id=tenant_id)
        self.set_tenant_active("t1", False)
        return candidates


# ---------------------------------------------------------------------------
# 5.1 — create_note stamps and anchors in its tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-18514cb1")
def test_create_note_stamps_and_anchors_inside_its_tenant(tmp_path: Path) -> None:
    db = tmp_path / "mintmory.db"
    _init_db(db)
    _add_tenant(db, "t1")
    _add_memory(db, "global-target", "Tokyo trip plan", "global", entity_ids=("tokyo", "trip"))
    _add_memory(db, "t1-target", "Tokyo trip budget", "t1", entity_ids=("tokyo", "trip"))
    store = SqliteBackend(db)

    result = create_note(store, "book hotel", about="Tokyo trip", tenant_id="t1")

    notes = _fetch(db, "SELECT id, tenant_id, content FROM memories WHERE is_note = 1")
    assert [(row["tenant_id"], row["content"]) for row in notes] == [("t1", "book hotel")]
    links = _fetch(
        db,
        "SELECT source_memory_id, target_memory_id, tenant_id FROM concept_links "
        "WHERE link_type = 'annotates'",
    )
    assert len(links) == 1
    assert links[0]["source_memory_id"] == notes[0]["id"]
    assert links[0]["target_memory_id"] == "t1-target"
    assert links[0]["tenant_id"] == "t1"
    assert result is not None
    assert result.note.tenant_id == "t1"
    assert result.anchor_kind == "memory"
    assert result.anchor_memory_id == "t1-target"


# ---------------------------------------------------------------------------
# 5.2 — notes_list forwards the tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-abd8e186")
def test_notes_list_passes_the_tenant_to_the_storage(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    _memory(store, "Global note", "global", is_note=True)
    tenant_note = _memory(store, "Tenant note", "t1", is_note=True)

    notes = notes_list(store, tenant_id="t1")

    assert [note.id for note in notes] == [tenant_note.id]
    assert notes[0].content == "Tenant note"
    assert all(note.tenant_id == "t1" for note in notes)


# ---------------------------------------------------------------------------
# 5.3 — image_jobs lists only one tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3b007667")
def test_image_jobs_lists_only_the_requested_tenant(tmp_path: Path) -> None:
    db = tmp_path / "mintmory.db"
    _init_db(db)
    _add_tenant(db, "t1")
    _add_image(db, "global-image", "global", "/shared/global.png", "global.png")
    _add_image(db, "tenant-image", "t1", "/shared/tenant.png", "tenant.png")
    store = _VisionRecordingStore(db)

    jobs = image_jobs(store, tenant_id="t1")

    assert [job.file_id for job in jobs] == ["tenant-image"]
    assert jobs[0].path == "/shared/tenant.png"
    assert jobs[0].rel == "tenant.png"
    assert jobs[0].mime == "image/png"
    assert ("list_image_file_records", "t1") in store.tenant_calls
    assert ("get_annotating_descriptions", "t1") in store.tenant_calls
    assert all(tenant_id == "t1" for _, tenant_id in store.tenant_calls)


# ---------------------------------------------------------------------------
# 5.4 — image_caption_put / caption_pending_images stay inside one tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-5e505f8c")
def test_image_caption_put_resolves_and_writes_inside_the_tenant(tmp_path: Path) -> None:
    db = tmp_path / "mintmory.db"
    _init_db(db)
    _add_tenant(db, "t1")
    _add_image(db, "tenant-image", "t1", "/shared/photo.png", "photo.png")
    _add_image(db, "global-image", "global", "/shared/photo.png", "photo.png")
    store = SqliteBackend(db)

    image_caption_put(store, "tenant-image", "A tenant photo.", tenant_id="t1")

    rows = _fetch(
        db,
        "SELECT id, tenant_id, content FROM memories WHERE content = 'A tenant photo.'",
    )
    assert len(rows) == 1
    assert rows[0]["tenant_id"] == "t1"
    links = _fetch(
        db,
        "SELECT target_memory_id, tenant_id FROM concept_links WHERE source_memory_id = ?",
        (rows[0]["id"],),
    )
    assert [(link["target_memory_id"], link["tenant_id"]) for link in links] == [
        ("tenant-image", "t1")
    ]

    with pytest.raises(KeyError) as exc_info:
        image_caption_put(store, "global-image", "cross-tenant", tenant_id="t1")
    assert "no active image file-record found" in str(exc_info.value)


@pytest.mark.l4("C-5e505f8c")
def test_image_caption_put_archives_prior_description_inside_the_tenant(
    tmp_path: Path,
) -> None:
    db = tmp_path / "mintmory.db"
    _init_db(db)
    _add_tenant(db, "t1")
    _add_image(db, "tenant-image", "t1", "/shared/photo.png", "photo.png")
    store = SqliteBackend(db)

    image_caption_put(store, "tenant-image", "first caption", tenant_id="t1")
    first = _fetch(
        db, "SELECT tenant_id, is_archived FROM memories WHERE content = 'first caption'"
    )
    assert len(first) == 1
    assert first[0]["tenant_id"] == "t1"
    assert first[0]["is_archived"] == 0

    image_caption_put(store, "tenant-image", "second caption", tenant_id="t1")

    archived = _fetch(db, "SELECT is_archived FROM memories WHERE content = 'first caption'")
    assert archived[0]["is_archived"] == 1
    active = _fetch(
        db,
        "SELECT content FROM memories WHERE content = 'second caption' AND is_archived = 0",
    )
    assert [row["content"] for row in active] == ["second caption"]


@pytest.mark.l4("C-5e505f8c")
def test_caption_pending_images_forwards_the_tenant(tmp_path: Path) -> None:
    db = tmp_path / "mintmory.db"
    _init_db(db)
    _add_tenant(db, "t1")
    tenant_file = tmp_path / "tenant.png"
    tenant_file.write_bytes(b"tenant-image-bytes")
    global_file = tmp_path / "global.png"
    global_file.write_bytes(b"global-image-bytes")
    _add_image(db, "tenant-image", "t1", str(tenant_file), "tenant.png")
    _add_image(db, "global-image", "global", str(global_file), "global.png")
    store = SqliteBackend(db)

    report = caption_pending_images(store, captioner=_StubCaptioner(), tenant_id="t1")

    descriptions = _fetch(
        db,
        "SELECT tenant_id, content FROM memories "
        "WHERE json_extract(metadata, '$.kind') = 'image_description'",
    )
    assert [(row["tenant_id"], row["content"]) for row in descriptions] == [
        ("t1", "described tenant-image")
    ]
    assert report is not None
    assert report.described == 1
    assert [(item.file_id, item.status) for item in report.items] == [("tenant-image", "described")]


# ---------------------------------------------------------------------------
# 5.5 — apply_feedback validates everything before the first score change
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-5d0cf777")
def test_apply_feedback_scoped_rejects_a_foreign_session_before_scoring(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    global_memory = _memory(store, "global fact", "global")
    global_session = store.create_session(
        QuerySession(query_text="global query", tenant_id="global")
    )

    with pytest.raises(ValueError) as exc_info:
        apply_feedback(store, global_session.id, [global_memory.id], [], tenant_id="t1")
    assert str(exc_info.value) == f"session {global_session.id!r} not found"
    global_fetched = store.get_memory(global_memory.id)
    assert global_fetched is not None
    assert global_fetched.usefulness_score == 0.0

    tenant_memory = _memory(store, "t1 fact", "t1")
    tenant_session = store.create_session(QuerySession(query_text="t1 query", tenant_id="t1"))
    apply_feedback(store, tenant_session.id, [tenant_memory.id], [], tenant_id="t1")
    refreshed = store.get_session(tenant_session.id, tenant_id="t1")
    assert refreshed is not None
    assert refreshed.concluded is True
    tenant_fetched = store.get_memory(tenant_memory.id, tenant_id="t1")
    assert tenant_fetched is not None
    assert tenant_fetched.usefulness_score == pytest.approx(0.5)


@pytest.mark.l4("C-5d0cf777")
def test_apply_feedback_scoped_validates_every_id_before_scoring(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t1")
    tenant_memory = _memory(store, "t1 fact", "t1")
    global_memory = _memory(store, "global fact", "global")
    tenant_session = store.create_session(QuerySession(query_text="t1 query", tenant_id="t1"))

    with pytest.raises(ValueError) as exc_info:
        apply_feedback(
            store,
            tenant_session.id,
            [tenant_memory.id, global_memory.id],
            [],
            tenant_id="t1",
        )
    assert str(exc_info.value) == f"memory {global_memory.id!r} not found"
    tenant_fetched = store.get_memory(tenant_memory.id, tenant_id="t1")
    assert tenant_fetched is not None
    assert tenant_fetched.usefulness_score == 0.0
    session = store.get_session(tenant_session.id, tenant_id="t1")
    assert session is not None
    assert session.concluded is False


@pytest.mark.l4("C-5d0cf777")
def test_apply_feedback_scoped_rejects_an_inactive_session_tenant(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    store.create_tenant("t2")
    _memory(store, "t2 fact", "t2")
    session = store.create_session(QuerySession(query_text="t2 query", tenant_id="t2"))
    store.set_tenant_active("t2", False)

    with pytest.raises(TenantInactiveError) as exc_info:
        apply_feedback(store, session.id, [], [], tenant_id="t2")
    assert exc_info.value.tenant_id == "t2"


# ---------------------------------------------------------------------------
# 5.6 — cochange reads are tenant-confined
# ---------------------------------------------------------------------------


def _seed_cochange(store: SqliteBackend) -> None:
    store.create_tenant("t1")
    for tenant_id, prefix in (("global", "g"), ("t1", "t")):
        _memory(
            store,
            f"{prefix} document",
            tenant_id,
            id=f"{prefix}-doc",
            source=MemorySource.DOCUMENT,
            valid_from=datetime(2026, 1, 1),
            metadata={
                "path": "/shared/doc.txt",
                "rel": f"{prefix}-doc.txt",
                "collection": "lib",
                "changeset_id": f"{prefix}-changeset",
                "changeset_observed_at": "2026-01-02T00:00:00",
                "changeset_kind": "incremental",
            },
        )
        _memory(
            store,
            f"{prefix} peer",
            tenant_id,
            id=f"{prefix}-peer",
            source=MemorySource.DOCUMENT,
            valid_from=datetime(2026, 1, 2),
            metadata={
                "path": f"/shared/{prefix}-peer.txt",
                "rel": f"{prefix}-peer.txt",
                "collection": "lib",
                "changeset_id": f"{prefix}-changeset",
                "changeset_observed_at": "2026-01-02T00:00:00",
                "changeset_kind": "incremental",
            },
        )
        store.add_link(
            ConceptLink(
                source_memory_id=f"{prefix}-doc",
                target_memory_id=f"{prefix}-peer",
                link_type=ConceptLinkType.RELATES_TO,
                entity=f"changeset:{prefix}-changeset",
                strength=0.75,
                confidence=0.75,
                source=LinkSource.INFERENCE,
                tenant_id=tenant_id,
            )
        )


@pytest.mark.l4("C-aa16078a")
def test_changed_with_is_confined_to_the_tenant(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    _seed_cochange(store)

    peers = cochange.changed_with(store, "/shared/doc.txt", tenant_id="t1")

    assert [peer["path"] for peer in peers] == ["/shared/t-peer.txt"]
    assert peers[0]["strength"] == pytest.approx(0.75)
    assert peers[0]["observed_at"] == "2026-01-02T00:00:00"
    assert peers[0]["kind"] == "incremental"


@pytest.mark.l4("C-aa16078a")
def test_documents_timeline_is_confined_to_the_tenant(tmp_path: Path) -> None:
    store = _store(tmp_path / "mintmory.db")
    _seed_cochange(store)

    timeline = cochange.documents_timeline(store, tenant_id="t1")

    assert [entry["path"] for entry in timeline] == [
        "/shared/t-peer.txt",
        "/shared/doc.txt",
    ]
    assert {entry["collection"] for entry in timeline} == {"lib"}
    assert {entry["date"] for entry in timeline} == {"2026-01-01", "2026-01-02"}


# ---------------------------------------------------------------------------
# 5.8 — multi-step creates stay non-atomic
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-e138c61a")
def test_create_note_leaves_the_note_when_the_tenant_is_deactivated_mid_run(
    tmp_path: Path,
) -> None:
    store = _DeactivatingAnchorStore(tmp_path / "mintmory.db")
    store.initialise()
    store.create_tenant("t1")
    _memory(store, "Tokyo trip budget", "t1", entity_ids=["tokyo", "trip"])

    with pytest.raises(TenantInactiveError):
        create_note(store, "book hotel", about="Tokyo trip", tenant_id="t1")

    rows = store.connect().execute("SELECT tenant_id, is_note FROM memories").fetchall()
    notes = [row for row in rows if row["is_note"] == 1]
    assert len(notes) == 1
    assert notes[0]["tenant_id"] == "t1"
    link_count = (
        store.connect()
        .execute("SELECT count(*) FROM concept_links WHERE link_type = 'annotates'")
        .fetchone()[0]
    )
    assert link_count == 0
