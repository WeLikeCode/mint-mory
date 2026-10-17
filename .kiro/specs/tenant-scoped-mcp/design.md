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

### Source and precedence

A new MCP-scope value resolved at server start, precedence highest-first:
1. `--tenant <id>` CLI argument on the `mintmory-mcp` command.
2. `MINTMORY_MCP_TENANT` env var (new `MINTMORY_MCP_` settings group, consistent
   with the existing convention).
3. Default `global`.

CLI argument wins over env (Requirement 1.3). The resolved value is stored once
(see "Scope holder") and never recomputed per call (Requirement 1.5).

### Fail-fast validation

At startup, after the store is initialised:
- If scope == `global` → always valid (the `multi-tenancy` schema seeds it).
- Else → `store.get_tenant(scope)`; if `None`, raise a clear startup error and
  exit non-zero. No implicit create, no silent fallback (Requirement 1.4).

This runs for stdio and SSE/HTTP identically because all paths go through the
same server bootstrap (Requirement 1.6).

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

### Writes (Requirement 3)
- `memory_add`: set `record.tenant_id = _scope_tenant` (literal, so a named
  scope writes under `T` and global writes under `"global"` — Requirement 3.2).
  Note: for writes we use the literal scope id (`global` is a real tenant row),
  whereas for reads we use `None` to mean unrestricted.
- `memory_archive`, link creation, `session_feedback`, `summary_put`,
  `image_caption_put`, `memory_note`: constrain the target to the scope; a
  foreign-tenant target is not-found / no-op (Requirement 3.3).
- `memory_dream`: pass `tenant_id=_effective_tenant()`; under a named scope only
  that tenant's memories are consolidated, idempotently (Requirement 3.4).

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
    t = store.create_tenant(Tenant(id=tenant_id, name=name))
    return t.model_dump(mode="json")
```

- Validation of `tenant_id` is delegated to the `multi-tenancy` `Tenant` model
  (Requirement 5.5); an invalid id surfaces as a clear error.
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

## Startup / bootstrap changes (`server.py`)

- Add a `MINTMORY_MCP_` settings group (or extend the existing MCP CLI entry) to
  read `tenant` (env `MINTMORY_MCP_TENANT`).
- Add `--tenant` to the `mintmory-mcp` command / entrypoint; CLI wins over env.
- In the server bootstrap (before serving): resolve `_scope_tenant`, call
  `_get_store()`, then run fail-fast validation (`get_tenant` unless global).
- Keep the `_store` singleton as-is; the scope is an independent module value.

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

Unit (MCP package, `:memory:` store, mock embedder):
- Scope resolution: default → `global`; env `MINTMORY_MCP_TENANT` →that tenant;
  `--tenant` overrides env; unknown named tenant → fail-fast startup error.
- `_effective_tenant()` mapping: global→None, named→T.
- Read boundary: with two tenants seeded, a named-scope server's `memory_search`
  / `memory_get` / `search_around` return only its tenant; a foreign id is
  not-found; a global-scope server sees both.
- Write boundary: named-scope `memory_add` persists under `T`; global under
  `global`; a named-scope attempt to archive a foreign record is not-found.
- No override: a tenant-like argument on a tool does not widen/redirect access.
- `tenant_create`: new id creates; existing id idempotent; invalid id errors;
  caller scope unchanged afterwards.
- `tenant_list`: returns all tenants in both scopes.
- `capabilities` reports the scope.

Integration (`tests/integration/`): bring up a named-scope and a global-scope
configuration against a shared DB with two tenants; assert isolation and the
unrestricted global case end-to-end.

Gates: `uv run pytest` (≥ 80% coverage), `uv run mypy packages/`,
`uv run ruff check packages/` all exit 0.

---

## Dependencies and sequencing

- **Hard dependency on `multi-tenancy`**: the `Tenant` model, `tenants` table,
  `create_tenant`/`get_tenant`/`list_tenants`, and the storage tenant predicate
  must exist first. This spec's tasks assume those are complete.
- No schema changes are introduced here (no new tables/columns), so the schema
  gate and OpenAPI are unaffected except for optional MCP-tool documentation.

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
