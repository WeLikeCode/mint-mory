# Change: LEANN-informed tuning (borrow ideas, adopt nothing)

**ID:** `leann-informed-tuning`
**Status:** proposed
**Capabilities:** `dreaming`, `search`
**Owner:** orchestrator (Opus)

## Why

The LEANN analysis (arXiv 2506.08276; see the conversation record / brainstorm
shortlist) concluded: **do not adopt the LEANN library or either of its value
props** — its storage-via-recompute premise is *inverted* for MintMory's tiny,
cheap-to-recompute hashing embeddings (recompute is ~86 µs/doc, not free, and the
2 KB BLOB is correct to store), and its ANN deliberately trades search latency
*up* for storage, breaking MintMory's single-file pure-Python ethos with a
FAISS + libomp/Boost/Protobuf/ZeroMQ/MKL footprint and a second on-disk index.

But the analysis surfaced a few **cheap, ethos-fitting wins** worth doing now, and
one decision worth recording so this isn't re-litigated. This change implements the
shortlist.

## What changes

1. **Hub-aware concept-graph pruning** (`dreaming` step 2). LEANN's one
   transferable idea: a uniform per-node degree cap can sever **hub** concepts
   that hold a cluster together. Make `_cap_per_node` give high-degree hub nodes a
   higher cap. Gated by new `MINTMORY_LINK_*` knobs that **default to today's exact
   behaviour** (no-op until measured), per the config-as-experiment discipline.
2. **Pluggable vector phase.** Extract MintMory's brute-force vector scan out of
   `search()` into a `_vector_scores(...)` method (mirroring `_fts_scores` /
   `_trigram_scores`), so an ANN backend can replace it later without touching the
   fusion logic. Behaviour identical today; this is seam-making, not a new index.
3. **Lock the re-embed guard.** `update_memory` already recomputes the embedding
   only on a real content change — verified in source. Add a regression test so
   that correct (already-implemented) behaviour can't silently regress. (The
   brainstorm's "recompute-don't-store" idea is explicitly NOT built — it would be
   a ~1.4 s/query regression at 16k to save ~33 MB.)
4. **ADR-0006 — vector-search scale strategy.** Record the decision: brute-force
   until ~100k–500k memories; then `sqlite-vec`'s `vec0` ANN (once stable v1) or
   `hnswlib`; **never LEANN** — with the crossover numbers and rationale.

## What this explicitly does NOT do
Adopt LEANN (library or optional extra); build recompute-don't-store; add an ANN
index now (premature by 6–30×); import two-level traversal / dynamic batching.

## Impact
- **Code:** `core/config.py` (LinkSettings knobs), `core/dreaming.py`
  (`_cap_per_node`), `core/storage.py` (`_vector_scores` extraction).
- **Tests:** `tests/test_dreaming.py`, `tests/test_search.py`/`test_storage.py`.
- **Docs:** `docs/architecture/ADR-0006-vector-search-scale.md`,
  `docs/EXPERIMENTS.md` (hub-pruning knob entry).
- **Back-compat:** all defaults reproduce today's behaviour (hub multiplier = 1.0
  = uniform cap; vector phase byte-identical). No schema change, no migration.
