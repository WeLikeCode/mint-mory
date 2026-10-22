# Capability: mcp (delta)

## ADDED Requirements

### Requirement: Document co-change query tool
The main MCP server SHALL expose a read-only tool `docs_changed_with(path)` that
returns the documents observed to have co-changed with the file at `path` (the peers
in the same `index-tree` change-set), each with its `strength`, `observed_at`, and
`kind` (which MAY be empty for legacy records without a change-set kind). It SHALL
return an empty list when the path is not indexed or not part of a
change-set, SHALL only return `source='document'` records (never other memories), and
SHALL describe the result as OBSERVED co-change (time/folder/content proximity), NOT a
version-controlled commit. The tool SHALL NOT mutate any store.

#### Scenario: Co-changed peers are returned for an indexed file
- **GIVEN** a working store with a document change-set containing file A and file B
- **WHEN** a client calls `docs_changed_with` with file A's path
- **THEN** the result includes file B with a `strength`, `observed_at`, and `kind`, contains no non-document memory, and an unknown/unindexed path yields an empty list.

### Requirement: Document recency timeline tool
The main MCP server SHALL expose a read-only tool `docs_timeline` (parameters:
`since`, `from_date`, `to_date`, `collection`, `limit`) that returns indexed documents
newest-first by file modified-time, each with `date`, `collection`, `path`, `title`,
and `valid_from`. It SHALL return only `source='document'` records and SHALL respect
the time window and `collection` filter. The effective `limit` SHALL be clamped to a
hard maximum (200) so a single call cannot return the whole corpus. A malformed
`since`/date window SHALL return a structured error object (e.g.
`{"error": "bad_request"}`) rather than an unhandled stack trace.

#### Scenario: Documents are returned newest-first within the cap
- **WHEN** a client calls `docs_timeline` with a time window
- **THEN** the documents are returned newest-first by modified-time, filtered to the requested collection when given, only document records appear, and no more than the hard-cap (200) rows are returned even if a larger `limit` was requested.

#### Scenario: A malformed window returns a clean error
- **WHEN** a client calls `docs_timeline` with an invalid `since` value
- **THEN** the tool returns a structured error object (not an unhandled exception/stack trace).

### Requirement: What-co-changed-with prompt
The main MCP server SHALL expose a `mintmory_what_cochanged_with(path)` prompt that
returns guidance to call `docs_changed_with` for the given path, explains how to read
`strength`/`observed_at`/`kind`, states the observed-co-change (not-a-commit) honesty
caveat, and hints to index the corpus (`index-tree --cochange`) when the result is
empty. The supplied `path` SHALL appear in the returned guidance, and the prompt SHALL
suggest no mutating action.

#### Scenario: The prompt directs to the co-change tool with the honesty caveat
- **WHEN** a client invokes `mintmory_what_cochanged_with` with a file path
- **THEN** the returned guidance references `docs_changed_with`, includes the path, carries the observed-co-change (not-a-version-controlled-commit) caveat, and suggests indexing when empty — and proposes no write/mutate operation.
