# mcp Specification

## Purpose
TBD - created by archiving change add-mcp-resources-prompts. Update Purpose after archive.

## Requirements

### Requirement: Schema resource
The main MCP server SHALL expose a read-only resource `mintmory://schema` that
returns the memory taxonomy: every `MemoryCategory` value, every `ConceptLinkType`
value, and every `MemorySource` value, each with a one-line description, plus the
list of `MemoryRecord` field names. Value names SHALL be derived from the code
enums, and every enum value SHALL have a description (no value left undescribed).
The resource SHALL contain no memory content and no user data.

#### Scenario: Schema resource lists the full taxonomy
- **GIVEN** the main MCP server
- **WHEN** a client reads `mintmory://schema`
- **THEN** the result includes all 8 memory categories and all 12 concept-link types, each with a non-empty description, plus the memory sources and the `MemoryRecord` field list, and contains no stored memory content.

### Requirement: Capabilities resource without secrets
The main MCP server SHALL expose a read-only resource `mintmory://capabilities`
that summarises the active configuration — embedding provider, LLM provider, whether
the LLM tier is enabled, the LLM model name, the vision provider, and whether
dreaming runs LLM steps. The resource SHALL NEVER include any API key or any
absolute database path, and a failure to load settings SHALL produce a safe minimal
response rather than raising to the client.

#### Scenario: Capabilities never leak secrets
- **WHEN** a client reads `mintmory://capabilities`
- **THEN** the result reports the provider names and the LLM-enabled/model/vision/dreaming flags, and contains no `api_key` value and no absolute filesystem path.

### Requirement: History sources resource on the read-only server
The history MCP server SHALL expose a read-only resource
`mintmory://history/sources` that returns the indexed collections with their counts
and the earliest/latest indexed dates, derived from the same aggregation as
`history_stats`, with no per-session content. It SHALL NOT expose any write
capability.

#### Scenario: History sources gives orientation without content
- **WHEN** a client reads `mintmory://history/sources`
- **THEN** the result includes the per-collection counts and the earliest/latest dates and contains no individual session summaries or transcripts.

### Requirement: Workflow prompts on the main server
The main MCP server SHALL expose pre-authored prompts, each named with a
`mintmory_` prefix: `mintmory_recall_before_task` (search-first then thread the
session id and close with feedback), `mintmory_onboard` (MintMory onboarding
policy), and `mintmory_session_closeout` (the session-feedback discipline). Each
prompt SHALL return guidance messages referencing the relevant MintMory tools, and
prompt parameters SHALL be reflected in the returned text. Existing tools SHALL
remain fully usable without invoking any prompt.

#### Scenario: Recall prompt encodes the search-then-feedback loop
- **WHEN** a client invokes `mintmory_recall_before_task` with an intent
- **THEN** the returned messages instruct searching memory for that intent, keeping the returned `session_id`, and closing the loop with `session_feedback`.

#### Scenario: Prompts are namespaced
- **WHEN** a client lists prompts on the main server
- **THEN** the workflow prompts appear with the `mintmory_` prefix.

### Requirement: Read-only changelog prompt on the history server
The history MCP server SHALL expose a `mintmory_changelog` prompt
(parameters: repo, since, kind) that returns guidance to call `history_timeline`
for the requested window. Every prompt and resource on the history server SHALL
reference only the read-only history tools and SHALL NOT suggest any write, add,
archive, or mutate action.

#### Scenario: Changelog prompt stays read-only
- **WHEN** a client invokes `mintmory_changelog` for a repo and window
- **THEN** the returned guidance references `history_timeline` (a read tool) and mentions no write/add/archive/mutate operation.

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

### Requirement: Co-change tools report SQLite-only on other backends
When the main MCP server's store is not a `SqliteBackend` (for example
`PostgresBackend`), `docs_changed_with` and `docs_timeline` SHALL return
`{"error": "not_implemented", "message": COCHANGE_SQLITE_ONLY_MESSAGE}` without
calling any co-change function, instead of raising. On a SQLite store both tools
SHALL behave exactly as before.

#### Scenario: docs_changed_with on a non-SQLite store
- **GIVEN** `server._store` is a stub that wraps the real SQLite store, forwards every attribute except `connect` (which raises `AttributeError`, as `PostgresBackend` has no `connect`), and is not a `SqliteBackend` instance
- **WHEN** a client calls `docs_changed_with` with `{"path": "/repo/a.py"}`
- **THEN** the call does not raise, and `res.data == {"error": "not_implemented", "message": COCHANGE_SQLITE_ONLY_MESSAGE}`, where the message is `co-change is SQLite-only: set MINTMORY_STORAGE_BACKEND=sqlite to use it`.

#### Scenario: docs_timeline on a non-SQLite store
- **GIVEN** the same stub store
- **WHEN** a client calls `docs_timeline` with `{}` and again with `{"since": "bogus"}`
- **THEN** both calls return the same `not_implemented` error dict (the backend check comes before the date parsing).

#### Scenario: SQLite behaviour is unchanged
- **WHEN** the existing tests in `packages/mcp/tests/test_cochange_tools.py` run against the real SQLite store
- **THEN** they pass unedited (peers, empty lists, the 200-row clamp, and the `bad_request` dict for a malformed `since`).
