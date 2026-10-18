# Requirements — Multi-Tenancy (Phase 1: foundation)

## Introduction

MintMory is today a flat, global store (no tenant concept, no auth). This feature
adds **tenancy as a data-model primitive** so records can belong to a named
tenant, while staying **100% backwards compatible**: everything behaves exactly
as today by operating as the reserved `global` tenant. Phase 1 = the typed tenant
boundary, the named-tenant write path, and opt-in read scoping (SQLite + core +
CLI). No auth.

### Read vs write tenant semantics (authoritative — resolves the absent-selector contradiction)

Two distinct notions, never conflated:
- **Reads/searches** take `tenant_id: str | None`. `None` = unscoped (all rows,
  today). `"T"` = confined to tenant T.
- **Writes** always persist a concrete `tenant_id`; unspecified = `"global"`.

So the global tenant = reads pass `None`, writes stamp `"global"`. A transport
MUST NOT pass literal `"global"` into a read (it would confine to global-only
rows and break backwards compat, Req 3.3).

### Isolation model

Row-scoped shared-table: a `tenant_id` column on every table-backed entity; one
DB holds all tenants. Isolation = a tenant predicate in candidate SQL + an
application-level write guard (SQLite cannot add a FK via `ALTER TABLE ADD
COLUMN`, so the guard, not the FK alone, enforces tenant-exists — Req 4). The
reserved id is `global`; existing rows backfill to it; it can be neither deleted
nor deactivated.

### Ownership boundaries (resolves cross-unit conflicts)

- **This spec owns:** data model, `schema.sql` (SQLite), SQLite storage
  signatures + write guard + composable contracts, per-tenant uniqueness, the
  `tenants` table + `Tenant`, SQLite migration, schema-only OpenAPI, and the
  **CLI** `--tenant` + `tenant create`/`tenant list`.
- **NOT this spec:** any MCP tool change / MCP tenant tools (→ `tenant-scoped-mcp`;
  MCP stays global here); the `DreamingEngine` CONSTRUCTOR `tenant_id` scope and
  the dream-all loop (→ `cross-tenant-copy-and-dreaming`). This spec DOES add a
  `tenant_id` read argument to the dreaming helper QUERIES and to the read-only
  job collectors (`DreamingEngine.collect_summary_jobs`, `vision.image_jobs`) —
  adding a read parameter is not the same as scoping the engine's run, which the
  copy spec owns. Postgres + `migrate.py` → `multi-tenancy-postgres`.

### Error contract (resolves "clear error" ambiguity)

One typed surface in `types.py`: `TenantError` base + `TenantNotFoundError`
(write to / scope to a missing tenant), `TenantInactiveError` (write to an
inactive tenant), `ProtectedTenantError` (deactivate `global`),
`InvalidTenantIdError` (bad id; subclasses `ValueError`), `CrossTenantLinkError`
(cross-tenant reference), `TenantImmutableError` (`update_memory` changing a
record's tenant), and `ScopeRequiredError` (reserved for the copy spec). A
backend FK `IntegrityError` is caught and re-raised as `TenantNotFoundError`. The
CLI maps each to a non-zero exit + message; the design table gives the HTTP codes
the HTTP/copy specs map.

### Scope (Phase 1, SQLite + core + CLI)

In scope: `tenant_id` on every model + the SQLite schema (backfilled to
`global`); the `tenants` table + `Tenant`; guarded named-tenant writes; per-tenant
uniqueness + same-tenant references; opt-in read scoping (`None` = today); the
CLI tenant surface; schema/migration/back-compat tests.

Out of scope: Postgres parity + `migrate.py` (→ `multi-tenancy-postgres`, which
depends on this and needs a Postgres service this unattended unit may lack); auth;
the MCP tenant surface (→ `tenant-scoped-mcp`); the `DreamingEngine` scope /
dream-all loop (→ `cross-tenant-copy-and-dreaming`); physical isolation; quotas.

---

## Glossary

- **Tenant** — a named data partition, id `^[a-z0-9][a-z0-9_-]{0,127}$`.
- **Global tenant** — reserved id `global`; read = `None`, write = `"global"`.
- **Write guard** — the per-write check that the tenant exists and is active.

---

## Requirements

### Requirement 1 — Tenant is a first-class stored entity

**User story:** As an operator, I want tenants to be real, listable records so
tenant creation is explicit and auditable.

#### Acceptance Criteria
1. The `tenants` table SHALL have `id` (TEXT PK), `name` (TEXT NOT NULL DEFAULT
   ''), `is_active` (bool, default true), `created_at`, `updated_at`.
2. A fresh DB SHALL seed `id = "global"` idempotently (a second initialise does
   not error or duplicate).
3. `create_tenant(tenant_id: str, name: str = "") -> Tenant` takes STRINGS (not
   a `Tenant` model, so the model validator never fires ahead of the method): it
   validates the id (raising `InvalidTenantIdError` directly), then `INSERT OR
   IGNORE` / `ON CONFLICT DO NOTHING`, then `SELECT` and return.
4. WHEN `create_tenant` is called with an existing id THEN it SHALL be
   idempotent: no duplicate, return the existing `Tenant`, no error. Concurrent
   calls converge to one row.
5. WHEN a caller attempts to deactivate the `global` tenant (via
   `set_tenant_active("global", False)`) THEN the system SHALL raise
   `ProtectedTenantError`. There is NO delete method in Phase 1; "delete" in the
   user story is satisfied by the absence of a delete API plus the deactivate
   guard (no tenant can be hard-deleted).
6. `InvalidTenantIdError` SHALL subclass `ValueError`. The `Tenant` model's id
   field validator SHALL raise it too; because `create_tenant` takes a string and
   validates before constructing the model, the method raises the plain
   `InvalidTenantIdError` (not wrapped in a Pydantic `ValidationError`).
7. The `tenants` table SHALL be represented by a `Tenant` Pydantic model in
   `types.py`. `Tenant.created_at`/`updated_at` default via `datetime.utcnow`;
   the SQL seed of `global` uses a fixed sentinel timestamp
   (`'1970-01-01T00:00:00'`). Tests SHALL compare tenant identity and `is_active`,
   NOT the timestamp value (the seed is a floor).
8. `get_tenant(tenant_id: str) -> Tenant | None` and `list_tenants() ->
   list[Tenant]` (all tenants, active and inactive, ordered by `id`) SHALL be the
   read methods. `set_tenant_active(tenant_id: str, active: bool) -> Tenant`
   raises `TenantNotFoundError` for an unknown id and `ProtectedTenantError` for
   deactivating `global`.

### Requirement 2 — Every table-backed entity is tenant-scoped

**User story:** As a developer, I want every stored record to carry a tenant.

#### Acceptance Criteria
1. Each table-backed model (`MemoryRecord`, `ConceptLink`, `MemorySummary`,
   `QuerySession`, `QueryResult`, and the `ManifestEntry` carrier) SHALL carry
   `tenant_id: str` defaulting to `global`.
2. WHEN a record is created without an explicit tenant THEN the system SHALL
   persist it with `tenant_id = "global"`.
3. A record reference SHALL keep both ends in the same tenant — enforced/tested
   for `concept_links.source↔target`, `query_results↔query_sessions`/`memories`,
   and `memories.superseded_by`; a cross-tenant reference raises
   `CrossTenantLinkError`. `update_memory` changing a record's own `tenant_id`
   raises `TenantImmutableError`.
4. The `tenant_id` column SHALL exist in `schema.sql` (SQLite) as `tenant_id
   TEXT NOT NULL DEFAULT 'global'`. On a freshly created schema and on any table
   rebuilt during migration (Req 6), it SHALL also carry `REFERENCES tenants(id)`.
   On a pre-existing table where the column is added via `ALTER TABLE ADD COLUMN`
   (which SQLite forbids combining with a FK), the write guard (Req 4.2) provides
   the equivalent protection. (The matching `schema_postgres.sql` change is in
   `multi-tenancy-postgres`; `types.py` — the source of truth — still carries
   `tenant_id` on every model here, so both backends agree on the model.)
5. The source-of-truth order `types.py > schema.sql > openapi.yaml` SHALL be
   followed.

### Requirement 3 — Backwards compatibility with existing databases

**User story:** As an existing user, I want my database to keep working after
upgrading.

#### Acceptance Criteria
1. WHEN an existing pre-feature database is opened THEN `initialise()` SHALL add
   the `tenant_id` column to every pre-existing table and backfill every
   pre-existing row to `tenant_id = "global"`.
2. WHEN the migration runs twice THEN the second run SHALL be a no-op
   (idempotent), following the existing `_ensure_*` pattern.
3. WHEN a user performs any pre-existing operation with no tenant (add, get,
   search, link, feedback, dream, stats, notes, summaries, images) THEN the
   observable result SHALL be identical to pre-feature behaviour (reads pass
   `None`; writes stamp `"global"`).
4. WHEN the migration cannot run (locked/old SQLite) THEN it SHALL degrade
   gracefully without crashing startup.
5. Schema initialisation SHALL be ordered so it never fails on a pre-feature DB:
   the tenant-leading INDEXES (e.g. `idx_memories_tenant`) SHALL NOT be created by
   a path that runs before the `tenant_id` columns exist — index creation on
   `tenant_id` happens inside/after `_ensure_tenant_columns`. The `tenants` TABLE
   and its `global` seed, by contrast, have no dependency on any `tenant_id`
   column, so `schema.sql` is their sole creator+seeder and may run them first;
   `_ensure_tenant_columns` never re-creates/re-seeds `tenants`.
6. A regression test SHALL open a pre-feature-shaped SQLite database (tables
   without `tenant_id`), run `initialise()`, and assert: columns added, all rows
   readable and attributed to `global`, indexes present, and a second
   `initialise()` is a no-op. (The equivalent Postgres migrated-path test is in
   `multi-tenancy-postgres`.)

### Requirement 4 — Writing into a named tenant (with a write guard)

**User story:** As an operator, I want to write into a specific tenant, with
writes to a missing or inactive tenant rejected.

#### Acceptance Criteria
1. WHEN a caller adds a memory (or any derived record) with an explicit
   `tenant_id` THEN the system SHALL persist it under that tenant.
2. WHEN a write targets a `tenant_id` not present in `tenants` THEN the system
   SHALL raise `TenantNotFoundError` and write nothing. This guard SHALL run as
   an explicit application-level check on EVERY write path (add_memory,
   update_memory, archive_memory, supersede_memory, add_link, create_session,
   record_query_results, apply_feedback, upsert_summary, note/image writes) and
   SHALL hold identically on SQLite (where there may be no FK on migrated tables)
   and Postgres.
3. WHEN a write targets a tenant whose `is_active = false` THEN the system SHALL
   raise `TenantInactiveError` and write nothing. Reads of an inactive tenant are
   permitted (read-only). A search that WOULD write (recording a `QuerySession` /
   `query_results`, or bumping access counts) under an inactive tenant SHALL skip
   those side-effect writes (return results, write nothing) rather than raise —
   the read succeeds, the incidental write is suppressed.
4. For the id-only writes (`archive_memory`, `supersede_memory`, `apply_feedback`)
   the write guard checks the STORED ROW's tenant: with `tenant_id=None` the
   operation acts on the row by id and the guard uses that row's tenant (so
   archiving a row in an inactive tenant raises `TenantInactiveError`); with a
   concrete `tenant_id` the row must also match it or the op is not-found.
5. Session side-effects of an UNSCOPED search (`tenant_id=None`) are exempt from
   the same-tenant reference rule: the `QuerySession` such a search records is
   stamped `"global"`, and its `query_results` MAY reference memories of ANY
   tenant (an unscoped search is a cross-tenant read-audit record, not a semantic
   link; the `CrossTenantLinkError` rule of Req 2.3 applies only to a session
   whose own `tenant_id` is a NAMED tenant, where every referenced memory must
   share it). An unscoped search MAY bump retrieval/access counts on rows in any
   tenant; it skips those incidental writes only for rows whose tenant is
   inactive. A search confined to tenant T records a T session referencing only T
   memories.
5. WHEN a memory is written under tenant T THEN its FTS/trigram/vector index
   entries SHALL remain correct and the memory SHALL be retrievable by a read
   confined to T.

### Requirement 5 — Opt-in read/search scoping (concrete signatures)

**User story:** As a developer, I want to confine reads/searches to a tenant via a
concrete, testable signature, while `None` keeps today's behaviour.

#### Acceptance Criteria
1. The following storage methods SHALL gain a trailing optional parameter
   `tenant_id: str | None = None` with `None` = unscoped (today) and a concrete
   value = confined — this list is exhaustive so the dependent MCP spec can scope
   EVERY tool: `get_memory`, `search`, `search_around`, `get_stats`,
   `list_notes`, `get_annotating_notes`, `get_annotating_descriptions`,
   `list_image_file_records`, `find_image_file_record`, `anchor_candidates`,
   `get_links`, `list_summaries`, `get_summary`, `get_session`,
   the manifest reads (`manifest_get`/`manifest_paths`), the cochange queries
   (`changed_with` / `documents_timeline`), the summary-job collector, the
   image-job collector, and every dreaming helper (`get_flagged_memories`,
   `get_never_accessed_stale`, `get_high_staleness_useful`, the anomaly getters,
   `list_active_memory_ids`, `get_stale_archivable_ids`, `get_rehabilitable_rows`,
   `get_existing_relates_to_pairs`). `SearchRequest` and `MemoryFilter` SHALL
   also carry `tenant_id: str | None = None`; when both the method arg and the
   request field are present, the explicit method arg wins (documented).
2. WHEN `get_memory(id, tenant_id="T")` is called for an id belonging to another
   tenant THEN it SHALL return `None` (not-found), never another tenant's record.
   WHEN called with `tenant_id=None` it SHALL behave as today (global by id).
3. WHEN a read/search is confined to T THEN the predicate `tenant_id = ?` SHALL
   be applied in the candidate SQL phases (`_fts_scores`, `_trigram_scores`,
   `_vector_scores`, `_load_memories`) and in each `search_around` hop, so no
   other-tenant row reaches fusion. `_passes_filter` checks `MemoryFilter.tenant_id`
   as defense-in-depth.
4. WHEN a read/search uses `tenant_id = None` THEN the emitted SQL SHALL be
   byte-for-byte today's SQL (no predicate), guaranteeing parity.
5. `get_stats` and the dreaming helpers SHALL honour the same rule: `None` =
   global counts (today); a concrete value = per-tenant counts/rows. The ONE
   deliberate exception to "never pass literal `global` to a read" is a dreaming
   engine scoped to the `global` tenant: it passes `"global"` to its own read
   helpers so the global tenant dreams only over its own rows (owned by
   `cross-tenant-copy-and-dreaming`). Ordinary (non-dreaming) reads still use
   `None` for "all rows"; only dreaming confines per tenant.
6. Concept/key disambiguation under per-tenant uniqueness: `get_summary(concept,
   tenant_id)` and `upsert_summary` conflict-target SHALL key on `(tenant_id,
   concept)`. Because `concept` is unique only per tenant, a by-concept GET needs
   a tenant: `get_summary(concept, tenant_id=None)` returns the `global`-tenant
   row if present else `None` (it never guesses among tenants). To read ACROSS
   tenants (e.g. a global-scope agent), use `list_summaries(tenant_id=None)`,
   which returns every tenant's summaries unrestricted; a global-scope MCP
   `summary_get` therefore resolves via `list_summaries` filtered by concept when
   it needs a non-global tenant's summary, not via the by-concept global get. A
   named scope T uses `get_summary(concept, "T")`. `get_session(id,
   tenant_id=None)` is by unique id; a concrete tenant adds `AND tenant_id = ?`.
7. A read/search confined to a tenant that does not exist SHALL return empty
   (not raise) — reads never assert tenant existence; only writes do (Req 4.2).
   A CLI `--tenant <missing> search` therefore returns no results, not an error.
8. New composable storage contracts this spec SHALL add (committed for the copy
   spec): `memory_exists_with_content(content, tenant_id: str | None = None)`;
   `list_memories(filter=None, tenant_id=None, limit=None) -> list[MemoryRecord]`
   (query-text-free); a `transaction()` context on the SQLite backend (exposed via
   `ports.py`) + `_on_conn` no-commit write variants so a caller can compose
   writes atomically. (Postgres equivalents are in `multi-tenancy-postgres`.)

### Requirement 6 — Tenant-scoped uniqueness and link integrity

**User story:** As a developer, I want per-tenant uniqueness so two tenants can
hold a summary for the same concept and equivalent links without collision.

#### Acceptance Criteria
1. `memory_summaries` uniqueness SHALL become `UNIQUE (tenant_id, concept)`.
2. `concept_links` uniqueness SHALL become `UNIQUE (tenant_id, source_memory_id,
   target_memory_id, link_type)`.
3. WHEN `add_link` is given endpoints in different tenants THEN it SHALL raise
   `CrossTenantLinkError`.
4. The upsert paths (`upsert_summary` ON CONFLICT, `add_link` INSERT OR IGNORE /
   ON CONFLICT) SHALL key on the new per-tenant unique constraints and remain
   idempotent per tenant.
5. `index_manifest`'s PK SHALL change from `path` to `(tenant_id, path)` so two
   tenants can index the same path. Manifest methods gain `tenant_id: str | None
   = None`; `manifest_delete(path, tenant_id=None)` deletes that path for the
   `global` tenant only.
6. On a pre-existing DB, changing these UNIQUE/PK constraints
   (`memory_summaries`, `concept_links`, `index_manifest`) SHALL use the guarded,
   idempotent table rebuild (`_ensure_index_mode_vision` pattern); rebuilt tables
   carry the `tenant_id` FK.

### Requirement 7 — CLI tenant selector (this spec's only transport)

**User story:** As a CLI user, I want to choose a tenant per command, defaulting
to global.

#### Acceptance Criteria
1. WHEN a CLI command runs without `--tenant` THEN it SHALL use global semantics
   (reads pass `None`, writes stamp `"global"`); WHEN run with `--tenant T` THEN
   reads are confined to T and writes stamp T.
2. The CLI SHALL add `tenant create <id> [--name]` and `tenant list` commands.
3. WHEN a CLI command targets a non-existent/inactive tenant for a write THEN it
   SHALL exit non-zero with the mapped `TenantError` message.
4. CLI changes SHALL go through `build_storage()` and core functions; no domain
   logic in the CLI.
5. MCP/HTTP tenant selectors are NOT in this spec (→ `tenant-scoped-mcp` / a
   future HTTP spec); MCP and HTTP stay global until those land, and this spec
   adds no per-call tenant argument to any MCP tool.

### Requirement 8 — Schema compliance, interface spec, and tests

**User story:** As a maintainer, I want the changes to satisfy the schema gate and
keep the three sources of truth in sync.

#### Acceptance Criteria
1. `test_schema.py` SHALL be extended: `tenants` in REQUIRED_TABLES; `tenant_id`
   in the REQUIRED column sets for memories, concept_links, query_sessions,
   memory_summaries, query_results, manifest; tenant-leading indexes in
   REQUIRED_INDEXES. Enum↔CHECK parity, FK, and FTS trigger assertions keep
   passing unchanged.
2. `docs/openapi/mintmory.yaml` SHALL be updated (last) with SCHEMA ADDITIONS
   ONLY: a `Tenant` schema + optional `tenant_id` on the schemas the API already
   uses (`MemoryRecord`, `MemoryCreate`, `MemoryFilter`, `SearchRequest`,
   `ConceptLink`, `ConceptLinkCreate`, `MemorySummary`, `QuerySession`). NO
   `POST /tenants` / `GET /tenants` paths and NO `X-Tenant-ID` header — the HTTP
   API stays global; OpenAPI must not document routes no code serves. Tenant
   create/list is CLI-only this phase.
3. Postgres + `migrate.py` → `multi-tenancy-postgres`; this spec touches only
   `schema.sql` and the SQLite backend.
4. WHEN the full suite runs THEN `uv run pytest`, `uv run mypy packages/`, and
   `uv run ruff check packages/` SHALL all exit 0 with coverage >= 80% (no
   Postgres tests here).
