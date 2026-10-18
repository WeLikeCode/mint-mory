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
   phases `_fts_scores`, `_trigram_scores`, `_vector_scores`, `_load_memories`
   SHALL, for a concrete tenant, add `tenant_id = %s` (on the `memories` row, or
   on `concept_links` for traversal and links) with the tenant as parameter, and
   for `None` execute exactly today's SQL text.
2. `_require_global_tenant` SHALL be removed from every read — including
   `get_summary`, `manifest_get` and `manifest_paths`, which already filter by
   their key since `multi-tenancy-postgres` — and then deleted.
3. Tests (fake pool), for each method: with `tenant_id="t1"` the executed SELECT
   contains `tenant_id = %s` and `"t1"` is among its parameters; with `None` no
   executed SELECT contains `tenant_id =` (the column list may name `tenant_id`;
   the predicate must not appear).

### Requirement 2 — Search

#### Acceptance Criteria

1. `search(request, query_embedding=None, *, tenant_id=None)` SHALL pass the
   tenant to its phases and to the `load_memories_fn`, `search_around_fn` and
   `get_annotating_notes_fn` callables, and pass `tenant_id` and `record_session
   = tenant_id is None or (t is not None and t.is_active)` (with `t =
   self.get_tenant(tenant_id)`) to `fuse_and_search`, as on SQLite.
2. Tests (fake pool): a search with `tenant_id="t1"` whose tenant row is
   inactive executes no INSERT into `query_sessions` / `query_results` and no
   retrieval UPDATE, and returns `session_id == ""`; with an active `t1` it
   inserts a session with `tenant_id` `"t1"`.

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
   and nothing for `"nope"`; a search under an inactive `t1` returns
   `session_id == ""`. Its SQLite leg runs in the L4 job; its Postgres leg in the
   `conformance-pg` CI job.

### Requirement 5 — Gates

#### Acceptance Criteria

1. The `.l4/config.yaml` gates SHALL pass with coverage ≥ 80%. No test needs
   Postgres, Docker or a network service.
