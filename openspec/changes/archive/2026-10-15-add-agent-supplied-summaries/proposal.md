# Change: Agent-supplied L3 summaries (BYO-LLM dreaming)

**ID:** `add-agent-supplied-summaries`
**Status:** proposed
**Capabilities:** `dreaming`
**Owner:** orchestrator (Opus)

## Why

L3 concept summaries (dreaming Step 3) are the one MintMory feature that **forces
a second LLM dependency**. `DreamingEngine` already takes an injected
`summarizer(concept, contents) -> str` (defaulting to `None` ⇒ the step is
skipped), and `build_summarizer` wires that callable from `MINTMORY_LLM_*`
(Ollama / OpenAI-compatible gateway). In a pure-Python `provider=none` deployment
— the default — `generate_summaries()` returns 0 and **no summaries are ever
produced**. The only way to get summaries through the running server today is to
stand up and configure an LLM backend.

But the **active agent is already an LLM.** Over MCP / CLI / HTTP it can write a
concept summary far better than a small local model — at no extra infrastructure
cost. The gap is purely **transport**: you cannot inject a Python callable across
an MCP tool call or an HTTP request. So the agent has no way to say "give me the
concepts that need summarising, and here is the text I wrote for one."

This change closes that gap with a **prepare/apply split**: the server hands the
agent the summary *jobs* (the concept + its memories' contents + the existing
summary, if any), the agent does the LLM work itself, and the server persists the
text. The configured-LLM path (`memory_dream` / `generate_summaries`) is left
**completely untouched**; this is a second, provider-independent way to populate
the exact same `memory_summaries` rows.

## What changes

1. **Two new core methods on `DreamingEngine`** (no LLM, no `summarizer`
   required):
   - `collect_summary_jobs(include_all=False) -> list[SummaryJob]` — returns the
     concepts the agent should summarise, selected by the **same** rules
     `generate_summaries` uses today (min-memories threshold, stoplist drop,
     `top_k` cap, content truncation/cap). By default it returns only concepts
     that **need a (re)summary** (no current `MemorySummary`, or a `memory_count`
     that no longer matches the current active count). `include_all=True` returns
     every qualifying concept.
   - `apply_summary(concept, summary_text) -> MemorySummary` — persists the
     agent's text for one concept (recomputing `memory_count` from the current
     active count) via the existing `adapter.upsert_summary`. Idempotent
     (overwrites by concept).

2. **A refactor of `generate_summaries` that changes NO behaviour.** The
   concept-selection + content-preparation logic currently inline in
   `generate_summaries` is extracted into ONE shared private helper that both
   `generate_summaries` and `collect_summary_jobs` call. `generate_summaries`
   must remain **byte-for-byte equivalent** — proven by the existing dreaming
   tests staying green with no edits.

3. **One new type — `SummaryJob`** (`core/types.py`): `concept`, `memory_ids`,
   `contents`, `memory_count`, `current_summary` — everything the agent needs to
   write (or refine) a summary, with no LLM call on the server.

4. **Thin transports over the new methods** (built the same way `memory_dream`
   builds its engine — `build_dreaming_engine` + the configured embedder):
   - MCP: `summary_jobs(include_all=False, limit=0)` and
     `summary_put(concept, summary_text)`; FastMCP `instructions` updated to
     mention the agent-supplied loop.
   - CLI: `summary-jobs` (rich/JSON) and `summary-put concept [text]`
     (`--file` / stdin fallback).
   - HTTP: `GET /summaries/jobs` and `PUT /summaries/{concept}`; `docs/openapi/
     mintmory.yaml` updated.

5. **No backend required for the new path.** It works with `provider=none`. Docs
   note that agent-supplied summaries need no `MINTMORY_LLM_*` configuration.

## What this explicitly does NOT do

- **No agent-driven contradiction resolution.** This change is **summaries
  only**. A prepare/apply split for contradiction resolution (let the agent
  resolve flagged non-note pairs) is a deliberate future follow-up and is NOT
  built here. `resolve_contradictions` and `build_conflict_resolver` are
  untouched.
- **No new `LLMProvider` value.** The new path is provider-independent; it does
  not introduce a `provider=agent` (or similar). It runs regardless of
  `MINTMORY_LLM_PROVIDER`, including `none`.
- **No behaviour change to any existing path.** `memory_dream`,
  `generate_summaries`, `run_light`, `run_full`, `summary_list`/`GET /summaries`,
  `summary_get`/`GET /summaries/{concept}` are unchanged. `generate_summaries`
  after the refactor is byte-for-byte equivalent (existing tests green, no edits).
- **No schema/storage change.** `memory_summaries`, `MemorySummary`, and
  `upsert_summary`/`get_summary`/`list_summaries` are reused as-is. No migration.
- **No new runtime dependency**, no network in the new core methods, no change to
  the one-core-three-transports shape.

## Impact

- **Core:** `core/dreaming.py` (extract the shared selection helper;
  `collect_summary_jobs`, `apply_summary`); `core/types.py` (`SummaryJob`).
- **Storage:** none expected (the new methods reuse `upsert_summary` /
  `get_summary` and the same active-memory scan as `generate_summaries`). If a
  helper is genuinely needed it is additive and owned by the storage task.
- **Transports:** `packages/mcp` (`summary_jobs`, `summary_put` +
  `instructions`), `packages/cli` (`summary-jobs`, `summary-put`),
  `packages/api` (`GET /summaries/jobs`, `PUT /summaries/{concept}` + a
  `SummaryPut` request schema), `docs/openapi/mintmory.yaml`.
- **Tests:** core dreaming (selection-helper equivalence; `collect_summary_jobs`
  needs-resummary rule; `apply_summary` idempotency + count) + each transport.
- **Docs:** `README` + `docs/` (the `summary_jobs → write → summary_put` loop;
  "no backend needed"), `docs/EXPERIMENTS.md` note, `openspec/README.md` bullet.
- **Back-compat:** purely additive. Every default reproduces today's behaviour;
  `collect_summary_jobs`/`apply_summary` do not require a configured LLM; the
  configured-LLM summary path is unchanged. No schema change, no migration.
