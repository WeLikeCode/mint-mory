# MintMory backend conformance suite

## What lives here

| File | Purpose |
|---|---|
| `__init__.py` | `BackendHandle` fixture wrapper (importable as `from conformance import BackendHandle`) |
| `conftest.py` | `backend` + `backend_factory` fixtures, parametrized over `sqlite` and `postgres` |
| `test_backend.py` | Comprehensive protocol conformance suite (MUST-pass + capability-gated) |
| `test_golden_retrieval.py` | Thresholded recall@5 baseline over a 70-memory deterministic corpus |

## Running today (Phase 1)

The SQLite leg always runs inside the standard `pytest` suite:

```sh
uv run pytest packages/core/tests/conformance -q
```

The Postgres leg auto-skips (`pytest.mark.skipif`) because:
1. `MINTMORY_TEST_PG_DSN` is not set, and
2. `mintmory.core.storage_postgres` does not exist yet (Phase 2).

## Adding the Postgres CI leg (Phase 2 TODO)

When `PostgresBackend` ships, add to the CI matrix:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    env:
      POSTGRES_PASSWORD: test
      POSTGRES_DB: mintmory_test
    ports:
      - 5432:5432
    options: >-
      --health-cmd pg_isready
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5

env:
  MINTMORY_TEST_PG_DSN: "postgresql://postgres:test@localhost:5432/mintmory_test"
```

The conformance suite will then run with `id=sqlite` and `id=postgres` parameters.
No test code changes are needed — the fixture already wires the Postgres path.

**Why not add the PG service now?** Standing up a `pgvector/pgvector:pg16`
container in Phase 1 costs real CI minutes for zero backend code — the Postgres
branch in the fixture is unreachable today.  The service container lands in Phase 2
together with `PostgresBackend`, so CI spend tracks backend availability exactly.

## MUST-pass vs capability-gated matrix

See the module-level docstring of `test_backend.py` for the authoritative table.
Short version:

- **MUST-pass** — all tests without `@pytest.mark.vector` or `@pytest.mark.trigram`
- **`@pytest.mark.vector`** — skips when `backend.vector_search_available()` is False
- **`@pytest.mark.trigram`** — probes at runtime; skips if substring search returns 0 hits

## Recall threshold (golden retrieval)

`recall@5 >= 0.70` — find the golden needle in the top-5 results for at least
8 out of 11 golden queries (ceil(0.70 × 11) = 8).  Baseline computed with
`HashingEmbedder(dim=64)` + FTS5 BM25 on SQLite.  Phase 2's Postgres backend
must meet the same threshold (design.md §6.1 bounded-drift guarantee).
