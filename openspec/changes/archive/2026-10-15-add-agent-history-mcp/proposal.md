# Change: Dedicated read-only agent-history MCP (`mintmory-history-mcp`)

## Why

MM-27 indexes agentic chat history into `~/.mintmory/agent-history.db` and exposes
it via the `mintmory history` CLI. Agents can already reach it by pointing the
generic `mintmory-mcp` at that DB, but that server also exposes write tools
(`memory_add`, `memory_dream`, …) and lacks the **time-ranged** query that makes
"what changed ~2 months ago" first-class. This change adds the Phase-4 MCP seam:
a dedicated, **read-only** history MCP with purpose-built timeline/search tools.

## What changes

- **Shared query module** `core/history/query.py` factors the timeline/search
  logic (currently inline in the CLI) into reusable functions returning plain
  dicts, so the CLI and the new MCP share one implementation (DRY). Includes the
  time-window resolver. Enforces the existing Hermes guard.
- **New MCP server** `mintmory-history-mcp` (`packages/mcp`,
  `mintmory.mcp.history_server`) — a FastMCP server exposing exactly three
  **read-only** tools: `history_timeline`, `history_search`, `history_stats`. No
  write tools. Reads `~/.mintmory/agent-history.db` (overridable via
  `MINTMORY_HISTORY_DB` / `--db`), and refuses to run against the working store.
- **CLI refactor**: `mintmory history timeline` / `search` call the shared query
  functions (behaviour unchanged; output rendering stays in the CLI).
- **Entry point**: `mintmory-history-mcp = "mintmory.mcp.history_server:main"`.

Additive: the existing `mintmory-mcp` server and `mintmory history` CLI behaviour
are unchanged; no schema changes.

## Impact

- Affected specs: **agent-history** (MODIFIED: adds the MCP query surface).
- Affected code: new `core/history/query.py`; new
  `packages/mcp/src/mintmory/mcp/history_server.py`; `packages/mcp/pyproject.toml`
  (new script); CLI `history timeline/search` refactor to use the shared module.
- New tests: `test_history_query.py`, `test_history_mcp.py`.
- No change to `schema.sql` or the working store.
