# Design — Multi-Tenancy Postgres Parity

> **Depends on:** `multi-tenancy` (`.kiro/specs/multi-tenancy/`). The SQLite
> backend built there is the behavioural oracle; this spec mirrors it into
> Postgres and adds the data migration. No model/`types.py` changes.

## Overview

Three edits, all mechanical given the SQLite oracle:
1. `schema_postgres.sql` — mirror the `tenants` table, `tenant_id` columns + FK,
   per-tenant UNIQUE, the `(tenant_id, path)` manifest PK, and tenant-leading
   indexes.
2. `storage_postgres.py` — mirror the write guard, `tenant_id` threading on the
   exhaustive read/write set, the predicate injection, the tenant management
   methods, and the `transaction()` + `_on_conn` contracts.
3. `migrate.py` — add `tenant_id` to the per-table column tuples and inserts, add
   the `tenants` table first, handle the pre-seeded `global` row.

## Grounding

`schema_postgres.sql` today mirrors the SQLite tables with `BOOLEAN`/`FLOAT`/
`JSONB`/`TIMESTAMP`/`vector`, a `content_tsv` generated column + GIN index and a
pg_trgm GIN index (no FTS5 triggers). `storage_postgres.py` implements the
`StorageBackend` protocol structurally. `migrate.py` is a one-shot SQLite→Postgres
copy with hard-coded `_*_COLS` tuples, `_insert_*_batch` functions, and
bool/datetime/jsonb/pk classification dicts + checksum verification.

## Schema (`schema_postgres.sql`)

Mirror of the SQLite schema (`multi-tenancy` design), with Postgres types:
`tenants(id TEXT PK, name TEXT NOT NULL DEFAULT '', is_active BOOLEAN NOT NULL
DEFAULT true, created_at TIMESTAMP, updated_at TIMESTAMP)` seeded via `ON
CONFLICT (id) DO NOTHING`; `tenant_id TEXT NOT NULL DEFAULT 'global' REFERENCES
tenants(id)` on the six tables; the two per-tenant UNIQUE constraints; the
`(tenant_id, path)` manifest PK; the tenant-leading indexes. `content_tsv` + its
GIN index and the pg_trgm index are untouched; tenant scoping is `WHERE
tenant_id = ?` on `memories`.

## Backend (`storage_postgres.py`)

Mirror the SQLite backend behaviour exactly:
- `_assert_tenant_writable(conn, tenant_id)` at the top of every write; a
  Postgres FK integrity error is caught and re-raised as `TenantNotFoundError`.
- `tenant_id` threaded on every read in `multi-tenancy` Req 5.1 and every write,
  with the predicate injected into the Postgres candidate/traversal SQL.
- `create_tenant(tenant_id: str, name="")` (validate → `ON CONFLICT DO NOTHING`
  → SELECT), `get_tenant`, `list_tenants`, `set_tenant_active`.
- `transaction()` context + `_on_conn` no-commit write variants for the copy
  spec, matching SQLite semantics.
- In-place migration `_ensure_tenant_columns`-equivalent for an existing Postgres
  DB: add columns + backfill `global`, add `tenants` + seed, apply the UNIQUE/PK
  changes by rebuilding (drop the auto-named `concept UNIQUE` via rebuild, not by
  name), guarded + idempotent, run under the existing `pg_advisory_lock`.

## Data migration (`migrate.py`)

Add `tenant_id` to every `_*_COLS` tuple and `_insert_*_batch`; add `tenants` to
the migration (copied FIRST, before referencing tables) and to the
bool/datetime/jsonb/pk classification dicts; copy `tenants` with `ON CONFLICT
(id) DO NOTHING` so the pre-seeded `global` row does not conflict; keep checksum
verification passing with `tenant_id` included.

## Testing strategy

All Postgres tests carry a `postgres` marker and skip when `MINTMORY_STORAGE_DSN`
is unset. Mirror the SQLite oracle's assertions: schema parity (tables/columns/
uniqueness/manifest PK/indexes), write guard on fresh + migrated Postgres DB,
scoped vs unscoped reads, per-tenant uniqueness, the in-place migration
(idempotent, backfill), and the SQLite→Postgres `migrate.py` moving `tenant_id`
and `tenants` with checksum passing. Gate: `uv run pytest`,
`uv run mypy packages/`, `uv run ruff check packages/` all exit 0.

## Risks

- **No Postgres in an unattended run** → tests are marked/skipped; CI with
  Postgres runs them. The behaviour is pinned by the SQLite oracle, lowering the
  risk of the skipped path diverging.
- **Unnamed `concept UNIQUE` constraint** → rebuild the table rather than `DROP
  CONSTRAINT <name>`.
