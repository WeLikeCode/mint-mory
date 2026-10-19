# Tasks — Multi-Tenancy 2/10: write guard, references, transactions

> **Depends on:** `multi-tenancy`. TDD per task; package gate after each
> (`uv run pytest packages/core/tests/`, `uv run mypy packages/core/`,
> `uv run ruff check packages/core/`); full `.l4/config.yaml` gates before the PR.
> No test needs Postgres, Docker or a network service.

- [x] 1. Re-entrant `transaction()` (`storage.py`, `ports.py`)
  - `_tx_lock` (`threading.RLock`) and `_tx_depth` in `__init__`; the outermost
    entry commits or rolls back; nested entries join. Add `transaction()` to the
    Protocol (`AbstractContextManager[object]`) and update the `ports.py`
    docstring. Postgres interim `transaction()` raises
    `TenancyNotSupportedError("transaction")`.
  - Tests: composed writes roll back together (rows, FTS5, trigram); nested
    blocks commit once; a second thread waits; existing `transaction()` users
    (`test_search.py`, `test_dreaming.py`) pass unchanged; the Postgres stub
    raises (`test_pg_transaction_tenancy` in `test_pg_tenancy.py`).
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 2. Write guard (`storage.py`)
  - `_assert_tenant_writable` and its call in every method of the R1.2 table,
    inside the method's transaction, before any SQL write; `_bump_retrieval`
    filtered to active tenants.
  - Tests: missing and inactive tenant per method (nothing written), on a fresh
    database and on one migrated from `pre_tenancy_schema.sql`; reads of an
    inactive tenant still work; `_bump_retrieval` skip.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 3. Same-tenant references (`storage.py`)
  - Checks of R2.1–R2.5 with the exact `CrossTenantLinkError` /
    `TenantImmutableError` arguments.
  - Tests: every example of R2.7; a batch of `record_query_results` with one bad
    row writes nothing; missing endpoints, sessions and memories still raise
    `sqlite3.IntegrityError`; `update_memory` of a missing id raises `KeyError`;
    the check order of R1.7 (an inactive tenant with a cross-tenant link raises
    `CrossTenantLinkError`).
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 4. `tenant_id` on id-only writes (`storage.py`, `ports.py`, `storage_postgres.py`)
  - Signatures and semantics of R3; Protocol updated; Postgres methods gain the
    parameter and call `_require_global_tenant` first.
  - Tests: R3.5 example; `apply_feedback` foreign id → `KeyError`;
    `supersede_memory` with `by_id` outside `T` → `KeyError` naming `by_id`; a
    missing id with `None` keeps today's behaviour; tenant never changes; Postgres
    stubs with `tenant_id="t1"` raise `TenancyNotSupportedError`
    (`test_pg_archive_memory_tenancy`, `test_pg_supersede_memory_tenancy`,
    `test_pg_apply_feedback_tenancy`, `test_pg_update_memory_tenancy` in
    `test_pg_tenancy.py`).
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 5. Full gate
  - Existing suite unchanged on a one-tenant database; `.l4/config.yaml` gates
    exit 0 with coverage ≥ 80%.
  - _Requirements: 5.1, 5.2_
