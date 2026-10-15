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
`metadata.modified_source = "fs_mtime"`. This SHALL apply to both the file-record
memory (`record_role = "file"`) and to each body-text chunk memory
(`record_role = "chunk"`) produced by full-text extraction, so the searchable body
of a document also carries recency. Body chunks SHALL NOT receive a `changeset_id`.

#### Scenario: Newer and older documents are distinguishable
- **GIVEN** two files indexed by `index-tree` with different `mtime`s
- **WHEN** they are written
- **THEN** each memory's `valid_from` equals its file's `mtime` (naive-UTC), `metadata.modified_source` is `"fs_mtime"`, and a newest-first query orders the later-`mtime` file first.

#### Scenario: Body chunks carry recency but do not duplicate timeline rows
- **GIVEN** a full-texted document that produces several body chunks
- **WHEN** the document is indexed
- **THEN** each body chunk has `valid_from` and `metadata.modified_source = "fs_mtime"` set with `record_role = "chunk"`, the chunks carry no `changeset_id`, and `docs timeline` shows the document as a single row (the file-record), not one row per chunk.

### Requirement: Observed co-change via clustering of changed files
The co-change pass SHALL group the files whose content changed in an `index-tree`
run (added or updated, excluding co-change-excluded suffixes) into change-sets by
clustering them with HDBSCAN over a composite distance combining modified-time
proximity, folder-path distance, and content-embedding similarity — or, per the
small-batch and all-noise fallback requirement, by deterministic
connected-components clustering — then applying the time-gap split and the
cluster-size cap. To remain tractable on large corpora, the pass SHALL partition the
changed files into per-folder, per-time-bucket clustering blocks (when
`cochange_block_by_folder` is enabled) and SHALL cluster each block independently,
computing the time term of each block distance matrix with vectorized array
operations, subject to a per-block partition-size ceiling. Each surviving cluster SHALL receive a
deterministic `changeset_id`; its members SHALL carry `metadata.changeset_id`,
`metadata.changeset_observed_at`, and `metadata.changeset_kind`, and SHALL be
linked pairwise in `concept_links` with `relates_to` edges (`entity =
"changeset:<id>"`, `strength` from the cluster membership probability) plus
`before` edges in modified-time order. A file that does not join any surviving
cluster (HDBSCAN noise, a dropped gap-split fragment, or a dropped oversized
cluster) SHALL NOT be placed in a change-set and SHALL receive no co-change edges.
Re-running with no new content changes SHALL NOT create new change-sets or
duplicate edges (idempotent).

#### Scenario: Two distinct edit bursts yield two change-sets
- **GIVEN** four files where two changed close in time within one folder and two changed close in time within another folder
- **WHEN** `index-tree --cochange` runs
- **THEN** two change-sets are produced, each with a deterministic `changeset_id`, its members carry that id and a `changeset_kind`, and the members are linked by `relates_to` (entity `changeset:<id>`) and `before` edges.

#### Scenario: A lone changed file is not co-change
- **GIVEN** a run in which exactly one knowledge file changed
- **WHEN** the co-change pass runs
- **THEN** no change-set is created and the file gets no `changeset_id` and no co-change edges.

#### Scenario: Large corpus stays tractable
- **GIVEN** a run with several thousand changed files spread across many folders
- **WHEN** the co-change pass runs with blocking enabled
- **THEN** clustering completes without building a single dense distance matrix over all changed files, and the produced change-sets are deterministic.

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
folder + content) and explicitly NOT a version-controlled commit, AND SHALL display
the change-set kind (`cold_full_index` versus `incremental`) so users do not mistake
a cold-index co-location grouping for an atomic or incremental edit change-set.

#### Scenario: Output states the limit
- **WHEN** `docs changed-with <path>` prints peers
- **THEN** the output includes a label indicating the grouping is observed co-change (not a version-controlled commit), shows the change-set kind, and shows each peer's edge strength and observed time.

### Requirement: Co-change time-gap guard
The co-change pass SHALL enforce a hard maximum modified-time gap between adjacent
members of any change-set, controlled by `max_cochange_gap_seconds` (default
86400). After clustering, each cluster SHALL be sorted by modified-time and split
wherever the gap between two time-adjacent members exceeds the threshold; every
resulting change-set SHALL have all adjacent internal modified-time gaps within the
threshold, regardless of folder-path or content proximity. A split fragment with
fewer than `min_cluster_size` members SHALL NOT become a change-set. This guard is
deterministic and is applied as a post-cluster split, not as a distance-matrix
modification.

#### Scenario: A cluster spanning a large time gap is split
- **GIVEN** a single cluster whose members fall into two dense bursts separated by a modified-time gap greater than `max_cochange_gap_seconds`
- **WHEN** the co-change pass runs
- **THEN** the cluster is split into the two bursts, each emitted change-set has all adjacent internal modified-time gaps within the threshold, and no single change-set spans the large gap.

#### Scenario: Stray far-apart members are dropped
- **GIVEN** a cluster where, after the time-gap split, a fragment has fewer than `min_cluster_size` members
- **WHEN** the split is applied
- **THEN** that fragment becomes no change-set, its files receive no co-change edges, and a dropped-fragment count is reported.

### Requirement: Co-change cluster-size cap
The co-change pass SHALL drop any change-set whose member count exceeds
`max_cochange_cluster_size` (default 50), applied after the time-gap split, and
SHALL report the number of change-sets dropped for size. A dropped change-set SHALL
write no `changeset_id`, no `changeset_kind`, and no co-change edges to its members.

#### Scenario: An oversized blob is dropped
- **GIVEN** a change-set with more members than `max_cochange_cluster_size` whose members all fall within the time-gap threshold
- **WHEN** the size cap is applied
- **THEN** the change-set is dropped, its members receive no `changeset_id` and no co-change edges, and the dropped-oversized count is incremented by one.

### Requirement: Non-knowledge types excluded from co-change
The co-change pass SHALL exclude image suffixes (when `cochange_exclude_images`),
build-artifact suffixes (when `cochange_exclude_artifacts`), and any suffix listed
in `cochange_exclude_suffixes_csv` from co-change clustering. Excluded files SHALL
still be indexed and SHALL still receive recency (`valid_from`/`modified_source`);
only their participation in change-sets is suppressed.

#### Scenario: Image files get recency but no co-change
- **GIVEN** a run in which several `.jpg` files and several `.md` files changed together within one folder and `cochange_exclude_images` is true
- **WHEN** `index-tree --cochange` runs
- **THEN** the `.jpg` files have `valid_from` set but carry no `changeset_id` and never appear in `docs changed-with`, while the `.md` files may still form a change-set.

### Requirement: Cold versus incremental co-change labelling
Each change-set SHALL be tagged with `metadata.changeset_kind` equal to
`"cold_full_index"` when the target collection had no prior manifest entries at the
start of the run, and `"incremental"` otherwise. The `changed-with` output SHALL
surface this kind so users can distinguish co-location-dominated cold-index
groupings from incremental edit co-change.

#### Scenario: Cold first index is labelled distinctly from later edits
- **GIVEN** an empty collection indexed for the first time, then a later incremental run that edits some files
- **WHEN** change-sets are produced in each run
- **THEN** the first run tags its change-sets `cold_full_index`, the later run tags its change-sets `incremental`, and `docs changed-with` shows the kind for a queried document.

### Requirement: Small-batch and all-noise co-change fallback
The co-change pass SHALL fall back to deterministic connected-components clustering
(single-linkage at a distance threshold) so that genuinely-close files still form a
change-set in cases where HDBSCAN produces none. The fallback SHALL trigger when
`cochange_fallback_enabled` is true (default) AND either the number of changed,
non-excluded files is at or below `cochange_fallback_max_n` (default 8) OR HDBSCAN
labelled every file as noise. In the fallback, two files SHALL be placed in the same
candidate cluster when their pairwise composite distance is at or below
`cochange_distance_eps` (default 0.35), with membership extended transitively
(connected components). Fallback candidate clusters SHALL pass through the same
time-gap split and cluster-size cap as the HDBSCAN path, SHALL be deterministic
(stable across re-runs), and SHALL produce the same `ChangeSet` shape (deterministic
`changeset_id`, `relates_to` + `before` edges).

#### Scenario: A small incremental edit of related files forms a change-set
- **GIVEN** four related files in one folder edited within the same short window (a normal incremental edit) for which HDBSCAN labels every file as noise
- **WHEN** the co-change pass runs with the fallback enabled
- **THEN** the four files whose pairwise distance is within `cochange_distance_eps` are unioned into one change-set with a deterministic `changeset_id`, and its members are linked by `relates_to` (entity `changeset:<id>`) and `before` edges.

#### Scenario: Distant files are not unioned by the fallback
- **GIVEN** the fallback path with two files whose pairwise composite distance exceeds `cochange_distance_eps`
- **WHEN** connected-components clustering runs
- **THEN** the two files are not placed in the same change-set unless a chain of intermediate files each within the threshold connects them.

### Requirement: Blocked co-change clustering
The co-change pass SHALL, when `cochange_block_by_folder` is enabled (default),
partition the changed files into clustering blocks keyed by parent folder and a
coarse modified-time bucket (`floor(mtime / cochange_time_bucket_seconds)`) before
clustering, and SHALL cluster within each block independently so that files in
different folders or different time buckets are never compared. Blocks SHALL be
processed in a deterministic sorted order, and the change-sets produced SHALL be
deterministic across repeated runs and across input ordering. When blocking is
disabled, the pass SHALL run a single global clustering over all changed files
(subject to the partition-size ceiling).

#### Scenario: Two folders cluster independently
- **GIVEN** changed files in two different folders, each folder containing a dense burst edited close in time, and blocking enabled
- **WHEN** the co-change pass runs
- **THEN** each folder forms its own block, files in different folders are never compared, and each burst yields its own change-set.

#### Scenario: Blocking can be disabled for a global pass
- **GIVEN** `cochange_block_by_folder` is false and a corpus smaller than the partition-size ceiling
- **WHEN** the co-change pass runs
- **THEN** all changed files are clustered in a single global pass.

### Requirement: Vectorized co-change distance with numerical parity
The co-change pass SHALL compute the modified-time term of the per-block composite
distance matrix with vectorized array operations. The folder-path and content terms
MAY use bounded per-block loops so that the result stays exact: the composite
distance MUST equal the prior scalar composition of the modified-time, folder-path,
and content terms within a small floating-point tolerance (1e-9), so that a single
global block reproduces the prior clustering result. The speed-up comes from
blocking, not from vectorizing every term.

#### Scenario: Vectorized distance matches the scalar oracle
- **GIVEN** a block of changed files with mixed folders, modified-times, and embeddings (some missing)
- **WHEN** the vectorized distance matrix is built
- **THEN** every entry equals the scalar time/path/content composition for that pair within floating-point tolerance, including the content-term drop when an embedding is missing.

### Requirement: Co-change partition-size ceiling
The co-change pass SHALL cap any single clustering block at
`max_cochange_partition_size` files (default 2000); a block exceeding the cap SHALL
be truncated to its first members in `(mtime, doc_id)` order, the truncation SHALL
be reported, and the truncation SHALL apply in both the blocked and the single-global
clustering paths so no clustering pass allocates an unbounded distance matrix.

#### Scenario: An oversized block is truncated and reported
- **GIVEN** a single block containing more files than `max_cochange_partition_size`
- **WHEN** the co-change pass runs
- **THEN** only the first `max_cochange_partition_size` files (by mtime then doc_id) are clustered, a truncation notice reporting the dropped count is emitted, and no distance matrix larger than the cap squared is allocated.
