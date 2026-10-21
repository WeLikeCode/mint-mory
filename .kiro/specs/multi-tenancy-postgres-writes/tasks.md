# Tasks — Multi-Tenancy 9/10: Postgres tenant directory, write guard and transactions

> **Depends on:** `multi-tenancy-postgres`, `multi-tenancy-writes`,
> `multi-tenancy`. TDD per task; package gate after each (`uv run pytest
> packages/core/tests/`, `uv run mypy packages/core/`, `uv run ruff check
> packages/core/`); full `.l4/config.yaml` gates before the PR. No test needs
> Postgres, Docker or a network service; add no skip, skipif or xfail marker and
> no `pytest.skip(` call.

- [x] 1. Connection binding and `transaction()` (`storage_postgres.py`)
  - `_tx_conn`, `_conn()`, `transaction()`; every method of R4.2 (reads and
    writes) moved to `_conn()`.
  - Tests: R4.5; `test_pg_transaction_tenancy` rewritten in place (R5.5).
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.5_

- [x] 2. Tenant directory (`storage_postgres.py`)
  - R1.1–R1.3.
  - Tests: R5.4, R5.7 (directory errors); the directory `test_pg_<method>_tenancy`
    functions rewritten in place (R5.5).
  - _Requirements: 1.1, 1.2, 1.3, 5.4, 5.5, 5.7_

- [x] 3. Write guard (`storage_postgres.py`)
  - R2.1–R2.4 with the private lookup helpers.
  - Tests: R5.1, R5.3, R5.6; the write `test_pg_<method>_tenancy` functions
    rewritten in place (R5.5).
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 5.1, 5.3, 5.5, 5.6_

- [x] 4. References and id-only writes (`storage_postgres.py`)
  - R3.1–R3.2.
  - Tests: R5.2, R5.7 (reference errors).
  - _Requirements: 3.1, 3.2, 5.2, 5.7_

- [ ] 5. Conformance tests (`packages/core/tests/conformance/test_conformance_tenancy_writes.py`)
  - R7.1 through the existing `backend` fixture.
  - _Requirements: 7.1_

- [ ] 6. Full gate
  - `.l4/config.yaml` gates exit 0 with coverage ≥ 80%.
  - _Requirements: 6.1_
