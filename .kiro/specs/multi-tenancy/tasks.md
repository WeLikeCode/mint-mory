# Tasks — Multi-Tenancy (Phase 1: foundation)

Order follows the source-of-truth hierarchy (`types.py` → `schema.sql` →
`schema_postgres.sql` → `openapi.yaml`) and the package dependency order
(`core` before `mcp`/`api`/`cli`). Each task is TDD: write the failing test
first, confirm it fails for the right reason, implement, then run the gate.

Gate per task (from `tech.md`): the affected package's tests exit 0,
`uv run mypy packages/<pkg>/` exits 0, `uv run ruff check packages/<pkg>/`
exits 0. Full gate before PR: `uv run pytest` (coverage ≥ 80%),
`uv run mypy packages/`, `uv run ruff check packages/`.

---

- [ ] 1. Data model: `Tenant`, `TENANT_GLOBAL`, and `tenant_id` fields in `types.py`
  - Add `TENANT_GLOBAL = "global"` constant and the `Tenant` Pydantic model
    (id/name/is_active/created_at/updated_at) with an id charset validator.
  - Add `tenant_id: str = Field(default=TENANT_GLOBAL, ...)` to `MemoryRecord`,
    `ConceptLink`, `MemorySummary`, `QuerySession`, `QueryResult`.
  - Add `tenant_id: str | None = None` to `MemoryFilter` and `SearchRequest`.
  - Add `tenant_id` to the `ManifestEntry` TypedDict in `ports.py`.
  - Write unit tests asserting defaults resolve to `global` and the validator
    rejects bad ids.
  - _Requirements: 1.6, 2.1, 2.2, 5.1_

- [ ] 2. SQLite schema: `tenants` table, `tenant_id` columns, uniqueness, indexes
  - Add the `tenants` table to `schema.sql` and seed `global` via
    `INSERT OR IGNORE`.
  - Add `tenant_id TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id)` to
    `memories`, `concept_links`, `memory_summaries`, `query_sessions`,
    `query_results`, `index_manifest`.
  - Change `memory_summaries` uniqueness to `UNIQUE (tenant_id, concept)` and
    `concept_links` uniqueness to
    `UNIQUE (tenant_id, source_memory_id, target_memory_id, link_type)`.
  - Add tenant-leading indexes (`idx_memories_tenant`, `idx_links_tenant`,
    `idx_summaries_tenant`, `idx_sessions_tenant`).
  - Keep the three FTS5 triggers unchanged.
  - _Requirements: 1.1, 1.2, 2.3, 2.4, 6.1, 6.2_

- [ ] 3. Schema-compliance gate: extend `test_schema.py`
  - Add `tenants` to REQUIRED_TABLES; add `tenant_id` to
    REQUIRED_MEMORIES_COLUMNS / REQUIRED_LINKS_COLUMNS /
    REQUIRED_SESSIONS_COLUMNS; add the new indexes to REQUIRED_INDEXES.
  - Add a test that a fresh `:memory:` DB seeds exactly one `global` tenant.
  - Add a FK test: inserting a memory with a non-existent `tenant_id` raises
    `IntegrityError`.
  - Confirm enum↔CHECK parity, existing FK, and FTS trigger tests still pass.
  - _Requirements: 8.1, 8.2_

- [ ] 4. Storage writes + column lockstep (`storage.py`, SQLite)
  - Add `tenant_id` to `_MEMORY_COLUMNS` and the link/summary/session/result/
    manifest column lists; update `_memory_row_values`, `_row_to_memory`, and
    the `update_memory` SET list in lockstep.
  - Thread `tenant_id` through `add_memory`, `add_link`, `create_session`,
    `upsert_summary`, `record_query_results` (value carried on the record).
  - Enforce same-tenant FK for links: reject `add_link` when source and target
    tenants differ (Requirement 6.3).
  - Write round-trip tests (write under a tenant → read back correct
    `tenant_id`) and the cross-tenant-link rejection test.
  - _Requirements: 4.1, 4.2, 4.3, 6.3, 6.4_

- [ ] 5. Idempotent migration for existing SQLite DBs (`_ensure_tenant_columns`)
  - Implement `_ensure_tenant_columns(conn)` called from `initialise()` after
    the existing `_ensure_*` calls: create/seed `tenants`, add missing
    `tenant_id` columns with `DEFAULT 'global'`, and rebuild tables whose UNIQUE
    constraint must change (reuse the `_ensure_index_mode_vision` rebuild
    pattern). Guard with try/except `sqlite3.OperationalError`.
  - Mirror the `is_note` migration tests: build a pre-feature-shaped DB, run
    `initialise()`, assert columns added + all rows backfilled to `global`, and
    a second `initialise()` is a no-op.
  - _Requirements: 3.1, 3.2, 3.4, 3.5_

- [ ] 6. Opt-in query/search scoping (`storage.py` + `hybrid_search.py`)
  - Inject `WHERE tenant_id = ?` into `_fts_scores`, `_trigram_scores`,
    `_vector_scores`, `_load_memories`, and each `search_around` hop — only when
    a tenant is supplied; emit today's exact SQL when the tenant arg is `None`.
  - Add optional `tenant_id` to `search`, `search_around`, `get_stats`, and the
    dreaming helper queries; `None` = global (today).
  - Add `MemoryFilter.tenant_id` check in `_passes_filter` as defense-in-depth.
  - Tests: scoped search returns only tenant T; unscoped returns all; parity
    with pre-feature results on a single-tenant DB; `search_around` under T does
    not pull other-tenant memories.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 7. Tenant management methods (`ports.py` + `storage.py`)
  - Add to the `StorageBackend` Protocol and `SqliteBackend`: `create_tenant`
    (idempotent), `get_tenant`, `list_tenants`, `set_tenant_active` (reject
    deactivating `global`).
  - Tests: create/get/list; create existing id is idempotent; deactivating
    `global` is rejected; writing to a non-existent tenant fails at the FK.
  - _Requirements: 1.3, 1.4, 1.5, 4.2_

- [ ] 8. Postgres parity (`schema_postgres.sql` + `storage_postgres.py`)
  - Mirror the `tenants` table (BOOLEAN/TIMESTAMP, `ON CONFLICT DO NOTHING`
    seed), the `tenant_id` columns + FK, the per-tenant UNIQUE constraints, and
    the tenant-leading indexes.
  - Thread `tenant_id` through the Postgres backend writes and inject the tenant
    predicate into its candidate/traversal SQL, matching the SQLite semantics.
  - Add/adjust Postgres schema-parity tests where they exist.
  - _Requirements: 2.4, 5.2, 6.1, 6.2, 8.1_

- [ ] 9. SQLite→Postgres migration (`migrate.py`)
  - Add `tenant_id` to `_MEMORIES_COLS` and every other `_*_COLS` tuple and the
    matching `_insert_*_batch` SQL; add the `tenants` table to the migration and
    classification dicts so checksum verification passes.
  - Test the migration moves `tenant_id` and the `tenants` table correctly.
  - _Requirements: 8.4_

- [ ] 10. CLI transport (`packages/cli/src/mintmory/cli/main.py`)
  - Add a `--tenant` option (absent → `global`) resolved near `_get_store()` and
    passed into core calls for add/search/link/dream/stats/notes/summaries.
  - Add `tenant create <id> [--name]` and `tenant list` commands.
  - Tests: command without `--tenant` behaves as today; with `--tenant T`
    scopes correctly.
  - _Requirements: 7.1, 7.4, 7.5_

- [ ] 11. MCP transport (`packages/mcp/src/mintmory/mcp/server.py`, `tools.py`)
  - Add optional `tenant_id` to the tool signatures (absent → `global`), with an
    env-var default for a per-process tenant; keep the `_store` singleton.
  - Add `tenant_create` / `tenant_list` tools.
  - Tests: tool input/output shapes include tenant; omission → global.
  - _Requirements: 7.2, 7.4, 7.5_

- [ ] 12. HTTP API transport (`packages/api/src/mintmory/api/app.py`, `schemas.py`)
  - Add a `resolve_tenant()` dependency reading `X-Tenant-ID` (absent →
    `global`), injected into routes and passed to core.
  - Add `POST /tenants` and `GET /tenants`; add `tenant_id` to the relevant
    request/response schemas.
  - Tests (httpx TestClient): no header → global; header → scoped; create/list
    tenants; writing to a missing tenant returns a clear error.
  - _Requirements: 7.3, 7.4, 7.5_

- [ ] 13. OpenAPI spec (`docs/openapi/mintmory.yaml`) — edited last
  - Add the `Tenant` schema and a reusable `X-Tenant-ID` header parameter;
    reference it from the relevant operations.
  - Add `tenant_id` to `MemoryRecord`, `MemoryCreate`, `MemoryFilter`,
    `SearchRequest`, `ConceptLink`, `ConceptLinkCreate`, `MemorySummary`,
    `QuerySession`.
  - Add `POST /tenants` and `GET /tenants` paths.
  - _Requirements: 8.3_

- [ ] 14. Integration + full-suite gate (`tests/integration/`)
  - Add a cross-package test: add→search→feedback under a named tenant and under
    global, asserting isolation when scoped and identical-to-today behaviour
    when unscoped.
  - Run the full gate: `uv run pytest` (coverage ≥ 80%),
    `uv run mypy packages/`, `uv run ruff check packages/` — all exit 0.
  - _Requirements: 3.3, 5.1, 8.5_
