"""RED tests for task 3 — HTTP dreaming and summary routes on a multi-tenant DB.

They trace requirement 3.1 (``POST /dream`` runs every tenant through
``run_dream``), 3.2 (the route still returns a ``DreamReport``, the per-tenant
total), 3.3 (``DreamFailedError`` becomes HTTP 500 ``{"detail": ...}``), 4.1
(``GET /summaries/jobs`` / ``PUT /summaries/{concept}`` stay on the global
tenant) and 4.2 (the image path relies on the core ``global`` defaults).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mintmory.api import app as app_module
from mintmory.core.dreaming import DreamingEngine
from mintmory.core.ports import StorageBackend
from mintmory.core.types import (
    ConceptLink,
    DreamReport,
    MemoryCategory,
    MemoryRecord,
    MemorySource,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    db_file = tmp_path / "api_tenancy.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_file))
    monkeypatch.setattr(app_module, "_store", None)
    with TestClient(app_module.app, raise_server_exceptions=False) as test_client:
        yield test_client
    monkeypatch.setattr(app_module, "_store", None)


def _store() -> StorageBackend:
    store = app_module._store
    assert store is not None
    return store


def _add(
    store: StorageBackend,
    memory_id: str,
    content: str,
    tenant_id: str,
    **fields: Any,
) -> MemoryRecord:
    return store.add_memory(
        MemoryRecord(
            id=memory_id,
            content=content,
            category=MemoryCategory.FACT,
            tenant_id=tenant_id,
            **fields,
        )
    )


def _seed_two_tenants(store: StorageBackend) -> None:
    store.create_tenant("t1")
    _add(store, "g1", "Alice works at Acme in Berlin", "global")
    _add(store, "g2", "Bob works at Acme in Berlin", "global")
    _add(store, "a1", "Alice works at Acme in Berlin", "t1")
    _add(store, "a2", "Carol works at Acme in Berlin", "t1")
    _add(store, "a3", "Dan works at Acme in Berlin", "t1")


def _seed_summary_tenants(store: StorageBackend) -> None:
    store.create_tenant("t1")
    for index in range(3):
        _add(
            store,
            f"g{index}",
            f"Global {index} fact",
            "global",
            entity_ids=["globalconcept"],
        )
        _add(
            store,
            f"a{index}",
            f"Tenant {index} fact",
            "t1",
            entity_ids=["tenantconcept"],
        )


def _all_links(store: StorageBackend, memory_ids: list[str]) -> list[ConceptLink]:
    by_id: dict[str, ConceptLink] = {}
    for memory_id in memory_ids:
        for link in store.get_links(memory_id):
            by_id[link.id] = link
    return list(by_id.values())


@pytest.mark.l4("C-7881686c", "C-d9c39ea3")
def test_dream_runs_each_tenant_without_cross_tenant_links(client: TestClient) -> None:
    store = _store()
    _seed_two_tenants(store)

    resp = client.post("/dream", json={"intensity": "light"})

    assert resp.status_code == 200, resp.text
    report = DreamReport(**resp.json())
    assert report.intensity.value == "light"
    assert report.new_links == 4

    grouped: dict[str, set[frozenset[str]]] = defaultdict(set)
    for link in _all_links(store, ["g1", "g2", "a1", "a2", "a3"]):
        grouped[link.tenant_id].add(frozenset({link.source_memory_id, link.target_memory_id}))
    assert grouped == {
        "global": {frozenset({"g1", "g2"})},
        "t1": {
            frozenset({"a1", "a2"}),
            frozenset({"a1", "a3"}),
            frozenset({"a2", "a3"}),
        },
    }


@pytest.mark.l4("C-63860dbc")
def test_dream_failure_returns_500_detail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: DreamingEngine) -> DreamReport:
        raise RuntimeError("boom")

    monkeypatch.setattr(DreamingEngine, "run_light", boom)
    monkeypatch.setattr(DreamingEngine, "run_full", boom)

    resp = client.post("/dream", json={"intensity": "full"})

    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["detail"] == "dreaming failed for tenant(s): global (RuntimeError: boom)"


@pytest.mark.l4("C-a0213e6c")
def test_summary_routes_stay_on_the_global_tenant(client: TestClient) -> None:
    store = _store()
    _seed_summary_tenants(store)

    jobs = client.get("/summaries/jobs")
    assert jobs.status_code == 200, jobs.text
    assert [job["concept"] for job in jobs.json()] == ["globalconcept"]

    put = client.put("/summaries/tenantconcept", json={"summary_text": "Global only."})
    assert put.status_code == 200, put.text
    assert put.json()["memory_count"] == 0
    assert store.get_summary("tenantconcept", "global") is not None
    assert store.get_summary("tenantconcept", "t1") is None


@pytest.mark.l4("C-051abf8f")
def test_image_jobs_use_the_global_default(client: TestClient) -> None:
    store = _store()
    store.create_tenant("t1")
    for memory_id, tenant_id, rel in (
        ("img-global", "global", "global.png"),
        ("img-tenant", "t1", "tenant.png"),
    ):
        store.add_memory(
            MemoryRecord(
                id=memory_id,
                content=f"Image file: {rel}",
                category=MemoryCategory.CONTEXT,
                source=MemorySource.DOCUMENT,
                tenant_id=tenant_id,
                metadata={
                    "collection": "test",
                    "path": f"/fake/{rel}",
                    "rel": rel,
                    "ext": ".png",
                    "size": 1024,
                    "mtime": 1_700_000_000.0,
                    "online_only": False,
                    "folder": ".",
                    "index_mode": "metadata",
                },
            )
        )

    resp = client.get("/images/jobs")

    assert resp.status_code == 200, resp.text
    assert [job["file_id"] for job in resp.json()] == ["img-global"]
