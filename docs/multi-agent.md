# Running MintMory for multiple agents

MintMory is built so several agents can share one memory. Everything ultimately
reads and writes **one SQLite file** in WAL mode (concurrent readers + a single
writer, where readers never block the writer). "Multiple agents" is really a
question of *how each agent reaches that file*. There are three supported
topologies — pick by **same machine vs networked** and **how write-heavy** the
agents are.

## TL;DR

| Scenario | Use | Transport |
|---|---|---|
| A few agents, same machine | **A — shared `.db`, one MCP per agent** | MCP (stdio) |
| Many agents / networked / non-MCP clients | **B-HTTP — one shared API server** | HTTP REST |
| Networked, but you want MCP semantics | **B-SSE — one shared MCP server** | MCP (SSE) |
| Heavy concurrent writers | **B** (+ tune `busy_timeout`) | HTTP or SSE |

**Yes, concurrent access via MCP is supported** — both as multiple stdio MCP
processes on a shared `.db`, and as one shared SSE MCP server with many clients.

---

## Pattern A — Shared `.db` file, one MCP (stdio) per agent

Each agent runs its own `mintmory-mcp` (stdio) process, all pointed at the **same**
`MINTMORY_DB`. Each process opens the same SQLite file; WAL handles concurrency.

```jsonc
// every agent's MCP config — note the IDENTICAL MINTMORY_DB
{
  "mcpServers": {
    "mintmory": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/mint-mory", "mintmory-mcp"],
      "env": { "MINTMORY_DB": "/srv/mintmory/shared.db" }
    }
  }
}
```

- ✅ Zero infra, fully MCP-native, no server to run.
- ❌ **Same host only.** Do not place the `.db` on a network filesystem (NFS/SMB) —
  SQLite's file locking is unreliable there. For cross-machine, use Pattern B.

This is the simplest setup and is battle-tested: several agents have concurrently
read and written one shared database this way.

## Pattern B — One shared server, many clients

Run a single process that owns the database; every agent is a client of it. The
server funnels all access through one process, which is the cleanest way to
mediate concurrency for many agents (and the right choice across machines).

### B-HTTP — REST API (language-agnostic)

```bash
MINTMORY_DB=/srv/mintmory/shared.db mintmory serve --host 0.0.0.0 --port 8080
```

Agents call REST: `POST /memories`, `POST /memories/search`, `POST /notes`,
`GET /notes`, `POST /dream`, `GET /stats`, `POST /sessions/{id}/feedback`, …
Works for any HTTP-capable agent, MCP or not.

> The API ships **without built-in auth**. If it's reachable beyond localhost, put
> it behind a reverse proxy / API gateway that adds authentication and TLS.

### B-SSE — shared MCP server over the network

```bash
MINTMORY_DB=/srv/mintmory/shared.db mintmory-mcp --transport sse --port 8081
```

MCP clients connect to the one SSE endpoint and get the full MCP toolset — MCP
semantics, shared, and remote-capable.

---

## How agents discover MintMory

Discovery is standard for each transport — you don't hand-roll a protocol.

- **MCP (A / B-SSE):** discovery is automatic. On connect, the client calls
  `tools/list` and receives every tool (`memory_add`, `memory_search`,
  `memory_note`, `memory_dream`, `session_feedback`, `notes_list`, …) **with JSON
  schemas**, plus the server's `instructions` (the 8 memory categories, 12 link
  types, `search_around`, the feedback loop, dreaming). To make an agent *use it
  well*, paste the policy in [`hermes-onboarding.md`](hermes-onboarding.md) — it is
  written for **any** MCP agent (recall-first → write-durable → close-the-loop
  feedback → dream).
- **HTTP (B-HTTP):** discovery is **OpenAPI**. The running server serves Swagger UI
  at `/docs` and the machine-readable spec at `/openapi.json`; the same contract is
  committed at [`openapi/mintmory.yaml`](openapi/mintmory.yaml). Point an agent (or
  its framework's OpenAPI-to-tools loader) at that to learn every endpoint + schema.

---

## Concurrency model & tuning

- **WAL** (set automatically): many concurrent readers + one writer; readers do not
  block the writer.
- **`busy_timeout`** (default **5000 ms**): a competing writer **waits** for the
  lock instead of immediately raising `database is locked`. Override with
  `MINTMORY_SQLITE_BUSY_TIMEOUT_MS` (set `0` for the old fail-fast behaviour, or
  higher for very write-heavy fleets).
- **Single writer.** Writes serialise at the SQLite level. For mostly-read,
  bursty-write agent memory, Pattern A is fine. For many heavy writers, prefer a
  Pattern-B server so a single process orders the writes.

## Agent-owned L3 summarisation

Agents can own the L3 concept-summary step themselves — no separate LLM backend
(`MINTMORY_LLM_*`) is needed. The flow is identical across all three transports:

1. **Get the work-list.** Call `summary_jobs` (MCP), `mintmory summary-jobs`
   (CLI), or `GET /summaries/jobs` (HTTP). MintMory returns only the concepts
   that need a (re)summary — concepts with no existing summary or whose stored
   `memory_count` has drifted from the current active count.
2. **Write each summary.** The calling agent is the LLM; it synthesises the
   supplied memory snippets into a short prose summary.
3. **Store it.** Call `summary_put` (MCP), `mintmory summary-put` (CLI), or
   `PUT /summaries/{concept}` (HTTP). MintMory persists the text and records the
   current active memory count so the concept does not reappear on the next
   work-list poll.

This is especially useful in multi-agent setups where one agent (e.g. a
long-running background worker that already carries an LLM context) periodically
polls for summary work and writes summaries on behalf of the shared store — no
extra Ollama / API-key configuration on the MintMory server side. The
configured-LLM path (`memory_dream`) and the agent-supplied path coexist:
`summary_put` simply overwrites whatever `memory_dream` last stored (idempotent
upsert keyed on concept).

---

## Isolation

A shared instance is a **shared brain** — every agent sees the same store (one
agent's notes are visible to all), and there is no per-agent ACL. If you need
isolation:

- give each agent **its own `.db`** (separate `MINTMORY_DB`), or
- **scope by metadata** — stamp an owner/`collection` tag on writes and filter on
  it at read time (the `index-tree` feature already uses `collection` tags this way).
