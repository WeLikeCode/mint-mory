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
- **Personal notes.** First-class user-authored "remember this" notes that are
  authoritative, anchorable to other memories, time-aware, and protected from
  auto-archival.
- **Document & folder ingestion.** Bulk-ingest files (PDF/DOCX/XLSX/PPTX via the
  optional `docs` extra) and recurrently index a directory tree — including
  cloud/online-only folders, indexed by metadata without downloading.
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
`summary_get`, `memory_note`, `notes_list`.

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
