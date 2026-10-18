# Requirements — Multi-Tenancy Postgres Parity

> **Depends on:** the `multi-tenancy` spec (`.kiro/specs/multi-tenancy/`), which
> delivers the data model (`tenant_id` on every model, the `Tenant` model + error
> types), the SQLite schema/backend, the write guard, per-tenant uniqueness, the
> composable storage contracts (`transaction()`, `_on_conn` write variants,
> `memory_exists_with_content`, `list_memories`), and the CLI. This spec brings
> the Postgres backend to the same behaviour and adds the SQLite→Postgres data
> migration. It changes no Pydantic models (the source of truth already carries
> `tenant_id`).

## Introduction

`multi-tenancy` is SQLite-only to keep that unit a feasible, unattended-mergeable
size. This spec mirrors every tenancy change into the Postgres backend so the two
backends are behaviourally identical, and updates `migrate.py` so an existing
SQLite database migrates into a tenant-aware Postgres database.

### Why a separate unit

- Postgres parity + the migrated-Postgres regression test require a Postgres
  service; isolating them means the SQLite unit can merge unattended without one.
- The change set (schema_postgres.sql, storage_postgres.py, migrate.py) is
  self-contained and mechanical once the SQLite behaviour is fixed as the oracle.

### Out of scope

- Any model/`types.py` change (done in `multi-tenancy`).
- Any transport change (CLI/MCP/HTTP).
- New tenancy behaviour — this spec only achieves parity with the SQLite oracle.

---

## Requirements

### Requirement 1 — Postgres schema parity (`schema_postgres.sql`)

#### Acceptance Criteria
1. `schema_postgres.sql` SHALL add the `tenants` table (BOOLEAN `is_active`,
   TIMESTAMP timestamps) and seed `global` via `INSERT ... ON CONFLICT (id) DO
   NOTHING`.
2. It SHALL add `tenant_id TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id)`
   to `memories`, `concept_links`, `memory_summaries`, `query_sessions`,
   `query_results`, `index_manifest`.
3. It SHALL change uniqueness to `UNIQUE (tenant_id, concept)` and
   `UNIQUE (tenant_id, source_memory_id, target_memory_id, link_type)`, and the
   `index_manifest` PK to `(tenant_id, path)`.
4. It SHALL add the tenant-leading indexes mirroring the SQLite set. The
   `content_tsv` generated column + GIN index and the pg_trgm index SHALL be
   unchanged; tenant scoping is a `WHERE tenant_id = ?` on `memories`.

### Requirement 2 — Postgres backend parity (`storage_postgres.py`)

#### Acceptance Criteria
1. The Postgres backend SHALL implement the same write guard
   (`_assert_tenant_writable`), the same `tenant_id` threading on every write and
   read (the exhaustive list from `multi-tenancy` Req 5.1), the same tenant
   predicate injection into its candidate/traversal SQL, and the same tenant
   management methods (`create_tenant`/`get_tenant`/`list_tenants`/
   `set_tenant_active`).
2. The Postgres backend SHALL expose the composable contracts the copy spec uses:
   a `transaction()` context and `_on_conn` no-commit write variants, matching the
   SQLite semantics.
3. The same `TenantError` subtypes SHALL be raised (a Postgres integrity error
   from the FK is caught and re-raised as `TenantNotFoundError`).

### Requirement 3 — Existing-Postgres migration

#### Acceptance Criteria
1. The Postgres backend SHALL provide an idempotent, in-place migration for an
   existing Postgres database (add `tenant_id` columns + backfill to `global`,
   add the `tenants` table + seed, apply the UNIQUE/PK changes), mirroring
   SQLite's `_ensure_tenant_columns`, guarded and idempotent, with the existing
   auto-named `concept UNIQUE` dropped by a rebuild (not by name).
2. A regression test SHALL cover the migrated-Postgres path (skipped when no
   Postgres DSN is configured).

### Requirement 4 — SQLite→Postgres data migration (`migrate.py`)

#### Acceptance Criteria
1. `tenant_id` SHALL be added to `_MEMORIES_COLS`, `_CONCEPT_LINKS_COLS`,
   `_MEMORY_SUMMARIES_COLS`, `_INDEX_MANIFEST_COLS`, `_QUERY_SESSIONS_COLS`,
   `_QUERY_RESULTS_COLS` and the matching `_insert_*_batch` SQL.
2. The `tenants` table SHALL be migrated BEFORE the tables that reference it, and
   added to the bool/datetime/jsonb/pk classification dicts.
3. The pre-seeded `global` row in the Postgres target SHALL be handled on copy
   via `ON CONFLICT (id) DO NOTHING` so the migration does not duplicate/conflict.
4. Checksum verification SHALL still pass with `tenant_id` included.

### Requirement 5 — Tests and gate

#### Acceptance Criteria
1. Postgres parity + migrated-Postgres + `migrate.py` tests SHALL be marked with
   a `postgres` pytest marker, skipped when `MINTMORY_STORAGE_DSN` is unset, so a
   runner without Postgres still passes; a runner with Postgres runs them.
2. The behaviour SHALL match the SQLite oracle: the same scoped-read / write-guard
   / uniqueness / migration assertions, mirrored for Postgres.
3. The full gate SHALL pass: `uv run pytest`, `uv run mypy packages/`,
   `uv run ruff check packages/` all exit 0 with coverage ≥ 80%.
