# Design: Lower MCP token usage with opt-in concise results (MM-38)

Backward-compatible token reduction. No new infrastructure (no sandbox); pure
result-shape + description work in the two MCP servers.

## 0. Measured baseline (Opus audit)

| Source | Tokens | Note |
|---|---|---|
| memory_search default (limit 10, full) | ~2,580 | full 30-field MemoryRecords |
| memory_search concise (limit 10) | ~240 | id+category+snippet+is_note |
| history_timeline default (limit 50, full) | ~10,500 | 15-field rows, full summary |
| main manifest + instructions | ~3,480 fixed | memory_dream desc embeds env docs |

## 1. `verbosity` parameter

Add `verbosity: Literal["full", "concise"] = "full"` to: `memory_search`,
`memory_get`, `history_timeline`, `history_search`. `"full"` returns exactly
today's shape (no regression). Validation: any value other than the two literals
is rejected by the tool signature.

## 2. Concise projections (pure helpers)

A new module `packages/mcp/src/mintmory/mcp/concise.py` (pure, no I/O, unit-tested):

```python
SNIPPET_CHARS = 200

def concise_memory(rec: dict) -> dict:        # from MemoryRecord.model_dump(mode="json")
    return {"id": rec["id"], "category": rec["category"],
            "snippet": _snip(rec.get("content", "")), "is_note": rec.get("is_note", False)}

def concise_search_response(resp: dict) -> dict:
    return {"session_id": resp["session_id"], "total_found": resp["total_found"],
            "search_around_ids": resp.get("search_around_ids", []),
            "memories": [concise_memory(m) for m in resp["memories"]],
            "notes_on_results": {k: [n["id"] for n in v]                  # ids only
                                 for k, v in resp.get("notes_on_results", {}).items()}}

def concise_history_row(row: dict) -> dict:
    return {"date": row["date"], "repo": row["repo"], "kind": row["kind"],
            "title": row["title"], "snippet": _snip(row["summary"])}

def _snip(text: str, n: int = SNIPPET_CHARS) -> str:
    return text if len(text) <= n else text[:n].rstrip() + "…"
```

- `concise_memory_get(rec) -> {id, category, content}` (full content — a single
  explicit fetch is where you DO want the body).
- The helpers operate on the already-serialised dicts the tools build today, so the
  core models and the shared `query._shape_row` are untouched (CLI unaffected).

## 3. Wiring in the tools

- `memory_search`: build `response.model_dump(...)` as now; if
  `verbosity == "concise"` return `concise_search_response(result)`.
- `memory_get`: if concise return `concise_memory_get(record_dump)`.
- `history_timeline`/`history_search`: rows come from `query.*`; if concise map each
  through `concise_history_row`. (The history tools currently return
  `list[dict]`; concise returns the same list type with fewer keys.)
- Return-type annotations stay `dict[str, Any]` / `list[dict[str, Any]]`, so mypy
  is unaffected.

## 4. Advertise concise (so the opt-in is used)

One line appended to each affected tool's docstring: *"Pass
`verbosity=\"concise\"` for a compact id+snippet projection when browsing/scanning;
use the default `\"full\"` only when you need the full body/metadata."* Add a
sentence to each server's `instructions` block pointing at concise-for-browse.

## 5. Description trimming (no behaviour change)

- `memory_dream` docstring: remove the embedded `MINTMORY_LLM_* / MINTMORY_LINK_* /
  MINTMORY_SUMMARY_*` configuration prose; replace with one line: "LLM-backed steps
  follow the configured tier; see docs (MCP.md / config docs). With
  provider=none (default) only structural steps run." Move the removed detail into
  a docs file (e.g. `docs/` MCP/config doc) so nothing is lost.
- Tighten both `instructions` blocks: keep the model + when-to-use guidance, drop
  repetitive prose. Target ~40% shorter without losing routing guidance.

## 6. Edge cases

- Empty results / `notes_on_results` empty → concise returns empty lists/dicts.
- `content` shorter than the snippet cap → returned unchanged (no ellipsis).
- `memory_get` miss → still returns `None` in both modes.
- Unknown `verbosity` value → rejected by the typed signature (no silent fallback).

## 7. Testing

- `test_concise.py` (pure): `concise_memory`/`concise_search_response`/
  `concise_history_row`/`concise_memory_get` field sets exactly; snippet truncation
  (long → cut + ellipsis; short → unchanged); `notes_on_results` reduced to ids;
  envelope fields preserved.
- MCP tool tests (existing MCP test pattern): `verbosity="full"` returns the
  unchanged shape (regression guard); `verbosity="concise"` returns the lean shape;
  default is full.
- A token-shape assertion: concise serialized length is materially smaller than full
  for a realistic record (sanity, not brittle exact counts).

## 8. Gates

`ruff` + `ruff format` clean; `mypy packages` clean (CI command — includes tests);
`pytest -q` ≥ 80%, full suite green (CI runs with `--extra cochange`);
`openspec validate optimize-mcp-token-usage --strict`.
