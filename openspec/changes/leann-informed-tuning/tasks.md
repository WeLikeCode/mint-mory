# Tasks — `leann-informed-tuning`

Disjoint file ownership for the Sonnet implementation workflow.

## 1. Hub-aware pruning — owns `core/config.py` + `core/dreaming.py`
- [x] 1.1 Add `hub_cap_multiplier` (1.0) + `hub_degree_percentile` (0.9) to `LinkSettings` (design §1a).
- [x] 1.2 Make `_cap_per_node` hub-aware with a 1.0 no-op fast path; wire the caller (design §1b).

## 2. Pluggable vector phase — owns `core/storage.py`
- [x] 2.1 Extract the inline vector block into `_vector_scores(...)`, byte-identical, NULL-guard kept;
      call it from `search()` (design §2).

## 3. Tests — owns `tests/test_dreaming.py`, `tests/test_search.py`, `tests/test_storage.py`
- [x] 3.1 Hub-pruning: 1.0 no-op equality + 2.0 hub-keeps-more (design §5).
- [x] 3.2 `_vector_scores` extraction stays green + empty/non-empty cases.
- [x] 3.3 Re-embed guard regression (design §3).

## 4. Docs — owns `docs/architecture/ADR-0006-vector-search-scale.md` + `docs/EXPERIMENTS.md`
- [x] 4.1 ADR-0006 (brute-force → vec0/hnswlib at ~100k; never LEANN) (design §4).
- [x] 4.2 EXPERIMENTS.md hub-pruning knob entry.

## 5. Review & integration (orchestrator, Opus)
- [x] 5.1 Verify gates (pytest/ruff/format/mypy).
- [x] 5.2 Independent Opus reviewer checks conformance + correctness + no-op invariant.
- [x] 5.3 Orchestrator applies all fixes, re-runs gates, commits.
