# Requirements — Multi-Tenancy (Phase 1: foundation)

## Introduction

MintMory is today a single, flat, global memory store: there is no tenant,
owner, workspace, or account concept anywhere in `packages/`, and no auth layer
in any transport. This feature introduces **tenancy as a data-model primitive**
so that memory and all related records can belong to a named tenant, while
remaining **100% backwards compatible**: every existing database, API call, MCP
tool call, and CLI command keeps behaving exactly as it does today by operating
as a reserved **global/default tenant**.

This is Phase 1 — "the basics." It establishes the typed, stored tenant boundary
and the write path into a named tenant, and it makes query-scoping **possible
and opt-in**. It does not change default read/search behaviour (still global)
and does not add authentication or authorization.

### Isolation model (decided)

Row-scoped shared-table isolation: a `tenant_id` column is added to every
table-backed entity; a single database/`.db` file continues to hold all
tenants. Isolation is enforced by query discipline (a tenant predicate), not by
physical database separation. This is the smallest backwards-compatible change
and keeps the "single `.db` file" storage design.

### The global tenant (decided)

- The reserved tenant id is the literal string `global`.
- Every existing row is backfilled to `global` on migration.
- Every operation that does not specify a tenant uses `global`.
- The `global` tenant always exists and cannot be deleted.

### In scope / out of scope (Phase 1)

In scope:
- A typed `tenant_id` on every table-backed model and every table (both SQLite
  and Postgres), with backfill of existing data to `global`.
- A first-class `tenants` table + `Tenant` model so tenant creation is a real,
  auditable operation.
- Writing memories (and derived records) into a named tenant.
- Tenant-scoped uniqueness for `memory_summaries.concept` and `concept_links`.
- A rejection rule for cross-tenant `concept_links`.
- Opt-in query/search scoping: when a tenant is supplied, reads/searches are
  confined to that tenant; when none is supplied, behaviour is global (today's
  behaviour).
- Threading a tenant selector through all three transports (CLI flag, MCP,
  HTTP header), defaulting to `global`.
- Schema-compliance, migration idempotency, and backwards-compatibility tests.

Out of scope (future phases):
- Authentication / authorization / tenant access control.
- Making query-scoping the *default* (reads stay global unless a tenant is given).
- Per-tenant physical isolation (separate `.db` files or Postgres schemas).
- Cross-tenant admin/aggregate views, tenant deletion of non-global tenants,
  quotas, or billing.

---

## Glossary

- **Tenant** — a named partition of memory data, identified by a string
  `tenant_id`.
- **Global tenant** — the reserved tenant with id `global`; the backwards-compatible
  default that owns all pre-existing data and all unscoped operations.
- **Tenant selector** — the value a transport resolves (CLI flag, MCP context/env,
  HTTP header) that determines which tenant an operation targets; absence means
  `global`.
- **Row-scoped isolation** — every row carries `tenant_id` and every query
  filters on it.

---

## Requirements

### Requirement 1 — Tenant is a first-class stored entity

**User story:** As an operator, I want tenants to be real, listable records so
that "manual tenant creation" is an explicit, auditable action rather than a
side effect of writing data.

#### Acceptance Criteria
1. WHEN the schema is initialised THEN the system SHALL provide a `tenants`
   table with at least: `id` (TEXT PRIMARY KEY), `name` (TEXT), `is_active`
   (bool, default true), `created_at`, `updated_at`.
2. WHEN a fresh database is initialised THEN the system SHALL ensure a tenant row
   with `id = "global"` exists (idempotently — initialising twice SHALL NOT
   error or duplicate it).
3. WHEN a caller creates a tenant with a new id THEN the system SHALL insert a
   `tenants` row and return the created `Tenant`.
4. WHEN a caller creates a tenant whose id already exists THEN the system SHALL
   NOT create a duplicate and SHALL surface a clear, deterministic outcome
   (idempotent create or explicit "already exists" — defined in design).
5. WHEN a caller attempts to delete or deactivate the `global` tenant THEN the
   system SHALL reject the operation.
6. The `tenants` table SHALL be represented by a `Tenant` Pydantic model in
   `types.py` (source of truth).

### Requirement 2 — Every table-backed entity is tenant-scoped

**User story:** As a developer, I want every stored record to carry a tenant so
that data can be partitioned and, in future, queried per tenant.

#### Acceptance Criteria
1. WHEN `types.py` is the source of truth THEN each table-backed model
   (`MemoryRecord`, `ConceptLink`, `MemorySummary`, `QuerySession`,
   `QueryResult`, and the `index_manifest`-backed carrier) SHALL carry a
   `tenant_id: str` field defaulting to `global`.
2. WHEN a record is created without an explicit tenant THEN the system SHALL
   persist it with `tenant_id = "global"`.
3. WHEN a record references another record (FK: `concept_links` -> `memories`,
   `query_results` -> `query_sessions`/`memories`, `memories.superseded_by`)
   THEN both ends SHALL belong to the same tenant.
4. The `tenant_id` column SHALL exist in BOTH `schema.sql` and
   `schema_postgres.sql`, with a foreign key to `tenants(id)`.
5. The source-of-truth order `types.py > schema.sql > openapi.yaml` SHALL be
   followed: `types.py` is edited first, then both schema files, then the
   OpenAPI spec.

### Requirement 3 — Backwards compatibility with existing databases

**User story:** As an existing user, I want my current `.db` to keep working
unchanged after upgrading, so that no data is lost and nothing I do today breaks.

#### Acceptance Criteria
1. WHEN an existing database created before this feature is opened THEN
   `initialise()` SHALL add the `tenant_id` column to every pre-existing table
   and backfill every pre-existing row to `tenant_id = "global"`.
2. WHEN the column-add migration runs twice on the same database THEN the second
   run SHALL be a no-op (idempotent), following the existing `_ensure_*` pattern
   in `StorageAdapter`.
3. WHEN a user performs any operation available today without mentioning a tenant
   (add, get, search, link, feedback, dream, stats, notes, summaries, images)
   THEN the observable result SHALL be identical to pre-feature behaviour.
4. WHEN the migration cannot run (locked/old SQLite) THEN it SHALL degrade
   gracefully without crashing startup, consistent with existing migrations.
5. A regression test SHALL open a pre-feature-shaped database, run
   `initialise()`, and assert all rows are readable and attributed to `global`.

### Requirement 4 — Writing into a named tenant

**User story:** As an operator, I want to write memories into a specific tenant
so that I can start partitioning data ahead of query-scoping.

#### Acceptance Criteria
1. WHEN a caller adds a memory with an explicit `tenant_id` THEN the system SHALL
   persist that memory (and any derived records it creates) under that tenant.
2. WHEN a caller writes to a `tenant_id` that does not exist in `tenants` THEN
   the system SHALL reject the write with a clear error (no implicit tenant
   creation), preserving FK integrity.
3. WHEN a memory is written under tenant T THEN its FTS/trigram/vector index
   entries SHALL remain correct and the memory SHALL be retrievable when
   querying is scoped to T.

### Requirement 5 — Opt-in query and search scoping

**User story:** As a developer, I want the ability to confine reads and searches
to a tenant, while leaving default behaviour global, so the foundation is usable
without changing anything for existing callers.

#### Acceptance Criteria
1. WHEN a read/search is issued WITHOUT a tenant selector THEN the system SHALL
   behave as today (global, across all rows regardless of `tenant_id`).
2. WHEN a read/search is issued WITH tenant selector T THEN the candidate SQL
   phases (`_fts_scores`, `_trigram_scores`, `_vector_scores`, `_load_memories`)
   and `search_around` graph traversal SHALL be constrained to rows where
   `tenant_id = T`.
3. WHEN search-around traverses links under tenant T THEN it SHALL NOT include
   memories from any other tenant (no cross-tenant leakage via graph traversal).
4. The tenant predicate SHALL be applied in the candidate SQL (not only in the
   Python-side `_passes_filter`), so filtering is enforced before fusion, with
   `_passes_filter` as optional defense-in-depth.
5. `get_stats` and dreaming helper queries SHALL support the same opt-in scoping:
   unscoped = global counts (today), scoped = per-tenant counts.

### Requirement 6 — Tenant-scoped uniqueness and link integrity

**User story:** As a developer, I want per-tenant uniqueness so that two tenants
can both have a summary for the same concept and equivalent links without
collision or leakage.

#### Acceptance Criteria
1. The `memory_summaries` uniqueness SHALL become per-tenant: unique on
   `(tenant_id, concept)` instead of global `concept`.
2. The `concept_links` uniqueness SHALL become per-tenant: unique on
   `(tenant_id, source_memory_id, target_memory_id, link_type)`.
3. WHEN a caller attempts to create a `concept_link` whose source and target
   belong to different tenants THEN the system SHALL reject it.
4. The upsert paths (`upsert_summary` ON CONFLICT, `add_link` INSERT OR IGNORE /
   ON CONFLICT) SHALL key on the new per-tenant unique constraints and remain
   idempotent (dreaming idempotency preserved).

### Requirement 7 — Transport tenant selectors

**User story:** As a user of the CLI, MCP, and HTTP transports, I want to choose
a tenant per operation, defaulting to global, so I can use the new capability
through the interface I already use.

#### Acceptance Criteria
1. WHEN a CLI command runs without a tenant flag THEN it SHALL operate on
   `global`; WHEN run with `--tenant T` THEN it SHALL operate on T.
2. WHEN an MCP tool is called without a tenant argument/context THEN it SHALL
   operate on `global`; WHEN a tenant is supplied THEN it SHALL operate on that
   tenant.
3. WHEN an HTTP request omits the tenant header THEN it SHALL operate on
   `global`; WHEN it sends the tenant header (e.g. `X-Tenant-ID`) THEN it SHALL
   operate on that tenant.
4. WHEN any transport receives a tenant selector referencing a non-existent
   tenant for a write THEN it SHALL return a clear error (consistent with
   Requirement 4.2).
5. Transport changes SHALL go through the single `build_storage()` /
   core-function chokepoint; no transport SHALL duplicate domain logic.

### Requirement 8 — Schema compliance, interface spec, and tests

**User story:** As a maintainer, I want the tenancy changes to satisfy the
non-negotiable schema gate and the interface spec so the three sources of truth
stay in sync.

#### Acceptance Criteria
1. `packages/core/tests/test_schema.py` SHALL be extended so the new `tenants`
   table, the `tenant_id` columns, and any new indexes are required and verified.
2. The enum↔CHECK parity, FK enforcement, and FTS trigger assertions SHALL
   continue to pass unchanged.
3. `docs/openapi/mintmory.yaml` SHALL be updated (last, per the hierarchy) to add
   a tenant parameter/field to the relevant operations and schemas, including a
   `Tenant` schema and a tenant-create operation.
4. The SQLite→Postgres migration (`migrate.py`) column tuples and insert SQL
   SHALL include `tenant_id` and the `tenants` table so migration + checksum
   verification still pass.
5. WHEN the full suite runs THEN `uv run pytest`, `uv run mypy packages/`, and
   `uv run ruff check packages/` SHALL all exit 0 with coverage >= 80%.
