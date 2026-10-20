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
