# Tasks: spans and metrics on the slow paths (OpenTelemetry, part 2 of 4)

Requires `add-telemetry-runtime` (inject both `span_exporter` and `metric_reader`: one alone turns the other signal
off; `mark_error`; the root `conftest.py` reset). Tests use the in-memory exporter and reader with
`pytest.importorskip("opentelemetry.sdk")`, `COLUMNS=200` for CLI output, and initialise telemetry themselves (an
entry-point init after that is a no-op). No new dependencies. Each test first, failing. Every helper is a no-op when
`telemetry.is_enabled()` is False and wraps its metric and attribute calls in `try/except Exception`.

## 1. Helpers (`telemetry.py`)
- [x] 1.1 Tests for "Span kind, parent context and exception options", the helpers on and off, `run_in_context`
  with four threads at once.
- [x] 1.2 `span()` options (here because `command_span` needs the flags; `add-telemetry-boundary-tracing` uses all
  four): `span(name, *, kind="internal", context=None, record_exception=True, set_status_on_exception=True, **attrs)`,
  `kind` typed `Literal["internal", "server", "client"]` and mapped by `{"internal": SpanKind.INTERNAL, "server":
  SpanKind.SERVER, "client": SpanKind.CLIENT}.get(kind, SpanKind.INTERNAL)`; all four passed to
  `_tracer.start_as_current_span`. No `staging` caller passes an attribute with these names (`step=` in
  `dreaming.py`, `gen_ai.*`/`prompt_chars` in `llm.py`). `_NoopSpan.update_name(name)`: a no-op.
- [ ] 1.3 `search_phase(name, *, span=True)`: context manager yielding an object with `set_count(n)`; times the block
  (`time.perf_counter()`), opens `mintmory.search.<name>` when `span`, sets `mintmory.result_count`, records
  `mintmory.search.latency_ms` (`phase=name`, histogram `unit="ms"`, pass `unit` through `_instrument`) in a `finally`;
  on an exception calls `mark_error(span, type(exc).__name__)` and re-raises. `timed_phase(name)`: the same as a
  decorator with `span=False`.
- [ ] 1.4 `run_in_context(fn)`: `ctx = contextvars.copy_context()` on the calling thread, returns a callable running
  `ctx.copy().run(fn, *a, **kw)` (one `Context` cannot be entered by two threads at once).
- [ ] 1.5 `set_attributes(**attrs)` on the current span; `counts_added(fn)`: after `fn` returns a record, calls
  `add_count("mintmory.memories.added", category=record.category.value)` and sets
  `fn.__mintmory_counter__ = "mintmory.memories.added"` on the wrapper.

## 2. Search (shared path)
- [ ] 2.1 Tests for "Search phase spans and latency" (SQLite; Postgres per its scenario: `PostgresBackend(...)` with
  every method `search` calls that touches the database patched on the instance) and "Span helpers without work or
  with a failure"; a note added with anchoring records no `mintmory.search.*` span or point.
- [ ] 2.2 `hybrid_search.collect_scores(*, fts_fn, trigram_fn, vector_fn) -> tuple[dict[str, float], dict[str, float],
  dict[str, float]]` (zero-argument callables; returns `(fts, trigram, vector)`): each call inside
  `search_phase("fts"|"substring"|"vector")` with `set_count(len(result))` (substring search off means `_trigram_scores`
  returns `{}`, count 0). Both backends' `search` (`storage.py` and `storage_postgres.py`) call it with lambdas over
  `_fts_scores`, `_trigram_scores`, `_vector_scores` (do not decorate those: `anchor_candidates` calls them directly,
  so note anchoring records no phase). In `fuse_and_search`, `search_phase("fusion")` around the body and
  `set_count(len(response.memories))`. Both `search` get `@telemetry.timed_phase("total")` under the existing
  `@telemetry.traced("mintmory.search")`; both `search_around` get `@telemetry.timed_phase("graph")`.

## 3. Embeddings (`embedder.py`)
- [ ] 3.1 Tests: "Hashing embedder is traced", `embed` (batch size 1), and `FakeEmbedder` (its `embed_batch` calls
  `embed`): one span per public call.
- [ ] 3.2 One shared decorator on `embed` and `embed_batch` of `HashingEmbedder`, `LocalEmbedder`, `OllamaEmbedder`,
  `OpenAIEmbedder`, `FakeEmbedder`, with a module `ContextVar[bool]` re-entrancy guard; class attribute `provider`
  (`hashing`, `local`, `ollama`, `openai`, `fake`); model from `self.model_name`.

## 4. CLI (`cli/main.py`)
- [ ] 4.1 Tests for "CLI commands are traced end to end" and "Indexing and conversion phases are traced" (every
  scenario, "Exit code 0 is not an error" included), plus: `mintmory add` gives `mintmory.cli.add` with
  `mintmory.add_memory` as child. The co-change scenarios need no `importorskip("sklearn")` (fallback path).
- [ ] 4.2 `telemetry.command_span(name)`: a decorator under `@app.command()` (keep `functools.wraps`; Typer follows
  `__wrapped__`) opening `mintmory.cli.<name>` through `telemetry.span(..., record_exception=False,
  set_status_on_exception=False)` (task 1.2; `typer.Exit` is a `RuntimeError`, so the defaults would mark exit 0);
  `mark_error(span, type(exc).__name__)` for `typer.Exit`/`SystemExit` with a non-zero code or any other exception;
  re-raise. Set the `index-tree` counts with `telemetry.set_attributes`.
- [ ] 4.3 `index_tree` (locate by name; `add-recurrent-tree-indexing` adds `text_candidate` but keeps `text_eligible`,
  `want_binary` and the single `extract_markdown` call): `mintmory.index_tree.scan` around `for root in roots:`;
  `.prune` inside `if prune:`; `.cochange` inside `if run_cochange and len(changed_docs) >= 2:` around the `try` (set
  `mintmory.outcome=unavailable` in the `except CoChangeUnavailable` branch); `mintmory.convert` around
  `extract_markdown(...)` in `if do_content:` only when `want_binary` (`contextlib.nullcontext()` otherwise);
  `mintmory.vision.caption` around `captioner.describe(...)` in the raster `else` branch where `captioner is not None`.
  `ingest`: `mintmory.convert` around its `extract_markdown(...)` call. The span helper sets `mintmory.outcome=ok`, or
  `failed` plus `mark_error` when the call raises; the existing `ConversionError`/`VisionError` handlers still count it.

## 5. Worker threads, counters, privacy
- [ ] 5.1 Test "Threads stay in the trace" (the test opens `root-a` / `root-b` with `telemetry.span`).
- [ ] 5.2 `history/ingest.py` `backfill` and `sync` (each has its own `ThreadPoolExecutor`): `prepare =
  telemetry.run_in_context(_prepare_session)` once, submit `prepare` (the `mintmory.cli.history.*` root spans cover the
  commands; no extra history span). `dreaming.py` `generate_summaries`: `pool.map(telemetry.run_in_context(lambda sel:
  summarizer(sel.concept, sel.contents)), prepared)`.
- [ ] 5.3 Test "Counter by category"; `@telemetry.counts_added` on both `add_memory`.
- [ ] 5.4 Tests of "Telemetry carries no content" (walk span names, span and event attributes, status descriptions,
  metric point attributes); the LLM test server is a `ThreadingHTTPServer` on `127.0.0.1:0`.

## 6. Checks
- [ ] 6.1 `docs/OBSERVABILITY.md` sections 4.3 and 4.4 list the new spans and metrics. `ruff check`,
  `ruff format --check`, `mypy packages`, full suite with coverage at or above 80%.
