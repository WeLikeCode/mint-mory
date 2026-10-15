# Change: spans and metrics on MintMory's slow paths, so a trace shows where the time goes (OpenTelemetry, part 2 of 4)

## Why

With part 1 (`add-telemetry-runtime`) every entry point exports to a collector. What it exports is still thin.
A search is one `mintmory.search` span; you cannot see whether the full-text, substring, vector or fusion stage is
slow. Embedding calls, document conversion, `index-tree`, the history backfill and its LLM distillation have no
spans. The metrics planned in `docs/OBSERVABILITY.md` section 4.4 (`mintmory.search.latency_ms` by phase,
`mintmory.embed.latency_ms`, `mintmory.memories.added`) do not exist. And the history backfill runs sessions in
a `ThreadPoolExecutor` (`packages/core/src/mintmory/core/history/ingest.py`, `backfill`), which drops the trace
context, so the LLM calls made there start new, unconnected traces.

## What changes

- Search: child spans `mintmory.search.fts`, `mintmory.search.substring`, `mintmory.search.vector` and
  `mintmory.search.fusion` in both storage backends, and the histogram `mintmory.search.latency_ms` with the
  attribute `phase` (`fts`, `substring`, `vector`, `fusion`, `graph`, `total`). They are measured in code shared by
  both backends (`hybrid_search.collect_scores`), so the SQLite tests exercise the Postgres path too, and note
  anchoring, which reuses the score functions, does not count as search.
- Embeddings: a `mintmory.embed` span and the histogram `mintmory.embed.latency_ms` for every embedder call.
- Long CLI commands get a root span (`mintmory.cli.<command>`), `index-tree` with its outcome counts; `index-tree` gets phase
  spans (`scan`, `prune`, `cochange`) and spans for each document conversion and image caption; `ingest` gets a span
  per conversion; the history backfill and sync, and the dream's concurrent summaries, keep the trace context in
  their worker threads (a fresh context copy per task).
- Counters: `mintmory.memories.added` (by category).
- A privacy rule with a test: telemetry carries counts, sizes, categories, phases and model names, never memory
  text, note text, query text, prompts, completions or file contents.

## Non-goals

HTTP, MCP and outbound trace propagation (part 3); the local collector stack and documentation (part 4);
database-driver spans; per-row or per-file spans for cheap work (a plain file stat or a text read gets none).

## Impact

- Code: `packages/core/src/mintmory/core/telemetry.py` (a phase helper), `storage.py`, `storage_postgres.py`,
  `hybrid_search.py`, `embedder.py`, `history/ingest.py`, `conversion.py` call sites, and
  `packages/cli/src/mintmory/cli/main.py` (command spans).
- Depends on `add-telemetry-runtime` (the test seam `init_telemetry(..., span_exporter=..., metric_reader=...)`).
- Overhead when telemetry is off: none beyond the existing no-op checks.
