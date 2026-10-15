# Capability: observability (delta)

## ADDED Requirements

### Requirement: Search phase spans and latency
Each search SHALL record child spans `mintmory.search.fts`, `.substring`, `.vector` and `.fusion` under `mintmory.search`, each with `mintmory.result_count`, and the histogram `mintmory.search.latency_ms` (unit `ms`) with `phase` = `fts`, `substring`, `vector`, `fusion`, `graph` (every search-around) or `total`. This SHALL live in code shared by both storage backends (`hybrid_search.py` and `telemetry.py`). Note anchoring SHALL NOT record search phases.

#### Scenario: A search shows its phases
- **GIVEN** telemetry with an in-memory span exporter and metric reader, and a SQLite store with three memories
- **WHEN** a search runs
- **THEN** the four phase spans have the `mintmory.search` span as parent, and latency points exist for `fts`, `substring`, `vector`, `fusion` and `total`

#### Scenario: The Postgres backend uses the shared path
- **GIVEN** a `PostgresBackend` built without a database (its pool is created lazily) whose data-access methods are patched
- **WHEN** its `search` runs with telemetry on
- **THEN** the same four phase spans and the `total` point are recorded

### Requirement: Search phases without work or with a failure
A stage with nothing to do (no query embedding, substring search off, no match) SHALL still record its span with `mintmory.result_count` = 0. A stage that raises SHALL end its span with status ERROR, still record its latency point, and re-raise unchanged.

#### Scenario: A stage with nothing to do
- **WHEN** a search runs without a query embedding
- **THEN** the `mintmory.search.vector` span has `mintmory.result_count` = 0

#### Scenario: A failing stage
- **GIVEN** `_fts_scores` patched to raise `RuntimeError`
- **WHEN** a search runs
- **THEN** the error propagates, the `mintmory.search.fts` span has status ERROR, and a `phase=fts` point is recorded

### Requirement: Embedding spans and latency
Every public `embed` or `embed_batch` call of an embedder in `embedder.py` SHALL record one `mintmory.embed` span (`mintmory.embed.provider`, `gen_ai.request.model` when known, `mintmory.embed.batch_size`, `mintmory.embed.dim`) and one `mintmory.embed.latency_ms` point (unit `ms`, `provider`, `model`).

#### Scenario: Hashing embedder is traced
- **WHEN** `HashingEmbedder().embed_batch(["a", "b"])` runs with telemetry on
- **THEN** one `mintmory.embed` span with `mintmory.embed.batch_size` = 2 and one latency point exist

### Requirement: CLI commands are traced end to end
`add`, `search`, `ingest`, `index-tree`, `dream`, `history backfill` and `history sync` SHALL each run inside a root span `mintmory.cli.<command>` (spaces become dots), ending with status ERROR when the command raises or exits non-zero, and never for exit code 0. `index-tree` SHALL set `mintmory.files.scanned`, `.added`, `.updated`, `.unchanged` and `.failed` from the counters of the same names that `index_tree` already keeps.

#### Scenario: Command spans and counts
- **GIVEN** telemetry with an in-memory exporter and a folder with two text files
- **WHEN** `mintmory index-tree <folder>`, `mintmory search hello` and `mintmory dream` run through the Typer test runner
- **THEN** `mintmory.cli.index-tree` (with `mintmory.files.scanned` = 2 and `mintmory.files.added` = 2), `mintmory.cli.search` and `mintmory.cli.dream` spans are exported, none with status ERROR

#### Scenario: A failing command is marked
- **WHEN** `mintmory ingest` runs on a path that does not exist (Typer does not validate it: the body finds no files and raises `typer.Exit(code=1)`)
- **THEN** the `mintmory.cli.ingest` span has status ERROR

### Requirement: Indexing and conversion phases are traced
`index-tree` SHALL record child spans `mintmory.index_tree.scan`, `mintmory.index_tree.prune` (with `--prune`) and `mintmory.index_tree.cochange` (when co-change runs), one `mintmory.convert` span per document conversion and one `mintmory.vision.caption` span per inline caption; `ingest` SHALL record one `mintmory.convert` span per conversion.

#### Scenario: index-tree phases
- **GIVEN** telemetry with an in-memory exporter and a folder with three text files
- **WHEN** `mintmory index-tree --prune --cochange <folder>` runs
- **THEN** the `mintmory.cli.index-tree` span has the children `mintmory.index_tree.scan`, `.prune` and `.cochange`

#### Scenario: Conversion and caption spans
- **GIVEN** `mintmory.core.conversion.extract_markdown` patched to return text, and `vision.captioner_from_settings` patched to return a fake captioner with `MINTMORY_VISION_PROVIDER=llm`
- **WHEN** `mintmory ingest report.pdf` runs, and `mintmory index-tree --vision <folder with one PNG>` runs
- **THEN** one `mintmory.convert` span (`mintmory.file.suffix` = `.pdf`) is a child of `mintmory.cli.ingest`, and one `mintmory.vision.caption` span is a descendant of `mintmory.cli.index-tree`

### Requirement: Worker threads keep the trace
Work handed to thread pools in a traced operation (session preparation in history backfill and sync, the dream's concurrent summaries) SHALL run in a fresh copy of the caller's context per task.

#### Scenario: Threads stay in the trace
- **GIVEN** telemetry with an in-memory exporter
- **WHEN** a history backfill of four sessions with `max_concurrency=4` and a span-opening fake distiller runs, and a full dream with summary concurrency 2 and a span-opening fake summarizer runs
- **THEN** every worker span has its operation's trace id and the backfill report has no errors

### Requirement: Memory counters
Adding a memory SHALL increment `mintmory.memories.added` with `category`, through one decorator shared by both backends' `add_memory`.

#### Scenario: Counter by category
- **WHEN** two `fact` memories and one `skill` memory are added to a SQLite store with telemetry on
- **THEN** the counter reports 2 for `category=fact` and 1 for `category=skill`, and `PostgresBackend.add_memory` carries the same decorator

### Requirement: Telemetry carries no content
Span attributes, span events and metric attributes SHALL NOT contain memory text, note text, query text, prompts, completions, file contents or HTTP header values; counts, sizes, categories, phases, outcomes, suffixes, provider and model names, and memory ids are allowed.

#### Scenario: No content leaks into telemetry
- **WHEN** a memory with text `SENTINEL-CONTENT-7f3a` is added, a search for `SENTINEL-QUERY-91c2` runs and a light dream runs, with telemetry on
- **THEN** no exported span, event or metric attribute value contains either sentinel
