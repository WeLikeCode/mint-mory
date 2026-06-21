# Capability: ingestion (delta)

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Observed co-change via clustering of changed files
The co-change pass SHALL group the files whose content changed in an `index-tree`
run (added or updated, excluding co-change-excluded suffixes) into change-sets by
clustering them with HDBSCAN over a composite distance combining modified-time
proximity, folder-path distance, and content-embedding similarity — or, per the
small-batch and all-noise fallback requirement, by deterministic
connected-components clustering — then applying the time-gap split and the
cluster-size cap. Each surviving cluster SHALL receive a
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

### Requirement: Honest co-change semantics in output
The `changed-with` query output SHALL label co-change results as observed (time +
folder + content) and explicitly NOT a version-controlled commit, AND SHALL display
the change-set kind (`cold_full_index` versus `incremental`) so users do not mistake
a cold-index co-location grouping for an atomic or incremental edit change-set.

#### Scenario: Output states the limit and the kind
- **WHEN** `docs changed-with <path>` prints peers
- **THEN** the output includes a label indicating the grouping is observed co-change (not a version-controlled commit), shows the change-set kind, and shows each peer's edge strength and observed time.
