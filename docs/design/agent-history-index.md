# Design: Agent-History Index — a searchable changelog of agentic work

> Status: **approved design, pre-implementation** (Opus max-thinking brainstorm +
> user decisions, 2026-06-20). Next step: turn Phase 1 into an OpenSpec change.

## Problem

Index all agentic chat histories — **Claude Code, Codex, Kiro** (and keep Hermes
separate) — so the user can quickly answer outcome questions like *"what was fixed
or added ~2 months ago in repo X?"*. Hard requirement: **authored documents/notes
must be trivially separable from machine chat transcripts**.

## Locked decisions

| Decision | Choice |
|---|---|
| **Substrate** | Dedicated `~/.mintmory/agent-history.db` (a MintMory store, physically isolated from `hermes.db`) |
| **Distillation** | Deterministic extractive summaries first (no LLM); LLM distillation added in Phase 2 |
| **Fidelity** | One summary per session + back-links (file path + byte offset); **no** raw-turn storage in v1 |
| **Refresh** | Manual `mintmory history sync` (tail-offset incremental); no background daemon in v1 |

## Data sources (verified on disk)

| Agent | Location | Format |
|---|---|---|
| Claude Code | `~/.claude/projects/<enc-cwd>/<uuid>.jsonl` | JSONL per session: `{type, message, timestamp, cwd, gitBranch, sessionId, isSidechain, toolUseResult}` |
| Codex | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` + `session_index.jsonl` (titles) + `history.jsonl` | `session_meta` + `response_item` lines; honor `external_agent_session_imports.json`; **skip** `codex-dev.db` (automations, not chat) |
| Kiro | `~/Library/Application Support/Kiro/User/globalStorage/kiro.kiroagent/workspace-sessions/<b64url(workspace)>/<uuid>.json` + sibling `sessions.json` (dates) | JSON `history[].message{role,content}`, `title`, `sessionType`; **ignore** `state.vscdb` (UI state) |
| Hermes | `~/.mintmory/hermes.db` | **Excluded as a source** — it's a memory store, not a transcript. May be cross-searched later. |

## Differentiation (docs/notes vs chat) — three concentric boundaries

1. **Physical** (primary): chat lives only in `agent-history.db`; docs/notes stay in
   `hermes.db`/the working store. Different files → cannot cross-contaminate.
2. **Structural**: every chat record carries `metadata.record_type='session_summary'`
   + `source=AGENT`. Mirrors the proven `is_note` overlay; survives a future merge.
3. **Collection**: `collection ∈ {claude-code, codex, kiro}` for provenance and
   clean per-source re-index / drop operations.

The new `mintmory history …` commands default to `record_type=session_summary` +
the history DB; existing `search`/`notes` keep reading the working store.

## Normalized schema (the contract every adapter targets)

```
SessionSummary {
  session_id, agent ∈ {claude_code,codex,kiro},
  repo (git-root basename), repo_path, branch,
  ts_start, ts_end, turn_count, tools_used[],
  kind ∈ {fix,feature,refactor,investigation,chore,docs,incident},
  title, summary_text (changelog voice, ≤600 chars),
  source_path, source_byte_offset, model, distiller_version
}
```
Stored as a `MemoryRecord`: `category=EPISODIC`, `source=AGENT`,
`valid_from=ts_start` (work time, **not** ingest time), metadata = the envelope above.

## Pipeline

`adapter → normalize/sessionize → REDACT → distill → write`, all idempotent.

- **Redactor (hard gate, runs before persistence AND before any LLM)** — measured
  secret density in a 62-file sample: 845 `mk_agent_` broker keys, 453 JWTs, 152
  `sk-/pk-` keys, 95 private-key blocks, 2 AWS, 2 GitHub, 2,929 `Authorization`
  headers. Redact those patterns → typed placeholders; exclude `.env`/`.pem`/`.key`
  bodies and `/tmp/*.env`; `chmod 600` the DB; `.gitignore` it; never sync off-machine.
- **Distiller** — v1 deterministic: first user prompt + last assistant text +
  file/git-touch signals → `{title, kind, summary}`. v2: configured LLM tier
  (local preferred for sensitive repos) producing strict JSON; `distiller_version`
  lets re-distillation re-run only when the prompt improves.
- **Dedup** — `index_manifest` (path + content_hash + mtime → skip unchanged);
  `session_id` as stable key → re-distill `UPDATE`s, never duplicates.

## Time query / changelog

`valid_from ∈ [now−N … window]` + optional `repo`/`kind`, sorted desc, rendered as
a dated release-notes timeline. Optional **week rollups** (`category=temporal`,
`valid_from/valid_until = week bounds`) for skimming → drill week → session →
(back-link) raw transcript. **Always query `valid_from`, never `created_at`.**

## Phased plan

- **Phase 0 — schema lock** (½–1 day): finalize the envelope + go/no-go. (Done in spirit.)
- **Phase 1 — MVP** (2–3 days): Claude Code adapter → redactor → deterministic
  summary → `agent-history.db` (EPISODIC + envelope, collection `claude-code`) +
  `mintmory history backfill --source claude` and `history timeline/search`
  (MemoryFilter + time window). Reuses `index_manifest`. **Answers the question for
  the 917 MB / 2,048-session source with no LLM.**
- **Phase 2 — LLM distill + rollups** (1–2 days): plug LLM tier into the distiller
  (deterministic fallback kept); add day/week rollups + group-by repo/kind.
- **Phase 3 — Codex + Kiro adapters** (1–2 days): same pipeline; collections
  `codex`/`kiro`; honor `external_agent_session_imports.json`. Unified timeline.
- **Phase 4 — keep-current + hardening** (1–2 days): `history sync` (tail-offset
  incremental), `history scrub` audit, optional per-repo session LINKING (dreaming)
  for narratives, optional MCP `history_search` tool.
- **Phase 5 (deferred)** — opt-in raw-turn retention + DuckDB analytics export, only if requested.

## Risks (carry into build)

Redaction misses (over-redact + scrub audit); summary info-loss (back-links);
LLM cost/quality on backfill (deterministic ships first); repo attribution for
worktrees (resolve main repo); timezone skew (UTC, query `valid_from`); **Hermes
contamination if misconfigured — the tool MUST refuse to run if target ==
hermes.db**; upstream format drift (isolated, version-aware adapters + fixtures).

## Open decisions deferred to build

- Retention policy (keep forever vs age-out) and any **repos to exclude entirely**
  (client/confidential work).
- Redaction strictness: credentials only, or also PII (emails/IPs/names)?
- Query surface beyond CLI: MCP tool (in-agent recall) and/or HTTP for a future UI?
- Granularity: also per-commit/PR records + git-log correlation to sharpen "what was fixed"?
- Whether related-session LINKING (dreaming) runs on this DB or entries stay flat.
