"""RED tests for task 2 — per-tenant keys for summaries and the manifest.

They trace requirements 4.3 (``get_summary`` takes a ``tenant_id``), 4.4
(``upsert_summary`` is keyed on ``(tenant_id, concept)``) and 4.5 (the four
manifest methods take a keyword-only ``tenant_id`` and ``ManifestEntry`` carries
one).
"""

from __future__ import annotations

import inspect

import pytest
from mintmory.core.ports import ManifestEntry
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import MemorySummary


@pytest.fixture()
def store() -> StorageAdapter:
    adapter = StorageAdapter(":memory:")
    adapter.initialise()
    return adapter


def _seed_tenant(store: StorageAdapter, tenant_id: str) -> None:
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO tenants (id, name, is_active, created_at, updated_at) "
            "VALUES (?, ?, 1, '2026-01-01T00:00:00', '2026-01-01T00:00:00')",
            (tenant_id, tenant_id),
        )


def _summary(
    concept: str,
    text: str,
    tenant_id: str = "global",
    count: int = 1,
) -> MemorySummary:
    return MemorySummary(
        concept=concept,
        summary_text=text,
        memory_count=count,
        tenant_id=tenant_id,
    )


def _summary_columns(store: StorageAdapter) -> set[str]:
    rows = store.connect().execute("PRAGMA table_info(memory_summaries)").fetchall()
    return {row["name"] for row in rows}


def _manifest_columns(store: StorageAdapter) -> set[str]:
    rows = store.connect().execute("PRAGMA table_info(index_manifest)").fetchall()
    return {row["name"] for row in rows}


# ---------------------------------------------------------------------------
# Requirement 4.3 — get_summary scoped by tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-619bc1e6")
def test_get_summary_filters_by_tenant(store: StorageAdapter) -> None:
    assert "tenant_id" in _summary_columns(store)
    params = inspect.signature(store.get_summary).parameters
    assert params["tenant_id"].default == "global"
    _seed_tenant(store, "t1")
    store.upsert_summary(_summary("acme", "global acme"))
    store.upsert_summary(_summary("acme", "t1 acme", "t1", count=2))

    global_row = store.get_summary("acme")
    assert global_row is not None
    assert global_row.tenant_id == "global"
    assert global_row.summary_text == "global acme"

    tenant_row = store.get_summary("acme", tenant_id="t1")
    assert tenant_row is not None
    assert tenant_row.tenant_id == "t1"
    assert tenant_row.summary_text == "t1 acme"

    assert store.get_summary("acme", tenant_id="t1x") is None


# ---------------------------------------------------------------------------
# Requirement 4.4 — upsert_summary keyed on (tenant_id, concept)
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-a41e591b")
def test_upsert_summary_keys_by_tenant_and_concept(store: StorageAdapter) -> None:
    assert "tenant_id" in _summary_columns(store)
    _seed_tenant(store, "t1")
    store.upsert_summary(_summary("acme", "global acme"))
    store.upsert_summary(_summary("acme", "t1 acme", "t1", count=2))

    rows = (
        store.connect()
        .execute(
            "SELECT tenant_id, concept FROM memory_summaries "
            "WHERE concept = 'acme' ORDER BY tenant_id"
        )
        .fetchall()
    )
    assert [(row["tenant_id"], row["concept"]) for row in rows] == [
        ("global", "acme"),
        ("t1", "acme"),
    ]

    tenant_before = store.get_summary("acme", tenant_id="t1")
    assert tenant_before is not None
    updated = store.upsert_summary(
        MemorySummary(
            concept="acme",
            summary_text="t1 updated",
            memory_count=5,
            tenant_id="t1",
        )
    )
    assert updated.summary_text == "t1 updated"
    assert updated.tenant_id == "t1"
    assert updated.id == tenant_before.id
    tenant_count = (
        store.connect()
        .execute(
            "SELECT COUNT(*) AS c FROM memory_summaries WHERE tenant_id = 't1' AND concept = 'acme'"
        )
        .fetchone()["c"]
    )
    assert tenant_count == 1


# ---------------------------------------------------------------------------
# Requirement 4.5 — manifest methods keyed by (tenant_id, path)
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-5b9008af")
def test_manifest_entry_carries_tenant_id(store: StorageAdapter) -> None:
    assert "tenant_id" in ManifestEntry.__annotations__
    assert "tenant_id" in _manifest_columns(store)
    store.manifest_upsert(
        "/a",
        "col",
        size=1,
        mtime=1.0,
        online_only=False,
        index_mode="metadata",
        memory_ids=[],
    )
    entry = store.manifest_get("/a")
    assert entry is not None
    assert entry["collection"] == "col"
    assert dict(entry).get("tenant_id") == "global"


@pytest.mark.l4("C-5b9008af")
def test_manifest_methods_scope_to_tenant(store: StorageAdapter) -> None:
    assert "tenant_id" in _manifest_columns(store)
    for method in (
        store.manifest_get,
        store.manifest_upsert,
        store.manifest_paths,
        store.manifest_delete,
    ):
        parameters = inspect.signature(method).parameters
        assert list(parameters)[-1] == "tenant_id"
        assert parameters["tenant_id"].kind is inspect.Parameter.KEYWORD_ONLY
        assert parameters["tenant_id"].default == "global"

    _seed_tenant(store, "t1")
    store.manifest_upsert(
        "/a",
        "global-col",
        size=1,
        mtime=1.0,
        online_only=False,
        index_mode="metadata",
        memory_ids=[],
    )
    store.manifest_upsert(
        "/a",
        "t1-col",
        size=2,
        mtime=2.0,
        online_only=False,
        index_mode="metadata",
        memory_ids=[],
        tenant_id="t1",
    )

    global_entry = store.manifest_get("/a")
    assert global_entry is not None
    assert global_entry["collection"] == "global-col"
    assert dict(global_entry).get("tenant_id") == "global"

    tenant_entry = store.manifest_get("/a", tenant_id="t1")
    assert tenant_entry is not None
    assert tenant_entry["collection"] == "t1-col"
    assert dict(tenant_entry).get("tenant_id") == "t1"

    assert store.manifest_paths("global-col") == {"/a"}
    assert store.manifest_paths("global-col", tenant_id="t1") == set()
    assert store.manifest_paths("t1-col", tenant_id="t1") == {"/a"}

    store.manifest_delete("/a", tenant_id="t1")
    assert store.manifest_get("/a") is not None
    assert store.manifest_get("/a", tenant_id="t1") is None
