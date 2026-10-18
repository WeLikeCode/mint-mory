# Tasks — Tenant-Scoped MCP

> **Depends on:** the `multi-tenancy` spec (`.kiro/specs/multi-tenancy/`). That
> spec must be implemented first — it provides the `Tenant` model, the `tenants`
> table, the `tenant_id` columns, the `create_tenant` / `get_tenant` /
> `list_tenants` storage methods, and the storage-level tenant scoping (the
> tenant predicate in candidate SQL + `search_around`). Do not start these tasks
> until that spec is complete.

These tasks assume the `multi-tenancy` data model and storage scoping exist.

Each task is TDD: write the failing test first, confirm it fails for the right
reason, implement, then run the gate. Per-task gate (from `tech.md`): the MCP
package tests exit 0, `uv run mypy packages/mcp/` exits 0, `uv run ruff check
packages/mcp/` exits 0. Full gate before PR: `uv run pytest` (coverage ≥ 80%),
`uv run mypy packages/`, `uv run ruff check packages/`.

---

- [ ] 1. MCP scope configuration + resolution (`config.py`, `server.py`)
  - Add `McpSettings(env_prefix="MINTMORY_MCP_")` with `tenant: str = ""` in
    `config.py`.
  - Add a `--tenant <id>` option to the `mintmory-mcp` entrypoint (the Typer
    callback handling `--transport`/`--port`); CLI wins over env; empty = global.
  - Add module-level `_scope_tenant` and `_effective_tenant()` (global→None,
    named→T) in `server.py`.
  - Tests: unset → `global`; env sets scope; `--tenant` overrides env;
    `_effective_tenant()` mapping.
  - _Requirements: 1.1, 1.2, 1.3, 1.7, 4.1_

- [ ] 2. Fail-fast bootstrap validation (`server.py`)
  - Implement `_bootstrap_scope(scope)`: set `_scope_tenant`, call
    `_get_store()`, then validate — invalid id → `InvalidTenantIdError`; named
    scope with `get_tenant(scope) is None` → `TenantNotFoundError`, exit
    non-zero; inactive scope → start with a warning (read-only); `global` →
    always valid. Call it from both the stdio and SSE/HTTP serve paths.
  - No implicit tenant creation; no silent fallback to global.
  - Tests: unknown tenant → error; invalid id → error; inactive tenant → starts;
    existing active → starts; global → starts.
  - _Requirements: 1.4, 1.5, 1.6, 1.8_

- [ ] 3. Scope the read/search tools (`server.py`, `tools.py`)
  - Thread `_effective_tenant()` into `memory_search` (via
    `SearchRequest.tenant_id`), `search_around`, `memory_get` (scoped get so a
    foreign id is not-found), `memory_stats`, summaries list/get/jobs, notes
    list, image jobs, and cochange tools.
  - Tests (two tenants seeded): named scope returns only its tenant; foreign id
    not-found; `search_around` under a named scope never returns other-tenant
    memories; global scope sees all.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 4. Scope the write tools (`server.py`, `tools.py`)
  - `memory_add` (free-standing) stamps `_scope_tenant`.
  - Reference-creating writes (`memory_note`, link creation — name the tool,
    `session_feedback`, `summary_put`) INHERIT the referenced record's tenant in
    BOTH scopes (never stamp `"global"` on a reference to a tenant-T record);
    references spanning >1 tenant raise `CrossTenantLinkError`; a global-scope
    `summary_put` on a concept in multiple tenants raises a clear ambiguity error.
  - Modify-in-place writes (`memory_archive`, `image_caption_put`) map to the
    `multi-tenancy` id-only writes with `tenant_id=_effective_tenant()`; named
    scope → foreign target not-found; tenant never re-stamped.
  - `memory_dream`: named scope → return the "requires
    cross-tenant-copy-and-dreaming" refusal (MCP tool error); global → unchanged.
  - Errors surface as MCP tool errors; `memory_get` foreign id → `null`.
  - Tests: named create under T; reference write inherits T under both scopes;
    cross-tenant reference → `CrossTenantLinkError`; cross-tenant archive →
    not-found; named `memory_dream` → refusal error; global `memory_dream`
    unchanged.
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 5. No per-call override (assertion + tests)
  - Confirm no read/write tool exposes a tenant parameter in its MCP schema
    (except `tenant_create`'s create-id). The scope comes solely from
    `_scope_tenant`.
  - Tests: inspect the registered tool schemas and assert no scope-changing
    tenant parameter; a global-scope process stays unrestricted and a named-scope
    process stays confined regardless of tool input.
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 6. `tenant_create` tool (`server.py` / `tools.py`)
  - Register `tenant_create(tenant_id, name="")` → `store.create_tenant(...)` →
    JSON-safe dict. Idempotent on existing id. No privilege gate. Does not change
    `_scope_tenant`.
  - Tests: new id creates; existing id idempotent; invalid id errors; caller
    scope unchanged afterwards; callable from both global and named scopes.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 7. `tenant_list` tool (`server.py` / `tools.py`)
  - Register `tenant_list()` → `[t.model_dump(mode="json") for t in
    store.list_tenants()]`. Returns all tenants in any scope; directory metadata
    only.
  - Tests: returns all seeded tenants under both global and named scopes; no
    memory data leaks in the payload.
  - _Requirements: 6.1, 6.2, 6.3_

- [ ] 8. Discoverability: capabilities + instructions (`server.py`)
  - Extend `mintmory://capabilities` to report `tenant_scope` (id) and
    `tenant_scoped` (bool), without exposing other tenants' data.
  - Add a sentence to the server `instructions` describing the boundary
    (global = all tenants, named = confined).
  - Tests: capabilities includes the scope fields for global and named configs.
  - _Requirements: 7.1, 7.2, 7.3_

- [ ] 9. Integration + full gate (`tests/integration/`)
  - Bring up named-scope and global-scope MCP configurations against a shared DB
    seeded with two tenants; assert end-to-end isolation (named) and unrestricted
    access (global) across add→search→feedback and the two tenant tools.
  - Run the full gate: `uv run pytest` (coverage ≥ 80%), `uv run mypy
    packages/`, `uv run ruff check packages/` — all exit 0.
  - _Requirements: 7.4, 7.5_
