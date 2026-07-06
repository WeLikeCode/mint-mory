# Tasks: Pluggable storage backend (design + decomposition)

This change is **design-only**. Its deliverable is the validated analysis, the
recommended backend, the port architecture, and the phased epic below. No backend
code lands here. Each phase becomes its own OpenSpec change when scheduled.

## 1. Design deliverable (this change)

- [x] 1.1 Map the SQLite coupling, including the `store.connect()` escape hatch
  (~20 raw-SQL sites) that extends the 7-constructor-site view.
- [x] 1.2 Compare candidate backends (PostgreSQL vs libSQL vs others) and recommend one.
- [x] 1.3 Define the `StorageBackend` port + `build_storage()` factory + `StorageSettings`.
- [x] 1.4 Enumerate the hard problems (FTS parity, vector parity, concurrency, migrations,
  data migration, conformance testing) each with a mitigation.
- [x] 1.5 Decompose into an ordered, independently-shippable phased epic.
- [x] 1.6 Record the human decisions required before Phase 2 (§8 of design.md).

## 2. Phase 0 — Extract the port (PURE REFACTOR) — ✅ SHIPPED as MM-46

- [x] 2.1 Absorb API-reachable raw-SQL/private leaks (dreaming, session, notes, vision,
  `/readyz`) into named public methods — verbatim SQL relocation, **preserving today's
  transaction boundaries** (session-conclude NOT made atomic — reviewers confirmed).
- [x] 2.1a Resolve the CLI `ingest` primary-store raw `connect()`: added the portable
  `memory_exists_with_content()` port method (preferred option).
- [x] 2.2 `manifest_get` → `ManifestEntry` (TypedDict, mapping-compatible); dropped `sqlite3.Row`.
- [x] 2.3 Defined `StorageBackend` Protocol (`core/ports.py`); renamed `StorageAdapter` →
  `SqliteBackend` + alias; `connect()`/`transaction()` kept on `SqliteBackend` only.
- [x] 2.4 `StorageSettings` (folds in `MINTMORY_DB` + `MINTMORY_SQLITE_BUSY_TIMEOUT_MS` alias, with a
  validator replicating the legacy malformed/negative tolerance) + `build_storage()` factory.
- [x] 2.5 Swapped portable call sites (api/mcp no-embedder, cli with-embedder) to the factory;
  pinned history + cochange to `SqliteBackend` explicitly.
- [x] 2.6 Exit met: all existing tests pass unmodified; mypy/ruff clean; grep proves no module
  outside storage/history/cochange/CLI touches `.connect()`/`_`-members; 1405 passed, 95.95% cov.

  *Implemented via workflow (Sonnet impl → 3 adversarial Opus reviewers, all pass, 0 must-fix →
  3 should-fix applied). Known Phase 2 follow-up: cochange MCP/CLI tools reach the primary store via
  `cast(SqliteBackend, ...)` — safe now (always SQLite), needs a runtime guard when postgres lands.*

## 3. Phase 1 — Backend conformance harness — ✅ SHIPPED as MM-47

- [x] 3.1 `backend` fixture (`tests/conformance/conftest.py`) parametrized over sqlite (always) +
  postgres (auto-skips until `MINTMORY_TEST_PG_DSN` set AND PostgresBackend importable). Built via
  `build_storage()` so Phase 2 validates the factory-dispatch plug-in path, not just the class.
- [x] 3.2 Golden-set retrieval (`test_golden_retrieval.py`): deterministic 70-memory / 7-cluster
  corpus + HashingEmbedder, `recall@5 >= 0.70` (SQLite baseline is 1.0 — headroom for PG tsvector drift).
- [x] 3.3 SQLite conformance leg runs inside the existing `gates` pytest. The `pgvector/pgvector:pg16`
  CI service + `MINTMORY_TEST_PG_DSN` is deferred to Phase 2 (an empty PG job now = pure waste); the
  YAML snippet is staged in `tests/conformance/README.md`.
- [x] 3.4 Exit met: 96 conformance tests green on SQLite (96 PG legs skip); documented MUST-pass vs
  capability-gated (`@pytest.mark.vector`/`@pytest.mark.trigram`) matrix. Full suite 1501 passed, 95.87% cov.

  *Workflow: Sonnet impl → 2 Opus reviewers (completeness reviewer FAILED first pass — caught
  `anchor_candidates`/`list_notes`/vision methods with zero coverage, both API-reachable + porting
  hazards) → all 2 must-fix + 4 should-fix applied → re-green. Coverage now spans all 33 port methods.*

## 4. Phase 2 — PostgresBackend — ✅ SHIPPED as MM-48

- [x] 4.1 `mintmory-core[postgres]` extra (psycopg3 `[binary,pool]` + pgvector).
- [x] 4.2 Schema (`schema_postgres.sql`): jsonb, boolean, native timestamps, generated `tsvector` +
  GIN, `pg_trgm` GIN, unconstrained `vector` column, same CHECKs + partial indexes. **Deviation
  (accepted): runtime DDL under `pg_advisory_xact_lock` instead of Alembic** — idempotent + race-safe
  across replicas; a versioned Alembic tree is deferred until the schema first evolves (wired into the
  Phase 4 migration Job then). Keeps the postgres image lean (no sqlalchemy).
- [x] 4.3 Three score methods (prefix `to_tsquery`/`ts_rank`, `pg_trgm similarity`, pgvector `<=>`
  exact scan) — extracted a SHARED `core/hybrid_search.py` fusion pipeline; both backends call it, so a
  backend implements only the three score methods (design §5.1). SQLite refactor is behaviour-preserving.
- [x] 4.4 Atomic `apply_feedback` (single UPDATE + LEAST/GREATEST, verified 200 concurrent votes → no
  lost updates); `update_memory` excludes counter columns (no clobber); API `anyio.to_thread` offload
  with the thread-limiter capped to `pool_max`.
- [x] 4.5 Exit met on a REAL Postgres 16 + pgvector (docker), verified independently on a clean DB,
  sequentially: conformance 96 passed, golden recall ≥ 0.70, soak + lost-update invariant passed;
  `ping()` returns False on outage (503, no crash-loop). Unconstrained-`vector` + dim-guard mirrors
  SQLite's NULL-skip so it's embedder-dim-agnostic. Vector column has NO ANN index yet (exact scan =
  today's semantics; HNSW deferred). CI gains a `conformance-pg` job (pgvector service container).

  *Workflow: Sonnet impl → 3 adversarial Opus reviewers (ALL PASS, 0 must-fix — each ran the live-PG
  suite; atomic feedback + shared-fusion parity independently verified) → 6 should-fix applied
  (advisory-lock leak → `pg_advisory_xact_lock`; to_thread offload; real lost-update soak assertion;
  mixed-dim test now runs on PG; dead `_passes_filter` removed). A `list_notes[postgres]` blip seen by
  one reviewer was parallel-reviewer TRUNCATE contention — clean sequential re-run: 0 failures.*
- [ ] 4.6 (Phase 2 follow-up, tracked) cochange MCP/CLI `cast(SqliteBackend, ...)` needs a runtime
  guard once postgres is a real runtime option; HNSW ANN index is a later perf change with its own recall test.

## 5. Phase 3 — Migration tooling — ✅ SHIPPED as MM-49

- [x] 5.1 `mintmory migrate-storage --from sqlite:PATH --to postgres:DSN` (core/migrate.py) — streaming
  batch copy in FK-safe order (memories two-pass for the self-referential `superseded_by`), type
  conversions (int→bool, ISO-TEXT→timestamp, JSON→jsonb, float32 BLOB→pgvector), `--dry-run` (writes
  nothing, runs NO DDL), `--force` (truncate+re-verify). Whole migration in ONE transaction — a
  mid-run crash rolls back to an empty target (no half-migrated DB).
- [x] 5.2 Verification: per-table row counts + SHA-256 content checksums (collation-independent Python
  BINARY sort so PG `en_US.utf8` vs SQLite `BINARY` can't spuriously fail); tsvector/embedding excluded
  from the checksum but embedding fidelity separately asserted (element-wise `max_abs_diff==0.0`). No
  embedding-dim enforcement needed (unconstrained vector + query-time dim-guard). K8s runbook in the
  module docstring. Non-empty target refused unless `--force`; DSN kept out of logs/tracebacks.
- [x] 5.3 Exit met: 34 round-trip tests green on real PG (all tables count+checksum PASS; read-parity
  via get_memory/search/get_links/list_notes/get_summary/manifest_get/get_session); idempotent re-run
  refused; `--dry-run` writes nothing. Orchestrator also ran a live end-to-end CLI smoke (dry-run →
  real migrate → refused re-run → queryable read-back through PostgresBackend). SQLite suite 1520
  passed, 90.29% cov; ruff + mypy(89) clean.

  *Workflow: Sonnet impl → 2 Opus reviewers (both PASS, 0 must-fix) → all 8 should-fix applied
  (collation-safe checksum sort, single-transaction rollback safety, real embedding-vector assertion,
  `postgres://` scheme parsing, dry-run runs no DDL, bad-DSN pre-flight). Nits deferred: runbook
  `kubectl set env` DSN-in-plaintext → superseded by Phase 4's Secret-ref DSN.*

## 6. Phase 4 — Helm HA relaxation — ✅ SHIPPED as MM-50

- [x] 6.1 `storage.backend` (sqlite|postgres) + `storage.postgres.{dsn,existingSecret,...}`; conditional
  `values.schema.json` via JSON Schema `if/then/else`: sqlite (default/fail-closed) keeps replicaCount
  max 1 + accessMode RWO; postgres relaxes to replicaCount ≤ 20 + `persistence.enabled:false`.
  deployment.yaml branches on backend — sqlite: Recreate + PVC + MINTMORY_DB; postgres: RollingUpdate
  (maxUnavailable 0), N replicas, stateless (no PVC), MINTMORY_STORAGE_BACKEND + DSN via `secretKeyRef`.
- [x] 6.2 New `postgres-secret.yaml` (DSN from value OR bypass for `existingSecret`; fail-fast if
  neither), `pdb.yaml` (+ soft pod anti-affinity) postgres-only; `values-postgres.yaml` example tier;
  mode-conditional README (guardrail table for sqlite; N-replica/RollingUpdate/no-PVC/BYO-DSN + CNPG
  recipe for postgres) + mode-aware NOTES.txt + migrate-storage runbook.
  **Deviation (accepted): no migration Job** — `PostgresBackend.initialise()` self-creates the schema
  under `pg_advisory_xact_lock` (race-safe across N replicas), so a deploy-time Job would add hook/RBAC
  complexity for no benefit; the one-time data move is the manual `mintmory migrate-storage` runbook.
- [x] 6.3 Exit met via OFFLINE validation (no live cluster; k6/kill-a-pod/CNPG-failover are a real-cluster
  follow-up): helm lint clean; kubeconform valid for sqlite (4), advanced (7), postgres (7); the
  **guardrail negative tests all reject** (sqlite+replicaCount=2, default+replicaCount=2 fail-closed,
  ReadWriteMany) while postgres+replicaCount=3 renders 3 replicas + RollingUpdate + no PVC + PDB. DSN
  verified to appear ONLY in a Secret (never ConfigMap/inline env); existingSecret bypasses chart Secret.

  *Workflow: Sonnet impl → 2 Opus reviewers (both PASS, 0 must-fix, 0 should-fix — the guardrail
  reviewer exhaustively proved the schema rejects every sqlite break-attempt and is not a no-op; the
  HA reviewer grep-verified DSN-secret-only + stateless pod). 4 cosmetic nits left as-is.*

---

## Epic status: ✅ COMPLETE (design + Phases 0–4 all shipped + CI-green)

MintMory storage is now pluggable (`MINTMORY_STORAGE_BACKEND=sqlite|postgres`): SQLite stays the
zero-dependency default; PostgreSQL delivers real HA (N stateless API replicas, RollingUpdate, no
single-writer PVC) with a verified SQLite→Postgres migration path. Follow-ups tracked in 4.6.
</content>
