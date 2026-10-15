# ingestion Specification

## Purpose
TBD - created by archiving change add-markitdown-ingestion. Update Purpose after archive.

## Requirements

### Requirement: Automatic document conversion on ingest
The system SHALL convert binary document formats to Markdown automatically
during `mintmory ingest`, routing each file by its suffix, so that office
documents become first-class indexable memories without a manual pre-step.

#### Scenario: Word/PDF/Excel are converted, not corrupted
- **WHEN** a user runs `mintmory ingest report.docx` (or `.pdf`/`.xlsx`/`.pptx`)
  with the `docs` extra installed
- **THEN** the file is converted via markitdown to Markdown, cleaned, chunked,
  and stored, and each stored memory's metadata records `converter: "markitdown"`.

#### Scenario: Plain text and Markdown bypass conversion
- **WHEN** a user ingests a `.md` or `.txt` file
- **THEN** it is read directly (no markitdown), cleaned with the conservative
  formatter, and stored with metadata `converter: "text"`.

### Requirement: Conservative formatting normalisation
The system SHALL apply a conservative, idempotent `clean_markdown` pass to all
ingested content that normalises line endings, strips trailing whitespace,
collapses 3+ blank lines to one, trims leading/trailing blank lines, and removes
HTML comments — without reflowing prose, altering fenced code, or changing table
structure.

#### Scenario: Cleanup is idempotent
- **WHEN** `clean_markdown` is applied twice to any input
- **THEN** the second application returns a value identical to the first.

### Requirement: Optional dependency, graceful degradation
The system SHALL keep `markitdown` an optional extra (`docs`) and SHALL NOT make
`mintmory.core` import-time depend on it. When a convertible binary is ingested
without the extra installed, the system SHALL skip that file with an actionable
message and continue ingesting the remaining files.

#### Scenario: Missing extra skips one file, not the run
- **WHEN** a user ingests a directory containing `a.md` and `b.pdf` without the
  `docs` extra installed
- **THEN** `a.md` is ingested, `b.pdf` is skipped with a message naming
  `uv sync --extra docs`, and the command exits 0.

### Requirement: Ingest safety limits and control
The system SHALL enforce configurable limits that bound conversion of untrusted
input — on-disk size, **decompressed output size**, and **per-file wall-clock
time** — and SHALL provide a `--convert/--no-convert` flag plus `MINTMORY_CONVERT_*`
settings (including `MINTMORY_CONVERT_ENABLED` as a global off-switch) to control
conversion behaviour. No single file may hang the run.

#### Scenario: Oversized file is rejected
- **WHEN** a file exceeds `MINTMORY_CONVERT_MAX_FILE_MB` on disk
- **THEN** that file is skipped with a clear "too large" message and the run
  continues.

#### Scenario: Decompression bomb is bounded by output size
- **WHEN** a small compressed file (zip-based docx/xlsx, or a PDF) decompresses
  to markdown larger than `MINTMORY_CONVERT_MAX_OUTPUT_MB`
- **THEN** the conversion is rejected (the on-disk cap alone does not bound the
  decompressed output) and the run continues.

#### Scenario: A wedged conversion does not hang the run
- **WHEN** converting a file takes longer than `MINTMORY_CONVERT_TIMEOUT_S`
- **THEN** that file is skipped with a "timed out" message, the bulk run
  continues, and the process can still exit (the conversion runs in a daemon
  thread).

#### Scenario: Global off-switch disables conversion
- **WHEN** `MINTMORY_CONVERT_ENABLED=false`
- **THEN** convertible binaries are skipped (not converted) even with the `docs`
  extra installed, while text/markdown still ingest.

### Requirement: Empty conversion is surfaced, not silently dropped
When a conversion succeeds but produces no extractable text, the system SHALL
report that explicitly and SHALL NOT count the file as successfully converted.

#### Scenario: Image-only PDF yields a clear note
- **WHEN** a convertible file produces empty text (e.g. an image-only scan)
- **THEN** the file is reported as "produced no extractable text", stored as
  zero memories, and excluded from the converted tally.

### Requirement: Conversion readiness is observable
`mintmory doctor` SHALL report whether markitdown is installed and how many
formats are convertible, as a non-fatal readiness row.

#### Scenario: Doctor reports conversion readiness
- **WHEN** a user runs `mintmory doctor`
- **THEN** the output includes a `conversion` row stating markitdown
  availability, and the row never changes the command's healthy/unhealthy exit.

### Requirement: Document recency from file modified-time

When `index-tree` writes or updates a document memory, it SHALL set the memory's
`valid_from` to the file's modified-time (`mtime`, as naive-UTC) and SHALL set
`metadata.modified_source = "fs_mtime"`. This makes documents orderable
newest→oldest and records the trust tier of the timestamp. Existing document
metadata (path, rel, size, mtime, collection) is unchanged; this is additive.

#### Scenario: Newer and older documents are distinguishable
- **GIVEN** two files indexed by `index-tree` with different `mtime`s
- **WHEN** they are written
- **THEN** each memory's `valid_from` equals its file's `mtime` (naive-UTC), `metadata.modified_source` is `"fs_mtime"`, and a newest-first query orders the later-`mtime` file first.

### Requirement: Observed co-change via clustering of changed files

The co-change pass SHALL group the files whose content changed in an `index-tree`
run (added or updated) into change-sets by clustering them with HDBSCAN over a
composite distance combining modified-time proximity, folder-path distance, and
content-embedding similarity. Each cluster SHALL receive a deterministic
`changeset_id`; its members SHALL carry `metadata.changeset_id` and
`metadata.changeset_observed_at`, and SHALL be linked pairwise in `concept_links`
with `relates_to` edges (`entity = "changeset:<id>"`, `strength` from the cluster
membership probability) plus `before` edges in modified-time order. A file that
does not join any cluster (HDBSCAN noise, `min_cluster_size = 2`) SHALL NOT be
placed in a change-set and SHALL receive no co-change edges. Re-running with no
new content changes SHALL NOT create new change-sets or duplicate edges
(idempotent).

#### Scenario: Two distinct edit bursts yield two change-sets
- **GIVEN** four files where two changed close in time within one folder and two changed close in time within another folder
- **WHEN** `index-tree --cochange` runs
- **THEN** two change-sets are produced, each with a deterministic `changeset_id`, its members carry that id, and the members are linked by `relates_to` (entity `changeset:<id>`) and `before` edges.

#### Scenario: A lone changed file is not co-change
- **GIVEN** a run in which exactly one file changed
- **WHEN** the co-change pass runs
- **THEN** no change-set is created and the file gets no `changeset_id` and no co-change edges.

### Requirement: Co-change writes are scoped to documents

The co-change pass SHALL operate only on `source = "document"` records that
changed in the current run. It SHALL NOT read or modify any other memory in the
target store. The `changed-with` and document-timeline queries SHALL return only
`source = "document"` records.

#### Scenario: Non-document memories are untouched
- **GIVEN** a working store containing both document memories and ordinary (non-document) memories
- **WHEN** `index-tree --cochange` runs and modifies the changed documents
- **THEN** no non-document memory is modified, and `docs changed-with` / `docs timeline` never return non-document memories.

### Requirement: Storage target defaults to the working store

Document indexing SHALL write to the working store (`hermes.db`) by default and
SHALL honour the existing `--db` option to target a separate database instead.
Co-change behaviour SHALL be identical regardless of which target is used.

#### Scenario: Default and override targets both work
- **WHEN** `index-tree` is run with no `--db`
- **THEN** documents and co-change data are written to the working store
- **AND WHEN** it is run with `--db <path>`, they are written to that database instead, with the same recency and co-change results.

### Requirement: Co-change degrades gracefully without the optional dependency

HDBSCAN clustering SHALL be provided by an optional `cochange` extra
(`scikit-learn`). Recency stamping SHALL always work. When co-change is requested
but the extra is not installed, the run SHALL complete (recency applied), SHALL
emit a one-line hint to install the extra, and SHALL NOT raise.

#### Scenario: Missing extra does not break indexing
- **GIVEN** `scikit-learn` is not installed
- **WHEN** `index-tree --cochange` runs
- **THEN** documents are indexed with `valid_from`/`modified_source` set, an install hint is printed, no change-sets are created, and the command exits successfully.

### Requirement: Honest co-change semantics in output

The `changed-with` query output SHALL label co-change results as observed (time +
folder + content) and explicitly NOT a version-controlled commit, so users do not
mistake inferred co-change for an atomic change-set.

#### Scenario: Output states the limit
- **WHEN** `docs changed-with <path>` prints peers
- **THEN** the output includes a label indicating the grouping is observed co-change (not a version-controlled commit) and shows each peer's edge strength and observed time.
