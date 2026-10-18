# Design — Multi-Tenancy 10/10: Postgres tenant-scoped reads and search

## Grounding (base branch + units 8–9)

- Postgres phases: `_fts_scores` (`content_tsv @@ to_tsquery(…)` ranked by
  `ts_rank`), `_trigram_scores` (`word_similarity` over `pg_trgm`),
  `_vector_scores` (`embedding <=> %s` with a `vector_dims` guard),
  `_load_memories` (`WHERE id IN (…)`); `search` calls the shared
  `fuse_and_search`; `search_around` runs one SELECT on `concept_links` per hop.
- After `multi-tenancy-postgres-writes` every method uses `self._conn()`, and the
  tenant directory works, so `search` can read the tenant's `is_active`.
- `_SELECT_MEMORY` names `tenant_id` since `multi-tenancy-postgres`, so the parity
  check looks for the predicate (`tenant_id =`), not for the column name.

## SQL construction

Same pattern as SQLite: build today's SQL, append `AND tenant_id = %s` (with the
alias the statement already uses) and the parameter only when the tenant is
concrete. For the FTS/trigram/vector phases the predicate goes into the `WHERE`
before `ORDER BY … LIMIT`, so the candidate limit counts only that tenant's
rows.

## Tests

- `packages/core/tests/test_pg_tenancy_reads.py` with `pg_fakes`: one
  parametrised test over the method list of R1.1 (call with `"t1"`, then with
  `None`, inspect `conn.executed`), plus R2.2 and R3.2.
- `packages/core/tests/conformance/test_tenancy_reads.py` (R4).

## Risks

- A phase left unconfined would let another tenant's ids reach fusion; the
  defense-in-depth drop in `fuse_and_search` (from `multi-tenancy-reads`) still
  removes them, and the per-method fake test catches the missing predicate.
