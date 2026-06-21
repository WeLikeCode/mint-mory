# Capability: ingestion (delta)

## ADDED Requirements

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
The co-change pass SHALL compute the per-block composite distance matrix using
vectorized array operations rather than a per-pair Python loop, and the result MUST
equal the prior scalar composition of the modified-time, folder-path, and content
terms within a small floating-point tolerance, so that a single global block
reproduces the prior clustering result.

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

## MODIFIED Requirements

### Requirement: Observed co-change via clustering of changed files
The co-change pass SHALL group the files whose content changed in an `index-tree`
run (added or updated) into change-sets by clustering them with HDBSCAN over a
composite distance combining modified-time proximity, folder-path distance, and
content-embedding similarity. To remain tractable on large corpora, the pass SHALL
partition the changed files into per-folder, per-time-bucket clustering blocks (when
`cochange_block_by_folder` is enabled) and SHALL compute each block distance matrix
with vectorized array operations, subject to a per-block partition-size ceiling.
Each cluster SHALL receive a deterministic `changeset_id`; its members SHALL carry
`metadata.changeset_id` and `metadata.changeset_observed_at`, and SHALL be linked
pairwise in `concept_links` with `relates_to` edges (`entity = "changeset:<id>"`,
`strength` from the cluster membership probability) plus `before` edges in
modified-time order. A file that does not join any cluster (HDBSCAN noise,
`min_cluster_size = 2`) SHALL NOT be placed in a change-set and SHALL receive no
co-change edges. Re-running with no new content changes SHALL NOT create new
change-sets or duplicate edges (idempotent).

#### Scenario: Two distinct edit bursts yield two change-sets
- **GIVEN** four files where two changed close in time within one folder and two changed close in time within another folder
- **WHEN** `index-tree --cochange` runs
- **THEN** two change-sets are produced, each with a deterministic `changeset_id`, its members carry that id, and the members are linked by `relates_to` (entity `changeset:<id>`) and `before` edges.

#### Scenario: A lone changed file is not co-change
- **GIVEN** a run in which exactly one file changed
- **WHEN** the co-change pass runs
- **THEN** no change-set is created and the file gets no `changeset_id` and no co-change edges.

#### Scenario: Large corpus stays tractable
- **GIVEN** a run with several thousand changed files spread across many folders
- **WHEN** the co-change pass runs with blocking enabled
- **THEN** clustering completes without building a single dense distance matrix over all changed files, and the produced change-sets are deterministic.
