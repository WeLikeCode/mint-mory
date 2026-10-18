# Requirements — Multi-Tenancy 1/10: foundation (types, SQLite schema, migration, tenant directory)

## Introduction

MintMory is a flat, global store today (no tenant concept, no auth). Tenancy is
delivered as ten small units, each its own Kiro spec and plan unit. This unit is
the foundation: the tenant as a typed, stored entity, a `tenant_id` on every
table-backed record, per-tenant uniqueness, the SQLite migration and the tenant
directory methods. With only the reserved `global` tenant every existing
operation behaves exactly as today.

The other nine units (`multi-tenancy-writes`, `-reads`, `tenant-scoped-core`,
`multi-tenancy-cli`, `tenant-scoped-mcp`, `cross-tenant-copy`,
`multi-tenancy-postgres`, `-postgres-writes`, `-postgres-reads`) are listed with
what they deliver in the design.

### Tenancy contract (shared by all ten units)

- A tenant id matches `^[a-z0-9][a-z0-9_-]{0,127}$`. The reserved id `global`
  always exists, cannot be deactivated, and there is no delete API.
- A write always persists a concrete tenant; a record built without one gets
  `global`.
- Pure reads (results returned to a caller) take `tenant_id: str | None = None`:
  `None` = every tenant (today's SQL, no predicate); a concrete id = only that
  tenant's rows; an id with no `tenants` row = empty result, never an error
  (delivered by `multi-tenancy-reads`; until `multi-tenancy-postgres-reads` the
  Postgres backend instead raises `TenancyNotSupportedError` for any tenant other
  than `global`, R6).
- Keyed reads/writes whose key is unique only per tenant (summary by concept,
  manifest by path) take a concrete `tenant_id: str = "global"`, never `None`
  (this unit).
- An inactive tenant is read-only (enforced by `multi-tenancy-writes`).

Out of scope here: the write guard and reference checks, read scoping, every
transport change, Postgres behaviour beyond the interim stubs of R6, auth.

## Requirements

### Requirement 1 — Types and errors (`types.py`)

#### Acceptance Criteria

1. `types.py` SHALL define `TENANT_GLOBAL: Final[str] = "global"`,
   `TENANT_ID_PATTERN: Final[str] = r"^[a-z0-9][a-z0-9_-]{0,127}$"` and
   `validate_tenant_id(tenant_id: str) -> str`, which returns the id unchanged
   when `re.fullmatch(TENANT_ID_PATTERN, tenant_id)` matches and otherwise raises
   `InvalidTenantIdError(tenant_id)`. Valid: `acme`, `t-1`, `a_b`, `global`.
   Invalid: `""`, `Acme`, `-x`, `a b`, a 129-character id.
2. `types.py` SHALL define `class Tenant(BaseModel)` with `id: str` (field
   validator calls `validate_tenant_id`), `name: str = ""`, `is_active: bool =
   True`, `created_at: datetime = Field(default_factory=datetime.utcnow)`,
   `updated_at: datetime = Field(default_factory=datetime.utcnow)`.
3. `types.py` SHALL define these exceptions with exactly these constructors and
   `str(exc)` messages (each stores its constructor arguments as attributes of
   the same name):

   | Class | Bases | Constructor | Message |
   |---|---|---|---|
   | `TenantError` | `Exception` | (base, not raised directly) | — |
   | `TenantNotFoundError` | `TenantError` | `(tenant_id: str)` | `tenant 'X' not found` |
   | `TenantInactiveError` | `TenantError` | `(tenant_id: str)` | `tenant 'X' is inactive (read-only)` |
   | `ProtectedTenantError` | `TenantError` | `()` | `the global tenant cannot be deactivated` |
   | `InvalidTenantIdError` | `TenantError`, `ValueError` | `(tenant_id: str)` | `invalid tenant id 'X': expected ^[a-z0-9][a-z0-9_-]{0,127}$` |
   | `CrossTenantLinkError` | `TenantError` | `(first_id: str, first_tenant: str, second_id: str, second_tenant: str)` | `cross-tenant reference: 'A' (tenant 'T1') -> 'B' (tenant 'T2')` |
   | `TenantImmutableError` | `TenantError` | `(memory_id: str, stored_tenant: str, requested_tenant: str)` | `memory 'M' belongs to tenant 'T1'; it cannot move to 'T2'` |
   | `ScopeRequiredError` | `TenantError` | `(operation: str, scope: str)` | `OP requires the global scope; this process is scoped to tenant 'T'` |
   | `TenantMigrationError` | `TenantError` | `(cause: str)` | `tenant migration failed: CAUSE; the existing tables were left unchanged` |
   | `TenancyNotSupportedError` | `TenantError`, `NotImplementedError` | `(operation: str)` | `OP: tenancy on the Postgres backend is not available yet` |

   (`'X'` is `repr()` of the argument.) This unit raises `InvalidTenantIdError`,
   `TenantNotFoundError`, `ProtectedTenantError`, `TenantMigrationError` and
   `TenancyNotSupportedError`; later units raise the others.
4. `MemoryRecord`, `ConceptLink`, `MemorySummary`, `QuerySession` and
   `QueryResult` SHALL gain `tenant_id: str = Field(default=TENANT_GLOBAL)` with a
   field validator calling `validate_tenant_id`.
   `MemoryRecord(content="x", category="fact").tenant_id == "global"`;
   `MemoryRecord(content="x", category="fact", tenant_id="Bad")` raises a pydantic
   `ValidationError`.
5. `SearchRequest` and `MemoryFilter` SHALL NOT change: read scoping is a method
   parameter (`multi-tenancy-reads`), so no HTTP request body gains a tenant field.
   None of the five models of R1.4 is an HTTP request body (verified; see the
   design), so the new field appears only in responses.

### Requirement 2 — SQLite schema (`schema.sql`)

#### Acceptance Criteria

1. `schema.sql` SHALL create, before `memories`:
   `CREATE TABLE IF NOT EXISTS tenants (id TEXT PRIMARY KEY, name TEXT NOT NULL
   DEFAULT '', is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
   updated_at TEXT NOT NULL)` and seed
   `INSERT OR IGNORE INTO tenants (id, name, is_active, created_at, updated_at)
   VALUES ('global', 'Global (default) tenant', 1, '1970-01-01T00:00:00',
   '1970-01-01T00:00:00')`. `schema.sql` is the only creator and seeder of
   `tenants`; a second `initialise()` leaves exactly one `global` row.
2. In the fresh DDL, `memories`, `concept_links`, `memory_summaries`,
   `index_manifest`, `query_sessions` and `query_results` SHALL each have
   `tenant_id TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id)` as their
   last column (the position `ALTER TABLE … ADD COLUMN` gives it on a migrated
   database, so fresh and migrated tables have the same column order; rows are
   read by column name either way).
3. Uniqueness SHALL be per tenant: `concept_links` has
   `UNIQUE (tenant_id, source_memory_id, target_memory_id, link_type)` instead of
   `UNIQUE (source_memory_id, target_memory_id, link_type)`; `memory_summaries`
   has `concept TEXT NOT NULL` (no column `UNIQUE`) and
   `UNIQUE (tenant_id, concept)`; `index_manifest` has `path TEXT NOT NULL` and
   `PRIMARY KEY (tenant_id, path)`, keeping the `index_mode` CHECK with
   `'metadata','content','vision'`.
4. `schema.sql` SHALL NOT create any index that names `tenant_id`: on a
   pre-feature database it runs before the column exists. The tenant indexes
   are created by the migration (R3.2).
5. The FTS5 and trigram triggers SHALL stay unchanged.

### Requirement 3 — Migration of an existing SQLite database

#### Acceptance Criteria

1. `SqliteBackend.initialise()` SHALL call `self._ensure_tenant_columns(conn)`
   after `_ensure_index_mode_vision(conn)`.
2. `SqliteBackend._tenant_migration_statements(conn: sqlite3.Connection) ->
   list[str]` SHALL return, in this order, only the DDL the database still needs:
   (a) for each of the six tables of R2.2 without a `tenant_id` column
   (`PRAGMA table_info`): `ALTER TABLE <t> ADD COLUMN tenant_id TEXT NOT NULL
   DEFAULT 'global'` (this backfills every existing row to `global`; SQLite
   cannot add a column with a foreign key, so on a migrated database `memories`,
   `query_sessions` and `query_results` have no FK to `tenants` — intentionally:
   the write guard of `multi-tenancy-writes` enforces it — while the three rebuilt
   tables of (b) do);
   (b) a rebuild of `concept_links` when no unique index has exactly the columns
   `(tenant_id, source_memory_id, target_memory_id, link_type)` in that order
   (`PRAGMA index_list` + `PRAGMA index_info`), of `memory_summaries` when none has
   exactly `(tenant_id, concept)`, and of `index_manifest` when its primary key
   (`PRAGMA table_info` `pk` ordinals) is not exactly `(tenant_id, path)`;
   a rebuild is `CREATE TABLE <t>__tenant_new` with the fresh DDL of R2, `INSERT
   INTO <t>__tenant_new (<columns>) SELECT <columns> FROM <t>`, `DROP TABLE <t>`,
   `ALTER TABLE <t>__tenant_new RENAME TO <t>`, then the table's existing indexes
   (`idx_links_source`, `idx_links_target`, `idx_links_type_strength`,
   `idx_links_entity`; `idx_manifest_collection`) re-created;
   (c) for each missing index: `CREATE INDEX IF NOT EXISTS idx_memories_tenant ON
   memories(tenant_id, is_active, is_archived)`, `idx_links_tenant ON
   concept_links(tenant_id, source_memory_id, link_type)`, `idx_sessions_tenant ON
   query_sessions(tenant_id, concluded, created_at)`.
   On a fresh or already migrated database it SHALL return `[]`.
3. `_ensure_tenant_columns` SHALL compute the plan once without a lock and return
   at once on `[]`; otherwise it SHALL run `PRAGMA foreign_keys = OFF`, `BEGIN
   IMMEDIATE`, compute the plan AGAIN inside the transaction (another process may
   have migrated meanwhile), execute that second plan in order (an empty second
   plan executes nothing), `COMMIT`, and run `PRAGMA foreign_keys = ON` in a
   `finally` (the SQLite table-rebuild procedure; legacy rows are copied even if
   old data violates an FK; `connect()` always enables foreign keys, so restoring
   ON is correct).
4. WHEN any statement raises `sqlite3.Error` THEN `_ensure_tenant_columns` SHALL
   `ROLLBACK` and raise `TenantMigrationError(str(exc))` from it, and
   `initialise()` SHALL propagate it (fail closed: the process does not start).
   Every pre-existing table is then exactly as before (only the `tenants` table
   from `schema.sql` may remain, which the previous release ignores). It is never
   swallowed: a half-migrated database would fail every query that names
   `tenant_id`.
5. WHEN `initialise()` runs a second time THEN `_tenant_migration_statements`
   SHALL return `[]`, no migration statement SHALL run, and the sorted `(type,
   name, sql)` rows of `sqlite_master` SHALL be identical before and after
   (`schema.sql`'s own `IF NOT EXISTS` / `INSERT OR IGNORE` statements still run,
   as today).
6. A test fixture `packages/core/tests/fixtures/pre_tenancy_schema.sql` SHALL be a
   byte copy of `schema.sql` as it is on the base branch before this change.
   Test: create a file database from it; insert memories `m1` ("Alice works at
   Acme", fact) and `m2` ("Bob works at Acme", fact), a `relates_to` link
   m1→m2, a summary for concept `acme`, one `index_manifest` row for path `/a`,
   one `query_sessions` row and one `query_results` row; then
   `SqliteBackend(path).initialise()`. Expected: all six tables have `tenant_id`;
   every row reads back with `tenant_id == "global"` through `get_memory`,
   `get_links`, `get_summary("acme")`, `manifest_get("/a")` and `get_session`; the
   three indexes exist; `PRAGMA table_info` of all six tables and the
   unique-index columns and `PRAGMA foreign_key_list` of the three rebuilt tables
   equal those of a fresh database; `PRAGMA foreign_key_list(memories)` has no
   `tenants` entry (R3.2(a)); a second `initialise()` is a no-op (R3.5).
7. Test (fault injection), on a file database built from
   `pre_tenancy_schema.sql` with the rows of R3.6: monkeypatch
   `_tenant_migration_statements` to return the real list with `"ALTER TABLE
   no_such_table ADD COLUMN x TEXT"` inserted after the first statement;
   `initialise()` raises `TenantMigrationError`; `PRAGMA table_info(memories)` has
   no `tenant_id`; the row counts of the six tables are unchanged.
8. Test (concurrent start): two `SqliteBackend`s on one pre-feature file; compute
   backend B's plan, let backend A `initialise()` (it migrates), then make B's
   first `_tenant_migration_statements` call return that stale plan (later calls
   real): `B.initialise()` succeeds, because the plan computed inside the
   transaction is `[]`.

### Requirement 4 — Persisting `tenant_id`; keyed summary and manifest methods

#### Acceptance Criteria

1. `_MEMORY_COLUMNS` SHALL end with `"tenant_id"` (after `"metadata"`);
   `_memory_row_values` appends `record.tenant_id`; `_row_to_memory` reads it.
   `update_memory` SHALL NOT write the column (its rules are in
   `multi-tenancy-writes`).
2. `add_link`, `create_session` and `record_query_results` SHALL insert the
   model's `tenant_id`; `_row_to_link`, `get_session` and `_row_to_summary` SHALL
   return the stored value. Round trip: `add_memory(MemoryRecord(...,
   tenant_id="t1"))` after `create_tenant("t1")` → `get_memory(id).tenant_id ==
   "t1"`.
3. `get_summary(concept: str, tenant_id: str = TENANT_GLOBAL) -> MemorySummary |
   None` SHALL select `WHERE tenant_id = ? AND concept = ?`.
4. `upsert_summary(summary: MemorySummary) -> MemorySummary` SHALL key its
   existing-row lookup, its `ON CONFLICT(tenant_id, concept) DO UPDATE` target and
   its returned row on `(summary.tenant_id, summary.concept)`. Example: upserting
   concept `acme` for `global` and for `t1` gives two rows; `get_summary("acme")`
   returns the `global` one, `get_summary("acme", "t1")` the `t1` one.
5. The manifest methods SHALL take a keyword-only `tenant_id: str =
   TENANT_GLOBAL` as their last parameter: `manifest_get(path, *, tenant_id) ->
   ManifestEntry | None` (the row for `(tenant_id, path)`),
   `manifest_upsert(path, collection, *, size, mtime, online_only, index_mode,
   memory_ids, content_hash=None, tenant_id)` (`ON CONFLICT(tenant_id, path)`),
   `manifest_paths(collection, *, tenant_id) -> set[str]`, and
   `manifest_delete(path, *, tenant_id) -> None` (deletes only `(tenant_id,
   path)`). `ManifestEntry` gains `tenant_id: str`. Example: upserting `/a` for
   `global` and for `t1` gives two rows; `manifest_delete("/a", tenant_id="t1")`
   leaves the `global` row. `ManifestEntry` is a `TypedDict` (no field default is
   possible), so both constructions — `SqliteBackend.manifest_get` and
   `PostgresBackend.manifest_get`, the only ones in the repository — SHALL set it.
6. With only the `global` tenant, every existing test SHALL pass unchanged
   (`test_schema.py` gets the additions of R7 only).
7. Until `multi-tenancy-writes` adds the write guard, a write naming a tenant
   with no `tenants` row is undefined (a fresh table's FK raises
   `sqlite3.IntegrityError`; a migrated table accepts it). No test of this unit
   writes to such a tenant, and no transport can name a tenant yet.

### Requirement 5 — Tenant directory methods (SQLite)

#### Acceptance Criteria

1. `create_tenant(tenant_id: str, name: str = "") -> Tenant` SHALL call
   `validate_tenant_id` first (so a bad id raises the plain
   `InvalidTenantIdError`, not a pydantic error), then `INSERT OR IGNORE INTO
   tenants` with `is_active = 1` and `created_at = updated_at =
   _iso(_utcnow())` (naive UTC, `datetime.isoformat()`, as every other
   timestamp in `storage.py`; pydantic parses it back), then return the stored
   row. An existing id returns the existing row unchanged (its `name` is not
   updated) and raises nothing; two calls from two `SqliteBackend`s on one file
   leave one row (test).
2. `get_tenant(tenant_id: str) -> Tenant | None` SHALL return the row or `None`
   (an invalid id returns `None`).
3. `list_tenants() -> list[Tenant]` SHALL return every tenant, active and
   inactive, ordered by `id` ascending; a fresh database returns `[global]`.
4. `set_tenant_active(tenant_id: str, active: bool) -> Tenant` SHALL raise
   `TenantNotFoundError` for an unknown id, raise `ProtectedTenantError` for
   `("global", False)`, return `global` unchanged for `("global", True)`, and
   otherwise set `is_active` and `updated_at` and return the row.
5. The seeded `global` row has the sentinel timestamps of R2.1; tests compare
   `id`, `name` and `is_active`, never the timestamp of a created tenant.

### Requirement 6 — Protocol and the Postgres interim

#### Acceptance Criteria

1. `ports.py` `StorageBackend` SHALL declare the four methods of R5 and the
   signatures of R4.3–R4.5, and `ManifestEntry` SHALL have `tenant_id`.
2. `PostgresBackend` SHALL satisfy the Protocol for `mypy` without tenant
   storage: a `@staticmethod` `_require_global_tenant(tenant_id: str | None,
   operation: str) -> None` raises `TenancyNotSupportedError(operation)` unless `tenant_id`
   is `None` or `"global"`; it runs before any pool access in `get_summary`, the
   four manifest methods, `upsert_summary` (`summary.tenant_id`), `add_memory`
   (`record.tenant_id`), `add_link`, `create_session` and `record_query_results`
   (each result). `get_tenant("global")` returns `Tenant(id="global",
   name="Global (default) tenant", is_active=True, created_at=datetime(1970, 1,
   1), updated_at=datetime(1970, 1, 1))`, any other id `None`; `list_tenants()`
   returns that one tenant; `create_tenant` and `set_tenant_active` raise
   `TenancyNotSupportedError`. Rows read from Postgres carry `tenant_id ==
   "global"` (the model default); no Postgres SQL changes in this unit.
3. Test: on `PostgresBackend("postgresql://unused")` (never initialised, no
   database) each stub raises or returns as stated without opening a connection.
   These tests live in `packages/core/tests/test_pg_tenancy.py`, one function per
   stubbed method named `test_pg_<method>_tenancy` (for example
   `test_pg_create_tenant_tenancy`); the later Postgres units rewrite these
   functions in place for the real behaviour and never delete them (L4 treats a
   deleted pre-existing test function as an integrity blocker).

### Requirement 7 — Schema gate and OpenAPI

#### Acceptance Criteria

1. `test_schema.py` SHALL add `tenants` to `REQUIRED_TABLES`; `tenant_id` to
   `REQUIRED_MEMORIES_COLUMNS`, `REQUIRED_LINKS_COLUMNS` and
   `REQUIRED_SESSIONS_COLUMNS`; new column assertions with `tenant_id` for
   `memory_summaries`, `query_results` and `index_manifest`; the three indexes of
   R3.2(c) to `REQUIRED_INDEXES`; and a test that a fresh database has exactly
   one `tenants` row: `('global', 'Global (default) tenant', 1,
   '1970-01-01T00:00:00')`. The enum↔CHECK, FK and FTS trigger tests stay green.
2. `docs/openapi/mintmory.yaml` SHALL add `tenant_id` (`type: string`, the
   pattern, `default: global`) to the response schemas `MemoryRecord`,
   `ConceptLink`, `MemorySummary` and `QuerySession` only. No `Tenant` schema, no
   path, no header and no request-body field: the HTTP API accepts no tenant input.

### Requirement 8 — Gates

#### Acceptance Criteria

1. The gates of `.l4/config.yaml` SHALL pass: `ruff check`, `ruff format
   --check`, `mypy packages` (strict) and `pytest` with the 80% coverage floor.
   No test of this unit needs Postgres, Docker or a network service.
