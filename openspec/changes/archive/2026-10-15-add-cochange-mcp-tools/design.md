# Design: Co-change/recency MCP tools + prompt (MM-41)

Additive, read-only. Thin MCP wrappers over existing `core/cochange` query
functions; no core changes. All on the **main** server (working store).

## 1. Existing functions wrapped (no change)

- `cochange.changed_with(store, path) -> list[dict]` (cochange.py:763) → rows
  `{path, strength, observed_at, kind}`; `[]` if the path has no `changeset_id` or
  is unknown. Already filters `source='document'` (never returns other memories).
  Note: `kind` is `""` for legacy rows lacking `changeset_kind` (not always one of
  `cold_full_index`/`incremental`) — the prompt/spec must not promise an enum value.
- `cochange.documents_timeline(store, *, since=None, from_iso=None, to_iso=None,
  collection=None, limit=50) -> list[dict]` (cochange.py:829) → rows `{date,
  collection, path, title, valid_from}`, newest-first; reuses `resolve_window`.

## 2. Tools (`server.py`, main server)

```python
@mcp.tool()
def docs_changed_with(path: str) -> list[dict[str, Any]]:
    """Documents observed to have co-changed with <path> (same index-tree change-set).

    OBSERVED co-change (time + folder + content proximity) — NOT a version-controlled
    commit. Returns [{path, strength, observed_at, kind}]; empty if the file is not
    indexed or not in a change-set. Read-only.
    """
    return changed_with(_get_store(), path)

_DOCS_TIMELINE_MAX = 200  # hard cap so an MCP caller cannot pull the whole corpus

@mcp.tool()
def docs_timeline(
    since: str | None = None, from_date: str | None = None, to_date: str | None = None,
    collection: str | None = None, limit: int = 50,
) -> list[dict[str, Any]] | dict[str, str]:
    """Indexed documents newest-first by file modified-time (valid_from).

    Returns [{date, collection, path, title, valid_from}]. since='30d' style window,
    or from_date/to_date ISO; optional collection filter. Read-only.
    """
    capped = max(1, min(limit, _DOCS_TIMELINE_MAX))   # token safety
    try:
        return documents_timeline(_get_store(), since=since, from_iso=from_date,
                                  to_iso=to_date, collection=collection, limit=capped)
    except ValueError as exc:                          # bad `since`/date grammar
        return {"error": "bad_request", "detail": str(exc)}
```

**Error handling (corrected).** `documents_timeline` → `resolve_window` raises
`ValueError` on a malformed `since`/date. There is NO history-tool precedent to
mirror (`history_timeline` does not catch it). The main-server precedent is
`notes_list`, which returns `{"error": "bad_request"}`. Match that: catch `ValueError`
and return `{"error": "bad_request", "detail": str(exc)}` — never let it become an
unhandled stack trace. **`limit` is clamped to `_DOCS_TIMELINE_MAX` (200)** because
`documents_timeline` enforces no cap of its own and per-row leanness does not bound
total payload. `changed_with` is naturally bounded (one change-set) → no cap needed.

- Import `changed_with`, `documents_timeline` from `mintmory.core.cochange` at module
  top (or lazily, matching the file's import style).
- Mirror the `from_date`/`to_date` MCP arg names already used by the history server's
  `history_timeline` for consistency (it maps to `from_iso`/`to_iso`).
- Return annotations `list[dict[str, Any]]` (no Any leaks beyond the dict payloads).
- `limit` passes through to the existing bound (documents_timeline has no max cap of
  its own beyond what's sensible — keep default 50, mirroring history_timeline).

## 3. Prompt (`server.py`, `mintmory_` prefix)

```python
@mcp.prompt()
def mintmory_what_cochanged_with(path: str) -> str:
    """Find documents that co-changed with a file, and how to read the result."""
    # returns guidance text:
    #  - call docs_changed_with("<path>")
    #  - each peer has strength (0-1), observed_at, and kind (cold_full_index vs incremental)
    #  - HONESTY: observed co-change = changed in the same observed window + folder/content
    #    proximity, NOT an atomic commit; cold_full_index peers are co-location, not co-edit
    #  - if empty: the file may not be indexed — run `mintmory index-tree <root> --cochange`
    #  - for recency, use docs_timeline
```
`path` flows into the returned text. Read-only guidance only.

## 4. Safety / token / placement

- **Read-only**: both tools only `SELECT`; the prompt suggests no mutation.
- **Scope**: `changed_with`/`documents_timeline` already constrain to
  `source='document'`; no non-document memory or scoring/state leaks. Returns are
  small flat dicts → no `verbosity` knob needed (MM-38 concern already satisfied).
- **Main vs history**: main server only. The history server stays untouched
  (read-only agent-history index; different DB).
- **Manifest**: +2 tools, +1 prompt on the main server; one-line descriptions.

## 5. Edge cases

- Unknown / unindexed `path` → `[]` (tool) ; prompt tells the agent to index.
- Documents indexed into a separate `--db` → not visible via MCP (documented
  limitation; default target is the working store).
- `docs_timeline` with a bad `since`/date grammar → catch the `ValueError` and
  return `{"error": "bad_request", "detail": ...}` (matching `notes_list`, the main
  server's precedent — `history_timeline` does NOT catch it), never a stack trace.
- `docs_timeline` `limit` is clamped to `_DOCS_TIMELINE_MAX` (200) for token safety.

## 6. Testing

- `docs_changed_with`: with a fixture working store containing a change-set, returns
  the peers (path/strength/observed_at/kind); unknown path → `[]`; never returns a
  non-document memory (insert one and assert absence).
- `docs_timeline`: newest-first ordering; collection filter; only `source='document'`
  rows; respects `limit`.
- `mintmory_what_cochanged_with`: listed with the `mintmory_` prefix; invoking with a
  path returns text that references `docs_changed_with`, includes the honesty caveat,
  and mentions the index-tree hint; the path appears in the text.
- Use the FastMCP in-memory `Client` pattern from `tests/test_resources_prompts.py`.

## 7. Gates

`ruff` + `ruff format` clean; `mypy packages` clean (CI command); `pytest -q` ≥ 80%
full suite green (`--extra cochange`); `openspec validate add-cochange-mcp-tools
--strict`.
