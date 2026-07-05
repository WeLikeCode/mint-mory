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

## 2. Phase 0 — Extract the port (PURE REFACTOR) — future change `refactor-storage-port`

- [ ] 2.1 Absorb API-reachable raw-SQL/private leaks (dreaming, session, notes, vision,
  `/readyz`) into named public methods — verbatim SQL relocation, **preserving today's
  transaction boundaries** (do NOT make session-conclude atomic here — deferred to Phase 2).
- [ ] 2.1a Resolve the CLI `ingest` primary-store raw `connect()` (`cli/main.py:314`): either add a
  portable `memory_exists_with_content()` port method (preferred) or pin `ingest` to `SqliteBackend`.
- [ ] 2.2 `manifest_get` → `ManifestEntry` (mapping-compatible); drop `sqlite3.Row` from signatures.
- [ ] 2.3 Define `StorageBackend` Protocol; rename `StorageAdapter` → `SqliteBackend` + alias;
  keep `connect()`/`transaction()` on `SqliteBackend` only.
- [ ] 2.4 `StorageSettings` (fold in `MINTMORY_DB` + `MINTMORY_SQLITE_BUSY_TIMEOUT_MS`) + `build_storage()`.
- [ ] 2.5 Swap portable call sites to the factory; pin the 3 history sites to `SqliteBackend`.
- [ ] 2.6 Exit: all existing tests pass with mechanical edits only; mypy/ruff clean; grep proves
  no module outside storage/history/cochange/CLI touches `.connect()`/`_`-members; behaviour byte-identical.

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
