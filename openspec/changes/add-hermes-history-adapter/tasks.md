# Tasks: Hermes session adapter (MM-39)

## 1. Adapter (`packages/core/src/mintmory/core/history/adapters/hermes.py`)
- [ ] `_DEFAULT_ROOT = "~/.hermes/sessions"`; `iter_sessions(root=None)` scandir,
  skip basenames starting `session_cron_`, soft-fail per file.
- [ ] `_parse_session(path)`: parse JSON; messages→NormalizedTurn (seq, ts=None,
  role∈{user,assistant,tool}, text=flatten(content), tool_name best-effort);
  SessionSummary(agent="hermes", repo="hermes", repo_path="", branch="",
  ts_start=session_start, ts_end=last_updated, model, source_path, turn_count);
  return None on error/empty.
- [ ] Content flattening helper for str | dict | list content.

## 2. Registration
- [ ] `models.AGENTS` += `"hermes"`.
- [ ] `ingest._ALL_SOURCES` += `"hermes"`.
- [ ] `ingest._load_adapter`: `elif name == "hermes"` → `hermes.iter_sessions`.
- [ ] `ingest._COLLECTION_FOR_AGENT["hermes"] = "hermes"`.

## 3. Tests + fixture
- [ ] Fixture: a small well-formed Hermes session JSON (and a `session_cron_*`
  fixture to prove exclusion) under the history test fixtures.
- [ ] Tests: well-formed parse (agent/repo/turn_count/ts/model/source_path);
  content flattening (str + structured); cron skipped; soft-fail on malformed/empty;
  registry wiring (`_load_adapter("hermes")`, `"hermes"` in `_ALL_SOURCES`/`AGENTS`,
  collection slug `"hermes"`).
- [ ] Optional end-to-end: fixture root → backfill → `session_summary` row with
  `collection="hermes"`.

## 4. Docs
- [ ] Note Hermes as a supported source in `docs/agent-history.md` (sources list).

## 5. Gates
- [ ] `ruff` + `ruff format` clean; `mypy packages` clean.
- [ ] `pytest -q` ≥ 80%; full suite green.
- [ ] `openspec validate add-hermes-history-adapter --strict`.
