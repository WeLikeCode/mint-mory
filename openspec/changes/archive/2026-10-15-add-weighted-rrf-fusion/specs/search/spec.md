# Capability: search (delta)

## ADDED Requirements

### Requirement: Vector-weighted RRF fusion

The hybrid-search fusion step SHALL support weighting the vector source's
contribution to Reciprocal Rank Fusion relative to the lexical (FTS5 + trigram)
sources, controlled by a single configuration knob `vector_rrf_weight`
(env `MINTMORY_SEARCH_VECTOR_RRF_WEIGHT`, via a new `SearchSettings`). The default
SHALL be `1.0`, which SHALL reproduce today's unweighted fusion **byte-for-byte**
(every existing search result and test unchanged). The value SHALL be bounded
`0.0 ≤ vector_rrf_weight ≤ 16.0`.

`scoring.rrf_merge` SHALL accept an optional `weights: Sequence[float] | None`
argument aligned 1:1 (length and order) with its positional `score_dicts`. When
`weights is None`, every source SHALL contribute `1.0 / (k + rank)` exactly as
today. When provided, source `i` SHALL contribute `weights[i] / (k + rank)`;
empty score dicts SHALL still be skipped; a `weights` length that does not match
the number of `score_dicts` SHALL raise `ValueError`. A uniform weights list
(all `1.0`) SHALL produce a result equal to `weights=None`.

`StorageAdapter` SHALL accept `vector_rrf_weight: float | None = None` in its
constructor and resolve it lazily from `SearchSettings` on first use (mirroring
the existing `note_bonus` / `auto_include_cap` resolution), so construction
performs no settings I/O. Both hybrid-search fusion sites (the primary `search`
pipeline and the `search-around` / `about` path) SHALL weight the **vector**
source by the resolved value while keeping FTS and trigram at weight `1.0`. The
single-source fast path (exactly one non-empty source) SHALL return that source
unweighted, and the subsequent min-max normalisation, effective-scoring,
filtering, sorting, limiting, and graph-union steps SHALL be unchanged.

#### Scenario: Default weight reproduces today's ranking
- **GIVEN** an adapter with the default `vector_rrf_weight` of `1.0`
- **WHEN** a hybrid search runs over FTS, trigram, and vector sources
- **THEN** the fused `base_scores` and the final result ordering SHALL be
  identical to the prior unweighted-RRF behaviour.

#### Scenario: Raising the vector weight promotes dense hits
- **GIVEN** an adapter constructed with `vector_rrf_weight=5.0` and a corpus
  containing a record that is the top vector (cosine) match for a query but only
  weakly matched by the lexical sources
- **WHEN** the query is searched
- **THEN** that record SHALL rank higher than it does under the default weight of
  `1.0`.

#### Scenario: rrf_merge weights are validated and uniform-equivalent
- **GIVEN** two score dicts `a` and `b`
- **WHEN** `rrf_merge(a, b, weights=[1.0, 1.0])` is compared to `rrf_merge(a, b)`
- **THEN** the results SHALL be equal
- **AND WHEN** `rrf_merge(a, b, weights=[1.0])` is called
- **THEN** it SHALL raise `ValueError`.
