# Change: Fix + improve search recall and ranking

**ID:** `improve-search-recall`
**Status:** IMPLEMENTED
**Capability:** `search`
**Owner:** team-lead (Claude)

## Why

A search for `video wall display credentials login` returned nothing, although a
file `Acme - credentials.txt` (indexed from OneDrive) contained the data.
Investigation found **five** distinct problems, in order of impact:

1. **Search crashed.** The hybrid vector phase did `float(row["dist"])` where
   `dist` is **NULL** — `vec_distance_cosine` returns NULL when a stored
   embedding has a different dimension than the query (the shared `hermes.db`
   holds embeddings from multiple embedders/dims). One such row aborted the whole
   search → the user saw "nothing". (Root cause.)
2. **Text file content was never indexed.** `index-tree` recorded `.txt`/`.md`
   files as metadata + folder-context only; the body (which held the terms) was
   not in the DB. Text files are tiny/cheap, unlike the 35 GB of online-only
   images that motivated metadata-only — they should be full-texted by default.
3. **No partial-word matching.** The file says `VIDEOWALL` (one token); whole-token
   FTS never matched `video`.
4. **Relevance was swamped by recency/usefulness.** `base_relevance` from RRF is
   ~0.02, but `recency_bonus` is up to 0.1 — so a recently-accessed memory
   outranked a strong text match. The right text hit ranked 49th.
5. **Space-split compounds didn't match.** `video wall` (two words) could not
   reach `videowall` (one token).

## What changed

1. **Crash guard** (`storage.search`): skip vector rows with NULL distance
   (mixed-dimension embeddings) instead of crashing; they still contribute via FTS.
2. **Text-content by default** (`index-tree --text-content`, default on): small
   plain-text files (`.txt/.md/.log/.rst`, ≤ `--text-max-kb`) are full-texted
   inline — no markitdown, no download budget. Heavy binary docs still need
   `--content`.
3. **Prefix FTS** (`_sanitise_fts_query`): tokens ≥3 chars become prefix queries
   (`"video"*` matches `videowall`).
4. **Relevance normalisation** (`storage.search`): min-max scale base relevance to
   [0, 1] so text relevance dominates and usefulness/recency tie-break (the right
   hit went 49th → 1st for `videowall`).
5. **Adjacent-token concatenation** (`_sanitise_fts_query`): `video wall` also
   queries `videowall*` (and `log in` → `login`).

## Result (live, `hermes.db`)

| query | creds-file rank before | after |
|---|---|---|
| `videowall` | 49 | **1** |
| `video wall display credentials login` | crash → nothing | **9 (first page)** |

## Impact

- **Code:** `packages/core/src/mintmory/core/storage.py` (`_sanitise_fts_query`,
  `search`), `packages/cli/src/mintmory/cli/main.py` (`index-tree --text-content`).
- **Tests:** `test_search.py` (+4 regressions), `test_cli.py` (text-content).
- **Data:** re-indexed the OneDrive collection so 28 text files gained full text.
- **Back-compat:** ranking changes affect ordering only; FTS broadening only adds
  recall. No schema change.

## Not done (offered follow-up)
True **substring** matching (`wall` inside `videowall`) needs an FTS5 **trigram**
tokenizer (a second FTS table + backfill). Prefix + concatenation cover the common
compound-word cases; trigram is the next step if mid-token matching is needed.
