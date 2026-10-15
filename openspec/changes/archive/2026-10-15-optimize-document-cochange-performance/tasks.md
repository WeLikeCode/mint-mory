# Tasks: Optimize document co-change performance (MM-35)

## 1. Config (`core/config.py`)
- [x] Add to `DocumentSettings`: `cochange_block_by_folder` (default True),
  `cochange_time_bucket_seconds` (default 86_400, ge=1),
  `max_cochange_partition_size` (default 2000, ge=2).
- [x] Tests (`test_config.py`): defaults + bounds.

## 2. Blocking (`core/cochange.py`)
- [x] `_build_blocks(docs, bucket_seconds, max_block)`: sort by (mtime, doc_id);
  key by `(parent_folder, floor(mtime / bucket_seconds))`; group; iterate keys in
  sorted order; truncate blocks above `max_block` (keep first N, count truncated).
  When the quality change's `max_cochange_gap_seconds` is present, use
  `min(bucket_seconds, gap)` as the effective bucket.
- [x] Tests: two folders -> two blocks; cross-folder/cross-bucket pairs never share
  a block; deterministic block order; truncation keeps first N by (mtime, doc_id)
  and reports the truncated count.

## 3. Vectorized distance (`core/cochange.py`)
- [x] `_block_distance_matrix(block, settings)`: broadcast time term; matrix-mul
  cosine (L2-normalised, zero-norm -> neutral 0.5); vectorized path term over
  pre-split parts; per-pair content-drop mask and effective denominator; diagonal 0;
  symmetric.
- [x] Numerical-parity test vs the MM-33 scalar `_time_distance`/`_path_distance`/
  `_cosine_distance` composition (within 1e-9) for random inputs.

## 4. Block loop (`core/cochange.py`)
- [x] In `cluster_changesets`: build blocks (or one capped block when
  `cochange_block_by_folder` is false); skip blocks below `min_cluster_size`; fit
  HDBSCAN per block; assemble change-sets per block via the existing path; report
  the truncated-doc count.
- [x] Keep `changeset_id`/edges/order assembly unchanged and deterministic.
- [x] Tests: blocking-off + sub-cap corpus reproduces MM-33 change-sets exactly
  (parity); blocking-on isolates well-separated bursts into the same change-sets;
  determinism across input shuffles; truncation path exercised.

## 5. CLI (`cli/main.py`)
- [x] Surface a logged one-line notice when any block is truncated
  (`partition truncated: N files dropped from a block of M`).
- [x] No flag changes required (knobs are env-driven via `MINTMORY_DOC_*`).

## 6. Docs
- [x] README/onboarding: document blocking, the `(folder, time-bucket)` trade-off
  (cross-folder/cross-boundary co-change suppressed when blocking is on), the
  truncation ceiling, and the new `MINTMORY_DOC_*` knobs.

## 7. Gates
- [x] `ruff` + `ruff format` clean; `mypy --strict` clean.
- [x] `pytest` >= 80% coverage; full suite green.
- [x] `openspec validate optimize-document-cochange-performance --strict`.
