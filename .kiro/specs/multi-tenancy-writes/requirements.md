# Requirements — Multi-Tenancy 2/10: write guard, same-tenant references, composable transactions (SQLite)

> **Depends on:** `multi-tenancy` (types, errors, `tenant_id` columns, tenant
> directory, `_require_global_tenant` on Postgres). Changes `storage.py`,
> `ports.py` and the Postgres interim stubs only; no transport changes.

## Introduction

After `multi-tenancy`, records carry a tenant but nothing stops a write into a
missing or inactive tenant, or a reference across tenants. This unit adds the
enforcement on the SQLite backend: a write guard on every write path, the
same-tenant reference rules, an optional `tenant_id` on the writes that act on
an existing row by id, and a re-entrant `transaction()` on the Protocol so a
caller (the copy in `cross-tenant-copy`) can compose many public writes into one
atomic unit. Reads are unchanged here (`multi-tenancy-reads`).

Interfaces used from `multi-tenancy`: `TENANT_GLOBAL`, `TenantNotFoundError(tenant_id)`,
`TenantInactiveError(tenant_id)`, `CrossTenantLinkError(first_id, first_tenant,
second_id, second_tenant)`, `TenantImmutableError(memory_id, stored_tenant,
requested_tenant)`, `TenancyNotSupportedError(operation)`, `create_tenant`,
`set_tenant_active`, the `tenant_id` field on the five models, and
`PostgresBackend._require_global_tenant(tenant_id, operation)`.

## Requirements

### Requirement 1 — Write guard

#### Acceptance Criteria

1. `SqliteBackend._assert_tenant_writable(conn: sqlite3.Connection, tenant_id:
   str) -> None` SHALL run `SELECT is_active FROM tenants WHERE id = ?` and raise
   `TenantNotFoundError(tenant_id)` when there is no row and
   `TenantInactiveError(tenant_id)` when `is_active = 0`.
2. Each write SHALL call it inside its `transaction()`, before any INSERT, UPDATE
   or DELETE, on this tenant, and write nothing when it raises:

   | Method | Guarded tenant |
   |---|---|
   | `add_memory(record=None, **fields)` | `record.tenant_id` |
   | `update_memory(memory_id, **fields)` | the stored row's tenant |
   | `archive_memory`, `supersede_memory`, `apply_feedback` | the stored row's tenant |
   | `add_link(link)` | `link.tenant_id` |
   | `create_session(session)` | `session.tenant_id` |
   | `record_query_results(results)` | each result's `tenant_id` |
   | `update_session_feedback(session_id, …)`, `mark_session_concluded(session_id)` | the stored session's tenant (a missing session keeps today's no-op) |
   | `upsert_summary(summary)` | `summary.tenant_id` |
   | `manifest_upsert(…, tenant_id)`, `manifest_delete(…, tenant_id)` | the `tenant_id` argument |

3. Example: `create_tenant("t1")`, `set_tenant_active("t1", False)`, then
   `add_memory(record=MemoryRecord(content="x", category="fact",
   tenant_id="t1"))` raises `TenantInactiveError` and the memory count is
   unchanged; `tenant_id="nope"` raises `TenantNotFoundError`. Both SHALL also
   hold on a database migrated from
   `packages/core/tests/fixtures/pre_tenancy_schema.sql` (whose `memories` table
   has no FK on `tenant_id`), which proves the guard, not the FK, enforces it.
4. `_bump_retrieval(ids, now)` (an incidental side effect of `search`) SHALL
   update only rows whose tenant is active (`… AND tenant_id IN (SELECT id FROM
   tenants WHERE is_active = 1)`) and never raise for an inactive tenant.
5. Reads SHALL NOT call the guard: a read of an inactive tenant's rows works.
6. The guard and the write run in one `transaction()` under the lock of R4, so
   within one process a deactivation cannot interleave with a write. Across
   processes, a tenant deactivated between the guard and the write lets that one
   write through (accepted).

### Requirement 2 — Same-tenant references

#### Acceptance Criteria

1. `add_link(link)`: WHEN both endpoints exist and their tenants differ THEN it
   SHALL raise `CrossTenantLinkError(link.source_memory_id, <source tenant>,
   link.target_memory_id, <target tenant>)`; WHEN they share tenant `E` but
   `link.tenant_id != E` THEN `CrossTenantLinkError(link.source_memory_id, E,
   link.target_memory_id, link.tenant_id)`. A missing endpoint keeps today's
   behaviour (the FK raises `sqlite3.IntegrityError`). Nothing is written on error.
2. `record_query_results(results)`: for each result, with `S` the stored tenant
   of its session and `M` the stored tenant of its memory: `result.tenant_id !=
   S` → `CrossTenantLinkError(result.session_id, S, result.memory_id,
   result.tenant_id)`; `S != "global"` and `M != S` →
   `CrossTenantLinkError(result.session_id, S, result.memory_id, M)`. A `global`
   session MAY reference memories of any tenant: it is the read-audit record of
   an unscoped search, not a semantic link. All results are validated before the
   first insert.
3. `supersede_memory(memory_id, by_id, …)`: WHEN both rows exist in different
   tenants THEN `CrossTenantLinkError(memory_id, <its tenant>, by_id, <its
   tenant>)`.
4. `add_memory(record)` with `record.superseded_by = X` and `update_memory(id,
   superseded_by=X)`: WHEN `X` exists in another tenant than the record THEN
   `CrossTenantLinkError(<record id>, <record tenant>, X, <X's tenant>)`; a missing
   `X` keeps today's FK behaviour.
5. `update_memory(memory_id, **fields)`: WHEN `fields` has `tenant_id` different
   from the stored tenant THEN `TenantImmutableError(memory_id, stored,
   requested)`; an equal value is accepted and the column is never written.
6. Soft references — `entity_ids`, `contradicts_ids`, a session's
   `useful_ids`/`stale_ids`, metadata values — are NOT checked by storage; the
   consumers in `tenant-scoped-core` resolve them with tenant-confined reads.
7. Examples (tenants `global` and `t1`, memories `g1` in `global`, `a1`, `a2` in
   `t1`): `add_link(ConceptLink(source_memory_id="g1", target_memory_id="a1",
   link_type="relates_to"))` → `CrossTenantLinkError`; the same link `a1`→`a2`
   with `tenant_id="t1"` succeeds; with the default `tenant_id` (`global`) →
   `CrossTenantLinkError`; a `global` session recording `a1` succeeds; a `t1`
   session recording `g1` → `CrossTenantLinkError`;
   `update_memory("a1", tenant_id="global")` → `TenantImmutableError`;
   `supersede_memory("a1", by_id="g1")` → `CrossTenantLinkError("a1", "t1",
   "g1", "global")` and a1 stays active; `update_memory("a1",
   superseded_by="g1")` → `CrossTenantLinkError`.

### Requirement 3 — `tenant_id` on writes that act by id

#### Acceptance Criteria

1. Signatures (SQLite and Protocol):
   `archive_memory(memory_id: str, tenant_id: str | None = None) -> None`,
   `supersede_memory(memory_id: str, by_id: str, tenant_id: str | None = None) ->
   None`, `apply_feedback(memory_id: str, useful: bool, stale: bool, tenant_id:
   str | None = None) -> None`.
2. `tenant_id=None`: act on the stored row by id and guard on its tenant (an
   inactive tenant's row raises `TenantInactiveError`). A missing row keeps
   today's behaviour: `archive_memory` and `supersede_memory` do nothing,
   `apply_feedback` raises `KeyError(f"memory {memory_id!r} not found")`.
3. Concrete `tenant_id=T`: the row SHALL exist with `tenant_id == T`, else
   `KeyError(f"memory {memory_id!r} not found")` — a foreign id is
   indistinguishable from a missing one. For `supersede_memory` both `memory_id`
   and `by_id` SHALL be in `T` (the `KeyError` names the first one that is not).
4. These writes never change a row's `tenant_id`.
5. Example: `archive_memory("a1", tenant_id="global")` raises `KeyError` and
   `a1` stays active; `archive_memory("a1")` and `archive_memory("a1",
   tenant_id="t1")` archive it.

### Requirement 4 — Re-entrant `transaction()` on the Protocol

#### Acceptance Criteria

1. `SqliteBackend.transaction()` SHALL stay a context manager yielding the
   `sqlite3.Connection` and become re-entrant: the outermost entry acquires
   `self._tx_lock` (a `threading.RLock` created in `__init__`) and sets
   `self._tx_depth` to 1; a nested entry in the same thread increments the depth
   and neither commits nor rolls back; when the outermost entry exits it commits,
   or rolls back and re-raises on an exception.
2. Because every public write already runs inside `with self.transaction()`, a
   caller SHALL be able to compose public writes atomically:
   `with store.transaction(): store.add_memory(a); store.add_memory(b);
   store.add_link(l)`. WHEN an exception leaves the block THEN none of `a`, `b`,
   `l` persists, including their FTS5/trigram rows and embeddings (columns and
   trigger-maintained tables of the same database).
3. Another thread's write SHALL wait on the lock until the outermost
   transaction of the first thread ends (no interleaving on the shared
   connection).
4. `ports.py` SHALL add `def transaction(self) -> AbstractContextManager[object]:
   ...` to `StorageBackend`, documenting that Protocol callers MUST NOT use the
   yielded value (it is backend-specific). The module docstring's "excluded from
   the Protocol" note SHALL be updated for `transaction()` (`connect()` stays
   SQLite-only).
5. `PostgresBackend` interim: `transaction()` raises
   `TenancyNotSupportedError("transaction")` when entered; the id-only writes of
   R3, and `update_memory` when `fields` has `tenant_id`, call
   `_require_global_tenant(tenant_id, …)` before any pool access and keep
   today's SQL for `None` and `"global"`.

### Requirement 5 — Compatibility and gates

#### Acceptance Criteria

1. On a database with only the `global` tenant every existing test SHALL pass
   unchanged.
2. The gates of `.l4/config.yaml` SHALL pass (ruff check, ruff format --check,
   mypy packages, pytest with the 80% coverage floor). No test needs Postgres,
   Docker or a network service.
