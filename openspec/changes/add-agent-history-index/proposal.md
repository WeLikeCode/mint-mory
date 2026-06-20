# Change: Agent-history index (`mintmory history`)

## Why

A developer using several coding agents (Claude Code, Codex, Kiro) accumulates a
huge, siloed, append-only trail of sessions (here: ~2,048 Claude sessions / 917 MB
+ 350 MB Codex + Kiro workspaces). The valuable question — *"what was fixed or
added ~2 months ago in repo X?"* — is unanswerable today without grepping
gigabytes of tool-call noise across three incompatible formats. The answer
actually lives in a handful of outcome sentences per session.

MintMory is the natural substrate (typed, time-aware, hybrid-search memory in a
single SQLite file), but the user's real working store (`hermes.db`, 15,958
memories) must NOT be polluted, and authored documents/notes must stay trivially
separable from machine chat transcripts. See `docs/design/agent-history-index.md`.

## What changes

A new, additive `mintmory history` capability — a **dedicated, summary-first
changelog** of agentic work:

- **Dedicated store** `~/.mintmory/agent-history.db` (a normal MintMory DB),
  physically isolated from the working store. The tool **refuses to run** if the
  target equals the configured working DB / `hermes.db`.
- **Adapters** for Claude Code, Codex, and Kiro normalise each session to one
  `SessionSummary` schema; **Hermes is excluded** (it is a memory store, not a
  transcript).
- **Redactor** (hard gate) strips secrets BEFORE anything is persisted.
- **Deterministic distiller** (v1, no LLM) produces a dated changelog summary per
  session; an LLM distiller is a documented seam for a later phase.
- **Writer** stores one `category=EPISODIC`, `source=AGENT`,
  `valid_from=session-start` memory per session with a strict metadata envelope
  (`record_type=session_summary`, `agent`, `repo`, `branch`, `kind`, `ts_start/end`,
  `source_path`, `source_offset`), `collection ∈ {claude-code,codex,kiro}`. Dedup
  via `index_manifest`.
- **CLI**: `mintmory history backfill`, `history sync` (tail-offset incremental),
  `history timeline` (time-ranged changelog), `history search`, `history scrub`
  (secret audit).

This is purely additive: no existing schema, search, or transport behaviour
changes; the working store is never touched.

## Impact

- Affected specs: **agent-history** (new capability).
- Affected code: new `packages/core/src/mintmory/core/history/` subpackage
  (models, redact, normalize, distill, adapters/{claude_code,codex,kiro}, ingest);
  new `history` Typer command group in `packages/cli`.
- No change to `schema.sql`, existing `StorageAdapter` search, or the working DB.
- New tests under `packages/core/tests/` (+ CLI). All gates stay green.
