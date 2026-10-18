# Tasks — Multi-Tenancy 5/10: CLI tenant selector and tenant commands

> **Depends on:** `tenant-scoped-core`, `multi-tenancy-reads`, `multi-tenancy`,
> `multi-tenancy-writes`. TDD per task; package gate after each (`uv run pytest
> packages/cli/tests/`, `uv run mypy packages/cli/`, `uv run ruff check
> packages/cli/`); full `.l4/config.yaml` gates before the PR. No test needs
> Postgres, Docker or a network service.

- [ ] 1. Root `--tenant` option and refusals (`main.py`)
  - Option, `_TENANT`, `_read_tenant`, `_write_tenant`, validation, the
    `_NO_TENANT_COMMANDS` refusal, `_fail`, `_tenant_errors`.
  - Tests: R6.4; `--tenant global stats` equals `stats`; option after the
    command → exit 2.
  - _Requirements: 1.1, 1.2, 1.3, 3.1, 3.2, 5.1_

- [ ] 2. Tenant-aware commands (`main.py`)
  - Every row of the R2.1 table, including `dream` through `run_dream`.
  - Tests: R6.2, R6.3, R6.5, R6.6; one assertion per table row (stored or
    returned tenant); `ingest` dedups within the write tenant only.
  - _Requirements: 2.1, 2.2, 2.3, 5.1, 5.2_

- [ ] 3. `tenant create` / `tenant list` (`main.py`)
  - The `tenant` group per R4.
  - Tests: R6.1; a fresh database lists only `global`; `--tenant acme tenant
    list` equals `tenant list`.
  - _Requirements: 3.2, 4.1, 4.2_

- [ ] 4. Integration test (`tests/integration/test_tenancy_cli.py`)
  - R6.7 against one SQLite file.
  - _Requirements: 6.7_

- [ ] 5. Full gate
  - `.l4/config.yaml` gates exit 0 with coverage ≥ 80%; existing CLI tests
    unchanged.
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1_
