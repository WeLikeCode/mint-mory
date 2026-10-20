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
| Q-001 | open | 2 | technical | packages/cli/tests/test_cli_tenancy_root.py:41 — `--tenant acme add` success contradicts R2.4/R6.4 |
<!-- l4:index:end -->

---

## Q-001: packages/cli/tests/test_cli_tenancy_root.py:41 — `--tenant acme add` success contradicts R2.4/R6.4

- **Status:** open
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
