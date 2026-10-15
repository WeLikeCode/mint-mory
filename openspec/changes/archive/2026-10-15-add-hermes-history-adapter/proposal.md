# Change: Hermes session adapter for the agent-history index (MM-39)

## Why

The agent-history index ships adapters for Claude Code, Codex, and Kiro, and the
original spec explicitly said *"Hermes SHALL NOT be ingested as a chat source"*
(add-agent-history-index). That exclusion conflated two separate things:

1. **Target-DB safety (correct, kept):** history writes must never touch the
   working store `hermes.db` — enforced by the Hermes guard on the *target* DB.
2. **Source exclusion (now reconsidered):** Hermes was assumed to have no separate
   chat transcripts. It does — **~1,676 interactive session transcripts** live at
   `~/.hermes/sessions/session_*.json` (`{session_id, model, session_start,
   last_updated, messages:[{role, content}], …}`), structurally just like the
   Claude/Codex/Kiro logs. They are genuine agentic chat history and are currently
   **not indexed**, so "what did Hermes do/discuss" is missing from the changelog.

Indexing Hermes transcripts targets `agent-history.db` (never `hermes.db`), so it
does NOT weaken the Hermes guard — the guard is about the write target, not the
read source.

## What changes

- **New adapter `adapters/hermes.py`** with `iter_sessions(root=None)` reading
  `~/.hermes/sessions/session_*.json` and normalising each to one `SessionSummary`
  + `list[NormalizedTurn]`, **failing soft** per malformed session (same contract
  as the other adapters).
- **Interactive-only:** index `session_<timestamp>_*.json`; **exclude**
  `session_cron_*.json` (automated background routines — would add changelog noise).
- **Attribution:** `agent="hermes"`, `repo="hermes"` (Hermes is not repo-scoped and
  its sessions carry no cwd), `repo_path=""`, `branch=""`, collection slug
  `"hermes"`. `ts_start`/`ts_end` from the session's `session_start`/`last_updated`
  (fallback: per-message order). `model` from the session's `model`. `source_path` =
  the session file.
- **Register** Hermes: add `"hermes"` to `_ALL_SOURCES`, `models.AGENTS`,
  `ingest._load_adapter`, and `_COLLECTION_FOR_AGENT["hermes"] = "hermes"`.
- **Redaction unchanged:** Hermes turns flow through the same redact→distill
  pipeline (so `mk_agent_…` keys / JWTs / `.env` contents are redacted before any
  storage or LLM, exactly as for the other sources).
- **Amend the spec:** the "Multi-agent adapters" requirement is updated to list
  Hermes as a source (the "Hermes SHALL NOT be ingested" clause is removed).

Out of scope: cron/background Hermes sessions (excluded by decision; can be enabled
later); repo inference from content (constant `"hermes"`); any change to the
working-store Hermes guard (untouched).

## Impact

- Affected specs: **agent-history** (MODIFIED multi-agent adapters requirement;
  ADDED Hermes adapter requirement).
- Affected code: `packages/core/src/mintmory/core/history/adapters/hermes.py`
  (new); `history/models.py` (`AGENTS`); `history/ingest.py` (`_ALL_SOURCES`,
  `_load_adapter`, `_COLLECTION_FOR_AGENT`); tests + a fixture session file.
- Migrations: none. Existing sources/behaviour unchanged; Hermes is additive. After
  merge, `mintmory history backfill` will include Hermes (or `--sources hermes`).
