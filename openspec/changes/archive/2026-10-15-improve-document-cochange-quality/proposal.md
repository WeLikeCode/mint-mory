# Change: Improve document co-change quality (MM-34)

## Why

MM-33 shipped observed co-change for `index-tree` (HDBSCAN over a composite
time+path+content distance). A live run against a 2913-file OneDrive folder (cold
index) showed the *clustering is honest but the change-sets are not trustworthy*:

1. **Path-dominance creates impossible change-sets.** The worst change-set spanned
   **2391 days (6.5 years)** — ten unrelated documents that merely share one folder.
   Once `path_distance = 0` and the content term is weak, the time term cannot pull
   them apart, so HDBSCAN happily groups files edited six years apart. No reasonable
   reader calls those "changed together."
2. **Bulk/binary dumps form giant junk clusters.** The largest change-set was
   **890 files** — a folder of timelapse `.jpg` frames written at one instant. Image
   and binary file types are not knowledge and create huge useless clusters that
   pollute every member's `changed-with` result.
3. **Cold first index measures co-LOCATION, not co-CHANGE.** On a first/bulk index
   every file is "new" and OneDrive stamps files at sync time, so 93% of change-sets
   were single-folder with a **median intra-set mtime span of 0 days**. True
   edit-co-change only emerges on incremental runs, but MM-33 labels both identically,
   so users cannot tell an inferred co-location blob from a real co-edit.
4. **Body-text chunks lack recency.** Full-texted files create body chunks
   (`category="fact"`, `source="document"`) with **no** `valid_from`/`modified_source`,
   so the searchable body of a document carries no recency signal even though the
   file-record does.
5. **HDBSCAN fails the primary use case (small incremental edits).** A second live
   run proved that editing **4 tightly-related files** in one folder at one moment
   (pairwise distances ~0.03 — an obvious single group) yields **zero** change-sets:
   HDBSCAN labelled all four as noise. HDBSCAN needs density *contrast* that a small
   uniform edit batch lacks, so "I changed these few files together" — the headline
   use case — produces no co-change at all.

These are correctness defects: today a user running `docs changed-with` on a real
document can get back ten files last touched in 2019 plus 800 timelapse frames, while
a real incremental edit of a handful of files returns nothing.

## What changes

All changes are scoped to the co-change pass and document recency; the existing
distance/HDBSCAN core and the storage/apply path are reused, not replaced.

- **A. Hard time-gap guard (post-cluster split).** After HDBSCAN, split every
  cluster wherever an internal **adjacent** mtime gap exceeds
  `max_cochange_gap_seconds` (new knob, default 24h). Sub-groups that fall below
  `min_cluster_size` after splitting become noise. This *guarantees* no change-set
  spans an internal gap larger than the threshold, killing the 6.5-year cluster. A
  pre-cluster distance clamp was rejected (see design): HDBSCAN's density linkage can
  still bridge far points through intermediates, so only a post-cluster split is a
  true invariant.
- **B. Cluster-size cap + non-knowledge type exclusion.** Exclude image/binary/dump
  suffixes from co-change **collection** (reusing `ARTIFACT_SUFFIXES` plus a new
  `IMAGE_SUFFIXES` set, extendable via `cochange_exclude_suffixes_csv`); excluded
  files are still indexed and still get recency — only co-change skips them. After
  clustering, **drop** any change-set larger than `max_cochange_cluster_size`
  (default 50) with a one-line warning. This kills the 890-file blob.
- **D. Body-chunk recency.** Stamp body-text chunks with `valid_from = mtime` and
  `metadata.modified_source = "fs_mtime"` (and a `record_role` discriminator so the
  document timeline keeps showing one row per file, not per chunk). Body chunks do
  NOT receive `changeset_id` — the file-record stays the single co-change node.
- **E. Cold-vs-incremental honesty label.** Tag each change-set with
  `metadata.changeset_kind` = `"cold_full_index"` when the collection had no prior
  manifest entries at run start, else `"incremental"`, and surface it in
  `docs changed-with` output. Makes the co-location-vs-co-change caveat
  machine-readable, not just prose.
- **F. Hybrid small-N / all-noise fallback (highest-priority correctness fix).** Keep
  HDBSCAN for large corpora, but fall back to deterministic connected-components
  (single-linkage at `cochange_distance_eps`, default 0.35) when the changed-file
  count is `<= cochange_fallback_max_n` (default 8) OR HDBSCAN returns all-noise.
  Fallback candidate clusters pass through the same gap-split (A) and size cap (B).
  This makes a normal incremental edit of a few files actually register as
  co-change — fixing defect 5.

## Impact

- Affected specs: **ingestion** (MODIFIED: co-change clustering requirement,
  recency requirement, honest-output requirement; ADDED: time-gap guard, size cap +
  type exclusion, cold/incremental labelling).
- Affected code: `core/cochange.py` (post-cluster split + size cap + kind tagging in
  `cluster_changesets`/`_changesets_from_labels`; connected-components fallback via
  `_changesets_from_components`; chunk-recency is CLI-side),
  `core/config.py` (`DocumentSettings`: new gap/cap/exclude/kind/fallback knobs),
  `core/tree_index.py` (`IMAGE_SUFFIXES` set), `cli/main.py` (filter excluded
  suffixes from the `ChangedDoc` collection; stamp body chunks; pass run-kind;
  `changed-with` prints kind).
- Migrations: none (additive metadata + new config knobs with no-op-preserving
  defaults where applicable).
- Out of scope: the O(n^2) performance rework (separate change
  `optimize-document-cochange-performance`); Microsoft Graph authoritative recency;
  cross-folder co-change tuning.
