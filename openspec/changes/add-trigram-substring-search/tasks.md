# Tasks — `add-trigram-substring-search`

Disjoint file ownership for parallel implementation against design.md.

## 1. Scoring — owns `packages/core/src/mintmory/core/scoring.py`
- [ ] 1.1 Make `rrf_merge` variadic (`*score_dicts`, skip empties), backward compatible.

## 2. Storage — owns `packages/core/src/mintmory/core/storage.py`
- [ ] 2.1 `enable_trigram` ctor flag + `_trigram_loaded`.
- [ ] 2.2 `_ensure_trigram` (best-effort create + triggers + one-time rebuild backfill),
      called from `initialise()`.
- [ ] 2.3 `_trigram_match_expr` + `_trigram_scores` (bm25-ranked substring).
- [ ] 2.4 `search()` N-way fusion (porter + trigram + vector); keep MM-13 normalisation
      and the NULL-distance guard.

## 3. Tests — owns `test_scoring.py`, `test_search.py`, `test_storage.py`, `test_schema.py`
- [ ] 3.1 Variadic RRF (3-way fusion + existing 2-arg cases).
- [ ] 3.2 Substring search (`wall` finds `firewall`); MM-13 tests stay green.
- [ ] 3.3 Trigram table best-effort: present when enabled, absent + search-OK when disabled.

## 4. Gates & integration (team-lead)
- [ ] 4.1 `pytest` / `ruff` / `ruff format` / `mypy` green.
- [ ] 4.2 Backfill live `hermes.db` (initialise rebuild) + verify `wall`→`videowall`/firewall.
- [ ] 4.3 Commit.
