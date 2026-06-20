# Tasks — add-agent-history-index

## 1. Core scaffolding (`core/history/`)
- [x] 1.1 `models.py`: `NormalizedTurn`, `SessionSummary`, `AGENTS`, `KINDS`.
- [x] 1.2 `redact.py`: `redact()` (all patterns, idempotent, over-redact) + `scan()`.
- [x] 1.3 `normalize.py`: `to_utc_iso()`, `resolve_repo()` (worktree-aware).
- [x] 1.4 `distill.py`: deterministic `distill()` (title/kind/summary, pure, idempotent).

## 2. Adapters (`core/history/adapters/`)
- [x] 2.1 `claude_code.iter_sessions()` — jsonl, content str|list, skip sidechain.
- [x] 2.2 `codex.iter_sessions()` — rollout payloads, session_index titles, import-skip.
- [x] 2.3 `kiro.iter_sessions()` — b64url workspace dirs + sessions.json dates.

## 3. Ingest + guard (`core/history/ingest.py`)
- [x] 3.1 `_assert_not_working_db()` (HermesGuardError) + `DEFAULT_HISTORY_DB`.
- [x] 3.2 `write_session()` — redact, EPISODIC+AGENT+envelope, idempotent on session_id.
- [x] 3.3 `backfill()` + `sync()` + `IngestReport`; index_manifest dedup; chmod 600.

## 4. CLI (`mintmory history` group)
- [x] 4.1 `backfill`, `sync`, `timeline` (--since/--from/--to/--repo/--kind), `search`, `scrub`.

## 5. Tests + fixtures
- [x] 5.1 redact, distill, adapters (committed fixtures), ingest (guard+dedup+valid_from), cli.

## 6. Gates
- [x] 6.1 `ruff check . && ruff format --check . && mypy packages && pytest -q` (cov ≥ 80).
