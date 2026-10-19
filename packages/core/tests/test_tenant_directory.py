"""RED tests for task 5 — the SQLite tenant directory (``storage.py``).

They trace requirements 5.1 (``create_tenant`` validates, is idempotent and
race-safe), 5.2 (``get_tenant``), 5.3 (``list_tenants``), 5.4
(``set_tenant_active``) and 5.5 (the seeded ``global`` row).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest
from mintmory.core.storage import SqliteBackend, StorageAdapter
from mintmory.core.types import (
    InvalidTenantIdError,
    ProtectedTenantError,
    Tenant,
    TenantNotFoundError,
)


@pytest.fixture()
def store() -> StorageAdapter:
    adapter = StorageAdapter(":memory:")
    adapter.initialise()
    return adapter


def _insert_tenant(
    store: StorageAdapter,
    tenant_id: str,
    *,
    name: str = "",
    is_active: int = 1,
    created_at: str = "2026-01-01T00:00:00",
    updated_at: str = "2026-01-01T00:00:00",
) -> None:
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO tenants (id, name, is_active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (tenant_id, name, is_active, created_at, updated_at),
        )


def _tenant_row(store: StorageAdapter, tenant_id: str) -> sqlite3.Row:
    row = store.connect().execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    assert row is not None
    return cast(sqlite3.Row, row)


def _tenant_count(store: StorageAdapter) -> int:
    row = store.connect().execute("SELECT COUNT(*) AS c FROM tenants").fetchone()
    assert row is not None
    return int(row["c"])


# ---------------------------------------------------------------------------
# Requirement 5.1 — create_tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-13c99d09")
def test_create_tenant_persists_and_returns_stored_row(store: StorageAdapter) -> None:
    created = store.create_tenant("acme", "Acme Corp")

    assert isinstance(created, Tenant)
    assert (created.id, created.name, created.is_active) == ("acme", "Acme Corp", True)

    row = _tenant_row(store, "acme")
    assert (row["id"], row["name"], row["is_active"]) == ("acme", "Acme Corp", 1)


@pytest.mark.l4("C-13c99d09")
def test_create_tenant_defaults_name_to_empty(store: StorageAdapter) -> None:
    created = store.create_tenant("acme")

    assert created.name == ""
    assert _tenant_row(store, "acme")["name"] == ""


@pytest.mark.l4("C-13c99d09")
def test_create_tenant_is_idempotent_and_keeps_existing_name(store: StorageAdapter) -> None:
    first = store.create_tenant("acme", "First")
    second = store.create_tenant("acme", "Second")

    assert first.name == "First"
    assert second.id == "acme"
    assert second.name == "First"
    assert _tenant_count(store) == 2


@pytest.mark.l4("C-13c99d09")
def test_create_tenant_validates_id_before_inserting(store: StorageAdapter) -> None:
    for bad_id in ("", "Acme", "-x", "a b", "a" * 129):
        with pytest.raises(InvalidTenantIdError):
            store.create_tenant(bad_id)

    assert _tenant_count(store) == 1


@pytest.mark.l4("C-13c99d09")
def test_create_tenant_from_two_backends_leaves_one_row(tmp_path: Path) -> None:
    path = tmp_path / "tenants.db"
    first = SqliteBackend(str(path))
    first.initialise()
    second = SqliteBackend(str(path))
    second.initialise()

    created_first = first.create_tenant("acme", "First")
    created_second = second.create_tenant("acme", "Second")

    assert created_first.name == "First"
    assert created_second.id == "acme"
    assert created_second.name == "First"
    rows = first.connect().execute("SELECT id, name FROM tenants WHERE id = 'acme'").fetchall()
    assert [(row["id"], row["name"]) for row in rows] == [("acme", "First")]


# ---------------------------------------------------------------------------
# Requirement 5.2 — get_tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-ef053fe0")
def test_get_tenant_returns_stored_tenant(store: StorageAdapter) -> None:
    _insert_tenant(store, "acme", name="Acme Corp")

    tenant = store.get_tenant("acme")

    assert tenant is not None
    assert isinstance(tenant, Tenant)
    assert (tenant.id, tenant.name, tenant.is_active) == ("acme", "Acme Corp", True)


@pytest.mark.l4("C-ef053fe0")
def test_get_tenant_reads_inactive_flag(store: StorageAdapter) -> None:
    _insert_tenant(store, "acme", is_active=0)

    tenant = store.get_tenant("acme")

    assert tenant is not None
    assert tenant.is_active is False


@pytest.mark.l4("C-ef053fe0")
def test_get_tenant_returns_none_for_unknown_or_invalid_id(store: StorageAdapter) -> None:
    assert store.get_tenant("missing") is None
    for bad_id in ("", "Acme", "-x", "a b", "a" * 129):
        assert store.get_tenant(bad_id) is None


# ---------------------------------------------------------------------------
# Requirement 5.3 — list_tenants
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-e39615c9")
def test_list_tenants_orders_all_tenants_by_id(store: StorageAdapter) -> None:
    _insert_tenant(store, "zeta", name="Zeta")
    _insert_tenant(store, "alpha", name="Alpha", is_active=0)
    _insert_tenant(store, "beta", name="Beta")

    tenants = store.list_tenants()

    assert [tenant.id for tenant in tenants] == ["alpha", "beta", "global", "zeta"]
    assert [tenant.is_active for tenant in tenants] == [False, True, True, True]
    assert tenants[0].name == "Alpha"


@pytest.mark.l4("C-e39615c9")
def test_list_tenants_on_fresh_database_returns_only_global(store: StorageAdapter) -> None:
    tenants = store.list_tenants()

    assert [tenant.id for tenant in tenants] == ["global"]
    assert tenants[0].name == "Global (default) tenant"
    assert tenants[0].is_active is True


# ---------------------------------------------------------------------------
# Requirement 5.4 — set_tenant_active
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-0df6c3f3")
def test_set_tenant_active_updates_flag_and_timestamp(store: StorageAdapter) -> None:
    _insert_tenant(store, "acme", name="Acme", updated_at="2020-01-01T00:00:00")
    _insert_tenant(store, "beta", name="Beta")

    updated = store.set_tenant_active("acme", False)

    assert isinstance(updated, Tenant)
    assert (updated.id, updated.name, updated.is_active) == ("acme", "Acme", False)
    row = _tenant_row(store, "acme")
    assert row["is_active"] == 0
    assert row["created_at"] == "2020-01-01T00:00:00"
    assert datetime.fromisoformat(row["updated_at"]) > datetime(2020, 1, 1)
    assert _tenant_row(store, "beta")["is_active"] == 1


@pytest.mark.l4("C-0df6c3f3")
def test_set_tenant_active_can_reactivate(store: StorageAdapter) -> None:
    _insert_tenant(store, "acme", is_active=0)

    updated = store.set_tenant_active("acme", True)

    assert updated.is_active is True
    assert _tenant_row(store, "acme")["is_active"] == 1


@pytest.mark.l4("C-0df6c3f3")
def test_set_tenant_active_unknown_id_raises_not_found(store: StorageAdapter) -> None:
    with pytest.raises(TenantNotFoundError) as excinfo:
        store.set_tenant_active("missing", False)

    assert excinfo.value.tenant_id == "missing"


@pytest.mark.l4("C-0df6c3f3")
def test_set_tenant_active_invalid_id_is_unknown(store: StorageAdapter) -> None:
    for bad_id in ("", "Acme", "-x", "a b", "a" * 129):
        with pytest.raises(TenantNotFoundError):
            store.set_tenant_active(bad_id, True)


@pytest.mark.l4("C-0df6c3f3")
def test_set_tenant_active_cannot_deactivate_global(store: StorageAdapter) -> None:
    with pytest.raises(ProtectedTenantError):
        store.set_tenant_active("global", False)

    assert _tenant_row(store, "global")["is_active"] == 1


@pytest.mark.l4("C-0df6c3f3")
def test_set_tenant_active_global_true_returns_unchanged(store: StorageAdapter) -> None:
    before = tuple(_tenant_row(store, "global"))

    tenant = store.set_tenant_active("global", True)

    assert (tenant.id, tenant.name, tenant.is_active) == (
        "global",
        "Global (default) tenant",
        True,
    )
    assert tuple(_tenant_row(store, "global")) == before


# ---------------------------------------------------------------------------
# Requirement 5.5 — the seeded global row
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-c089869a", "C-ef053fe0", "C-e39615c9")
def test_seeded_global_row_has_sentinel_fields_and_timestamps(store: StorageAdapter) -> None:
    tenant = store.get_tenant("global")

    assert tenant is not None
    assert (tenant.id, tenant.name, tenant.is_active) == (
        "global",
        "Global (default) tenant",
        True,
    )
    assert tenant.created_at == datetime(1970, 1, 1)
    assert tenant.updated_at == datetime(1970, 1, 1)

    listed = store.list_tenants()
    assert [row.id for row in listed] == ["global"]
    assert listed[0].created_at == datetime(1970, 1, 1)
    assert listed[0].updated_at == datetime(1970, 1, 1)
