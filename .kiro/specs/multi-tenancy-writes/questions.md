# Questions — multi-tenancy-writes

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
| Q-001 | answered | 3 | ambiguous | packages/core/tests/test_tenant_persistence.py:91 contradicts requirement 2.5 |
<!-- l4:index:end -->

---

## Q-001: packages/core/tests/test_tenant_persistence.py:91 contradicts requirement 2.5

- **Status:** answered
- **Blocking tasks:** 3
- **Kind:** ambiguous
- **Asked:** 2026-10-19T19:22Z by deepseek, run r-20261019T1754Z-ec85, task 3

### Context
test_update_memory_does_not_write_tenant_id expects update_memory(record.id, content="Alice works at Globex", tenant_id="t2") on a row stored in t1 to succeed silently and leave tenant_id=t1. Requirement 2.5 (and packages/core/tests/test_tenancy_references.py:446-452) require TenantImmutableError whenever fields carries a tenant_id different from the stored tenant. Both test files are frozen, so the gate cannot pass without unfreezing one of them.

### Options
1. Edit `packages/core/tests/test_tenant_persistence.py`: replace line 91 with a content-only update `store.update_memory(record.id, content="Alice works at Globex")` and add `with pytest.raises(TenantImmutableError): store.update_memory(record.id, tenant_id="t2")`, keeping the existing assertions that the stored tenant stays t1.
2. Edit `packages/core/tests/test_tenancy_references.py`: remove the differing-tenant assertions at lines 446-452 and keep the old silent-ignore behaviour for update_memory(tenant_id=...).
3. Keep both test files unchanged and accept that this criterion cannot be satisfied together with the existing test.

### Answer
<!-- write below this line -->
Option 1. Requirement 2.5 of this unit deliberately changes the behaviour the multi-tenancy unit pinned: a differing tenant_id on update_memory now raises TenantImmutableError, while the stored tenant is still never written. So the older test changes, not the requirement: in packages/core/tests/test_tenant_persistence.py, make line 91 a content-only update, add pytest.raises(TenantImmutableError) for update_memory(record.id, tenant_id="t2"), and keep the assertions that the stored tenant stays t1.
