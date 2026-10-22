# Capability: observability (delta)

## Purpose

MintMory's observability: OpenTelemetry traces and metrics from every entry point (CLI, REST API, MCP servers), safe and silent when no collector runs, distributed across HTTP, MCP and outbound LLM calls, with a local collector, Jaeger and Prometheus stack for development.

## ADDED Requirements

### Requirement: Span kind, parent context and exception options
`telemetry.span` SHALL have the signature `span(name, *, kind="internal", context=None, record_exception=True, set_status_on_exception=True, **attrs)` and pass `kind` (`"internal"`, `"server"`, `"client"`, mapped to `SpanKind`; any other value maps to INTERNAL), `context` and both flags to the tracer's `start_as_current_span`. The defaults are the SDK's, so existing callers (`dreaming.py`, `llm.py`, `traced`) keep their behaviour. With telemetry off it SHALL yield `_NoopSpan`, which gains a no-op `update_name(name)`. This unit's `command_span` uses the two flags; `add-telemetry-boundary-tracing`, which depends on this unit, uses all four options and `update_name` for its server and client spans and does not change `span()`.

#### Scenario: Options reach the span
- **GIVEN** telemetry initialised with an injected in-memory span exporter
- **WHEN** `with telemetry.span("a", kind="server"): pass` and `with telemetry.span("d", kind="bogus"): pass` run, then inside `pytest.raises(RuntimeError)` `with telemetry.span("b", record_exception=False, set_status_on_exception=False): raise RuntimeError("SENTINEL-12")` and the same with defaults as span `c`
- **THEN** `a` has kind SERVER and `d` kind INTERNAL; `b` has status UNSET and no event; `c` has status ERROR with an empty description (scrubbed) and one `exception` event whose only attribute is `exception.type=RuntimeError`; with telemetry not initialised, `with telemetry.span("a", kind="server", record_exception=False) as sp: sp.update_name("b")` raises nothing and `sp` is a `_NoopSpan`

### Requirement: Search phase spans and latency
Each search SHALL record child spans `mintmory.search.fts`, `.substring`, `.vector` and `.fusion` under `mintmory.search`, each with `mintmory.result_count`, and the histogram `mintmory.search.latency_ms` (unit `ms`) with `phase` = `fts`, `substring`, `vector`, `fusion`, `graph` (every search-around) or `total`. This SHALL live in code shared by both storage backends (`hybrid_search.py` and `telemetry.py`). Note anchoring SHALL NOT record search phases.

#### Scenario: A search shows its phases
- **GIVEN** telemetry with an injected in-memory span exporter and metric reader, and a SQLite store with three memories
- **WHEN** a search runs
- **THEN** the four phase spans have the `mintmory.search` span as parent, and latency points exist for `fts`, `substring`, `vector`, `fusion` and `total`

#### Scenario: Search-around alone records only its graph point
- **WHEN** `search_around` is called directly (it runs no score stage)
- **THEN** one `phase=graph` point is recorded and no `mintmory.search.fts`, `.substring`, `.vector` or `.fusion` span

#### Scenario: The Postgres backend uses the shared path
- **GIVEN** a `PostgresBackend` built without a database (its pool is created lazily) whose data-access methods are patched
- **WHEN** its `search` runs with telemetry on
- **THEN** the same four phase spans and the `total` point are recorded

### Requirement: Span helpers without work or with a failure
A search stage with nothing to do (no query embedding, substring search off, no match) SHALL still record its span with `mintmory.result_count` = 0. When the code wrapped by any span helper of this change raises (`search_phase`, the embed decorator, `mintmory.convert`, `mintmory.vision.caption`, `command_span`), the helper SHALL mark its span with `telemetry.mark_error(span, <exception class name>)` from `add-telemetry-runtime`, still record its metric point if it has one, and re-raise the exception unchanged. Recording a metric point or attribute SHALL never raise into the caller.

#### Scenario: A stage with nothing to do
- **WHEN** a search runs without a query embedding
- **THEN** the `mintmory.search.vector` span has `mintmory.result_count` = 0

#### Scenario: A failing stage
- **GIVEN** `_fts_scores` patched to raise `RuntimeError`
- **WHEN** a search runs
- **THEN** the same `RuntimeError` propagates, the `mintmory.search.fts` span has status ERROR and `error.type=RuntimeError`, and a `phase=fts` point is recorded

#### Scenario: A metric failure stays inside telemetry
- **GIVEN** telemetry on and `telemetry.record_value` patched to raise `RuntimeError`
- **WHEN** `HashingEmbedder().embed("a")` and a search run
- **THEN** both return their normal results

### Requirement: Embedding spans and latency
Every public `embed` or `embed_batch` call of an embedder in `embedder.py` SHALL record one `mintmory.embed` span (kind INTERNAL) with `mintmory.embed.provider` (the `create_embedder` name: `hashing`, `local`, `ollama`, `openai`, `fake`), `gen_ai.request.model` (the embedder's `model_name`, omitted when empty), `mintmory.embed.batch_size` and `mintmory.embed.dim`, and one `mintmory.embed.latency_ms` point (unit `ms`, attributes `provider` and `model`, `model` omitted when empty). A public method calling another (`FakeEmbedder.embed_batch` calls `embed`) SHALL record once.

#### Scenario: Hashing embedder is traced
- **WHEN** `HashingEmbedder().embed_batch(["a", "b"])` runs with telemetry on
- **THEN** one `mintmory.embed` span with `mintmory.embed.provider=hashing`, `mintmory.embed.batch_size` = 2 and `mintmory.embed.dim` = the embedder's dimension, and one latency point exist

#### Scenario: Network embedders name their model
- **WHEN** `OllamaEmbedder` embeds one text against a local test HTTP server, and an `OpenAIEmbedder` built with `OpenAIEmbedder.__new__` and a stub client embeds one text
- **THEN** each records one `mintmory.embed` span with `mintmory.embed.provider` (`ollama`, `openai`), `gen_ai.request.model` and `mintmory.embed.dim`, and `LocalEmbedder.embed` and `.embed_batch` carry the same decorator (`__wrapped__`)

### Requirement: CLI commands are traced end to end
`add`, `search`, `ingest`, `index-tree`, `dream`, `history backfill` and `history sync` SHALL each run inside a root span `mintmory.cli.<command>` (spaces become dots), marked with `mark_error` when the command raises or exits non-zero, never for exit code 0. `telemetry.command_span(name)` SHALL open that span with `record_exception=False, set_status_on_exception=False` and mark it only through `mark_error`: `typer.Exit` is a `RuntimeError` subclass (Typer 0.26.7), so the SDK default would mark an exit with code 0 as ERROR. `index-tree` SHALL set `mintmory.files.scanned`, `.added`, `.updated`, `.unchanged` and `.failed` from the counters `index_tree` already keeps (`scanned`, `added`, `updated`, `unchanged`, `failed`).

#### Scenario: Command spans and counts
- **GIVEN** telemetry with an in-memory exporter and a folder with two text files
- **WHEN** `mintmory index-tree <folder>`, `mintmory search hello` and `mintmory dream` run through the Typer test runner
- **THEN** `mintmory.cli.index-tree` (with `mintmory.files.scanned` = 2 and `mintmory.files.added` = 2), `mintmory.cli.search` and `mintmory.cli.dream` spans are exported, none with status ERROR; and `mintmory history sync` over an empty session folder (the fixtures of `packages/cli/tests/test_history_cli.py`) exports a `mintmory.cli.history.sync` span

#### Scenario: A failing command is marked
- **WHEN** `mintmory ingest` runs on a path that does not exist (Typer does not validate it: the body finds no files and raises `typer.Exit(code=1)`)
- **THEN** the `mintmory.cli.ingest` span has status ERROR and `error.type=Exit`

#### Scenario: Exit code 0 is not an error
- **GIVEN** telemetry with an in-memory exporter, a function decorated with `telemetry.command_span("probe-ok")` raising `typer.Exit(code=0)` and one decorated with `telemetry.command_span("probe-fail")` raising `typer.Exit(code=1)`
- **WHEN** each is called inside `pytest.raises(typer.Exit)`
- **THEN** span `mintmory.cli.probe-ok` has status UNSET and no event; `mintmory.cli.probe-fail` has status ERROR, `error.type=Exit` and no event

### Requirement: Indexing and conversion phases are traced
Under `mintmory.cli.index-tree`, `index-tree` SHALL record `mintmory.index_tree.scan` around the walk over the roots (including the per-file co-change embeddings), `mintmory.index_tree.prune` around the `--prune` pass, and `mintmory.index_tree.cochange` around the post-walk co-change block, which runs only when co-change is on and at least two files were added or updated (`if run_cochange and len(changed_docs) >= 2:`); that span SHALL carry `mintmory.outcome=ok` and `mintmory.cochange.changesets` (the count `apply_changesets` returns), or `mintmory.outcome=unavailable` when `CoChangeUnavailable` is caught (no ERROR). Inside the walk it SHALL record one `mintmory.convert` span per binary conversion (the `extract_markdown` call when `want_binary` is true; the plain-text pass, `text_eligible` without `want_binary`, records none) and one `mintmory.vision.caption` span around each `captioner.describe(...)` call of the raster branch, which runs only when `vision.captioner_from_settings` returns a captioner (`MINTMORY_VISION_PROVIDER=llm`); SVG text and rasters queued for the agent record none. `ingest` SHALL record one `mintmory.convert` span per `extract_markdown` call. Both span kinds carry `mintmory.file.suffix`, `mintmory.file.size_bytes` and `mintmory.outcome` (`ok`, or `failed` on the `ConversionError` / `VisionError` the commands catch and count).

#### Scenario: index-tree phases
- **GIVEN** telemetry with an in-memory exporter and a folder with three text files written at once
- **WHEN** `mintmory index-tree --prune --cochange <folder>` runs
- **THEN** `mintmory.cli.index-tree` has the children `mintmory.index_tree.scan`, `.prune` and `.cochange`, the last with `mintmory.outcome=ok` (three files in one folder and time block take the connected-components fallback, since `cochange_fallback_max_n` defaults to 8, so scikit-learn is not needed), and no `mintmory.convert` span exists

#### Scenario: No co-change span without co-change work
- **WHEN** `mintmory index-tree --cochange` runs over a folder with one text file, and `--no-cochange` over three
- **THEN** neither run exports a `mintmory.index_tree.cochange` span

#### Scenario: Conversion spans
- **GIVEN** `mintmory.core.conversion.extract_markdown` patched to return `ExtractResult(text="converted", method="markitdown", path=...)`
- **WHEN** `mintmory ingest report.pdf` runs, and `mintmory index-tree --content --content-types pdf <folder with report.pdf>`
- **THEN** one `mintmory.convert` span (`mintmory.file.suffix=.pdf`, `mintmory.outcome=ok`) is a child of `mintmory.cli.ingest`, and one is a descendant of the content run's `mintmory.index_tree.scan`

#### Scenario: Inline caption span
- **GIVEN** `MINTMORY_VISION_PROVIDER=llm`, `mintmory.core.llm.post_chat_completion` patched to return `{"choices": [{"message": {"content": "A caption."}}]}` (as `test_index_tree_vision_llm_mode_captions_raster_inline` in `packages/cli/tests/test_cli.py` does), and a folder with `photo.png` (`b"\x89PNG\r\n\x1a\n" + b"\x00" * 16`)
- **WHEN** `mintmory index-tree <folder> --no-text-content --vision` runs, then the same over a fresh database with `MINTMORY_VISION_PROVIDER` unset
- **THEN** the first run prints `images-described` and exports one `mintmory.vision.caption` span (`mintmory.file.suffix=.png`, `mintmory.outcome=ok`) under `mintmory.index_tree.scan`; the second prints `images-queued` and exports none

### Requirement: Worker threads keep the trace
Work handed to thread pools in a traced operation (session preparation in history `backfill` and `sync`, the dream's concurrent summaries) SHALL run in a fresh copy of the caller's context per task.

#### Scenario: Threads stay in the trace
- **GIVEN** telemetry with an in-memory exporter
- **WHEN** inside a test span `root-a`, `backfill(..., max_concurrency=4)` runs, and then `sync(..., max_concurrency=4)` into a second, empty history database, each over four sessions (the stub adapter of `test_backfill_concurrent_no_data_loss` in `packages/core/tests/test_history_ingest.py`) with a fake distiller that opens span `fake.distill`; and inside a test span `root-b`, `DreamingEngine(store, summarizer=fake, summary_settings=SummarySettings(concurrency=2, min_memories=2)).run_full()` runs over four memories (two quoting `"alpha-x"`, two quoting `"beta-y"`, so at least two concepts), the fake summarizer opening span `fake.summarize`
- **THEN** every `fake.distill` span has the trace id of `root-a`, every `fake.summarize` span that of `root-b`, and the backfill and sync reports have `errors == 0`

### Requirement: Memory counters
Adding a memory SHALL increment `mintmory.memories.added` with `category` (the `MemoryCategory` value, e.g. `fact`), through one decorator shared by both backends' `add_memory`.

#### Scenario: Counter by category
- **WHEN** two `fact` memories and one `skill` memory are added to a SQLite store with telemetry on
- **THEN** the counter reports 2 for `category=fact` and 1 for `category=skill`, and `PostgresBackend.add_memory` carries the same decorator

### Requirement: Telemetry carries no content
Span names, span and event attributes, status descriptions and metric attributes SHALL NOT contain memory text, note text, query text, prompts, completions, file contents, concept names or header values. A failed span carries status ERROR and `error.type` only; exception messages are removed at export by the runtime's scrubber. On `staging` the existing spans already comply and stay as they are: `gen_ai.chat` carries `gen_ai.system`, `gen_ai.request.model`, `prompt_chars`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `latency_ms`, `ok`; `mintmory.dream.light` / `.full` carry counts (`new_links`, `new_summaries`, `contradictions_resolved`, `archived`, `rehabilitated`); `mintmory.dream.step` carries `step` and `count`; metrics `mintmory.llm.latency_ms`, `mintmory.llm.calls` (`model`, `ok`) and `mintmory.dream.duration_ms` (`intensity`).

#### Scenario: No content leaks into telemetry
- **WHEN** a memory with text `SENTINEL-CONTENT-7f3a` is added, a search for `SENTINEL-QUERY-91c2` runs and `build_dreaming_engine(store).run_light()` runs, with telemetry on
- **THEN** no exported span, event or metric attribute value contains either sentinel

#### Scenario: Notes, LLM calls, concept names, headers and indexed files leak nothing
- **GIVEN** telemetry on; a local test HTTP server answering `POST /v1/chat/completions` with `{"choices": [{"message": {"content": "SENTINEL-OUT-2b"}}]}`; a SQLite store with three memories each containing `"zq-concept-41"` (quoted, so the entity extractor yields the concept `zq-concept-41`) and `SENTINEL-DREAM-8e`
- **WHEN** `notes.create_note(store, "SENTINEL-NOTE-5d")` runs, `build_dreaming_engine(store, LLMSettings(provider="ollama", base_url=<server>/v1, model="m", api_key="SENTINEL-KEY-6e")).run_full()` runs (the summary prompt holds the concept name and `SENTINEL-DREAM-8e`, the `Authorization` header the key), and `mintmory index-tree` indexes a text file containing `SENTINEL-FILE-3c`
- **THEN** the server received at least one chat request, and no exported span name, span or event attribute, status description or metric attribute contains `zq-concept-41`, `SENTINEL-NOTE-5d`, `SENTINEL-DREAM-8e`, `SENTINEL-OUT-2b`, `SENTINEL-KEY-6e` or `SENTINEL-FILE-3c`

#### Scenario: A failure does not leak its message
- **GIVEN** `_fts_scores` patched to raise `RuntimeError("no such column: SENTINEL-QUERY-91c2")`
- **WHEN** a search runs with telemetry on and the error propagates
- **THEN** the `mintmory.search.fts` span has status ERROR and `error.type=RuntimeError`, and no exported span (including `mintmory.search`), event or status description contains the sentinel
