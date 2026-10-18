# Tasks — Multi-Tenancy Postgres Parity

> **Depends on:** `multi-tenancy` (`.kiro/specs/multi-tenancy/`). Do not start
> until it is complete; the SQLite backend is the behavioural oracle. No
> `types.py` changes here.

TDD per task; gate per task: `uv run pytest packages/core/tests/` (Postgres
tests are `postgres`-marked and skip without `MINTMORY_STORAGE_DSN`),
`uv run mypy packages/core/`, `uv run ruff check packages/core/`. Full gate
before PR: `uv run pytest` (≥ 80%), `uv run mypy packages/`,
`uv run ruff check packages/`.

---

- [ ] 1. Postgres schema parity (`schema_postgres.sql`)
  - Add the `tenants` table (BOOLEAN/TIMESTAMP, `ON CONFLICT DO NOTHING` seed),
    `tenant_id ... REFERENCES tenants(id)` on the six tables, the two per-tenant
    UNIQUE constraints, the `(tenant_id, path)` manifest PK, and the
    tenant-leading indexes. Leave `content_tsv`/GIN/pg_trgm unchanged.
  - Tests (`postgres`-marked): schema has the table/columns/uniqueness/PK/indexes.
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 2. Postgres backend parity (`storage_postgres.py`)
  - Mirror the write guard, `tenant_id` on the exhaustive read/write set, the
    predicate injection, the tenant management methods, and the `transaction()` +
    `_on_conn` contracts. Re-raise FK integrity errors as `TenantNotFoundError`.
  - Tests (`postgres`-marked): write guard (missing/inactive), scoped vs unscoped
    reads, per-tenant uniqueness, cross-tenant errors, tenant methods — mirroring
    the SQLite oracle.
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 3. In-place existing-Postgres migration (`storage_postgres.py`)
  - Idempotent add-column + backfill + `tenants` seed + UNIQUE/PK rebuild (drop
    auto-named `concept UNIQUE` by rebuild), under `pg_advisory_lock`.
  - Test (`postgres`-marked): pre-feature Postgres DB → migrated, backfilled,
    second run no-op.
  - _Requirements: 3.1, 3.2_

- [ ] 4. SQLite→Postgres data migration (`migrate.py`)
  - Add `tenant_id` to every `_*_COLS` + `_insert_*_batch`; add `tenants` first
    with `ON CONFLICT (id) DO NOTHING`; update classification dicts; keep
    checksum passing.
  - Test (`postgres`-marked): migrating a tenant-aware SQLite DB yields matching
    tenant data in Postgres; checksum passes.
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 5. Full gate
  - `uv run pytest` (≥ 80%; Postgres tests skip without a DSN), `uv run mypy
    packages/`, `uv run ruff check packages/` — all exit 0.
  - _Requirements: 5.1, 5.2, 5.3_
