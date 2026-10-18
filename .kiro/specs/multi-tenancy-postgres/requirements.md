# Requirements — Multi-Tenancy 8/10: Postgres schema, migrations and column parity

> **Depends on:** `multi-tenancy` (the model `tenant_id` fields, the SQLite DDL
> that this unit mirrors, `get_summary(concept, tenant_id="global")`, the
> keyword-only manifest `tenant_id`, `TenantMigrationError`,
> `TenancyNotSupportedError`, `PostgresBackend._require_global_tenant`). Changes
> `schema_postgres.sql`, `storage_postgres.py`, `migrate.py` and tests; no
> model, transport or SQLite change.

## Introduction

This unit gives a Postgres database the same tenant columns, keys and indexes as
SQLite: in the fresh DDL, by an in-place migration of an existing Postgres
database, and in the SQLite→Postgres data migration (`migrate.py`). The Postgres
backend then reads and writes the `tenant_id` column, but still accepts only the
`global` tenant: the write guard and tenant directory arrive with
`multi-tenancy-postgres-writes`, tenant-confined reads with
`multi-tenancy-postgres-reads`.

### How it is proven without a database in the L4 job

The L4 job has no Postgres: L4 offers no service or Docker socket to gates, and a
skipped test proves nothing there. Every acceptance criterion here is therefore
proven by tests that need no database: text checks of `schema_postgres.sql`, a
pure planning function for the migration, a fake psycopg pool that records SQL,
and `migrate.py`'s dry-run path (which opens no Postgres connection). The
repository's own CI job `conformance-pg` (service `pgvector/pgvector:pg16`,
`MINTMORY_TEST_PG_DSN`) keeps running the conformance suite with `-k postgres`
and `test_migrate.py` against a real database on every pull request; that is
supplementary evidence, not an L4 gate. No `skip`/`skipif`/`xfail` marker or
`pytest.skip(` call SHALL be added.

## Requirements

### Requirement 1 — Fresh DDL (`schema_postgres.sql`)

#### Acceptance Criteria

1. Before `memories` the file SHALL create `CREATE TABLE IF NOT EXISTS tenants
   (id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', is_active BOOLEAN NOT NULL
   DEFAULT TRUE, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL)`
   and seed `INSERT INTO tenants (id, name, is_active, created_at, updated_at)
   VALUES ('global', 'Global (default) tenant', TRUE, '1970-01-01 00:00:00',
   '1970-01-01 00:00:00') ON CONFLICT (id) DO NOTHING` (the SQLite sentinel).
2. The `CREATE TABLE` block of each of `memories`, `concept_links`,
   `memory_summaries`, `index_manifest`, `query_sessions`, `query_results` SHALL
   contain `tenant_id TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id)`.
3. `concept_links` SHALL use `CONSTRAINT concept_links_tenant_unique UNIQUE
   (tenant_id, source_memory_id, target_memory_id, link_type)`;
   `memory_summaries` `concept TEXT NOT NULL` and `CONSTRAINT
   memory_summaries_tenant_concept_key UNIQUE (tenant_id, concept)`;
   `index_manifest` `path TEXT NOT NULL` and `PRIMARY KEY (tenant_id, path)`.
4. No `CREATE INDEX` in the file SHALL name `tenant_id` (the file runs before the
   migration on an existing database). `content_tsv`, its GIN index and the
   `pg_trgm` index stay unchanged.
5. Test (text only): parse each `CREATE TABLE … (…);` block and assert R1.1–R1.4.

### Requirement 2 — In-place migration of an existing Postgres database

#### Acceptance Criteria

1. `storage_postgres.py` SHALL define the pure function
   `plan_pg_tenant_migration(columns: dict[str, set[str]], uniques: dict[str,
   list[tuple[str, tuple[str, ...]]]], primary_keys: dict[str, tuple[str,
   tuple[str, ...]]], indexes: set[str]) -> list[str]` (`columns`: column names
   per table; `uniques`: `(constraint name, columns)` per table; `primary_keys`:
   `(name, columns)` per table; `indexes`: existing index names). It SHALL return,
   in order: (a) for each of the six tables (in R1.2 order) without `tenant_id`:
   `ALTER TABLE <t> ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'global' REFERENCES
   tenants(id)`; (b) when `concept_links` has no unique on `(tenant_id,
   source_memory_id, target_memory_id, link_type)`: `ALTER TABLE concept_links
   DROP CONSTRAINT "<name>"` for each unique on `(source_memory_id,
   target_memory_id, link_type)`, then `ALTER TABLE concept_links ADD CONSTRAINT
   concept_links_tenant_unique UNIQUE (tenant_id, source_memory_id,
   target_memory_id, link_type)`; the same for `memory_summaries` (old unique on
   `(concept,)`, new `memory_summaries_tenant_concept_key UNIQUE (tenant_id,
   concept)`); when the `index_manifest` primary key is not `(tenant_id, path)`:
   `ALTER TABLE index_manifest DROP CONSTRAINT "<pk name>"` then `ALTER TABLE
   index_manifest ADD PRIMARY KEY (tenant_id, path)`; (c) for each missing index:
   `CREATE INDEX IF NOT EXISTS idx_memories_tenant ON memories (tenant_id,
   is_active, is_archived)`, `CREATE INDEX IF NOT EXISTS idx_links_tenant ON
   concept_links (tenant_id, source_memory_id, link_type)`, `CREATE INDEX IF NOT
   EXISTS idx_sessions_tenant ON query_sessions (tenant_id, concluded,
   created_at)`. For a fully migrated snapshot it SHALL return `[]`.
2. `PostgresBackend._ensure_tenant_columns(conn)` SHALL read the snapshot from
   the catalog (`information_schema.columns`, `pg_constraint` with `contype IN
   ('u', 'p')` and its `conkey` column names in key order, `pg_indexes`, all
   limited to `current_schema()` and the six tables) and execute the plan on
   `conn`. `initialise()` SHALL call it after `_create_schema(conn)` inside the
   same transaction that holds `pg_advisory_xact_lock`, before `conn.commit()`;
   concurrent replicas therefore migrate one at a time and the second finds `[]`.
3. WHEN any statement fails THEN the transaction SHALL roll back (Postgres DDL is
   transactional) and `initialise()` SHALL raise `TenantMigrationError(str(exc))`
   from it: the existing tables are unchanged and the process does not start.
4. Tests (no database): the pre-feature snapshot (six tables without
   `tenant_id`, uniques `concept_links_source_memory_id_target_memory_id_link_type_key`
   and `memory_summaries_concept_key`, primary key `index_manifest_pkey` on
   `(path,)`, none of the three indexes) → exactly the 15 statements of R2.1 in
   order; the migrated snapshot → `[]`; columns present but old keys → only (b)
   and (c). With the fake pool of R5 answering the catalog queries with the
   pre-feature snapshot, the statements `initialise()` executes after
   `pg_advisory_xact_lock` are the DDL file, the catalog reads, then the 15
   statements in order, followed by a commit; a fake that raises on the first
   `ALTER` makes `initialise()` raise `TenantMigrationError`, with a rollback
   recorded and no commit after the advisory lock.

### Requirement 3 — The backend reads and writes `tenant_id`

#### Acceptance Criteria

1. `_SELECT_MEMORY` SHALL end with `tenant_id`; the INSERTs of `add_memory`,
   `add_link`, `create_session`, `record_query_results`, `upsert_summary` and
   `manifest_upsert` SHALL include the model's `tenant_id`; `_row_to_memory`,
   `_row_to_link`, the summary and session mappers and `manifest_get` SHALL
   return the stored value.
2. Conflict targets SHALL be per tenant: `add_link` `ON CONFLICT (tenant_id,
   source_memory_id, target_memory_id, link_type) DO NOTHING`, `upsert_summary`
   `ON CONFLICT (tenant_id, concept) DO UPDATE`, `manifest_upsert` `ON CONFLICT
   (tenant_id, path) DO UPDATE`; `get_summary(concept, tenant_id)` and the four
   manifest methods SHALL add `tenant_id = %s` with their key.
3. `_require_global_tenant` SHALL stay on these record writes and keyed methods
   (only `global` is accepted until `multi-tenancy-postgres-writes` /
   `-reads`).
4. `PostgresBackend._truncate_all()` (test isolation) SHALL also run `DELETE FROM
   tenants WHERE id <> 'global'`.
5. Tests (fake pool): the SQL text and parameters of each statement of R3.1–R3.2
   (e.g. `add_link` executes an INSERT whose column list includes `tenant_id`, whose
   parameters include `"global"` and whose text contains `ON CONFLICT (tenant_id,
   source_memory_id, target_memory_id, link_type) DO NOTHING`); a row dict with
   `tenant_id = "global"` maps to a model with `tenant_id == "global"`.

### Requirement 4 — SQLite→Postgres data migration (`migrate.py`)

#### Acceptance Criteria

1. `_TENANTS_COLS = ("id", "name", "is_active", "created_at", "updated_at")`;
   `_FK_ORDER` SHALL start with `"tenants"`; `_TABLE_COLS`, `_TABLE_PK`
   (`["id"]`), `_CHECKSUM_EXCLUDED` (empty), `_BOOL_COLS` (`{"is_active"}`),
   `_DATETIME_COLS` (`{"created_at", "updated_at"}`) and `_JSONB_COLS` (empty)
   SHALL have a `tenants` entry; `_TABLE_PK["index_manifest"]` becomes
   `["tenant_id", "path"]`.
2. `"tenant_id"` SHALL be appended to the six `_*_COLS` tuples and to the column
   and value lists of the six `_insert_*_batch` functions; `concept_links` uses
   `ON CONFLICT (tenant_id, source_memory_id, target_memory_id, link_type) DO
   NOTHING`, `index_manifest` `ON CONFLICT (tenant_id, path) DO NOTHING`.
3. `_insert_tenants_batch(conn, rows, *, dry_run=False) -> int` SHALL run
   `INSERT INTO tenants (id, name, is_active, created_at, updated_at) VALUES (%s,
   %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING` (the target's seeded `global`
   equals the source's, so its checksum matches) and be registered in
   `_TABLE_INSERT_FN`; `_pg_truncate_all` SHALL add `tenants` to its `TRUNCATE`.
4. Before any write, and in `dry_run` too, `migrate_sqlite_to_postgres` SHALL
   raise `ValueError("source database predates multi-tenancy: open it once with
   this MintMory version (any command) to migrate it, then retry")` when the
   source has no `tenants` table or one of the six tables has no `tenant_id`
   (the source is opened read-only, so it is never migrated here), and
   `ValueError(f"source table {table!r} references unknown tenant(s): {ids}")`
   (`ids` a sorted list, first offending table in `_FK_ORDER`) when a `tenant_id`
   value has no row in the source `tenants`.
5. Checksums SHALL include `tenant_id` (it is not excluded), so a changed
   `tenant_id` changes the row checksum.
6. Tests (no database): the dry-run report of a tenant-aware SQLite source lists
   `tenants` first with its row count; both `ValueError`s (a source built from
   `packages/core/tests/fixtures/pre_tenancy_schema.sql`, and a source with a
   `tenant_id` value `ghost` written with foreign keys off); the SQL and parameters
   of `_insert_tenants_batch` and of the `concept_links` / `index_manifest`
   inserts on a fake connection; the checksum difference of R4.5.

### Requirement 5 — Postgres test seam

#### Acceptance Criteria

1. `packages/core/tests/pg_fakes.py` SHALL provide `FakePool`, `FakeConnection`
   and `FakeCursor`: `FakePool(conn).connection()` is a context manager yielding
   `conn` (calling `conn.rollback()` and re-raising on an exception);
   `FakeConnection` has `execute(sql, params=None) -> FakeCursor`,
   `cursor(row_factory=None) -> FakeCursor`, `commit()`, `rollback()`, and records
   `executed: list[tuple[str, Any]]`, `commits: int`, `rollbacks: int`; a
   `responder: Callable[[str, Any], list[Any]]` supplies the rows of each
   statement and a `fail_on: Callable[[str], bool] | None` makes matching
   statements raise `RuntimeError`; `FakeCursor` has `execute`, `executemany`
   (records one entry per parameter set), `fetchone`, `fetchall`, `rowcount`,
   and works as a context manager. Tests install it with `backend =
   PostgresBackend("postgresql://unused"); backend._pool = FakePool(conn)`.
   The later Postgres units reuse it.

### Requirement 6 — Gates

#### Acceptance Criteria

1. The `.l4/config.yaml` gates SHALL pass with coverage ≥ 80%. No test needs
   Postgres, Docker or a network service.
2. (Not an L4 gate.) On the pull request, the repository's `conformance-pg` job
   is expected to stay green on a real database: its `initialise()` runs the
   catalog reads of R2.2 on a fresh schema and finds `[]`.
