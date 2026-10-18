# Design — Multi-Tenancy 1/10: foundation

## Grounding (base branch, verified)

- `packages/core/src/mintmory/core/storage.py` `SqliteBackend`: one shared
  connection (`connect()`), `transaction()` commits/rolls back,
  `initialise()` runs `schema.sql` with `executescript` then `_ensure_trigram`,
  `_ensure_is_note_column`, `_ensure_index_mode_vision` (best-effort, they swallow
  `sqlite3.OperationalError`). `_MEMORY_COLUMNS` + `_memory_row_values` +
  `_row_to_memory` + the `update_memory` SET list are kept in lockstep.
  `upsert_summary` looks up `get_summary(summary.concept)` and uses
  `ON CONFLICT(concept)`; `manifest_upsert` uses `ON CONFLICT(path)`.
- `ports.py` `StorageBackend` is a `@runtime_checkable` Protocol;
  `build_storage()` returns `StorageBackend`, so `PostgresBackend` must satisfy
  it structurally or `mypy packages` fails. `transaction()` is not on the
  Protocol today (it is added by `multi-tenancy-writes`).
- `manifest_*` callers: `cli/main.py` (`index-tree`) and
  `core/history/ingest.py` (history DB, also a `SqliteBackend`). All pass
  positional `path`/`collection` and keywords; a keyword-only trailing
  `tenant_id` keeps them working.
- `get_summary` callers: `dreaming.py`, MCP `summary_get`, API
  `GET /summaries/{concept}`, the backends' `upsert_summary`. A default of
  `"global"` keeps them identical on a one-tenant database.
- `packages/core/tests/test_schema.py` builds its `db`/`conn` fixtures with
  `StorageAdapter(":memory:").initialise()`, so the migration runs there too and
  the tenant indexes exist for `REQUIRED_INDEXES`.

## Types

All new names live in `types.py` (the source of truth), next to the models.
`validate_tenant_id` is the single validator; `Tenant` and the five models call
it from a `field_validator("tenant_id")` / `field_validator("id")`. Inside a
pydantic validator the `ValueError` subclass is wrapped into `ValidationError`;
`create_tenant` calls `validate_tenant_id` itself before building a `Tenant`, so
callers of the method see the plain `InvalidTenantIdError`.

Every error class sets its message in `__init__` via `super().__init__(msg)` and
keeps its arguments as attributes, e.g.

```python
class TenantNotFoundError(TenantError):
    def __init__(self, tenant_id: str) -> None:
        super().__init__(f"tenant {tenant_id!r} not found")
        self.tenant_id = tenant_id
```

## Schema

`tenants` is created first in `schema.sql` so the fresh tables' FK target exists
before any insert. The fresh DDL of the six tables carries the FK; tables that
already exist are untouched by `CREATE TABLE IF NOT EXISTS` and get the column
from the migration instead. No `CREATE INDEX` in `schema.sql` names `tenant_id`.

## Migration (`_ensure_tenant_columns`)

`_tenant_migration_statements(conn)` inspects the database and returns a list of
statements; `_ensure_tenant_columns(conn)` executes it. Splitting plan and
execution gives tests a seam for fault injection (R3.7) and makes the
"migrated database ⇒ `[]`" rule (R3.2, R3.5) directly testable.

Statement order is load-bearing: (a) the `ADD COLUMN`s run first, so the
rebuild `INSERT … SELECT` of (b) can name `tenant_id` on the old table; (c) the
indexes come last, after the column exists on every table.

The rebuild DDL is the same column list as `schema.sql`; drift is caught by the
R3.6 test, which compares `PRAGMA table_info` and the unique-index columns of
a migrated and a fresh database. `index_manifest`'s rebuilt DDL keeps the
`'vision'` CHECK, so `_ensure_index_mode_vision` (which runs before and checks
for `'vision'` in the stored SQL) stays a no-op afterwards.

Atomicity: SQLite DDL is transactional, so `BEGIN IMMEDIATE … COMMIT` makes the
whole plan all-or-nothing; `PRAGMA foreign_keys` cannot change inside a
transaction, hence OFF before `BEGIN` and ON in `finally`. On `sqlite3.Error`:
`ROLLBACK`, then `TenantMigrationError`. This deliberately differs from the
best-effort `_ensure_*` helpers: running with a partly migrated schema would make
every insert and select that names `tenant_id` fail, so refusing to start with a
clear message is the safe outcome.

Fault-injection test:

```python
real = SqliteBackend._tenant_migration_statements
def broken(self, conn):
    stmts = real(self, conn)
    return stmts[:1] + ["ALTER TABLE no_such_table ADD COLUMN x TEXT"] + stmts[1:]
monkeypatch.setattr(SqliteBackend, "_tenant_migration_statements", broken)
with pytest.raises(TenantMigrationError):
    SqliteBackend(path).initialise()
```

## Keyed methods

`get_summary`/`upsert_summary` and the manifest methods move to the composite
keys. `upsert_summary` keeps the existing id of a `(tenant_id, concept)` row so
an update does not change the summary id (today's behaviour per concept).

## Tenant directory

Plain SQL on `tenants` through `transaction()` (writes) and `connect()` (reads).
`create_tenant` is `INSERT OR IGNORE` + `SELECT`, so it is idempotent and
race-safe without a read-then-write.

## Postgres interim

`PostgresBackend` gets the new methods and parameters but no tenant storage.
`_require_global_tenant` is the one guard; because every Postgres row is a
`global` row until `multi-tenancy-postgres` adds the column, `None` and
`"global"` keep today's SQL and any other tenant fails loudly with
`TenancyNotSupportedError` (a `TenantError`, so the CLI and MCP map it like any
tenant error). The guard runs before `assert self._pool is not None`, which lets
the R6.3 test run without a database.

## OpenAPI

Only the four response schemas gain the field, because the API returns these
models and the field now appears in its JSON. Nothing is added that the API does
not serve.

## Error table (HTTP codes used by `tenant-scoped-core`)

| Exception | HTTP |
|---|---|
| `TenantNotFoundError` | 404 |
| `TenantInactiveError`, `CrossTenantLinkError`, `TenantImmutableError` | 409 |
| `ProtectedTenantError`, `ScopeRequiredError` | 403 |
| `InvalidTenantIdError` | 422 |
| `TenancyNotSupportedError` | 501 |
| `TenantMigrationError` | 503 |

## Risks

- Lockstep drift between the column list, row values and row mapper → the R4.2
  round-trip test and the R3.6 fresh-vs-migrated comparison.
- A legacy database with dangling FK rows → the rebuild runs with
  `foreign_keys = OFF`, as SQLite documents, so old rows are preserved.
- The migration is one-way: an older MintMory opening a migrated database fails
  on summary and manifest upserts (their old `ON CONFLICT` targets no longer
  exist). Release notes should say to back up the `.db` file before upgrading.
