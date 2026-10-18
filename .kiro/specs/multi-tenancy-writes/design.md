# Design — Multi-Tenancy 2/10: write guard, references, transactions

## Grounding (base branch + `multi-tenancy`)

- `SqliteBackend` holds one shared `sqlite3.Connection` (`check_same_thread=False`)
  and every public write is `with self.transaction() as conn: conn.execute(…)`.
  Today `transaction()` commits on every exit, so a caller wrapping several
  writes gets one commit per write — composition is impossible.
- `apply_feedback` reads the row with `connect()` and raises `KeyError` for a
  missing id; `archive_memory` / `supersede_memory` issue an `UPDATE … WHERE id
  = ?` and silently do nothing for a missing id; `add_link` is `INSERT OR IGNORE`
  and a missing endpoint fails the FK with `sqlite3.IntegrityError`.
- The API (`PATCH`/`DELETE /memories/{id}`, `POST /memories/{id}/links`), MCP and
  CLI call these methods; none passes a tenant yet, so `None` keeps them as today.

## Helpers (private, `storage.py`)

```python
def _assert_tenant_writable(self, conn: sqlite3.Connection, tenant_id: str) -> None: ...
def _stored_tenant(self, conn: sqlite3.Connection, memory_id: str) -> str | None:
    """SELECT tenant_id FROM memories WHERE id = ?; None when missing."""
def _session_tenant(self, conn: sqlite3.Connection, session_id: str) -> str | None: ...
```

Write order inside each method's transaction: resolve stored tenants → tenant
checks (R2/R3) → `_assert_tenant_writable` → the existing SQL. Validation of a
batch (`record_query_results`) completes before the first insert.

## Re-entrant transaction

```python
@contextmanager
def transaction(self) -> Generator[sqlite3.Connection, None, None]:
    with self._tx_lock:                      # RLock: re-entrant per thread
        conn = self.connect()
        self._tx_depth += 1
        try:
            yield conn
        except BaseException:
            self._tx_depth -= 1
            if self._tx_depth == 0:
                conn.rollback()
            raise
        else:
            self._tx_depth -= 1
            if self._tx_depth == 0:
                conn.commit()
```

The lock also serialises writers from different threads on the shared
connection, which removes today's hazard of one thread's `commit()` committing
another thread's half-done work. Reads do not take the lock (as today). A nested
block that raises leaves the decision to the outermost block: if the caller
catches the exception inside the outer block, the outer block still commits the
statements that succeeded (no savepoints). `initialise()` and the `_ensure_*`
helpers keep their own commits; they are never called inside a transaction.

Rollback coverage: embeddings are a column of `memories`, FTS5 and trigram are
virtual tables maintained by triggers in the same database, so a rollback undoes
them with the row. No external index exists for SQLite.

## Postgres interim

`PostgresBackend.transaction()` is a `@contextmanager` that raises
`TenancyNotSupportedError("transaction")` before yielding; the real one arrives
with `multi-tenancy-postgres-writes`. The id-only writes gain the `tenant_id`
parameter and call `_require_global_tenant`; every Postgres row is a `global`
row until then, so `None` and `"global"` keep today's SQL.

## Tests (all SQLite, `packages/core/tests/test_tenancy_writes.py`)

- Guard on each method of the R1.2 table (missing and inactive tenant), on a
  fresh database and on one migrated from `pre_tenancy_schema.sql`.
- `_bump_retrieval` skips an inactive tenant's rows (retrieval_count unchanged)
  and still bumps an active tenant's rows.
- Every example of R2.7 and R3.5.
- Transactions: three writes then `raise RuntimeError` inside one block → zero
  new rows and `memories_fts MATCH` finds nothing; nested blocks commit once
  (count `commit` calls via a wrapper connection or check visibility from a second
  `SqliteBackend` on the same file only after the outer block exits); a second
  thread's `add_memory` blocks until the first thread's block exits
  (`threading.Event`, then assert the order of completion).
- `packages/core/tests/test_pg_tenancy.py` (`PostgresBackend("postgresql://unused")`):
  `test_pg_transaction_tenancy` (entering `transaction()` raises
  `TenancyNotSupportedError`) and `test_pg_<method>_tenancy` for the id-only
  writes (`tenant_id="t1"` raises before any connection).

## Risks

- A write path missing from the guard table → the per-method guard tests.
- Thread starvation on a long copy → copies are bounded (`cross-tenant-copy`
  caps a selection at 10,000 memories).
