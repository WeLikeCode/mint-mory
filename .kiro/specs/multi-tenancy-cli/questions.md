# Questions — multi-tenancy-cli

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
| Q-001 | accepted | 2 | technical | packages/cli/tests/test_cli_tenancy_root.py:41 — `--tenant acme add` success contradicts R2.4/R6.4 |
| Q-002 | answered | none | verdict | Criterion C-8610aa4b (Req 2.2): accept as satisfied? |
| Q-003 | answered | none | verdict | Criterion C-92f6541b (Req 2.3): accept as satisfied? |
| Q-004 | answered | none | verdict | Criterion C-b86d1447 (Req 2.4): accept as satisfied? |
| Q-005 | open | none | verdict | Criterion C-5dc41637 (Req 5.2): accept as satisfied? |
| Q-006 | open | none | verdict | Criterion C-17c1d2d1 (Req 6.4): accept as satisfied? |
| Q-007 | open | none | verdict | Criterion C-29450002 (Req 6.6): accept as satisfied? |
| Q-008 | open | none | verdict | Criterion C-f9c22bd5 (Req 6.7): accept as satisfied? |
| Q-009 | open | none | verdict | Criterion C-fbe84147 (Req 6.8): accept as satisfied? |
| Q-010 | open | none | verdict | Criterion C-0459af16 (Req 6.9): accept as satisfied? |
| Q-011 | open | none | verdict | Criterion C-5cf1ac32 (Req 6.10): accept as satisfied? |
| Q-012 | open | none | verdict | Criterion C-a9f24733 (Req 6.11): accept as satisfied? |
| Q-013 | open | none | verdict | Finding F-2192b892: Global image-caption-put exits 2, not 1 |
<!-- l4:index:end -->

---

## Q-001: packages/cli/tests/test_cli_tenancy_root.py:41 — `--tenant acme add` success contradicts R2.4/R6.4

- **Status:** accepted
- **Blocking tasks:** 2
- **Kind:** technical
- **Asked:** 2026-10-20T11:52Z by deepseek, run r-20261020T1121Z-d7e0, task 2

### Context
The frozen task-1 test test_tenant_option_goes_before_the_command invokes `runner.invoke(app, ["--tenant", "acme", "add", "x"])` on a fresh cli_db where tenant acme was never created and asserts exit_code == 0 and `Added memory`. Task 2 criterion C-b86d1447 (R2.4) requires every writing command, including `add`, to check `store.get_tenant(_TENANT)` before any work and raise TenantNotFoundError when the tenant is None (exit 1), and R6.4/C-17c1d2d1 explicitly asserts `--tenant nope add x` exits 1 with `tenant 'nope' not found`. Both cannot hold on the same fresh DB: the new guard makes the task-1 test fail with `error: tenant 'acme' not found` (exit 1), though all task-2 tests pass.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/cli/tests/test_cli_tenancy_root.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy-cli`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/cli/tests/test_cli_tenancy_root.py`: insert `created = runner.invoke(app, ["tenant", "create", "acme"]); assert created.exit_code == 0, created.output` immediately before `before = runner.invoke(app, ["--tenant", "acme", "add", "x"])`.
2. Keep the test unchanged and waive R2.4/R6.4 for `add`, accepting that `--tenant <missing> add` exits 0 and writes a row in a non-existent tenant.

### Clarifier suggestion
Edit `packages/cli/tests/test_cli_tenancy_root.py`: insert `created = runner.invoke(app, ["tenant", "create", "acme"]); assert created.exit_code == 0, created.output` immediately before `before = runner.invoke(app, ["--tenant", "acme", "add", "x"])`.

### Answer
<!-- write below this line -->

---

## Q-002: Criterion C-8610aa4b (Req 2.2): accept as satisfied?

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-8610aa4b (Req 2.2)

### Context
Criterion C-8610aa4b (Req 2.2) is needs human after round 1.

Scenario:
`dream` without `--tenant` (or with `--tenant global`) SHALL dream every active tenant separately and print the per-tenant total; `--tenant T` dreams only `T`.

Why: uncovered: no adequate discriminating test traces it
Judge: pass
Tracing tests: none
Ignored tests: packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3))

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
accept: main.py:335 passes _read_tenant() to run_dream; dreaming.py:1066-1083 dreams each active tenant separately and prints total(); --tenant T runs only T (a CliRunner probe: --tenant acme dream made only acme links)
---

## Q-003: Criterion C-92f6541b (Req 2.3): accept as satisfied?

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-92f6541b (Req 2.3)

### Context
Criterion C-92f6541b (Req 2.3) is needs human after round 1.

Scenario:
A read confined to a missing tenant SHALL print an empty result and exit 0 (`mintmory --tenant nope search x` prints `0 result(s)`); so do the job lists `summary-jobs` and `image-jobs` (they only read, with `W`).

Why: uncovered: no adequate discriminating test traces it
Judge: pass
Tracing tests: none
Ignored tests: packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled (it traces 7 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3))

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
accept: --tenant nope search / summary-jobs / image-jobs exit 0 with empty results (test_cli_tenancy.py 179-185, 440-442, 480-482; confirmed by a CliRunner probe)
---

## Q-004: Criterion C-b86d1447 (Req 2.4): accept as satisfied?

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-b86d1447 (Req 2.4)

### Context
Criterion C-b86d1447 (Req 2.4) is needs human after round 1.

Scenario:
Before any work, every writing command of R2.1 — `add`, `ingest`, `note`, `summary-put`, `image-caption-put`, `vision-run` — SHALL, when `_TENANT` is set, check `store.get_tenant(_TENANT)` and raise `TenantNotFoundError` when it is `None` and `TenantInactiveError` when it is inactive (exit 1, R5), so the outcome never depends on whether the command reaches a guarded write. (`dream` gets the same check from `run_dream`.)

Why: uncovered: no adequate discriminating test traces it
Judge: pass
Tracing tests: none
Ignored tests: packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled (it traces 7 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_note_and_notes_are_tenant_scoped (it traces 5 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_vision_run_and_caption_put_use_the_write_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3))

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
accept: _check_write_tenant (main.py:102) runs before any store work in add, ingest, note, summary-put, image-caption-put and vision-run (main.py:263, 485, 1248, 1369, 1488, 1534); dream gets the check from run_dream (dreaming.py:1076-1079); all exit 1 for a missing or inactive tenant
---

## Q-005: Criterion C-5dc41637 (Req 5.2): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-5dc41637 (Req 5.2)

### Context
Criterion C-5dc41637 (Req 5.2) is needs human after round 1.

Scenario:
`TenantNotFoundError` / `TenantInactiveError` from a write SHALL leave the database unchanged.

Why: uncovered: no adequate discriminating test traces it
Judge: pass
Tracing tests: none
Ignored tests: packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled (it traces 7 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_note_and_notes_are_tenant_scoped (it traces 5 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_vision_run_and_caption_put_use_the_write_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3))

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-006: Criterion C-17c1d2d1 (Req 6.4): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-17c1d2d1 (Req 6.4)

### Context
Criterion C-17c1d2d1 (Req 6.4) is needs human after round 1.

Scenario:
Missing and inactive tenants: `--tenant nope add x` → exit 1, stderr `tenant 'nope' not found`, no row; `--tenant nope search x` → exit 0, `0 result(s)`; after `set_tenant_active("acme", False)` (Python API on the same file) `--tenant acme add y` → exit 1 with `is inactive` and `--tenant acme search uses` still lists the Acme row.

Why: uncovered: no adequate discriminating test traces it
Judge: pass
Tracing tests: none
Ignored tests: packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled (it traces 7 criteria (verifier.max_criteria_per_test=3))

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-007: Criterion C-29450002 (Req 6.6): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-29450002 (Req 6.6)

### Context
Criterion C-29450002 (Req 6.6) is needs human after round 1.

Scenario:
ingest: a file `a.txt` holding `Acme ingest fact`; `--tenant acme ingest a.txt` stores one `acme` row; repeating it stores nothing (dedup within `acme`); `ingest a.txt` then stores one `global` row (the `acme` copy does not suppress it).

Why: uncovered: no adequate discriminating test traces it
Judge: pass
Tracing tests: none
Ignored tests: packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3))

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-008: Criterion C-f9c22bd5 (Req 6.7): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-f9c22bd5 (Req 6.7)

### Context
Criterion C-f9c22bd5 (Req 6.7) is needs human after round 1.

Scenario:
note/notes: `global` holds "Initech HQ is in Austin"; `--tenant acme add "Carol works at Initech"` (the only `acme` memory about Initech); `--tenant acme note "renew contract" --about Initech` stores a note with `tenant_id == "acme"` and one `ANNOTATES` link from the note to the Carol memory (`anchor_kind == "memory"`: with the `global` memory out of reach it is the only, hence dominant, candidate), never to the `global` one; `--tenant acme notes` lists it; `notes` (unscoped) lists it too.

Why: uncovered: no adequate discriminating test traces it
Judge: pass
Tracing tests: none
Ignored tests: packages.cli.tests.test_cli_tenancy::test_note_and_notes_are_tenant_scoped (it traces 5 criteria (verifier.max_criteria_per_test=3))

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-009: Criterion C-fbe84147 (Req 6.8): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-fbe84147 (Req 6.8)

### Context
Criterion C-fbe84147 (Req 6.8) is needs human after round 1.

Scenario:
dream: `acme` holds "Carol works at Initech" and "Dan works at Initech", `global` holds "Alice works at Acme" and "Bob works at Acme"; `--tenant nope dream` exits 1 with `tenant 'nope' not found`: `--tenant acme dream` creates links only between `acme` memories (the Carol–Dan link among them) and none touching a `global` memory; a following `dream` adds the Alice–Bob link; no link ever joins two tenants (in the integration sequence of R6.13 the same assertions hold over the accumulated data).

Why: uncovered: no adequate discriminating test traces it
Judge: pass
Tracing tests: none
Ignored tests: packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3))

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-010: Criterion C-0459af16 (Req 6.9): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-0459af16 (Req 6.9)

### Context
Criterion C-0459af16 (Req 6.9) is needs human after round 1.

Scenario:
summary-jobs/summary-put: `acme` holds "Carol works at Initech", "Dan works at Initech", "Eve works at Initech" and `global` holds "Alice works at Acme", "Bob works at Acme", "Frank works at Acme"; `--tenant acme summary-jobs --json` lists concept `initech` and not `acme`; `--tenant acme summary-put initech "Initech summary"` stores a summary with `tenant_id == "acme"`; `--tenant nope summary-jobs --json` prints `[]` and exits 0.

Why: uncovered: no adequate discriminating test traces it
Judge: pass
Tracing tests: none
Ignored tests: packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3))

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-011: Criterion C-5cf1ac32 (Req 6.10): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-5cf1ac32 (Req 6.10)

### Context
Criterion C-5cf1ac32 (Req 6.10) is needs human after round 1.

Scenario:
image-jobs/image-caption-put: an `acme` image file-record added with `add_memory(record=MemoryRecord(content="x.png", category="context", source="document", tenant_id="acme", metadata={"path": "/tmp/x.png", "rel": "x.png", "ext": ".png", "size": 10, "collection": "c"}))`: `--tenant acme image-jobs --json` lists its id and `image-jobs --json` does not; `--tenant acme image-caption-put <id> "a cat"` stores a description with `tenant_id == "acme"`; `image-caption-put <id> "a cat"` (global) exits 1 and its output contains today's `no active image file-record found`.

Why: uncovered: no adequate discriminating test traces it
Judge: fail
Tracing tests: none
Ignored tests: packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3))

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-012: Criterion C-a9f24733 (Req 6.11): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-a9f24733 (Req 6.11)

### Context
Criterion C-a9f24733 (Req 6.11) is needs human after round 1.

Scenario:
vision-run: with `mintmory.core.vision.captioner_from_settings` monkeypatched to return a stub object and `mintmory.core.vision.caption_pending_images` monkeypatched to record its keyword arguments and return `CaptionRunReport()`, `--tenant acme vision-run` exits 0 and the recorded `tenant_id` is `"acme"`; `--tenant nope vision-run` and `--tenant nope image-caption-put x "a cat"` exit 1 with `tenant 'nope' not found` (R2.4).

Why: uncovered: no adequate discriminating test traces it
Judge: pass
Tracing tests: none
Ignored tests: packages.cli.tests.test_cli_tenancy::test_vision_run_and_caption_put_use_the_write_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3))

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-013: Finding F-2192b892: Global image-caption-put exits 2, not 1

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier

### Context
The judge raised a major finding in round 1, and no deterministic check confirms it (criterion C-5cf1ac32). It reports behaviour that no scenario pins down.

Title: Global image-caption-put exits 2, not 1
Detail: R6.10 requires exit 1 with 'no active image file-record found'; the code exits 2 via BadParameter and the test was weakened to != 0.
Suggested fix: WHEN image-caption-put is given an id or path with no active image file-record in the selected tenant THEN the command exits 2 with a usage error containing 'no active image file-record found'.

Answer `accept` to waive the finding, or `reject` and say why: a rejected finding is fixed by a fix unit.

### Options
1. accept
2. reject: <reason>

### Answer
<!-- write below this line -->
