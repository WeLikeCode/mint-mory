# Tasks — Multi-Tenancy (Phase 1: foundation, SQLite + core + CLI)

Order follows the source-of-truth hierarchy (`types.py` → `schema.sql` →
`openapi.yaml`) and the package dependency order (`core` before the CLI). Each
task is TDD: write the failing test first, confirm it fails for the right
reason, implement, then run the gate.

Gate per task (from `tech.md`): the affected package's tests exit 0,
`uv run mypy packages/<pkg>/` exits 0, `uv run ruff check packages/<pkg>/`
exits 0. Full gate before PR: `uv run pytest` (coverage ≥ 80%),
`uv run mypy packages/`, `uv run ruff check packages/`.

**Scope (ownership):** this unit owns the data model, `schema.sql` (SQLite),
the SQLite backend + write guard + composable contracts, the SQLite migration,
schema-only OpenAPI, and the CLI tenant surface. It does NOT touch Postgres
(`schema_postgres.sql`, `storage_postgres.py`, `migrate.py` → the
`multi-tenancy-postgres` spec), does NOT change MCP tool signatures or register
MCP tenant tools (→ `tenant-scoped-mcp`), and does NOT scope the `DreamingEngine`
(→ `cross-tenant-copy-and-dreaming`).

---

- [ ] 1. Data model + errors (`types.py`)
  - `TENANT_GLOBAL = "global"` and the `Tenant` model (string id validator
    raising `InvalidTenantIdError`).
  - Error types in `types.py`: `TenantError` base + `TenantNotFoundError`,
    `TenantInactiveError`, `ProtectedTenantError`, `InvalidTenantIdError`
    (subclasses `ValueError`), `CrossTenantLinkError`, `TenantImmutableError`,
    and `ScopeRequiredError` (reserved for the copy spec).
  - `tenant_id: str = Field(default=TENANT_GLOBAL, ...)` on `MemoryRecord`,
    `ConceptLink`, `MemorySummary`, `QuerySession`, `QueryResult`; `tenant_id:
    str | None = None` on `MemoryFilter`, `SearchRequest`; `tenant_id` on the
    `ManifestEntry` TypedDict (`ports.py`).
  - Tests: defaults → `global`; bad id → `InvalidTenantIdError`; error subclassing.
  - _Requirements: 1.6, 1.7, 2.1, 2.2_

- [ ] 2. SQLite schema (`schema.sql`)
  - `tenants` table + `INSERT OR IGNORE` seed of `global` (sentinel timestamp) —
    schema.sql is the SOLE owner of the tenants CREATE+seed.
  - `tenant_id TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id)` on the six
    scoped tables (fresh-schema FK). Uniqueness → `UNIQUE (tenant_id, concept)`
    and `UNIQUE (tenant_id, source, target, link_type)`; `index_manifest` PK →
    `(tenant_id, path)`. Do NOT create the tenant-leading indexes in a block that
    runs before `_ensure_tenant_columns`. FTS5 triggers unchanged.
  - _Requirements: 1.1, 1.2, 2.4, 6.1, 6.2, 6.5_

- [ ] 3. Schema-compliance gate (`test_schema.py`)
  - `tenants` in REQUIRED_TABLES; `tenant_id` in the REQUIRED column sets for
    memories, concept_links, query_sessions AND memory_summaries, query_results,
    manifest; tenant-leading indexes in REQUIRED_INDEXES; fresh DB seeds exactly
    one `global`. Confirm enum↔CHECK parity, FK, FTS trigger tests still pass.
  - _Requirements: 8.1, 8.2_

- [ ] 4. SQLite writes, lockstep, write guard, composable contracts (`storage.py`)
  - `tenant_id` into `_MEMORY_COLUMNS` + link/summary/session/result/manifest
    lists; `_memory_row_values`, `_row_to_memory`, `update_memory` SET in lockstep.
  - `_assert_tenant_writable(conn, tenant_id)` at the top of every write; FK
    `IntegrityError` → `TenantNotFoundError`. `update_memory` tenant change →
    `TenantImmutableError`; cross-tenant `add_link`/`record_query_results`/
    `supersede_memory` → `CrossTenantLinkError`. Id-only writes
    (`archive_memory`, `supersede_memory`, `apply_feedback`) take `tenant_id:
    str | None = None`, guarding on the stored row's tenant.
  - Add `memory_exists_with_content(content, tenant_id=None)`,
    `list_memories(filter, tenant_id, limit)`, the `transaction()` context
    (expose in `ports.py`), and `_on_conn` no-commit write variants for the copy
    spec.
  - Tests: round-trip; missing/inactive-tenant writes; cross-tenant/immutable
    errors; id-only guard; contracts behave.
  - _Requirements: 2.3, 4.1, 4.2, 4.3, 4.4, 5.8, 6.3, 6.4_

- [ ] 5. Idempotent SQLite migration + index ordering (`_ensure_tenant_columns`)
  - After the existing `_ensure_*`: (1) ADD COLUMN `tenant_id` where missing;
    (2) rebuild `concept_links`, `memory_summaries`, `index_manifest` to new
    UNIQUE/PK + FK (only if old shape); (3) then `CREATE INDEX IF NOT EXISTS` the
    tenant-leading indexes. `_ensure_tenant_columns` does NOT create/seed tenants
    (schema.sql owns it). Guard + atomicity per design.
  - Tests: pre-feature DB → columns added, rows backfilled to `global`, indexes
    present, write guard rejects a missing tenant on the migrated (no-FK) DB,
    simulated mid-migration failure leaves DB unchanged, second `initialise()`
    no-op.
  - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 6.5, 6.6_

- [ ] 6. Opt-in read/search scoping (`storage.py`, `hybrid_search.py`)
  - Add `tenant_id: str | None = None` to the exhaustive read list in Req 5.1
    (incl. `get_memory`, `search_around`, `get_stats`, `get_links`, notes/image
    reads, `list_summaries`, `get_summary`, `get_session`, manifest reads,
    cochange queries, summary/image job collectors, dreaming helpers). Inject
    `WHERE tenant_id = ?` into candidate SQL + `search_around` hops + `get_memory`
    only when concrete; emit today's SQL on `None`. Concept disambiguation per
    Req 5.6. `_passes_filter` checks `MemoryFilter.tenant_id`.
  - Tests: `get_memory(id,"T")` → None for foreign id; confined vs unscoped
    parity; `search_around` confined; read to missing tenant → empty (not raise);
    `get_summary` disambiguation.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [ ] 7. Tenant management methods (`ports.py` + `storage.py`)
  - `create_tenant(tenant_id: str, name="") -> Tenant` (validate id →
    `InvalidTenantIdError`; INSERT OR IGNORE + SELECT; idempotent), `get_tenant`,
    `list_tenants` (all, ordered), `set_tenant_active` (`TenantNotFoundError`
    unknown; `ProtectedTenantError` deactivating `global`).
  - Tests: create/get/list; existing id idempotent; invalid id; deactivate
    `global` rejected; `set_tenant_active` unknown id; inactive = read-only.
  - _Requirements: 1.3, 1.4, 1.5, 1.8, 4.2, 4.3_

- [ ] 8. CLI transport (`packages/cli/src/mintmory/cli/main.py`)
  - `--tenant` as a GLOBAL Typer callback option (absent → global semantics;
    `T` → confined reads / write T). Apply it to:
    add, get, search, link, feedback, archive, stats, notes, summaries, images.
    Do NOT apply it to `dream` (dream stays global until the copy spec adds the
    engine scope). Add `tenant create <id> [--name]` and `tenant list` (prints
    id/name/is_active). Map `TenantError` subtypes to exit code 1 + message.
  - Tests: no `--tenant` as today; `--tenant T` scopes add/get/search/archive;
    write to missing/inactive tenant exits non-zero; `--tenant <missing> search`
    returns empty (exit 0).
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 9. Confirm MCP + HTTP remain global (regression)
  - Assert MCP tools and HTTP routes still operate as the global tenant: no
    signature changes, no MCP tenant tools, no `X-Tenant-ID`. Regression test:
    MCP `memory_search` / HTTP `POST /memories/search` with no tenant returns all
    rows after this unit lands.
  - _Requirements: 7.5_

- [ ] 10. OpenAPI (`docs/openapi/mintmory.yaml`) — schema additions only
  - Add the `Tenant` schema; add optional `tenant_id` to `MemoryRecord`,
    `MemoryCreate`, `MemoryFilter`, `SearchRequest`, `ConceptLink`,
    `ConceptLinkCreate`, `MemorySummary`, `QuerySession`. Do NOT add `POST
    /tenants` / `GET /tenants` paths or the `X-Tenant-ID` header (no routes are
    served here — spec↔route parity must hold).
  - _Requirements: 8.2_

- [ ] 11. Integration + full-suite gate (`tests/integration/`)
  - add→search→feedback under a named tenant and under global; isolation when
    confined, identical-to-today when unscoped; write guard + `create_tenant` via
    CLI. Run the full gate (SQLite only; no Postgres needed).
  - _Requirements: 3.3, 5.1, 8.4_
