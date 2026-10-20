# Tasks — Multi-Tenancy 4/10: tenant-scoped dreaming and core functions

> **Depends on:** `multi-tenancy`, `multi-tenancy-writes`, `multi-tenancy-reads`.
> TDD per task; gate the touched packages after each (`uv run pytest
> packages/<pkg>/tests/`, `uv run mypy packages/<pkg>/`, `uv run ruff check
> packages/<pkg>/`); full `.l4/config.yaml` gates before the PR. No test needs
> Postgres, Docker or a network service.

- [x] 1. Engine scope (`dreaming.py`, `llm.py`)
  - `tenant_id` keyword on `DreamingEngine`, every step read and write confined
    per R1.2–R1.4; `build_dreaming_engine(…, tenant_id=None)` and
    `build_conflict_resolver(settings, adapter, *, tenant_id=None)`.
  - Tests: Scenario A (R1.7) and Scenario B (R1.8); the legacy engine's existing
    tests pass unchanged.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

- [x] 2. Per-tenant entry points (`dreaming.py`)
  - `EngineFactory`, `DreamAllReport` (+ `total()`), `DreamFailedError`,
    `dream_all_tenants`, `run_dream` per R2.1–R2.5.
  - Tests: R2.6 parity on two files; R2.7 cases; `total()` sums and anomaly
    order; `run_dream` with an unknown / inactive tenant raises before running.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 3. Transports dream per tenant; summary paths on `global`
  - MCP `memory_dream`, CLI `dream`, HTTP `POST /dream` → `run_dream(…,
    tenant_id=None, …)`; MCP/CLI/API summary jobs and put → engine with
    `tenant_id=TENANT_GLOBAL`. Output shapes unchanged.
  - Tests: two tenants → no cross-tenant link after each transport's dream and
    the returned JSON/table is a `DreamReport`; `summary_jobs` lists only
    `global` concepts; `DreamingEngine.run_light` monkeypatched to raise →
    `ToolError` / exit 1 / HTTP 500 (R3.3).
  - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2_

- [ ] 4. Core functions (`notes.py`, `vision.py`, `session.py`, `cochange.py`)
  - Signatures and behaviour of R5.1–R5.6.
  - Tests: the R5.1 anchoring example; `notes_list(tenant_id="t1")`;
    `image_jobs` / `image_caption_put` confined (foreign file-record →
    `KeyError`); `apply_feedback` with a foreign session or memory id raises
    `ValueError`, with an inactive tenant's id raises `TenantInactiveError`, and
    in both cases changes no score; `changed_with` / `documents_timeline` with
    `tenant_id="t1"` return only `t1` documents.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

- [ ] 5. HTTP API error mapping (`api/app.py`)
  - The `TenantError` handler with the R6.2 codes; `DreamFailedError` → 500.
  - Tests: the R6.3 examples; unscoped search over two tenants (R6.1).
  - _Requirements: 6.1, 6.2, 6.3_

- [ ] 6. Full gate
  - Existing suite unchanged on a one-tenant database; `.l4/config.yaml` gates
    exit 0 with coverage ≥ 80%.
  - _Requirements: 7.1_
