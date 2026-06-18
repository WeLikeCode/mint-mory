# ADR-0006: Vector Search Strategy — Brute-Force Now, ANN at the Crossover

**Status:** Accepted  
**Date:** 2026-06-18  
**Deciders:** MintMory core team  
**Supersedes:** (none — vector search scaling decision)

---

## Context

MintMory's hybrid search pipeline merges three ranked lists — FTS5 full-text,
trigram, and vector cosine — via Reciprocal Rank Fusion.  The vector phase is
currently an inline brute-force cosine scan over every stored embedding using
`sqlite-vec`'s `vec_distance_cosine`.

As of this writing the production database holds **~16k memories** (high-water
mark, post-ingest).  The question before us is: should MintMory adopt an
Approximate Nearest-Neighbour (ANN) index now, and if so, which one?

### Embedding geometry

The shipped default embedder is `HashingEmbedder` (pure-Python, 512-dimensional
`float32` vectors; see ADR-0004 and EXPERIMENTS §6.3).  Each stored vector is
**2 KB** (`512 × 4 bytes`).  The full vector store for 16k memories is
**~32 MB** — comfortably within SQLite's default page cache and well within
typical RAM on developer hardware.

### Measured scan latency

Brute-force cosine over `N` stored vectors with `sqlite-vec`:

| N memories | Observed / estimated vector-phase latency |
|---|---|
| ~16k (current) | **1–15 ms** |
| ~100k | ~10–90 ms (linear extrapolation) |
| ~500k | ~50–500 ms |
| ~1M | ~0.5–2 s |

At the current scale the vector phase is sub-15 ms and is never the bottleneck
(FTS5 and trigram phases dominate for short queries; network or disk I/O
dominate for the MCP transport).  The crossover where scan latency becomes
user-perceptible (>100 ms end-to-end contribution) is approximately
**100k–500k memories** — a **6–30× growth headroom** from today's high-water
mark.

### The real `.db` bloat source

Contrary to intuition, embeddings are *not* the dominant source of database
size growth.  The main contributors are:

1. **Trigram content table** — SQLite's `content=` FTS5 option stores a full
   copy of every memory's `content` for the trigram index (approximately one
   byte per character, uncompressed at the page level).
2. **FTS5 index segments** — the full-text index on `content` is also a
   significant share of the file.
3. **Vector blobs** — only 2 KB per memory with the hashing embedder
   (`512 × float32`).  At 500k memories that is 1 GB of raw embedding data,
   but this is dwarfed by the content duplication from (1) and (2) at the same
   scale.

The storage argument for ANN indices (which keep only a compressed graph or
quantised centroids rather than the full vectors) is therefore **inverted** for
MintMory: ANN adds a second on-disk index structure without meaningfully
reducing total `.db` size.

### Why not LEANN?

LEANN (Learning-Enhanced ANN) was evaluated and **rejected**:

- **Latency moves in the wrong direction.**  LEANN trades some recall accuracy
  for faster *approximate* retrieval, but at MintMory's scale (<500k) the
  brute-force scan is already faster than any ANN construction overhead.
- **Heavy native dependencies.**  LEANN relies on FAISS, which chains in
  `libomp` / OpenBLAS / MKL (platform-dependent), `Protobuf`, and optionally
  `ZeroMQ`.  These break the single-file, pure-Python ethos (see ADR-0001).
- **Second on-disk index.**  LEANN requires a separate index file alongside the
  `.db`, complicating the "single SQLite file is the entire database" guarantee.
- **Storage win is inverted.**  The 2 KB hashing embedding makes quantisation
  savings negligible; the real bloat is trigram content duplication, not
  vectors.

---

## Decision

**Keep brute-force cosine scan (`_vector_scores`) until ~100k–500k memories,
then adopt `sqlite-vec`'s `vec0` ANN extension once it reaches stable v1, or
`hnswlib` if `vec0` ANN is not yet stable at that point.  Never LEANN.**

The vector phase is now isolated in the `_vector_scores` method on
`StorageAdapter` (parallel to `_fts_scores` and `_trigram_scores`), with the
contract:

```python
def _vector_scores(
    self, query: str, query_embedding: np.ndarray | None, limit: int
) -> dict[str, float]:
    """Vector phase of hybrid search: brute-force cosine over stored embeddings.

    Returns {memory_id: -distance} (higher = better); {} when no embedder /
    sqlite-vec / embedding is available. NULL distances (mixed-dimension
    embeddings) are skipped. Isolated behind this method so an ANN backend can
    replace the scan later without touching search()/fusion (see ADR-0006).
    """
```

Swapping in an ANN backend at the crossover requires only a new implementation
of `_vector_scores`; `search()`, RRF fusion, and normalisation are untouched.

### ANN backend selection at the crossover

| Backend | Why preferred / when |
|---|---|
| **`sqlite-vec` `vec0` ANN** | First choice: zero extra dependencies (already a `sqlite-vec` user), stores the index inside the `.db`, same single-file guarantee.  Adopt once `sqlite-vec` ships a stable v1 ANN API. |
| **`hnswlib`** | Fallback if `vec0` ANN is not stable at the crossover: pure C++ with a minimal Python binding, no FAISS/Boost/MKL chain, and well-understood recall/latency curves. |
| **FAISS / LEANN / ScaNN** | **Never** — see rationale above. |

### Crossover trigger

Re-evaluate this decision when **any** of the following is true:

- Active memory count exceeds **100k** AND vector-phase latency exceeds
  **50 ms** (measured via the OpenTelemetry `storage.vector` span).
- Active memory count exceeds **500k** unconditionally.

---

## Rationale

### Why not ANN now?

At ~16k memories the brute-force scan runs in **1–15 ms**.  Introducing an ANN
index today would:

1. Add build/update overhead (index rebuild or incremental HNSW insert on every
   `store_memory` call).
2. Risk recall regression — ANN is approximate by definition, and at this scale
   exact retrieval is free.
3. Add dependency weight for zero measurable latency gain.

### Why `sqlite-vec` first, then `hnswlib`?

`sqlite-vec` is already a runtime dependency.  Adding `vec0` ANN (when stable)
costs zero extra packages and keeps the single-file guarantee: the ANN graph
lives inside the `.db` alongside memories and FTS segments.

`hnswlib` is the lightest standalone ANN library: header-only C++, Python wheel
ships as a self-contained binary, no BLAS/MKL/Protobuf chain.  Recall@10 is
typically 0.95+ at HNSW default parameters for 512-dim float32, which is more
than sufficient for MintMory's retrieval quality bar.

### Isolation rationale

Extracting the vector phase into `_vector_scores` (design §2) is the
architectural prerequisite for a future ANN swap.  Without this isolation,
the ANN migration would require diffing into the middle of the `search()` method,
with high risk of accidentally altering RRF weights or result shapes.  With
`_vector_scores` as the seam, the swap is a one-method replacement with the
same `dict[str, float]` contract.

---

## Consequences

### Positive

- **No new dependencies today.**  The brute-force path uses only `sqlite-vec`
  and `numpy`, both already present.
- **Exact recall.**  Brute-force returns the true nearest neighbours; no
  approximate recall loss until the scale at which ANN is needed.
- **Clean migration path.**  `_vector_scores` is the single seam for a future
  ANN backend; everything above it (`search()`, RRF, normalisation) is frozen.
- **Storage budget maintained.**  No second index file; the `.db` remains the
  single source of truth.

### Negative / Risks

- **Latency cliff at ~1M.**  If the memory store grows rapidly past 500k without
  a monitoring alert, the scan latency will degrade visibly (~0.5–2 s).
  Mitigate: the OpenTelemetry `storage.vector` span tracks per-call vector-phase
  latency; alert at 50 ms sustained.
- **`sqlite-vec` `vec0` ANN timeline is uncertain.**  If `vec0` ANN is still
  pre-stable when the crossover is reached, `hnswlib` is the immediate fallback.
  The `_vector_scores` interface absorbs either choice transparently.

### Neutral

- The `limit` parameter passed to `_vector_scores` is the candidate pool size
  (`pool` in `search()`), not the final result count.  This matches the
  brute-force `ORDER BY dist LIMIT ?` semantics exactly; an ANN implementation
  must honour the same `limit` for RRF correctness.

---

## References

- ADR-0001: Python monorepo / single-file / pure-Python ethos
- ADR-0004: Pluggable embedding provider (`HashingEmbedder`, 512d, 2 KB/memory)
- `core/storage.py`: `_vector_scores`, `_fts_scores`, `_trigram_scores`, `search()`
- sqlite-vec project: https://alexgarcia.xyz/sqlite-vec/
- hnswlib: https://github.com/nmslib/hnswlib
- EXPERIMENTS.md §6.3: measured vector-phase latency and recall on ~16k-memory corpus
- design.md §2 (`leann-informed-tuning`): `_vector_scores` extraction contract
