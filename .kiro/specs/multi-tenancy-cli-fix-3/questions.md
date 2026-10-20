# Questions — multi-tenancy-cli-fix-3

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
| Q-001 | answered | 1.1 | technical | Unfreeze packages/cli/tests/conftest.py so CLI help tests are colour-independent |
<!-- l4:index:end -->

---

## Q-001: Unfreeze packages/cli/tests/conftest.py so CLI help tests are colour-independent

- **Status:** answered
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-10-20T20:17Z by deepseek, run r-20261020T2006Z-327a, task 1.1

### Context
FB-001/F-250a0697 says: fix without changing production code or test_cli_tenancy_root.py by adding packages/cli/tests/conftest.py with an autouse fixture that does monkeypatch.setattr(typer.rich_utils, 'FORCE_TERMINAL', None) for every CLI test. The harness rejected the previous attempt because it restored that new file with rule 'test support file' (ledger r-20261020T2006Z-327a, seq 41), leaving the existing test to fail whenever GITHUB_ACTIONS makes Typer force a colour terminal. The file is the only place an autouse fixture can live for all CLI test modules; modifying an existing conftest or the frozen test file has the same problem.

### Options
1. Unfreeze packages/cli/tests/conftest.py for task 1.1: allow the new file with the autouse FORCE_TERMINAL=None fixture, plus a regression test that forces FORCE_TERMINAL=True and asserts --help has no ANSI escapes.
2. Name a different non-frozen support file/location where the harness permits the autouse fixture to be added.

### Answer
<!-- write below this line -->
Option 1. Unfreeze packages/cli/tests/conftest.py for task 1.1: add it as a new file with an autouse fixture that sets typer.rich_utils.FORCE_TERMINAL to None (monkeypatch.setattr), so every CLI test renders help as on a non-terminal whatever GITHUB_ACTIONS, FORCE_COLOR or PY_COLORS say (the repository CI sets GITHUB_ACTIONS=true). Add the regression test in a new test file: with FORCE_TERMINAL forced to True and then the conftest reset applied, --help has no ANSI escape (\x1b[) and contains the tenant option sentence. Do not change production code or packages/cli/tests/test_cli_tenancy_root.py.
