# Exposing the agent-history index to agentic tools (MCP)

The agent-history index (`mintmory history`, see
[`design/agent-history-index.md`](design/agent-history-index.md)) lives in its own
SQLite file at `~/.mintmory/agent-history.db` — **separate from your working
memory store** (`hermes.db`). This doc shows how to make that history searchable
from inside agentic tools (Claude Code, Cursor, etc.) over MCP.

There are two tiers. **👉 Use Tier 2 (the dedicated read-only `mintmory-history-mcp`
server) — it's the recommended setup.** Tier 1 is a zero-code fallback kept for
reference; it works but also exposes write tools.

---

## Tier 1 — (fallback) point the existing MintMory MCP server at the history DB

MintMory already ships an MCP server (`mintmory-mcp`) whose database is chosen by
the `MINTMORY_DB` env var. Register a **second, separate** MCP server whose DB is
the history file. Agents then get `memory_search` over your past sessions, fully
isolated from your working store.

### Claude Code

```bash
claude mcp add agent-history \
  --env MINTMORY_DB=$HOME/.mintmory/agent-history.db \
  -- uv run --project /ABSOLUTE/PATH/TO/mint-mory mintmory-mcp
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
      "args": ["run", "--project", "/ABSOLUTE/PATH/TO/mint-mory", "mintmory-mcp"],
      "env": { "MINTMORY_DB": "/Users/you/.mintmory/agent-history.db" }
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
  -- uv run --project /ABSOLUTE/PATH/TO/mint-mory mintmory-history-mcp
```

`--scope user` makes it available in **every** Claude Code project on this machine.
For Cursor / other clients, use the same command/args in their `mcp.json` (no env
needed unless your DB is non-default):

```jsonc
{ "mcpServers": { "agent-history": {
  "command": "uv",
  "args": ["run","--project","/ABSOLUTE/PATH/TO/mint-mory","mintmory-history-mcp"]
}}}
```

Typical agent use: *"call history_timeline with since='2m' and repo='mintkey' to
see what was fixed there ~2 months ago"*, or `history_search("kong jwt")` for topic
recall. Results are dated session summaries with `source_path` back-links.

## Resources & Prompts (MM-40)

The history server also exposes:

**Resource:**
- `mintmory://history/sources` — per-collection session counts + earliest/latest dates. Read with your MCP client to get an orientation view without fetching session content.

**Prompt:**
- `mintmory_changelog(repo?, since?, kind?)` — guidance to call `history_timeline` for the requested window. Read-only; references no write tools.

The main `mintmory-mcp` server (for working memory) exposes:

**Resources:**
- `mintmory://schema` — all 8 memory categories, 12 link types, and 4 sources with one-line descriptions, plus the `MemoryRecord` field list.
- `mintmory://capabilities` — active configuration summary (embedding provider, LLM provider + enabled flag + model, vision provider, dreaming steps). Never includes API keys.

**Prompts:**
- `mintmory_onboard(db_path?, llm_enabled?)` — the MintMory adoption policy as a prompt.
- `mintmory_recall_before_task(intent, link_types?)` — search-first → act → session_feedback discipline.
- `mintmory_session_closeout(session_id, useful_ids?, stale_ids?)` — the session feedback close-out call.
- `mintmory_what_cochanged_with(path)` — guidance to call `docs_changed_with` for the given path,
  interpret `strength`/`observed_at`/`kind`, with the observed-co-change (not-a-commit) honesty caveat,
  and an index-tree hint when the result is empty. Read-only; no write suggestions.

**Tools (MM-41, read-only, working-store scope):**
- `docs_changed_with(path)` → documents observed to co-change with `path` in the same `index-tree`
  change-set. Returns `[{path, strength, observed_at, kind}]`; empty if not indexed or not in a
  change-set. `kind` may be `""` for legacy rows. OBSERVED co-change (time + folder + content
  proximity) — **not** a version-controlled commit. Read-only; only `source='document'` records.
  > **Scope**: reads the working store (`MINTMORY_DB`). Documents indexed into a separate `--db`
  > are not visible here. Populate with `mintmory index-tree <root> --cochange`.
- `docs_timeline(since?, from_date?, to_date?, collection?, limit=50)` → indexed documents newest-first
  by file mtime. Returns `[{date, collection, path, title, valid_from}]`. `limit` is capped at 200
  for token safety. A malformed date/since returns `{"error":"bad_request","detail":...}`. Read-only;
  only `source='document'` records appear.

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
mintmory history timeline --since 2m --repo mintkey      # "~2 months ago in mintkey"
mintmory history timeline --from 2026-04-01 --to 2026-04-30 --kind fix
mintmory history search "kong jwt injection" --since 90d
mintmory history scrub                                    # audit for any residual secrets
```

## Safety notes

- The history DB is created `chmod 600` and should stay out of any off-machine
  backup/sync (it is your agents' transcript exhaust). Add it to ignore lists.
- Secrets are redacted at ingest (`[REDACTED:…]` placeholders); `history scrub`
  re-audits and exits non-zero if anything slipped through. Run it after a backfill.
- Never point the DB selector (`--db`, or `MINTMORY_DB` for Tier-1 / `MINTMORY_HISTORY_DB`
  for Tier-2) at `hermes.db`/`memories.db` — the tooling refuses, but the env is
  yours to set, so keep the history DB a distinct file.

---

## `verbosity="concise"` — lightweight browsing

All four token-heavy read tools accept an optional `verbosity` parameter:

| Tool | `verbosity="full"` (default) | `verbosity="concise"` |
|---|---|---|
| `memory_search` | Full `SearchResponse` (~25 fields/hit) | `{id, category, snippet, is_note}` per hit; `notes_on_results` → ids only |
| `memory_get` | All 30 fields | `{id, category, content}` |
| `history_timeline` | 15-field row | `{date, repo, kind, title, snippet}` |
| `history_search` | 15-field row | `{date, repo, kind, title, snippet}` |

Use `verbosity="concise"` for browse/scan passes; switch to `verbosity="full"` when
you need the body, metadata, scoring fields, or source_path back-links.

Default is always `"full"` — existing clients are unaffected.

---

## LLM tier configuration for `memory_dream`

`memory_dream` runs structural steps (anomaly detection, concept linking) with any
configuration, but the summariser and contradiction-resolver are backed by the
configured LLM tier:

| Env var | Purpose | Example |
|---|---|---|
| `MINTMORY_LLM_PROVIDER` | `none` (default, skips LLM steps), `openai` (OpenAI-compatible) | `openai` |
| `MINTMORY_LLM_BASE_URL` | Base URL of the provider / gateway | `http://localhost:8789/v1` |
| `MINTMORY_LLM_API_KEY` | API key for the provider | `pk-hermes-...` |
| `MINTMORY_LLM_MODEL` | Model name to use | `MiniMax-M2.7` |
| `MINTMORY_LINK_*` | Concept-linking policy | see source |
| `MINTMORY_SUMMARY_*` | Summary generation policy | see source |

With `MINTMORY_LLM_PROVIDER=none` (the default), the summary-generation and
contradiction-resolution steps are skipped (`new_summaries=0`,
`contradictions_resolved=0`) and only structural steps run. No LLM backend is
required for the structural steps.

A Portkey gateway (self-hosted, `localhost:8789`) with a `pk-<name>-<org>` virtual
key is the recommended way to proxy cloud models (MiniMax-M2.5 / M2.7) to MintMory.
