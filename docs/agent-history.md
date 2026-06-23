# Agent History — a searchable changelog of your agentic work

MintMory can index the chat history of your coding agents — **Claude Code,
Codex, Kiro, and Hermes** — into one searchable, time-aware changelog, so you (or an
agent) can answer questions like *"what did I fix or add in `mintkey` about two
months ago?"* in seconds instead of grepping gigabytes of transcripts.

It is **read-optimised, secret-redacted, and isolated**: history lives in its own
SQLite file (`~/.mintmory/agent-history.db`), completely separate from your
working memory store — so authored documents/notes never mix with machine chat
transcripts.

- **Humans:** use the `mintmory history` CLI (below).
- **Agents:** use the read-only `mintmory-history-mcp` MCP server (tools:
  `history_timeline`, `history_search`, `history_stats`).
- MCP setup details: [`agent-history-mcp.md`](agent-history-mcp.md). Design +
  rationale: [`design/agent-history-index.md`](design/agent-history-index.md).

---

## How it works (30-second model)

```
~/.claude/projects/**.jsonl   ─┐
~/.codex/sessions/**.jsonl    ─┤  adapters → redact secrets → distill →  ~/.mintmory/
Kiro globalStorage sessions   ─┤  (one dated summary per session)         agent-history.db
~/.hermes/sessions/session_*  ─┘
```

- **One summary per session.** Each session becomes a single dated changelog
  entry: `2026-04-18 · mintkey · FIX: <what happened>`, with a `source_path`
  back-link to the original transcript for deep dives. (Raw turns aren't stored.)
- **Work-time, not ingest-time.** Entries are dated by when the work happened
  (`valid_from`), so "2 months ago" means 2 months ago — even if you indexed today.
- **Secrets are redacted at ingest** (API keys, JWTs, broker keys, private keys,
  `Authorization` headers → `[REDACTED:…]`). A `scrub` audit re-checks the store.
- **Differentiation:** every chat record is tagged `record_type=session_summary`,
  `source=AGENT`, and `collection ∈ {claude-code, codex, kiro, hermes}`, and lives in a
  separate DB — so it's trivially distinct from your authored docs/notes.

---

## Quickstart (humans)

> Prereqs: clone the repo and `uv sync` (see the README *Install* section).
> Commands below assume `mintmory` is on your PATH — otherwise prefix each with
> `uv run` (e.g. `uv run mintmory history backfill`).

```bash
# 1. Install with the local embedder (optional but better recall)
uv sync --extra local

# 2. Index everything (first run; reads ~/.claude, ~/.codex, Kiro)
mintmory history backfill

# 3. Ask "what changed ~2 months ago in mintkey?"
mintmory history timeline --since 2m --repo mintkey

# 4. Topic recall
mintmory history search "kong jwt injection"

# 5. Keep it current later (cheap; only re-reads changed sessions)
mintmory history sync
```

---

## CLI reference

| Command | What it does |
|---|---|
| `mintmory history backfill [--source claude_code\|codex\|kiro\|hermes] [--limit N] [--db PATH]` | Index all sessions (idempotent — safe to re-run). |
| `mintmory history sync [--source …] [--db PATH]` | Incremental refresh: skips unchanged session files. |
| `mintmory history timeline [--since 2m \| --from ISO --to ISO] [--repo R] [--kind K] [--limit N]` | Dated changelog window, newest-first. |
| `mintmory history search QUERY [--repo R] [--since 90d] [--limit N]` | Hybrid (keyword+vector) search over session summaries. |
| `mintmory history scrub [--db PATH]` | Audit the store for any residual secrets (exit ≠ 0 if found). |

**`--since` grammar:** `Nd` days, `Nw` weeks, `Nm` months (30d), `Ny` years.
Mutually exclusive with `--from/--to`. Default window is 90 days.
**`--kind`:** one of `fix, feature, refactor, investigation, chore, docs, incident`.
The v1 deterministic distiller is conservative and defaults to `investigation`, so
`--kind fix` may return fewer rows than you expect (the LLM distiller, when wired,
classifies more precisely).

---

## For agents (MCP)

Register the **read-only** history server once; it's then available in every
project (`--scope user`):

```bash
claude mcp add agent-history --scope user \
  -- uv run --project /ABSOLUTE/PATH/TO/mint-mory mintmory-history-mcp
```

The server advertises three tools (and **only** these — it cannot write anything):

| Tool | Use it for |
|---|---|
| `history_timeline(since="2m", repo?, kind?, from_date?, to_date?, limit?)` | "What changed / was fixed in the last N days/weeks/months" (the headline query). |
| `history_search(query_text, repo?, since?, limit?)` | Topic recall across all past sessions. |
| `history_stats()` | Counts by source + kind, and earliest/latest dates. |

Each result is a dated session summary with `repo`, `kind`, `agent`, and a
`source_path` back-link. Example agent prompt: *"Use history_timeline with
since='2m' and repo='mintkey' to find what I fixed there two months ago."*

> Other clients (Cursor, etc.) don't inherit Claude's user scope — add the same
> `command`/`args` to their own `mcp.json`. See [`agent-history-mcp.md`](agent-history-mcp.md).

---

## How-to recipes

- **"What did I ship last week?"** → `mintmory history timeline --since 1w`
- **"All fixes in a repo this quarter"** → `mintmory history timeline --since 3m --repo myapp --kind fix`
- **"Find that session about the Kong JWT bug"** → `mintmory history search "kong jwt" --since 6m`
- **"A specific date range"** → `mintmory history timeline --from 2026-04-01 --to 2026-04-30`
- **"Re-read the original transcript"** → copy the `source_path` from a result and open it.
- **"Index only one tool"** → `mintmory history backfill --source codex` (or `--source hermes` for Hermes sessions)
- **"What's even in here?"** → the `history_stats` MCP tool, or a quick SQL count
  (see *Inspect the store directly* under Debugging).

---

## Debugging & troubleshooting

| Symptom | Cause → Fix |
|---|---|
| **`mintmory: command not found`** | You're not in the synced repo / `mintmory` isn't on PATH. Run from the cloned repo, or prefix with `uv run` (`uv run mintmory history …`). |
| **`history timeline` shows nothing** | Not indexed yet, or wrong window. Run `mintmory history backfill`, then widen `--since` (e.g. `--since 2y`). Confirm rows exist with the SQL count below (or the `history_stats` MCP tool). |
| **Results look out of date** | The index is a snapshot. Run `mintmory history sync` to pull in new/changed sessions before querying. |
| **`ImportError: sentence-transformers` / weak search** | The `local` embedder isn't installed. Run `uv sync --extra local` (the default hashing embedder works too, but recall is weaker). |
| **Summaries start with `Asked: <local-command-caveat>…`** | Known v1 cosmetic limitation of the *deterministic* distiller (it grabbed a system wrapper as the prompt). Wire an LLM tier (`MINTMORY_LLM_*`) to enable the LLM distiller — dates/repos/search are unaffected. |
| **A repo shows as `unknown` or the wrong name** | The session's `cwd` wasn't a git repo, or it ran in a worktree. The summary still indexes; repo attribution is best-effort. |
| **`HermesGuardError: … resolves to the working store`** | The DB you selected resolves to `hermes.db`/`memories.db`/`$MINTMORY_DB` — refused by design. The **CLI** picks the DB via `--db` only; the **MCP server** picks it via `MINTMORY_HISTORY_DB` (or its `--db`). They are not interchangeable. Use a distinct file (default `~/.mintmory/agent-history.db`). |
| **Codex sessions look missing** | Sessions imported from another agent whose original file still exists are skipped (indexed via that agent instead, to avoid double-counting). Orphaned imports (original deleted) are kept. |
| **Re-running backfill seems to "rewrite" everything** | The per-session write is idempotent on `session_id` (no duplicates). The report's `written` counter is informational; check real counts with the SQL below (or the `history_stats` MCP tool). |
| **Worried about leaked secrets** | Run `mintmory history scrub` — it re-scans every stored summary and exits non-zero if anything slipped past redaction. The DB is `chmod 600`; keep it out of off-machine backups. |
| **MCP tools don't appear in my agent** | Re-add with `--scope user`, confirm `mintmory-history-mcp` is on PATH (`uv run --project … mintmory-history-mcp --help`), and that the `--project` path is absolute and valid. |
| **MCP server won't start** | It runs the Hermes guard on startup — check `MINTMORY_HISTORY_DB` isn't the working store. Test directly: `MINTMORY_HISTORY_DB=~/.mintmory/agent-history.db uv run --project … mintmory-history-mcp`. |

**Inspect the store directly** (read-only SQL):
```bash
sqlite3 ~/.mintmory/agent-history.db \
  "SELECT json_extract(metadata,'\$.collection') AS src, count(*) FROM memories GROUP BY src;"
```

---

## Privacy & safety

- The history DB is created `chmod 600` and lives in `~/.mintmory/` (outside any
  repo). **Keep it out of cloud-synced/off-machine backups** — it is your agents'
  transcript exhaust even after redaction.
- Redaction is over-eager by design (false positives are safe). Run
  `mintmory history scrub` after a backfill to confirm a clean store.
- Hermes / your working memory store is **never** touched by `history` commands.
