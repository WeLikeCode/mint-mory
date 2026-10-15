# agent-history Specification

## Purpose
TBD - created by archiving change add-agent-history-index. Update Purpose after archive.

## Requirements

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

### Requirement: Time-ranged changelog query

The system SHALL answer "what changed in the last N / between dates" by querying
the history DB on `valid_from` within a window (e.g. `history timeline --since 60d`),
optionally filtered by `repo` and `kind`, sorted newest-first, rendered as a dated
changelog. `history search` SHALL run hybrid search over session summaries.

#### Scenario: Two-months-ago query returns dated outcomes
- **WHEN** `mintmory history timeline --since 75d --repo mintkey` runs
- **THEN** it lists that repo's sessions whose `valid_from` falls in the window, newest first, each as a dated `repo · KIND: summary` line.

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

### Requirement: Read-only history MCP server

The system SHALL provide a dedicated MCP server `mintmory-history-mcp`
(`mintmory.mcp.history_server`) that exposes the agent-history index to agentic
tools as **read-only**. It SHALL register exactly three tools — `history_timeline`,
`history_search`, `history_stats` — and SHALL NOT expose any tool that writes,
adds, archives, dreams, or otherwise mutates a store. It SHALL read the history DB
from `MINTMORY_HISTORY_DB` (or `--db`), defaulting to `~/.mintmory/agent-history.db`,
and SHALL enforce the Hermes guard at startup (refuse a working-store path).

#### Scenario: Only read tools are exposed
- **WHEN** the `mintmory-history-mcp` server's registered tools are enumerated
- **THEN** they SHALL be exactly `history_timeline`, `history_search`, `history_stats`
- **AND** no write/mutate tool (e.g. `memory_add`, `memory_dream`, `memory_archive`, `summary_put`) SHALL be present.

#### Scenario: Refuses the working store
- **WHEN** the server is started with `MINTMORY_HISTORY_DB`/`--db` pointing at `hermes.db`, `memories.db`, or `$MINTMORY_DB`
- **THEN** it SHALL fail fast with the Hermes guard error and not serve.

### Requirement: Shared time-ranged query surface

Timeline and search SHALL be implemented once in `core/history/query.py`
(`timeline`, `search`, `resolve_window`) and shared by both the `mintmory history`
CLI and the MCP server, so their results are consistent. `timeline` SHALL return
session summaries whose `valid_from` falls in the resolved window (newest-first),
optionally filtered by `repo` and `kind`; `search` SHALL hybrid-search across
session summaries only. `resolve_window` SHALL treat `since` (`Nd/Nw/Nm/Ny`) as
mutually exclusive with `from/to` and default to the last 90 days.

#### Scenario: Time-window timeline
- **GIVEN** an indexed history DB with sessions dated across several months
- **WHEN** `history_timeline(since="75d", repo="mintkey")` is called (MCP or CLI)
- **THEN** it returns only that repo's sessions whose `valid_from` is within the last 75 days, newest-first, each a dated summary row with a `source_path` back-link.

### Requirement: Deterministic session segmentation

The system SHALL split a session's normalized turns into one or more segments by a
**pure, deterministic** function of the turns (no LLM, no I/O), so segment ids and
counts are stable across re-ingest. Segmentation SHALL be **enabled by default**
(`SegmentSettings.enabled`). A session whose turn count is ≤ `max_turns`, or when
disabled, SHALL yield exactly one segment spanning all turns. Otherwise segments
SHALL accumulate to ~`target_turns` and close at the **next `user`-role turn** (a
segment boundary SHALL NOT fall between a user turn and the assistant/tool turns
answering it), force-closing at `max_turns`; a gap greater than `gap_minutes`
between consecutive turns SHALL force a boundary; a trailing segment smaller than
`min_turns` SHALL merge into the previous one. Each segment SHALL carry a turn
range (`turn_lo`..`turn_hi`, inclusive `seq`) covering the turns with no gaps or
overlap.

#### Scenario: Short session stays one segment; long session splits at user turns
- **GIVEN** a session with fewer turns than `max_turns`
- **THEN** segmentation yields exactly one segment covering all turns.
- **GIVEN** a long session
- **WHEN** it is segmented
- **THEN** each boundary falls at a `user` turn (never inside a tool/assistant burst), and the segments' turn ranges tile the session with no gaps or overlap.

### Requirement: One timeline record per segment

Each segment SHALL be stored as one `MemoryRecord` (`category=EPISODIC`,
`source=AGENT`, `record_type="session_summary"`) with `valid_from` = the segment's
first-turn time, so segments interleave chronologically. The metadata envelope
SHALL include `segment_id` (`<session_id>#<index>`), `segment_index`,
`segment_count`, `turn_lo`, `turn_hi`, and `title`. Writes SHALL be idempotent on
`segment_id`. When a re-distill produces FEWER segments than before, the orphaned
higher-index segments SHALL be archived (`is_archived=1`), not duplicated or left
stale; they SHALL disappear from timeline/search/stats.

#### Scenario: Re-segmenting to fewer parts archives the orphans
- **GIVEN** a session previously stored as 5 segments
- **WHEN** it is re-ingested and now yields 3 segments
- **THEN** segments 0–2 are updated in place and segments 3–4 are archived (absent from timeline), with no duplicate rows.

### Requirement: Optional, local-first LLM segment distiller

When `MINTMORY_LLM_*` is configured, the system SHALL distill each segment via an
LLM into a title, kind, summary, outcome, and a `next_context` handed to the
following segment's prompt. The distiller SHALL be built ONLY when the provider is
set AND the LLM `base_url` is local — a non-local (cloud) endpoint SHALL require an
explicit opt-in (`--allow-cloud-llm` / `MINTMORY_HISTORY_SEG_ALLOW_CLOUD_LLM`);
otherwise the system SHALL fall back to deterministic per-segment summaries.
With `provider=none` the system SHALL produce deterministic per-segment summaries
with **zero LLM calls** (offline). Any LLM error, empty, or malformed-JSON result
SHALL fall back to the deterministic summary for that segment and never abort the
run.

#### Scenario: Cloud endpoint is not used without opt-in
- **GIVEN** `MINTMORY_LLM_*` points at a non-localhost base_url and `allow_cloud_llm` is false
- **WHEN** the history distiller is built
- **THEN** it is `None` (deterministic path used) and no transcript leaves the machine.

### Requirement: Secrets redacted before reaching the LLM

The system SHALL redact every segment turn's text (and the carried `prev_context`)
before it is placed into an LLM prompt, so no live secret is sent to the LLM
endpoint. The distilled output SHALL also be redacted before persistence.

#### Scenario: A planted secret never reaches the model
- **GIVEN** a segment turn containing an `mk_agent_…` key or a JWT
- **WHEN** the LLM distiller builds its prompt
- **THEN** the prompt text contains only `[REDACTED:…]` placeholders, not the secret.

### Requirement: Cost-bounded, recent-first re-distillation

LLM distillation SHALL be cost-bounded: a content-hash cache SHALL skip unchanged
segments; `--max-llm-calls` SHALL cap calls per run (excess segments fall back to
deterministic); `--llm-only-since DATE` SHALL restrict LLM spend to recent
sessions. `distiller_version` SHALL gate re-runs. The ingest report SHALL surface
`segments_written`, `llm_calls`, `llm_cache_hits`, and `llm_fallbacks`.

#### Scenario: A call budget caps LLM spend and falls back
- **GIVEN** a backfill with `--max-llm-calls 10` over sessions needing more than 10 segment distillations
- **WHEN** the run reaches 10 LLM calls
- **THEN** the remaining segments use deterministic summaries, the run completes, and the report shows `llm_calls = 10` with the rest counted as fallbacks/deferred.

### Requirement: Segment-aware timeline ordering and rendering

`timeline` SHALL order by `valid_from` descending with a
`(session_id, segment_index)` tiebreak so a session's segments stay in author
order within the same timestamp second. The CLI SHALL render the segment `title`
and a `[k/N]` marker when `segment_count > 1`, and offer a `--group-by-session`
view. MCP `history_timeline`/`history_search` rows SHALL include `segment_index`,
`segment_count`, `turn_lo`, `turn_hi`, and `title`; `history_stats` SHALL report
both total sessions and total segments.

#### Scenario: Same-second segments keep author order
- **GIVEN** two segments of one session whose `valid_from` falls in the same second
- **WHEN** the timeline is rendered newest-first
- **THEN** they appear adjacent in ascending `segment_index` order, not interleaved with each other arbitrarily.

### Requirement: Bounded LLM distiller prompt

The LLM distiller SHALL bound the transcript it sends to the model so an oversized
segment cannot produce an unbounded prompt. Each turn's text SHALL be truncated to
`SegmentSettings.max_turn_chars`, and the assembled transcript SHALL be elided to
`SegmentSettings.max_prompt_chars` by head+tail elision. Boundedness is the hard
guarantee. Elision SHALL drop/shorten assistant and tool turns first and SHALL NOT
drop any `user`-role turn **unless the user turns alone exceed `max_prompt_chars`**,
in which case it SHALL keep the first user turn (the ask), the last turn (the
outcome), and as many remaining user turns as fit. The first ask and last turn
SHALL always survive. Redaction SHALL be applied BEFORE truncation, so no secret is
exposed by truncating.

#### Scenario: A huge segment yields a bounded, ask-preserving prompt
- **GIVEN** a segment containing a 200k-character turn and several long turns
- **WHEN** `distill_llm` builds the prompt
- **THEN** the prompt's transcript length is ≤ `max_prompt_chars` (plus a small elision marker), every `user` turn's (truncated) text is present, the first ask and last turn are present, and no secret appears.

### Requirement: Bounded LLM generation

The distiller's chat completion SHALL be length-bounded via `max_tokens` so a model
cannot generate indefinitely. `LLMSettings.max_tokens` (default 0 = unset) and an
optional `max_tokens` argument to the chat call SHALL cause `max_tokens` to be sent
in the `/chat/completions` payload only when greater than 0; the history distiller
SHALL bound generation using `SegmentSettings.distill_max_tokens`. Existing callers
that pass no `max_tokens` and leave `LLMSettings.max_tokens=0` SHALL behave exactly
as before (no field sent).

#### Scenario: Distiller caps completion length
- **WHEN** the history distiller calls the model
- **THEN** the request payload includes a `max_tokens` equal to `distill_max_tokens`
- **AND** a plain `chat()` with `LLMSettings.max_tokens=0` sends no `max_tokens` field.

### Requirement: Incremental, crash-safe ingest commits

Backfill and sync SHALL commit each session's distilled segments as that session's
distillation completes, so progress persists and is visible during a long run. All
database writes SHALL occur only on the main thread (distillation MAY run in worker
threads); a failure distilling one session SHALL be counted in `report.errors` and
SHALL NOT discard already-committed sessions.

#### Scenario: A mid-run failure does not lose earlier work
- **GIVEN** a backfill over several sessions where distilling session #3 raises
- **WHEN** the run completes
- **THEN** sessions #1 and #2 are persisted, `report.errors == 1`, and no partial/duplicate rows exist.

### Requirement: Concise history result projection
The `history_timeline` and `history_search` MCP tools SHALL accept a `verbosity`
parameter with values `"full"` and `"concise"`, defaulting to `"full"`. With
`"full"` they SHALL return exactly the current 15-field row shape, preserving
backward compatibility. With `"concise"` each returned row SHALL be reduced to at
least `date`, `repo`, `kind`, `title`, and a `snippet` (the row `summary` truncated
to ~200 characters), omitting the bulkier fields (such as `ts_start`, `branch`,
`agent`, `collection`, `source_path`, `segment_count`, `turn_lo`, `turn_hi`, and the
full `summary`). The concise projection SHALL be applied at the MCP layer only and
SHALL NOT change the shared query row shape used by the CLI.

#### Scenario: Concise timeline rows are reduced
- **GIVEN** an agent-history DB with session summaries in the window
- **WHEN** `history_timeline` is called with `verbosity="concise"`
- **THEN** each row contains `date`, `repo`, `kind`, `title`, and a `snippet`, does NOT contain `branch`/`ts_start`/`segment_count`/`turn_lo`/`turn_hi`/`source_path`/full `summary`, and the rows remain newest-first.

#### Scenario: Full verbosity and CLI output are unchanged
- **WHEN** `history_timeline` or `history_search` is called with the default `verbosity="full"`
- **THEN** the returned rows are byte-identical to the pre-change 15-field shape
- **AND** the `mintmory history` CLI output (which shares the underlying query) is unchanged regardless of the MCP verbosity.
