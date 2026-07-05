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

## 3. Phase 1 — Backend conformance harness — future change `add-storage-conformance-suite`

- [ ] 3.1 Parametrize storage-behaviour tests over a `backend` fixture (sqlite always; PG when DSN set).
- [ ] 3.2 Golden-set retrieval corpus + thresholded recall assertions (recall@K vs SQLite baseline).
- [ ] 3.3 CI matrix: sqlite always; `postgres:16`+pgvector service container wired, allowed-empty.
- [ ] 3.4 Exit: conformance green on SQLite; documented MUST-vs-capability test matrix.

## 4. Phase 2 — PostgresBackend — future change `add-postgres-backend`

- [ ] 4.1 `mintmory-core[postgres]` extra (psycopg3 + pool + pgvector).
- [ ] 4.2 Alembic initial schema (jsonb, boolean, timestamptz, generated tsvector + GIN, pg_trgm,
  `vector` column, same CHECKs + partial indexes).
- [ ] 4.3 Three score methods (tsquery/`ts_rank`, `similarity`/pg_trgm, `<=>` exact scan) behind the shared fusion path.
- [ ] 4.4 Atomic rewrites of `apply_feedback`/hot mutators; API `to_thread` offload.
- [ ] 4.5 Exit: conformance + golden set green on PG; `/readyz` survives PG outage; 2-process soak, zero integrity errors.

## 5. Phase 3 — Migration tooling — future change `add-storage-migration-tool`

- [ ] 5.1 `mintmory migrate-storage --from sqlite:PATH --to postgres:DSN` streaming copy + type conversion + `--dry-run`.
- [ ] 5.2 Row-count + per-table checksum verification; dimension-policy enforcement; K8s runbook.
- [ ] 5.3 Exit: round-trip test (migrate fixture, run read-suite on PG, diff vs SQLite); idempotent re-run.

## 6. Phase 4 — Helm HA relaxation — future change `relax-chart-ha-constraints`

- [ ] 6.1 `storage.backend` + DSN secret-ref; conditional `values.schema.json` (sqlite → today's
  constraints; postgres → replicaCount N, RollingUpdate, `persistence.enabled:false`).
- [ ] 6.2 Migration Job hook; PDB + anti-affinity; CNPG BYO docs; mode-conditional README.
- [ ] 6.3 Exit: documented green validation on a real cluster (3 replicas under k6 through a rolling
  update, kill-a-pod, CNPG failover).
</content>
