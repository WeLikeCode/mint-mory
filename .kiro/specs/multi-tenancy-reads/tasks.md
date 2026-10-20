# Tasks — Multi-Tenancy 3/10: tenant-scoped reads and search

> **Depends on:** `multi-tenancy`, `multi-tenancy-writes`. TDD per task; package
> gate after each (`uv run pytest packages/core/tests/`, `uv run mypy
> packages/core/`, `uv run ruff check packages/core/`); full `.l4/config.yaml`
> gates before the PR. No test needs Postgres, Docker or a network service.

- [x] 1. Record and entity reads (`storage.py`, `ports.py`)
  - `tenant_id` on `get_memory`, `get_links`, `get_annotating_notes`,
    `get_annotating_descriptions`, `find_image_file_record`,
    `list_image_file_records`, `list_notes`, `list_summaries`, `get_session`,
    `get_stats`, `memory_exists_with_content`; Protocol updated.
  - Tests: three-way (`t1` / `None` / `nope`) per method; R1.2–R1.4.
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Dreaming helper reads (`storage.py`, `ports.py`)
  - `tenant_id` on the ten dreaming helpers of R1.1; Protocol updated.
  - Tests: three-way per helper with the seed of the design.
  - _Requirements: 1.1_

- [x] 3. Search, traversal and anchoring (`storage.py`, `hybrid_search.py`)
  - Tenant on `_fts_scores`, `_trigram_scores`, `_vector_scores`,
    `_load_memories`, `search_around`, `anchor_candidates`, `search`;
    `fuse_and_search(…, tenant_id=None, record_session=True)` with the session
    stamping, the defense-in-depth drop and `session_id = ""`.
  - Tests: the R3.6 examples; R3.7; an unscoped search records a `global`
    session over both tenants; `anchor_candidates("Alice", tenant_id="t1")`
    returns only `t1` rows and writes nothing.
  - _Requirements: 2.1, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [x] 4. `list_memories` (`storage.py`, `ports.py`)
  - Per R4.1; Protocol entry.
  - Tests: the R4.2 examples; negative limit → `ValueError`; R4.3.
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 5. SQL parity trace test
  - The R2.2 test over every read of R1.1 except `search`.
  - _Requirements: 2.1, 2.2_

- [x] 6. Postgres interim (`storage_postgres.py`)
  - Same parameters on every Postgres read, `_require_global_tenant` first;
    `list_memories` stub.
  - Tests: R5.3; `uv run mypy packages` passes.
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 7. Full gate
  - Existing suite unchanged; `.l4/config.yaml` gates exit 0 with coverage ≥ 80%.
  - _Requirements: 6.1, 6.2_
