# Questions — multi-tenancy-postgres-reads

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
| Q-001 | answered | 1 | technical | packages/core/tests/test_pg_tenancy_reads.py:222 scoped invocation does not pass a tenant |
<!-- l4:index:end -->

---

## Q-001: packages/core/tests/test_pg_tenancy_reads.py:222 scoped invocation does not pass a tenant

- **Status:** answered
- **Blocking tasks:** 1
- **Kind:** technical
- **Asked:** 2026-10-21T21:28Z by deepseek, run r-20261021T2100Z-e2d8, task 1

### Context
test_pg_read_adds_tenant_predicate_and_keeps_none_sql first calls `case.invoke(backend)` and asserts the executed SELECT contains `tenant_id = %s` with `_TENANT` in its parameters, then calls `case.invoke(backend)` again and asserts no `tenant_id =` predicate. Every ReadCase.invoke lambda in `_read_cases()` takes only `backend` and calls the method without `tenant_id` (for example `lambda backend: backend.get_memory("m1")`), so both invocations are identical `None` calls. Requirement 1.3 requires the first call to use `tenant_id="t1"` and the second `None`, so no backend implementation can satisfy both assertions. This is a technical defect in the red test, not an ambiguity in the spec.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_pg_tenancy_reads.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy-postgres-reads`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_pg_tenancy_reads.py`: change `ReadCase.invoke` to `Callable[[PostgresBackend, str | None], object]`, add a `tenant` parameter to every lambda in `_read_cases()` and pass it as the trailing `tenant_id` argument (e.g. `lambda backend, tenant: backend.get_memory("m1", tenant)`), and change line 222 to `_call_without_guard(lambda: case.invoke(backend, _TENANT))`.
2. Edit `packages/core/tests/test_pg_tenancy_reads.py`: keep the lambdas as-is but change `_read_cases()` entries to carry two invokers (`scoped_invoke` and `unscoped_invoke`) and call the scoped one on line 222.

### Clarifier suggestion
Edit `packages/core/tests/test_pg_tenancy_reads.py`: change `ReadCase.invoke` to `Callable[[PostgresBackend, str | None], object]`, add a `tenant` parameter to every lambda in `_read_cases()` and pass it as the trailing `tenant_id` argument (e.g. `lambda backend, tenant: backend.get_memory("m1", tenant)`), and change line 222 to `_call_without_guard(lambda: case.invoke(backend, _TENANT))`.

### Answer
<!-- write below this line -->
Option 1, with the tenant passed by keyword: for task 1 edit packages/core/tests/test_pg_tenancy_reads.py. Change ReadCase.invoke to Callable[[PostgresBackend, str | None], object]; give every lambda in _read_cases() a `tenant` parameter and pass it as `tenant_id=tenant` (by keyword, never positionally: anchor_candidates(about, limit, tenant_id) and get_never_accessed_stale(days_old, min_staleness, tenant_id) would take it as the wrong argument, and list_notes is keyword-only); the first call (line 222) is case.invoke(backend, _TENANT) and the second case.invoke(backend, None). Change no other file under packages/core/tests. (Answered by the owner's delegate on the owner's explicit instruction, 2026-10-22.)
