# Capability: mcp (delta)

## ADDED Requirements

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
