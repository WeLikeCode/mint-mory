# Capability: agent-history (delta)

## ADDED Requirements

### Requirement: Read-only history MCP server

The system SHALL provide a dedicated MCP server `mintmory-history-mcp`
(`mintmory.mcp.history_server`) that exposes the agent-history index to agentic
tools as **read-only**. It SHALL register exactly three tools — `history_timeline`,
`history_search`, `history_stats` — and SHALL NOT expose any tool that writes,
adds, archives, dreams, or otherwise mutates a store. It SHALL read the history DB
from `MINTMORY_HISTORY_DB` (or `--db`), defaulting to `~/.mintmory/agent-history.db`,
and SHALL enforce the Hermes guard at startup (refuse a working-store path).

#### Scenario: Only read tools are exposed
- **WHEN** the `mintmory-history-mcp` server's registered tools are enumerated
- **THEN** they SHALL be exactly `history_timeline`, `history_search`, `history_stats`
- **AND** no write/mutate tool (e.g. `memory_add`, `memory_dream`, `memory_archive`, `summary_put`) SHALL be present.

#### Scenario: Refuses the working store
- **WHEN** the server is started with `MINTMORY_HISTORY_DB`/`--db` pointing at `hermes.db`, `memories.db`, or `$MINTMORY_DB`
- **THEN** it SHALL fail fast with the Hermes guard error and not serve.

### Requirement: Shared time-ranged query surface

Timeline and search SHALL be implemented once in `core/history/query.py`
(`timeline`, `search`, `resolve_window`) and shared by both the `mintmory history`
CLI and the MCP server, so their results are consistent. `timeline` SHALL return
session summaries whose `valid_from` falls in the resolved window (newest-first),
optionally filtered by `repo` and `kind`; `search` SHALL hybrid-search across
session summaries only. `resolve_window` SHALL treat `since` (`Nd/Nw/Nm/Ny`) as
mutually exclusive with `from/to` and default to the last 90 days.

#### Scenario: Time-window timeline
- **GIVEN** an indexed history DB with sessions dated across several months
- **WHEN** `history_timeline(since="75d", repo="mintkey")` is called (MCP or CLI)
- **THEN** it returns only that repo's sessions whose `valid_from` is within the last 75 days, newest-first, each a dated summary row with a `source_path` back-link.
