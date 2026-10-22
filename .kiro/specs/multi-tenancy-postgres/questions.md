# Questions — multi-tenancy-postgres

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
| Q-001 | answered | 1 | technical | packages/core/tests/test_pg_fakes.py:24 — deliverable pg_fakes.py is frozen as a red test, so the R5.1 stubs can never pass |
<!-- l4:index:end -->

---

## Q-001: packages/core/tests/test_pg_fakes.py:24 — deliverable pg_fakes.py is frozen as a red test, so the R5.1 stubs can never pass

- **Status:** answered
- **Blocking tasks:** 1
- **Kind:** technical
- **Asked:** 2026-10-21T10:20Z by glm, run r-20261021T0949Z-2268, task 1

### Context
The 12 frozen self-tests assert the full R5.1 fake behaviour against packages.core.tests.pg_fakes (e.g. line 24 `conn.executed == [("SELECT * FROM memories WHERE id = %s", ("m1",))]`, line 60 `conn.commits == 2`, line 75 the fail_on RuntimeError). The task line and R5.1 name packages/core/tests/pg_fakes.py as the deliverable that SHALL provide FakePool/FakeConnection/FakeCursor, but the red commit included that file as zero-value stubs and the harness classified it as a frozen red test: the ledger's task.unfrozen events record paths: [] with kept: [{path: packages/core/tests/pg_fakes.py, why: "a red test of this task"}], and guard.test_tamper fired on that exact path in green attempts 1-3, restoring the stubs each time before judging. The tests import directly from that module and packages/core/tests has no conftest.py, so no edit outside it can make them pass: green is unreachable while the file stays frozen.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `conftest.py`, `packages/core/tests/pg_fakes.py`, `packages/core/tests/test_pg_fakes.py`, write an answer that names its path exactly as written here or run `l4 questions accept Q-NNN --unit multi-tenancy-postgres`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit packages/core/tests/pg_fakes.py: unfreeze this one file for task 1 so its zero-value stubs are replaced with the full R5.1 implementation (recording executed/commits/rollbacks, responder rows returned exactly as the code reads them, fail_on raising RuntimeError(f"fake failure: {sql}") after recording, cursor executemany recording one entry per parameter set, FakePool.connection() yielding the given or factory-made connection with connections/checkouts tracking and rollback-on-exception, close() a no-op).
2. Edit the task plan: add packages/core/tests/pg_fakes.py to task 1's named paths so task.unfrozen unfreezes it (test_pg_fakes.py stays frozen).

### Answer
<!-- write below this line -->
Option 1: unfreeze packages/core/tests/pg_fakes.py for task 1 and replace its zero-value stubs with the full R5.1 FakePool, FakeConnection and FakeCursor that the frozen self-tests assert; change no other file under packages/core/tests. (Answered by the owner's delegate on the owner's explicit instruction, 2026-10-21.)
