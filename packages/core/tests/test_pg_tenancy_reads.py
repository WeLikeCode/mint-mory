"""RED tests for task 1 — tenant-scoped Postgres reads.

They trace requirement 1.1 (every read of the ``multi-tenancy-reads`` R1.1
table and the four candidate phases scaffolds its SQL with ``tenant_id = %s``
for a concrete tenant and reproduces today's SQL for ``None``), 1.2
(``_require_global_tenant`` is gone from the reads and deleted, while the keyed
summary/manifest reads keep filtering by tenant) and 1.3 (the fake-pool SQL and
parameter assertions for every read).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pytest
from mintmory.core.embedder import HashingEmbedder
from mintmory.core.storage_postgres import PostgresBackend
from mintmory.core.types import SearchAroundSpec, TenancyNotSupportedError

from packages.core.tests.pg_fakes import FakeConnection, FakePool

_TENANT = "t1"
_CUTOFF = "2020-01-01T00:00:00+00:00"


def _responder(sql: str, params: Any) -> list[Any]:
    """Answer what each statement needs: counts, averages, empty lists."""
    normalised = " ".join(sql.split())
    if "COUNT(" in normalised:
        return [(0,)]
    if "AVG(" in normalised:
        return [(None, None)]
    return []


def _backend() -> tuple[PostgresBackend, FakeConnection]:
    conn = FakeConnection(responder=_responder)
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)
    return backend, conn


def _as_tuple(params: Any) -> tuple[Any, ...]:
    if params is None:
        return ()
    return tuple(params)


def _statements(conn: FakeConnection) -> list[tuple[str, tuple[Any, ...]]]:
    return [(" ".join(sql.split()), _as_tuple(params)) for sql, params in conn.executed]


def _call_without_guard(call: Callable[[], object]) -> None:
    error: TenancyNotSupportedError | None = None
    try:
        call()
    except TenancyNotSupportedError as exc:
        error = exc
    assert error is None, f"read still uses the interim tenancy guard: {error}"


@dataclass(frozen=True)
class ReadCase:
    name: str
    invoke: Callable[[PostgresBackend], object]
    none_params: tuple[Any, ...]
    tenant_params: tuple[Any, ...]


def _read_cases() -> list[ReadCase]:
    return [
        ReadCase(
            "get_memory",
            lambda backend: backend.get_memory("m1"),
            ("m1",),
            ("m1", _TENANT),
        ),
        ReadCase(
            "search_around",
            lambda backend: backend.search_around(["a1"], SearchAroundSpec()),
            (0.0, "a1", "a1"),
            (0.0, "a1", "a1", _TENANT),
        ),
        ReadCase(
            "get_links",
            lambda backend: backend.get_links("m1"),
            ("m1", "m1"),
            ("m1", "m1", _TENANT),
        ),
        ReadCase(
            "get_annotating_notes",
            lambda backend: backend.get_annotating_notes("m1", 3),
            ("m1", "annotates", 3),
            ("m1", "annotates", _TENANT, 3),
        ),
        ReadCase(
            "get_annotating_descriptions",
            lambda backend: backend.get_annotating_descriptions("m1", 3),
            ("m1", "annotates", 3),
            ("m1", "annotates", _TENANT, 3),
        ),
        ReadCase(
            "find_image_file_record",
            lambda backend: backend.find_image_file_record("/x.png"),
            ("/x.png", "/x.png"),
            ("/x.png", "/x.png", _TENANT),
        ),
        ReadCase(
            "anchor_candidates",
            lambda backend: backend.anchor_candidates("Alice"),
            ("alice:*", "alice:*", 50),
            ("alice:*", "alice:*", _TENANT, 50),
        ),
        ReadCase(
            "list_image_file_records",
            lambda backend: backend.list_image_file_records(),
            (),
            (_TENANT,),
        ),
        ReadCase(
            "list_notes",
            lambda backend: backend.list_notes(),
            (50,),
            (_TENANT, 50),
        ),
        ReadCase(
            "list_summaries",
            lambda backend: backend.list_summaries(),
            (),
            (_TENANT,),
        ),
        ReadCase(
            "get_session",
            lambda backend: backend.get_session("s1"),
            ("s1",),
            ("s1", _TENANT),
        ),
        ReadCase(
            "get_stats",
            lambda backend: backend.get_stats(),
            (),
            (_TENANT,),
        ),
        ReadCase(
            "memory_exists_with_content",
            lambda backend: backend.memory_exists_with_content("Alice"),
            ("Alice",),
            ("Alice", _TENANT),
        ),
        ReadCase(
            "get_flagged_memories",
            lambda backend: backend.get_flagged_memories(),
            (),
            (_TENANT,),
        ),
        ReadCase(
            "get_never_accessed_stale",
            lambda backend: backend.get_never_accessed_stale(),
            (3.0,),
            (3.0, _TENANT),
        ),
        ReadCase(
            "get_high_staleness_useful",
            lambda backend: backend.get_high_staleness_useful(),
            (5.0, 3.0),
            (5.0, 3.0, _TENANT),
        ),
        ReadCase(
            "get_anomaly_high_staleness_useful_ids",
            lambda backend: backend.get_anomaly_high_staleness_useful_ids(5.0, 3.0),
            (5.0, 3.0),
            (5.0, 3.0, _TENANT),
        ),
        ReadCase(
            "get_anomaly_never_accessed_ids",
            lambda backend: backend.get_anomaly_never_accessed_ids(_CUTOFF),
            (_CUTOFF,),
            (_CUTOFF, _TENANT),
        ),
        ReadCase(
            "get_anomaly_flagged_ids",
            lambda backend: backend.get_anomaly_flagged_ids(),
            (),
            (_TENANT,),
        ),
        ReadCase(
            "list_active_memory_ids",
            lambda backend: backend.list_active_memory_ids(),
            (),
            (_TENANT,),
        ),
        ReadCase(
            "get_stale_archivable_ids",
            lambda backend: backend.get_stale_archivable_ids(5.0, _CUTOFF),
            (5.0, _CUTOFF),
            (5.0, _CUTOFF, _TENANT),
        ),
        ReadCase(
            "get_rehabilitable_rows",
            lambda backend: backend.get_rehabilitable_rows(_CUTOFF),
            (_CUTOFF,),
            (_CUTOFF, _TENANT),
        ),
        ReadCase(
            "get_existing_relates_to_pairs",
            lambda backend: backend.get_existing_relates_to_pairs(),
            ("relates_to",),
            ("relates_to", _TENANT),
        ),
    ]


@pytest.mark.l4("C-8a7e36a7", "C-c717092d")
@pytest.mark.parametrize("case", _read_cases(), ids=lambda case: case.name)
def test_pg_read_adds_tenant_predicate_and_keeps_none_sql(case: ReadCase) -> None:
    backend, conn = _backend()

    conn.executed.clear()
    _call_without_guard(lambda: case.invoke(backend))
    scoped = _statements(conn)
    assert scoped, f"{case.name} executed no SELECT for tenant {_TENANT!r}"
    for sql, params in scoped:
        assert sql.upper().startswith("SELECT"), f"{case.name}: {sql}"
        assert "tenant_id = %s" in sql, f"{case.name} has no tenant predicate: {sql}"
        assert _TENANT in params, f"{case.name} has no tenant parameter: {params}"
        assert params == case.tenant_params, f"{case.name} scoped parameters: {params}"

    conn.executed.clear()
    case.invoke(backend)
    unscoped = _statements(conn)
    assert len(unscoped) == len(scoped), f"{case.name} changed its statement count"
    for sql, params in unscoped:
        assert "tenant_id =" not in sql, f"{case.name} unscoped predicate present: {sql}"
        assert params == case.none_params, f"{case.name} unscoped parameters: {params}"


# ---------------------------------------------------------------------------
# Requirement 1.1 / 1.3 — the candidate phases gain the trailing tenant
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-8a7e36a7", "C-c717092d")
def test_pg_fts_scores_adds_tenant_predicate() -> None:
    backend, conn = _backend()

    assert backend._fts_scores("alice", 50, _TENANT) == {}
    sql, params = _statements(conn)[0]
    assert (
        "WHERE content_tsv @@ to_tsquery('english', %s) AND tenant_id = %s "
        "ORDER BY rank DESC LIMIT %s" in sql
    )
    assert params == ("alice:*", "alice:*", _TENANT, 50)

    conn.executed.clear()
    assert backend._fts_scores("alice", 50) == {}
    sql, params = _statements(conn)[0]
    assert sql == (
        "SELECT id, ts_rank(content_tsv, to_tsquery('english', %s)) AS rank "
        "FROM memories WHERE content_tsv @@ to_tsquery('english', %s) "
        "ORDER BY rank DESC LIMIT %s"
    )
    assert params == ("alice:*", "alice:*", 50)


@pytest.mark.l4("C-8a7e36a7", "C-c717092d")
def test_pg_trigram_scores_wraps_or_clauses_for_tenant() -> None:
    backend, conn = _backend()
    backend._trgm_available = True

    assert backend._trigram_scores("alice", 50, _TENANT) == {}
    sql, params = _statements(conn)[0]
    assert (
        "WHERE (similarity(%s, content) > 0.05 OR word_similarity(%s, content) > 0.1) "
        "AND tenant_id = %s" in sql
    )
    assert params == ("alice", "alice", "alice", "alice", _TENANT, 50)

    conn.executed.clear()
    assert backend._trigram_scores("alice", 50) == {}
    sql, params = _statements(conn)[0]
    assert sql == (
        "SELECT id, GREATEST(similarity(%s, content), word_similarity(%s, content)) AS sim "
        "FROM memories WHERE similarity(%s, content) > 0.05 "
        "OR word_similarity(%s, content) > 0.1 ORDER BY sim DESC LIMIT %s"
    )
    assert params == ("alice", "alice", "alice", "alice", 50)


@pytest.mark.l4("C-8a7e36a7", "C-c717092d")
def test_pg_vector_scores_adds_tenant_predicate() -> None:
    backend, conn = _backend()
    backend.embedder = HashingEmbedder(dim=8)
    backend._vec_available = True
    embedding = np.zeros(8, dtype=np.float32)

    assert backend._vector_scores("x", embedding, 50, _TENANT) == {}
    sql, params = _statements(conn)[0]
    assert "AND vector_dims(embedding) = %s AND tenant_id = %s" in sql
    np.testing.assert_array_equal(params[0], embedding)
    assert params[1:] == (8, _TENANT, 50)

    conn.executed.clear()
    assert backend._vector_scores("x", embedding, 50) == {}
    sql, params = _statements(conn)[0]
    assert sql == (
        "SELECT id, (embedding <=> %s) AS dist FROM memories "
        "WHERE embedding IS NOT NULL AND vector_dims(embedding) = %s "
        "ORDER BY dist ASC LIMIT %s"
    )
    np.testing.assert_array_equal(params[0], embedding)
    assert params[1:] == (8, 50)


@pytest.mark.l4("C-8a7e36a7", "C-c717092d")
def test_pg_load_memories_adds_tenant_predicate() -> None:
    backend, conn = _backend()

    assert backend._load_memories(["a1"], _TENANT) == []
    sql, params = _statements(conn)[0]
    assert "WHERE id IN (%s) AND tenant_id = %s" in sql
    assert params == ("a1", _TENANT)

    conn.executed.clear()
    assert backend._load_memories(["a1"]) == []
    sql, params = _statements(conn)[0]
    assert "tenant_id =" not in sql
    assert params == ("a1",)


# ---------------------------------------------------------------------------
# Requirement 1.2 — the interim guard is removed, the keyed reads still scope
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-0887e505")
def test_pg_require_global_tenant_is_deleted() -> None:
    assert not hasattr(PostgresBackend, "_require_global_tenant")


@pytest.mark.l4("C-0887e505")
@pytest.mark.parametrize(
    ("name", "invoke", "expected_params"),
    [
        (
            "get_summary",
            lambda backend: backend.get_summary("c", tenant_id=_TENANT),
            ("c", _TENANT),
        ),
        (
            "manifest_get",
            lambda backend: backend.manifest_get("/a", tenant_id=_TENANT),
            ("/a", _TENANT),
        ),
        (
            "manifest_paths",
            lambda backend: backend.manifest_paths("c", tenant_id=_TENANT),
            ("c", _TENANT),
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_pg_keyed_read_keeps_tenant_predicate_without_guard(
    name: str,
    invoke: Callable[[PostgresBackend], object],
    expected_params: tuple[Any, ...],
) -> None:
    backend, conn = _backend()

    _call_without_guard(lambda: invoke(backend))
    statements = _statements(conn)
    assert statements, f"{name} executed no SELECT"
    sql, params = statements[0]
    assert sql.upper().startswith("SELECT"), f"{name}: {sql}"
    assert "tenant_id = %s" in sql, f"{name} has no tenant predicate: {sql}"
    assert params == expected_params, f"{name} parameters: {params}"
