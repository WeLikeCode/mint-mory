# Change: Optimize document co-change performance (MM-35)

## Why

MM-33's co-change clustering builds a **dense precomputed N×N distance matrix in a
pure-Python double loop**, then runs HDBSCAN over it. A live run measured the cost:

- 2913 changed files -> ~4.2M unordered pairs -> **~175 s** wall-clock to build the
  matrix, plus a **~68 MB** float64 matrix held in memory.
- Both time and memory are **O(n^2)**. At 10k files the matrix alone is ~800 MB and
  the build time is minutes; the feature does not scale past a single mid-sized
  folder, which is exactly the use case (OneDrive / network shares routinely hold
  tens of thousands of files).

The pure-Python triple-nested arithmetic (`_time_distance`/`_path_distance`/
`_cosine_distance` called per pair) is the dominant term, and the dense matrix is
the memory ceiling. This blocks the feature on any realistically large corpus.

## What changes

Two correctness-preserving optimizations, gated so the existing global behaviour
stays available:

- **C1. Block (partition) candidates before clustering.** Partition the changed
  files into blocks keyed by `(folder, coarse-time-bucket)`, where the time bucket
  is `floor(mtime / bucket_seconds)` (bucket defaults to the co-change time-gap, so
  two files that the time-gap guard would split anyway never share a block).
  Cluster **within each block independently**. Files in different folders, or more
  than a bucket apart in time, are never compared — which the path term and the
  time-gap guard already separate, so no real co-change is lost. This turns one
  O(N^2) matrix into many small O(k_i^2) matrices: total work drops from O(N^2) to
  O(sum k_i^2) ~ O(N * mean-block-size). For the 2913-file run (93% single-folder,
  median 0-day span) this is sub-second.
- **C2. Vectorize the per-block distance with numpy.** Replace the Python double
  loop with broadcast numpy: a vectorized pairwise time-difference, a vectorized
  cosine (matrix-multiply of L2-normalised embeddings), and a vectorized path
  distance over pre-split path-part arrays. This removes the per-pair Python call
  overhead even inside a block.
- **C3. Hard partition-size ceiling.** Cap any single block at
  `max_cochange_partition_size` files; if a block exceeds it, keep the
  earliest-by-(mtime, doc_id) N and log a one-line truncation notice. This bounds
  worst-case memory/time even for a pathological single-folder dump.

Determinism is preserved: blocks are processed in a stable sorted order, the
global `(mtime, doc_id)` sort still drives within-block order and `changeset_id`,
and the same inputs always yield the same change-sets. Blocking is on by default
(`cochange_block_by_folder = true`); setting it false restores MM-33's single
global pass for users who explicitly want cross-folder/cross-window co-change.

## Impact

- Affected specs: **ingestion** (ADDED: blocked clustering, vectorized distance,
  partition-size ceiling; MODIFIED: the clustering requirement to note blocking).
- Affected code: `core/cochange.py` (new `_build_blocks`, vectorized
  `_block_distance_matrix`, block loop in `cluster_changesets`), `core/config.py`
  (`DocumentSettings`: `cochange_block_by_folder`, `cochange_time_bucket_seconds`,
  `max_cochange_partition_size`).
- Migrations: none.
- Out of scope: an ANN/approximate-neighbour backend; incremental re-clustering
  across runs; GPU. The quality fixes (time-gap guard, size cap, type exclusion)
  live in the separate `improve-document-cochange-quality` change; this change is
  shippable independently of it (it consumes the gap value if present, else its own
  `cochange_time_bucket_seconds` default).
