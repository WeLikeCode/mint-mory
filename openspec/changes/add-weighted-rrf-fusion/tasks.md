# Tasks — add-weighted-rrf-fusion

## 1. Scoring
- [x] 1.1 Add `weights: Sequence[float] | None = None` to `rrf_merge`; uniform
  default reproduces today's formula; weighted path uses `weights[i]/(k+rank)`;
  `ValueError` on length mismatch; `from collections.abc import Sequence`.

## 2. Config
- [x] 2.1 Add `SearchSettings` (`MINTMORY_SEARCH_` prefix) with
  `vector_rrf_weight: float = Field(default=1.0, ge=0.0, le=16.0)`.

## 3. Storage wiring
- [x] 3.1 `StorageAdapter.__init__`: add `vector_rrf_weight: float | None = None`
  + `self._vector_rrf_weight`.
- [x] 3.2 Add `_resolve_vector_rrf_weight()` (lazy `SearchSettings`, import-in-method).
- [x] 3.3 Apply weighted fusion at BOTH sites (`search` + `about`/search-around),
  vector weighted, lexical 1.0, single-source fast path preserved.

## 4. Tests
- [x] 4.1 `test_scoring.py`: uniform==default; weighted reorders; length-mismatch
  raises; determinism.
- [x] 4.2 `test_search.py`/`test_storage.py`: default 1.0 == today (regression);
  weight=5.0 reorders a vector-strong/lexically-weak record up; lazy resolve.
- [x] 4.3 `test_config.py`: default 1.0; env parse; bounds.

## 5. Gates
- [x] 5.1 `ruff check . && ruff format --check . && mypy packages && pytest -q` (cov ≥ 80).
