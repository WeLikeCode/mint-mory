# Design — Multi-Tenancy (Phase 1: foundation)

## Overview

This design adds tenancy as a **row-scoped, shared-table** data primitive. Every
table-backed entity gains a `tenant_id TEXT` column (FK to a new `tenants`
table), defaulting to the reserved tenant `global`. A single `.db` /
Postgres database continues to hold all tenants.

The change is backwards compatible by construction:
- The column default is `global`, so inserts that do not mention a tenant behave
  as today.
- An idempotent column-add migration backfills every pre-existing row to
  `global`, following the established `_ensure_*` pattern in `StorageAdapter`.
- Reads/searches are **unscoped by default** (global, exactly like today). A
  tenant predicate is injected into the candidate SQL only when a tenant selector
  is supplied.

The work follows the source-of-truth hierarchy strictly:
`types.py` → `schema.sql` (+ `schema_postgres.sql`) → `openapi.yaml`.

### Grounding notes (verified against current code)

- No tenant/owner/workspace concept exists anywhere in `packages/` today.
- `build_storage()` in `storage_factory.py` is the single construction
  chokepoint used by all three transports (CLI `main.py`, MCP `server.py`, API
  `app.py` — note the API has `app.py` + `schemas.py`, no `routes/` dir).
- Table-backed models: `MemoryRecord`, `ConceptLink`, `MemorySummary`,
  `QuerySession`, `QueryResult`; plus the `index_manifest` table, which has no
  Pydantic model (it is the `ManifestEntry` TypedDict in `ports.py`).
- Candidate rows for search are pulled globally by `_fts_scores`,
  `_trigram_scores`, `_vector_scores`, and `_load_memories`; `_passes_filter`
  in `hybrid_search.py` is a Python-side post-load filter only.
- `memory_summaries.concept` is globally `UNIQUE`; `concept_links` is
  `UNIQUE (source_memory_id, target_memory_id, link_type)`.
- `_MEMORY_COLUMNS` (storage.py) + `_memory_row_values` + `_row_to_memory` +
  the `update_memory` SET list must stay in lockstep; `migrate.py` mirrors them
  in `_MEMORIES_COLS` + `_insert_memories_batch`.
- Schema gate lives in `test_schema.py` (REQUIRED_TABLES / COLUMNS / INDEXES /
  TRIGGERS, enum↔CHECK parity, FK enforcement, `_ensure_*` migration test
  pattern).

---

## Architecture

### Tenant resolution flow

```
transport selector (CLI --tenant | MCP ctx/env | HTTP X-Tenant-ID)
        │   (absent → "global")
        ▼
core function call  add_memory(..., tenant_id=...) / search(..., tenant_id=None|T)
        ▼
StorageBackend (SqliteBackend | PostgresBackend)
        │   write: INSERT ... (tenant_id)      [FK to tenants(id)]
        │   read (unscoped): no predicate      [today's behaviour]
        │   read (scoped T): WHERE tenant_id = ? in candidate SQL + traversal
        ▼
one database, all tenants
```

The tenant selector is a plain value threaded through core function signatures.
There is no implicit global state and no auth. `TENANT_GLOBAL = "global"` is a
module-level constant in `types.py` reused everywhere.

### Why row-scoped (not DB-per-tenant)

- Smallest backwards-compatible delta; keeps the single-file storage design.
- One `initialise()`, one schema gate, one FTS index set.
- Enables future cross-tenant admin/aggregate reads.
- Trade-off: isolation is query-enforced. Mitigated by pushing the predicate
  into candidate SQL (not just `_passes_filter`) so no un-scoped row reaches
  fusion when a tenant is supplied.

---

## Data model changes (`types.py` — edited first)

### New: `Tenant` model + constant

```python
TENANT_GLOBAL = "global"

class Tenant(BaseModel):
    id: str = Field(default=TENANT_GLOBAL, min_length=1, max_length=128)
    name: str = ""
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

Tenant id charset is constrained (e.g. `^[a-z0-9][a-z0-9_-]{0,127}$`) via a
field validator so ids are safe, stable, and predictable.

### Add `tenant_id` to every table-backed model

`MemoryRecord`, `ConceptLink`, `MemorySummary`, `QuerySession`, `QueryResult`
each gain:

```python
tenant_id: str = Field(default=TENANT_GLOBAL, min_length=1, max_length=128)
```

The `index_manifest` carrier (`ManifestEntry` TypedDict in `ports.py`) also gains
`tenant_id` for parity.

### Filter / request surface

- `MemoryFilter` gains `tenant_id: str | None = None` (None = unscoped = today).
- `SearchRequest` gains `tenant_id: str | None = None`.
- `MemoryStats` is unchanged in shape; `get_stats` gains an optional tenant arg.

Default `None` preserves backwards compatibility (Requirement 5.1).

---

## Schema changes (`schema.sql` and `schema_postgres.sql` — edited second)

### New `tenants` table

SQLite:
```sql
CREATE TABLE IF NOT EXISTS tenants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
-- seed the reserved global tenant (idempotent)
INSERT OR IGNORE INTO tenants (id, name, is_active, created_at, updated_at)
VALUES ('global', 'Global (default) tenant', 1,
        '1970-01-01T00:00:00', '1970-01-01T00:00:00');
```

Postgres mirrors this with `BOOLEAN`/`TIMESTAMP` and
`INSERT ... ON CONFLICT (id) DO NOTHING`.

### `tenant_id` column on every scoped table

Each of `memories`, `concept_links`, `memory_summaries`, `query_sessions`,
`query_results`, `index_manifest` gains:

```sql
tenant_id TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id)
```

Notes:
- `NOT NULL DEFAULT 'global'` is what makes fresh inserts and legacy rows land in
  the global tenant automatically.
- The FK to `tenants(id)` enforces Requirement 4.2 (no writing to a
  non-existent tenant). Because the schema seeds `global`, the default never
  dangles.
- SQLite requires `PRAGMA foreign_keys = ON` (already re-asserted per connection
  in `StorageAdapter.connect()`), so the FK is enforced at runtime.

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

The existing indexes remain (global reads still use them). Postgres mirrors the
same index set.

### FTS / tenant interaction

- SQLite FTS5 (`memories_fts`) is external-content keyed on `memories.rowid`; the
  three triggers stay exactly as-is (they index `content` only). Tenant scoping
  of FTS results is done by **joining back to `memories` and filtering
  `memories.tenant_id = ?`** in `_fts_scores` / `_trigram_scores` — the triggers
  are untouched, so Invariant §4.6 holds.
- Postgres `content_tsv` generated column + GIN index are likewise unchanged;
  the tenant predicate is a `WHERE tenant_id = ?` on `memories`.

---

## Storage layer changes (`storage.py`, `storage_postgres.py`, `ports.py`)

### Column lockstep (critical)

Add `tenant_id` to `_MEMORY_COLUMNS` and the equivalent column lists for links,
summaries, sessions, results, and manifest, and update in lockstep:
`_memory_row_values`, `_row_to_memory`, the `update_memory` SET list, and the
mirrored tuples/inserts in `migrate.py` (`_MEMORIES_COLS`,
`_insert_memories_batch`, and the other `_*_COLS` / `_insert_*_batch`).

### Idempotent migration for existing DBs

Add `_ensure_tenant_columns(conn)` called from `initialise()` after the three
existing `_ensure_*` calls. It follows the proven pattern:

```python
def _ensure_tenant_columns(self, conn) -> None:
    try:
        # 0. ensure tenants table + seed global (schema.sql already does this on
        #    fresh DBs; guard for pre-existing DBs)
        # 1. for each scoped table: PRAGMA table_info; if 'tenant_id' missing →
        #    ALTER TABLE <t> ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'global'
        # 2. existing rows inherit the DEFAULT 'global' automatically
        conn.commit()
    except sqlite3.OperationalError:
        pass  # degrade gracefully (old/locked SQLite), consistent with peers
```

SQLite note: `ALTER TABLE ADD COLUMN` cannot add a column that is simultaneously
a FK with a non-constant default in one step on very old SQLite; the column is
added with `DEFAULT 'global'` (constant) and the FK relationship is relied upon
for fresh-schema tables. The `tenants` table is created/seeded first so `global`
always resolves. Uniqueness changes on pre-existing DBs are handled by the
table-rebuild approach already used by `_ensure_index_mode_vision`
(CREATE new → INSERT SELECT → DROP old → RENAME) where a UNIQUE constraint must
change; the rebuild is guarded and idempotent.

### Public method signatures

Writes gain an explicit tenant:
- `add_memory(record)` — tenant travels on the record (`record.tenant_id`).
- `add_link(link)` — tenant on the link; reject if source/target tenants differ
  (looked up/validated) → Requirement 6.3.
- `create_session(...)`, `upsert_summary(...)`, `record_query_results(...)` —
  tenant on the record.

Reads gain an optional tenant:
- `search(request)` — reads `request.tenant_id` (None = unscoped).
- `search_around(...)`, `get_stats(...)`, and dreaming helpers gain
  `tenant_id: str | None = None`; None keeps today's global behaviour.
- `get_memory(id)` stays by-id but, when future callers pass a tenant, can
  enforce `AND tenant_id = ?`. Phase 1 keeps `get_memory(id)` global-by-id for
  backwards compatibility and adds the scoped path where a tenant is available.

### Where the predicate goes

The tenant `WHERE tenant_id = ?` is injected into the candidate SQL of
`_fts_scores`, `_trigram_scores`, `_vector_scores`, and `_load_memories`, and into
each `search_around` hop's SQL, **only when a tenant is supplied**. When the
tenant arg is `None`, the SQL is byte-for-byte today's SQL (no predicate). This
keeps Requirement 5.1 literally true and avoids cross-tenant leakage (5.2–5.4).
`_passes_filter` additionally checks `MemoryFilter.tenant_id` as defense-in-depth.

### New tenant methods (Requirement 1)

Add to the `StorageBackend` Protocol in `ports.py` and both backends:
- `create_tenant(tenant: Tenant) -> Tenant` — INSERT; on existing id, return the
  existing row (idempotent create). Rationale: idempotent create is friendlier
  for provisioning and matches the `INSERT OR IGNORE` ethos; the transport layer
  may expose an explicit "already exists" signal.
- `get_tenant(id) -> Tenant | None`.
- `list_tenants() -> list[Tenant]`.
- `set_tenant_active(id, active: bool)` — rejects when `id == "global"` and
  `active is False` (Requirement 1.5). No hard delete of `global`.

---

## Transport changes

All three resolve a selector and pass it into core; none duplicates logic. The
selector defaults to `global` when absent.

### CLI (`packages/cli/src/mintmory/cli/main.py`)
- Add a global `--tenant` option (Typer) resolved in `_get_store()`-adjacent
  code or per command; absent → `global`.
- Add `tenant create <id> [--name]` and `tenant list` commands.

### MCP (`packages/mcp/src/mintmory/mcp/server.py`, `tools.py`)
- Tools accept an optional `tenant_id` argument (absent → `global`), or resolve
  from an env var for a per-process default. The module-level singleton `_store`
  stays; tenancy is a per-call value, not a per-store binding.
- Add `tenant_create` / `tenant_list` tools.

### HTTP API (`packages/api/src/mintmory/api/app.py`, `schemas.py`)
- Add a FastAPI dependency `resolve_tenant()` reading header `X-Tenant-ID`
  (absent → `global`), injected into each route and passed to core.
- Add `POST /tenants` (create) and `GET /tenants` (list). Add `tenant_id` to the
  relevant request schemas / responses where appropriate.
- The single `_store` + `get_store()` singleton is unchanged; tenancy is a
  per-request value.

---

## OpenAPI (`docs/openapi/mintmory.yaml` — edited last)

- Add a `Tenant` schema and a reusable `TenantHeader` parameter
  (`X-Tenant-ID`, optional, default `global`) under `components`.
- Reference `TenantHeader` from the relevant operations.
- Add `tenant_id` to `MemoryRecord`, `MemoryCreate`, `MemoryFilter`,
  `SearchRequest`, `ConceptLink`, `ConceptLinkCreate`, `MemorySummary`, and
  `QuerySession` schemas.
- Add `POST /tenants` and `GET /tenants` paths.

---

## Testing strategy

Unit (`:memory:` SQLite, mock embedder, no LLM):
- Schema gate additions: `tenants` in REQUIRED_TABLES; `tenant_id` in each
  REQUIRED_*_COLUMNS set; new indexes in REQUIRED_INDEXES.
- Fresh DB seeds the `global` tenant exactly once.
- FK: writing a memory with a non-existent `tenant_id` raises `IntegrityError`.
- Per-tenant uniqueness: two tenants can hold a summary for the same concept and
  equivalent links; same-tenant duplicate link is still ignored/idempotent.
- Cross-tenant link creation is rejected.
- Scoped search returns only tenant T rows; unscoped search returns all rows
  (parity with pre-feature results on a single-tenant DB).
- `search_around` under T does not pull other-tenant memories.
- Migration: replicate the `is_note` backfill test — build a pre-feature-shaped
  DB (no `tenant_id`), run `initialise()`, assert columns added, all rows
  backfilled to `global`, and a second `initialise()` is a no-op.

Integration (`tests/integration/`, real file):
- Full add→search→feedback loop under a named tenant and under global, asserting
  isolation when scoped and identical-to-today behaviour when unscoped.

Postgres parity:
- Mirror the schema/column/uniqueness assertions for `schema_postgres.sql`; add
  `tenant_id` to `migrate.py` tuples and assert the migration + checksum still
  pass.

Gates (per `tech.md`): `uv run pytest` (coverage ≥ 80%), `uv run mypy
packages/`, `uv run ruff check packages/` all exit 0.

---

## Backwards-compatibility checklist

- [ ] Column default `'global'` on every scoped table.
- [ ] `tenants` seeded with `global`; `global` cannot be deactivated/deleted.
- [ ] Reads/searches with no tenant selector emit today's exact SQL.
- [ ] `_ensure_tenant_columns` idempotent and graceful on old/locked SQLite.
- [ ] `_MEMORY_COLUMNS` / row (de)serialisers / `update_memory` / `migrate.py`
      tuples all updated in lockstep.
- [ ] FTS triggers untouched; tenant scoping via join-back filter.
- [ ] Schema gate, enum↔CHECK parity, FK, and trigger tests pass.

---

## Risks and mitigations

- **Lockstep drift** (column added in one place, missed in another) → a single
  task enumerates every lockstep site; schema-gate + round-trip serialise tests
  catch omissions.
- **UNIQUE change on existing DBs** requires table rebuild → reuse the proven
  `_ensure_index_mode_vision` rebuild pattern; guarded + idempotent.
- **Silent cross-tenant leak** if predicate is only in `_passes_filter` →
  predicate is injected into candidate SQL and traversal; `_passes_filter` is
  defense-in-depth, not the enforcement point.
- **Postgres/SQLite divergence** → schema and migration tasks are paired; both
  schema files and `migrate.py` are updated together.
