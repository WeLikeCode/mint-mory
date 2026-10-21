# Questions — multi-tenancy-postgres-writes

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
| Q-001 | accepted | 1 | technical | packages/core/tests/test_pg_tenancy.py:299 — test_pg_transaction_tenancy still asserts the removed interim stub |
| Q-002 | accepted | 1 | technical | packages/core/tests/test_transfer_links.py:359 — test_postgres_copy_fails_closed_before_any_write expects the removed transaction stub |
| Q-003 | open | 2 | technical | packages/core/tests/test_pg_tenancy.py:255-292 - directory tests still assert the interim stub |
<!-- l4:index:end -->

---

## Q-001: packages/core/tests/test_pg_tenancy.py:299 — test_pg_transaction_tenancy still asserts the removed interim stub

- **Status:** accepted
- **Blocking tasks:** 1
- **Kind:** technical
- **Asked:** 2026-10-21T18:29Z by deepseek, run r-20261021T1803Z-808e, task 1

### Context
The pre-existing test creates a PostgresBackend with `_pool = None` and asserts `transaction()` raises TenancyNotSupportedError('transaction'). R4.1/C-f97c4a2c replaces the stub with a re-entrant transaction and R5.5/C-1b7a83e9 requires this exact function rewritten in place; after the implementation it fails with AssertionError because there is no pool. The red ledger note already left this in-place rewrite for green after an unfreeze, and the pre-existing-test guard rejects changing the file without an allowance.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_pg_tenancy.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy-postgres-writes`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_pg_tenancy.py`: add `from packages.core.tests.pg_fakes import FakeConnection, FakePool` to the imports and replace lines 298-307 (the `@pytest.mark.l4("C-74b68113")` decorator plus `test_pg_transaction_tenancy`) with: ```python @pytest.mark.l4("C-1b7a83e9") def test_pg_transaction_tenancy() -> None: conn = FakeConnection() backend = PostgresBackend("postgresql://unused") backend._pool = FakePool(conn) with backend.transaction() as yielded: assert yielded is conn assert conn.commits == 1 ```
2. Edit `packages/core/tests/test_pg_tenancy.py`: remove the `@pytest.mark.l4("C-74b68113")` decorator and `test_pg_transaction_tenancy` entirely; the new tests in test_pg_tenancy_writes.py already trace C-1b7a83e9.

### Clarifier suggestion
Edit `packages/core/tests/test_pg_tenancy.py`: add `from packages.core.tests.pg_fakes import FakeConnection, FakePool` to the imports and replace lines 298-307 (the `@pytest.mark.l4("C-74b68113")` decorator plus `test_pg_transaction_tenancy`) with:

\```python
@pytest.mark.l4("C-1b7a83e9")
def test_pg_transaction_tenancy() -> None:
    conn = FakeConnection()
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)

    with backend.transaction() as yielded:
        assert yielded is conn

    assert conn.commits == 1
\```

### Answer
<!-- write below this line -->
---

## Q-002: packages/core/tests/test_transfer_links.py:359 — test_postgres_copy_fails_closed_before_any_write expects the removed transaction stub

- **Status:** accepted
- **Blocking tasks:** 1
- **Kind:** technical
- **Asked:** 2026-10-21T18:29Z by deepseek, run r-20261021T1803Z-808e, task 1

### Context
This pre-existing test builds a PostgresBackend with `_pool = None` and expects `copy_between_tenants` to fail with TenancyNotSupportedError('transaction'). After R4.1 entering transaction() no longer raises; on a pool-less backend it now asserts, so the test fails with AssertionError. cross-tenant-copy R7.4 only promises this fail-closed stub 'until multi-tenancy-postgres-writes ... land', so the test premise is obsolete now, but the pre-existing-test guard rejects changing it without an allowance.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_transfer_links.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy-postgres-writes`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_transfer_links.py`: add `TenantNotFoundError` to the `mintmory.core.types` import and add `from packages.core.tests.pg_fakes import FakeConnection, FakePool`, then replace lines 359-377 (`test_postgres_copy_fails_closed_before_any_write`) with: ```python @pytest.mark.l4("C-ae539615") def test_postgres_copy_fails_closed_before_any_write() -> None: conn = FakeConnection() backend = PostgresBackend("postgresql://unused") backend._pool = FakePool(conn) with pytest.raises(TenantNotFoundError): transfer.copy_between_tenants( backend, source_tenant="acme", dest_tenant="beta", all_active=True ) assert not [ sql for sql, _params in conn.executed if sql.lstrip().startswith("INSERT INTO memories") ] assert conn.commits == 0 assert conn.rollbacks == 1 ```
2. Edit `packages/core/src/mintmory/core/storage_postgres.py`: keep the old test unchanged by making `transaction()` raise `TenancyNotSupportedError("transaction")` when `self._pool is None` (fail closed on an uninitialised backend) before the pool assert.

### Clarifier suggestion
Edit `packages/core/tests/test_transfer_links.py`: add `TenantNotFoundError` to the `mintmory.core.types` import and add `from packages.core.tests.pg_fakes import FakeConnection, FakePool`, then replace lines 359-377 (`test_postgres_copy_fails_closed_before_any_write`) with:

\```python
@pytest.mark.l4("C-ae539615")
def test_postgres_copy_fails_closed_before_any_write() -> None:
    conn = FakeConnection()
    backend = PostgresBackend("postgresql://unused")
    backend._pool = FakePool(conn)

    with pytest.raises(TenantNotFoundError):
        transfer.copy_between_tenants(
            backend, source_tenant="acme", dest_tenant="beta", all_active=True
        )

    assert not [
        sql for sql, _params in conn.executed if sql.lstrip().startswith("INSERT INTO memories")
    ]
    assert conn.commits == 0
    assert conn.rollbacks == 1
\```

### Answer
<!-- write below this line -->

---

## Q-003: packages/core/tests/test_pg_tenancy.py:255-292 - directory tests still assert the interim stub

- **Status:** open
- **Blocking tasks:** 2
- **Kind:** technical
- **Asked:** 2026-10-21T19:08Z by deepseek, run r-20261021T1832Z-8b02, task 2

### Context
R5.5 requires test_pg_get_tenant_tenancy, test_pg_list_tenants_tenancy, test_pg_create_tenant_tenancy and test_pg_set_tenant_active_tenancy to be rewritten in place with the fake pool, but the red step left them unchanged. They call _backend() with _pool=None and assert a synthetic 'global' Tenant from get_tenant/list_tenants and TenancyNotSupportedError from create_tenant/set_tenant_active, while R1.1-R1.3/C-edb554ee require the synthetic global and those TenancyNotSupportedError raises to be removed. Implementing R1 makes all four fail (assert self._pool is not None at storage_postgres.py:383), and green may not edit frozen tests.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_pg_tenancy.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy-postgres-writes`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_pg_tenancy.py`: replace test_pg_get_tenant_tenancy, test_pg_list_tenants_tenancy, test_pg_create_tenant_tenancy and test_pg_set_tenant_active_tenancy (lines 254-292) with FakePool-backed versions that assert the new directory behaviour: get_tenant maps a returned row and returns None when absent, list_tenants returns rows ordered by id, create_tenant inserts then selects and returns the row, set_tenant_active raises ProtectedTenantError for ('global', False) without an UPDATE, and no test asserts a synthetic 'global' or TenancyNotSupportedError.

### Clarifier suggestion
Edit `packages/core/tests/test_pg_tenancy.py`: replace test_pg_get_tenant_tenancy, test_pg_list_tenants_tenancy, test_pg_create_tenant_tenancy and test_pg_set_tenant_active_tenancy (lines 254-292) with FakePool-backed versions that assert the new directory behaviour: get_tenant maps a returned row and returns None when absent, list_tenants returns rows ordered by id, create_tenant inserts then selects and returns the row, set_tenant_active raises ProtectedTenantError for ('global', False) without an UPDATE, and no test asserts a synthetic 'global' or TenancyNotSupportedError.

### Answer
<!-- write below this line -->
