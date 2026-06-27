# Tasks: MCP resources + prompts (MM-40)

## 1. Schema helper
- [ ] Curated `dict[str,str]` description map beside the enums (or in a small
  `mcp` helper) for every `MemoryCategory`/`ConceptLinkType`/`MemorySource` value
  (copy the inline-comment text). Coverage guard: assert every enum value has a desc.

## 2. Main-server resources (`server.py`)
- [ ] `@mcp.resource("mintmory://schema")` → categories/link_types/sources/fields
  (names iterated from enums + curated descriptions).
- [ ] `@mcp.resource("mintmory://capabilities")` → providers + llm_enabled +
  llm_model + vision_provider + dreaming_llm_steps; NEVER api_key or abs DB path;
  load failure → safe minimal dict, never raise.

## 3. Main-server prompts (`server.py`, `mintmory_` prefix)
- [ ] `mintmory_recall_before_task(intent, link_types="")`.
- [ ] `mintmory_onboard(db_path="", llm_enabled=False)` (from onboarding Part 1).
- [ ] `mintmory_session_closeout(session_id, useful_ids="", stale_ids="")`.

## 4. History server (`history_server.py`, read-only)
- [ ] Refactor `history_stats` aggregation into a shared helper; add
  `@mcp.resource("mintmory://history/sources")` returning by_collection + totals +
  earliest/latest.
- [ ] `mintmory_changelog(repo="", since="90d", kind="")` prompt — references only
  read tools.

## 5. Tests
- [ ] schema: all 8 + 12 values with non-empty descriptions; coverage test.
- [ ] capabilities: providers/flags present; output has NO api_key and NO absolute
  path; load-failure path safe.
- [ ] history/sources: collections + date range; no per-session content.
- [ ] prompts: listed with `mintmory_` prefix; invocation text references correct
  tools; history prompts/resource mention only read tools; params flow in.
- [ ] manifest sanity: ≤ 8 new listed items total.

## 6. Docs
- [ ] Note the new resources + prompts in `docs/agent-history-mcp.md` and/or the
  main MCP doc (onboarding doc kept as-is).

## 7. Gates
- [ ] `ruff` + `ruff format` clean; `mypy packages` clean.
- [ ] `pytest -q` ≥ 80%; full suite green.
- [ ] `openspec validate add-mcp-resources-prompts --strict`.
