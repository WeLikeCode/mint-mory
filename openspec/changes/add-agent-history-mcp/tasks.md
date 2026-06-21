# Tasks — add-agent-history-mcp

## 1. Shared query module
- [x] 1.1 `core/history/query.py`: `resolve_window`, `timeline`, `search`, `_open_history`
  (Hermes guard), row-dict shape. Reuse the CLI since-grammar.

## 2. CLI refactor (DRY, no behaviour change)
- [x] 2.1 `mintmory history timeline` / `search` call `query.timeline` / `query.search`;
  keep output rendering + flags identical.

## 3. Read-only MCP server
- [x] 3.1 `packages/mcp/.../history_server.py`: FastMCP "mintmory-history" with
  `history_timeline`, `history_search`, `history_stats` (NO write tools); `_db_path()`
  from `MINTMORY_HISTORY_DB`/default; `main()` with guard + stdio/sse.
- [x] 3.2 `packages/mcp/pyproject.toml`: `mintmory-history-mcp` script entry.

## 4. Tests
- [x] 4.1 `test_history_query.py` (window/timeline/search/guard) +
  `test_history_mcp.py` (exactly 3 read-only tools, no write tools, guard, returns rows).

## 5. Gates
- [x] 5.1 `ruff check . && ruff format --check . && mypy packages && pytest -q` (cov ≥ 80).
