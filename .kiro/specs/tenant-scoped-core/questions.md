# Questions — tenant-scoped-core

<!-- l4:questions v1
How to answer: write under "### Answer" and set **Status** to `answered`.
To accept the clarifier's suggestion as-is, set **Status** to `accepted`.
Status values: open · answered · accepted · answered-by-clarifier · dismissed · superseded
Kind values: technical · product · ambiguous · verdict · harness. For a `verdict` question, start the answer with `accept` or
`reject`, then give your reason; for a `harness` question, with `accept` or `retry`.
Do not change question IDs. Commit and push to the l4/… branch to resume the run. -->

<!-- l4:index:start -->
| ID | Status | Blocking | Kind | Question |
|----|--------|----------|------|----------|
| Q-001 | answered | 1 | ambiguous | R1.7 assumes LinkSettings() default min_shared_entities=1, but the code default is 2 |
| Q-002 | accepted | 3 | technical | packages/mcp/tests/test_tenancy_dreaming_mcp_transport.py:114 |
| Q-003 | accepted | 3 | technical | packages/cli/tests/test_tenancy_dreaming_cli_transport.py:112 |
| Q-004 | accepted | 3 | technical | packages/api/tests/test_tenancy_dreaming_api_transport.py:111 |
| Q-005 | answered | none | verdict | Criterion C-7881686c (Req 3.1): accept as satisfied? |
| Q-006 | answered | none | verdict | Criterion C-d9c39ea3 (Req 3.2): accept as satisfied? |
| Q-007 | open | none | verdict | Criterion C-63860dbc (Req 3.3): accept as satisfied? |
| Q-008 | open | none | verdict | Criterion C-a0213e6c (Req 4.1): accept as satisfied? |
<!-- l4:index:end -->

---

## Q-001: R1.7 assumes LinkSettings() default min_shared_entities=1, but the code default is 2

- **Status:** answered
- **Blocking tasks:** 1
- **Kind:** ambiguous
- **Asked:** 2026-10-20T05:19Z by deepseek, run r-20261020T0514Z-8813, task 1

### Context
C-1db051ad / requirements.md R1.7 says Scenario A uses the *default* LinkSettings(), where 'a pair links when it shares >= 1 entity', and expects three relates_to links among a1/a2/a3, which share only the single entity 'acme'. The actual default is min_shared_entities=2 (config.py:108; the docstring in dreaming.py:274 is stale), adopted deliberately as the production-tuned 'E-L-MID' profile, so the scenario yields 0 links. Existing tests work around this with an explicit _permissive() (min_shared_entities=1). The tenancy work does not otherwise need any config change. How should the Scenario A test be written?

### Options
1. Write Scenario A with an explicit LinkSettings(min_shared_entities=1) and leave the production default at 2.
2. Change the LinkSettings.min_shared_entities default to 1 as part of this unit (undoes the production tuning).
3. Keep the default at 2 and adjust the Scenario A fixture/expected links (requires re-specifying R1.7).

### Answer
<!-- write below this line -->
Option 1. Write Scenario A with an explicit LinkSettings(min_shared_entities=1) and leave the production default at 2. R1.7's intent is its parenthetical (a pair links when it shares at least one entity); the word 'default' is a slip, since min_shared_entities=2 is the deliberate production tuning (E-L-MID) and the existing tests use the same permissive setting. Do not change config defaults in this unit. Keep the rest of Scenario A as written (SummarySettings() default, the summarizer, the memories and the expected three relates_to links among a1, a2 and a3, none crossing tenants). Where another scenario only compares the legacy engine with the tenant engine, both sides may keep the default LinkSettings(), as long as both use the same settings.

---

## Q-002: packages/mcp/tests/test_tenancy_dreaming_mcp_transport.py:114

- **Status:** accepted
- **Blocking tasks:** 3
- **Kind:** technical
- **Asked:** 2026-10-20T07:25Z by deepseek, run r-20261020T0522Z-d787, task 3

### Context
The test seeds g1/g2/a1/a2/a3 with contents that share only the single entity 'acme' and asserts report.new_links == 4. The product default is deliberately LinkSettings.min_shared_entities=2 (config.py:108), as confirmed by the Q-001 answer, and R3.1 requires memory_dream to build the engine with settings.link. A spec-compliant tool therefore creates 0 links, so this frozen assertion cannot pass without changing the fixture or violating R3.1/Q-001.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/mcp/tests/test_tenancy_dreaming_mcp_transport.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit tenant-scoped-core`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/mcp/tests/test_tenancy_dreaming_mcp_transport.py`: in `_seed_two_tenants` (lines 66-70) use contents that share two entities by replacing `"Alice works at Acme", "global"` with `"Alice works at Acme in Berlin", "global"`, `"Bob works at Acme", "global"` with `"Bob works at Acme in Berlin", "global"`, `"Alice works at Acme", "t1"` with `"Alice works at Acme in Berlin", "t1"`, `"Carol works at Acme", "t1"` with `"Carol works at Acme in Berlin", "t1"`, and `"Dan works at Acme", "t1"` with `"Dan works at Acme in Berlin", "t1"`.
2. Keep min_shared_entities=2 and change the test to assert new_links == 0 and no links at all.
3. Change production MCP dreaming to ignore settings.link and use LinkSettings(min_shared_entities=1), contradicting R3.1 and Q-001.

### Clarifier suggestion
Edit `packages/mcp/tests/test_tenancy_dreaming_mcp_transport.py`: in `_seed_two_tenants` (lines 66-70) use contents that share two entities by replacing `"Alice works at Acme", "global"` with `"Alice works at Acme in Berlin", "global"`, `"Bob works at Acme", "global"` with `"Bob works at Acme in Berlin", "global"`, `"Alice works at Acme", "t1"` with `"Alice works at Acme in Berlin", "t1"`, `"Carol works at Acme", "t1"` with `"Carol works at Acme in Berlin", "t1"`, and `"Dan works at Acme", "t1"` with `"Dan works at Acme in Berlin", "t1"`.

### Answer
<!-- write below this line -->
---

## Q-003: packages/cli/tests/test_tenancy_dreaming_cli_transport.py:112

- **Status:** accepted
- **Blocking tasks:** 3
- **Kind:** technical
- **Asked:** 2026-10-20T07:25Z by deepseek, run r-20261020T0522Z-d787, task 3

### Context
The CLI dream test seeds g1/g2/a1/a2/a3 with contents that share only 'acme' and asserts the rendered new_links is 4. The deliberate production default is min_shared_entities=2 (config.py:108, Q-001), and R3.1 requires the CLI to build the engine with settings.link, so the command correctly creates 0 links and the frozen assertion cannot pass without changing the fixture or violating R3.1/Q-001.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/cli/tests/test_tenancy_dreaming_cli_transport.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit tenant-scoped-core`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/cli/tests/test_tenancy_dreaming_cli_transport.py`: in `_seed_two_tenants` (lines 64-68) use contents that share two entities by replacing `"Alice works at Acme", "global"` with `"Alice works at Acme in Berlin", "global"`, `"Bob works at Acme", "global"` with `"Bob works at Acme in Berlin", "global"`, `"Alice works at Acme", "t1"` with `"Alice works at Acme in Berlin", "t1"`, `"Carol works at Acme", "t1"` with `"Carol works at Acme in Berlin", "t1"`, and `"Dan works at Acme", "t1"` with `"Dan works at Acme in Berlin", "t1"`.
2. Keep min_shared_entities=2 and change the test to assert new_links is 0 and no links at all.
3. Change production CLI dreaming to ignore settings.link and use LinkSettings(min_shared_entities=1), contradicting R3.1 and Q-001.

### Clarifier suggestion
Edit `packages/cli/tests/test_tenancy_dreaming_cli_transport.py`: in `_seed_two_tenants` (lines 64-68) use contents that share two entities by replacing `"Alice works at Acme", "global"` with `"Alice works at Acme in Berlin", "global"`, `"Bob works at Acme", "global"` with `"Bob works at Acme in Berlin", "global"`, `"Alice works at Acme", "t1"` with `"Alice works at Acme in Berlin", "t1"`, `"Carol works at Acme", "t1"` with `"Carol works at Acme in Berlin", "t1"`, and `"Dan works at Acme", "t1"` with `"Dan works at Acme in Berlin", "t1"`.

### Answer
<!-- write below this line -->
---

## Q-004: packages/api/tests/test_tenancy_dreaming_api_transport.py:111

- **Status:** accepted
- **Blocking tasks:** 3
- **Kind:** technical
- **Asked:** 2026-10-20T07:25Z by deepseek, run r-20261020T0522Z-d787, task 3

### Context
The API dream test seeds g1/g2/a1/a2/a3 with contents that share only 'acme' and asserts new_links == 4. R3.1 requires the API to keep building DreamingEngine(store, tenant_id=t), whose default LinkSettings has min_shared_entities=2 (config.py:108, Q-001), so it correctly creates 0 links; an environment override would not help because the API does not load LinkSettings. The frozen assertion cannot pass without changing the fixture or contradicting R3.1/Q-001.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/api/tests/test_tenancy_dreaming_api_transport.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit tenant-scoped-core`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/api/tests/test_tenancy_dreaming_api_transport.py`: in `_seed_two_tenants` (lines 67-71) use contents that share two entities by replacing `"Alice works at Acme", "global"` with `"Alice works at Acme in Berlin", "global"`, `"Bob works at Acme", "global"` with `"Bob works at Acme in Berlin", "global"`, `"Alice works at Acme", "t1"` with `"Alice works at Acme in Berlin", "t1"`, `"Carol works at Acme", "t1"` with `"Carol works at Acme in Berlin", "t1"`, and `"Dan works at Acme", "t1"` with `"Dan works at Acme in Berlin", "t1"`.
2. Keep min_shared_entities=2 and change the test to assert new_links == 0 and no links at all.
3. Change production API dreaming to build DreamingEngine with LinkSettings(min_shared_entities=1), contradicting R3.1 and Q-001.

### Clarifier suggestion
Edit `packages/api/tests/test_tenancy_dreaming_api_transport.py`: in `_seed_two_tenants` (lines 67-71) use contents that share two entities by replacing `"Alice works at Acme", "global"` with `"Alice works at Acme in Berlin", "global"`, `"Bob works at Acme", "global"` with `"Bob works at Acme in Berlin", "global"`, `"Alice works at Acme", "t1"` with `"Alice works at Acme in Berlin", "t1"`, `"Carol works at Acme", "t1"` with `"Carol works at Acme in Berlin", "t1"`, and `"Dan works at Acme", "t1"` with `"Dan works at Acme in Berlin", "t1"`.

### Answer
<!-- write below this line -->

---

## Q-005: Criterion C-7881686c (Req 3.1): accept as satisfied?

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-7881686c (Req 3.1)

### Context
Criterion C-7881686c (Req 3.1) is needs human after round 1.

Scenario:
MCP `memory_dream(intensity="light")` (`packages/mcp/src/mintmory/mcp/server.py`), CLI `dream [--full/--light]` (`packages/cli/src/mintmory/cli/main.py`) and HTTP `POST /dream` (`packages/api/src/mintmory/api/app.py`, whose route function is itself named `run_dream`, so it imports the core function as `from mintmory.core.dreaming import run_dream as run_tenant_dreams`) SHALL call `run_dream(store, intensity=…, tenant_id=None, engine_factory=…)`; MCP and CLI build engines with `build_dreaming_engine(store, settings.llm, link_settings=settings.link, summary_settings=settings.summary, tenant_id=t)`, the API with `DreamingEngine(store, tenant_id=t)` (as today, no LLM).

Why: the judge answered insufficient_evidence
Judge: insufficient_evidence
Tracing tests: packages.api.tests.test_tenancy_dreaming_api_transport::test_dream_runs_each_tenant_without_cross_tenant_links (passed, red_assertion); packages.cli.tests.test_tenancy_dreaming_cli_transport::test_dream_runs_each_tenant_without_cross_tenant_links (passed, red_assertion); packages.mcp.tests.test_tenancy_dreaming_mcp_transport::test_memory_dream_runs_each_tenant_without_cross_tenant_links (passed, red_assertion)
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
accept: verified on the unit branch: MCP memory_dream (server.py), CLI dream (main.py) and HTTP POST /dream (app.py, importing run_dream as run_tenant_dreams) each call run_dream(store, intensity=..., tenant_id=None, engine_factory=...); MCP and CLI build engines with build_dreaming_engine(store, settings.llm, link_settings=settings.link, summary_settings=settings.summary, tenant_id=t), the API with DreamingEngine(store, tenant_id=t). The three transport tests that trace it pass.
---

## Q-006: Criterion C-d9c39ea3 (Req 3.2): accept as satisfied?

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-d9c39ea3 (Req 3.2)

### Context
Criterion C-d9c39ea3 (Req 3.2) is needs human after round 1.

Scenario:
The return shape SHALL stay a `DreamReport` in every transport (MCP JSON, CLI table, API `response_model=DreamReport`): for the global scope it is the per-tenant total. `multi-tenancy-cli` and `tenant-scoped-mcp` add the named scope later with the same function.

Why: the judge answered insufficient_evidence
Judge: insufficient_evidence
Tracing tests: packages.api.tests.test_tenancy_dreaming_api_transport::test_dream_runs_each_tenant_without_cross_tenant_links (passed, red_assertion); packages.cli.tests.test_tenancy_dreaming_cli_transport::test_dream_runs_each_tenant_without_cross_tenant_links (passed, red_assertion); packages.mcp.tests.test_tenancy_dreaming_mcp_transport::test_memory_dream_runs_each_tenant_without_cross_tenant_links (passed, red_assertion)
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
accept: verified on the unit branch: run_dream returns a DreamReport (one tenant's, or DreamAllReport.total() for the global scope, the per-tenant total); MCP returns report.model_dump(mode='json'), the CLI prints the DreamReport table, the API route has response_model=DreamReport (its test parses the body as DreamReport).
---

## Q-007: Criterion C-63860dbc (Req 3.3): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-63860dbc (Req 3.3)

### Context
Criterion C-63860dbc (Req 3.3) is needs human after round 1.

Scenario:
`DreamFailedError` SHALL surface as an MCP tool error (fastmcp `ToolError` on the client), a CLI `error: <message>` on stderr with exit code 1, and HTTP 500 `{"detail": <message>}`. Test seam: monkeypatch both `mintmory.core.dreaming.DreamingEngine.run_light` and `.run_full` to raise `RuntimeError("boom")`, so every tenant's pass fails at any intensity (the CLI defaults to light, MCP's `memory_dream` to `"light"`, and the API's `DreamRequest.intensity` is required).

Why: the judge answered insufficient_evidence
Judge: insufficient_evidence
Tracing tests: packages.api.tests.test_tenancy_dreaming_api_transport::test_dream_failure_returns_500_detail (passed, red_assertion); packages.cli.tests.test_tenancy_dreaming_cli_transport::test_dream_failure_reports_error_on_stderr (passed, red_assertion); packages.mcp.tests.test_tenancy_dreaming_mcp_transport::test_memory_dream_failure_surfaces_as_a_tool_error (passed, red_assertion)
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-008: Criterion C-a0213e6c (Req 4.1): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-a0213e6c (Req 4.1)

### Context
Criterion C-a0213e6c (Req 4.1) is needs human after round 1.

Scenario:
MCP `summary_jobs` / `summary_put`, CLI `summary-jobs` / `summary-put` and HTTP `GET /summaries/jobs` / `PUT /summaries/{concept}` SHALL build their engine with `tenant_id=TENANT_GLOBAL`, so on a multi-tenant database they work on `global` memories only. On a one-tenant database the output is identical to today.

Why: the judge answered insufficient_evidence
Judge: insufficient_evidence
Tracing tests: packages.api.tests.test_tenancy_dreaming_api_transport::test_summary_routes_stay_on_the_global_tenant (passed, red_assertion); packages.cli.tests.test_tenancy_dreaming_cli_transport::test_summary_commands_stay_on_the_global_tenant (passed, red_assertion); packages.mcp.tests.test_tenancy_dreaming_mcp_transport::test_summary_paths_stay_on_the_global_tenant (passed, red_assertion)
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
