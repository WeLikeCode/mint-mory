# Tasks: spans and metrics on the slow paths (OpenTelemetry, part 2 of 4)

Requires `add-telemetry-runtime` (its test seam `init_telemetry(..., span_exporter=..., metric_reader=...)`,
`reset_telemetry()`, and the root `conftest.py` that resets telemetry around each test). Use `InMemorySpanExporter`
(`opentelemetry.sdk.trace.export.in_memory_span_exporter`) and `InMemoryMetricReader`
(`opentelemetry.sdk.metrics.export`) in tests, with `pytest.importorskip("opentelemetry.sdk")`. No new dependencies.
Write each test first and see it fail. Every helper below must be a cheap no-op when telemetry is off (check
`telemetry.is_enabled()` first, as the existing helpers do). For CLI tests that read Rich tables, set
`monkeypatch.setenv("COLUMNS", "200")` as `test_index_tree_cochange_cli.py` does.

## 1. Telemetry helpers (`packages/core/src/mintmory/core/telemetry.py`)
- [ ] 1.1 Tests for the helpers below with telemetry on and off, including `run_in_context` used by four threads at
  once (no `RuntimeError`).
- [ ] 1.2 Add `search_phase(name: str, *, span: bool = True)`, a context manager yielding an object with
  `set_count(n: int)`. When enabled it times the block with `time.perf_counter()`, opens the span
  `mintmory.search.<name>` (only when `span=True`), sets `mintmory.result_count` when `set_count` was called, and on
  exit records `record_value("mintmory.search.latency_ms", ms, phase=name)`. Create histograms with `unit="ms"` (pass
  `unit` to `create_histogram` in `_instrument`).
- [ ] 1.3 Add `run_in_context(fn)`: call `contextvars.copy_context()` on the calling thread and return a callable that
  runs `ctx.copy().run(fn, *args, **kwargs)`, so each call gets a fresh copy and one wrapped callable can run in
  several threads at once. (Running the same `Context` object in two threads raises
  `RuntimeError: cannot enter context`.)
- [ ] 1.4 Add `set_attributes(**attrs)`: sets attributes on the current span when enabled (None values skipped).

## 2. Search phases (inside `search()`, not on the score methods)
- [ ] 2.1 Test "A search shows its phases" for `SqliteBackend`, and a test that adding a note with anchoring
  (`anchor_candidates`) records no `mintmory.search.*` span and no latency point. Add the phase assertions to the
  Postgres conformance tests if they can run (they are skipped without a database).
- [ ] 2.2 `_fts_scores`, `_trigram_scores` and `_vector_scores` are also called by `anchor_candidates`
  (`storage.py`, `storage_postgres.py`), so do not decorate them. In `search()` of both backends compute the three
  score dicts into local variables, each inside `with telemetry.search_phase("fts") as ph: ... ph.set_count(len(scores))`
  (`"substring"` for the trigram scores, `"vector"` for the vector scores), then call `fuse_and_search` inside
  `with telemetry.search_phase("fusion") as ph:` with `ph.set_count(len(response.memories))`. Record
  `phase="total"` for the whole `search` call (`with telemetry.search_phase("total", span=False):` around the body,
  under the existing `@telemetry.traced("mintmory.search")`), and `phase="graph"` around the body of `search_around` in
  both backends (`span=False`: it already has the `mintmory.search_around` span; every search-around counts, also the
  ones the fusion step makes).

## 3. Embeddings (`packages/core/src/mintmory/core/embedder.py`)
- [ ] 3.1 Test "Hashing embedder is traced", one for `embed` (batch size 1), and one for `FakeEmbedder` (its
  `embed_batch` calls `embed`, the reverse of `HashingEmbedder` and `OllamaEmbedder`): each public call yields exactly
  one `mintmory.embed` span.
- [ ] 3.2 Wrap `embed` and `embed_batch` of `HashingEmbedder`, `LocalEmbedder`, `OllamaEmbedder`, `OpenAIEmbedder` and
  `FakeEmbedder` with one shared decorator that creates the `mintmory.embed` span with the attributes in the spec and
  records `mintmory.embed.latency_ms`. A module-level `ContextVar[bool]` re-entrancy guard makes the inner call (the one
  `embed` makes to `embed_batch`, or the reverse) skip the span and the metric. Read the provider name and model from
  the instance (add a class attribute `provider` where missing).

## 4. Command spans (`packages/cli/src/mintmory/cli/main.py`)
- [ ] 4.1 Tests "A command span carries its counts", "index-tree shows its phases" (with `--prune`), "A failing
  command is marked", one that `mintmory add` produces `mintmory.cli.add` with `mintmory.add_memory` as its child, and
  one that a command ending with exit code 0 is not marked ERROR.
- [ ] 4.2 Add `telemetry.command_span(name)`, usable as a decorator placed under `@app.command()` (Typer follows
  `__wrapped__`, so keep `functools.wraps`): it opens `mintmory.cli.<name>` with `record_exception=False,
  set_status_on_exception=False` (the SDK defaults would mark `typer.Exit(0)` as ERROR and leave `SystemExit(1)`
  unmarked), then sets status ERROR and records the exception for `typer.Exit` or `SystemExit` with a non-zero code and
  for any other exception, leaves the status unset for code 0, and re-raises. Apply it to the commands in the spec.
  Inside the commands, set the outcome counts they already compute with `telemetry.set_attributes(...)`, for example
  `mintmory.files.scanned`, `.added`, `.updated`, `.unchanged`, `.converted`, `.failed`, `.pruned` in `index-tree`.
- [ ] 4.3 In `index_tree`: open `mintmory.index_tree.scan` around the per-entry walk loop,
  `mintmory.index_tree.prune` inside `if prune:` (pruning only runs with `--prune`), and `mintmory.index_tree.cochange`
  inside the co-change branch; wrap each markitdown conversion in `mintmory.convert` (attributes
  `mintmory.file.suffix`, `mintmory.file.size_bytes`, `mintmory.outcome`) and each inline image caption in
  `mintmory.vision.caption`. In `ingest`, wrap each conversion in `mintmory.convert`.

## 5. Worker threads
- [ ] 5.1 Test "Backfill threads stay in the trace" with `max_concurrency=4` and 4 sessions (use the fixtures of
  `test_history_ingest.py` and a fake distiller that opens a span); assert the trace ids and `report.errors == 0`.
  Add a test that the dream's concurrent summaries (`dreaming.py`, the `ThreadPoolExecutor` with
  `ss.concurrency > 1`) create `gen_ai.chat` (or summarizer) spans inside the dream's trace.
- [ ] 5.2 In `history/ingest.py` `backfill` and `sync`, wrap once before the `submit` loop:
  `prepare = telemetry.run_in_context(_prepare_session)` and submit `prepare`. In `dreaming.py`, map
  `telemetry.run_in_context(lambda sel: summarizer(sel.concept, sel.contents))` the same way. Wrap the backfill and
  sync bodies in `mintmory.history.backfill` / `mintmory.history.sync` spans with the report counts as attributes.

## 6. Counters
- [ ] 6.1 Test "Counter by category".
- [ ] 6.2 In `add_memory` of both backends call `telemetry.add_count("mintmory.memories.added", category=<value>)`
  after a successful insert.

## 7. Privacy
- [ ] 7.1 Test "No content leaks into telemetry": walk every exported span's `attributes`, every event's attributes,
  and every metric data point's attributes, and assert no value contains the sentinels.
- [ ] 7.2 Review every attribute added in this change and the existing ones (`llm.py` `gen_ai.chat`, `dreaming.py`)
  against the rule; remove any that carries text.

## 8. Checks
- [ ] 8.1 Update `docs/OBSERVABILITY.md` sections 4.3 and 4.4 to list the spans and metrics that now exist. Run
  `ruff check`, `ruff format --check`, `mypy packages` and the full test suite; coverage stays at or above 80%.
