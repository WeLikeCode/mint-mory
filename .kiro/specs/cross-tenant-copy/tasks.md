# Tasks — Multi-Tenancy 7/10: cross-tenant copy

> **Depends on:** `multi-tenancy-writes`, `multi-tenancy-reads`,
> `tenant-scoped-mcp`, `multi-tenancy-cli`, `multi-tenancy`. TDD per task; gate
> the touched packages after each; full `.l4/config.yaml` gates before the PR. No
> test needs Postgres, Docker or a network service.

- [x] 1. Report, errors and validation (`transfer.py`)
  - `COPY_MAX`, `CopySelectionError`, `CopyReport`, the validation of R2 in order.
  - Tests: every rejection of R2.1 with type and message (R9.7).
  - _Requirements: 1.1, 2.1, 2.2, 9.7_

- [x] 2. Selection, duplicates and record copy (`transfer.py`)
  - R3 selection and notes expansion; R4 duplicates; R5 record mapping; one
    `store.transaction()` around everything.
  - Tests: R9.2 (records part), R9.4, R9.5 (including the in-selection duplicate
    and the inactive note), R9.6, R9.9; R5 field-by-field mapping; source rows
    unchanged (R7.2).
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 7.1, 7.2, 9.2, 9.4, 9.5, 9.6, 9.9_

- [x] 3. Links and atomicity (`transfer.py`)
  - R6 link copy; rollback on any exception.
  - Tests: R9.2 links, R9.3, R9.8; a link to a skipped duplicate is not created.
  - _Requirements: 6.1, 7.1, 7.3, 7.4, 9.2, 9.3, 9.8_

- [x] 4. MCP `tenant_copy` (`packages/mcp/.../server.py`)
  - Tool per R8.1 (unknown filter keys rejected); `TOOL_TENANT_SCOPE` entry and
    kind `"copy"`; the parameter test and `test_all_tools_registered` of
    `tenant-scoped-mcp` updated in place.
  - Tests: R9.10 (MCP part).
  - _Requirements: 8.1, 9.10_

- [x] 5. CLI `tenant copy` (`packages/cli/.../main.py`)
  - Command per R8.2.
  - Tests: R9.10 (CLI part).
  - _Requirements: 8.2, 9.10_

- [ ] 6. Integration and full gate
  - `tests/integration/test_tenancy_copy.py` (R9.11); `.l4/config.yaml` gates exit
    0 with coverage ≥ 80%.
  - _Requirements: 9.1, 9.11, 10.1_
