# Tasks — `add-agent-supplied-summaries`

Disjoint file ownership so parallel Sonnet agents do not collide. Core work is
split by file: **Group 1 owns `core/types.py`** (the `SummaryJob` model — a pure
addition every other group imports), **Group 2 owns `core/dreaming.py`** (the
shared selection helper refactor + the two new methods). Storage is NOT expected
to change; **Group 3** exists only to add a storage helper IF Group 2 needs one
(see §3) and otherwise is a no-op. Transports are split by package (Groups 4/5/6),
tests by package (Group 7), docs (Group 8).

**Order:** run Group 1 first (pure addition). Then Group 2 (the engine work —
this is the critical path and the byte-for-byte-equivalence proof). Groups 4/5/6
(transports) run in parallel after Group 2 lands `collect_summary_jobs` /
`apply_summary`; they treat the design §5 signatures as fixed. Group 7 (tests)
runs alongside/after its corresponding impl group. Group 8 (docs) last.

## 1. Core types — owns `core/types.py`
- [x] 1.1 Add the `SummaryJob` model (concept, memory_ids, contents,
      memory_count, current_summary: str | None = None) in the "Dreaming process
      types" block, matching the existing Pydantic style (design §2).

## 2. Core dreaming — owns `core/dreaming.py`
- [x] 2.1 Add `@dataclass(frozen=True) _SummarySelection` (concept, contents,
      memory_count, memory_ids) near `_LinkCandidate` (design §1a).
- [x] 2.2 Extract today's `generate_summaries` selection (design §0 steps 1–6)
      into `_select_summary_concepts(self) -> list[_SummarySelection]`,
      additionally collecting `memory_ids` index-aligned with `contents` (design
      §1b).
- [x] 2.3 Rewrite `generate_summaries` to call `_select_summary_concepts()` and
      otherwise be UNCHANGED (same early-return, concurrency branch, idempotency
      skip, upsert, count) — byte-for-byte equivalent (design §1c). PROOF: the
      five existing summary tests pass unedited (do not touch them).
- [x] 2.4 Add `collect_summary_jobs(self, include_all: bool = False) ->
      list[SummaryJob]` with the needs-resummary rule (no current summary OR
      `memory_count` drift); no summarizer/LLM (design §3).
- [x] 2.5 Add `apply_summary(self, concept, summary_text) -> MemorySummary` +
      the `_active_count_for_concept` helper; recompute `memory_count`, persist
      via `adapter.upsert_summary`; idempotent; no LLM (design §4, §4a).
- [x] 2.6 Import `SummaryJob` from `core.types` in `dreaming.py`.

## 3. Storage (CONDITIONAL) — owns `core/storage.py`
- [x] 3.1 ONLY IF Group 2 chooses to back `_active_count_for_concept` with a
      storage method rather than an inline scan: add an additive read helper
      (e.g. `active_memory_count_for_entity` or similar) and call it from
      `dreaming.py`. Default expectation: **no storage change** (the inline scan
      in design §4a suffices). If unused, this group is a no-op — do NOT touch
      `storage.py` speculatively.

## 4. Transport: MCP — owns `packages/mcp/src/mintmory/mcp/server.py`
- [x] 4.1 `summary_jobs(include_all=False, limit=0)` tool: build engine via
      `build_dreaming_engine`, `collect_summary_jobs`, post-slice `limit`,
      `model_dump(mode="json")` (design §5a).
- [x] 4.2 `summary_put(concept, summary_text)` tool: build engine, `apply_summary`,
      return dict (design §5a).
- [x] 4.3 Update FastMCP `instructions` (mention the agent-supplied summary loop;
      no backend required) and the tool-map comment block at the top of the file
      (design §5a).

## 5. Transport: CLI — owns `packages/cli/src/mintmory/cli/main.py`
- [x] 5.1 `summary-jobs` command (`--all/--needed`, `--limit`, `--json`; rich
      table default) via `build_dreaming_engine` + `_get_store()` (design §5b).
- [x] 5.2 `summary-put` command (concept arg; text arg → `--file` → stdin;
      strip + reject empty) (design §5b).
- [x] 5.3 Update the module docstring command list (top of `main.py`).

## 6. Transport: HTTP API — owns `packages/api/src/mintmory/api/{schemas.py,app.py}`
      + `docs/openapi/mintmory.yaml`
- [x] 6.1 `SummaryPut` request schema (`summary_text`, required, minLength 1)
      in `schemas.py` (design §5c).
- [x] 6.2 `GET /summaries/jobs` (→ `list[SummaryJob]`, `include_all`/`limit`
      query) declared BEFORE `GET /summaries/{concept}`; `PUT /summaries/{concept}`
      (→ `MemorySummary`). Build engine via `build_dreaming_engine`; add the
      `load_settings` / `build_dreaming_engine` / `SummaryJob` / `SummaryPut`
      imports (design §5c).
- [x] 6.3 OpenAPI YAML: add the two paths + `SummaryJob` and `SummaryPut`
      component schemas under the Summaries section (design §5c).

## 7. Tests — owns the `tests/` trees (per package; disjoint from impl groups)
- [x] 7.1 core (`tests/test_dreaming.py`): the five existing summary tests stay
      green UNEDITED; `_select_summary_concepts` equivalence (order, memory_count,
      truncation/cap, memory_ids alignment, top_k, stoplist);
      `collect_summary_jobs` (no-summarizer/provider=none returns jobs;
      include_all vs default; current_summary; counts; below-min/stoplist
      excluded); `apply_summary` (verbatim text, count, is_current, idempotent,
      incremental round-trip with `collect_summary_jobs`) (design §7).
- [x] 7.2 mcp (`tests/test_tools.py`): `summary_jobs` (include_all/limit) +
      `summary_put` round-trip via `summary_get`; both with no LLM (design §7).
- [x] 7.3 cli (`tests/test_cli.py`): `summary-jobs` (table/`--json`/`--all`/
      `--limit`); `summary-put` (text arg / `--file` / stdin / empty rejection)
      (design §7).
- [x] 7.4 api (`tests/test_routes.py`): `GET /summaries/jobs` 200 (not shadowed),
      query params; `PUT /summaries/{concept}` 200 + visible via
      `GET /summaries/{concept}` (design §7).

## 8. Docs — owns `README*`, `docs/EXPERIMENTS.md`, agent/onboarding docs,
      `openspec/README.md`
- [x] 8.1 README / agent doc: "agent-supplied summaries (BYO-LLM dreaming)"
      section — the `summary_jobs → agent writes text → summary_put` loop; works
      with `provider=none` (no `MINTMORY_LLM_*` backend).
- [x] 8.2 `docs/EXPERIMENTS.md`: note that L3 summaries can be agent-supplied
      (no backend) as an alternative to the configured-LLM path; selection still
      follows `MINTMORY_SUMMARY_*`.
- [x] 8.3 `openspec/README.md`: add the `add-agent-supplied-summaries` bullet.

## 9. Review & integration (orchestrator, Opus)
- [x] 9.1 Verify gates per package (pytest cov ≥ 80 / ruff / ruff format /
      mypy --strict).
- [x] 9.2 Independent Opus reviewer: confirm `generate_summaries` is byte-for-byte
      equivalent (existing summary tests unedited + green), the new methods never
      call an LLM (work at `provider=none`), selection parity
      (`include_all=True` == `generate_summaries`' set), the incremental rule, and
      `apply_summary` idempotency.
- [x] 9.3 Orchestrator applies fixes, re-runs gates, commits.
