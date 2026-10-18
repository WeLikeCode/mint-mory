# Design — Multi-Tenancy 6/10: tenant-scoped MCP server

## Grounding (base branch, verified)

- `packages/mcp/src/mintmory/mcp/server.py`: `mcp = FastMCP(name="mintmory", …,
  instructions=…)`, module global `_store` with lazy `_get_store()`
  (`build_storage()` + `initialise()`, no embedder), resources
  `mintmory://schema` and `mintmory://capabilities`, and 18 tools: `memory_add`,
  `memory_get`, `memory_search` (graph traversal via `search_around_link_types` /
  `search_around_depth`; there is no separate `search_around` tool),
  `memory_dream`, `memory_stats`, `session_feedback`, `memory_archive`,
  `summary_list`, `summary_get`, `summary_jobs`, `summary_put`, `memory_note`,
  `notes_list`, `docs_changed_with`, `docs_timeline`, `image_jobs`,
  `image_caption_put`, `vision_run`. There is no link-creation tool; links are
  created only inside `memory_note` (anchor) and `image_caption_put`.
- `main()` uses `argparse` (`--transport stdio|sse`, `--port`, `--db`, which sets
  `MINTMORY_DB`), calls `init_telemetry`, then `mcp.run(transport="stdio")` or
  `mcp.run(transport="sse", port=args.port)`.
- `packages/mcp/tests/test_tools.py`: `mcp_client` fixture (in-memory `Client`,
  `MINTMORY_DB` in `tmp_path`, `server._store` reset), `test_all_tools_registered`
  asserts the exact tool set, tool errors are asserted with
  `pytest.raises(ToolError)`.
- `config.py` groups are `BaseSettings` with `SettingsConfigDict(env_prefix=
  "MINTMORY_<GROUP>_", extra="ignore")`.
- `history_server.py` is a separate MCP server over the agent-history database;
  it has no MintMory memory tools and is out of scope.

## Startup

```python
_scope_tenant: str = TENANT_GLOBAL

def _effective_tenant() -> str | None:
    return None if _scope_tenant == TENANT_GLOBAL else _scope_tenant

def _bootstrap_scope(scope: str) -> None:
    global _scope_tenant
    validate_tenant_id(scope)
    store = _get_store()
    if scope != TENANT_GLOBAL:
        t = store.get_tenant(scope)
        if t is None:
            raise TenantNotFoundError(scope)
        if not t.is_active:
            print(f"mintmory-mcp: warning: tenant {scope!r} is inactive; this server is read-only",
                  file=sys.stderr)
    _scope_tenant = scope
```

`main()` order: parse args → apply `--db` → resolve the scope (R1.2) →
`_bootstrap_scope` (exit 1 on `TenantError`) → `init_telemetry` → `mcp.run`.
One bootstrap for both transports is what makes stdio and SSE behave the same.

## Tool wiring

Each tool body reads `E`/`S` at call time and passes them as in the R2.1 table;
storage enforces the boundary (predicate in SQL, write guard, same-tenant
references), so a tool cannot leak by forgetting a post-filter. The per-tool
error behaviour is today's: `memory_get` returns `null` for not found;
`memory_archive` now catches the `KeyError` of a foreign id (named scope) and
returns `{"error": "not_found", "message": str(exc)}`; `session_feedback` and
`image_caption_put` keep their error dicts; any `TenantError` propagates and
fastmcp turns it into a tool error.

Why the global scope creates only in `global`: a global agent creating a note
or a description inside tenant `T` would be a write into `T` by an agent that is
not `T`'s; confining creates to `global` keeps every reference inside one tenant
with one simple rule, while reads and by-id modifications stay unrestricted
(today's behaviour). Only `cross-tenant-copy` writes into another tenant, and it
is an explicit, separate tool.

## Discoverability

`mintmory_capabilities()` adds the two keys to both its normal and its fallback
dict. The instruction sentence is appended to the existing `instructions`
string.

## Tests

- `packages/mcp/tests/test_tenancy_mcp.py`: R1.6 (driving `main()`), R2.2
  inventory, R2.3, R3.2, R4.2, R5.3, R6.1, R7, R8.1–R8.3 (deactivate with
  `store.set_tenant_active` between calls; two `tenant_create` calls through
  `asyncio.gather`).
- Fixtures: `acme_client` creates `acme`, calls `_bootstrap_scope("acme")`,
  yields the client, then resets `server._scope_tenant` and `server._store`.
- `tests/integration/test_tenancy_mcp.py`: one file database, scope `acme` then
  `global` (R9.2).

## Risks

- A future tool added without a decision → the inventory test fails until
  `TOOL_TENANT_SCOPE` lists it.
- `_scope_tenant` leaking between tests → fixture teardown resets it.
