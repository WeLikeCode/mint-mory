# Capability: mcp (delta)

## ADDED Requirements

### Requirement: Co-change tools report SQLite-only on other backends
When the main MCP server's store is not a `SqliteBackend` (for example
`PostgresBackend`), `docs_changed_with` and `docs_timeline` SHALL return
`{"error": "not_implemented", "message": COCHANGE_SQLITE_ONLY_MESSAGE}` without
calling any co-change function, instead of raising. On a SQLite store both tools
SHALL behave exactly as before.

#### Scenario: docs_changed_with on a non-SQLite store
- **GIVEN** `server._store` is a stub that wraps the real SQLite store, forwards every attribute except `connect` (which raises `AttributeError`, as `PostgresBackend` has no `connect`), and is not a `SqliteBackend` instance
- **WHEN** a client calls `docs_changed_with` with `{"path": "/repo/a.py"}`
- **THEN** the call does not raise, and `res.data == {"error": "not_implemented", "message": COCHANGE_SQLITE_ONLY_MESSAGE}`, where the message is `co-change is SQLite-only: set MINTMORY_STORAGE_BACKEND=sqlite to use it`.

#### Scenario: docs_timeline on a non-SQLite store
- **GIVEN** the same stub store
- **WHEN** a client calls `docs_timeline` with `{}` and again with `{"since": "bogus"}`
- **THEN** both calls return the same `not_implemented` error dict (the backend check comes before the date parsing).

#### Scenario: SQLite behaviour is unchanged
- **WHEN** the existing tests in `packages/mcp/tests/test_cochange_tools.py` run against the real SQLite store
- **THEN** they pass unedited (peers, empty lists, the 200-row clamp, and the `bad_request` dict for a malformed `since`).
