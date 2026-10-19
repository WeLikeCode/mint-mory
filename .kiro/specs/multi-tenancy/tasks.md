# Tasks — Multi-Tenancy 1/10: foundation

Each task is TDD: write the failing test, confirm it fails for the right reason,
implement, run the package gate (`uv run pytest packages/core/tests/`,
`uv run mypy packages/core/`, `uv run ruff check packages/core/`). Full gate
before the PR: the gates of `.l4/config.yaml`. No Postgres, Docker or network is
needed by any test here.

- [x] 1. Types and errors (`types.py`)
  - `TENANT_GLOBAL`, `TENANT_ID_PATTERN`, `validate_tenant_id`, `Tenant`, the
    error classes with the exact constructors and messages of R1.3, and
    `tenant_id` + validator on `MemoryRecord`, `ConceptLink`, `MemorySummary`,
    `QuerySession`, `QueryResult`. `SearchRequest` and `MemoryFilter` unchanged.
  - Tests: the valid/invalid ids of R1.1; model defaults are `global`; a bad id
    on a model raises `ValidationError`; each error's message and attributes;
    `InvalidTenantIdError` is a `ValueError`, `TenancyNotSupportedError` a
    `NotImplementedError`.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Pre-feature fixture, SQLite schema and per-tenant keys (`schema.sql`, `storage.py`, `ports.py`)
  - First, in this task's red commit, copy today's `schema.sql` byte for byte to
    `packages/core/tests/fixtures/pre_tenancy_schema.sql` (a test-support file
    under `**/fixtures/**`: L4 freezes it once added, later tasks only read it).
  - Then edit `schema.sql`: `tenants` + seed first; `tenant_id … REFERENCES
    tenants(id)` as the last column of the six tables; per-tenant `UNIQUE` on
    `concept_links` and `memory_summaries`; `index_manifest` primary key
    `(tenant_id, path)`; no index on `tenant_id`; triggers unchanged.
  - In the same task (the old `ON CONFLICT(concept)` / `ON CONFLICT(path)`
    targets stop matching a constraint once the keys change, so the package gate
    would fail between separate tasks): `get_summary(concept,
    tenant_id="global")`, `upsert_summary` on `(tenant_id, concept)`, the four
    manifest methods with the keyword-only `tenant_id`, `ManifestEntry.tenant_id`.
  - Tests: two tenants with the same concept and the same manifest path (R4.4,
    R4.5 examples; create `t1` with a raw `INSERT INTO tenants`, the directory
    methods come in task 5); the existing summary/manifest/history-ingest tests
    pass unchanged.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 4.3, 4.4, 4.5_

- [x] 3. Migration (`storage.py`)
  - `_tenant_migration_statements(conn)` (R3.2 detection rules and order) and
    `_ensure_tenant_columns(conn)` (R3.3 transaction, R3.4 fail closed), called
    from `initialise()` after `_ensure_index_mode_vision`.
  - Tests: the R3.6 pre-feature fixture scenario; R3.5 second-run no-op with
    `sqlite_master` compared; on a new file, the plan right after `schema.sql`
    is exactly the three `CREATE INDEX` statements and `[]` after
    `initialise()`; the R3.7 fault injection; the R3.8 stale-plan start.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [x] 4. Persist `tenant_id` on every row (`storage.py`)
  - Lockstep of R4.1–R4.2 (`_MEMORY_COLUMNS`, row values, row mappers, the
    link/session/result inserts).
  - Tests: round trip of every model's `tenant_id`.
  - _Requirements: 4.1, 4.2, 4.6, 4.7_

- [x] 5. Tenant directory (`storage.py`)
  - `create_tenant`, `get_tenant`, `list_tenants`, `set_tenant_active` per R5.
  - Tests: create/get/list order; existing id returns the row unchanged (name
    kept); invalid id raises plain `InvalidTenantIdError`; `get_tenant` of an
    invalid or unknown id is `None`; `set_tenant_active` unknown →
    `TenantNotFoundError`; `("global", False)` → `ProtectedTenantError`;
    deactivate then reactivate `t1`; `create_tenant("t1")` from two
    `SqliteBackend`s on one file leaves one row.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 6. Protocol and Postgres interim (`ports.py`, `storage_postgres.py`)
  - Protocol entries of R6.1; `_require_global_tenant` and the stubs of R6.2.
  - Tests (no database) in `packages/core/tests/test_pg_tenancy.py`, one
    `test_pg_<method>_tenancy` function per stubbed method: on
    `PostgresBackend("postgresql://unused")` each raises
    `TenancyNotSupportedError` for tenant `t1` (`create_tenant` /
    `set_tenant_active` always), `get_tenant` / `list_tenants` return the
    synthetic `global`; `uv run mypy packages` passes.
  - _Requirements: 6.1, 6.2, 6.3_

- [ ] 7. Schema gate and OpenAPI
  - `test_schema.py` additions of R7.1; `docs/openapi/mintmory.yaml` additions of
    R7.2 (response schemas only).
  - _Requirements: 7.1, 7.2_

- [ ] 8. Full gate
  - Run the `.l4/config.yaml` gates; all exit 0 with coverage ≥ 80%.
  - _Requirements: 8.1_
