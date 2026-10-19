# Requirements — Multi-Tenancy 6/10: tenant-scoped MCP server

> **Depends on:** `tenant-scoped-core` (`run_dream`, `build_dreaming_engine(…,
> tenant_id=…)`, the `tenant_id` parameters of `create_note`, `notes_list`,
> `image_jobs`, `image_caption_put`, `caption_pending_images`,
> `session.apply_feedback`, `changed_with`, `documents_timeline`),
> `multi-tenancy-reads` (`get_memory(id, tenant_id)`, `search(…, tenant_id=…)`,
> `get_stats(tenant_id)`, `list_summaries(tenant_id)`), `multi-tenancy`
> (`get_tenant`, `create_tenant`, `list_tenants`, `get_summary(concept,
> tenant_id)`, `validate_tenant_id`, `TENANT_GLOBAL`, the `TenantError` types)
> and `multi-tenancy-writes` (`archive_memory(id, tenant_id)` raising `KeyError`
> for a foreign id; the write guard). Changes `packages/core/.../config.py`
> (`McpSettings`), `packages/mcp/src/mintmory/mcp/server.py` and MCP tests.

## Introduction

A `mintmory-mcp` process is bound to one tenant scope for its whole lifetime,
resolved once at startup from `--tenant` or `MINTMORY_MCP_TENANT`. No tool takes
a scope argument. The global scope (default) reads every tenant and creates in
`global` (today's behaviour); a named scope `T` reads and writes only `T`. Two
tools manage the tenant directory. There is no auth: a process's scope is an
isolation boundary for the agent using it, not a security boundary. One process
serves one tenant on every transport (stdio and SSE); serving several tenants
means running several processes.

Scope mapping: `_scope_tenant` is the literal scope (`"global"` or `"T"`), used
as the write tenant; `_effective_tenant()` returns `None` for the global scope
(unrestricted reads) and `"T"` otherwise.

## Requirements

### Requirement 1 — Scope resolution and fail-fast startup

#### Acceptance Criteria

1. `config.py` SHALL add `class McpSettings(BaseSettings)` with
   `model_config = SettingsConfigDict(env_prefix="MINTMORY_MCP_", extra="ignore")`
   and `tenant: str = ""`.
2. `server.main()` (argparse) SHALL add `--tenant` (default `None`). The scope is
   the `--tenant` value when non-empty, else `McpSettings().tenant` when
   non-empty, else `"global"`.
3. `server._bootstrap_scope(scope: str) -> None` SHALL call
   `validate_tenant_id(scope)` (`InvalidTenantIdError`), call `_get_store()`,
   and for a non-global scope raise `TenantNotFoundError(scope)` when
   `get_tenant(scope)` is `None`; an inactive tenant prints `mintmory-mcp:
   warning: tenant 'T' is inactive; this server is read-only` to stderr and
   continues. Only after these checks it sets the module global `_scope_tenant`.
   It never creates a tenant and never falls back to `global`.
4. `main()` SHALL call `_bootstrap_scope` before `mcp.run(...)` for both
   `--transport stdio` and `--transport sse`; on a `TenantError` it prints
   `mintmory-mcp: error: <message>` to stderr and raises `SystemExit(1)` without
   calling `mcp.run`.
5. `_scope_tenant: str = TENANT_GLOBAL` and `_effective_tenant() -> str | None`
   SHALL be module-level; no tool changes `_scope_tenant`.
6. Tests drive `main()` with a monkeypatched `sys.argv`, `MINTMORY_DB` in
   `tmp_path` and `mcp.run` replaced by a recorder: no option and no env →
   scope `global`, `run` called; `MINTMORY_MCP_TENANT=acme` (existing) → `acme`;
   `--tenant acme` with `MINTMORY_MCP_TENANT=other` → `acme`; `--tenant nope` →
   `SystemExit(1)`, stderr `tenant 'nope' not found`, `run` not called; `--tenant
   Bad` → `SystemExit(1)` with `invalid tenant id`; an inactive `acme` → starts
   and warns; `--transport sse --tenant acme` → bootstrap ran, then `run(transport=
   "sse", port=8081)`.

### Requirement 2 — Every tool's tenant (complete inventory)

#### Acceptance Criteria

1. Each registered tool SHALL make exactly this call (`E = _effective_tenant()`,
   `S = _scope_tenant`):

   | Tool | Kind | Call |
   |---|---|---|
   | `memory_add` | create | `add_memory(record=MemoryRecord(…, tenant_id=S))` |
   | `memory_get` | read | `get_memory(memory_id, tenant_id=E)`; a foreign id returns `null` |
   | `memory_search` | read | `search(request, tenant_id=E)` (its `search_around_*` traversal is confined too) |
   | `memory_stats` | read | `get_stats(tenant_id=E)` |
   | `memory_archive` | modify | `archive_memory(memory_id, tenant_id=E)`; `KeyError` → `{"error": "not_found", "message": …}` |
   | `session_feedback` | modify | `session.apply_feedback(…, tenant_id=E)`; a `ValueError` (missing or foreign session, foreign id) → today's `{"error": "conflict", "message": …}`; a `KeyError` (missing id, global scope) and a `TenantError` propagate as a tool error, as today |
   | `summary_list` | read | `list_summaries(tenant_id=E)` |
   | `summary_get` | read | `get_summary(concept, S)` |
   | `summary_jobs`, `summary_put` | create | `build_dreaming_engine(…, tenant_id=S)` |
   | `memory_note` | create | `create_note(…, tenant_id=S)` |
   | `notes_list` | read | `notes_list(…, tenant_id=E)` |
   | `docs_changed_with`, `docs_timeline` | read | `tenant_id=E` |
   | `image_jobs`, `image_caption_put`, `vision_run` | create | `tenant_id=S` (`image_caption_put` keeps its `not_found` error dict) |
   | `memory_dream` | dream | `run_dream(store, intensity=…, tenant_id=E, engine_factory=lambda t: build_dreaming_engine(…, tenant_id=t))` |
   | `tenant_create`, `tenant_list` | directory | R5 |

2. `server.py` SHALL define `TOOL_TENANT_SCOPE: Final[dict[str, str]]` mapping
   every tool name to its kind in the table, the kinds being exactly `"read"`,
   `"create"`, `"modify"`, `"dream"` and `"directory"` (`cross-tenant-copy`
   later adds `"copy"`). A test SHALL assert that the set of
   tool names from `Client.list_tools()` equals `set(TOOL_TENANT_SCOPE)`, so a new
   tool without a scoping decision fails the suite; `test_all_tools_registered`
   gains `tenant_create` and `tenant_list`.
3. A `TenantError` raised in a tool (for example `TenantInactiveError`) SHALL
   surface as a tool error: the fastmcp client raises
   `fastmcp.exceptions.ToolError` whose message contains the exception's message.

### Requirement 3 — Named scope `T` is a hard boundary

#### Acceptance Criteria

1. Every read and every write of R2 SHALL be confined to `T`: results contain
   only `T` rows, creates are stamped `T`, a foreign id behaves as not found.
   The only exception is the tenant directory: `tenant_list` shows every tenant
   and `tenant_create` may create another tenant (R5); neither exposes or
   changes any tenant's memory data.
2. Examples with `global` holding g1 "Alice uses Postgres" and g2 "Carol uses
   Postgres", and `acme` holding a1 "Alice uses SQLite" and a2 "Bob uses SQLite"
   (entities from `extract_entities`; default link settings), scope `acme`:
   `memory_search("Alice")` returns only a1 and its session is an `acme` session;
   `memory_get(g1)` → `null`; `memory_archive(g1)` → `{"error": "not_found", …}`
   and g1 stays active; `memory_add(…)` stores `tenant_id == "acme"`;
   `memory_stats` counts 2 before that add; `memory_dream` returns `new_links ==
   1` and creates exactly the link a1–a2 with `tenant_id == "acme"` (no link
   touches g1 or g2, although a1 and g1 share `alice`);
   `session_feedback(session_id, useful_ids=[g1])` → the `conflict` error dict
   and no score changes.

### Requirement 4 — Global scope

#### Acceptance Criteria

1. Reads SHALL span every tenant; creates SHALL be stamped `global` and any
   record they reference SHALL be a `global` record (note anchors, summary jobs,
   image jobs and descriptions); modifications by id act on the stored row of
   any tenant and never change its tenant.
2. Examples, scope `global`, same data: `memory_search("Alice")` returns g1 and
   a1; `memory_get(a1)` returns it; `memory_archive(a1)` archives it and its
   `tenant_id` stays `acme`; `memory_note("check index", about="SQLite")` creates
   a `global` note that never anchors to a1; `summary_put("alice", "…")`
   (`apply_summary` accepts any concept, with no `min_memories` threshold, and
   recomputes `memory_count` — here 1, from g1) stores a
   `global` summary and `summary_get("alice")` returns it; `summary_list` returns
   every tenant's summaries, each with its `tenant_id`; on fresh data,
   `memory_dream` dreams each tenant separately and returns a `DreamReport` with
   `new_links == 2` (g1–g2 in `global`, a1–a2 in `acme`) and no link between g1
   and a1.

### Requirement 5 — `tenant_create` and `tenant_list` tools

#### Acceptance Criteria

1. `tenant_create(tenant_id: str, name: str = "") -> dict[str, Any]` SHALL return
   `store.create_tenant(tenant_id, name).model_dump(mode="json")`; an existing id
   returns the existing tenant unchanged; an invalid id raises
   `InvalidTenantIdError` (a `ToolError` on the client); it is available in every
   scope and does not change `_scope_tenant`.
2. `tenant_list() -> list[dict[str, Any]]` SHALL return `[t.model_dump(mode=
   "json") for t in store.list_tenants()]` (keys `id`, `name`, `is_active`,
   `created_at`, `updated_at`; no memory data) in every scope.
3. Tests: create in the global and in a named scope; idempotent second call;
   invalid id; `_scope_tenant` unchanged after a create; list returns every
   tenant in both scopes.

### Requirement 6 — No per-call scope override

#### Acceptance Criteria

1. No tool SHALL accept a parameter that selects a tenant, except
   `tenant_create`'s `tenant_id` (the id of the tenant being created). Test: for
   every tool of `list_tools()`, the property names of `inputSchema` containing
   `tenant` are empty, except `{"tenant_id"}` for `tenant_create`. (The later
   `cross-tenant-copy` unit adds `tenant_copy`, whose `source_tenant` /
   `dest_tenant` name copy endpoints, the kind `"copy"`, and the matching
   exceptions in this test and in `test_all_tools_registered`.)

### Requirement 7 — Discoverability

#### Acceptance Criteria

1. The `mintmory://capabilities` resource SHALL add `"tenant_scope":
   _scope_tenant` and `"tenant_scoped": _scope_tenant != "global"` (also in its
   `{"error": "settings unavailable"}` fallback): global → `{…, "tenant_scope":
   "global", "tenant_scoped": false}`, scope `acme` → `"acme"`, `true`.
2. The server `instructions` SHALL end with: `TENANCY: this server is bound to
   one tenant scope for its lifetime (see mintmory://capabilities); the global
   scope reads every tenant and writes the global tenant, a named scope reads and
   writes only its tenant. tenant_create and tenant_list manage the tenant
   directory.`

### Requirement 8 — Failure cases

#### Acceptance Criteria

1. A named scope whose tenant is deactivated after startup SHALL keep serving
   reads, including the job lists `summary_jobs` and `image_jobs` (they only
   read); the tools that write — `memory_add`, `memory_archive`,
   `session_feedback`, `summary_put`, `memory_note`, `image_caption_put` (and
   `vision_run` when it has an image to caption) — raise `TenantInactiveError`
   (tool error); `memory_search` returns results with `session_id == ""` (no
   session is recorded), and `memory_dream` raises `TenantInactiveError`.
2. A global-scope modification of a row whose tenant is inactive SHALL raise
   `TenantInactiveError` (tool error) and change nothing for that row;
   `session_feedback` validates the session and every id first
   (`tenant-scoped-core` R5.5), so a call naming an inactive tenant's memory
   changes no score at all; only a deactivation racing the call can stop it
   part-way.
3. Two concurrent `tenant_create("acme")` calls SHALL both return the same
   tenant (one row). A tenant cannot disappear after startup (no delete API).

### Requirement 9 — Tests and gates

#### Acceptance Criteria

1. MCP tests use the in-memory fastmcp `Client` with the existing `mcp_client`
   fixture; a fixture sets the scope with `_bootstrap_scope("acme")` after
   creating `acme`, and every fixture resets `server._scope_tenant =
   TENANT_GLOBAL` and `server._store = None` on teardown.
2. An integration test `tests/integration/test_tenancy_mcp_integration.py` (unit
   tests live in `packages/mcp/tests/test_mcp_tenancy.py`; the names differ) SHALL run R3.2 and
   R4.2 against one SQLite file, switching the scope between them.
3. The `.l4/config.yaml` gates SHALL pass with coverage ≥ 80%. No test needs
   Postgres, Docker or a network service.
