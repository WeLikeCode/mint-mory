# Requirements — Multi-Tenancy 9/10: Postgres tenant directory, write guard and transactions

> **Depends on:** `multi-tenancy-postgres` (tenant columns and keys on Postgres,
> `packages/core/tests/pg_fakes.py`), `multi-tenancy-writes` (the SQLite
> behaviour this unit reproduces: guard table, reference rules, id-only writes,
> re-entrant `transaction()`) and `multi-tenancy` (tenant directory semantics,
> error types, `packages/core/tests/test_pg_tenancy.py`). Changes
> `storage_postgres.py` and tests only; no signature changes (the Protocol
> already has them).

## Introduction

Until now the Postgres backend accepts only the `global` tenant and its
`transaction()` raises. This unit gives it the same write behaviour as SQLite:
the tenant directory, the write guard, the same-tenant reference rules, the
`tenant_id` of the writes that act by id, and a re-entrant `transaction()` that
every method — reads included — joins, so the copy can compose reads and writes
atomically. Tenant-confined reads stay for `multi-tenancy-postgres-reads`.

Proof without a database in the L4 job: acceptance tests use the fake pool of
`pg_fakes.py` and assert the executed SQL, parameters, commits and rollbacks.
Backend-agnostic conformance tests (R7) also run on SQLite in the L4 job and on
a real Postgres in the repository's `conformance-pg` CI job (supplementary, not
an L4 gate). No skip, skipif or xfail marker and no `pytest.skip(` call SHALL be
added, and no existing test function SHALL be deleted (an L4 integrity blocker).

## Requirements

### Requirement 1 — Tenant directory

#### Acceptance Criteria
1. `create_tenant(tenant_id, name="")` SHALL call `validate_tenant_id`, run
   `INSERT INTO tenants (id, name, is_active, created_at, updated_at) VALUES (%s,
   %s, TRUE, %s, %s) ON CONFLICT (id) DO NOTHING`, then `SELECT id, name,
   is_active, created_at, updated_at FROM tenants WHERE id = %s` and return it
   (an existing id returns the existing row).
2. `get_tenant(tenant_id)` SHALL `SELECT` the row (`None` when absent);
   `list_tenants()` SHALL return all rows `ORDER BY id`;
   `set_tenant_active(tenant_id, active)` SHALL raise `TenantNotFoundError` for an
   unknown id and `ProtectedTenantError` for `("global", False)`, return `global`
   unchanged for `("global", True)`, and otherwise `UPDATE tenants SET is_active =
   %s, updated_at = %s WHERE id = %s` and return the row.
3. The synthetic `global` of the interim and the `TenancyNotSupportedError` of
   `create_tenant` / `set_tenant_active` SHALL be removed.

### Requirement 2 — Write guard

#### Acceptance Criteria
1. `_assert_tenant_writable(conn, tenant_id)` SHALL run `SELECT is_active FROM
   tenants WHERE id = %s` (through `_execute_dict`, row `{"is_active": bool}`) on
   the write's connection and raise `TenantNotFoundError` / `TenantInactiveError`
   as on SQLite.
2. It SHALL guard exactly the writes of the `multi-tenancy-writes` R1.2 table
   (`add_memory`, `update_memory`, `archive_memory`, `supersede_memory`,
   `apply_feedback`, `add_link`, `create_session`, `record_query_results`,
   `update_session_feedback`, `mark_session_concluded`, `upsert_summary`,
   `manifest_upsert`, `manifest_delete`) on the same tenant, in the check order
   of `multi-tenancy-writes` R1.7, writing nothing when it raises.
   `_bump_retrieval` SHALL add `AND tenant_id IN (SELECT id FROM tenants WHERE
   is_active)`.
3. `_require_global_tenant` SHALL be removed from every write path and keyed
   write. A write never calls a method that still carries it: lookups a write
   needs (the existing summary id for `upsert_summary`, the stored tenant of a
   memory or session) use private helpers on the write's connection —
   `_stored_tenant(conn, memory_id)` (`SELECT tenant_id FROM memories WHERE id =
   %s`), `_session_tenant(conn, session_id)` (`SELECT tenant_id FROM
   query_sessions WHERE id = %s`), `_summary_id(conn, tenant_id, concept)`
   (`SELECT id FROM memory_summaries WHERE tenant_id = %s AND concept = %s`),
   each returning the value of its single-column dict row or `None`.
4. Like SQLite across processes, a tenant deactivated between the guard and the
   write lets that one write through (no row lock; accepted).

### Requirement 3 — Same-tenant references and id-only writes

#### Acceptance Criteria
1. `add_link`, `record_query_results`, `supersede_memory`, `superseded_by` on
   `add_memory` / `update_memory`, and `tenant_id` in `update_memory` fields SHALL
   raise the same errors with the same arguments, and keep the same missing-row
   outcomes, as `multi-tenancy-writes` R2.1–R2.5 (`CrossTenantLinkError(first_id,
   first_tenant, second_id, second_tenant)`, `TenantImmutableError(memory_id,
   stored, requested)`; a missing endpoint, session or memory leaves the database
   error to Postgres, a `ForeignKeyViolation`); a `global` session MAY reference
   any tenant's memories.
2. `archive_memory(memory_id, tenant_id=None)`, `supersede_memory(memory_id,
   by_id, tenant_id=None)`, `apply_feedback(memory_id, useful, stale,
   tenant_id=None)` SHALL behave as `multi-tenancy-writes` R3: `None` acts by id;
   a concrete tenant that does not own the row raises `KeyError(f"memory
   {memory_id!r} not found")`.

### Requirement 4 — Re-entrant `transaction()` and one connection helper

#### Acceptance Criteria
1. `PostgresBackend` SHALL hold `self._tx_conn: ContextVar[Any | None]` (one per
   instance, default `None`) and implement `transaction()` as a context manager:
   when a connection is already bound in the current context it yields it and
   neither commits nor rolls back; otherwise it takes a pool connection, binds
   it, yields it, commits on success, and unbinds it in `finally`; on an exception
   it re-raises and leaves the rollback to the pool's connection context (no
   explicit `rollback()` call, so it happens once).
2. A private `_conn()` context manager SHALL yield the bound connection when one
   exists (no commit) and otherwise a pool connection that it commits on
   success. EVERY method of the backend that today opens
   `self._pool.connection()` — reads and writes, including `get_memory`,
   `get_tenant`, `get_links`, `get_session`, `search` and its phases — SHALL use
   `with self._conn() as conn:` instead and drop its own `commit()`; only
   `initialise()`, `_ensure_extensions()`, `_probe_capabilities()`, `ping()`,
   `close()` and `_truncate_all()` keep their own pool handling. So inside a
   `transaction()` every call sees the rows written earlier in it.
3. On Postgres a failed statement aborts the whole transaction: a caller that
   catches an exception inside a `transaction()` block cannot continue, and the
   final commit fails. This differs from SQLite and is accepted (no savepoints);
   the only composer, `cross-tenant-copy`, never catches inside its block.
4. A `ContextVar` is per thread and per asyncio task, so another request has its
   own connection. A task or thread started inside a `transaction()` block
   inherits the binding (context copy); callers SHALL NOT use the store from such
   children while the block is open (the copy does not). The per-instance
   variable lives as long as the backend, which is a long-lived singleton.
5. Tests (fake pool): with `FakePool(conn)`, two `add_memory` calls inside `with
   backend.transaction():` add no commit and leaving the block adds exactly one;
   an exception inside adds no commit and at least one rollback; a nested
   `transaction()` adds no commit of its own; a `get_memory` inside the block runs
   on `conn` (it appears in `conn.executed` after the inserts and `checkouts`
   stays 1). With `FakePool(FakeConnection)` (a factory), an `add_memory` from a
   second thread while the block is open runs on a second connection
   (`pool.connections[1]`), which commits once by itself.

### Requirement 5 — Tests of R1–R3 (fake pool)

#### Acceptance Criteria
1. For each guarded write, a missing and an inactive tenant (the responder
   returns `[]` / `[{"is_active": False}]` for the guard SELECT) raise the right
   error and no INSERT, UPDATE or DELETE follows the guard in `executed`.
2. Each reference rule raises with the stated arguments when the responder
   returns `[{"tenant_id": "t1"}]` and `[{"tenant_id": "global"}]` for the two
   `_stored_tenant` lookups; `archive_memory("a1", tenant_id="global")` with a
   stored `t1` row raises `KeyError`.
3. `_bump_retrieval(["a1"], now)` executes an UPDATE containing `tenant_id IN
   (SELECT id FROM tenants WHERE is_active)`.
4. The directory methods execute the SQL of R1 and map the returned dict rows.
5. The `test_pg_<method>_tenancy` functions of `packages/core/tests/test_pg_tenancy.py`
   for the methods of R1–R4 (`create_tenant`, `set_tenant_active`, `get_tenant`,
   `list_tenants`, `transaction`, the guarded writes) SHALL be rewritten in place —
   same names, fake pool — to assert the new behaviour; the read ones stay as
   they are until `multi-tenancy-postgres-reads`.

### Requirement 6 — Gates

#### Acceptance Criteria
1. The `.l4/config.yaml` gates SHALL pass with coverage ≥ 80%. No test needs
   Postgres, Docker or a network service.

### Requirement 7 — Conformance tests (supplementary)

#### Acceptance Criteria
1. `packages/core/tests/conformance/test_tenancy_writes.py` SHALL use the
   existing `backend` fixture and only Protocol methods to check: a write to a
   missing and to an inactive tenant raises and writes nothing; a cross-tenant
   `add_link` raises `CrossTenantLinkError`; `archive_memory(id,
   tenant_id=<other tenant>)` raises `KeyError`; two `add_memory` calls inside a
   `transaction()` that then raises leave no row. Its SQLite leg runs in the L4
   job; its Postgres leg runs in the `conformance-pg` CI job.
