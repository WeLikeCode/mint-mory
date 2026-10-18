# Tasks — Multi-Tenancy 8/10: Postgres schema, migrations and column parity

> **Depends on:** `multi-tenancy`. TDD per task; package gate after each
> (`uv run pytest packages/core/tests/`, `uv run mypy packages/core/`,
> `uv run ruff check packages/core/`); full `.l4/config.yaml` gates before the PR.
> No test needs Postgres, Docker or a network service; add no skip, skipif or
> xfail marker and no `pytest.skip(` call.

- [ ] 1. Test seam (`packages/core/tests/pg_fakes.py`)
  - `FakePool`, `FakeConnection`, `FakeCursor` per R5.1, with a self-test.
  - _Requirements: 5.1_

- [ ] 2. Fresh DDL (`schema_postgres.sql`)
  - R1.1–R1.4.
  - Tests: the text checks of R1.5.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ] 3. In-place migration (`storage_postgres.py`)
  - `plan_pg_tenant_migration`, `_ensure_tenant_columns` with the catalog reads,
    the call in `initialise()`, `TenantMigrationError` on failure.
  - Tests: every case of R2.4.
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [ ] 4. Column parity and per-tenant keys (`storage_postgres.py`)
  - R3.1–R3.4.
  - Tests (new file `packages/core/tests/test_pg_tenancy_columns.py`): R3.5 for
    each listed statement; the existing `test_pg_<method>_tenancy` functions
    pass unchanged.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 5. `migrate.py`
  - R4.1–R4.5.
  - Tests: R4.6; the existing pure-logic tests of `test_migrate.py` pass
    (updated in place where they build rows by hand; no test function deleted).
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [ ] 6. Full gate
  - `.l4/config.yaml` gates exit 0 with coverage ≥ 80%.
  - _Requirements: 6.1, 6.2_
