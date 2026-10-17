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
  - Add a `MINTMORY_MCP_` settings group exposing `tenant` (env
    `MINTMORY_MCP_TENANT`, default `global`), or extend the MCP entrypoint to
    read it.
  - Add a `--tenant` option to the `mintmory-mcp` command; CLI wins over env.
  - Add module-level `_scope_tenant` and `_effective_tenant()` (global→None,
    named→T) in `server.py`.
  - Tests: default → `global`; env sets scope; `--tenant` overrides env;
    `_effective_tenant()` mapping.
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 4.1_

- [ ] 2. Fail-fast startup validation (`server.py`)
  - In the server bootstrap (before serving, both stdio and SSE/HTTP): resolve
    scope, init store, then validate — if scope != `global` and
    `store.get_tenant(scope) is None`, raise a clear error and exit non-zero.
  - No implicit tenant creation; no silent fallback to global.
  - Tests: unknown named tenant → startup error; existing tenant → starts;
    global → always starts.
  - _Requirements: 1.4, 1.6_

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
  - `memory_add` persists under the literal `_scope_tenant` (named → T, global →
    `"global"`). Constrain `memory_archive`, link creation, `session_feedback`,
    `summary_put`, `image_caption_put`, `memory_note`, and `memory_dream` to the
    scope; foreign-tenant targets are not-found / no-op.
  - Tests: named-scope write lands under T; global under `global`; cross-tenant
    archive attempt is not-found; `memory_dream` under T is tenant-local and
    idempotent.
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 5. No per-call override (guard + tests)
  - Ensure no tool exposes a caller-settable tenant that changes the boundary;
    if any tenant-like argument exists, the configured scope takes precedence.
  - Tests: a global-scoped agent stays unrestricted and a named-scoped agent
    stays confined regardless of tool arguments.
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
