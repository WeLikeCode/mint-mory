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
| Q-002 | answered | 1 | technical | packages/core/tests/test_pg_tenancy.py:641 read tests still require the interim guard |
| Q-003 | answered | 1 | technical | packages/core/tests/test_pg_tenancy_columns.py:456 keyed reads still require the interim guard |
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

---

## Q-002: packages/core/tests/test_pg_tenancy.py:641 read tests still require the interim guard

- **Status:** answered
- **Blocking tasks:** 1
- **Kind:** technical
- **Asked:** 2026-10-21T21:48Z by deepseek, run r-20261021T2131Z-5a19, task 1

### Context
R1.2 says the read `test_pg_<method>_tenancy` functions of `packages/core/tests/test_pg_tenancy.py` SHALL be rewritten in place (same names) to assert R1.3, and that `test_pg_get_summary_tenancy`, `test_pg_manifest_get_tenancy` and `test_pg_manifest_paths_tenancy` SHALL be rewritten to assert a tenant-scoped SELECT that raises nothing. The file is frozen at its old behaviour: `test_pg_require_global_tenant_tenancy` (line 105) requires `_require_global_tenant` to exist, lines 121-190 expect the keyed reads to raise `TenancyNotSupportedError`, and lines 629-928 expect all 25 reads (`_assert_read_rejects_tenant`, `test_pg_get_memory_tenancy`, ... `test_pg_list_memories_tenancy`) to raise before touching the pool. The new red test `test_pg_tenancy_reads.py:339` requires `_require_global_tenant` to be deleted and the red read tests require the tenant SQL, so the two are mutually exclusive. Red did not rewrite these tests (only test_pg_tenancy_reads.py was added), green cannot change tests, and the Q-001 answer says not to change other test files.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_pg_tenancy.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy-postgres-reads`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_pg_tenancy.py`: delete `test_pg_require_global_tenant_tenancy` (lines 105-112); rewrite `test_pg_get_summary_tenancy`, `test_pg_manifest_get_tenancy` and `test_pg_manifest_paths_tenancy` (lines 121-190) to assert that `get_summary("c", tenant_id="t1")`, `manifest_get("/a", tenant_id="t1")` and `manifest_paths("c", tenant_id="t1")` execute a SELECT containing `tenant_id = %s` with `"t1"` among the parameters and raise nothing; and rewrite `_assert_read_rejects_tenant` plus every `test_pg_<method>_tenancy` read test (lines 629-928) to drive each read through `FakePool` and assert the R1.3 tenant predicate and parameters, keeping the same function names.
2. Edit `packages/core/tests/test_pg_tenancy.py`: keep the file frozen and accept that its 25 read tests, `test_pg_require_global_tenant_tenancy` and the three keyed tests will fail after R1.2.

### Clarifier suggestion
Edit `packages/core/tests/test_pg_tenancy.py`: delete `test_pg_require_global_tenant_tenancy` (lines 105-112); rewrite `test_pg_get_summary_tenancy`, `test_pg_manifest_get_tenancy` and `test_pg_manifest_paths_tenancy` (lines 121-190) to assert that `get_summary("c", tenant_id="t1")`, `manifest_get("/a", tenant_id="t1")` and `manifest_paths("c", tenant_id="t1")` execute a SELECT containing `tenant_id = %s` with `"t1"` among the parameters and raise nothing; and rewrite `_assert_read_rejects_tenant` plus every `test_pg_<method>_tenancy` read test (lines 629-928) to drive each read through `FakePool` and assert the R1.3 tenant predicate and parameters, keeping the same function names.

### Answer
<!-- write below this line -->
Option 1, except that no test function is deleted (R1.2: "None is deleted"): for task 1 edit packages/core/tests/test_pg_tenancy.py. Rewrite test_pg_require_global_tenant_tenancy in place (same name, same l4 markers) to assert that PostgresBackend no longer has `_require_global_tenant` and that TenancyNotSupportedError is still importable from mintmory.core.types; rewrite test_pg_get_summary_tenancy, test_pg_manifest_get_tenancy and test_pg_manifest_paths_tenancy to assert that get_summary("c", tenant_id="t1"), manifest_get("/a", tenant_id="t1") and manifest_paths("c", tenant_id="t1") execute a SELECT containing `tenant_id = %s` with "t1" among its parameters and raise nothing; rewrite _assert_read_rejects_tenant and every read test_pg_<method>_tenancy (same names) to drive each read through FakePool and assert R1.3 (tenant predicate and parameter position for "t1", today's SQL and parameters for None). Change no other file under packages/core/tests except as other answers say. (Answered by the owner's delegate on the owner's explicit instruction, 2026-10-22.)
---

## Q-003: packages/core/tests/test_pg_tenancy_columns.py:456 keyed reads still require the interim guard

- **Status:** answered
- **Blocking tasks:** 1
- **Kind:** technical
- **Asked:** 2026-10-21T21:48Z by deepseek, run r-20261021T2131Z-5a19, task 1

### Context
`test_guards_stay_on_record_writes_and_keyed_methods_before_pool_access` calls `get_summary("acme", tenant_id="acme")`, `manifest_get("/a", tenant_id="acme")` and `manifest_paths("default", tenant_id="acme")` inside `pytest.raises(TenancyNotSupportedError)`. R1.2 (and the red keyed test in `test_pg_tenancy_reads.py`) require those same calls to execute a tenant-scoped SELECT and raise nothing; `_require_global_tenant` is deleted. No implementation can satisfy both. The same test's `add_memory` write-guard assertions do remain valid.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_pg_tenancy_columns.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy-postgres-reads`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_pg_tenancy_columns.py`: in `test_guards_stay_on_record_writes_and_keyed_methods_before_pool_access` (line 428) replace the loop that expects `TenancyNotSupportedError` from `get_summary`/`manifest_get`/`manifest_paths` with assertions that each of those calls executes a SELECT containing `tenant_id = %s` with `_TENANT` (`"acme"`) among its parameters and raises nothing, keeping the `add_memory` write-guard assertions.
2. Edit `packages/core/tests/test_pg_tenancy_columns.py`: keep the file frozen and accept that `test_guards_stay_on_record_writes_and_keyed_methods_before_pool_access` will fail after R1.2.

### Clarifier suggestion
Edit `packages/core/tests/test_pg_tenancy_columns.py`: in `test_guards_stay_on_record_writes_and_keyed_methods_before_pool_access` (line 428) replace the loop that expects `TenancyNotSupportedError` from `get_summary`/`manifest_get`/`manifest_paths` with assertions that each of those calls executes a SELECT containing `tenant_id = %s` with `_TENANT` (`"acme"`) among its parameters and raises nothing, keeping the `add_memory` write-guard assertions.

### Answer
<!-- write below this line -->
Option 1 (accepted by the owner's delegate on the owner's explicit instruction, 2026-10-22): edit packages/core/tests/test_pg_tenancy_columns.py for task 1 as the suggestion says.
