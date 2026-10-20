# Questions — multi-tenancy-cli-fix-4

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
| Q-001 | answered | 1.1 | technical | Make packages/cli/tests/conftest.py exist at HEAD for the colour-independent CLI help fixture |
<!-- l4:index:end -->

---

## Q-001: Make packages/cli/tests/conftest.py exist at HEAD for the colour-independent CLI help fixture

- **Status:** answered
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-10-20T21:16Z by deepseek, run r-20261020T2041Z-32d2, task 1.1

### Context
FB-001/F-da38e145 says: add packages/cli/tests/conftest.py with an autouse fixture that does monkeypatch.setattr(typer.rich_utils, 'FORCE_TERMINAL', None), without changing production code or the existing help test. The harness blocks this in the current phase. review_test_chore (tdd.py:1922-1949) unconditionally restores every new or changed test-support file (conftest.py matches tdd.test_support_globs) in a single 'tests' chore, ignoring any unfreeze. restore_frozen/manifest_at_head only list paths that exist at HEAD, so a brand-new conftest.py is removed by the untracked-support-file loop and no human answer can grant it. The previous two attempts were restored (ledger seq 135); Q-001 in fix-3 was answered to unfreeze the path but still could not help because the file did not exist at HEAD. The existing help tests pass in the L4 sandbox, where GITHUB_ACTIONS is unset, so this cannot be reproduced without the file. I made no changes.

### Options
1. Commit packages/cli/tests/conftest.py yourself on l4/kiro/multi-tenancy-cli before the next run, with an autouse fixture that calls monkeypatch.setattr(typer.rich_utils, 'FORCE_TERMINAL', None) for every CLI test; task 1.1 then only adds the regression test that forces FORCE_TERMINAL=True and asserts --help has no ANSI escapes and contains the tenant sentence.
2. Change this task's handling so a test-support file may be added (for example, run it outside review_test_chore with the path explicitly opened) and state that, so the implementer can add both the conftest.py fixture and the regression test.
3. Name a different mechanism the harness permits for the autouse reset, other than packages/cli/tests/conftest.py.

### Answer
<!-- write below this line -->
Option 1, done: commit 2df8259 adds packages/cli/tests/conftest.py with the autouse fixture (monkeypatch.setattr(typer.rich_utils, 'FORCE_TERMINAL', None)) on l4/kiro/multi-tenancy-cli. Checked locally: with GITHUB_ACTIONS=true all 207 CLI tests pass (test_help_documents_the_tenant_option failed without it). The regression test already exists: packages/cli/tests/test_cli_tenancy_help_colour.py (fix-3). Do not change conftest.py. Never set FORCE_TERMINAL in a test: the fixture runs before the test body, so a test that sets it to True and expects no ANSI escape fails. If task 1.1 must add a test, add one that runs `tenant --help` and asserts its output has no '\x1b[' and lists the tenant commands.
