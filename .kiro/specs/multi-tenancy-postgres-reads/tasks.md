# Tasks — Multi-Tenancy 10/10: Postgres tenant-scoped reads and search

> **Depends on:** `multi-tenancy-postgres-writes`, `multi-tenancy-reads`,
> `multi-tenancy-postgres`. TDD per task; package gate after each (`uv run pytest
> packages/core/tests/`, `uv run mypy packages/core/`, `uv run ruff check
> packages/core/`); full `.l4/config.yaml` gates before the PR. No test needs
> Postgres, Docker or a network service; add no skip, skipif or xfail marker and
> no `pytest.skip(` call.

- [x] 1. Tenant predicate on every read (`storage_postgres.py`)
  - R1.1; remove `_require_global_tenant` from reads and delete it (R1.2).
  - Tests: R1.3 for every method; the read `test_pg_<method>_tenancy` functions
    rewritten in place (R1.2).
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Search (`storage_postgres.py`)
  - R2.1.
  - Tests: R2.2.
  - _Requirements: 2.1, 2.2_

- [ ] 3. `list_memories` (`storage_postgres.py`)
  - R3.1.
  - Tests: R3.2.
  - _Requirements: 3.1, 3.2_

- [ ] 4. Conformance tests (`packages/core/tests/conformance/test_conformance_tenancy_reads.py`)
  - R4.1 through the existing `backend` fixture.
  - _Requirements: 4.1_

- [ ] 5. Full gate
  - `.l4/config.yaml` gates exit 0 with coverage ≥ 80%.
  - _Requirements: 5.1_
