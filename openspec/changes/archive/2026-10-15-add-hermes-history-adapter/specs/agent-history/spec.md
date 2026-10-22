# Capability: agent-history (delta)

## MODIFIED Requirements

### Requirement: Multi-agent adapters and deterministic distillation

The system SHALL provide adapters for Claude Code, Codex, Kiro, and Hermes that
normalise each source's on-disk format to one `SessionSummary` schema, failing soft
per malformed session. (The earlier exclusion of Hermes as a source is removed;
Hermes interactive transcripts at `~/.hermes/sessions/` are now an indexable
source. The Hermes guard on the *target* database — history MUST NOT write to the
working store `hermes.db` — is unchanged.) v1 distillation SHALL be deterministic
(no network/LLM): a title, a `kind`
(`fix|feature|refactor|investigation|chore|docs|incident`), and a ≤600-char
changelog summary derived from the session's turns. An LLM distiller is an explicit
future seam and SHALL NOT be required.

#### Scenario: A Claude session is normalised and distilled without an LLM
- **GIVEN** a Claude Code `<uuid>.jsonl` session with user/assistant turns and a `cwd`
- **WHEN** it is indexed with no LLM configured
- **THEN** a `SessionSummary` is produced with `agent="claude_code"`, `repo` resolved from the cwd, a non-empty deterministic `title`/`summary_text`, and a `kind` from `{fix,feature,refactor,investigation,chore,docs,incident}`.

#### Scenario: The working store is never a write target
- **GIVEN** any history ingest run
- **WHEN** the target database path resolves to the working store `hermes.db`
- **THEN** the run refuses with the Hermes guard error and writes nothing, regardless of which source adapters are enabled.

## ADDED Requirements

### Requirement: Hermes session adapter

The system SHALL provide a Hermes adapter that reads interactive session
transcripts from `~/.hermes/sessions/session_*.json` and normalises each to one
`SessionSummary` with `agent="hermes"`, `repo="hermes"`, and collection slug
`"hermes"`, failing soft per malformed or empty session. The adapter SHALL EXCLUDE
automated background sessions whose filename begins `session_cron_`. Each session's
`messages` SHALL be mapped to `NormalizedTurn`s (roles `user`/`assistant`/`tool`,
structured content flattened to text), and `ts_start`/`ts_end` SHALL come from the
session's start/last-updated timestamps. Hermes turns SHALL pass through the same
redaction as other sources before storage. Indexing Hermes SHALL target the
agent-history database only and SHALL NOT write to the working store.

#### Scenario: An interactive Hermes session is indexed
- **GIVEN** a well-formed `~/.hermes/sessions/session_<ts>_<hash>.json` with a `messages` array
- **WHEN** the Hermes adapter iterates sessions
- **THEN** it yields a `SessionSummary` with `agent="hermes"`, `repo="hermes"`, the correct `turn_count`, `model`, `source_path`, and timestamps, and the record is stored with `collection="hermes"`.

#### Scenario: Background cron sessions are excluded
- **GIVEN** a `session_cron_<id>_<ts>.json` file alongside interactive sessions
- **WHEN** the Hermes adapter iterates sessions
- **THEN** the cron file is skipped and only interactive sessions are yielded.

#### Scenario: A malformed Hermes session is skipped softly
- **GIVEN** a session file with invalid JSON or an empty `messages` array
- **WHEN** the adapter iterates
- **THEN** that file is skipped, no exception aborts the walk, and the remaining valid sessions are still yielded.
