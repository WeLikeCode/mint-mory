# Requirements — Tenant-Scoped MCP

> **Depends on:** the `multi-tenancy` spec (`.kiro/specs/multi-tenancy/`). That
> spec must be implemented first — it provides the `Tenant` model, the `tenants`
> table, the `tenant_id` columns, the `create_tenant` / `get_tenant` /
> `list_tenants` storage methods, the error types (`TenantError` and subtypes),
> and — critically — the committed read signatures this spec relies on:
> `get_memory(id, tenant_id=None)` (foreign id → `None`), `search` via
> `SearchRequest.tenant_id`, and `tenant_id: str | None = None` on
> `search_around`, `get_stats`, `get_links`, `list_notes`,
> `get_annotating_notes`, `get_annotating_descriptions`,
> `list_image_file_records`, `find_image_file_record`, `anchor_candidates`, and
> the dreaming helpers. This spec builds on those and does not re-specify them.
>
> **Ownership (resolves the duplicate-scope conflict):** the `multi-tenancy` spec
> deliberately leaves the entire MCP tenant surface to THIS spec. `multi-tenancy`
> does not add any per-call `tenant_id` MCP argument and registers no MCP tenant
> tools. THIS spec is the sole owner of the MCP connection scope, the
> `tenant_create` / `tenant_list` MCP tools, and the scope wiring of every MCP
> tool. It does NOT own the `DreamingEngine` tenant scope or a "dream all
> tenants" loop — those belong to `cross-tenant-copy-and-dreaming`; here
> `memory_dream` simply passes the connection scope to whatever dreaming entry
> point exists at the time (see Req 3.4).

## Introduction

This feature binds an MCP server **process** to a **single tenant for the
lifetime of that process** and exposes two tenant-management tools
(`tenant_create`, `tenant_list`) over MCP. The tenant scope is resolved once from
the MCP server's launch configuration — **not** a per-call argument. Once
configured, that MCP server process only ever operates within its scope.

**Process vs connection (resolves the ambiguity finding):** the scope is
**per server process**. One `mintmory-mcp` process serves one tenant. For the
HTTP/SSE transport this means a given server process is single-tenant for all
connections it serves; serving multiple tenants requires running multiple
processes with different `--tenant` values. This spec does NOT implement
per-connection scoping within one process. The glossary and Req 1.5 use "process"
accordingly.

Scope semantics (decided):
- **Global scope** (the default, tenant id `global`): the agent operates
  **unrestricted** — reads and searches span all tenants' data. This is today's
  behaviour and the backwards-compatible default.
- **Named-tenant scope** (tenant id `T`): the agent is hard-isolated to `T`.
  Every read, search, graph traversal, write, and stat is confined to `T`; it
  **cannot** access any other tenant's data.
- The scope **cannot be overridden per call**. There is no per-tool tenant
  argument that changes the boundary; the connection's configured scope governs
  every operation.

There is **no admin/privilege model**. `tenant_create` and `tenant_list` are
plain tools available to any MCP agent regardless of scope. `tenant_list` returns
all tenants in both scopes (it is a directory of tenant ids/names and exposes no
tenant's memory data).

### Relationship to the `multi-tenancy` spec

This feature **depends on** the `multi-tenancy` spec, which provides the data
model (`Tenant` model, `tenant_id` on every table-backed model), the `tenants`
table, and the storage-level tenant scoping mechanics (the tenant predicate in
candidate SQL + graph traversal). This spec does **not** re-specify those; it
adds the MCP connection-scope enforcement and the two MCP tools on top of them.

### Transports

- MCP over **stdio** (`mintmory-mcp`).
- MCP over **HTTP/SSE** (`mintmory-mcp --transport sse` / HTTP MCP).

Both are the MCP transport of the `mintmory-mcp` package. The plain REST API
(`mintmory-api`) is out of scope for this spec.

### Out of scope

- Authentication, authorization, roles, or admin privileges.
- Per-call tenant overrides or per-connection (multi-tenant-per-process) scoping.
- The `DreamingEngine` tenant scope and the global "dream all tenants" loop
  (owned by `cross-tenant-copy-and-dreaming`); this spec only passes the scope to
  `memory_dream`.
- Tenant deletion, quotas, or billing.
- Scope enforcement on the REST API or CLI (the CLI's per-call `--tenant` from
  the `multi-tenancy` spec is unaffected).

---

## Glossary

- **Scope** — the single tenant an MCP server **process** is bound to for its
  whole lifetime, resolved from launch configuration.
- **Global scope** — scope == `global`. Per the `multi-tenancy` read/write rule:
  reads pass `tenant_id = None` (unrestricted, all tenants) and writes stamp
  `"global"`. This is today's behaviour.
- **Named-tenant scope** — scope == some tenant id `T`; hard-isolated to `T`
  (reads pass `tenant_id = "T"`, writes stamp `"T"`).
- **`_effective_tenant()`** — the process-held translation: returns `None` when
  the scope is `global` (so reads are unrestricted) and `"T"` for a named scope.
- **`_scope_tenant`** — the literal scope id (`"global"` or `"T"`) used as the
  write `tenant_id`.

---

## Requirements

### Requirement 1 — Connection-level scope configuration

**User story:** As an operator deploying an MCP agent, I want to configure which
tenant that agent is bound to when I launch the server, so the agent's access is
fixed for its whole session.

#### Acceptance Criteria
1. WHEN the MCP server starts THEN it SHALL resolve a tenant scope from its launch
   configuration (a `--tenant` CLI argument on the `mintmory-mcp` command and/or a
   `MINTMORY_MCP_TENANT` env var), following the existing pydantic-settings /
   `MINTMORY_<GROUP>_` convention.
2. WHEN no scope is configured THEN the server SHALL default to the `global`
   scope (backwards compatible — identical to today).
3. WHEN both the CLI argument and the env var are present THEN the resolution
   order SHALL be deterministic and documented (CLI argument wins).
4. WHEN a named-tenant scope `T` is configured AND `get_tenant(T)` returns
   `None` THEN the server SHALL fail fast at startup with a clear error (map the
   `multi-tenancy` `TenantNotFoundError`), exiting non-zero. It SHALL NOT
   implicitly create the tenant and SHALL NOT silently fall back to global.
5. WHEN a named-tenant scope `T` is configured AND `T` exists but
   `is_active = false` THEN the server SHALL start (an inactive tenant is
   read-only per `multi-tenancy` Req 4.3): reads under `T` work, and a write tool
   surfaces `TenantInactiveError`. The server SHALL NOT fail startup for an
   inactive scope.
6. WHEN the `--tenant` / `MINTMORY_MCP_TENANT` value is empty or fails the
   `multi-tenancy` id charset THEN the server SHALL fail fast with
   `InvalidTenantIdError` (an empty value means "not set" → `global`, not an
   error; a non-empty invalid value is an error).
7. The resolved scope SHALL be fixed for the lifetime of the server process and
   SHALL NOT change between tool calls.
8. Scope resolution SHALL apply identically to the stdio and HTTP/SSE transports
   (both run through the same bootstrap).

### Requirement 2 — Scope is a hard read/search boundary

**User story:** As an operator, I want a named-tenant agent to be unable to see
any other tenant's data, so tenants are isolated from each other.

#### Acceptance Criteria
1. WHEN the scope is a named tenant `T` THEN every read/search tool
   (`memory_search`, `memory_get`, `search_around`, `memory_stats`, summaries,
   notes, images, cochange) SHALL return only data belonging to `T`.
2. WHEN the scope is a named tenant `T` THEN `search_around` graph traversal
   SHALL NOT reach or return memories from any other tenant.
3. WHEN the scope is `global` THEN read/search tools SHALL operate unrestricted
   across all tenants' data (today's behaviour).
4. WHEN a named-tenant agent requests a memory by id that belongs to a different
   tenant THEN the server SHALL behave as if it does not exist (not found) —
   it SHALL NOT return another tenant's record.
5. The boundary SHALL be enforced via the `multi-tenancy` storage scoping (tenant
   predicate in candidate SQL + traversal), not only by post-filtering.

### Requirement 3 — Scope is a hard write boundary

**User story:** As an operator, I want a named-tenant agent to write only into
its own tenant, so it cannot pollute or cross into another tenant.

#### Acceptance Criteria
1. WHEN the scope is a named tenant `T` THEN every write tool (`memory_add`,
   `memory_archive`, link creation, `session_feedback`, `summary_put`,
   `image_caption_put`, `memory_note`, `memory_dream`) SHALL act only on `T`'s
   data and SHALL persist new records under `tenant_id = T` (using `_scope_tenant`
   as the write id).
2. WHEN the scope is `global` the write rule SHALL preserve the `multi-tenancy`
   same-tenant invariant (a reference never crosses tenants):
   - A write that CREATES a free-standing record (`memory_add`) stamps
     `"global"`.
   - A write that CREATES a record REFERENCING an existing record — a note
     annotating memory M (`memory_note`), a link between M1 and M2 (link
     creation), a session recording results for memories (`session_feedback`) —
     SHALL inherit the tenant of the referenced record(s): the new note/link/
     session is stamped with the referenced memory's `tenant_id`, so no
     cross-tenant reference is created. If the references span more than one
     tenant (e.g. a link between two tenants' memories), the write SHALL raise
     `CrossTenantLinkError`.
   - `summary_put(concept, text)` does NOT reference a specific memory, so there
     is nothing to inherit: it stamps `_scope_tenant` directly (named → `T`,
     global → `"global"`), keyed on `(tenant_id, concept)`. A global-scope agent
     writes `global`-tenant summaries; per-tenant summaries are written by that
     tenant's own scoped agent or regenerated by per-tenant dreaming (the copy
     spec). No concept→memory resolution and no disambiguation error.
   - A write that MODIFIES an existing record (`memory_archive`,
     `image_caption_put` on an existing image record) SHALL act on that record
     in place and SHALL NOT change its `tenant_id`.
   This makes a global-scope agent "unrestricted" for reads and for choosing
   which record to act on, while still never producing a cross-tenant reference.
3. WHEN a named-tenant agent attempts to modify or archive a record belonging to
   a different tenant THEN the operation SHALL behave as not-found (no cross-tenant
   mutation), because the underlying lookup is confined to `T` via the committed
   scoped read signatures.
4. Tenant-safe `memory_dream` requires the per-tenant `DreamingEngine`, which is
   owned by `cross-tenant-copy-and-dreaming`. To avoid a half-built dreaming path,
   THIS spec does the minimum and defers the rest:
   - For a **named** scope `T`, this spec SHALL make `memory_dream` refuse to run
     an un-tenant-safe dream: it returns a clear "tenant-scoped dreaming requires
     the cross-tenant-copy-and-dreaming capability" error rather than silently
     dreaming globally (which could create cross-tenant links). Once
     `cross-tenant-copy-and-dreaming` lands, it replaces this stub with the real
     `DreamingEngine(tenant_id=T)` wiring.
   - For the **global** scope, `memory_dream` behaves exactly as today
     (unchanged), because `cross-tenant-copy-and-dreaming` owns the global
     multi-tenant loop.
   This removes the ordering hazard: a named-scope agent never triggers a global
   cross-tenant dream. The dependency on `cross-tenant-copy-and-dreaming` for
   real named-scope dreaming is explicit.

### Requirement 4 — No per-call scope override

**User story:** As an operator, I want the configured scope to be the only scope,
so an agent cannot escape its tenant by passing a different tenant in a call.

#### Acceptance Criteria
1. The MCP tools SHALL NOT expose any per-call parameter that selects or changes
   the tenant boundary. (Note: `tenant_create(tenant_id=...)` takes a tenant id,
   but that id names the tenant being CREATED in the directory — it does not
   change the calling process's scope; see Req 5.4.)
2. BECAUSE no tool exposes a scope-changing argument, there is no "conflicting
   argument" path to resolve. The scope comes solely from `_scope_tenant`, so a
   tool cannot be made to read or write another tenant by any argument it
   accepts. A test SHALL assert that the read/write tools take no tenant
   parameter in their MCP schemas (other than `tenant_create`'s create-id).
3. A global-scope process SHALL remain unrestricted; a named-tenant process SHALL
   remain confined — determined only by `_scope_tenant`, never by tool input.

### Requirement 4b — Complete tool inventory (no silent unscoped tool)

**User story:** As a maintainer, I want every existing MCP tool accounted for, so
no tool silently leaks across tenants under a named scope.

#### Acceptance Criteria
1. The design SHALL enumerate EVERY registered MCP tool (memory_add, memory_get,
   memory_archive, memory_search, memory_stats, memory_dream, session_feedback,
   summary_list, summary_get, summary_jobs, summary_put, image_jobs,
   image_caption_put, vision_run, memory_note, notes_list, docs_changed_with,
   docs_timeline, and any others present) with the core/storage call it makes and
   the `tenant_id` it passes.
2. For each read/list tool, the underlying storage method SHALL be one that
   `multi-tenancy` Req 5.1 made tenant-aware; if any such method is missing from
   that list, this spec's tasks SHALL treat extending `multi-tenancy`'s scoped
   reads as a prerequisite (and the `multi-tenancy` Req 5.1 list is written to
   include summary list/get/jobs, image jobs, cochange, and session reads).
3. A test SHALL fail if a new MCP tool is added without a tenant-scoping decision
   (e.g. an inventory test comparing registered tools against a known-scoped set).

### Requirement 5 — `tenant_create` tool

**User story:** As an MCP agent, I want a tool to create a new tenant, so I can
provision tenants without a separate admin interface.

#### Acceptance Criteria
1. WHEN `tenant_create` is called with a new tenant id THEN the server SHALL
   create the tenant (via the `multi-tenancy` storage `create_tenant`) and return
   the created `Tenant` as a JSON-safe dict.
2. WHEN `tenant_create` is called with an existing id THEN the behaviour SHALL be
   idempotent and deterministic (return the existing tenant, consistent with the
   `multi-tenancy` storage contract).
3. `tenant_create` SHALL be available to any MCP agent regardless of its scope
   (no admin/privilege gate).
4. Creating a tenant SHALL NOT change the calling agent's own scope (it still
   only sees its configured scope afterwards).
5. The tenant id SHALL be validated per the `multi-tenancy` `Tenant` id rules;
   an invalid id SHALL return a clear error.

### Requirement 6 — `tenant_list` tool

**User story:** As an MCP agent, I want a tool to list tenants, so I can see what
tenants exist.

#### Acceptance Criteria
1. WHEN `tenant_list` is called THEN the server SHALL return all tenants
   (id, name, is_active, timestamps) as a JSON-safe list, regardless of the
   caller's scope.
2. `tenant_list` SHALL expose only tenant directory metadata and SHALL NOT expose
   any tenant's memory records.
3. `tenant_list` SHALL be available to any MCP agent regardless of its scope.

### Requirement 7 — Discoverability and parity

**User story:** As a maintainer, I want the new tools and scope to be discoverable
and consistent with the existing MCP surface.

#### Acceptance Criteria
1. `tenant_create` and `tenant_list` SHALL be registered as MCP tools returning
   JSON-safe dicts via `model_dump(mode="json")`, matching existing tool style.
2. The `mintmory://capabilities` resource SHALL report the server's configured
   tenant scope (the id and whether it is global), without exposing other
   tenants' data.
3. The server `instructions` SHALL mention the scope behaviour so agents
   understand their boundary.
4. Tests SHALL cover: scope resolution (default global, env/arg, fail-fast on
   unknown tenant), the read/search/write boundary under a named scope, the
   unrestricted global scope, no-per-call-override, and both new tools.
5. The full gate SHALL pass: `uv run pytest` (coverage ≥ 80%),
   `uv run mypy packages/`, `uv run ruff check packages/` all exit 0.
