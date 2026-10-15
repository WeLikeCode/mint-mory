# Change: Document co-change/recency MCP tools + what-co-changed prompt (MM-41)

## Why

The document recency + co-change feature (MM-33/34/35) is **CLI-only**:
`mintmory docs changed-with <path>` and `mintmory docs timeline` query the working
store via `core/cochange.changed_with(store, path)` and
`cochange.documents_timeline(store, …)`, but **no MCP tool exposes them**, so MCP
agents cannot ask "what co-changed with this file?" or "which docs are newest?".
MM-40 noted a deferred `what_cochanged_with` prompt blocked on this gap; this change
fills it.

**Placement correction:** these belong on the **main** MCP server, not the history
server. Document records are written by `index-tree` into the **working store**
(`source='document'`) — which the main server's `_get_store()` operates on — whereas
the history server is the read-only agent-history index (`agent-history.db`). The
MM-40 note that put a co-change prompt on the history server was a mis-attribution.

## What changes (additive, read-only)

Two new **main-server tools** (thin wrappers over existing, already-reviewed
`core/cochange` functions; both read-only over the working store):
- `docs_changed_with(path)` → `cochange.changed_with(_get_store(), path)`. Returns
  the peer documents in the same observed change-set: `[{path, strength,
  observed_at, kind}]`; `[]` when the path is unknown or not in a change-set. The
  description states the honesty limit (observed co-change — same time window +
  folder/content proximity — **not** a version-controlled commit), matching the CLI.
- `docs_timeline(since?, from_date?, to_date?, collection?, limit=50)` →
  `cochange.documents_timeline(...)`. Returns documents newest-first by file mtime:
  `[{date, collection, path, title, valid_from}]`. Completes the doc-recency surface
  so the co-change answer pairs with "which is newer". (`changed_with` is the core
  for the prompt; `docs_timeline` is the recency companion — the whole feature is
  otherwise unreachable from MCP.)

One new **main-server prompt**:
- `mintmory_what_cochanged_with(path)` → guidance to call `docs_changed_with(path)`,
  interpret the strength/observed_at/kind, surface the honesty caveat, and (if empty)
  hint that the corpus may need `index-tree --cochange`. May also reference
  `docs_timeline` for recency.

Returns are already lean (small flat dicts), so no `verbosity` knob is needed. The
working store already scopes these queries to `source='document'`, so non-document
memories are never returned. Manifest cost: +2 tools, +1 prompt on the main server
(returns themselves cost nothing until called) — within the MM-38/MM-40 token budget.

## Impact

- Affected specs: **mcp** (ADDED: two read-only doc-query tools + the
  `mintmory_what_cochanged_with` prompt).
- Affected code: `packages/mcp/src/mintmory/mcp/server.py` (two `@mcp.tool()` + one
  `@mcp.prompt()`); tests. No change to `core/cochange.py` or any existing tool.
- Limitation (documented): if documents were indexed into a **separate** DB
  (`index-tree --db <other>`), the MCP (which uses the working store) won't see them;
  the default `index-tree` target IS the working store, so the common case works.
- Migrations: none. Purely additive, read-only.
