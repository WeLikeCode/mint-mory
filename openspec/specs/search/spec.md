# search Specification

## Purpose
TBD - created by archiving change optimize-mcp-token-usage. Update Purpose after archive.

## Requirements

### Requirement: Concise memory search projection
The `memory_search` MCP tool SHALL accept a `verbosity` parameter with values
`"full"` and `"concise"`, defaulting to `"full"`. With `"full"` the tool SHALL
return exactly the current `SearchResponse` shape (full `MemoryRecord` objects),
preserving backward compatibility. With `"concise"` each returned hit SHALL be
reduced to at least `id`, `category`, and a `snippet` (the memory `content`
truncated to ~200 characters), omitting internal scoring/state fields, the full
`content`, and the raw `metadata` blob; the response envelope SHALL still include
`session_id`, `total_found`, and `search_around_ids`; and `notes_on_results` SHALL
be reduced to note ids only (no nested full records).

#### Scenario: Concise search omits internal fields and shrinks results
- **GIVEN** a memory store with matching memories
- **WHEN** `memory_search` is called with `verbosity="concise"`
- **THEN** each hit contains `id`, `category`, and a `snippet` (content truncated with an ellipsis when longer than the cap), does NOT contain `usefulness_score`/`staleness_score`/`metadata`/full `content`, the envelope still has `session_id` and `total_found`, and `notes_on_results` maps to lists of ids only.

#### Scenario: Full verbosity is unchanged
- **WHEN** `memory_search` is called with the default `verbosity="full"` (or no verbosity argument)
- **THEN** the response is byte-identical to the pre-change `SearchResponse` (full `MemoryRecord` objects), so existing clients are unaffected.

### Requirement: Concise single-memory fetch
The `memory_get` MCP tool SHALL accept the same `verbosity` parameter (default
`"full"`). With `"concise"` it SHALL return only `id`, `category`, and the full
`content` of the memory (the field a caller fetching a single memory actually
wants), omitting the scoring/state machinery. A missing id SHALL return `None` in
both modes.

#### Scenario: Concise get returns id, category, and content only
- **GIVEN** an existing memory id
- **WHEN** `memory_get` is called with `verbosity="concise"`
- **THEN** the result has exactly `id`, `category`, and `content` and none of the internal scoring/state/timestamp fields.

#### Scenario: Missing id returns None in both modes
- **WHEN** `memory_get` is called with an unknown id in either verbosity
- **THEN** it returns `None`.

### Requirement: Search tolerates mixed-dimension embeddings
Hybrid search SHALL NOT fail when the store contains embeddings of differing
dimensions (e.g. written by different embedders). Rows whose vector distance is
undefined SHALL be skipped from the vector phase, not crash the query.

#### Scenario: A foreign-dimension embedding does not break search
- **WHEN** a memory's stored embedding has a different dimension than the query
  embedding
- **THEN** the search still returns results (that memory ranked by FTS), and no
  error is raised.

### Requirement: Partial-word and compound matching
FTS search SHALL match query terms as prefixes (so `video` matches `videowall`)
and SHALL try adjacent-token concatenations (so `video wall` matches `videowall`).

#### Scenario: Compound token is found
- **WHEN** a user searches `video wall` and a memory contains `VIDEOWALL`
- **THEN** that memory is among the results.

### Requirement: Text relevance dominates ranking
Retrieval ranking SHALL place strong text matches above weak matches regardless
of their recency/usefulness modifiers; relevance is normalised to a comparable
scale before usefulness/recency are applied as tie-breakers.

#### Scenario: A strong lexical match outranks a recently-accessed weak match
- **WHEN** a rare term matches one memory strongly and another only weakly but
  that other was recently accessed
- **THEN** the strong match ranks first.

### Requirement: Substring (mid-token) matching
Search SHALL match query terms (>= 3 chars) as **substrings** of stored tokens,
via an FTS5 trigram index, so a term inside a compound or longer word is found.

#### Scenario: A mid-token substring is found
- **WHEN** a user searches `wall` and a memory contains `firewall` or `VIDEOWALL`
- **THEN** that memory is among the results (whole-token FTS alone would miss it).

### Requirement: Multi-source rank fusion
Search SHALL fuse all available lexical and vector sources (porter-FTS bm25,
trigram bm25, vector similarity) with Reciprocal Rank Fusion, then normalise
relevance before usefulness/recency tie-breakers.

#### Scenario: A substring-only match still ranks
- **WHEN** a memory matches a query only via the trigram (substring) source
- **THEN** it appears in the fused results, ranked by its fused relevance.

### Requirement: Trigram is best-effort and optional
The trigram index SHALL be created best-effort (graceful no-op if the tokenizer
is unavailable) and SHALL be disableable. Search SHALL function (porter-FTS +
vector) whether or not the trigram source is present.

#### Scenario: Missing/disabled trigram does not break search
- **WHEN** the trigram tokenizer is unavailable or disabled
- **THEN** search still returns results from the remaining sources and raises no
  error.

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
