# Tasks: spans and metrics on the slow paths (OpenTelemetry, part 2 of 4)

Requires `add-telemetry-runtime` (`init_telemetry(span_exporter=, metric_reader=)`, `reset_telemetry()`, the root
`conftest.py` reset). Tests use `InMemorySpanExporter` and `InMemoryMetricReader` with
`pytest.importorskip("opentelemetry.sdk")`, and `monkeypatch.setenv("COLUMNS", "200")` for CLI output. No new
dependencies. Each test first, failing. Every helper is a cheap no-op when `telemetry.is_enabled()` is False.

## 1. Helpers (`telemetry.py`)
- [ ] 1.1 Tests for the helpers on and off, including `run_in_context` used by four threads at once.
- [ ] 1.2 `search_phase(name, *, span=True)`: context manager yielding an object with `set_count(n)`; times the block
  (`time.perf_counter()`), opens `mintmory.search.<name>` when `span`, sets `mintmory.result_count`, records
  `mintmory.search.latency_ms` (`phase=name`, histogram `unit="ms"`, pass `unit` through `_instrument`) in a `finally`;
  on an exception the span gets status ERROR and `error.type` = the class name, and the exception propagates
  (messages are scrubbed at export by part 1, for this span, the existing `traced`/`span` helpers and library spans). `timed_phase(name)`: the same as a
  decorator with `span=False`.
- [ ] 1.3 `run_in_context(fn)`: `ctx = contextvars.copy_context()` on the calling thread, returns a callable running
  `ctx.copy().run(fn, *a, **kw)` (one `Context` cannot be entered by two threads at once).
- [ ] 1.4 `set_attributes(**attrs)` on the current span; `counts_added(fn)`: a decorator that, after `fn` returns a
  record, calls `add_count("mintmory.memories.added", category=<record.category value>)` and sets
  `fn.__mintmory_counter__ = "mintmory.memories.added"` on the wrapper.

## 2. Search (shared path)
- [ ] 2.1 Tests for "Search phase spans and latency" (SQLite, and Postgres per its scenario: `PostgresBackend(...)`
  with every method `search` calls that touches the database patched on the instance) and "Search phases without
  work or with a failure"; a note added with anchoring records no `mintmory.search.*` span or point.
- [ ] 2.2 In `hybrid_search.py` add `collect_scores(*, fts_fn, trigram_fn, vector_fn)` that calls each inside
  `search_phase("fts"|"substring"|"vector")` and `set_count(len(result))` (0 for empty) and returns the three dicts.
  Both backends' `search` call it with lambdas over their `_fts_scores`, `_trigram_scores`, `_vector_scores` (do not
  decorate those: `anchor_candidates` calls them directly, not through `collect_scores`, so note anchoring records no
  phase; `search_around` runs no score stage). Inside `fuse_and_search` open `search_phase("fusion")` around
  the body and `set_count(len(response.memories))`. Decorate both backends' `search` with `@telemetry.timed_phase("total")`
  under the existing `@telemetry.traced("mintmory.search")`, and both `search_around` with `@telemetry.timed_phase("graph")`.

## 3. Embeddings (`embedder.py`)
- [ ] 3.1 Tests: "Hashing embedder is traced", `embed` (batch size 1), and `FakeEmbedder` (its `embed_batch` calls
  `embed`, the reverse of `HashingEmbedder`): one span per public call.
- [ ] 3.2 One shared decorator on `embed` and `embed_batch` of `HashingEmbedder`, `LocalEmbedder`, `OllamaEmbedder`,
  `OpenAIEmbedder`, `FakeEmbedder`, with a module `ContextVar[bool]` re-entrancy guard so the inner call records nothing;
  provider from a class attribute `provider` (add where missing), model from the instance.

## 4. CLI (`cli/main.py`)
- [ ] 4.1 Tests for "CLI commands are traced end to end" and "Indexing and conversion phases are traced" (both
  scenarios each), plus: `mintmory add` gives `mintmory.cli.add` with `mintmory.add_memory` as child; exit code 0 is
  not ERROR.
- [ ] 4.2 `telemetry.command_span(name)`: a decorator under `@app.command()` (keep `functools.wraps`; Typer follows
  `__wrapped__`) opening `mintmory.cli.<name>` with `record_exception=False, set_status_on_exception=False`; ERROR and
  `error.type` (class name) for `typer.Exit`/`SystemExit` with a non-zero code or any other exception; unset for code 0;
  re-raise. Apply to the commands of the spec; set the `index-tree` counts with `telemetry.set_attributes`.
- [ ] 4.3 `index_tree`: `mintmory.index_tree.scan` around the per-entry loop, `.prune` inside `if prune:`, `.cochange`
  inside the co-change branch, `mintmory.convert` per binary conversion, i.e. the `extract_markdown` call when `want_binary` is true (the `want_text`
  pass gets no span) (`mintmory.file.suffix`,
  `mintmory.file.size_bytes`, `mintmory.outcome`), `mintmory.vision.caption` per inline caption; `ingest`:
  `mintmory.convert` per conversion.

## 5. Worker threads, counters, privacy
- [ ] 5.1 Test "Threads stay in the trace" (fixtures of `test_history_ingest.py`; assert `report.errors == 0`).
- [ ] 5.2 `history/ingest.py` `backfill` and `sync`: wrap once, `prepare = telemetry.run_in_context(_prepare_session)`,
  submit `prepare`; spans `mintmory.history.backfill` / `.sync` with the report counts. `dreaming.py`: map
  `telemetry.run_in_context(lambda sel: summarizer(sel.concept, sel.contents))`.
- [ ] 5.3 Test "Counter by category"; put `@telemetry.counts_added` on both backends' `add_memory`.
- [ ] 5.4 Test "No content leaks into telemetry" (walk span attributes, event attributes, metric point attributes);
  review the attributes of this change and the existing `gen_ai.chat` and `dreaming.py` spans; drop any that carry text.

## 6. Checks
- [ ] 6.1 `docs/OBSERVABILITY.md` sections 4.3 and 4.4 list the spans and metrics that now exist. `ruff check`,
  `ruff format --check`, `mypy packages`, full suite with coverage at or above 80%.
