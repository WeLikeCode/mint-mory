# Design — Multi-Tenancy (Phase 1: foundation)

## Overview

This design adds tenancy as a **row-scoped, shared-table** data primitive. Every
table-backed entity gains a `tenant_id TEXT NOT NULL DEFAULT 'global'` column,
defaulting to the reserved tenant `global`. A single `.db` / Postgres database
continues to hold all tenants.

The change is backwards compatible by construction:
- The column default is `'global'`, so inserts that do not mention a tenant land
  in the global tenant.
- An idempotent column-add migration backfills every pre-existing row to
  `global`, following the established `_ensure_*` pattern in `StorageAdapter`.
- **Reads/searches use an optional `tenant_id: str | None`.** `None` = unscoped
  (spans all rows, today's exact behaviour); a concrete value = confined. A
  tenant predicate is injected into the candidate SQL **only when a concrete
  tenant is supplied**.

The read/write asymmetry and FK reality are stated authoritatively in
requirements.md ("Read vs write tenant semantics", "Isolation model"). In short:
reads take `tenant_id: str | None` (`None` = all rows; concrete = confined; never
`"global"` for a read); writes stamp a concrete id (unspecified = `"global"`).
SQLite can't add a FK via `ALTER TABLE ADD COLUMN`, so fresh/rebuilt tables carry
the FK and the write guard enforces tenant-exists on migrated tables. SoT order:
`types.py` → `schema.sql` → `openapi.yaml`.

### Grounding (verified)

`build_storage()` is the single construction chokepoint. Table-backed models:
`MemoryRecord`, `ConceptLink`, `MemorySummary`, `QuerySession`, `QueryResult`,
plus `index_manifest` (`ManifestEntry` TypedDict, no Pydantic model). Search
candidates come from `_fts_scores`/`_trigram_scores`/`_vector_scores`/
`_load_memories`; `_passes_filter` is post-load only. Today
`memory_summaries.concept` is globally UNIQUE and `concept_links` is
`UNIQUE(source,target,link_type)`. `_MEMORY_COLUMNS` + `_memory_row_values` +
`_row_to_memory` + the `update_memory` SET list must stay in lockstep (the
`migrate.py` `_*_COLS` mirror is `multi-tenancy-postgres`'s). Schema gate:
`test_schema.py`.

---

## Architecture

This spec wires only the **CLI** selector. The MCP and HTTP selectors are owned
by other specs (`tenant-scoped-mcp` / a future HTTP spec); the MCP server and
HTTP API keep behaving as the global tenant until those land. `TENANT_GLOBAL =
"global"` is a module-level constant in `types.py` reused everywhere.

Ownership (resolves cross-unit duplicate-scope findings): this spec adds the
optional read `tenant_id`, the write guard, uniqueness, SQLite migration,
schema-only OpenAPI, and the CLI (Postgres + `migrate.py` →
`multi-tenancy-postgres`). It does NOT touch MCP tool signatures or register MCP
tenant tools (owned by `tenant-scoped-mcp`), and does NOT scope the
`DreamingEngine` or run a dream-all-tenants loop (owned by
`cross-tenant-copy-and-dreaming`); it only makes the dreaming helper queries
tenant-aware.

Row-scoped (not DB-per-tenant) is the smallest backwards-compatible delta, keeps
one DB/schema-gate/FTS index set, and enables future cross-tenant admin reads.
Isolation is query-enforced: the predicate is pushed into candidate SQL (not just
`_passes_filter`) so no unscoped row reaches fusion when a tenant is supplied.

---

## Data model changes (`types.py` — edited first)

### New: `Tenant` model + constant

`TENANT_GLOBAL = "global"`. `Tenant(id, name="", is_active=True, created_at,
updated_at)` with an id field validator for `^[a-z0-9][a-z0-9_-]{0,127}$`
(raising `InvalidTenantIdError`).

### Add `tenant_id` to every table-backed model

`MemoryRecord`, `ConceptLink`, `MemorySummary`, `QuerySession`, `QueryResult`
each gain `tenant_id: str = Field(default=TENANT_GLOBAL, ...)`; the
`index_manifest` `ManifestEntry` TypedDict (`ports.py`) gains `tenant_id` too.

### Filter / request surface

- `MemoryFilter` gains `tenant_id: str | None = None` (None = unscoped = today).
- `SearchRequest` gains `tenant_id: str | None = None`.
- `MemoryStats` is unchanged in shape; `get_stats` gains an optional tenant arg.

Default `None` preserves backwards compatibility (Requirement 5.1).

---

## Schema changes (`schema.sql` — SQLite only; Postgres is `multi-tenancy-postgres`)

This spec edits `schema.sql` and the SQLite backend only. `types.py` (the source
of truth) carries `tenant_id` on every model, so the Postgres spec mirrors the
DDL without changing the model. The `tenants` CREATE + seed may stay in
`schema.sql` (self-contained, safe to run first); the `tenant_id` columns and
their indexes are created by the migration (below).

### New `tenants` table

```sql
CREATE TABLE IF NOT EXISTS tenants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
INSERT OR IGNORE INTO tenants (id, name, is_active, created_at, updated_at)
VALUES ('global', 'Global (default) tenant', 1,
        '1970-01-01T00:00:00', '1970-01-01T00:00:00');
```

### `tenant_id` column on every scoped table

Each of `memories`, `concept_links`, `memory_summaries`, `query_sessions`,
`query_results`, `index_manifest` gains, **in the fresh schema**:

```sql
tenant_id TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id)
```

Notes:
- `NOT NULL DEFAULT 'global'` makes fresh inserts and legacy rows land in the
  global tenant automatically.
- On a **fresh** schema and on any table **rebuilt** during migration, the FK is
  present and (with `PRAGMA foreign_keys = ON`, already re-asserted per
  connection) enforced at runtime.
- On a **pre-existing** table where the column is added via `ALTER TABLE ADD
  COLUMN`, there is NO FK (SQLite limitation). The write guard enforces
  tenant-exists there instead. Do not claim the FK alone satisfies Req 4.2 —
  the write guard is the load-bearing enforcement.

### Uniqueness changes (Requirement 6)

- `memory_summaries`: replace `concept TEXT UNIQUE` with a table-level
  `UNIQUE (tenant_id, concept)`.
- `concept_links`: replace `UNIQUE (source_memory_id, target_memory_id,
  link_type)` with `UNIQUE (tenant_id, source_memory_id, target_memory_id,
  link_type)`.

### Indexes

Add tenant-leading indexes to support scoped reads without regressing global
reads:
- `idx_memories_tenant ON memories(tenant_id, is_active, is_archived)`
- `idx_links_tenant ON concept_links(tenant_id, source_memory_id, link_type)`
- `idx_summaries_tenant ON memory_summaries(tenant_id, concept)`
- `idx_sessions_tenant ON query_sessions(tenant_id, concluded, created_at)`

`index_manifest`'s PRIMARY KEY changes from `path` to `(tenant_id, path)` so two
tenants can index the same path (rebuilt on migration like the UNIQUE-changing
tables). The existing indexes remain for global reads.

### FTS / tenant interaction

SQLite FTS5 (`memories_fts`) is external-content keyed on `memories.rowid`; the
three triggers stay exactly as-is (they index `content` only). Tenant scoping of
FTS results joins back to `memories` and filters `memories.tenant_id = ?` in
`_fts_scores`/`_trigram_scores`; the triggers are untouched (Invariant §4.6).

---

## Storage layer changes (`storage.py`, `ports.py` — SQLite only here)

### Column lockstep (critical)

Add `tenant_id` to `_MEMORY_COLUMNS` and the equivalent column lists for links,
summaries, sessions, results, and manifest, and update in lockstep:
`_memory_row_values`, `_row_to_memory`, and the `update_memory` SET list. (The
`migrate.py` `_*_COLS` mirror is in `multi-tenancy-postgres`, since migrate.py is
the SQLite→Postgres path.)

### Idempotent migration for existing DBs

Seed ownership: `schema.sql` is the SOLE creator+seeder of the `tenants` table.
`_ensure_tenant_columns` does NOT re-create/seed it; it only GUARDS (if the
`tenants` table is somehow absent on a very old DB, it is a no-op degrade, since
`initialise()` ran `schema.sql` first). This removes the two-owner ambiguity.

Add `_ensure_tenant_columns(conn)` from `initialise()` after the existing
`_ensure_*` calls, ordering load-bearing: (1) `ALTER TABLE ADD COLUMN tenant_id
... DEFAULT 'global'` on each scoped table missing it; (2) rebuild
`concept_links`, `memory_summaries`, and `index_manifest` to their new
UNIQUE/PK + tenant FK (only if the stored DDL still has the old shape), reusing
the `_ensure_index_mode_vision` pattern; (3) only now `CREATE INDEX IF NOT
EXISTS` the tenant-leading indexes (never in a top-of-`schema.sql` block that
runs before the column exists). Guarded by `try/except sqlite3.OperationalError`
with the atomicity rule below.

### Public method signatures (concrete — the dependent specs build on these)

Two kinds of writes, with explicit tenant sourcing:

- **Record-carrying writes** — `add_memory(record)`, `update_memory(record)`,
  `create_session(session)`, `record_query_results(...)`, `upsert_summary(summary)`,
  `add_link(link)`, note/image writes: the tenant is `record.tenant_id` (default
  `"global"`). The write guard runs on that value first.
  - `update_memory`: if `record.tenant_id` differs from the stored row's tenant,
    raise `TenantImmutableError` (a record's tenant is fixed after creation).
  - `add_link`: look up both endpoints; if either is missing raise
    `TenantNotFoundError`, if they differ or `link.tenant_id` differs from the
    shared endpoint tenant raise `CrossTenantLinkError`.
  - `record_query_results`: if the session's `tenant_id` is a NAMED tenant, every
    referenced memory must share it, else `CrossTenantLinkError`. If the session
    is the `"global"` session of an UNSCOPED search, the results may reference any
    tenant's memories (exempt — it is a cross-tenant read audit, not a link; see
    requirements Req 4.5).
- **Id-only writes** — `archive_memory`, `supersede_memory`, `apply_feedback`
  take a trailing `tenant_id: str | None = None`. `None` → act by id, guard on the
  stored row's tenant. Concrete → act only if the stored row matches, else
  not-found. So `--tenant T archive <foreign-id>` is not-found.

**Reads** gain a trailing `tenant_id: str | None = None` (None = today):
- `get_memory(id, tenant_id: str | None = None) -> MemoryRecord | None`:
  `None` → `SELECT ... WHERE id = ?` (today). A concrete value →
  `SELECT ... WHERE id = ? AND tenant_id = ?`, so a foreign id returns `None`.
  This is a committed signature the `tenant-scoped-mcp` spec depends on.
- `search(request)` uses `request.tenant_id`; the full exhaustive list of reads
  gaining `tenant_id: str | None = None` is in requirements Req 5.1 and includes
  `search_around`, `get_stats`, `get_links`, `list_notes`, `get_annotating_notes`,
  `get_annotating_descriptions`, `list_image_file_records`,
  `find_image_file_record`, `anchor_candidates`, `list_summaries`, `get_summary`,
  `get_session`, `manifest_get`/`manifest_paths`, the cochange queries
  (`changed_with`, `documents_timeline`), the summary-job collector
  (`DreamingEngine.collect_summary_jobs`), the image-job collector
  (`vision.image_jobs`), and every dreaming helper. Method arg wins over
  `request.tenant_id`.
- Concept-keyed reads disambiguate per Req 5.6: `get_summary(concept,
  tenant_id=None)` returns the `global` row or `None`; a concrete tenant uses
  `(tenant_id, concept)`.

### New composable storage contracts (committed for the copy spec — Req 5.8)

- `memory_exists_with_content(content, tenant_id: str | None = None) -> bool`.
- `list_memories(filter: MemoryFilter | None = None, tenant_id: str | None =
  None, limit: int | None = None) -> list[MemoryRecord]` (query-text-free list).
- `transaction()` context on the backend (SQLite has one; exposed via `ports.py`)
  and `_on_conn` write variants (`add_memory`/`add_link`/note writes) that run on
  a supplied connection without committing, so `copy_between_tenants` can wrap
  many writes in one transaction. The Postgres equivalents are added by
  `multi-tenancy-postgres`; the SQLite ones are added here.

### Write guard (the enforcement point for Req 4.2 / 4.3)

A private helper `_assert_tenant_writable(conn, tenant_id)` on each backend,
called at the top of every write: `SELECT is_active FROM tenants WHERE id=?`;
`None` → `TenantNotFoundError`; inactive → `TenantInactiveError`. Being an
explicit SELECT, it protects migrated SQLite tables that lack the FK and is
backend-independent. A FK violation on a fresh/rebuilt table is caught and
re-raised as `TenantNotFoundError`. (TOCTOU between the guard SELECT and the
INSERT is acceptable here: the FK on fresh/rebuilt tables is the backstop, and a
tenant deactivated mid-write at worst lets one in-flight write through.)

### Where the predicate goes

The tenant `WHERE tenant_id = ?` is injected into the candidate SQL of
`_fts_scores`, `_trigram_scores`, `_vector_scores`, and `_load_memories`, and into
each `search_around` hop's SQL, **only when a tenant is supplied**. When the
tenant arg is `None`, the SQL is byte-for-byte today's SQL (no predicate). This
keeps Requirement 5.1 literally true and avoids cross-tenant leakage (5.2–5.4).
`_passes_filter` additionally checks `MemoryFilter.tenant_id` as defense-in-depth.

### New tenant methods (Requirement 1)

Add to the `StorageBackend` Protocol in `ports.py` and the SQLite backend:
- `create_tenant(tenant_id: str, name: str = "") -> Tenant` — takes STRINGS.
  Validate `tenant_id` (raise `InvalidTenantIdError` directly on bad charset),
  then `INSERT OR IGNORE` / `INSERT ... ON CONFLICT (id) DO NOTHING`, then
  `SELECT` and return the `Tenant`. Idempotent + concurrency-safe. Taking strings
  (not a `Tenant` model) means the model validator never fires ahead of the
  method, so the method is the single source of the `InvalidTenantIdError`.
- `get_tenant(id) -> Tenant | None`.
- `list_tenants() -> list[Tenant]` — all tenants (active + inactive), ordered by id.
- `set_tenant_active(id, active: bool) -> Tenant` — `TenantNotFoundError` for an
  unknown id; `ProtectedTenantError` when deactivating `global`. No delete API.

Inactive-tenant semantics (resolves the undefined-`is_active` finding): an
inactive tenant is **read-only** — reads confined to it still work, but the write
guard raises `TenantInactiveError`. Reactivation is `set_tenant_active(id, True)`.

---

## Error contract (one typed surface — resolves "clear error" ambiguity)

Defined in `types.py` / a small `core` module and raised by storage:

| Exception | Raised when | CLI | HTTP (future spec) |
|---|---|---|---|
| `TenantNotFoundError` | write to / scope to a tenant not in `tenants` | exit≠0 | 409 (write) / 404 (scope) |
| `TenantInactiveError` | write to a tenant with `is_active=false` | exit≠0 | 409 |
| `ProtectedTenantError` | deactivate `global` (there is no delete API) | exit≠0 | 403 |
| `InvalidTenantIdError` | id fails `^[a-z0-9][a-z0-9_-]{0,127}$` | exit≠0 | 422 |
| `CrossTenantLinkError` | link / reference whose ends differ in tenant | exit≠0 | 409 |
| `TenantImmutableError` | `update_memory` tries to change a record's own tenant | exit≠0 | 409 |
| `ScopeRequiredError` | a scoped caller invokes a global-only op (copy spec) | exit≠0 | 403 |

All subtypes live in `types.py` (task 1). `ScopeRequiredError` is reserved for
the copy spec. `InvalidTenantIdError` subclasses `ValueError`; the `Tenant`
validator raises it (bad `Tenant()` → `ValidationError`), but `create_tenant`
takes a string and validates first, so it raises the plain type (tests assert
the plain type). A backend FK `IntegrityError` → `TenantNotFoundError`. The CLI
mapping is here; the HTTP column is the contract the HTTP/copy specs map.

---

## Transport changes (CLI only in this spec)

This spec wires only the CLI. MCP and HTTP selectors are owned by other specs.

### CLI (`packages/cli/src/mintmory/cli/main.py`)
- Add `--tenant` as a **global Typer callback option** (one declaration, shared
  by all commands). Absent → global semantics (read `None`, write `"global"`);
  `--tenant T` → read confined to T, write stamps T. Resolution lives next to
  `_get_store()`.
- Add `tenant create <id> [--name]` and `tenant list` (prints `id`, `name`,
  `is_active` as a table). Map `TenantError` subtypes to a non-zero exit (code 1)
  with the message.
- **`dream` is NOT given a `--tenant` by this spec.** `DreamingEngine` tenant
  scoping is owned by `cross-tenant-copy-and-dreaming`; until it lands, `dream`
  runs exactly as today (global, no engine change). This spec's `--tenant` wiring
  covers add/get/search/link/feedback/archive/stats/notes/summaries/images only.
  (The dependent spec adds `dream --tenant` when it adds the engine scope.)

### MCP and HTTP — explicitly unchanged here
This spec does NOT modify MCP tool signatures and registers no MCP tenant tools;
the MCP server keeps behaving as the global tenant. It does NOT add the
`X-Tenant-ID` header handling; the HTTP API keeps behaving as the global tenant.
Those surfaces are delivered by `tenant-scoped-mcp` (MCP) and a future HTTP spec.

---

## OpenAPI (`docs/openapi/mintmory.yaml` — edited last)

OpenAPI must not document routes the API does not serve. Since the HTTP API stays
global in this spec, this spec's OpenAPI change is limited to **schema additions
that reflect the data model** (no new paths):

- Add a `Tenant` schema.
- Add the optional `tenant_id` field to `MemoryRecord`, `MemoryCreate`,
  `MemoryFilter`, `SearchRequest`, `ConceptLink`, `ConceptLinkCreate`,
  `MemorySummary`, `QuerySession` (these fields now exist on the models the API
  already returns/accepts, so the spec stays truthful).
- Do NOT add `POST /tenants` / `GET /tenants` or the `X-Tenant-ID` header here —
  those are served by the HTTP tenant spec that adds the actual routes, added in
  the same change as the code so the spec↔route parity holds.

---

## Testing strategy

The per-task test bullets in tasks.md are the authoritative test list. Decidable
scenarios worth calling out here:

- **SQL parity (Req 5.4):** "byte-for-byte today's SQL" is tested by asserting
  the unscoped (`None`) path takes the same code branch as before — concretely,
  a unit test checks that no `WHERE tenant_id` clause is emitted when
  `tenant_id is None` (assert on the built query string the backend produces),
  and a behavioural test asserts unscoped results equal the pre-feature results
  on a single-tenant DB. No external SQL-trace tooling is required.
- **Write guard** on a fresh AND a migrated (no-FK) DB (guard is load-bearing).
- **Migration** (Req 3.4): full migration succeeds; a simulated mid-migration
  failure leaves the DB readable and unchanged; a second `initialise()` no-op.
- **Timestamp equivalence (Req 1.7):** the test compares tenant identity/
  `is_active`, not the timestamp value.
- (Postgres parity + migrated-Postgres tests live in `multi-tenancy-postgres`,
  not here — this unit is SQLite-only, so its unattended run needs no Postgres
  service.)

Gates (per `tech.md`): `uv run pytest` (coverage ≥ 80%), `uv run mypy
packages/`, `uv run ruff check packages/` all exit 0.

---

## Migration atomicity and failure (Req 3.4)

`_ensure_tenant_columns` commits only when the whole migration completed; on
`sqlite3.OperationalError` it rolls back so the DB is either fully pre-feature or
fully migrated (never half). A pre-feature DB that cannot migrate keeps working
untenanted (the guard is a no-op while `tenants` is absent). Test: full migration
succeeds; a simulated mid-migration failure leaves the DB readable and unchanged.

## Risks

- **Lockstep drift** → one task enumerates every site; schema-gate + round-trip
  tests catch omissions.
- **UNIQUE change on existing DBs** → the `_ensure_index_mode_vision` rebuild
  pattern; the auto-named `concept UNIQUE` is dropped by rebuild (not by name).
- **Silent cross-tenant leak** → predicate in candidate SQL + traversal;
  `_passes_filter` is defense-in-depth only.
