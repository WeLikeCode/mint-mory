# Change: Pluggable storage backend for real HA (design + decomposition)

## Why

MintMory's only persistence layer is a single SQLite file opened by
`StorageAdapter` (`packages/core/src/mintmory/core/storage.py`) with one cached
`sqlite3.Connection`. This is an excellent zero-dependency local default — and it
hard-locks the Kubernetes deployment into a single-writer topology that the shipped
Helm chart enforces structurally: `replicaCount` schema-capped at 1,
`strategy: Recreate` (never RollingUpdate), a ReadWriteOnce block-storage PVC, and 1
uvicorn worker. Horizontal scaling and rolling updates are impossible today.

For real HA (N stateless API replicas, RollingUpdate, no single-writer PVC), the
storage backend must become **pluggable behind a port** so the REST API can run
against an external multi-writer database — while SQLite stays the default so the CLI,
MCP servers, and single-pod deploys keep the zero-dependency single-file experience
byte-for-byte unchanged.

**This change is DESIGN + DECOMPOSITION ONLY.** No backend is implemented here. It
records the analysis, the recommended backend (PostgreSQL), the port architecture, the
hard problems, and a phased epic whose Phase 0 (a pure, zero-behaviour-change refactor)
is the only part safe to build first. Later phases become their own OpenSpec changes.

## What changes

- **A storage port.** Define a `StorageBackend` Protocol equal to the current public
  `StorageAdapter` surface; `StorageAdapter` becomes `SqliteBackend`; a
  `build_storage()` factory selects the backend via
  `MINTMORY_STORAGE_BACKEND=sqlite|postgres`. Hybrid search (FTS + trigram + vector +
  RRF fusion) stays **behind** the port so backend ranking differences never leak.
  - **Key finding (extends the initial coupling map):** the effective coupling is not
    the 7 constructor call sites but the `store.connect()` escape hatch — ~20 non-test
    sites run raw SQL against the raw `sqlite3.Connection`. Phase 0's real work is
    absorbing the **API-reachable** leaks (`dreaming.py`, `session.py`, `notes.py`,
    `vision.py`, `/readyz`) into named port methods, while SQLite-by-design local
    features (history DB, cochange) stay pinned to `SqliteBackend` explicitly.
- **Recommended backend: PostgreSQL** (+ `pgvector` exact-scan for vectors, generated
  `tsvector`/`ts_rank` for lexical, `pg_trgm` for substring). It is the only candidate
  that *removes* the single-writer constraint rather than relocating it (libSQL/`sqld`
  moves it to a 1-replica StatefulSet). MintMory's Python-side RRF fusion makes lexical
  parity largely a rank-order problem (bounded, golden-set-testable) rather than a
  score-parity problem — with a bounded single-source-path caveat (design §6.1).
- **Phased epic (this change specifies the end-state contract; phases ship separately):**
  Phase 0 extract the port (pure refactor); Phase 1 backend conformance test harness;
  Phase 2 `PostgresBackend`; Phase 3 SQLite→Postgres migration tooling; Phase 4 Helm
  chart HA relaxation + multi-replica validation.

## Impact

- Affected specs: **storage** (new capability — ADDED: pluggable backend port, backend
  selection + SQLite default, hybrid-search-behind-the-port, backend conformance suite,
  Postgres backend, migration tooling, HA chart relaxation).
- Files (future phases, not this change): new `core/ports.py` + `build_storage()`;
  `storage.py` → `SqliteBackend` (+ alias); new `StorageSettings` in `config.py`;
  future `storage_pg.py` + Alembic tree + `mintmory-core[postgres]` extra; conditional
  Helm chart. **No code changes land with this design change.**
- Migrations: none now. Future data migration is an explicit one-shot
  `mintmory migrate-storage` (dual-write rejected — single-writer origin makes a brief
  write-freeze copy trivially safe).
- Out of scope: the history DB and cochange stay SQLite-only local features; a fully
  async storage port (rejected — the port stays sync, the API offloads via a thread).
</content>
</invoke>
