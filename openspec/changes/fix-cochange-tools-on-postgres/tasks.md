# Tasks — fix-cochange-tools-on-postgres

Paths: `server.py` = `packages/mcp/src/mintmory/mcp/server.py`, `main.py` =
`packages/cli/src/mintmory/cli/main.py`, `cochange.py` =
`packages/core/src/mintmory/core/cochange.py`. Line numbers are as of `staging`
a08aee3. `mypy packages` (strict) also checks the tests: annotate every function.

## 1. Failing tests first
- [x] 1.1 Shared stub (define it in each test module that needs it; it is a few lines):
  ```python
  class _NonSqliteStore:
      """Wraps a real SqliteBackend but is not one and has no connect() (like PostgresBackend)."""

      def __init__(self, inner: Any) -> None:
          self._inner = inner

      def __getattr__(self, name: str) -> Any:
          if name == "connect":
              raise AttributeError(name)
          return getattr(self._inner, name)
  ```
- [x] 1.2 MCP tests in `packages/mcp/tests/test_cochange_tools.py`, using the existing
  `mcp_client` fixture. In each test first do
  `server._store = cast(Any, _NonSqliteStore(server._get_store()))` (`cast` from
  `typing`: the stub is not a `StorageBackend`, so mypy strict rejects a plain
  assignment; do not use `monkeypatch.setattr` here, its undo would put the closed
  real store back into `server._store`). The fixture's teardown calls
  `server._store.close()`, which the stub forwards, then resets it to `None`.
  - `test_docs_changed_with_non_sqlite_store_returns_error`: scenario
    "docs_changed_with on a non-SQLite store"; compare against the imported
    constant `from mintmory.core.cochange import COCHANGE_SQLITE_ONLY_MESSAGE`.
  - `test_docs_timeline_non_sqlite_store_returns_error`: scenario "docs_timeline on
    a non-SQLite store" (both `{}` and `{"since": "bogus"}`).
  Today both raise a `ToolError` from the client (the tool hits `AttributeError`).
- [x] 1.3 CLI tests in `packages/cli/tests/test_index_tree_cochange_cli.py`, using its
  `cli_db` fixture (it sets `COLUMNS=200`) and `_make_tree` / `_store` / `_doc_meta`
  helpers (that module calls `pytest.importorskip("sklearn")` at import, so it is
  skipped without the `cochange` extra; the gates install it with `--extra cochange`).
  Build the stub around `_store(cli_db)` and
  `monkeypatch.setattr("mintmory.cli.main._get_store", lambda: stub)`.
  - `test_docs_commands_non_sqlite_store_exit_cleanly`: scenario "docs commands on a
    non-SQLite store" (`runner.invoke(app, ["docs", "timeline"])` and
    `runner.invoke(app, ["docs", "changed-with", "/any/path"])`).
  - `test_index_tree_non_sqlite_store_skips_cochange`: scenario "index-tree on a
    non-SQLite store skips co-change"
    (`runner.invoke(app, ["index-tree", str(root), "--cochange"])`; then for every
    path in `_BURST`, `"changeset_id" not in _doc_meta(_store(cli_db), str(root / rel))`).
  Run `.venv/bin/pytest -q --no-cov packages/mcp/tests/test_cochange_tools.py
  packages/cli/tests/test_index_tree_cochange_cli.py -k non_sqlite`; all four fail.

## 2. Fix
- [x] 2.1 `cochange.py`: add the module-level constant
  `COCHANGE_SQLITE_ONLY_MESSAGE: str = "co-change is SQLite-only: set MINTMORY_STORAGE_BACKEND=sqlite to use it"`
  (exact text) near the top, after the imports.
- [x] 2.2 `server.py` `docs_changed_with` (:677-690): change the return annotation to
  `list[dict[str, Any]] | dict[str, str]`; body:
  `store = _get_store()`; `if not isinstance(store, SqliteBackend): return {"error": "not_implemented", "message": COCHANGE_SQLITE_ONLY_MESSAGE}`;
  `return changed_with(store, path)` (the `cast` is no longer needed). Add one
  docstring line: "SQLite-only: on another storage backend returns
  {"error": "not_implemented", "message": ...}."
- [x] 2.3 `server.py` `docs_timeline` (:694-721): the same check right after
  `capped = ...` and before the `try`; pass the narrowed `store` instead of
  `cast(SqliteBackend, _get_store())`; same docstring line. Import the constant
  next to `changed_with, documents_timeline` (`server.py:43`). `cast` is used only at
  `server.py:690` and `:713` today, so drop it from `from typing import Any, Literal,
  cast` (`server.py:33`), or ruff reports F401.
- [x] 2.4 `main.py` `docs timeline` (:1658-1700) and `docs changed-with` (:1704-1751):
  right after `store = _get_store()` add
  `if not isinstance(store, _SqliteBackend):` →
  `console.print(f"[red]error[/red]: {COCHANGE_SQLITE_ONLY_MESSAGE}")` and
  `raise typer.Exit(code=1)`; then call the co-change function with `store`
  (no `cast`). Import the constant inside each function next to the existing
  `from mintmory.core.cochange import ...`.
- [x] 2.5 `main.py` `index_tree`: right after `store = _get_store()` and
  `run_cochange = ...` (:550-551) add
  `from mintmory.core.storage import SqliteBackend as _SqliteBackend` (if not already
  imported in that scope) and
  `if run_cochange and not isinstance(store, _SqliteBackend):` →
  `console.print(f"[yellow]co-change skipped[/yellow]: {COCHANGE_SQLITE_ONLY_MESSAGE}")`
  and `run_cochange = False`. This also skips the per-file embeddings collected for
  co-change and the co-change rows of the report. Leave the post-walk block
  (:889-912) as it is.
- [x] 2.6 `docs/agent-history-mcp.md` (the `docs_changed_with` / `docs_timeline`
  bullets, :127-135): add "SQLite-only: on another storage backend both tools return
  `{"error":"not_implemented","message":...}`."

## 3. Gates
- [ ] 3.1 `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`,
  `.venv/bin/mypy packages`, `.venv/bin/pytest -q` (coverage gate). These are the real gates of `.l4/config.yaml` (uv sync, ruff, mypy,
  pytest); OpenSpec validation is not a task gate (design.md `## Decisions`).
