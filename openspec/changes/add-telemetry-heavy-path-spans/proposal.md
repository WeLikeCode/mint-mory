# Change: spans and metrics on MintMory's slow paths, so a trace shows where the time goes (OpenTelemetry, part 2 of 4)

## Why

Part 1 (`add-telemetry-runtime`) makes telemetry safe to turn on, and `add-telemetry-entry-points` makes every entry
point initialise it. What MintMory exports is still thin. A search is one `mintmory.search` span; you cannot see
whether the full-text, substring, vector or fusion stage is slow. Embedding calls, document conversion, `index-tree`,
the history backfill and its LLM distillation have no spans. The metrics planned in `docs/OBSERVABILITY.md` section 4.4
(`mintmory.search.latency_ms` by phase, `mintmory.embed.latency_ms`, `mintmory.memories.added`) do not exist. And the
history backfill runs sessions in a `ThreadPoolExecutor` (`packages/core/src/mintmory/core/history/ingest.py`,
`backfill`, and `sync` likewise), which drops the trace context, so the LLM calls made there start new traces.

## What changes

- Search: child spans `mintmory.search.fts`, `.substring`, `.vector`, `.fusion` in both storage backends, and the
  histogram `mintmory.search.latency_ms` by `phase` (`fts`, `substring`, `vector`, `fusion`, `graph`, `total`),
  measured in code shared by both backends (`hybrid_search.collect_scores`); note anchoring does not count as search.
- Embeddings: a `mintmory.embed` span and the histogram `mintmory.embed.latency_ms` for every embedder call.
- CLI root spans (`mintmory.cli.<command>`); `index-tree` counts, phases (`scan`, `prune`, `cochange`), conversion and
  inline caption spans; `ingest` conversion spans; worker threads (history, dream summaries) keep the trace context.
- Counters: `mintmory.memories.added` (by category).
- A privacy rule with sentinel tests (content, notes, prompts, completions, concept names, header values, files).
- Failures use part 1's `mark_error`; telemetry never raises into the caller.

## Non-goals

HTTP, MCP and outbound trace propagation (part 3); the local collector stack and documentation (part 4);
database-driver spans; per-row or per-file spans for cheap work (a plain file stat or a text read gets none).

## Impact

- Code: `telemetry.py` (phase, command and context helpers), `storage.py`, `storage_postgres.py`, `hybrid_search.py`,
  `embedder.py`, `history/ingest.py`, `dreaming.py`, and `packages/cli/src/mintmory/cli/main.py`.
- Depends on `add-telemetry-runtime` (test seam, `mark_error`), `fix-cochange-tools-on-postgres` and
  `add-recurrent-tree-indexing` (both edit `index_tree`). Not on `add-telemetry-entry-points`: the tests initialise
  telemetry themselves, and in `cli/main.py` this unit edits command bodies, not the callback that unit adds.
- Overhead when telemetry is off: none beyond the existing no-op checks.
