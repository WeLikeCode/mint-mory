# Design: Hermes session adapter (MM-39)

Mirrors the existing adapters (`adapters/claude_code.py` etc.): a pure
`iter_sessions()` that yields `(SessionSummary, list[NormalizedTurn])`, fails soft,
and feeds the unchanged redact→distill→commit pipeline.

## 1. Source format (`~/.hermes/sessions/session_*.json`)

One JSON object per file:
```
{ "session_id": str, "model": str, "base_url": str, "platform": str,
  "session_start": ISO8601, "last_updated": ISO8601,
  "system_prompt": str, "tools": [...], "message_count": int,
  "messages": [ { "role": "user"|"assistant"|"tool", "content": str|obj }, ... ] }
```
Filenames: `session_<YYYYMMDD>_<HHMMSS>_<hash>.json` (interactive) and
`session_cron_<id>_<ts>.json` (background). **Index interactive only** — skip any
basename starting `session_cron_`.

## 2. `adapters/hermes.py`

```python
_DEFAULT_ROOT = "~/.hermes/sessions"

def iter_sessions(root: str | None = None) -> Iterator[tuple[SessionSummary, list[NormalizedTurn]]]:
    # scandir root; for each *.json whose basename does NOT start "session_cron_":
    #   parse_session(path) -> (summary, turns) or None (soft fail); yield if not None
```

`_parse_session(path)`:
- `json.load`; on any error / non-dict / empty `messages` → return `None` (soft fail).
- **Turns:** enumerate `messages`; `seq = i`; `role` mapped to
  `{"user","assistant","tool"}` (Hermes already uses these; anything else →
  `"tool"` for non-user/assistant, or skip empty); `text = _content_text(content)`
  where content may be a str or a structured object (dict/list) → flatten to a
  string (json.dumps for non-str, like the other adapters handle tool payloads);
  per-message ts = `None` (Hermes messages carry no per-turn timestamp), so segment
  timing falls back to session ts (existing segment logic handles None ts).
- **tools_used:** collect from `tool`-role messages' tool name if present, else from
  the top-level `tools` list names; dedup, sorted (best-effort; `[]` if none).
- **session_id:** the `session_id` field, else the filename stem.
- **ts_start/ts_end:** `session_start` / `last_updated` (ISO-8601); fallback to
  `"1970-01-01T00:00:00Z"` if absent.
- **SessionSummary:** `agent="hermes"`, `repo="hermes"`, `repo_path=""`,
  `branch=""`, `model=session.get("model","")`, `source_path=abspath(path)`,
  `turn_count=len(turns)`, `source_offset=0`.

Pure + deterministic; no network. Drops sessions with zero usable turns.

## 3. Registration (small edits)

- `models.AGENTS`: add `"hermes"` → `("claude_code","codex","kiro","hermes")`.
- `ingest._ALL_SOURCES`: add `"hermes"`.
- `ingest._load_adapter`: add `elif name == "hermes": from ...adapters import hermes;
  _ADAPTERS[name] = hermes.iter_sessions`.
- `ingest._COLLECTION_FOR_AGENT["hermes"] = "hermes"`.

No other call sites change — backfill/sync iterate `_ALL_SOURCES`, so Hermes is
picked up automatically; `--sources hermes` works via the existing flag.

## 4. Redaction / safety

Unchanged. Hermes turns are redacted by the existing pipeline before storage/LLM
(the `mk_agent_…` / JWT / secret scenarios already covered). The target DB is
`agent-history.db`; the Hermes guard (which forbids the *target* being `hermes.db`)
is untouched and still passes — we only added a *source*.

## 5. Edge cases

- `~/.hermes/sessions` absent → `iter_sessions` yields nothing (no error).
- Malformed/partial JSON, missing `messages`, empty messages → soft-skip that file.
- `content` as a dict/list (tool calls/results) → flattened to text, not dropped.
- Cron files present → skipped by the `session_cron_` prefix filter.
- Non-ASCII / large sessions → handled like other adapters (truncation/segmentation
  happen downstream in the distiller, not here).

## 6. Testing

- `test_history_adapters.py` (extend) / `adapters/hermes` tests with a small
  fixture session JSON under the test fixtures dir:
  - parses a well-formed Hermes session → one `SessionSummary(agent="hermes",
    repo="hermes")` with the right turn_count, ts_start/end, model, source_path.
  - role/content flattening (str + structured content) → correct `NormalizedTurn`s.
  - **cron files are skipped** (a `session_cron_*.json` fixture yields nothing).
  - soft-fail: malformed JSON / empty messages → skipped, walk continues.
  - registry: `_load_adapter("hermes")` returns the callable; `"hermes"` in
    `_ALL_SOURCES` and `AGENTS`; collection slug maps to `"hermes"`.
- Optional: an end-to-end ingest test (fixture root → backfill into a temp
  agent-history DB → a `session_summary` row with `collection="hermes"`).

## 7. Gates

`ruff` + `ruff format` clean; `mypy packages` clean (CI command); `pytest -q` ≥ 80%
full suite green (`--extra cochange` env); `openspec validate
add-hermes-history-adapter --strict`.
