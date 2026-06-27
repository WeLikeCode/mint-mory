# Tasks: Co-change/recency MCP tools + prompt (MM-41)

## 1. Main-server tools (`server.py`)
- [ ] Import `changed_with`, `documents_timeline` from `mintmory.core.cochange`.
- [ ] `@mcp.tool() docs_changed_with(path)` → `changed_with(_get_store(), path)`;
  docstring states the observed-co-change (not a commit) honesty limit.
- [ ] `@mcp.tool() docs_timeline(since=None, from_date=None, to_date=None,
  collection=None, limit=50)` → `documents_timeline(_get_store(), since=...,
  from_iso=from_date, to_iso=to_date, collection=..., limit=capped)`.
  **Clamp `limit` to `_DOCS_TIMELINE_MAX=200`** (token safety). **Catch `ValueError`
  (bad since/date) → return `{"error":"bad_request","detail":str(exc)}`** (match
  `notes_list`; `history_timeline` does NOT catch it — don't claim to mirror it).

## 2. Main-server prompt (`server.py`, `mintmory_` prefix)
- [ ] `mintmory_what_cochanged_with(path)` → guidance: call docs_changed_with; read
  strength/observed_at/kind; honesty caveat; index-tree hint if empty; mention
  docs_timeline for recency. `path` flows into the text.

## 3. Tests (FastMCP Client; mirror test_resources_prompts.py)
- [ ] docs_changed_with: peers returned for a change-set fixture; unknown path → [];
  a non-document memory is never returned.
- [ ] docs_timeline: newest-first; collection filter; source='document' only; limit
  clamped to 200; malformed `since` → `{"error":"bad_request"}` (not a stack trace).
- [ ] prompt: listed with mintmory_ prefix; text references docs_changed_with +
  honesty caveat + index hint; path appears.

## 4. Docs
- [ ] Add the two tools + prompt to the MCP doc (docs/agent-history-mcp.md or main
  MCP doc); note the working-store/default-DB scope.

## 5. Gates
- [ ] `ruff` + `ruff format` clean; `mypy packages` clean.
- [ ] `pytest -q` ≥ 80%; full suite green.
- [ ] `openspec validate add-cochange-mcp-tools --strict`.
