# Change: Lower MCP token usage with opt-in concise results (MM-38)

## Why

Informed by Anthropic's "Code execution with MCP" article, an Opus audit measured
MintMory's two MCP servers' token footprint:

- **Fixed manifest cost ≈ 4,700 tokens/session** (16 main-server tools + 3
  history tools + two `instructions` blocks), before any call. Bloat includes
  `memory_dream`'s description embedding `MINTMORY_LLM_*` env-var docs.
- **Result cost is the bigger driver.** `memory_search` returns full ~30-field
  `MemoryRecord` objects — most fields are internal scoring/state the agent never
  reads (`usefulness_score`, `staleness_score`, `reinforcement_count`,
  `retrieval_count`, the `is_*` flags, `superseded_by`, `contradicts_ids`, three
  timestamps) plus full `content` (≤10k chars) and a free-form `metadata` blob.
  Measured **≈2,580 tokens for a default 10-hit search** (≈25,500 at limit=100);
  `notes_on_results` can attach whole extra records per hit (unbounded). The
  history tools return 15-field rows with full `summary` text
  (`history_timeline` default limit=50 ≈ 10,500 tokens/call).

A concise projection (id + category + content snippet) is ≈24 tokens/hit — a
**~90% reduction** on the most-called tool.

## What changes

Backward-compatible, opt-in (defaults and limits unchanged):

- **`verbosity` parameter** (`"full"` | `"concise"`, default `"full"`) on the
  token-heavy read tools: `memory_search`, `memory_get` (main server) and
  `history_timeline`, `history_search` (history server). `"full"` is byte-identical
  to today.
- **Concise projections** (the article's "distill before returning"):
  - search hit → `{id, category, snippet, is_note}` (snippet = content truncated
    to ~200 chars); drops the internal scoring/state fields, full content, and raw
    metadata. The envelope keeps `session_id`/`total_found`/`search_around_ids`.
  - `memory_get` concise → `{id, category, content}`.
  - history row → `{date, repo, kind, title, snippet}` (drops
    branch/ts_start/segment_count/turn_lo/turn_hi/source_path/agent/collection).
  - In concise search, `notes_on_results` returns note **ids** only, not full
    nested records (removes the unbounded multiplier).
- **Advertise concise** so the opt-in is actually used: each affected tool's
  description gains a one-line "use `verbosity=\"concise\"` to browse/scan; `\"full\"`
  only when you need the body", and the server `instructions` mention it.
- **Trim fixed-cost description bloat (no behaviour change):** move
  `memory_dream`'s embedded env-var configuration prose to the docs (keep a
  one-line pointer); tighten the two `instructions` blocks. Frees ~1,000+ fixed
  tokens/session; no tool removed or gated.

Out of scope (kept by explicit decision): default output stays `full`; default
limits unchanged (search 10 / timeline 50, max 100); all 16 tools stay
always-registered. Full code-execution mode is deferred to a separate future-track
stub (`add-mcp-code-execution-mode`).

## Impact

- Affected specs: **search** (memory_search/memory_get concise), **agent-history**
  (history_timeline/history_search concise).
- Affected code: `packages/mcp/src/mintmory/mcp/server.py` (memory_search,
  memory_get, instructions, memory_dream description), `packages/mcp/src/mintmory/
  mcp/history_server.py` (timeline/search, instructions), small pure projection
  helpers; docs for the relocated `memory_dream` config prose. The shared
  `core/history/query.py:_shape_row` is NOT mutated — concise projection is applied
  at the MCP layer so CLI output is untouched.
- Migrations: none. Defaults identical → existing MCP clients unaffected.
