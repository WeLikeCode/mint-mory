# Capability: observability (delta)

## ADDED Requirements

### Requirement: Search phase spans and latency
Each search SHALL record child spans `mintmory.search.fts`, `mintmory.search.substring`, `mintmory.search.vector` and `mintmory.search.fusion` under `mintmory.search`, in both storage backends, each with `mintmory.result_count`. The histogram `mintmory.search.latency_ms` (unit `ms`) SHALL record these phases, `graph` (every search-around) and `total`, in the attribute `phase`. Note anchoring SHALL NOT record search phases.

#### Scenario: A search shows its phases
- **GIVEN** telemetry initialised with an in-memory span exporter and metric reader, and a SQLite store with three memories
- **WHEN** a search runs
- **THEN** the exporter holds `mintmory.search.fts`, `mintmory.search.substring`, `mintmory.search.vector` and `mintmory.search.fusion` spans whose parent is the `mintmory.search` span, and the reader holds `mintmory.search.latency_ms` points for `fts`, `substring`, `vector`, `fusion` and `total`

### Requirement: Search phases without work or with a failure
`search()` always runs all four stages, so a stage with nothing to do (no query embedding, substring search off, no match) SHALL still record its span with `mintmory.result_count` = 0. A stage that raises SHALL end its span with status ERROR, still record its latency point, and re-raise the exception unchanged.

#### Scenario: A stage with nothing to do
- **GIVEN** telemetry initialised with in-memory exporters and a search without a query embedding
- **WHEN** the search runs
- **THEN** the `mintmory.search.vector` span exists with `mintmory.result_count` = 0

#### Scenario: A failing stage
- **GIVEN** telemetry initialised with in-memory exporters and `_fts_scores` patched to raise `RuntimeError`
- **WHEN** a search runs
- **THEN** the `RuntimeError` propagates, the `mintmory.search.fts` span has status ERROR, and a `phase=fts` latency point is recorded

### Requirement: Embedding spans and latency
Every call to `embed` or `embed_batch` of an embedder in `embedder.py` SHALL record a `mintmory.embed` span with the attributes `mintmory.embed.provider`, `gen_ai.request.model` (when the embedder has a model), `mintmory.embed.batch_size` and `mintmory.embed.dim`, and the histogram `mintmory.embed.latency_ms` (unit `ms`) with `provider` and `model`.

#### Scenario: Hashing embedder is traced
- **GIVEN** telemetry initialised with in-memory exporters
- **WHEN** `HashingEmbedder().embed_batch(["a", "b"])` runs
- **THEN** one `mintmory.embed` span with `mintmory.embed.batch_size` = 2 is exported and one latency point is recorded

### Requirement: Long-running commands are traced end to end
The CLI commands `add`, `search`, `ingest`, `index-tree`, `dream`, `vision-run`, `history backfill`, `history sync` and `migrate-storage` SHALL each run inside a root span `mintmory.cli.<command>` (spaces become dots) that carries the command's outcome counts. The span SHALL end with status ERROR when the command raises or exits with a non-zero code, and SHALL NOT be marked ERROR for exit code 0.

#### Scenario: A command span carries its counts
- **GIVEN** telemetry initialised with an in-memory exporter and a folder with two text files
- **WHEN** `mintmory index-tree <folder>` runs through the Typer test runner
- **THEN** a `mintmory.cli.index-tree` span is exported with the attribute `mintmory.files.scanned` = 2

#### Scenario: A failing command is marked
- **GIVEN** telemetry initialised with an in-memory exporter
- **WHEN** `mintmory ingest` runs on a path that does not exist (Typer does not validate it: the command body finds no files, prints "No matching files to ingest" and raises `typer.Exit(code=1)`)
- **THEN** the `mintmory.cli.ingest` span has status ERROR

### Requirement: Indexing and conversion phases are traced
`index-tree` SHALL record the child spans `mintmory.index_tree.scan`, `mintmory.index_tree.prune` and `mintmory.index_tree.cochange` (when co-change runs), one `mintmory.convert` span per document conversion and one `mintmory.vision.caption` span per inline image caption; `ingest` SHALL record one `mintmory.convert` span per document conversion.

#### Scenario: index-tree shows its phases
- **GIVEN** telemetry initialised with an in-memory exporter and a folder with two text files
- **WHEN** `mintmory index-tree --prune <folder>` runs through the Typer test runner
- **THEN** the `mintmory.cli.index-tree` span has the children `mintmory.index_tree.scan` and `mintmory.index_tree.prune`

#### Scenario: A conversion is traced
- **GIVEN** telemetry initialised with an in-memory exporter and `mintmory.core.conversion.extract_markdown` patched to return text
- **WHEN** `mintmory ingest report.pdf` runs through the Typer test runner
- **THEN** one `mintmory.convert` span with `mintmory.file.suffix` = `.pdf` is a child of the `mintmory.cli.ingest` span

### Requirement: Worker threads keep the trace
Work that MintMory hands to thread pools during a traced operation (session preparation in the history backfill and sync, and the dream's concurrent summary calls) SHALL run in a fresh copy of the caller's context per task, so spans created there are children of the caller's span.

#### Scenario: Dream summaries stay in the trace
- **GIVEN** telemetry initialised with an in-memory exporter, summary concurrency 2 and a fake summarizer that opens a span
- **WHEN** a full dream summarises two concepts
- **THEN** both summarizer spans have the trace id of the dream's `mintmory.dream.full` span

#### Scenario: Backfill threads stay in the trace
- **GIVEN** telemetry initialised with an in-memory exporter and a history backfill over two sessions with more than one worker
- **WHEN** the backfill runs
- **THEN** every span created in a worker has the trace id of the backfill's root span and the backfill report has no errors

### Requirement: Memory counters
Adding a memory SHALL increment the counter `mintmory.memories.added` with the attribute `category`, in both storage backends.

#### Scenario: Counter by category
- **GIVEN** telemetry initialised with an in-memory metric reader
- **WHEN** two `fact` memories and one `skill` memory are added
- **THEN** the counter reports 2 for `category=fact` and 1 for `category=skill`

### Requirement: Telemetry carries no content
Span attributes, span events and metric attributes SHALL NOT contain memory text, note text, search query text, prompts, completions, file contents or HTTP header values. They MAY contain counts, sizes, lengths, categories, phases, outcomes, file suffixes, provider and model names, and memory identifiers.

#### Scenario: No content leaks into telemetry
- **GIVEN** telemetry initialised with in-memory exporters
- **WHEN** a memory with the text `SENTINEL-CONTENT-7f3a` is added, a search for `SENTINEL-QUERY-91c2` runs, and a light dream runs
- **THEN** no exported span attribute, span event attribute or metric attribute value contains `SENTINEL-CONTENT-7f3a` or `SENTINEL-QUERY-91c2`
