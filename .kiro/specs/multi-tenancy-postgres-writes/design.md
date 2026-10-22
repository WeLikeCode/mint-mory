# Design — Multi-Tenancy 9/10: Postgres tenant directory, write guard and transactions

## Grounding (base branch + `multi-tenancy-postgres`)

- Every `PostgresBackend` method opens `with self._pool.connection() as conn:`;
  writes call `conn.commit()` themselves; reads use `_execute_dict`. A
  `psycopg_pool` connection context rolls back on an exception and returns the
  connection to the pool.
- `apply_feedback` is one server-side atomic `UPDATE`; `update_memory` reads the
  row with `get_memory` and then updates a fixed SET list.
- After `multi-tenancy-postgres` every table has `tenant_id` with an FK to
  `tenants`, and `_require_global_tenant` still limits writes to `global`.

## Connection binding

```python
from contextvars import ContextVar

def __init__(…):
    …
    self._tx_conn: ContextVar[Any | None] = ContextVar(f"mintmory_pg_tx_{id(self)}", default=None)

@contextmanager
def _conn(self) -> Iterator[Any]:
    bound = self._tx_conn.get()
    if bound is not None:
        yield bound
        return
    assert self._pool is not None
    with self._pool.connection() as conn:
        self._register_adapters(conn)
        yield conn
        conn.commit()

@contextmanager
def transaction(self) -> Iterator[Any]:
    if self._tx_conn.get() is not None:
        yield self._tx_conn.get()
        return
    assert self._pool is not None
    with self._pool.connection() as conn:
        self._register_adapters(conn)
        token = self._tx_conn.set(conn)
        try:
            yield conn
            conn.commit()
        finally:
            self._tx_conn.reset(token)
        # on an exception the pool's connection context rolls back (once)
```

A `ContextVar` is per thread and per asyncio task, so a transaction in one
request is invisible to another; each gets its own pool connection and Postgres
isolates them. That is why no lock is needed here (unlike SQLite's single
shared connection). Reads go through `_conn()` too: otherwise a read inside a
transaction would take a second pool connection and miss the rows written
earlier in the same block (for example `update_memory` reading the row that
`add_memory` just wrote).

## Guard and references

The same helper names as SQLite (`_assert_tenant_writable`, `_stored_tenant`,
`_session_tenant`) run on the method's connection, so inside a `transaction()`
they see the transaction's own uncommitted rows. Postgres raises a
`ForeignKeyViolation` for a missing endpoint just as SQLite raises
`IntegrityError`; both are left as they are (today's behaviour).

## Tests

- `packages/core/tests/test_pg_tenancy_writes.py` with `pg_fakes`: a responder
  keyed on SQL prefixes (`SELECT is_active FROM tenants` → `[{"is_active":
  False}]`, `SELECT tenant_id FROM memories WHERE id` → the tenant of the
  requested id, …).
- `packages/core/tests/conformance/test_conformance_tenancy_writes.py` (R7): runs through
  the existing parametrised `backend` fixture; the fixture's skip of the Postgres
  leg without `MINTMORY_TEST_PG_DSN` is the existing one in `conftest.py`.

## Risks

- A method left on `self._pool.connection()` → it would not join a
  transaction; the R4.5 tests cover `add_memory` and `get_memory` inside a block,
  and the conformance test of R7 composes writes on a real database.
