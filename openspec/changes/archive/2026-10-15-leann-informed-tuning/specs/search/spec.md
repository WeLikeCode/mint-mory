# Capability: search (delta)

## ADDED Requirements

### Requirement: Isolated, replaceable vector phase
The hybrid search vector phase SHALL be encapsulated behind a single
`_vector_scores(...)` seam (alongside `_fts_scores`/`_trigram_scores`) so the
brute-force scan can be replaced by an ANN backend later without changing the
fusion/normalisation logic. The current behaviour (brute-force cosine, NULL-distance
skip for mixed-dimension embeddings) SHALL be preserved exactly.

#### Scenario: Extraction preserves results
- **WHEN** the vector phase is moved behind `_vector_scores`
- **THEN** hybrid search returns the same results as before for the same inputs.

#### Scenario: Degrades without an embedder
- **WHEN** no embedder or sqlite-vec extension is available
- **THEN** `_vector_scores` returns an empty mapping and search falls back to the
  FTS/trigram sources.
