"""RED tests for task 7 — schema gate coverage (R7.1).

The schema gate (``test_schema.py``) is itself the deliverable of R7.1: it must
list the ``tenants`` table, the ``tenant_id`` column of all six tables, the three
tenant indexes, and assert the seeded ``global`` row.  These tests inspect the
gate module so the gate change is pinned before it is made.
"""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest

GATE_PATH = Path(__file__).with_name("test_schema.py")


def _gate_globals() -> dict[str, Any]:
    return runpy.run_path(str(GATE_PATH))


@pytest.mark.l4("C-27174f33")
def test_schema_gate_lists_tenants_and_tenant_id_columns() -> None:
    gate = _gate_globals()
    source = GATE_PATH.read_text(encoding="utf-8")

    assert "tenants" in gate["REQUIRED_TABLES"]
    assert "tenant_id" in gate["REQUIRED_MEMORIES_COLUMNS"]
    assert "tenant_id" in gate["REQUIRED_LINKS_COLUMNS"]
    assert "tenant_id" in gate["REQUIRED_SESSIONS_COLUMNS"]

    for constant, table in (
        ("REQUIRED_SUMMARY_COLUMNS", "memory_summaries"),
        ("REQUIRED_RESULTS_COLUMNS", "query_results"),
        ("REQUIRED_MANIFEST_COLUMNS", "index_manifest"),
    ):
        columns = gate.get(constant)
        assert columns is not None, f"{constant} is missing from {GATE_PATH.name}"
        assert "tenant_id" in columns, f"{constant} does not assert tenant_id"
        assert f"PRAGMA table_info({table})" in source, (
            f"{GATE_PATH.name} has no column assertion for {table}"
        )


@pytest.mark.l4("C-27174f33")
def test_schema_gate_lists_the_three_tenant_indexes() -> None:
    indexes = _gate_globals()["REQUIRED_INDEXES"]

    assert {"idx_memories_tenant", "idx_links_tenant", "idx_sessions_tenant"} <= set(indexes)


@pytest.mark.l4("C-27174f33")
def test_schema_gate_asserts_exactly_one_global_tenant_row() -> None:
    gate = _gate_globals()
    source = GATE_PATH.read_text(encoding="utf-8")

    assert callable(gate.get("test_tenants_has_exactly_one_global_row"))
    assert "FROM tenants" in source
    assert "Global (default) tenant" in source
    assert "1970-01-01T00:00:00" in source
