# Questions — multi-tenancy

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
| Q-001 | accepted | 5 | technical | packages/core/tests/test_tenant_directory.py:191 |
| Q-002 | accepted | 7 | technical | packages/core/tests/test_tenant_schema_gate.py:29 |
| Q-003 | answered | none | verdict | Criterion C-877680dc (Req 4.6): accept as satisfied? |
| Q-004 | open | none | verdict | Hold H-e0757174: the diff is longer than 120000 characters: the judge saw only the start |
<!-- l4:index:end -->

---

## Q-001: packages/core/tests/test_tenant_directory.py:191

- **Status:** accepted
- **Blocking tasks:** 5
- **Kind:** technical
- **Asked:** 2026-10-19T16:22Z by deepseek, run r-20261019T1437Z-76f9, task 5

### Context
test_set_tenant_active_updates_flag_and_timestamp calls `_insert_tenant(store, "acme", name="Acme", updated_at="2020-01-01T00:00:00")`. The helper defaults `created_at` to "2026-01-01T00:00:00", but line 199 asserts `row["created_at"] == "2020-01-01T00:00:00"`. set_tenant_active must not modify created_at, so the assertion is unsatisfiable as written; the spec (R5.4) only says to update is_active and updated_at.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_tenant_directory.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_tenant_directory.py`: at line 191 change `_insert_tenant(store, "acme", name="Acme", updated_at="2020-01-01T00:00:00")` to `_insert_tenant(store, "acme", name="Acme", created_at="2020-01-01T00:00:00", updated_at="2020-01-01T00:00:00")`
2. Edit `packages/core/tests/test_tenant_directory.py`: at line 199 change `assert row["created_at"] == "2020-01-01T00:00:00"` to `assert row["created_at"] == "2026-01-01T00:00:00"`

### Clarifier suggestion
Edit `packages/core/tests/test_tenant_directory.py`: at line 191 change `_insert_tenant(store, "acme", name="Acme", updated_at="2020-01-01T00:00:00")` to `_insert_tenant(store, "acme", name="Acme", created_at="2020-01-01T00:00:00", updated_at="2020-01-01T00:00:00")`

### Answer
<!-- write below this line -->

---

## Q-002: packages/core/tests/test_tenant_schema_gate.py:29

- **Status:** accepted
- **Blocking tasks:** 7
- **Kind:** technical
- **Asked:** 2026-10-19T17:16Z by deepseek, run r-20261019T1645Z-97d7, task 7

### Context
The red test requires test_schema.py to gain the tenants table, tenant_id columns, the three tenant indexes and a global-row assertion (R7.1). test_schema.py is an existing test file frozen for the green step: the previous attempt's edit was restored with 'green may not change test files; tests belong in the red step'. The other R7.2 deliverable (OpenAPI) is already implemented and passing.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_schema.py`, `packages/core/tests/test_tenant_schema_gate.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_schema.py`: add `tenants` to `REQUIRED_TABLES`; add `tenant_id` to `REQUIRED_MEMORIES_COLUMNS`, `REQUIRED_LINKS_COLUMNS` and `REQUIRED_SESSIONS_COLUMNS`; add `REQUIRED_SUMMARY_COLUMNS`, `REQUIRED_RESULTS_COLUMNS` and `REQUIRED_MANIFEST_COLUMNS` (each including `tenant_id`) with column tests using `PRAGMA table_info(memory_summaries)`, `PRAGMA table_info(query_results)` and `PRAGMA table_info(index_manifest)`; add `idx_memories_tenant`, `idx_links_tenant` and `idx_sessions_tenant` to `REQUIRED_INDEXES`; and add `test_tenants_has_exactly_one_global_row` asserting the seeded row `('global', 'Global (default) tenant', 1, '1970-01-01T00:00:00')` via a `SELECT ... FROM tenants` query.
2. Keep test_schema.py frozen and accept that R7.1 cannot be delivered in this task.

### Clarifier suggestion
Edit `packages/core/tests/test_schema.py`: add `tenants` to `REQUIRED_TABLES`; add `tenant_id` to `REQUIRED_MEMORIES_COLUMNS`, `REQUIRED_LINKS_COLUMNS` and `REQUIRED_SESSIONS_COLUMNS`; add `REQUIRED_SUMMARY_COLUMNS`, `REQUIRED_RESULTS_COLUMNS` and `REQUIRED_MANIFEST_COLUMNS` (each including `tenant_id`) with column tests using `PRAGMA table_info(memory_summaries)`, `PRAGMA table_info(query_results)` and `PRAGMA table_info(index_manifest)`; add `idx_memories_tenant`, `idx_links_tenant` and `idx_sessions_tenant` to `REQUIRED_INDEXES`; and add `test_tenants_has_exactly_one_global_row` asserting the seeded row `('global', 'Global (default) tenant', 1, '1970-01-01T00:00:00')` via a `SELECT ... FROM tenants` query.

### Answer
<!-- write below this line -->

---

## Q-003: Criterion C-877680dc (Req 4.6): accept as satisfied?

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-877680dc (Req 4.6)

### Context
Criterion C-877680dc (Req 4.6) is needs human after round 1.

Scenario:
With only the `global` tenant, every existing test SHALL pass unchanged (`test_schema.py` gets the additions of R7 only).

Why: uncovered: no adequate discriminating test traces it
Judge: pass
Tracing tests: none
Ignored tests: packages.core.tests.test_tenant_persistence::test_memory_tenant_id_persists_and_round_trips (it traces 4 criteria (verifier.max_criteria_per_test=3))

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
accept: Req 4.6 is an invariant over the existing suite. The tests gate ran the whole suite green in round 1 (step 3 ok), and the only pre-existing test file the unit changed is packages/core/tests/test_schema.py, with 65 added lines and none removed: the R7.1 additions accepted in Q-002. No other existing test changed.
---

## Q-004: Hold H-e0757174: the diff is longer than 120000 characters: the judge saw only the start

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier

### Context
After round 1 the verifier cannot decide on its own: the diff is longer than 120000 characters: the judge saw only the start

Answer `accept` if the unit can go on as it stands, or `reject` and say why; end the reason with a sentence WHEN ... THEN ... so that a fix unit can be made.

### Options
1. accept
2. reject: <reason>

### Answer
<!-- write below this line -->
