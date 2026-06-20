# Design & FROZEN interface contract — `add-weighted-rrf-fusion`

Implementers MUST match these signatures, names, defaults, and behaviours exactly.
Where intuition and this doc disagree, this doc wins. Overarching invariant
(MintMory config ethos): **every new default reproduces today's behaviour** so the
knob is a tracked experiment. Here that means `vector_rrf_weight = 1.0` yields a
byte-identical fusion result to the current unweighted `rrf_merge`.

---

## 1. `core/scoring.py` — `rrf_merge` gains optional per-source weights

New signature (keep `*score_dicts` and `k`):
```python
def rrf_merge(
    *score_dicts: dict[str, float],
    k: int = 60,
    weights: Sequence[float] | None = None,
) -> dict[str, float]:
```
(`from collections.abc import Sequence` at module top.)

Behaviour:
- **No-op fast path / default:** `weights is None` ⇒ every source contributes
  `1.0 / (k + rank)` — EXACTLY today's formula and result. (Keeps every existing
  `test_scoring` assertion green.)
- **Weighted path:** `weights` is a sequence aligned 1:1 with the *positional*
  `score_dicts` (same length, same order). Source `i` contributes
  `weights[i] / (k + rank)`. Empty dicts are still skipped (a skipped dict simply
  contributes nothing; its weight is ignored). If `len(weights) != len(score_dicts)`
  raise `ValueError`.
- `weights=[1.0, 1.0, ...]` (all ones) MUST produce a result equal to
  `weights=None` (uniform == default). Determinism and the existing tie/order
  behaviour are unchanged.

Docstring updated to mention the optional weights and the uniform-default equivalence.

---

## 2. `core/config.py` — `SearchSettings`

Add a settings class next to the others (keep the commented-knob style):
```python
class SearchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_SEARCH_", extra="ignore")

    # Weighted RRF fusion (LEANN-recall-informed, docs/EXPERIMENTS.md §10): scale
    # the vector source's RRF contribution relative to the lexical (FTS+trigram)
    # sources. 1.0 == today's uniform fusion (NO-OP default). Recommended 3.0 for
    # real semantic embedders; leave at 1.0 for the lexical hashing default.
    vector_rrf_weight: float = Field(default=1.0, ge=0.0, le=16.0)
```

---

## 3. `core/storage.py` — wire the weight through

### 3a. `StorageAdapter.__init__`
Add a parameter (after `auto_include_cap`), stored for lazy resolution — mirroring
the existing `note_bonus` idiom:
```python
vector_rrf_weight: float | None = None,
...
self._vector_rrf_weight: float | None = vector_rrf_weight
```

### 3b. Lazy resolve helper
Resolve once, lazily, from `SearchSettings` (import inside the method to avoid the
module-load circular import, as the note settings do):
```python
def _resolve_vector_rrf_weight(self) -> float:
    if self._vector_rrf_weight is None:
        from mintmory.core.config import SearchSettings  # noqa: PLC0415

        self._vector_rrf_weight = SearchSettings().vector_rrf_weight
    return self._vector_rrf_weight
```

### 3c. Both fusion sites (`search` ~L826 and the `about`/search-around path ~L1027)
Today each builds:
```python
sources = [s for s in (fts_scores, trigram_scores, vec_scores) if s]
if not sources:
    base_scores = {}
elif len(sources) == 1:
    base_scores = sources[0]
else:
    base_scores = scoring.rrf_merge(*sources)
```
Replace with a weight-aligned version (vector weighted, lexical = 1.0). The
ordering of the tuple list MUST stay `(fts, trigram, vec)` so the vector weight
lands on the vector source:
```python
w = self._resolve_vector_rrf_weight()
paired = [
    (fts_scores, 1.0),
    (trigram_scores, 1.0),
    (vec_scores, w),
]
paired = [(s, wt) for (s, wt) in paired if s]
if not paired:
    base_scores = {}
elif len(paired) == 1:
    base_scores = paired[0][0]
else:
    base_scores = scoring.rrf_merge(
        *[s for s, _ in paired], weights=[wt for _, wt in paired]
    )
```
Everything after `base_scores` (min-max normalisation, `effective_score`,
filtering, sort, limit, graph union) is UNCHANGED. Apply the SAME edit to both
sites (keep them structurally identical).

Invariant: with `vector_rrf_weight == 1.0` the `weights` list is all ones, so
`base_scores` is byte-identical to today at both sites; the single-source fast
path is preserved (a lone vector source is returned as-is, never weighted).

---

## 4. Tests (contract)
- `test_scoring.py`: (a) `rrf_merge(a, b)` == `rrf_merge(a, b, weights=[1.0, 1.0])`
  (uniform == default, no-op proof); (b) with `weights=[1.0, 1.0, 5.0]` a doc
  ranked high ONLY by the third (vector) source outranks a doc ranked high only by
  a lexical source that the unweighted merge would have placed first; (c)
  `len(weights) != len(score_dicts)` raises `ValueError`; (d) determinism/idempotence.
- `test_search.py` / `test_storage.py`: (a) `vector_rrf_weight=1.0` (default) →
  search results identical to today on an existing fixture (regression guard);
  (b) `StorageAdapter(..., vector_rrf_weight=5.0)` → on a small fixture where a
  record is the top vector hit but weak lexically, it ranks higher than under the
  default; (c) lazy resolution reads `SearchSettings` once.
- `test_config.py`: `SearchSettings` default is `1.0`; `MINTMORY_SEARCH_VECTOR_RRF_WEIGHT=3.0`
  env parses; bounds (`ge=0.0, le=16.0`) enforced.

All gates: `pytest` (cov ≥ 80), `ruff check`, `ruff format --check`, `mypy --strict`.
