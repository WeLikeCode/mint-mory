# Design: Optimize document co-change performance (MM-35)

Reworks the clustering compute in `core/cochange.cluster_changesets` from a single
O(n^2) pure-Python dense-matrix build into a blocked + numpy-vectorized pipeline.
Public behaviour (the change-sets produced) is preserved up to the documented
blocking trade-off; the apply/query path is untouched.

## 0. Measured baseline (the problem)

| N (changed files) | pairs | matrix build (Python loop) | matrix RAM (float64) |
|---|---|---|---|
| 2913 | ~4.24M | ~175 s | ~68 MB |
| 10000 | ~50M | minutes | ~800 MB |

Both axes are O(n^2). The per-pair Python calls dominate runtime; the dense matrix
dominates memory. Target: near-linear in N for realistic corpora, with a hard ceiling
on any single clustering pass.

## 1. `core/config.py` — new `DocumentSettings` knobs

```python
cochange_block_by_folder: bool = True            # partition by (folder, time-bucket) before clustering
cochange_time_bucket_seconds: int = Field(default=86_400, ge=1)  # coarse time bucket width
max_cochange_partition_size: int = Field(default=2000, ge=2)     # hard per-block ceiling (truncate + log)
```

`cochange_time_bucket_seconds` defaults to 24h, matching the quality change's
`max_cochange_gap_seconds`. If that knob exists (quality change merged), the block
loop uses `min(time_bucket, gap)` as the bucket width so blocking never groups files
the gap guard would split — but this change does not *depend* on the quality change:
absent it, the bucket default stands alone.

## 2. Blocking — `_build_blocks`

```python
def _build_blocks(
    docs: list[ChangedDoc], bucket_seconds: int, max_block: int
) -> list[list[ChangedDoc]]:
    """Partition changed docs into clustering blocks, deterministically."""
```

Algorithm:
1. Sort docs once by `(mtime, doc_id)` (the existing global determinism rule).
2. Key each doc by `(parent_folder_of_rel, floor(mtime / bucket_seconds))`.
   `parent_folder` = `rel.rsplit("/", 1)[0]` (root files share the `""` key).
3. Group by key; iterate keys in **sorted order** for deterministic block order.
4. **Truncate** any block longer than `max_block` to its first `max_block` docs
   (already in `(mtime, doc_id)` order), counting truncated docs for a logged notice.

**Why `(folder, time-bucket)`.** The composite distance already makes cross-folder
pairs far via the path term, and (with the quality change) the time-gap guard splits
cross-bucket pairs anyway. So two docs that differ in folder OR in time-bucket would
not survive as co-change in the global pass either — blocking removes only
comparisons that would have been pruned. The one true semantic change: a real
co-edit that straddles a bucket boundary (e.g. files at 23:59 and 00:01 with a 24h
day-aligned bucket) could be split. Mitigation: buckets are `floor(mtime/width)` on
the raw epoch (not calendar-aligned), so the boundary is arbitrary w.r.t. human
days; and `cochange_block_by_folder = false` restores the global pass for users who
need exact cross-boundary behaviour. This is documented as the explicit trade-off.

## 3. Vectorized per-block distance — `_block_distance_matrix`

Replaces the Python double loop for a block of `k` docs (k <= max_block):

```python
def _block_distance_matrix(block: list[ChangedDoc], s: DocumentSettings) -> NDArray[np.float64]:
```

- **Time term.** `m = np.array([d.mtime for d in block])`; pairwise
  `time = np.minimum(1.0, np.abs(m[:, None] - m[None, :]) / tau)`. One broadcast,
  no loop.
- **Content term.** IMPLEMENTATION NOTE (parity-driven): a stacked
  `E_norm @ E_norm.T` matmul drifts from MM-33's scalar `_cosine_distance` by more
  than the 1e-9 parity bound, because `np.linalg.norm(matrix, axis=1)` (a different
  LAPACK reduction) does not bit-match `float(np.linalg.norm(row_f32))` per row. To
  keep the parity GATE exact, the shipped content term is computed with a bounded
  per-pair loop reusing the SAME `np.dot` + per-array `np.linalg.norm` the scalar
  oracle uses (cached per-doc norms). The vectorization win therefore comes from
  blocking (C1) + the partition cap, NOT from matmul of the content term; the
  residual per-block content cost stays O(k^2) Python but is bounded by
  `max_cochange_partition_size`. Rows with a missing embedding (None) drop the
  content weight from the denominator; a present-but-zero-norm embedding keeps
  content at the neutral 0.5 (matching MM-33 exactly). These two cases are distinct.
- **Path term.** Pre-split each `rel` into parent-dir parts once; compute pairwise
  common-prefix length and depths with a small vectorized routine (or a tight loop
  over the `<= max_block` rows — bounded and cheap). Same formula as MM-33's
  `_path_distance`: `(depth_a + depth_b - 2*common) / max(1, depth_a + depth_b)`.
- **Combine.** `D = (w_t*time + w_p*path + w_c_eff*content) / denom`, where
  `w_c_eff`/`denom` are per-pair arrays reflecting the content-drop mask. Diagonal
  forced to 0.0; matrix symmetric by construction.

**Numerical-parity requirement.** `_block_distance_matrix` MUST produce values
equal (within float tolerance, e.g. 1e-9) to MM-33's scalar `_time_distance` /
`_path_distance` / `_cosine_distance` composition for the same pair, so that — with
blocking disabled and the whole corpus in one block — the clustering result is
identical to MM-33. This parity is a test gate.

## 4. Block loop in `cluster_changesets`

```python
if s.cochange_block_by_folder:
    blocks = _build_blocks(sorted_docs, bucket, s.max_cochange_partition_size)
else:
    blocks = [sorted_docs[: s.max_cochange_partition_size]]  # single block, still capped
for block in blocks:
    if len(block) < s.min_cluster_size:   # too small to cluster
        continue
    D = _block_distance_matrix(block, s)
    hdb = HDBSCAN(metric="precomputed", min_cluster_size=s.min_cluster_size).fit(D)
    # ... existing label -> ChangeSet assembly, per block ...
```

- HDBSCAN runs once per block; its complexity is now bounded by the block size.
- The single-block (blocking-off) path still applies `max_cochange_partition_size`
  as a hard ceiling so a pathological run can never allocate an unbounded matrix.
- Change-set assembly (`_changesets_from_labels`, the deterministic `changeset_id`,
  edges, order) is unchanged and runs per block; ids stay unique because they hash
  the block members' doc_ids + max mtime.
- Truncated-doc count is returned/logged so the operator knows a block was capped.

## 5. Complexity & expected improvement

- Old: one matrix, O(N^2) time and memory.
- New: `sum_i O(k_i^2)`. With `B` blocks of mean size `k_bar`, that is
  `~B * k_bar^2 = N * k_bar`. On the live corpus (93% single-folder, median 0-day
  span) most blocks are tiny, so this is effectively O(N) and **sub-second** vs
  175 s. Peak matrix RAM falls from one 68 MB matrix to the largest single block's
  `k_max^2 * 8` bytes (e.g. a 2000-cap block = ~32 MB worst case, typically far
  less). The time term IS vectorized (numpy broadcast); the content/path terms keep
  bounded per-pair loops for exact parity (see §3), so within a single large block
  the per-pair Python overhead remains — bounded by `max_cochange_partition_size`.
  The dominant real-world win is blocking (C1): it shrinks `k_i` so the residual
  per-pair cost is small. (Note: the effective bucket width is
  `min(cochange_time_bucket_seconds, max_cochange_gap_seconds)`, so lowering the gap
  guard also shrinks blocking buckets.)

## 6. Edge cases

- **One giant single-folder block** (e.g. 5000 files one folder, one bucket):
  truncated to `max_cochange_partition_size` (2000) with a logged notice; the cap
  bounds the worst case. (The quality change's size cap then drops the resulting
  oversized cluster — complementary, not conflicting.)
- **All files at the root** (`rel` has no `/`): single folder key `""`; still
  partitioned by time-bucket.
- **Blocking disabled:** one capped block; with the corpus under the cap and one
  block, output is numerically identical to MM-33 (parity test).
- **Empty / `<2` docs or `<2` per block:** no clustering; empty result (unchanged).
- **Missing embeddings in a block:** vectorized content mask reproduces MM-33's
  per-pair content-drop and neutral-0.5 behaviour exactly.

## 7. Testing

- **Parity (`test_cochange.py`):** with `cochange_block_by_folder=false` and a corpus
  smaller than the cap, `_block_distance_matrix` matches the scalar distances within
  1e-9 and `cluster_changesets` returns the same change-sets as the MM-33 loop
  (keep the old scalar functions as the oracle).
- **Blocking correctness:** two folders each with a dense burst -> blocks isolate
  them; cross-folder pairs never compared; same change-sets as the (slower) global
  pass would give for these well-separated inputs.
- **Determinism:** block order and change-set ids stable across repeated runs and
  across input shuffles (post sort-first).
- **Truncation:** a block above `max_cochange_partition_size` is truncated to the
  first N by (mtime, doc_id); truncated count reported.
- **Vectorized terms:** unit tests asserting time/path/content broadcast results
  equal the scalar helpers for random inputs (property-style).
- **Perf smoke (optional, non-gating):** a synthetic 3000-file multi-folder input
  clusters in well under the old timing (assert wall-clock under a generous bound,
  or assert no dense N^2 matrix is allocated by checking the max block size).

## 8. Gates

`ruff` + `ruff format` clean; `mypy --strict` clean; `pytest >= 80%`; full suite
green; `openspec validate optimize-document-cochange-performance --strict`.
