# Tasks — Multi-Tenancy 5/10: CLI tenant selector and tenant commands

> **Depends on:** `tenant-scoped-core`, `multi-tenancy-reads`, `multi-tenancy`,
> `multi-tenancy-writes`. TDD per task; package gate after each (`uv run pytest
> packages/cli/tests/`, `uv run mypy packages/cli/`, `uv run ruff check
> packages/cli/`); full `.l4/config.yaml` gates before the PR. No test needs
> Postgres, Docker or a network service.

- [x] 1. Root `--tenant` option and refusals (`main.py`)
  - Option and help text, `_TENANT`, `_read_tenant`, `_write_tenant`,
    validation, the `_NO_TENANT_COMMANDS` refusal, `_fail`, `_fail_text`,
    `_tenant_errors`.
  - Tests: R6.5; option after the command → exit 2.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.1, 3.2, 5.1, 6.5_

- [x] 2. Tenant-aware commands (`main.py`)
  - Every row of the R2.1 table, including `dream` through `run_dream`.
  - Tests: R6.3, R6.4, R6.6, R6.7, R6.8, R6.9, R6.10, R6.11, R6.12 (each test
    starts as R6.2 says).
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 5.1, 5.2, 6.2, 6.3, 6.4, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 6.12_

- [x] 3. `tenant create` / `tenant list` (`main.py`)
  - The `tenant` group per R4.
  - Tests: R6.1; a fresh database lists only `global`; `--tenant acme tenant
    list` equals `tenant list`.
  - _Requirements: 3.2, 4.1, 4.2, 6.1_

- [ ] 4. Integration test (`tests/integration/test_tenancy_cli.py`)
  - R6.13 against one SQLite file, at the paths of R6.14.
  - _Requirements: 6.13, 6.14_

- [ ] 5. Full gate
  - `.l4/config.yaml` gates exit 0 with coverage ≥ 80%; existing CLI tests
    unchanged.
  - _Requirements: 7.1_
