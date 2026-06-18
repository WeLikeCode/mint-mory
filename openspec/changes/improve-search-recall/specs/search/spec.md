# Capability: search (delta)

## ADDED Requirements

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
