# Tasks — Multi-Tenancy 9/10: Postgres tenant directory, write guard and transactions

> **Depends on:** `multi-tenancy-postgres`, `multi-tenancy-writes`,
> `multi-tenancy`. TDD per task; package gate after each (`uv run pytest
> packages/core/tests/`, `uv run mypy packages/core/`, `uv run ruff check
> packages/core/`); full `.l4/config.yaml` gates before the PR. No test needs
> Postgres, Docker or a network service; add no skip, skipif or xfail marker and
> no `pytest.skip(` call.

- [ ] 1. Connection binding and `transaction()` (`storage_postgres.py`)
  - `_tx_conn`, `_conn()`, `transaction()`; every method moved to `_conn()`.
  - Tests: R4.4; the no-stray-`commit()` test of the design.
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 2. Tenant directory (`storage_postgres.py`)
  - R1.1–R1.3.
  - Tests: R5.3.
  - _Requirements: 1.1, 1.2, 1.3, 5.3_

- [ ] 3. Write guard (`storage_postgres.py`)
  - R2.1–R2.3.
  - Tests: R5.1.
  - _Requirements: 2.1, 2.2, 2.3, 5.1_

- [ ] 4. References and id-only writes (`storage_postgres.py`)
  - R3.1–R3.2.
  - Tests: R5.2.
  - _Requirements: 3.1, 3.2, 5.2_

- [ ] 5. Conformance tests (`packages/core/tests/conformance/test_tenancy_writes.py`)
  - R7.1 through the existing `backend` fixture.
  - _Requirements: 7.1_

- [ ] 6. Full gate
  - `.l4/config.yaml` gates exit 0 with coverage ≥ 80%.
  - _Requirements: 6.1_
