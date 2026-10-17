# Change: Co-change tools fail cleanly on a non-SQLite store

## Why

The co-change functions in `packages/core/src/mintmory/core/cochange.py` take a
`SqliteBackend` and call `store.connect()`; `PostgresBackend` has no `connect()`.
add-pluggable-storage-backend declared co-change SQLite-only, but every caller casts
the store and calls through, so with `MINTMORY_STORAGE_BACKEND=postgres` two MCP
tools, two CLI commands and the default `index-tree` co-change pass crash with
`AttributeError` instead of reporting that co-change is SQLite-only (see Evidence).

## What changes

- One message constant in `core/cochange.py`:
  `COCHANGE_SQLITE_ONLY_MESSAGE = "co-change is SQLite-only: set MINTMORY_STORAGE_BACKEND=sqlite to use it"`.
- MCP: both tools check `isinstance(store, SqliteBackend)` first and otherwise return
  `{"error": "not_implemented", "message": COCHANGE_SQLITE_ONLY_MESSAGE}` (the
  server's existing error shape; `not_implemented` is already used by `vision_run`).
- CLI `docs timeline` / `docs changed-with`: print the message in red and exit 1.
- CLI `index-tree`: when co-change would run on a non-SQLite store, print one notice
  line, skip the co-change pass, and finish the run normally (exit 0, report printed).

Co-change on Postgres itself stays out of scope.

## Evidence

`apply_changesets` (`cochange.py:682`), `changed_with` (:763) and
`documents_timeline` (:829) call `store.connect()`; `PostgresBackend`
(`packages/core/src/mintmory/core/storage_postgres.py:172`) has no `connect()`.
With `MINTMORY_STORAGE_BACKEND=postgres`:

1. The MCP tools `docs_changed_with` and `docs_timeline`
   (`packages/mcp/src/mintmory/mcp/server.py:677-690` and `:694-721`) pass
   `cast(SqliteBackend, _get_store())` and raise `AttributeError` (the client sees an
   unhandled tool error) instead of the server's error dict.
2. The CLI commands `mintmory docs timeline` and `mintmory docs changed-with`
   (`packages/cli/src/mintmory/cli/main.py:1658-1700` and `:1704-1751`) do the same
   cast and crash with a traceback.
3. `mintmory index-tree` runs the co-change pass by default
   (`DocumentSettings.cochange_enabled = True`, `config.py:306`). After the whole walk
   has been written, `apply_changesets(cast(_SqliteBackend, store), …)`
   (`main.py:889-896`) raises `AttributeError` as soon as a change-set is found, so a
   default `index-tree` run on a Postgres store ends in a traceback and prints no
   report.

All three reproduce with a stub store that, like `PostgresBackend`, is not a
`SqliteBackend` and has no `connect()` (each raised `AttributeError: connect`);
none was run against a live Postgres.

## Impact

- Affected specs: **mcp** (ADDED), **ingestion** (ADDED).
- Code: `packages/core/src/mintmory/core/cochange.py` (constant),
  `packages/mcp/src/mintmory/mcp/server.py`, `packages/cli/src/mintmory/cli/main.py`,
  `docs/agent-history-mcp.md` (one line).
- Tests: `packages/mcp/tests/test_cochange_tools.py`,
  `packages/cli/tests/test_index_tree_cochange_cli.py`.
- No behaviour change on SQLite (the default).
