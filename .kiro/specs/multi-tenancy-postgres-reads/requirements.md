# Requirements — Multi-Tenancy 10/10: Postgres tenant-scoped reads and search

> **Depends on:** `multi-tenancy-postgres-writes` (`_conn()`, the tenant
> directory and write guard on Postgres, `pg_fakes.py`), `multi-tenancy-reads`
> (the read signatures and semantics this unit reproduces: its R1.1 table,
> search side effects, `list_memories`) and `multi-tenancy-postgres` (the
> `tenant_id` column and indexes). Changes `storage_postgres.py` and tests only;
> the signatures already match the Protocol.

## Introduction

The last tenancy unit removes the Postgres interim entirely: every Postgres read
honours `tenant_id` exactly as SQLite does — `None` is today's SQL over every
tenant, a concrete id confines the SQL, an unknown id gives an empty result —
and `search` and `list_memories` behave as in `multi-tenancy-reads`. After it,
`_require_global_tenant` no longer exists.

Proof without a database in the L4 job: fake-pool tests assert SQL text and
parameters; backend-agnostic conformance tests run on SQLite in the L4 job and
on a real Postgres in the `conformance-pg` CI job (supplementary). No skip,
skipif or xfail marker and no `pytest.skip(` call SHALL be added.

## Requirements

### Requirement 1 — Every read is tenant-aware

#### Acceptance Criteria

1. The Postgres implementations of every method in the R1.1 table of
   `multi-tenancy-reads` (`get_memory`, `search`, `search_around`, `get_links`,
   `get_annotating_notes`, `get_annotating_descriptions`,
   `find_image_file_record`, `anchor_candidates`, `list_image_file_records`,
   `list_notes`, `list_summaries`, `get_session`, `get_stats`,
   `memory_exists_with_content`, the ten dreaming helpers) and of the private
   phases, which gain the same trailing parameter as on SQLite —
   `_fts_scores(query, limit, tenant_id=None)`, `_trigram_scores(query, limit,
   tenant_id=None)`, `_vector_scores(query, query_embedding, limit,
   tenant_id=None)`, `_load_memories(ids, tenant_id=None)` — SHALL, for a
   concrete tenant, add `tenant_id = %s` with the tenant as parameter on the
   table each statement reads (`memories`; `concept_links` for traversal, links
   and the link count; `query_sessions` for `get_session`; `memory_summaries` for
   `list_summaries` and the summary count), qualified with the statement's
   existing alias where it joins (for example `m.tenant_id = %s`), and for `None`
   execute exactly today's SQL text. They run on `self._conn()` (since
   `multi-tenancy-postgres-writes`), so inside a `transaction()` they see its
   rows.
2. `_require_global_tenant` SHALL be removed from every read — including
   `get_summary`, `manifest_get` and `manifest_paths`, which already filter by
   their key since `multi-tenancy-postgres` — and then deleted.
   `TenancyNotSupportedError` stays in `types.py` (public error surface). The
   read `test_pg_<method>_tenancy` functions of
   `packages/core/tests/test_pg_tenancy.py` (from `multi-tenancy-reads`, among
   them `test_pg_list_memories_tenancy`) SHALL be rewritten in place — same
   names, fake pool — to assert R1.3; none is deleted (an L4 integrity
   blocker).
3. Tests (fake pool), for each method: with `tenant_id="t1"` the executed SELECT
   contains `tenant_id = %s` and `"t1"` is among its parameters; with `None` no
   executed SELECT contains `tenant_id =` (the column list may name `tenant_id`;
   the predicate must not appear). The responder returns `[]` for list reads,
   `[(0,)]` for every `COUNT(*)` and `[(None, None)]` for the averages of
   `get_stats` (it reads `fetchone()[0]`). The private phases are called
   directly; the vector phase is called with `backend._vec_available = True` and a
   `query_embedding` of `numpy.zeros(8, dtype=numpy.float32)`.

### Requirement 2 — Search

#### Acceptance Criteria

1. `search(request, query_embedding=None, *, tenant_id=None)` SHALL pass the
   tenant to its phases and to the `load_memories_fn`, `search_around_fn` and
   `get_annotating_notes_fn` callables, and pass `tenant_id` and `record_session
   = tenant_id is None or (t is not None and t.is_active)` (with `t =
   self.get_tenant(tenant_id)`) to `fuse_and_search`, as on SQLite.
2. Tests (fake pool), `SearchRequest(query="Alice")`: the responder answers the
   FTS phase with `[("a1", 0.5)]` (it reads `row[0]`, `row[1]`), `_load_memories`
   with one memory row dict for `a1` with `tenant_id` `"t1"`, and the tenant
   lookup with the tenant's row dict; the trigram and vector phases are off
   (`_trgm_available` and `_vec_available` stay `False`). With `t1` inactive: no INSERT into `query_sessions` /
   `query_results`, no retrieval UPDATE, `session_id == ""`, and `a1` returned;
   with `t1` active: a session INSERT whose parameters include `"t1"`; with a
   tenant `nope` that has no row: no INSERT, `session_id == ""`.

### Requirement 3 — `list_memories`

#### Acceptance Criteria

1. `list_memories(filter=None, *, tenant_id=None, limit=None)` SHALL run `SELECT
   {_SELECT_MEMORY} FROM memories WHERE is_archived = FALSE` (plus `AND tenant_id
   = %s`) `ORDER BY created_at, id`, keep the rows for which
   `_passes_filter(mem, filter or MemoryFilter(), include_archived=False)` holds,
   and return the first `limit` (`None` all, `0` none, negative →
   `ValueError("limit must be >= 0")`). The interim stub is removed.
2. Test (fake pool): rows returned by the responder are filtered and limited as
   in `multi-tenancy-reads` R4.2.

### Requirement 4 — Conformance tests (supplementary)

#### Acceptance Criteria

1. `packages/core/tests/conformance/test_tenancy_reads.py` SHALL use the
   existing `backend` fixture and only Protocol methods: with memories in
   `global` and `t1`, `get_memory`, `search`, `get_stats`, `list_memories` and
   `search_around` return only `t1` rows for `"t1"`, both tenants for `None`,
   and nothing for `"nope"`; `search_around(["g1", "a1"], SearchAroundSpec(),
   tenant_id="t1")` returns only `t1` neighbours; a search under an inactive `t1`
   returns `session_id == ""`. Its SQLite leg runs in the L4 job; its Postgres leg
   in the `conformance-pg` CI job.

### Requirement 5 — Gates

#### Acceptance Criteria

1. The `.l4/config.yaml` gates SHALL pass with coverage ≥ 80%. No test needs
   Postgres, Docker or a network service.
