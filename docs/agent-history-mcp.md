# Exposing the agent-history index to agentic tools (MCP)

The agent-history index (`mintmory history`, see
[`design/agent-history-index.md`](design/agent-history-index.md)) lives in its own
SQLite file at `~/.mintmory/agent-history.db` — **separate from your working
memory store** (`hermes.db`). This doc shows how to make that history searchable
from inside agentic tools (Claude Code, Cursor, etc.) over MCP.

There are two tiers. **Tier 1 works today with zero new code.**

---

## Tier 1 — point the existing MintMory MCP server at the history DB (now)

MintMory already ships an MCP server (`mintmory-mcp`) whose database is chosen by
the `MINTMORY_DB` env var. Register a **second, separate** MCP server whose DB is
the history file. Agents then get `memory_search` over your past sessions, fully
isolated from your working store.

### Claude Code

```bash
claude mcp add agent-history \
  --env MINTMORY_DB=$HOME/.mintmory/agent-history.db \
  -- uv run --project /Users/alexandruiacobescu/gooseProjects/MintMory mintmory-mcp
```

(Use `--scope user` to make it available in every project.) You'll now have two
MintMory MCP servers: your normal one (working memory) and `agent-history`
(read-your-past-sessions). They cannot cross-contaminate — different files.

### Cursor / any `mcp.json`-based client

```jsonc
{
  "mcpServers": {
    "agent-history": {
      "command": "uv",
      "args": ["run", "--project", "/Users/alexandruiacobescu/gooseProjects/MintMory", "mintmory-mcp"],
      "env": { "MINTMORY_DB": "/Users/alexandruiacobescu/.mintmory/agent-history.db" }
    }
  }
}
```

**How an agent uses it:** call `memory_search` with a topic, e.g.
*"mintkey JWT Kong fix"*, and it returns the matching session summaries (each is a
dated `repo · KIND: what happened` line with a `source_path` back-link in metadata).

**Caveats of Tier 1:**
- `mintmory-mcp` also exposes write tools (`memory_add`, `memory_dream`, …). They'd
  write into the *history* DB, not your working store — harmless, but it's not
  strictly read-only. If you want read-only, use Tier 2.
- `memory_search` is topic search; the **time-range** query ("what changed ~2
  months ago") is not first-class over MCP yet — that's exactly what Tier 2 adds.
- Keep this DB current with `mintmory history sync` (see below); the MCP server
  reads whatever is in the file.

---

## Tier 2 — the dedicated, read-only history MCP (recommended) ✅ shipped (MM-28)

A purpose-built MCP, `mintmory-history-mcp`, that exposes exactly **three
read-only tools** — no write/mutate tools are reachable — making the time-ranged
"what changed" query first-class for agents:

- `history_timeline(since="90d" | from_date/to_date ISO, repo?, kind?, limit?)` →
  the dated changelog window (the "2 months ago" query).
- `history_search(query_text, repo?, since?, limit?)` → hybrid search over session
  summaries, newest-first.
- `history_stats()` → counts by source/kind + earliest/latest dates.

It wraps the same `core.history.query` functions the CLI uses, reads
`MINTMORY_HISTORY_DB` (default `~/.mintmory/agent-history.db`), and enforces the
Hermes guard at startup (refuses the working store). Register it — **this is the
recommended setup, replacing Tier 1**:

```bash
claude mcp add agent-history --scope user \
  -- uv run --project /Users/alexandruiacobescu/gooseProjects/MintMory mintmory-history-mcp
```

`--scope user` makes it available in **every** Claude Code project on this machine.
For Cursor / other clients, use the same command/args in their `mcp.json` (no env
needed unless your DB is non-default):

```jsonc
{ "mcpServers": { "agent-history": {
  "command": "uv",
  "args": ["run","--project","/Users/alexandruiacobescu/gooseProjects/MintMory","mintmory-history-mcp"]
}}}
```

Typical agent use: *"call history_timeline with since='2m' and repo='mintkey' to
see what was fixed there ~2 months ago"*, or `history_search("kong jwt")` for topic
recall. Results are dated session summaries with `source_path` back-links.

---

## Keeping it current

The index is a snapshot; refresh it before you query (append-only logs make this
cheap — only changed/new session files are re-read):

```bash
mintmory history sync        # incremental: skips unchanged sessions
```

Run it manually, or wire a `launchd`/`cron` job if you want it automatic.

## Querying from the CLI (no MCP needed)

```bash
mintmory history timeline --since 75d --repo mintkey     # "~2 months ago in mintkey"
mintmory history timeline --from 2026-04-01 --to 2026-04-30 --kind fix
mintmory history search "kong jwt injection" --since 90d
mintmory history scrub                                    # audit for any residual secrets
```

## Safety notes

- The history DB is created `chmod 600` and should stay out of any off-machine
  backup/sync (it is your agents' transcript exhaust). Add it to ignore lists.
- Secrets are redacted at ingest (`[REDACTED:…]` placeholders); `history scrub`
  re-audits and exits non-zero if anything slipped through. Run it after a backfill.
- Never point `--db` (or the MCP `MINTMORY_DB`) at `hermes.db`/`memories.db` — the
  tooling refuses, but the MCP env is yours to set, so keep them distinct.
