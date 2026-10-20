"""RED tests for task 5 — HTTP API tenancy error mapping and global scope.

They trace requirement 6.1 (the API stays global: unscoped search, creates
stamped ``global``), 6.2 (every ``TenantError`` maps to its HTTP status with a
``{"detail": str(exc)}`` body) and 6.3 (the cross-tenant link, in-tenant
archive, and inactive-tenant patch examples).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mintmory.api import app as app_module
from mintmory.core.ports import StorageBackend
from mintmory.core.types import (
    CrossTenantLinkError,
    InvalidTenantIdError,
    MemoryCategory,
    MemoryRecord,
    ProtectedTenantError,
    ScopeRequiredError,
    TenancyNotSupportedError,
    TenantError,
    TenantImmutableError,
    TenantInactiveError,
    TenantMigrationError,
    TenantNotFoundError,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    db_file = tmp_path / "api_tenancy_errors.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_file))
    monkeypatch.setattr(app_module, "_store", None)
    with TestClient(app_module.app, raise_server_exceptions=False) as test_client:
        yield test_client
    monkeypatch.setattr(app_module, "_store", None)


def _store() -> StorageBackend:
    store = app_module._store
    assert store is not None
    return store


def _add(store: StorageBackend, memory_id: str, content: str, tenant_id: str) -> MemoryRecord:
    return store.add_memory(
        MemoryRecord(
            id=memory_id,
            content=content,
            category=MemoryCategory.FACT,
            tenant_id=tenant_id,
        )
    )


_TENANT_ERROR_CASES: list[tuple[Callable[[], TenantError], int]] = [
    (lambda: TenantNotFoundError("t1"), 404),
    (lambda: TenantInactiveError("t1"), 409),
    (lambda: CrossTenantLinkError("a1", "t1", "g1", "global"), 409),
    (lambda: TenantImmutableError("a1", "t1", "global"), 409),
    (lambda: ProtectedTenantError(), 403),
    (lambda: ScopeRequiredError("index-tree", "t1"), 403),
    (lambda: InvalidTenantIdError("bad tenant"), 422),
    (lambda: TenancyNotSupportedError("create_tenant"), 501),
    (lambda: TenantMigrationError("boom"), 503),
]


@pytest.mark.parametrize(("error_factory", "expected_status"), _TENANT_ERROR_CASES)
@pytest.mark.l4("C-48ed16ae")
def test_tenant_errors_map_to_http_statuses(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error_factory: Callable[[], TenantError],
    expected_status: int,
) -> None:
    error = error_factory()
    store = _store()

    def _raise(*args: object, **kwargs: object) -> MemoryRecord | None:
        raise error

    monkeypatch.setattr(store, "get_memory", _raise)

    resp = client.get("/memories/whatever")

    assert resp.status_code == expected_status
    assert resp.json() == {"detail": str(error)}


@pytest.mark.l4("C-8308a89a")
def test_cross_tenant_link_archive_and_inactive_patch_examples(client: TestClient) -> None:
    store = _store()
    store.create_tenant("t1")
    _add(store, "a1", "Alice works at Acme", "t1")
    _add(store, "a2", "Bob works at Acme", "t1")

    link_resp = client.post(
        "/memories/a1/links",
        json={"target_memory_id": "a2", "link_type": "relates_to"},
    )
    assert link_resp.status_code == 409, link_resp.text
    assert link_resp.json()["detail"]
    assert store.get_links("a1") == []

    delete_resp = client.delete("/memories/a1")
    assert delete_resp.status_code == 204, delete_resp.text
    archived = store.get_memory("a1")
    assert archived is not None
    assert archived.is_archived is True
    assert archived.tenant_id == "t1"

    store.set_tenant_active("t1", False)
    patch_resp = client.patch("/memories/a1", json={"verified": True})
    assert patch_resp.status_code == 409, patch_resp.text
    assert patch_resp.json()["detail"]


@pytest.mark.l4("C-1c14608f")
def test_search_is_unscoped_and_creates_are_stamped_global(client: TestClient) -> None:
    store = _store()
    store.create_tenant("t1")
    _add(store, "g-search", "Global deployment notes for Acme.", "global")
    _add(store, "t-search", "Tenant deployment notes for Acme.", "t1")

    search = client.post("/memories/search", json={"query": "deployment", "limit": 10})
    assert search.status_code == 200, search.text
    found = {item["id"]: item["tenant_id"] for item in search.json()["memories"]}
    assert found == {"g-search": "global", "t-search": "t1"}

    created = client.post(
        "/memories",
        json={"content": "A fresh API memory.", "category": "fact"},
    )
    assert created.status_code == 201, created.text
    assert MemoryRecord(**created.json()).tenant_id == "global"
