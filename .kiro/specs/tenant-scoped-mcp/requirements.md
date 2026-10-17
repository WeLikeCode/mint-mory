# Requirements — Tenant-Scoped MCP

> **Depends on:** the `multi-tenancy` spec (`.kiro/specs/multi-tenancy/`). That
> spec must be implemented first — it provides the `Tenant` model, the `tenants`
> table, the `tenant_id` columns, the `create_tenant` / `get_tenant` /
> `list_tenants` storage methods, and the storage-level tenant scoping (the
> tenant predicate in candidate SQL + `search_around`). This spec builds on
> those and does not re-specify them.

## Introduction

This feature binds an MCP server instance to a **single tenant for the lifetime
of its connection** and exposes two tenant-management tools (`tenant_create`,
`tenant_list`) over MCP. The tenant scope is a connection/process-level boundary,
resolved once from the MCP server's launch configuration — **not** a per-call
argument. Once configured, that MCP agent only ever operates within its scope.

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
- Per-call tenant overrides or per-session (multi-tenant-per-process) scoping.
- Tenant deletion, quotas, or billing.
- Scope enforcement on the REST API or CLI (the CLI's per-call `--tenant` from
  the `multi-tenancy` spec is unaffected).

---

## Glossary

- **Scope** — the single tenant an MCP server instance is bound to for its whole
  lifetime, resolved from launch configuration.
- **Global scope** — scope == `global`; unrestricted, sees all tenants' data.
- **Named-tenant scope** — scope == some tenant id `T`; hard-isolated to `T`.
- **Connection-level** — resolved once per server process/connection at startup,
  not per tool call.

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
4. WHEN a named-tenant scope `T` is configured AND `T` does not exist in the
   `tenants` table THEN the server SHALL fail fast at startup with a clear error
   (it SHALL NOT implicitly create the tenant and SHALL NOT silently fall back to
   global).
5. The resolved scope SHALL be fixed for the lifetime of the server
   process/connection and SHALL NOT change between tool calls.
6. Scope resolution SHALL apply identically to the stdio and HTTP/SSE transports.

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
   data and SHALL persist new records under `tenant_id = T`.
2. WHEN the scope is `global` THEN writes SHALL persist under `tenant_id =
   "global"` (today's behaviour).
3. WHEN a named-tenant agent attempts to modify or archive a record belonging to
   a different tenant THEN the operation SHALL fail / be a no-op as not found,
   never a cross-tenant mutation.
4. `memory_dream` consolidation under scope `T` SHALL only link/summarise/resolve
   within `T` and SHALL remain idempotent.

### Requirement 4 — No per-call scope override

**User story:** As an operator, I want the configured scope to be the only scope,
so an agent cannot escape its tenant by passing a different tenant in a call.

#### Acceptance Criteria
1. The MCP tools SHALL NOT expose a per-call parameter that changes the tenant
   boundary.
2. WHEN a tool invocation includes any tenant-like argument that conflicts with
   the configured scope THEN the configured scope SHALL take precedence (the
   argument SHALL NOT widen or redirect access).
3. A global-scoped agent SHALL remain unrestricted; a named-tenant agent SHALL
   remain confined — regardless of tool arguments.

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
