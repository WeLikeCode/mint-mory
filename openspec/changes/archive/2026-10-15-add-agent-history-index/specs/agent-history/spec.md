# Capability: agent-history (delta)

## ADDED Requirements

### Requirement: Dedicated, isolated agent-history store

The system SHALL index agentic chat sessions into a **dedicated** MintMory
database (default `~/.mintmory/agent-history.db`), physically separate from the
user's working store. Every `history` operation SHALL refuse to run
(`HermesGuardError`) if the target database resolves to the working store — the
`MINTMORY_DB` value, the CLI default `~/.mintmory/memories.db`, or any
`*/hermes.db`. The dedicated DB file SHALL be created with `0o600` permissions.

#### Scenario: Refuses to target the working store
- **WHEN** a `history` command is given a `--db` equal to `hermes.db`, `memories.db`, or `$MINTMORY_DB`
- **THEN** it SHALL raise `HermesGuardError` and write nothing.

### Requirement: Differentiation from authored documents/notes

Indexed chat sessions SHALL be distinguishable from authored documents/notes by
**all** of: (1) residing in the dedicated history DB; (2) carrying
`metadata.record_type = "session_summary"` and `source = AGENT`; (3) a
`collection` of `claude-code`, `codex`, or `kiro`. The `history` query commands
SHALL default to `record_type = "session_summary"`; they SHALL NOT read the
working store.

#### Scenario: Chat summaries never surface in a document search
- **GIVEN** the dedicated history DB of session summaries and the separate working store of documents/notes
- **WHEN** the user runs `mintmory search` (working store) vs `mintmory history search` (history DB)
- **THEN** document/note results and chat-session results never intermix, and every chat record is tagged `record_type="session_summary"`, `source=AGENT`, and a per-source `collection`.

### Requirement: Session summaries with work-time and provenance

Each session SHALL be stored as one memory: `category = EPISODIC`,
`source = AGENT`, `valid_from = session start time` (work time, NOT ingest time),
content = the changelog summary, and a metadata envelope containing at least
`record_type, agent, repo, repo_path, branch, kind, session_id, ts_start, ts_end,
turn_count, tools_used, source_path, source_offset, model, distiller_version`.
Storage SHALL be idempotent on `session_id` (re-ingest UPDATEs, never duplicates),
and unchanged source files SHALL be skipped via the index manifest on re-run.

#### Scenario: Re-running ingest does not duplicate
- **GIVEN** a session already indexed
- **WHEN** ingest runs again and the source file is unchanged
- **THEN** no new memory is created (manifest skip) and the existing memory is preserved.

### Requirement: Secret redaction before persistence

The system SHALL redact secrets (OpenAI-style keys, `mk_agent_` broker keys, JWTs,
AWS `AKIA` keys, GitHub tokens, PEM private-key blocks, `Authorization` header
values) from every string BEFORE it is written to the history DB and BEFORE it is
sent to any LLM. Redaction SHALL be idempotent. A `history scrub` command SHALL
re-scan stored summaries and report (and exit non-zero on) any residual secrets.

#### Scenario: A pasted broker key never lands in the store
- **GIVEN** a session transcript containing an `mk_agent_…` key and a `Bearer eyJ…` JWT
- **WHEN** the session is indexed
- **THEN** the stored summary contains `[REDACTED:mk_agent]` / `[REDACTED:jwt]` placeholders and no live secret, and `history scrub` reports zero residual secrets.

### Requirement: Multi-agent adapters and deterministic distillation

The system SHALL provide adapters for Claude Code, Codex, and Kiro that normalise
each source's on-disk format to one `SessionSummary` schema, failing soft per
malformed session. Hermes SHALL NOT be ingested as a chat source. v1 distillation
SHALL be deterministic (no network/LLM): a title, a `kind`
(`fix|feature|refactor|investigation|chore|docs|incident`), and a ≤600-char
changelog summary derived from the session's turns. An LLM distiller is an
explicit future seam and SHALL NOT be required.

#### Scenario: A Claude session is normalised and distilled without an LLM
- **GIVEN** a Claude Code `<uuid>.jsonl` session with user/assistant turns and a `cwd`
- **WHEN** it is indexed with no LLM configured
- **THEN** a `SessionSummary` is produced with `agent="claude_code"`, `repo` resolved from the cwd, a non-empty deterministic `title`/`summary_text`, and a `kind` from `{fix,feature,refactor,investigation,chore,docs,incident}`.

### Requirement: Time-ranged changelog query

The system SHALL answer "what changed in the last N / between dates" by querying
the history DB on `valid_from` within a window (e.g. `history timeline --since 60d`),
optionally filtered by `repo` and `kind`, sorted newest-first, rendered as a dated
changelog. `history search` SHALL run hybrid search over session summaries.

#### Scenario: Two-months-ago query returns dated outcomes
- **WHEN** `mintmory history timeline --since 75d --repo mintkey` runs
- **THEN** it lists that repo's sessions whose `valid_from` falls in the window, newest first, each as a dated `repo · KIND: summary` line.
