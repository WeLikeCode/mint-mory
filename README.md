# MintMory

[![CI](https://github.com/WeLikeCode/mint-mory/actions/workflows/ci.yml/badge.svg)](https://github.com/WeLikeCode/mint-mory/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)

**Typed, graph-linked, self-consolidating memory for LLM agents — in a single SQLite file.**

MintMory gives an agent a long-term memory that is *typed* (every memory has a
category), *linked* (memories connect through a concept graph), *searchable*
(hybrid keyword + substring + vector), and *self-improving* (a background
"dreaming" pass consolidates, links, summarises, and resolves contradictions).
It is local-first and dependency-light: no external vector database, no required
model downloads, no cloud. One `.db` file holds everything.

The data model is inspired by the Palantir Foundry Ontology: knowledge is most
useful when it is typed, linked, and queryable — not stored as opaque blobs.

---

## Highlights

- **Benchmarked head-to-head.** MintMory's generic hybrid search matches or beats
  the purpose-built [mempalace](https://github.com/mempalace/mempalace) across all
  four of its agent-memory benchmarks (LongMemEval, LoCoMo, ConvoMem, MemBench) —
  same embedder, zero benchmark-specific tuning, one SQLite file. Numbers +
  one-command reproduction: **[BENCHMARKS.md](BENCHMARKS.md)**.
- **One core, three transports.** The same domain logic is exposed as a **CLI**
  (Typer), an **MCP server** (for Claude Code, Cursor, Open WebUI, …), and an
  **HTTP API** (FastAPI).
- **Hybrid search.** FTS5 keyword (BM25) + FTS5 **trigram substring** + optional
  **vector** similarity, fused with Reciprocal Rank Fusion and relevance-normalised.
- **Pure-Python by default.** The default embedder is an in-process feature-hashing
  embedder — no PyTorch, no network. Swap in `sentence-transformers`, Ollama, or
  OpenAI embeddings via an extra when you want them.
- **Typed ontology.** 8 memory categories and 12 typed concept-link relationships.
- **Dreaming.** Idempotent background consolidation: anomaly detection, concept
  linking (hub-aware pruning), LLM summaries, contradiction resolution, archival,
  rehabilitation. The LLM tier is optional and off by default.
- **Agent-supplied summaries.** An alternative to the LLM-backed dreaming path:
  call `summary_jobs` (MCP / CLI / HTTP) to get the concepts that need
  summarising, write each summary yourself (you are the LLM), and send it back
  with `summary_put`. No `MINTMORY_LLM_*` backend required — works with
  `MINTMORY_LLM_PROVIDER=none`.
- **Agent-supplied image understanding (G5).** Close the image-description gap
  without a vision backend: call `image_jobs` to get the indexed raster images
  that still need a description, look at each (via its `path` or inline base64
  for online-only files), write one combined description blob, and store it with
  `image_caption_put`. SVG text is extracted automatically (pure-Python, no model).
  Proprietary formats (`.psd`, `.xd`, …) remain metadata-only. Optional `[image]`
  / `[ocr]` extras; `ocr` is a future stub.
- **Automated LLM vision captioning.** Set `MINTMORY_VISION_PROVIDER=llm` to
  caption raster images server-side via an OpenAI-compatible vision model (Ollama
  `llava`, LM Studio, hosted endpoint). `index-tree --vision` then captions inline
  during the walk; `mintmory vision-run` / `vision_run` (MCP) /
  `POST /images/caption-run` (HTTP) caption already-indexed pending images without
  re-walking. No new required dependency — reuses stdlib `urllib` from `core/llm.py`.
  `agent` stays the default (zero behaviour change). `ocr` stays a stub.
- **Personal notes.** First-class user-authored "remember this" notes that are
  authoritative, anchorable to other memories, time-aware, and protected from
  auto-archival.
- **Document & folder ingestion.** Bulk-ingest files (PDF/DOCX/XLSX/PPTX via the
  optional `docs` extra) and recurrently index a directory tree — including
  cloud/online-only folders, indexed by metadata without downloading.
- **Agent history index.** Index your **Claude Code / Codex / Kiro** chat history
  into a separate, secret-redacted changelog and ask *"what did I fix/add ~2 months
  ago?"* via the `mintmory history` CLI or the read-only `mintmory-history-mcp`
  server — fully isolated from your working store. Guide: **[agent-history.md](docs/agent-history.md)**.
- **Single file.** SQLite + `sqlite-vec` + FTS5. Back it up by copying one file.

---

## Install

MintMory uses [uv](https://docs.astral.sh/uv/). Clone and sync:

```bash
git clone https://github.com/WeLikeCode/mint-mory.git
cd mint-mory
uv sync                 # core + CLI + MCP + API
uv sync --extra docs    # optional: PDF/DOCX/XLSX/… ingestion (markitdown)
uv sync --extra local   # optional: local sentence-transformers embeddings
```

Requires Python 3.12+.

---

## Quickstart

### CLI

```bash
export MINTMORY_DB=~/.mintmory/memories.db

mintmory add "The parking integration uses OAuth PKCE" --category fact
mintmory note "Remember the prod gateway rotates certs monthly" --about "gateway"
mintmory search "oauth gateway"
mintmory ingest ./docs --glob "*.md,*.pdf,*.docx"     # bulk ingest (needs the docs extra for binaries)
mintmory dream --full                                  # consolidate
mintmory doctor                                        # one-shot health check
```

### MCP (e.g. Claude Code / Cursor)

```jsonc
{
  "mcpServers": {
    "mintmory": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/mint-mory", "mintmory-mcp"],
      "env": { "MINTMORY_DB": "/path/to/your/memories.db" }
    }
  }
}
```

Tools exposed: `memory_add`, `memory_search`, `memory_get`, `memory_archive`,
`memory_stats`, `memory_dream`, `session_feedback`, `summary_list`,
`summary_get`, `summary_jobs`, `summary_put`, `memory_note`, `notes_list`,
`image_jobs`, `image_caption_put`, `vision_run`.

### HTTP API

```bash
mintmory serve --port 8080      # FastAPI + OpenAPI docs at /docs
```

### Multiple agents, one memory

Several agents can share one MintMory instance — either as **one MCP process per
agent against a shared `.db`** (same machine), or as **a single shared server**
(HTTP REST or MCP-over-SSE) for networked / many-agent setups. Concurrent access
via MCP is supported in both forms. See **[`docs/multi-agent.md`](docs/multi-agent.md)**
for the topologies, discovery, and concurrency tuning.

---

## Architecture

```
        CLI (Typer)        MCP (FastMCP)        HTTP (FastAPI)
              \                  |                   /
               \                 |                  /
                =========  mintmory.core  =========
                 types · storage · search · dreaming
                 embedder · scoring · notes · config
                              |
                   one SQLite .db file
            (sqlite-vec + FTS5 porter + FTS5 trigram)
```

- **Storage:** a single SQLite database. Vectors via `sqlite-vec`; keyword search
  via FTS5 (`porter`); substring search via a second FTS5 (`trigram`) index.
- **Search:** keyword (BM25) + trigram substring + optional vector, fused with RRF,
  relevance min-max normalised, then nudged by usefulness/recency.
- **Dreaming:** six idempotent steps run on demand (`mintmory dream`) — safe to run
  repeatedly; the LLM-backed steps are skipped when no LLM tier is configured.

See [`AGENTS.md`](AGENTS.md) for the deep design contract and
[`docs/`](docs/) for ADRs, the OpenAPI spec, and experiment records.

---

## Configuration

Everything is environment-driven (pydantic-settings); **every default reproduces
sensible local-first behaviour**. Common knobs:

| Variable | Default | Meaning |
|---|---|---|
| `MINTMORY_DB` | `~/.mintmory/memories.db` | database path |
| `MINTMORY_EMBED_PROVIDER` | `hashing` | `hashing` (pure-Python) / `local` / `ollama` / `openai` |
| `MINTMORY_LLM_PROVIDER` | `none` | enable summaries + contradiction resolution (`ollama`/`openai`) |
| `MINTMORY_LLM_BASE_URL` / `_MODEL` / `_API_KEY` | — | OpenAI-compatible LLM tier |
| `MINTMORY_NOTE_BONUS` | `0.05` | ranking boost for user notes |
| `MINTMORY_SQLITE_BUSY_TIMEOUT_MS` | `5000` | how long a writer waits for a lock (multi-agent); `0` = fail fast |

The LLM tier is OpenAI-compatible, so it works with Ollama, LM Studio, vLLM, or a
hosted endpoint. It is **off by default** (fully offline).

**Agent-supplied summaries** do not require an LLM tier. Use
`mintmory summary-jobs` / `summary_jobs` (MCP) / `GET /summaries/jobs` to get
the pending L3 summary work-list, write the text, and return it with
`mintmory summary-put` / `summary_put` / `PUT /summaries/{concept}`. The
selection policy (`MINTMORY_SUMMARY_*` settings, stoplist) is respected
regardless of which path writes the summary.

---

## Image Understanding (agent-supplied and automated vision, G5)

MintMory supports two vision paths — agent-supplied (default) and automated
server-side (`llm`). Both use the same persistence layer (`image_caption_put`,
the `image_jobs` work-list, the no-drift guarantee) and the same `[image]` extra
for optional Pillow downscaling.

### Agent-supplied path (default, `provider=agent`)

The agent that already holds the image in context is the vision capability. The
loop works identically over all three transports:

1. **Index the tree.** Run `mintmory index-tree --vision /path/to/folder`. SVG files
   have their embedded `<text>` / `<title>` / `<desc>` content extracted automatically
   (pure stdlib, no model). Raster images (`.jpg`, `.png`, `.gif`, `.webp`, …) are
   queued as agent jobs and recorded in the manifest with `index_mode=vision`.
   Proprietary formats (`.xd`, `.vsdx`, `.psd`, …) are skipped and flagged
   (`vision-skipped`) — they remain metadata-only.

2. **Get the work-list.** Call `image_jobs` (MCP), `mintmory image-jobs` (CLI), or
   `GET /images/jobs` (HTTP). Only raster images that do NOT yet have an active
   description are returned by default (`include_all=False`). Each job carries the
   `file_id`, `path`, `rel`, `mime`, `size`, and `online_only` flag. For
   online-only (cloud-placeholder) images, or when `include_bytes=True`, the
   response also includes an inline base64 `image_b64` payload within the configured
   size cap (`MINTMORY_VISION_MAX_IMAGE_MB`, default 8 MB); oversized images set
   `oversized=True` and omit the payload so the agent can fall back to `path`.

3. **Describe each image.** You (the calling agent) are the vision-capable model.
   Write one combined description blob: what the image depicts plus any legible text.

4. **Store the description.** Call `image_caption_put` (MCP), `mintmory
   image-caption-put` (CLI), or `PUT /images/{file_id}` (HTTP). MintMory persists
   the description as a searchable `context` memory ANNOTATES-linked to the image
   file-record and archives any prior description (no-drift: the image drops from the
   default `image_jobs` work-list immediately).

**No vision backend is required for the `agent` path** — it is the default.

### Automated LLM vision path (`MINTMORY_VISION_PROVIDER=llm`)

Set `MINTMORY_VISION_PROVIDER=llm` to caption raster images automatically via an
OpenAI-compatible vision model (e.g. Ollama `llava`, LM Studio, a hosted endpoint).

**Inline during indexing** — `mintmory index-tree --vision /path/to/folder`
captions each raster as it is encountered (instead of queuing an agent job).
Per-image failures (network/timeout/empty response) are logged and skipped; one
bad image never aborts the walk.

**Caption already-indexed images** (without re-walking the tree):

```bash
mintmory vision-run                      # CLI — describes pending images
mintmory vision-run --limit 20           # cap to 20 images
mintmory vision-run --budget 100         # 100 MB download budget for online-only
mintmory vision-run --all                # re-caption ALL images (not just pending)
```

Or via MCP: call `vision_run` (with optional `limit`, `budget_mb`, `include_all`).
Or via HTTP: `POST /images/caption-run` (body: `{"limit":0,"budget_mb":0,"include_all":false}`).

With `provider=agent` (the default), `vision-run` / `vision_run` /
`POST /images/caption-run` are no-ops (they return `{"provider":"agent","described":0}`)
— zero behaviour change unless you opt in.

**No new required dependency.** The vision HTTP call reuses the stdlib `urllib`
machinery already in `core/llm.py` (OpenAI-compatible `/chat/completions` shape
with a multimodal `image_url` content part). No `openai` SDK.

**Optional extras:**

```bash
uv sync --extra image   # Pillow: auto-downscale large embedded payloads (lazy import)
uv sync --extra ocr     # pytesseract: reserved for the future 'ocr' vision provider
```

**Relevant env knobs** (`MINTMORY_VISION_*`):

| Variable | Default | Meaning |
|---|---|---|
| `MINTMORY_VISION_PROVIDER` | `agent` | `agent` (default) / `llm` (automated server-side) / `ocr` (stub, future) |
| `MINTMORY_VISION_BASE_URL` | `http://localhost:11434/v1` | Base URL for the vision model endpoint (`llm` path only) |
| `MINTMORY_VISION_MODEL` | `llava` | Vision model name (`llm` path only) |
| `MINTMORY_VISION_API_KEY` | — | Bearer API key for the vision endpoint (omitted if not set) |
| `MINTMORY_VISION_VISION_MAX_TOKENS` | `512` | Max tokens in the caption response (`llm` path only) |
| `MINTMORY_VISION_VISION_TIMEOUT_S` | `120.0` | Per-image HTTP timeout in seconds (1–600; `llm` path only) |
| `MINTMORY_VISION_VISION_TEMPERATURE` | `0.0` | Sampling temperature for the vision model (0.0–2.0; `llm` path only) |
| `MINTMORY_VISION_VISION_PROMPT` | `""` | Override the default caption prompt (empty = use built-in default) |
| `MINTMORY_VISION_MAX_IMAGE_MB` | `8.0` | Max on-disk size to embed as base64 (0 = no cap) |
| `MINTMORY_VISION_DOWNSCALE_MAX_PX` | `1568` | Longest-edge downscale target for embedded payloads (needs `[image]`; 0 = off) |
| `MINTMORY_VISION_MAX_DOWNLOAD_MB` | `200.0` | Budget for downloading online-only image bytes (shared with `--max-download-mb`) |

---

## Agent history (`mintmory history`)

Index your coding agents' chat history (Claude Code, Codex, Kiro) into a separate,
secret-redacted, time-aware changelog so you can recall *what was fixed or added,
when* — without polluting your working memory store.

```bash
uv sync --extra local                          # better recall (optional)
mintmory history backfill                       # index all sessions (idempotent)
mintmory history timeline --since 2m --repo X   # "what changed ~2 months ago in X"
mintmory history search "kong jwt"              # topic recall
mintmory history sync                           # keep current (incremental)
mintmory history scrub                          # audit for residual secrets
```

For agents, expose the **read-only** MCP server (tools: `history_timeline`,
`history_search`, `history_stats`) in every project:

```bash
claude mcp add agent-history --scope user \
  -- uv run --project /ABSOLUTE/PATH/TO/mint-mory mintmory-history-mcp
```

Full guide (humans + agents, how-to, debugging): **[docs/agent-history.md](docs/agent-history.md)**.
MCP setup specifics: [docs/agent-history-mcp.md](docs/agent-history-mcp.md).

---

## Development

```bash
uv run pytest          # tests (coverage gate ≥ 80%)
uv run ruff check .    # lint
uv run ruff format .   # format
uv run mypy packages   # strict type-check
```

Changes are designed spec-first under [`openspec/`](openspec/): each change has a
`proposal.md`, a frozen `design.md`, `tasks.md`, and capability spec deltas. See
[`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## License

[MIT](LICENSE).
