# Questions — add-local-observability-stack-fix-2

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
| Q-001 | answered | 1.1 | ambiguous | Removing the skipif markers edits existing tests, which this test-chore step reverts |
<!-- l4:index:end -->

---

## Q-001: Removing the skipif markers edits existing tests, which this test-chore step reverts

- **Status:** answered
- **Blocking tasks:** 1.1
- **Kind:** ambiguous
- **Asked:** 2026-10-18T19:59Z by deepseek, run r-20261018T1952Z-fb34, task 1.1

### Context
F-f5fcb85c (FB-001) names tests/integration/test_helm_telemetry.py:121-131 and tests/integration/test_observability_stack.py:197-199 and asks to remove the three `@pytest.mark.skipif(shutil.which(...) is None, ...)` decorators while keeping the tests. This run's phase is a single test chore (`.l4/fix.json` lists F-f5fcb85c under both `chores` and `test_chores`, so `chore_kind` is `tests`). The phase contract says no existing test may be changed ("a test you edit or remove is put back"), and `l4.implementer.tdd.review_test_chore` keeps only new test files or tests that are purely appended to a unit-owned test file (`appended_only`); any other change to an existing test file is reverted and logged as `guard.test_tamper`. Removing a decorator changes an existing top-level statement, so `appended_only` is False and the edit is reverted (I verified this with the installed harness). This is the same guard that left fix-1 with no code change, and the injected lesson says not to touch the frozen test paths. Because the requested result is a modification of existing tests, no test I can add in this step can remove those markers, and no stub/guarded parameter applies (the subject is not production code). To let the decorators be removed, the existing test paths must be unfrozen for this task (the `[test-infra]` task tag, or a human answer that unfreezes those two files), or the finding must be routed as a fix/refactor chore that runs under the normal green step rather than a test chore.

### Options
1. Unfreeze tests/integration/test_helm_telemetry.py and tests/integration/test_observability_stack.py for task 1.1 (or tag the task `[test-infra]`) so the three decorators may be removed as FB-001 asks.
2. Keep the markers (accept FB-001 as unaddressable under the test-chore guard) and withdraw F-f5fcb85c.

### Answer
<!-- write below this line -->
Option 1: unfreeze tests/integration/test_helm_telemetry.py and tests/integration/test_observability_stack.py for task 1.1. Remove only the three @pytest.mark.skipif(shutil.which(...) is None, ...) decorators (and an import of shutil left unused); change nothing else in those files. helm and docker are on the gate runner: these tests already ran and passed in the gates.
