# Capability: search (delta)

## ADDED Requirements

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
