# Capability: search (delta)

## ADDED Requirements

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
