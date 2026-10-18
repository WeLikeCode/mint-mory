# Design — Tenant-Scoped MCP

> **Depends on:** the `multi-tenancy` spec (`.kiro/specs/multi-tenancy/`). That
> spec must be implemented first — it provides the `Tenant` model, the `tenants`
> table, the `tenant_id` columns, the `create_tenant` / `get_tenant` /
> `list_tenants` storage methods, and the storage-level tenant scoping (the
> tenant predicate in candidate SQL + `search_around`). This design builds on
> those and introduces no schema changes of its own.

## Overview

This design binds a `mintmory-mcp` server instance to one tenant for the lifetime
of its process/connection and adds two MCP tools (`tenant_create`,
`tenant_list`). It sits on top of the `multi-tenancy` spec, which already
provides: the `Tenant` model + `tenants` table, `tenant_id` on every table-backed
model, storage methods `create_tenant` / `get_tenant` / `list_tenants`, and the
tenant predicate injected into candidate SQL and `search_around` traversal.

The core idea: resolve a **scope** once at startup, hold it in a single
server-level value, and pass it into every core call as the tenant argument. A
named scope produces the hard boundary; the `global` scope passes "unscoped"
(None) so reads/searches span all tenants — exactly today's behaviour.

### Grounding notes (verified against current code)

- `packages/mcp/src/mintmory/mcp/server.py` holds a module-level `_store:
  StorageBackend | None` with lazy `_get_store()` calling `build_storage()`
  (no settings arg, no embedder) then `initialise()`. All tools are thin wrappers
  over `mintmory.core` and return `model_dump(mode="json")`.
- The server supports stdio (default), SSE (`--transport sse --port 8081`), and
  HTTP MCP, per the module docstring.
- Config is pydantic-settings groups with `MINTMORY_<GROUP>_` prefixes
  (`config.py`); `load_settings()` builds a fresh `Settings` from env.
- There are MCP resources `mintmory://schema` and `mintmory://capabilities`;
  the latter already reports a safe config summary.

---

## Scope resolution (Requirement 1)

### Source and precedence (concrete mechanism)

Add a `McpSettings(BaseSettings)` group in `core/config.py` with
`model_config = SettingsConfigDict(env_prefix="MINTMORY_MCP_")` and a field
`tenant: str = ""` (empty = not set). The `mintmory-mcp` entrypoint in
`server.py` (the Typer/CLI callback that today starts the server and parses
`--transport`/`--port`) gains a `--tenant <id>` option. Resolution order,
highest first:
1. `--tenant <id>` CLI option.
2. `McpSettings().tenant` (env `MINTMORY_MCP_TENANT`).
3. `""` → treated as `global`.

The entrypoint computes the scope string, then calls a single bootstrap function
`_bootstrap_scope(scope: str) -> None` that sets the module global
`_scope_tenant` and runs fail-fast validation. Tests set the scope by calling
`_bootstrap_scope("...")` directly (no subprocess needed), which also documents
how `_scope_tenant` is set under test.

### Fail-fast validation (`_bootstrap_scope`)

After `_get_store()` is initialised:
- Empty/unset scope → `_scope_tenant = "global"`; always valid.
- Non-empty scope failing the `multi-tenancy` id charset → raise
  `InvalidTenantIdError`, exit non-zero (Req 1.6).
- `scope == "global"` → valid (seeded by `multi-tenancy`).
- Else `store.get_tenant(scope)`:
  - `None` → raise `TenantNotFoundError`, exit non-zero (Req 1.4). No implicit
    create, no silent fallback.
  - exists but `is_active == False` → **start anyway** (Req 1.5); the tenant is
    read-only, so writes later surface `TenantInactiveError`. Log a warning.
  - exists and active → proceed.

This runs for stdio and SSE/HTTP identically (one bootstrap, Req 1.8).

### Scope holder

Add a module-level scope alongside `_store`:

```python
_scope_tenant: str = TENANT_GLOBAL  # resolved once at startup

def _effective_tenant() -> str | None:
    """Tenant to pass to core. None = unscoped (global sees everything)."""
    return None if _scope_tenant == TENANT_GLOBAL else _scope_tenant
```

`_effective_tenant()` is the single translation point from "scope" to the
`multi-tenancy` tenant argument:
- `global` scope → `None` → core runs unscoped (all tenants) = today's behaviour.
- named scope `T` → `T` → core confines every query/write to `T`.

Rationale for mapping global→None: the `multi-tenancy` storage layer treats a
`None` tenant as "emit today's exact SQL, no predicate," which is precisely
"global sees everything." A named tenant injects the predicate. This reuses the
existing mechanism with zero new storage branches.

---

## Wiring the scope through tools

Every tool handler reads `_effective_tenant()` and passes it into the core
call using the `multi-tenancy` signatures. No tool takes a tenant parameter from
the caller (Requirement 4.1).

### Reads / searches (Requirement 2)
- `memory_search`: set `SearchRequest.tenant_id = _effective_tenant()` before
  calling `store.search(...)`.
- `search_around`: pass `tenant_id=_effective_tenant()`.
- `memory_get`: when scoped, call the scoped get so a foreign id returns
  not-found (Requirement 2.4); when global (`None`), today's by-id behaviour.
- `memory_stats`, summaries list/get/jobs, notes list, image jobs, cochange:
  pass `tenant_id=_effective_tenant()`; `None` = global.

### Writes (Requirement 3) — one rule, no cross-tenant references

- `memory_add` (free-standing create): `record.tenant_id = _scope_tenant` (named
  → `T`, global → `"global"`).
- Writes that CREATE a record REFERENCING an existing record — `memory_note`
  (annotates memory M), link creation (M1↔M2), `session_feedback` (records
  `query_results` for retrieved memories), `summary_put` (a per-concept summary):
  the new record INHERITS the referenced record's tenant, in BOTH scopes. This is
  the single rule that keeps the `multi-tenancy` same-tenant invariant:
  - Resolve the referenced memory/memories (named scope → scoped read confined to
    `T`, so a foreign target is not-found; global scope → unrestricted read).
  - Stamp the new note/link/session/summary with the referenced record's
    `tenant_id`. If the references span >1 tenant (a link across tenants), raise
    `CrossTenantLinkError` (from `multi-tenancy`).
  - Concretely: `memory_note` on a tenant-T memory creates a T note (even under
    global scope); `session_feedback` records a session+results under the
    retrieved memories' tenant.
  - `summary_put(concept, text)` stamps `_scope_tenant` directly (named → `T`,
    global → `"global"`), keyed on `(tenant_id, concept)` — a summary is not a
    reference to a specific memory, so there is nothing to inherit and no
    disambiguation. (Per-tenant summaries are regenerated by the copy spec's
    per-tenant dreaming; a global agent simply writes global summaries.)
- Writes that MODIFY an existing record — `memory_archive(id)`,
  `image_caption_put` on an existing image: act on that row in place; named scope
  resolves the target confined to `T` (foreign → not-found); the row's
  `tenant_id` is never changed. These map to the `multi-tenancy` id-only writes
  (`archive_memory(id, tenant_id=_effective_tenant())`).
- `memory_dream` — NOT wired to an engine here (see Req 3.4): named scope →
  return the "requires cross-tenant-copy-and-dreaming" refusal (an MCP error
  dict, below); global scope → unchanged (today's dream). The real wiring is
  installed by `cross-tenant-copy-and-dreaming`, which also updates the Req 4b
  inventory test.

### Error return convention (MCP)

A `TenantError` raised by core is caught at the tool boundary and returned as an
MCP tool error (fastmcp surfaces a raised exception as a tool error to the
client); the message is the exception's. So `TenantInactiveError`,
`CrossTenantLinkError`, the invalid-id error, and the `memory_dream` named-scope
refusal all surface as MCP tool errors (not silent null/empty). `memory_get` of a
foreign id returns `null` (not an error — it is simply not found under the
scope). Startup fail-fast raises (process exits non-zero); under test,
`_bootstrap_scope` raises the exception directly (not `SystemExit`), so tests
assert on the exception type.

### Enforcement point

Enforcement lives in the `multi-tenancy` storage layer (predicate in candidate
SQL + traversal), not in the MCP tool bodies (Requirement 2.5). The tool bodies
only supply the scope; they cannot be bypassed because the scope value is
server-held and tools never accept a competing tenant argument.

### The write/read asymmetry (explicit)

| Scope | Read tenant arg | Write tenant_id |
|---|---|---|
| `global` | `None` (unrestricted) | `"global"` |
| named `T` | `T` (confined) | `T` |

`_effective_tenant()` returns the read arg; `_scope_tenant` is the write id.
This is the one subtlety in the design and is covered by tests.

---

## New tools

### `tenant_create` (Requirement 5)

```python
@mcp.tool()
def tenant_create(tenant_id: str, name: str = "") -> dict[str, Any]:
    """Create a new tenant. Idempotent: returns the existing tenant if the id
    already exists. Available to any agent regardless of scope. Does NOT change
    this agent's own scope."""
    store = _get_store()
    t = store.create_tenant(tenant_id, name)   # STRINGS — multi-tenancy Req 1.3
    return t.model_dump(mode="json")
```

- `create_tenant` takes STRINGS (multi-tenancy Req 1.3), so an invalid id raises
  the plain `InvalidTenantIdError` (not a Pydantic-wrapped error), which the tool
  surfaces as an MCP error (Req 5.5). Do NOT build a `Tenant(...)` here.
- No privilege gate (Requirement 5.3). Creating a tenant does not re-point
  `_scope_tenant` (Requirement 5.4).

### `tenant_list` (Requirement 6)

```python
@mcp.tool()
def tenant_list() -> list[dict[str, Any]]:
    """List all tenants (directory metadata only — no memory data). Available to
    any agent regardless of scope."""
    store = _get_store()
    return [t.model_dump(mode="json") for t in store.list_tenants()]
```

Returns all tenants in every scope (Requirement 6.1); exposes only
id/name/is_active/timestamps (Requirement 6.2).

---

## Startup / bootstrap changes (`server.py`, `config.py`)

- Add `McpSettings(env_prefix="MINTMORY_MCP_")` with `tenant: str = ""` in
  `config.py`.
- Add `--tenant <id>` to the `mintmory-mcp` entrypoint (the existing Typer
  callback that handles `--transport`/`--port`); CLI wins over env.
- The entrypoint computes the scope and calls `_bootstrap_scope(scope)`, which
  sets `_scope_tenant`, calls `_get_store()`, and runs fail-fast validation
  (above). Both stdio and SSE/HTTP paths call `_bootstrap_scope` before serving.
- Keep the `_store` singleton as-is; `_scope_tenant` is an independent module
  global set only by `_bootstrap_scope`.

---

## Discoverability (Requirement 7)

- Register both tools in the standard style (JSON-safe dicts).
- Extend `mintmory://capabilities` to include:
  ```json
  { "tenant_scope": "global", "tenant_scoped": false }
  ```
  (id + whether it is global; no other tenants' data).
- Add a sentence to the server `instructions` describing the boundary:
  global = all tenants, named = confined to one.

---

## Testing strategy

Unit (MCP package, `:memory:` store, mock embedder; set scope via
`_bootstrap_scope("...")`):
- Scope resolution: unset → `global`; `MINTMORY_MCP_TENANT` → that tenant;
  `--tenant` overrides env; unknown named tenant → `TenantNotFoundError` at
  bootstrap; invalid id → `InvalidTenantIdError`; inactive tenant → starts, with
  a later write raising `TenantInactiveError`.
- `_effective_tenant()` mapping: global→None, named→T.
- Read boundary: with two tenants seeded, a named-scope server's `memory_search`
  / `memory_get` / `search_around` return only its tenant; a foreign id is
  not-found; a global-scope server sees both.
- Write boundary: named-scope `memory_add` persists under `T`; global under
  `global`; a named-scope attempt to archive a foreign record is not-found; a
  global-scope archive of a named-tenant record succeeds and does NOT re-stamp
  that record's tenant.
- No override: assert the read/write tool MCP schemas expose no tenant parameter
  (except `tenant_create`'s create-id).
- `tenant_create`: new id creates; existing id idempotent; invalid id →
  `InvalidTenantIdError`; caller `_scope_tenant` unchanged afterwards.
- `tenant_list`: returns all tenants in both scopes.
- `capabilities` reports `tenant_scope` / `tenant_scoped`.

Integration (`tests/integration/`): bring up a named-scope and a global-scope
configuration against a shared DB with two tenants; assert isolation and the
unrestricted global case end-to-end.

Gates: `uv run pytest` (≥ 80% coverage), `uv run mypy packages/`,
`uv run ruff check packages/` all exit 0.

---

## Dependencies and sequencing

- **Hard dependency on `multi-tenancy`**: the `Tenant` model, `tenants` table,
  `create_tenant`/`get_tenant`/`list_tenants`, the `TenantError` types, and the
  committed scoped read signatures (`get_memory(id, tenant_id=None)` etc.) must
  exist first. This spec's tasks assume those are complete.
- No DB schema changes here (no new tables/columns). The only `core` change is
  the `McpSettings` config group; the schema gate is unaffected. OpenAPI is
  unaffected except for optional MCP-tool documentation.

---

## Risks and mitigations

- **Global→None vs write-id asymmetry** misused → centralise in
  `_effective_tenant()` (read) and `_scope_tenant` (write); one table in this
  doc + explicit tests.
- **A read path that forgets the scope arg** leaks across tenants → enforce in
  the storage layer (predicate in SQL) and add a test per read tool; prefer a
  single helper that stamps the tenant onto `SearchRequest`/calls.
- **Fail-fast skipped on one transport** → resolve + validate in the shared
  bootstrap used by stdio and SSE/HTTP, not per-transport.
- **Caller passes a tenant argument expecting override** → tools expose no such
  parameter; if a future arg exists, scope takes precedence (Requirement 4.2).
