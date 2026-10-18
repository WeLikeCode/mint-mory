# Tasks — Multi-Tenancy 2/10: write guard, references, transactions

> **Depends on:** `multi-tenancy`. TDD per task; package gate after each
> (`uv run pytest packages/core/tests/`, `uv run mypy packages/core/`,
> `uv run ruff check packages/core/`); full `.l4/config.yaml` gates before the PR.
> No test needs Postgres, Docker or a network service.

- [ ] 1. Re-entrant `transaction()` (`storage.py`, `ports.py`)
  - `_tx_lock` (`threading.RLock`) and `_tx_depth` in `__init__`; the outermost
    entry commits or rolls back; nested entries join. Add `transaction()` to the
    Protocol (`AbstractContextManager[object]`) and update the `ports.py`
    docstring. Postgres interim `transaction()` raises
    `TenancyNotSupportedError("transaction")`.
  - Tests: composed writes roll back together (rows, FTS5, trigram); nested
    blocks commit once; a second thread waits; existing `transaction()` users
    (cochange, `history scrub` tests) pass unchanged; the Postgres stub raises.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 2. Write guard (`storage.py`)
  - `_assert_tenant_writable` and its call in every method of the R1.2 table,
    inside the method's transaction, before any SQL write; `_bump_retrieval`
    filtered to active tenants.
  - Tests: missing and inactive tenant per method (nothing written), on a fresh
    database and on one migrated from `pre_tenancy_schema.sql`; reads of an
    inactive tenant still work; `_bump_retrieval` skip.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [ ] 3. Same-tenant references (`storage.py`)
  - Checks of R2.1–R2.5 with the exact `CrossTenantLinkError` /
    `TenantImmutableError` arguments.
  - Tests: every example of R2.7; a batch of `record_query_results` with one bad
    row writes nothing; missing endpoints still raise `sqlite3.IntegrityError`.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [ ] 4. `tenant_id` on id-only writes (`storage.py`, `ports.py`, `storage_postgres.py`)
  - Signatures and semantics of R3; Protocol updated; Postgres methods gain the
    parameter and call `_require_global_tenant` first.
  - Tests: R3.5 example; `apply_feedback` foreign id → `KeyError`;
    `supersede_memory` with `by_id` outside `T` → `KeyError` naming `by_id`; a
    missing id with `None` keeps today's behaviour; tenant never changes; Postgres
    stub with `tenant_id="t1"` raises `TenancyNotSupportedError`.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 5. Full gate
  - Existing suite unchanged on a one-tenant database; `.l4/config.yaml` gates
    exit 0 with coverage ≥ 80%.
  - _Requirements: 5.1, 5.2_
