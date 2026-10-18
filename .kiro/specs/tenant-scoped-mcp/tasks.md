# Tasks — Multi-Tenancy 6/10: tenant-scoped MCP server

> **Depends on:** `tenant-scoped-core`, `multi-tenancy-reads`, `multi-tenancy`,
> `multi-tenancy-writes`. TDD per task; package gate after each (`uv run pytest
> packages/mcp/tests/`, `uv run mypy packages/mcp/`, `uv run ruff check
> packages/mcp/`); full `.l4/config.yaml` gates before the PR. No test needs
> Postgres, Docker or a network service.

- [ ] 1. Scope settings and startup (`config.py`, `server.py`)
  - `McpSettings`; `--tenant`; resolution of R1.2; `_scope_tenant`,
    `_effective_tenant`, `_bootstrap_scope`; `main()` order and exit 1.
  - Tests: every case of R1.6.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [ ] 2. Read tools (`server.py`)
  - `memory_get`, `memory_search`, `memory_stats`, `summary_list`,
    `summary_get`, `notes_list`, `docs_changed_with`, `docs_timeline` per the R2.1
    table.
  - Tests: the read parts of R3.2 and R4.2.
  - _Requirements: 2.1, 3.1, 4.1_

- [ ] 3. Create, modify and dream tools (`server.py`)
  - `memory_add`, `memory_archive`, `session_feedback`, `summary_jobs`,
    `summary_put`, `memory_note`, `image_jobs`, `image_caption_put`,
    `vision_run`, `memory_dream` per the R2.1 table; `TenantError` → tool error.
  - Tests: the write parts of R3.2 and R4.2; R2.3; R8.1; R8.2.
  - _Requirements: 2.1, 2.3, 3.1, 3.2, 4.1, 4.2, 8.1, 8.2_

- [ ] 4. `tenant_create` / `tenant_list` and the inventory (`server.py`)
  - The two tools per R5; `TOOL_TENANT_SCOPE`; update
    `test_all_tools_registered`.
  - Tests: R5.3; R2.2 inventory; R6.1 schema scan; R8.3.
  - _Requirements: 2.2, 5.1, 5.2, 5.3, 6.1, 8.3_

- [ ] 5. Capabilities and instructions (`server.py`)
  - The two capability keys (normal and fallback) and the `TENANCY:` sentence.
  - Tests: R7.1 for both scopes and for the fallback (monkeypatch
    `load_settings` to raise); the instruction text ends with the R7.2 sentence.
  - _Requirements: 7.1, 7.2_

- [ ] 6. Integration and full gate
  - `tests/integration/test_tenancy_mcp.py` (R9.2); `.l4/config.yaml` gates exit
    0 with coverage ≥ 80%; existing MCP tests unchanged except the inventory set.
  - _Requirements: 9.1, 9.2, 9.3_
