"""
Route tests for the MintMory HTTP API.

Each test runs against a fresh temp SQLite DB (never ``~/.mintmory``): the
``client`` fixture points ``MINTMORY_DB`` at a ``tmp_path`` file, resets the
module-level ``_store`` cache, and drives the app through a ``TestClient``
context manager so the lifespan opens/closes the store.

Conformance: every JSON response is validated by constructing the matching
``types.py`` model from it (``MemoryRecord(**resp.json())`` etc.). Since the
OpenAPI spec is derived from ``types.py``, a successful round-trip through the
canonical model is a dependency-free proxy for OpenAPI conformance.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from mintmory.api import app as app_module
from mintmory.core.types import (
    ConceptLink,
    DreamReport,
    ImageDescription,
    ImageJob,
    MemoryRecord,
    MemoryStats,
    MemorySummary,
    NoteResult,
    QuerySession,
    SearchResponse,
    SummaryJob,
)


@pytest.fixture
def client(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """A TestClient backed by a throwaway DB, with the global store reset."""
    db_file = tmp_path / "api_test.db"  # type: ignore[operator]
    monkeypatch.setenv("MINTMORY_DB", str(db_file))
    # Reset any cached global store from a previous test/run.
    monkeypatch.setattr(app_module, "_store", None)
    with TestClient(app_module.app) as test_client:
        yield test_client
    monkeypatch.setattr(app_module, "_store", None)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _create_memory(client: TestClient, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "content": "The Acme parking integration uses OAuth 2.0 with PKCE.",
        "category": "fact",
    }
    body.update(overrides)
    resp = client.post("/memories", json=body)
    assert resp.status_code == 201, resp.text
    data: dict[str, object] = resp.json()
    return data


# ---------------------------------------------------------------------------
# Memories — create / get round-trip
# ---------------------------------------------------------------------------


def test_add_memory_returns_201_and_conformant_record(client: TestClient) -> None:
    resp = client.post(
        "/memories",
        json={
            "content": "User prefers dark mode in the dashboard.",
            "category": "preference",
            "source": "user",
            "confidence": 0.9,
            "verified": True,
            "metadata": {"project_id": "acme"},
        },
    )
    assert resp.status_code == 201, resp.text
    record = MemoryRecord(**resp.json())  # OpenAPI-conformance proxy
    assert record.content == "User prefers dark mode in the dashboard."
    assert record.category.value == "preference"
    assert record.source.value == "user"
    assert record.confidence == 0.9
    assert record.verified is True
    assert record.metadata == {"project_id": "acme"}
    # Server-side defaults / derived fields.
    assert record.is_active is True
    assert record.is_archived is False
    assert record.usefulness_score == 0.0


def test_add_then_get_round_trip_preserves_content(client: TestClient) -> None:
    created = _create_memory(client)
    memory_id = created["id"]

    resp = client.get(f"/memories/{memory_id}")
    assert resp.status_code == 200, resp.text
    fetched = MemoryRecord(**resp.json())
    assert fetched.id == memory_id
    assert fetched.content == created["content"]
    assert fetched.category.value == "fact"


def test_add_memory_runs_entity_extraction(client: TestClient) -> None:
    created = _create_memory(client)
    # Entity extraction should populate entity_ids server-side.
    assert isinstance(created["entity_ids"], list)
    assert created["entity_ids"], "expected at least one extracted entity"


def test_add_memory_rejects_missing_required_field(client: TestClient) -> None:
    resp = client.post("/memories", json={"content": "no category here"})
    assert resp.status_code == 422


def test_add_memory_rejects_bad_category(client: TestClient) -> None:
    resp = client.post("/memories", json={"content": "bad cat", "category": "not_a_category"})
    assert resp.status_code == 422


def test_get_missing_memory_returns_404(client: TestClient) -> None:
    resp = client.get("/memories/does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Memories — PATCH
# ---------------------------------------------------------------------------


def test_patch_updates_fields_and_returns_record(client: TestClient) -> None:
    created = _create_memory(client)
    memory_id = created["id"]

    resp = client.patch(
        f"/memories/{memory_id}",
        json={"verified": True, "confidence": 0.5},
    )
    assert resp.status_code == 200, resp.text
    updated = MemoryRecord(**resp.json())
    assert updated.verified is True
    assert updated.confidence == 0.5
    # Unchanged fields preserved.
    assert updated.content == created["content"]


def test_patch_content_triggers_entity_reextraction(client: TestClient) -> None:
    created = _create_memory(client)
    memory_id = created["id"]
    resp = client.patch(
        f"/memories/{memory_id}",
        json={"content": "Acme Corp deployed Kubernetes on GCP."},
    )
    assert resp.status_code == 200, resp.text
    updated = MemoryRecord(**resp.json())
    assert updated.content == "Acme Corp deployed Kubernetes on GCP."


def test_patch_missing_memory_returns_404(client: TestClient) -> None:
    resp = client.patch("/memories/nope", json={"verified": True})
    assert resp.status_code == 404


def test_patch_with_empty_body_returns_422(client: TestClient) -> None:
    created = _create_memory(client)
    resp = client.patch(f"/memories/{created['id']}", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Memories — DELETE (archive)
# ---------------------------------------------------------------------------


def test_delete_archives_and_returns_204(client: TestClient) -> None:
    created = _create_memory(client)
    memory_id = created["id"]

    resp = client.delete(f"/memories/{memory_id}")
    assert resp.status_code == 204
    assert resp.content == b""

    # Record is retained but archived.
    fetched = client.get(f"/memories/{memory_id}")
    assert fetched.status_code == 200
    record = MemoryRecord(**fetched.json())
    assert record.is_archived is True
    assert record.is_active is False


def test_delete_missing_memory_returns_404(client: TestClient) -> None:
    resp = client.delete("/memories/missing")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_returns_searchresponse_shape(client: TestClient) -> None:
    _create_memory(client, content="OAuth 2.0 parking integration with PKCE flow.")
    _create_memory(client, content="The weather in Cluj is sunny today.")

    resp = client.post("/memories/search", json={"query": "OAuth parking", "limit": 5})
    assert resp.status_code == 200, resp.text
    parsed = SearchResponse(**resp.json())  # conformance
    assert parsed.session_id
    assert parsed.total_found == len(parsed.memories)
    # FTS should surface the OAuth memory.
    contents = [m.content for m in parsed.memories]
    assert any("OAuth" in c for c in contents)


def test_search_session_is_retrievable(client: TestClient) -> None:
    _create_memory(client, content="OAuth integration details.")
    resp = client.post("/memories/search", json={"query": "OAuth"})
    session_id = SearchResponse(**resp.json()).session_id

    session_resp = client.get(f"/sessions/{session_id}")
    assert session_resp.status_code == 200
    session = QuerySession(**session_resp.json())
    assert session.id == session_id
    assert session.concluded is False


def test_search_rejects_empty_query(client: TestClient) -> None:
    resp = client.post("/memories/search", json={"query": ""})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


def test_create_link_and_list(client: TestClient) -> None:
    src = _create_memory(client, content="OAuth 2.0 is used for auth.")
    tgt = _create_memory(client, content="PKCE is required for OAuth.")

    resp = client.post(
        f"/memories/{src['id']}/links",
        json={
            "target_memory_id": tgt["id"],
            "link_type": "depends_on",
            "entity": "OAuth 2.0",
            "strength": 0.8,
        },
    )
    assert resp.status_code == 201, resp.text
    link = ConceptLink(**resp.json())  # conformance
    assert link.source_memory_id == src["id"]
    assert link.target_memory_id == tgt["id"]
    assert link.link_type.value == "depends_on"
    assert link.source.value == "user"

    # The link is listed for the source memory.
    listed = client.get(f"/memories/{src['id']}/links")
    assert listed.status_code == 200
    links = [ConceptLink(**item) for item in listed.json()]
    assert any(item.id == link.id for item in links)


def test_create_symmetric_link_creates_reverse(client: TestClient) -> None:
    src = _create_memory(client, content="Fact A about widgets.")
    tgt = _create_memory(client, content="Fact B about widgets.")

    resp = client.post(
        f"/memories/{src['id']}/links",
        json={"target_memory_id": tgt["id"], "link_type": "relates_to"},
    )
    assert resp.status_code == 201, resp.text

    # The reverse link is visible from the target memory's perspective.
    tgt_links = client.get(f"/memories/{tgt['id']}/links")
    assert tgt_links.status_code == 200
    reverse = [
        ConceptLink(**item)
        for item in tgt_links.json()
        if item["source_memory_id"] == tgt["id"] and item["target_memory_id"] == src["id"]
    ]
    assert reverse, "expected a reverse link for the symmetric type"


def test_get_links_min_strength_filter(client: TestClient) -> None:
    src = _create_memory(client, content="Source memory.")
    tgt = _create_memory(client, content="Target memory.")
    client.post(
        f"/memories/{src['id']}/links",
        json={"target_memory_id": tgt["id"], "link_type": "uses", "strength": 0.2},
    )
    resp = client.get(f"/memories/{src['id']}/links", params={"min_strength": 0.5})
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_links_filter_by_type(client: TestClient) -> None:
    src = _create_memory(client, content="Source memory two.")
    tgt = _create_memory(client, content="Target memory two.")
    client.post(
        f"/memories/{src['id']}/links",
        json={"target_memory_id": tgt["id"], "link_type": "uses"},
    )
    resp = client.get(f"/memories/{src['id']}/links", params={"link_type": "before"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_link_source_not_found_404(client: TestClient) -> None:
    tgt = _create_memory(client)
    resp = client.post(
        "/memories/missing-src/links",
        json={"target_memory_id": tgt["id"], "link_type": "uses"},
    )
    assert resp.status_code == 404


def test_create_link_target_not_found_404(client: TestClient) -> None:
    src = _create_memory(client)
    resp = client.post(
        f"/memories/{src['id']}/links",
        json={"target_memory_id": "missing-tgt", "link_type": "uses"},
    )
    assert resp.status_code == 404


def test_create_self_link_returns_422(client: TestClient) -> None:
    src = _create_memory(client)
    resp = client.post(
        f"/memories/{src['id']}/links",
        json={"target_memory_id": src["id"], "link_type": "uses"},
    )
    assert resp.status_code == 422


def test_get_links_missing_memory_404(client: TestClient) -> None:
    resp = client.get("/memories/missing/links")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Dream
# ---------------------------------------------------------------------------


def test_dream_light_returns_report(client: TestClient) -> None:
    _create_memory(client, content="OAuth 2.0 memory one.")
    _create_memory(client, content="OAuth 2.0 memory two.")

    resp = client.post("/dream", json={"intensity": "light"})
    assert resp.status_code == 200, resp.text
    report = DreamReport(**resp.json())  # conformance
    assert report.intensity.value == "light"
    assert report.duration_ms >= 0.0
    assert report.anomalies is not None


def test_dream_full_returns_report(client: TestClient) -> None:
    _create_memory(client, content="Memory for full dream.")
    resp = client.post("/dream", json={"intensity": "full"})
    assert resp.status_code == 200, resp.text
    report = DreamReport(**resp.json())
    assert report.intensity.value == "full"


def test_dream_rejects_bad_intensity(client: TestClient) -> None:
    resp = client.post("/dream", json={"intensity": "deep"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Sessions — feedback
# ---------------------------------------------------------------------------


def test_session_feedback_applies_and_concludes(client: TestClient) -> None:
    mem = _create_memory(client, content="OAuth feedback memory.")
    search = client.post("/memories/search", json={"query": "OAuth"})
    session_id = SearchResponse(**search.json()).session_id

    resp = client.post(
        f"/sessions/{session_id}/feedback",
        json={
            "confidence_rating": 4,
            "useful_ids": [mem["id"]],
            "stale_ids": [],
            "reasoning": "It directly answered the question.",
        },
    )
    assert resp.status_code == 200, resp.text
    session = QuerySession(**resp.json())  # conformance
    assert session.concluded is True
    assert session.confidence_rating == 4
    assert session.useful_ids == [mem["id"]]

    # The useful memory got reinforced.
    updated = MemoryRecord(**client.get(f"/memories/{mem['id']}").json())
    assert updated.usefulness_score > 0.0
    assert updated.reinforcement_count == 1


def test_session_feedback_already_concluded_returns_409(client: TestClient) -> None:
    mem = _create_memory(client, content="Conflict feedback memory.")
    search = client.post("/memories/search", json={"query": "Conflict"})
    session_id = SearchResponse(**search.json()).session_id

    payload = {"confidence_rating": 3, "useful_ids": [mem["id"]], "stale_ids": []}
    first = client.post(f"/sessions/{session_id}/feedback", json=payload)
    assert first.status_code == 200
    second = client.post(f"/sessions/{session_id}/feedback", json=payload)
    assert second.status_code == 409


def test_session_feedback_missing_session_returns_404(client: TestClient) -> None:
    resp = client.post(
        "/sessions/nope/feedback",
        json={"confidence_rating": 3, "useful_ids": [], "stale_ids": []},
    )
    assert resp.status_code == 404


def test_session_feedback_rejects_bad_confidence(client: TestClient) -> None:
    search = client.post("/memories/search", json={"query": "anything"})
    session_id = SearchResponse(**search.json()).session_id
    resp = client.post(
        f"/sessions/{session_id}/feedback",
        json={"confidence_rating": 9, "useful_ids": [], "stale_ids": []},
    )
    assert resp.status_code == 422


def test_get_missing_session_returns_404(client: TestClient) -> None:
    resp = client.get("/sessions/missing")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Stats & summaries
# ---------------------------------------------------------------------------


def test_stats_returns_conformant_shape(client: TestClient) -> None:
    _create_memory(client)
    resp = client.get("/stats")
    assert resp.status_code == 200, resp.text
    stats = MemoryStats(**resp.json())  # conformance
    assert stats.total_memories >= 1
    assert stats.active >= 1


def test_list_summaries_empty_by_default(client: TestClient) -> None:
    resp = client.get("/summaries")
    assert resp.status_code == 200
    assert resp.json() == []


def test_summaries_round_trip_via_dreaming(client: TestClient) -> None:
    # No summarizer is injected by the API, so dreaming creates none — the
    # summary endpoints still return well-formed (empty / 404) responses.
    client.post("/dream", json={"intensity": "light"})
    listed = client.get("/summaries", params={"include_stale": True})
    assert listed.status_code == 200
    summaries = [MemorySummary(**item) for item in listed.json()]
    assert summaries == []

    missing = client.get("/summaries/OAuth%202.0")
    assert missing.status_code == 404


def test_get_summary_happy_path_and_stale_filter(client: TestClient) -> None:
    # Summaries are produced only by dreaming with an injected summarizer, which
    # the HTTP surface never wires up. Seed two summaries directly through the
    # live store (inside the running lifespan) to exercise the read endpoints'
    # happy path and the include_stale filter.
    store = app_module.get_store()
    store.upsert_summary(
        MemorySummary(
            concept="OAuth 2.0",
            summary_text="OAuth 2.0 is used with PKCE across services.",
            memory_count=3,
            is_current=True,
        )
    )
    store.upsert_summary(
        MemorySummary(
            concept="Legacy SDK",
            summary_text="The legacy SDK is deprecated.",
            memory_count=2,
            is_current=False,
        )
    )

    # GET /summaries/{concept} happy path.
    resp = client.get("/summaries/OAuth%202.0")
    assert resp.status_code == 200, resp.text
    summary = MemorySummary(**resp.json())  # conformance
    assert summary.concept == "OAuth 2.0"
    assert summary.memory_count == 3
    assert summary.is_current is True

    # Default list excludes the non-current summary.
    default_list = client.get("/summaries")
    assert default_list.status_code == 200
    concepts = {item["concept"] for item in default_list.json()}
    assert concepts == {"OAuth 2.0"}

    # include_stale=True surfaces both.
    full_list = client.get("/summaries", params={"include_stale": True})
    assert full_list.status_code == 200
    all_concepts = {item["concept"] for item in full_list.json()}
    assert all_concepts == {"OAuth 2.0", "Legacy SDK"}


def test_get_store_raises_without_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    # Defensive: get_store() outside a running lifespan must raise.
    monkeypatch.setattr(app_module, "_store", None)
    with pytest.raises(RuntimeError):
        app_module.get_store()


# ---------------------------------------------------------------------------
# Notes — POST /notes
# ---------------------------------------------------------------------------


def test_post_notes_returns_201_and_conformant_note_result(client: TestClient) -> None:
    """POST /notes with content only must return 201 and a valid NoteResult."""
    resp = client.post(
        "/notes",
        json={"content": "Remember to renew the server TLS certificate before Q1 2027."},
    )
    assert resp.status_code == 201, resp.text
    result = NoteResult(**resp.json())  # OpenAPI-conformance proxy
    assert result.note.is_note is True
    assert result.anchor_kind == "none"
    assert result.anchor_memory_id is None
    assert result.anchor_phrase is None


def test_post_notes_idempotent_second_call_is_also_201(client: TestClient) -> None:
    """Each POST /notes call creates a new note and returns 201 (not 200)."""
    body = {"content": "Buy oat milk."}
    r1 = client.post("/notes", json=body)
    r2 = client.post("/notes", json=body)
    assert r1.status_code == 201
    assert r2.status_code == 201
    # Two separate notes are created (different ids).
    assert NoteResult(**r1.json()).note.id != NoteResult(**r2.json()).note.id


def test_post_notes_with_when_stores_valid_from(client: TestClient) -> None:
    """POST /notes with 'when' must set valid_from on the note record."""
    resp = client.post(
        "/notes",
        json={"content": "Team hackathon.", "when": "2026-11-10T09:00:00"},
    )
    assert resp.status_code == 201, resp.text
    result = NoteResult(**resp.json())
    assert result.note.valid_from is not None
    assert result.note.category.value == "temporal"


def test_post_notes_with_about_sets_anchor_phrase(client: TestClient) -> None:
    """POST /notes with 'about' must set anchor_phrase on the returned NoteResult."""
    resp = client.post(
        "/notes",
        json={
            "content": "Pack adapters for the trip.",
            "about": "Japan travel",
        },
    )
    assert resp.status_code == 201, resp.text
    result = NoteResult(**resp.json())
    assert result.anchor_phrase == "Japan travel"
    assert result.anchor_kind in {"memory", "topic", "none"}


def test_post_notes_missing_content_returns_422(client: TestClient) -> None:
    """POST /notes without 'content' must return 422 (validation error)."""
    resp = client.post("/notes", json={"about": "something"})
    assert resp.status_code == 422


def test_post_notes_empty_content_returns_422(client: TestClient) -> None:
    """POST /notes with empty content (min_length=1 violated) must return 422."""
    resp = client.post("/notes", json={"content": "", "category": "episodic"})
    assert resp.status_code == 422


def test_post_notes_invalid_category_returns_422(client: TestClient) -> None:
    """POST /notes with an unrecognised category enum value must return 422."""
    resp = client.post("/notes", json={"content": "Some note.", "category": "not_a_category"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Notes — GET /notes
# ---------------------------------------------------------------------------


def test_get_notes_empty_returns_200_and_empty_list(client: TestClient) -> None:
    """GET /notes on a store with no notes must return 200 with []."""
    resp = client.get("/notes")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_get_notes_returns_only_is_note_records(client: TestClient) -> None:
    """GET /notes must exclude plain (non-note) memories."""
    # Add a plain memory.
    _create_memory(client, content="A plain memory, not a note.")
    # Add a note via the notes route.
    client.post("/notes", json={"content": "A genuine user note."})
    resp = client.get("/notes")
    assert resp.status_code == 200, resp.text
    records = [MemoryRecord(**item) for item in resp.json()]
    assert len(records) == 1
    assert records[0].is_note is True


def test_get_notes_upcoming_filter(client: TestClient) -> None:
    """GET /notes?upcoming=true returns only notes with valid_from in the future."""
    client.post("/notes", json={"content": "Far future note.", "when": "2099-12-31T00:00:00"})
    client.post("/notes", json={"content": "Undated note."})
    resp = client.get("/notes", params={"upcoming": True})
    assert resp.status_code == 200, resp.text
    records = [MemoryRecord(**item) for item in resp.json()]
    assert len(records) >= 1
    for rec in records:
        assert rec.valid_from is not None


def test_get_notes_overdue_filter(client: TestClient) -> None:
    """GET /notes?overdue=true returns only notes with valid_from in the past."""
    client.post("/notes", json={"content": "Past task.", "when": "2020-03-01T00:00:00"})
    client.post("/notes", json={"content": "Future task.", "when": "2099-06-01T00:00:00"})
    resp = client.get("/notes", params={"overdue": True})
    assert resp.status_code == 200, resp.text
    records = [MemoryRecord(**item) for item in resp.json()]
    assert len(records) >= 1


def test_get_notes_both_flags_returns_422(client: TestClient) -> None:
    """GET /notes with both upcoming=true and overdue=true must return 422."""
    resp = client.get("/notes", params={"upcoming": True, "overdue": True})
    assert resp.status_code == 422


def test_get_notes_limit_param(client: TestClient) -> None:
    """GET /notes?limit=2 caps the number of returned notes."""
    for i in range(5):
        client.post("/notes", json={"content": f"Note {i} for limit test."})
    resp = client.get("/notes", params={"limit": 2})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) <= 2


def test_get_notes_note_result_conforms_to_memory_record(client: TestClient) -> None:
    """Each item returned by GET /notes must parse as a valid MemoryRecord."""
    client.post("/notes", json={"content": "Conformance check note."})
    resp = client.get("/notes")
    assert resp.status_code == 200, resp.text
    for item in resp.json():
        record = MemoryRecord(**item)
        assert record.is_note is True


# ---------------------------------------------------------------------------
# GET /summaries/jobs — agent-supplied L3
# ---------------------------------------------------------------------------


def test_get_summary_jobs_returns_200_not_shadowed_by_concept(client: TestClient) -> None:
    """GET /summaries/jobs must return 200 (not a 404 from the {concept} handler)."""
    resp = client.get("/summaries/jobs")
    assert resp.status_code == 200, resp.text


def test_get_summary_jobs_empty_db_returns_empty_list(client: TestClient) -> None:
    """With no qualifying concepts the response is an empty JSON array."""
    resp = client.get("/summaries/jobs")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_get_summary_jobs_conforms_to_summary_job_model(client: TestClient) -> None:
    """Each element returned by GET /summaries/jobs must parse as a SummaryJob."""
    # A fresh DB has no qualifying concepts so the list is empty; we still assert
    # the shape contract by confirming list[SummaryJob] parses without error.
    resp = client.get("/summaries/jobs")
    assert resp.status_code == 200, resp.text
    jobs = [SummaryJob(**item) for item in resp.json()]
    assert jobs == []


def test_get_summary_jobs_include_all_param_accepted(client: TestClient) -> None:
    """include_all=true query parameter must be accepted (no 422)."""
    resp = client.get("/summaries/jobs", params={"include_all": "true"})
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


def test_get_summary_jobs_include_all_false_default(client: TestClient) -> None:
    """include_all defaults to false; the query param is optional."""
    resp = client.get("/summaries/jobs")
    assert resp.status_code == 200, resp.text
    # No assertion on contents here — just status and type.
    assert isinstance(resp.json(), list)


def test_get_summary_jobs_limit_param_accepted(client: TestClient) -> None:
    """limit=0 (no cap) and limit=2 are both valid query params."""
    for limit_val in ("0", "2"):
        resp = client.get("/summaries/jobs", params={"limit": limit_val})
        assert resp.status_code == 200, resp.text
        assert isinstance(resp.json(), list)


def test_get_summary_jobs_limit_negative_rejected(client: TestClient) -> None:
    """limit < 0 must return 422 (ge=0 constraint)."""
    resp = client.get("/summaries/jobs", params={"limit": "-1"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /summaries/{concept} — agent-supplied L3
# ---------------------------------------------------------------------------


def test_put_summary_returns_200_and_conformant_memory_summary(client: TestClient) -> None:
    """PUT /summaries/{concept} returns 200 and a valid MemorySummary."""
    resp = client.put(
        "/summaries/alphaplatform",
        json={"summary_text": "Alpha platform handles routing."},
    )
    assert resp.status_code == 200, resp.text
    summary = MemorySummary(**resp.json())  # OpenAPI-conformance proxy
    assert summary.concept == "alphaplatform"
    assert summary.summary_text == "Alpha platform handles routing."
    assert summary.is_current is True
    assert isinstance(summary.memory_count, int)


def test_put_summary_text_stored_verbatim(client: TestClient) -> None:
    """The summary text is stored verbatim (no stripping of prose)."""
    text = "  Beta platform: fast, reliable, and scalable.  "
    resp = client.put("/summaries/betaplatform", json={"summary_text": text})
    assert resp.status_code == 200, resp.text
    # apply_summary strips nothing — text stored verbatim as sent.
    assert resp.json()["summary_text"] == text


def test_put_summary_visible_via_get_summary(client: TestClient) -> None:
    """After PUT /summaries/{concept}, GET /summaries/{concept} returns the stored summary."""
    client.put(
        "/summaries/gammaplatform",
        json={"summary_text": "Gamma platform powers analytics."},
    )
    resp = client.get("/summaries/gammaplatform")
    assert resp.status_code == 200, resp.text
    summary = MemorySummary(**resp.json())
    assert summary.concept == "gammaplatform"
    assert summary.summary_text == "Gamma platform powers analytics."


def test_put_summary_round_trip_then_list(client: TestClient) -> None:
    """PUT then GET /summaries shows the concept in the default listing."""
    client.put("/summaries/deltaplatform", json={"summary_text": "Delta platform is offline."})
    listed = client.get("/summaries")
    assert listed.status_code == 200
    concepts = {item["concept"] for item in listed.json()}
    assert "deltaplatform" in concepts


def test_put_summary_idempotent_overwrite(client: TestClient) -> None:
    """PUT twice for the same concept overwrites (INSERT OR REPLACE semantics)."""
    client.put("/summaries/epsilonplatform", json={"summary_text": "First summary."})
    resp2 = client.put("/summaries/epsilonplatform", json={"summary_text": "Second summary."})
    assert resp2.status_code == 200
    assert resp2.json()["summary_text"] == "Second summary."

    # Only one record in the list for this concept.
    listed = client.get("/summaries")
    matching = [item for item in listed.json() if item["concept"] == "epsilonplatform"]
    assert len(matching) == 1


def test_put_summary_empty_text_returns_422(client: TestClient) -> None:
    """summary_text with empty string violates min_length=1 -> 422."""
    resp = client.put("/summaries/zetaplatform", json={"summary_text": ""})
    assert resp.status_code == 422


def test_put_summary_missing_body_returns_422(client: TestClient) -> None:
    """PUT without a body returns 422 (summary_text is required)."""
    resp = client.put("/summaries/etaplatform", json={})
    assert resp.status_code == 422


def test_put_summary_works_without_llm_backend(client: TestClient) -> None:
    """PUT /summaries/{concept} succeeds with no LLM configured (provider=none default)."""
    # The test fixture never sets MINTMORY_LLM_* -> provider=none.
    resp = client.put("/summaries/thetaplatform", json={"summary_text": "No LLM needed."})
    assert resp.status_code == 200


def test_get_summary_jobs_after_put_does_not_resurface_concept(client: TestClient) -> None:
    """Incremental rule: after PUT, jobs (default) must NOT re-surface the concept
    on an unchanged DB (stored memory_count 0 == current active count 0)."""
    client.put("/summaries/iotaplatform", json={"summary_text": "Iota platform syncs data."})
    resp = client.get("/summaries/jobs")
    assert resp.status_code == 200, resp.text
    concepts = [item["concept"] for item in resp.json()]
    assert "iotaplatform" not in concepts


def test_get_summary_jobs_not_shadowed_by_concept_handler(client: TestClient) -> None:
    """GET /summaries/jobs must not 404 via the GET /summaries/{concept} handler.

    The literal path /summaries/jobs must resolve before the parametrised
    /summaries/{concept} route — verifying the FastAPI route-ordering contract
    required by design §5c.
    """
    # Seed a summary for 'jobs' as a concept to make the collision scenario realistic.
    client.put("/summaries/jobs", json={"summary_text": "This is the concept named jobs."})

    # GET /summaries/jobs must still return the list (200), not the concept summary.
    resp = client.get("/summaries/jobs")
    assert resp.status_code == 200, resp.text
    # The response must be a list (array), not the MemorySummary dict for 'jobs'.
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# Images — GET /images/jobs + PUT /images/{file_id}
# ---------------------------------------------------------------------------


def _seed_image_file_record(
    client: TestClient,
    *,
    rel: str = "photos/sample.png",
    path: str = "/tmp/photos/sample.png",  # noqa: S108 — test-only, no real file
    ext: str = ".png",
) -> str:
    """Seed a synthetic image file-record via POST /memories and return its id.

    Replicates the metadata shape ``index-tree`` writes so that ``image_jobs``
    discovers it.  No real file needs to exist for the discovery tests.
    """
    resp = client.post(
        "/memories",
        json={
            "content": f"[image] {rel}",
            "category": "context",
            "source": "document",
            "metadata": {
                "collection": "test-lib",
                "path": path,
                "rel": rel,
                "ext": ext,
                "size": 1024,
                "mtime": 1_700_000_000.0,
                "online_only": False,
                "folder": rel.rsplit("/", 1)[0] if "/" in rel else ".",
                "index_mode": "vision",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    file_id: str = resp.json()["id"]
    assert file_id
    return file_id


def test_get_image_jobs_returns_200_on_empty_db(client: TestClient) -> None:
    """GET /images/jobs returns 200 and an empty list on a fresh DB."""
    resp = client.get("/images/jobs")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_get_image_jobs_conforms_to_image_job_model(client: TestClient) -> None:
    """Each element from GET /images/jobs must parse as an ImageJob."""
    resp = client.get("/images/jobs")
    assert resp.status_code == 200, resp.text
    jobs = [ImageJob(**item) for item in resp.json()]
    assert jobs == []


def test_get_image_jobs_query_params_accepted(client: TestClient) -> None:
    """include_all, include_bytes, and limit query params are accepted without 422."""
    for params in (
        {},
        {"include_all": "true"},
        {"include_bytes": "true"},
        {"limit": "5"},
        {"include_all": "false", "limit": "0"},
    ):
        resp = client.get("/images/jobs", params=params)
        assert resp.status_code == 200, f"params={params!r}: {resp.text}"
        assert isinstance(resp.json(), list)


def test_get_image_jobs_limit_negative_rejected(client: TestClient) -> None:
    """limit < 0 violates ge=0 → 422."""
    resp = client.get("/images/jobs", params={"limit": "-1"})
    assert resp.status_code == 422


def test_get_image_jobs_surfaces_unseeded_raster(client: TestClient) -> None:
    """A raster file-record with no description appears in GET /images/jobs."""
    file_id = _seed_image_file_record(client)
    resp = client.get("/images/jobs")
    assert resp.status_code == 200, resp.text
    jobs = resp.json()
    assert len(jobs) == 1
    job = ImageJob(**jobs[0])  # conformance
    assert job.file_id == file_id
    assert job.mime == "image/png"
    assert job.online_only is False
    assert job.image_b64 is None
    assert job.oversized is False
    assert job.current_description is None


def test_put_image_caption_returns_200_and_conformant_image_description(
    client: TestClient,
) -> None:
    """PUT /images/{file_id} returns 200 and a valid ImageDescription."""
    file_id = _seed_image_file_record(client, rel="cat.png", path="/tmp/cat.png")  # noqa: S108
    resp = client.put(
        f"/images/{file_id}",
        json={"description": "A tabby cat sitting on a red cushion."},
    )
    assert resp.status_code == 200, resp.text
    desc = ImageDescription(**resp.json())  # OpenAPI-conformance proxy
    assert desc.file_id == file_id
    assert desc.record.is_note is False
    assert desc.record.metadata.get("kind") == "image_description"
    assert desc.replaced_description_id is None  # first put — nothing to replace


def test_put_image_caption_text_stored_verbatim(client: TestClient) -> None:
    """The description text is stored verbatim (no trimming)."""
    file_id = _seed_image_file_record(client, rel="dog.png", path="/tmp/dog.png")  # noqa: S108
    text = "  A golden retriever running through a meadow.  "
    resp = client.put(f"/images/{file_id}", json={"description": text})
    assert resp.status_code == 200, resp.text
    # Core stores verbatim; transport does not strip.
    assert resp.json()["record"]["content"] == text


def test_put_image_caption_unknown_file_id_returns_404(client: TestClient) -> None:
    """PUT /images/{file_id} with an unknown id returns 404."""
    resp = client.put(
        "/images/no-such-file-id",
        json={"description": "Some description."},
    )
    assert resp.status_code == 404


def test_put_image_caption_empty_description_returns_422(client: TestClient) -> None:
    """PUT /images/{file_id} with empty description violates min_length=1 → 422."""
    file_id = _seed_image_file_record(client)
    resp = client.put(f"/images/{file_id}", json={"description": ""})
    assert resp.status_code == 422


def test_put_image_caption_missing_description_returns_422(client: TestClient) -> None:
    """PUT /images/{file_id} without a body field returns 422."""
    file_id = _seed_image_file_record(client)
    resp = client.put(f"/images/{file_id}", json={})
    assert resp.status_code == 422


def test_put_image_caption_round_trip_then_jobs_empty(client: TestClient) -> None:
    """After PUT /images/{file_id}, GET /images/jobs must NOT re-surface that image.

    This is the no-drift guarantee: image_caption_put archives prior descriptions
    and creates a new active one, so the needs-redescribe predicate is satisfied.
    """
    file_id = _seed_image_file_record(client, rel="bird.jpg", path="/tmp/bird.jpg")  # noqa: S108

    # Confirm the image appears in the default jobs list before describing.
    resp_before = client.get("/images/jobs")
    assert resp_before.status_code == 200
    job_ids_before = [j["file_id"] for j in resp_before.json()]
    assert file_id in job_ids_before

    # Store a description.
    put_resp = client.put(
        f"/images/{file_id}",
        json={"description": "A blue jay perched on a birch branch."},
    )
    assert put_resp.status_code == 200, put_resp.text

    # The image must no longer appear in the default jobs list.
    resp_after = client.get("/images/jobs")
    assert resp_after.status_code == 200
    job_ids_after = [j["file_id"] for j in resp_after.json()]
    assert file_id not in job_ids_after, (
        "image must be absent from default /images/jobs after a successful PUT"
    )


def test_put_image_caption_idempotent_replaces_prior(client: TestClient) -> None:
    """Re-putting a description archives the old one and sets replaced_description_id."""
    file_id = _seed_image_file_record(client, rel="flower.png", path="/tmp/flower.png")  # noqa: S108

    # First describe.
    first = client.put(
        f"/images/{file_id}", json={"description": "A red rose against a white background."}
    )
    assert first.status_code == 200
    first_desc_id: str = first.json()["record"]["id"]

    # Second describe — must archive the first.
    second = client.put(f"/images/{file_id}", json={"description": "A red rose with morning dew."})
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["replaced_description_id"] == first_desc_id

    # After the second put the image still does not reappear in jobs.
    jobs_resp = client.get("/images/jobs")
    assert jobs_resp.status_code == 200
    assert all(j["file_id"] != file_id for j in jobs_resp.json())


def test_get_image_jobs_include_all_surfaces_described_image(client: TestClient) -> None:
    """include_all=true returns already-described images with current_description set."""
    file_id = _seed_image_file_record(client, rel="sky.webp", path="/tmp/sky.webp", ext=".webp")

    client.put(
        f"/images/{file_id}", json={"description": "A sunset over the ocean with orange hues."}
    )

    resp = client.get("/images/jobs", params={"include_all": "true"})
    assert resp.status_code == 200
    matching = [j for j in resp.json() if j["file_id"] == file_id]
    assert len(matching) == 1
    job = ImageJob(**matching[0])  # conformance
    assert job.current_description == "A sunset over the ocean with orange hues."


def test_get_image_jobs_svg_not_surfaced(client: TestClient) -> None:
    """SVG file-records must never appear in GET /images/jobs."""
    client.post(
        "/memories",
        json={
            "content": "[svg] logo.svg",
            "category": "context",
            "source": "document",
            "metadata": {
                "collection": "lib",
                "path": "/tmp/logo.svg",  # noqa: S108
                "rel": "logo.svg",
                "ext": ".svg",
                "size": 256,
                "mtime": 1_700_000_000.0,
                "online_only": False,
                "folder": ".",
                "index_mode": "vision",
            },
        },
    )
    resp = client.get("/images/jobs")
    assert resp.status_code == 200
    # SVG-only store → zero raster jobs.
    assert resp.json() == []


def test_get_image_jobs_works_without_vision_backend(client: TestClient) -> None:
    """GET /images/jobs works with provider=agent (the default — no backend needed)."""
    file_id = _seed_image_file_record(client)
    # No MINTMORY_VISION_* env vars set → provider=agent; must not error.
    resp = client.get("/images/jobs")
    assert resp.status_code == 200
    assert any(j["file_id"] == file_id for j in resp.json())


# ---------------------------------------------------------------------------
# POST /images/caption-run (new — add-llm-vision-provider, Group 6.4)
# ---------------------------------------------------------------------------


def test_caption_run_agent_provider_is_noop(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /images/caption-run with provider=agent (default) returns 200 and a
    CaptionRunReport with provider='agent' and all-zero counts.

    No images are described; no captioner is invoked. This is the documented
    no-op when MINTMORY_VISION_PROVIDER is not set (or is 'agent').
    """
    from mintmory.core.types import CaptionRunReport

    monkeypatch.delenv("MINTMORY_VISION_PROVIDER", raising=False)
    resp = client.post("/images/caption-run", json={})
    assert resp.status_code == 200, resp.text
    report = CaptionRunReport(**resp.json())  # OpenAPI-conformance proxy
    assert report.provider == "agent"
    assert report.described == 0
    assert report.skipped == 0
    assert report.failed == 0
    assert report.budget_hit is False
    assert report.items == []


def test_caption_run_agent_provider_empty_body_is_valid(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /images/caption-run with an empty JSON body uses all defaults and is 200."""
    monkeypatch.delenv("MINTMORY_VISION_PROVIDER", raising=False)
    resp = client.post("/images/caption-run", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "agent"


def test_caption_run_request_body_params_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /images/caption-run accepts limit, budget_mb, and include_all params."""
    monkeypatch.delenv("MINTMORY_VISION_PROVIDER", raising=False)
    resp = client.post(
        "/images/caption-run",
        json={"limit": 10, "budget_mb": 50.0, "include_all": True},
    )
    assert resp.status_code == 200
    assert resp.json()["provider"] == "agent"


def test_caption_run_limit_negative_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /images/caption-run with limit < 0 returns 422 (ge=0 constraint)."""
    monkeypatch.delenv("MINTMORY_VISION_PROVIDER", raising=False)
    resp = client.post("/images/caption-run", json={"limit": -1})
    assert resp.status_code == 422


def test_caption_run_budget_mb_negative_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /images/caption-run with budget_mb < 0 returns 422 (ge=0.0 constraint)."""
    monkeypatch.delenv("MINTMORY_VISION_PROVIDER", raising=False)
    resp = client.post("/images/caption-run", json={"budget_mb": -1.0})
    assert resp.status_code == 422


def test_caption_run_ocr_provider_returns_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /images/caption-run with provider=ocr returns 422 (ocr is still a stub).

    The route maps NotImplementedError from captioner_from_settings to HTTP 422
    with a clear detail message.
    """
    monkeypatch.setenv("MINTMORY_VISION_PROVIDER", "ocr")
    resp = client.post("/images/caption-run", json={})
    assert resp.status_code == 422, resp.text
    detail = resp.json().get("detail", "")
    # The message must mention the agent-supplied alternative or 'not implemented'.
    assert "agent" in detail.lower() or "not implemented" in detail.lower()


def test_caption_run_llm_provider_no_pending_images(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /images/caption-run with provider=llm and no pending images returns 200.

    With no pending raster images the captioner is never called (no network).
    described=0, failed=0, provider='llm'.
    """
    from mintmory.core.types import CaptionRunReport

    monkeypatch.setenv("MINTMORY_VISION_PROVIDER", "llm")
    resp = client.post("/images/caption-run", json={})
    assert resp.status_code == 200, resp.text
    report = CaptionRunReport(**resp.json())
    assert report.provider == "llm"
    assert report.described == 0
    assert report.failed == 0


def test_caption_run_llm_provider_with_stubbed_poster(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pytest.TempPathFactory,
) -> None:
    """POST /images/caption-run with provider=llm + a monkeypatched poster describes images.

    No real network: ``post_chat_completion`` is monkeypatched to return a canned
    response. After the run the image must be absent from GET /images/jobs (no-drift).
    """
    from mintmory.core import llm as llm_mod
    from mintmory.core.types import CaptionRunReport

    monkeypatch.setenv("MINTMORY_VISION_PROVIDER", "llm")

    # Create a real tiny PNG so describe() can read bytes.
    img_path = tmp_path / "test.png"  # type: ignore[operator]
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    # Seed a pending raster image file-record.
    file_id = _seed_image_file_record(
        client,
        rel="test.png",
        path=str(img_path),
        ext=".png",
    )

    # Confirm it shows up as pending.
    jobs_before = client.get("/images/jobs")
    assert jobs_before.status_code == 200
    assert any(j["file_id"] == file_id for j in jobs_before.json())

    # Monkeypatch the poster so no real HTTP call is made.
    def _fake_poster(
        *,
        base_url: str,
        api_key: object,
        payload: object,
        timeout_s: object,
        system: object,
        model: object,
    ) -> dict[str, object]:
        return {"choices": [{"message": {"content": "A test PNG with no real content."}}]}

    monkeypatch.setattr(llm_mod, "post_chat_completion", _fake_poster)

    resp = client.post("/images/caption-run", json={})
    assert resp.status_code == 200, resp.text
    report = CaptionRunReport(**resp.json())
    assert report.described == 1, f"expected described=1, got {report}"
    assert report.failed == 0
    assert report.provider == "llm"
    assert len(report.items) == 1
    assert report.items[0].status == "described"

    # After the run, the image must be absent from default GET /images/jobs (no-drift).
    jobs_after = client.get("/images/jobs")
    assert jobs_after.status_code == 200
    assert not any(j["file_id"] == file_id for j in jobs_after.json()), (
        "described image must be absent from GET /images/jobs after caption-run"
    )
