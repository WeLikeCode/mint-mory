# Requirements — Multi-Tenancy 3/10: tenant-scoped reads and search (SQLite)

> **Depends on:** `multi-tenancy` (columns, `get_tenant`, `TENANT_GLOBAL`,
> `_require_global_tenant`) and `multi-tenancy-writes` (`record_query_results`
> same-tenant rule, `_bump_retrieval` skips inactive tenants). Changes
> `storage.py`, `hybrid_search.py`, `ports.py` and the Postgres interim stubs;
> no transport changes (every caller still passes nothing, so behaviour is
> today's).

## Introduction

This unit gives every storage read an optional tenant: `tenant_id: str | None =
None`, where `None` is today's unscoped read over all tenants and a concrete id
confines the read to that tenant in SQL (not by post-filtering). It also scopes
`search` and adds two query-text-free reads the copy needs. The read rule:

- `None` → every tenant; the executed SQL is exactly today's (no predicate).
- `"T"` → only rows with `tenant_id = 'T'`; the predicate is in the candidate
  SQL of every phase, so no other tenant's row reaches fusion.
- An id with no `tenants` row → an empty result (`[]`, `None`, zero counts),
  never an error. Reads never call the write guard.

## Requirements

### Requirement 1 — Exhaustive read signatures (SQLite and Protocol)

#### Acceptance Criteria

1. These methods SHALL take the trailing parameter shown (positional-or-keyword
   unless the method is already keyword-only), with the semantics above:

   | Method (new parameter last) |
   |---|
   | `get_memory(memory_id: str, tenant_id: str \| None = None) -> MemoryRecord \| None` |
   | `search(request: SearchRequest, query_embedding: np.ndarray \| None = None, *, tenant_id: str \| None = None) -> SearchResponse` |
   | `search_around(anchor_ids: list[str], spec: SearchAroundSpec, tenant_id: str \| None = None) -> list[str]` |
   | `get_links(memory_id: str, link_type: ConceptLinkType \| None = None, tenant_id: str \| None = None) -> list[ConceptLink]` |
   | `get_annotating_notes(memory_id: str, cap: int, tenant_id: str \| None = None) -> list[MemoryRecord]` |
   | `get_annotating_descriptions(memory_id: str, cap: int, tenant_id: str \| None = None) -> list[MemoryRecord]` |
   | `find_image_file_record(path_or_rel: str, tenant_id: str \| None = None) -> MemoryRecord \| None` |
   | `anchor_candidates(about: str, limit: int = 5, tenant_id: str \| None = None) -> list[tuple[float, MemoryRecord]]` |
   | `list_image_file_records(tenant_id: str \| None = None) -> list[MemoryRecord]` |
   | `list_notes(*, entity=None, anchor_substr=None, upcoming=False, overdue=False, include_archived=False, limit=50, now=None, tenant_id: str \| None = None) -> list[MemoryRecord]` |
   | `list_summaries(tenant_id: str \| None = None) -> list[MemorySummary]` |
   | `get_session(session_id: str, tenant_id: str \| None = None) -> QuerySession \| None` |
   | `get_stats(tenant_id: str \| None = None) -> MemoryStats` |
   | `memory_exists_with_content(content: str, tenant_id: str \| None = None) -> bool` |
   | `get_flagged_memories(tenant_id: str \| None = None) -> list[MemoryRecord]` |
   | `get_never_accessed_stale(days_old: int = 7, min_staleness: float = 3.0, tenant_id: str \| None = None) -> list[MemoryRecord]` |
   | `get_high_staleness_useful(min_staleness: float = 5.0, min_usefulness: float = 3.0, tenant_id: str \| None = None) -> list[MemoryRecord]` |
   | `get_anomaly_high_staleness_useful_ids(min_staleness: float, min_usefulness: float, tenant_id: str \| None = None) -> list[str]` |
   | `get_anomaly_never_accessed_ids(cutoff_iso: str, tenant_id: str \| None = None) -> list[str]` |
   | `get_anomaly_flagged_ids(tenant_id: str \| None = None) -> list[str]` |
   | `list_active_memory_ids(*, ordered: bool = False, tenant_id: str \| None = None) -> list[str]` |
   | `get_stale_archivable_ids(min_staleness: float, cutoff_iso: str, tenant_id: str \| None = None) -> list[str]` |
   | `get_rehabilitable_rows(cutoff_iso: str, tenant_id: str \| None = None) -> list[tuple[str, float]]` |
   | `get_existing_relates_to_pairs(tenant_id: str \| None = None) -> set[frozenset[str]]` |

   All of these methods already exist on the base branch on `SqliteBackend`, on
   the `StorageBackend` Protocol and on `PostgresBackend` (verified; the dreaming
   helpers were moved out of `dreaming.py` before this plan); this unit only adds
   the parameter and the predicate, never their selection rules.
   `get_summary(concept, tenant_id="global")` and the manifest methods keep the
   concrete key of `multi-tenancy`. With this table every storage read the MCP,
   CLI, API and core functions call has a tenant parameter.
2. WHEN `get_memory(id, tenant_id="t1")` is called for a `global` row THEN it
   SHALL return `None`; with `tenant_id=None` it returns the row (today).
3. `get_stats("t1")` SHALL count only `t1` rows in every field (memories,
   active, stale, archived, `concept_links`, `memory_summaries`, averages,
   `top_concepts`); `get_stats()` counts all tenants (today); `get_stats("nope")`
   returns zero counts, averages `0.0` (today's code maps a `NULL` average to
   `0.0`) and `top_concepts == []`.
4. `list_summaries()` keeps today's `ORDER BY concept`; with a tenant it adds
   `WHERE tenant_id = ?`. Each returned summary carries its `tenant_id`.

### Requirement 2 — Predicate placement and SQL parity

#### Acceptance Criteria

1. With a concrete tenant the predicate `tenant_id = ?` (on the `memories` alias
   or on `concept_links`) SHALL be in the SQL of `_fts_scores`,
   `_trigram_scores`, `_vector_scores` and `_load_memories` (each gains a
   trailing `tenant_id: str | None = None`), in each `search_around` hop (on
   `concept_links`, whose rows are same-tenant by `multi-tenancy-writes`), and in
   every method of R1.1.
2. With `tenant_id=None` the executed SQL SHALL be exactly today's. Test: register
   `conn.set_trace_callback(statements.append)` on `store.connect()`, call every
   read of R1.1 except `search` with `None`, and assert no traced statement
   contains the predicate text `tenant_id =`; call them with `"t1"` and assert
   every traced `SELECT` that reads `memories`, `concept_links`,
   `memory_summaries` or `query_sessions` contains it. (The predicate is written
   exactly `tenant_id = ?`, with an optional table alias.)

### Requirement 3 — Scoped search and its side effects

#### Acceptance Criteria

1. `search(request, query_embedding=None, *, tenant_id=None)` SHALL pass the
   tenant to every candidate phase and bind it into the callables it hands to
   `fuse_and_search` (`load_memories_fn`, `search_around_fn`,
   `get_annotating_notes_fn`). `SearchRequest` is unchanged, so the HTTP body of
   `POST /memories/search` accepts no tenant and the API stays unscoped.
2. `hybrid_search.fuse_and_search` SHALL gain keyword parameters `tenant_id: str
   | None = None` and `record_session: bool = True`. With a concrete tenant it
   SHALL also drop any loaded memory whose `tenant_id` differs
   (defense in depth). It SHALL build the session as `QuerySession(query_text=
   request.query, tenant_id=tenant_id or TENANT_GLOBAL)` and each `QueryResult`
   with the session's `tenant_id`.
3. WHEN `record_session` is `False` THEN `fuse_and_search` SHALL NOT call
   `create_session_fn`, `record_query_results_fn` or `bump_retrieval_fn`, and
   SHALL return `session_id = ""` (`SearchResponse.session_id` is a `str`;
   feedback for `""` fails with today's `session '' not found`). The session
   tenant is `TENANT_GLOBAL if tenant_id is None else tenant_id`.
4. `SqliteBackend.search` SHALL pass `record_session = tenant_id is None or
   (t is not None and t.is_active)` with `t = self.get_tenant(tenant_id)`: a
   search confined to an inactive or missing tenant returns its results (empty
   for a missing tenant) and writes nothing, rather than raising.
5. An unscoped search (`None`) SHALL record a `global` session whose results may
   reference memories of every tenant (the read-audit exemption of
   `multi-tenancy-writes` R2.2) and bump retrieval counts only for active
   tenants' rows.
6. Examples (tenants `global` with g1 "Alice uses Postgres", `t1` with a1 "Alice
   uses SQLite"): `search(SearchRequest(query="Alice"))` returns both and records a
   `global` session with two results; `search(…, tenant_id="t1")` returns only
   the `t1` memory and records a `t1` session; after
   `set_tenant_active("t1", False)` the `t1` search returns the memory, `session_id
   == ""`, and the session/result counts and its `retrieval_count` are
   unchanged; `tenant_id="nope"` returns no memories and `session_id == ""`;
   with `t1` inactive, the unscoped `search(SearchRequest(query="Alice"))`
   returns g1 and a1, records one `global` session with two results, raises g1's
   `retrieval_count` by 1 and leaves a1's unchanged.
7. `search_around(anchors, spec, tenant_id="t1")` SHALL never return a memory
   of another tenant, even when the anchors list holds a foreign id: anchors are
   never part of the output (today's behaviour), and every hop reads only `t1`
   links, so a foreign anchor's links (which belong to its own tenant) are never
   followed. Example: with `g1`→`g2` (`global`) and `a1`→`a2` (`t1`),
   `search_around(["g1", "a1"], SearchAroundSpec(), tenant_id="t1") == ["a2"]`.
8. `anchor_candidates(about, limit, tenant_id)` stays side-effect free, as
   today: it records no session and bumps no counter for any tenant.

### Requirement 4 — Query-text-free list for the copy

#### Acceptance Criteria

1. `list_memories(filter: MemoryFilter | None = None, *, tenant_id: str | None =
   None, limit: int | None = None) -> list[MemoryRecord]` SHALL select `SELECT *
   FROM memories WHERE is_archived = 0` (plus `AND tenant_id = ?` when concrete)
   `ORDER BY created_at, id`, keep the rows for which
   `hybrid_search._passes_filter(mem, filter or MemoryFilter(),
   include_archived=False)` is true (verified on the base branch: it rejects
   `is_active = 0` when `active_only`, and `is_stale = 1` when `exclude_stale`;
   `MemoryFilter` defaults both to `True`), and return the first `limit` of them
   (`None` = all, `0` = `[]`, a negative limit raises `ValueError("limit must be
   >= 0")`).
2. Example: `t1` holds an active fact, a stale fact (`is_stale=1`), an archived
   fact and an inactive fact; `list_memories(tenant_id="t1")` returns the active
   one; `list_memories(MemoryFilter(exclude_stale=False), tenant_id="t1")` returns
   the active and the stale one; `limit=1` returns the oldest;
   `list_memories()` (no tenant) also returns the other tenants' active rows;
   `list_memories(tenant_id="nope")` returns `[]`.
3. `memory_exists_with_content(content, tenant_id="t1")` SHALL be true only when
   a `t1` row has exactly that content.

### Requirement 5 — Protocol and the Postgres interim

#### Acceptance Criteria

1. `ports.py` SHALL declare every signature of R1.1 and `list_memories`.
2. `PostgresBackend` SHALL take the same parameters; each method calls
   `_require_global_tenant(tenant_id, <method name>)` before any pool access, so
   `None` and `"global"` keep today's SQL (every Postgres row is a `global` row
   until `multi-tenancy-postgres`) and any other tenant raises
   `TenancyNotSupportedError`. `PostgresBackend.search` keeps calling
   `fuse_and_search` without the new keywords (their defaults give today's
   `global` session) until `multi-tenancy-postgres-reads`. `PostgresBackend.list_memories` raises
   `TenancyNotSupportedError("list_memories")` until
   `multi-tenancy-postgres-reads`.
3. Test (no database): on `PostgresBackend("postgresql://unused")` a read with
   `tenant_id="t1"` and `list_memories()` raise `TenancyNotSupportedError`
   without opening a connection. These tests go into
   `packages/core/tests/test_pg_tenancy.py`, one `test_pg_<method>_tenancy`
   function per read (for example `test_pg_list_memories_tenancy`), which
   `multi-tenancy-postgres-reads` rewrites in place and never deletes.

### Requirement 6 — Compatibility and gates

#### Acceptance Criteria

1. Every existing caller passes no tenant and every existing test SHALL pass
   unchanged.
2. The gates of `.l4/config.yaml` SHALL pass with coverage ≥ 80%. No test needs
   Postgres, Docker or a network service.
