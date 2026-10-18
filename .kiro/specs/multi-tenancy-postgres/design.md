# Design — Multi-Tenancy 8/10: Postgres schema, migrations and column parity

## Grounding (base branch, verified)

- `schema_postgres.sql`: `IF NOT EXISTS` DDL for the six tables with
  `BOOLEAN`/`FLOAT`/`JSONB`/`TIMESTAMP`/`vector`, a generated `content_tsv` with
  a GIN index, a `pg_trgm` GIN index; `concept_links` has an unnamed `UNIQUE
  (source_memory_id, target_memory_id, link_type)`, `memory_summaries.concept` is
  `TEXT NOT NULL UNIQUE`, `index_manifest.path` is `TEXT PRIMARY KEY`.
- `PostgresBackend.initialise()`: creates the `psycopg_pool.ConnectionPool` only
  when `self._pool is None`, installs extensions, then in one connection runs
  `SELECT pg_advisory_xact_lock(…)`, `_create_schema(conn)` (the whole DDL file)
  and `conn.commit()`, then probes capabilities. Every method uses `with
  self._pool.connection() as conn:` and `_execute_dict(conn, sql, params)`
  (`conn.cursor(row_factory=…)`).
- Conflict targets today: `add_link` `ON CONFLICT (source_memory_id,
  target_memory_id, link_type)`, `upsert_summary` `ON CONFLICT(concept)`,
  `manifest_upsert` `ON CONFLICT(path)` — all three stop matching a constraint
  once the keys change, which is why this unit changes the backend SQL together
  with the DDL.
- `migrate.py`: one-shot SQLite→Postgres copy driven by `_FK_ORDER`,
  `_TABLE_COLS`, `_TABLE_PK`, classification dicts, `_insert_*_batch(conn, rows)`
  (`conn.cursor()` + `executemany`), `_pg_truncate_all`, checksum verification;
  `dry_run=True` opens no Postgres connection; the source is opened
  `mode=ro`.
- Real-Postgres tests exist only behind `MINTMORY_TEST_PG_DSN`: the conformance
  fixture's `postgres` parameter and `test_migrate.py`'s `_SKIP_PG` classes, run
  by the `conformance-pg` job of `.github/workflows/ci.yml`.

## Migration

Splitting catalog reading (needs a database) from planning (pure) puts the
whole decision logic under database-free tests. The catalog queries:

```sql
SELECT table_name, column_name FROM information_schema.columns
 WHERE table_schema = current_schema() AND table_name = ANY(%s);
SELECT c.conrelid::regclass::text AS table_name, c.conname, c.contype,
       array_agg(a.attname ORDER BY k.ord) AS columns
  FROM pg_constraint c
  CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
 WHERE c.contype IN ('u', 'p') AND c.connamespace = current_schema()::regnamespace
   AND c.conrelid::regclass::text = ANY(%s)
 GROUP BY 1, 2, 3;
SELECT indexname FROM pg_indexes WHERE schemaname = current_schema();
```

Constraints are dropped by the name found in the catalog (the old ones were
auto-named), so no table rebuild is needed; `ADD COLUMN … REFERENCES` gives
migrated tables the FK directly (unlike SQLite). `ADD COLUMN … DEFAULT 'global'`
backfills existing rows. All of it runs in the advisory-locked transaction of
`initialise()`; a failure rolls the whole transaction back.

## Fakes

`pg_fakes.py` records every statement; tests assert on substrings of the SQL
text and on parameter tuples. `_register_adapters` already swallows errors, so
`pgvector.register_vector(fake_conn)` failing is harmless. Capability probes get
`[]` from the default responder (`fetchone()` is `None`), so they report no
extension, which is what the code already handles.

## migrate.py

`tenants` first in `_FK_ORDER` satisfies the FKs of every other table. The
pre-checks query the read-only source (`sqlite_master`, `PRAGMA table_info`,
`SELECT DISTINCT tenant_id FROM <t> WHERE tenant_id NOT IN (SELECT id FROM
tenants)`), so they run in `dry_run` as well and fail before any target write.

## What is not proven automatically

The `ALTER` statements of R2.1 are not executed against a real pre-feature
Postgres database by any automated test: the plan is unit-tested, and the
catalog SQL runs on a real database in every `conformance-pg` run (where it
returns the migrated shape). A person can run the in-place migration once on a
copy of a production database before relying on it.
