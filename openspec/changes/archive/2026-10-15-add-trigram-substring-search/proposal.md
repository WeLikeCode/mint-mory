# Change: FTS5 trigram substring search + N-way RRF fusion

**ID:** `add-trigram-substring-search`
**Status:** proposed
**Capability:** `search`
**Owner:** team-lead (Claude)

## Why

After `improve-search-recall` (MM-13), prefix + adjacent-token concatenation let
`video` match `videowall` and `video wall` reach it — but **mid-token substrings
still miss**: a search for `wall` does not match `firewall`/`videowall`, and any
typo/partial inside a token is invisible. Whole-token (porter/unicode61) FTS
cannot do substring matching.

SQLite's FTS5 **`trigram` tokenizer** indexes every 3-char sequence, enabling true
**substring** MATCH (`wall` → any token containing `wall`). It is available in our
SQLite (3.50.4, verified). Adding it as a **secondary recall source**, fused with
the existing porter-FTS (bm25-ranked) and vector phases, closes the gap.

### On BM25
FTS5's `bm25()` is **already** the ranking function used for the porter-FTS source
(`_fts_scores`). This change applies the same `bm25()` to the trigram source and
**fuses all sources via Reciprocal Rank Fusion (RRF)** — so bm25 relevance, trigram
substring recall, and vector similarity all contribute. No separate BM25 engine is
needed (and FTS5 `bm25()` exposes only per-column weights, of which we have one).

## What changes

1. **`memories_trigram`** — a second **standalone** FTS5 table with
   `tokenize='trigram'`, kept in sync by **rowid-based** triggers. Created
   **best-effort** (like the `sqlite-vec` load): a `_trigram_loaded` flag; if the
   tokenizer is unavailable, search silently degrades to porter-FTS + vector.
   Existing DBs are **backfilled** once via `INSERT…SELECT`. (An external-content
   variant was tried first but corrupts the index after a bulk `'rebuild'` —
   "database disk image is malformed" on the next UPDATE; `_ensure_trigram`
   migrates any such legacy table. See `design.md` §2b.)
2. **`_trigram_scores()`** — substring candidates ranked by `bm25(memories_trigram)`.
3. **N-way RRF** — `scoring.rrf_merge` becomes variadic (`*score_dicts`), fusing
   porter-FTS + trigram + vector (each when present). Backward compatible with the
   existing 2-arg calls.
4. **Off switch** — `StorageAdapter(enable_trigram=True)` (default on) so the
   substring source can be disabled if it adds noise for a given corpus.

Relevance is still min-max normalised to [0, 1] (MM-13) before usefulness/recency
tie-breakers, so the broader trigram recall does not distort ranking.

## Impact

- **Code:** `packages/core/src/mintmory/core/scoring.py` (variadic `rrf_merge`),
  `packages/core/src/mintmory/core/storage.py` (trigram table/triggers/backfill,
  `_trigram_scores`, `_trigram_match_expr`, `search` fusion, `enable_trigram`).
- **Tests:** `test_scoring.py` (variadic RRF), `test_search.py` (substring),
  `test_storage.py`/`test_schema.py` (trigram table best-effort).
- **Data:** the live `hermes.db` is backfilled into `memories_trigram` on first
  `initialise()` after the change (one-time `rebuild`).
- **Back-compat:** no change to the `memories`/`memories_fts` schema; trigram is
  additive and best-effort. Pure recall/ranking improvement.
