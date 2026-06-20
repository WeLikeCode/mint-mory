# Change: Weighted RRF fusion (vector-weighted hybrid search)

## Why

The LEANN-adapted recall benchmark (`docs/EXPERIMENTS.md §10`) measured a real
defect in MintMory's hybrid search: at 100k-passage scale the **unweighted** RRF
fusion over FTS + trigram + vector *lowers* recall@3 versus pure vector search —
the two lexical rank-lists out-vote the correct dense hit at the head of the list.
The regression replicates across both real semantic embedders (MiniLM: hybrid@3
0.663 vs vector@3 0.710; nomic: 0.663 vs 0.702).

The fix investigation (`docs/eval/rrf_investigation.py`) showed that **weighting
the vector source ×3–5 in RRF** recovers and overshoots the gap: recall@3
0.665 → 0.722 (+5.7pt) and recall@10 0.857 → 0.890 (+3.3pt), beating *both* the
unweighted default *and* pure-vector at both cutoffs (vector dominates the head;
lexical keeps the tail).

## What changes

- `scoring.rrf_merge` gains an optional, per-source `weights` argument. When
  omitted it behaves byte-identically to today (uniform 1.0).
- A new `SearchSettings` (env prefix `MINTMORY_SEARCH_`) exposes
  `vector_rrf_weight` with **default 1.0 — exactly today's behaviour**.
- Both hybrid-search fusion sites (`StorageAdapter.search` and the
  `search-around`/about path) weight the vector source by the configured value;
  FTS and trigram stay at weight 1.0. The single-source fast path and the
  min-max normalisation that follow are unchanged.
- `StorageAdapter.__init__` accepts `vector_rrf_weight: float | None = None`,
  resolved lazily from `SearchSettings` on first search — mirroring the existing
  `note_bonus` / `auto_include_cap` lazy-settings idiom.

This is additive and **off by default**: with `vector_rrf_weight=1.0` every
existing search result (and every existing test) is unchanged. The shipped
`hashing` embedder — where fusion already *helps* — is unaffected unless an
operator opts in.

## Impact

- Affected specs: `search`
- Affected code: `core/scoring.py` (`rrf_merge`), `core/config.py`
  (`SearchSettings`), `core/storage.py` (`StorageAdapter.__init__` + the two
  fusion sites).
- No schema change. No new dependency. Backward compatible (default = no-op).
