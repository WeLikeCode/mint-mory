# Design: Pluggable storage backend for real HA

**Status:** Design only — no code changes land with this change. It feeds a phased epic.
**Scope:** `packages/core` storage layer, the REST API deployable, the Helm chart HA posture.
**Non-goals:** Implementing any backend now; changing the MCP/CLI local-first experience;
touching the history-DB semantics.

## 1. Motivation & goal

MintMory's only persistence layer is a single SQLite file opened by `StorageAdapter`
(`packages/core/src/mintmory/core/storage.py:172`) with one cached `sqlite3.Connection`
(`storage.py:212-223`, `check_same_thread=False`, WAL, `busy_timeout`). Great zero-dependency
local default — and it hard-locks the K8s deployment into a single-writer topology the shipped
chart enforces structurally:

- `replicaCount` schema-capped at **1** (`deploy/helm/mintmory/values.schema.json`; `values.yaml`)
- `strategy: Recreate` — never RollingUpdate (`deploy/helm/mintmory/templates/deployment.yaml`)
- `persistence.accessMode` pinned to `ReadWriteOnce` block storage
- 1 uvicorn worker; in-cluster backup CronJob impossible (RWO PVC can't be co-mounted)

**Goal:** make the *storage backend* pluggable behind a port so the REST API (`packages/api`)
can run N stateless replicas against an external database with real HA (RollingUpdate, no PVC,
HPA-capable), while: (1) SQLite stays the **default** — CLI/MCP/single-pod unchanged; (2) hybrid
search stays **behind** the port so backend ranking differences never leak; (3) the decomposition
has a Phase 0 pure refactor safe to build immediately.

## 2. Coupling inventory (authoritative)

### 2.1 The de-facto port: `StorageAdapter`'s public surface

~32 public methods (lifecycle `connect/close/transaction/initialise`; memory CRUD; index
manifest; feedback; search + `search_around` + notes lookups; links; sessions; summaries;
stats/dreaming). Two signature problems for a port:

- **`manifest_get` returns `sqlite3.Row`** (`storage.py:612-619`) — a SQLite type in the public
  signature. Becomes a dict/dataclass (`ManifestEntry`); callers use `row["key"]` so it is
  behaviour-preserving.
- **`transaction()` yields a raw `sqlite3.Connection`** (`storage.py:242-250`) — used by
  `core/session.py` for raw UPDATEs. The port cannot yield a driver connection.

### 2.2 ⚠️ Key finding — the `connect()` escape hatch (extends the coupling map)

The 7 constructor call sites understate the coupling. **`store.connect()` returns the raw
`sqlite3.Connection`, and ~20 non-test sites run raw SQL against it.** The effective port is not
the public methods — raw SQL leaks around them.

**Reachable from the REST API (MUST go behind the port):**

| Site | What it does | Hazard |
|---|---|---|
| `core/dreaming.py` (7+ raw SELECTs) | dream-step queries over `memories`/`concept_links` (via `POST /dream`, `GET /summaries/jobs`) | plain SQL, portable |
| `core/session.py` (raw UPDATEs in `transaction()`) | `query_sessions`/`query_results` writes (via `POST /sessions/{id}/feedback`) | INTEGER bools |
| `core/notes.py` | calls private `adapter._anchor_candidates()` (via `POST /notes`) | hybrid-search internals |
| `core/vision.py` | raw SELECT with `json_extract(...)` + private row mapper (via `GET /images/jobs`) | `json_extract`, private helper |
| `api/app.py` | `get_store().connect().execute("SELECT 1")` in `/readyz` | needs `ping()` port method |
| `cli/main.py:417` | private `store._vector_search_available()` (doctor/status) | private attr |

**CLI commands that run raw SQL on the primary store — must be resolved in Phase 0.** The
`ingest` command (`cli/main.py:314`) does `store.connect().execute("SELECT 1 FROM memories WHERE
content = ?")` for dedup on the *primary* store (not the history store). Since §5.3 routes the CLI's
primary store through `build_storage()`, a user with `MINTMORY_STORAGE_BACKEND=postgres` would break
`ingest` (the port deliberately excludes `connect()`). Phase 0 MUST either (a) absorb the dedup into
a port method (`memory_exists_with_content(content) -> bool`) — preferred, it is trivially portable —
or (b) pin `ingest` (and any other primary-store raw-SQL CLI command) explicitly to `SqliteBackend`.
`cli/main.py:1617` (`redact-scan`) is fine — it goes through the history store, already
SQLite-pinned.

**SQLite-pinned by design (stay on a `SqliteBackend`-only surface, NOT in the port):** the
history DB (`history/ingest.py`, `history/query.py`, `mcp/history_server.py`) with the Hermes
guard, and cochange (`core/cochange.py`, incl. `ORDER BY rowid DESC`). Both are local CLI/MCP
features with no HA requirement and are not routed in `api/app.py`.

### 2.3 SQLite-specific surfaces, by porting difficulty

| # | Surface | Difficulty | Postgres replacement | libSQL |
|---|---|---|---|---|
| 1 | External-content FTS5 `memories_fts` (`porter unicode61`), trigger-sync, `bm25()`, `rowid` joins | **High** | generated `tsvector` + GIN + `ts_rank`/`websearch_to_tsquery` (semantics differ, §6.1) | native FTS5 |
| 2 | Standalone trigram FTS5, runtime create/backfill | **High** | `pg_trgm` (`similarity`, `gin_trgm_ops`) | native |
| 3 | sqlite-vec `vec_distance_cosine` brute-force over float32 BLOB; mixed-dim → NULL skipped | **Medium** | `pgvector` `<=>` cosine; HNSW later | native vec / ext |
| 4 | Weighted RRF fusion + min-max normalise in Python | **None** | unchanged (why parity is soft, §6.1) | unchanged |
| 5 | Graph BFS in Python over `concept_links` | **None** | unchanged | unchanged |
| 6 | `json_extract(metadata,'$.x')` | **Low** | JSONB `->>`  (an upgrade) | unchanged |
| 7 | `INSERT OR IGNORE/REPLACE`, `ON CONFLICT DO UPDATE` | **Low** | `ON CONFLICT` variants | unchanged |
| 8 | INTEGER bools, TEXT ISO-8601 ts, TEXT JSON arrays | **Low** | native bool/timestamptz/jsonb (ordering note §6.5) | unchanged |
| 9 | PRAGMAs `foreign_keys/journal_mode/busy_timeout` (locked by `test_schema.py`) | **Low** | pool config replaces busy_timeout | mostly honored |
| 10 | Runtime Python migrations (`_ensure_*`) via PRAGMA + try/except | **Medium** | Alembic (§6.4) | same pattern |
| 11 | `executescript(schema.sql)` per-startup DDL | **Medium** | deploy-time migration (N-replica DDL race) | works |
| 12 | Single cached conn, `check_same_thread=False`, `:memory:` default, implicit autocommit | **Medium** | pool + explicit tx (§6.3) | ≈ sqlite3 client |
| 13 | Partial indexes | **None** | native | identical |
| 14 | CHECK/enum constraints locked to `types.py` by tests | **Low** | identical CHECKs | identical |
| 15 | `sqlite3.Row` in signature; `transaction()` yields driver conn | **Low** (Phase 0) | dict + unit-of-work | same |
| 16 | `ORDER BY rowid DESC` (`cochange.py`) | **Low** (SQLite-pinned anyway) | explicit ordering column | identical |
| 17 | The `connect()` escape hatch (~20 sites, §2.2) | **High organizationally** | absorb into named methods | — |

### 2.4 What the tests lock

- `test_schema.py` asserts SQLite artifacts by `sqlite_master`/`PRAGMA` introspection, FK/CHECK
  enforcement, WAL, migration backfill → inherently backend-specific; stays the SQLite conformance
  leg; a `test_schema_pg.py` twin asserts via `information_schema`.
- `test_storage.py` (~35 tests): behavioural invariants (round-trip fidelity of all columns,
  entity re-extraction, feedback increment/cap/threshold, note-flagging exception, embed
  discipline) — backend-agnostic seed of the conformance suite.
- `test_search.py` (~35 tests): retrieval *behavior* not scores (prefix/compound/substring
  matching, filtering, search-around semantics, note auto-include, mixed-dim embedding survival,
  RRF weight effects) — the golden behaviors a second backend must reproduce.

### 2.5 How the store is created/shared

- **API** (`api/app.py`): module-level `_store` global in `lifespan`, **no embedder** (API-added
  memories get NULL embeddings — asymmetry vs CLI); all routes `async def` calling blocking
  sqlite3 on the event loop.
- **MCP** (`mcp/server.py`): lazy module-level `_store`.
- **CLI** (`cli/main.py`): fresh adapter per command, **with** embedder.
- **History**: dedicated-DB open helpers with the Hermes guard.
- Config precedent: per-group `pydantic-settings` with `MINTMORY_<GROUP>_` prefixes → a
  `StorageSettings` group slots in. `MINTMORY_DB` and `MINTMORY_SQLITE_BUSY_TIMEOUT_MS` are read
  via raw `os.environ` today; Phase 0 folds them into the group (keeping the env names).

## 3. Candidate backends — feasibility

### 3.1 libSQL / Turso (`sqld`)
Near-zero dialect distance (FTS5 + triggers + `bm25()` work; native vectors or sqlite-vec). **But
no multi-writer story:** single-primary + read replicas + write-forwarding. The K8s single-writer
constraint is not removed — it is **relocated** to a `sqld` StatefulSet (1 replica, RWO PVC, no
OSS automated failover). Rolling updates of the API become possible (real win), the write path
stays a SPOF. Cheapest port (days), delivers **half-HA**.

### 3.2 PostgreSQL (+ pgvector, tsvector, pg_trgm) — **recommended**
- Lexical: generated `tsvector` column + GIN + `websearch_to_tsquery`/`ts_rank_cd`; prefix via
  `tsquery :*`. Not BM25 — but fusion consumes only rank-order per source then min-max normalises,
  so absolute-score parity is irrelevant (§6.1). No triggers (generated column removes surface #1's
  trigger apparatus).
- Substring: `pg_trgm` + `gin_trgm_ops` (bundled contrib, zero extra ops).
- Vector: `pgvector` `vector(d)` + `<=>`. **Exact scan = identical semantics to today;** HNSW is a
  later pure-perf upgrade.
- Multi-writer / HA: the only candidate with true app-tier multi-writer and mature HA (CloudNativePG
  operator or managed PG).
- Dialect distance: a real second dialect, but §2.3 shows most is Low; the High items (#1,#2) are
  contained in 3 already-isolated private methods (`_fts_scores`/`_trigram_scores`/`_vector_scores`).

### 3.3 Why not others (one line each)
- **MySQL:** weaker FTS relevance, fragmented vectors, no advantage over PG.
- **Dedicated vector DB (Qdrant/Weaviate):** solves 1 of 17 surfaces; leaves the relational graph
  needing a SQL store → two stateful systems + a consistency seam through hybrid search.
- **LiteFS:** single-writer + FUSE + Consul; Fly.io-optimized, not vanilla K8s.
- **rqlite:** Raft through one leader (still single-writer); SQL-over-HTTP breaks the sqlite3 driver
  assumption; limited extensions.
- **Turso Cloud (SaaS):** real failover, but a hard external dependency contradicting MintMory's
  "offline by default" philosophy.

### 3.4 Comparison

| Criterion | SQLite (today) | libSQL/sqld | **PostgreSQL** |
|---|---|---|---|
| Multi-writer app replicas | ✗ | ✗ (forward to 1 primary) | **✓** |
| API RollingUpdate | ✗ | ✓ | **✓** |
| FTS parity | baseline | ≈100% | ~85% behavioral (rank-order, golden-set-verifiable) |
| Vector parity | baseline | high (ext caveat) | **exact scan = parity; HNSW = upgrade** |
| HA maturity | n/a | low (OSS) / SaaS | **very high (CNPG/managed)** |
| Port cost | — | ~0 (days) | real (weeks), contained to 3 methods + mechanical upserts |
| Ops added | none | niche DB StatefulSet+PVC | Postgres (boring, operator-managed) |
| Removes single-writer PVC | ✗ | partially (moves it) | **✓ (API stateless)** |

## 4. What "real HA" requires — and which chart invariants relax

With external Postgres (`MINTMORY_STORAGE_BACKEND=postgres`):

| Chart invariant | Today | Postgres mode | SQLite mode |
|---|---|---|---|
| `replicaCount` max 1 | hard cap | **relaxed** — N replicas, HPA (schema becomes conditional on backend) | stays 1 |
| `strategy: Recreate` | forced | **RollingUpdate** (maxUnavailable 0) | stays |
| PVC RWO block | required | **no PVC** — `persistence.enabled=false` | stays |
| 1 uvicorn worker | required | multiple allowed | stays |
| `/readyz` = `SELECT 1` on file | trivial | real readiness gate (pool → PG reachability, timeout so a blip flips readiness not liveness) | stays |
| in-cluster backup impossible | true | moot — PG-native backups | stays |
| PDB / anti-affinity | pointless at 1 | **add** (HA hygiene) | n/a |

**Does NOT relax / new obligations:** statefulness moves, not vanishes (PG needs its own HA — chart
defaults to **BYO DSN** secret-ref, optionally documents CNPG, never vendors a StatefulSet PG);
**DDL races** — N replicas can't each run `initialise()` at startup → deploy-time migration Job with
a lock; **concurrency** — read-modify-write in `apply_feedback`/`update_memory` was implicitly
serialized by the single writer and becomes genuinely concurrent (§6.3). If libSQL were chosen, the
API constraints relax but a new `sqld` StatefulSet inherits `replicas:1`+RWO+Recreate — the
constraint is *relocated*, the decisive argument for PG.

## 5. Architecture: the `StorageBackend` port

### 5.1 The Protocol
New `packages/core/src/mintmory/core/ports.py`, a `@runtime_checkable` `StorageBackend` Protocol
(structural — `SqliteBackend` needs no inheritance, mocks stay cheap): lifecycle
(`initialise/close/ping` — `ping` NEW, replaces `/readyz`'s `connect().execute("SELECT 1")`); the 28
domain methods with unchanged signatures except `manifest_get` → `ManifestEntry`; plus NEW methods
absorbing the §2.2 API-reachable leaks: the ~5 dreaming query shapes, session write methods
mirroring `session.py`'s current statements, `anchor_candidates` (promotes `_anchor_candidates`),
`list_image_file_records` (vision), `vector_search_available`.

**Phase 0 preserves today's transaction boundaries verbatim — it does NOT make session-conclude
atomic.** Today's conclude is deliberately non-atomic: `session.apply_feedback` runs each
per-memory `apply_feedback` in its own transaction, then a *separate* `transaction()` updates
`query_sessions`/`query_results`. Folding these into one atomic `conclude_session_with_feedback`
would change partial-failure/rollback semantics — a behaviour change that violates Phase 0's
"byte-identical" contract. The port therefore exposes the write operations at the SAME boundaries;
making conclude atomic is deferred to **Phase 2** (where multi-writer concurrency makes it both
necessary and testable).

**Deliberately excluded from the port:** `connect()` and `transaction()` — SQLite implementation
details that stay on `SqliteBackend` only, so history/cochange/CLI local code keeps working and is
typed against `SqliteBackend` explicitly (documenting them as local-only).

**Hybrid search stays behind `search()`:** `_sanitise_fts_query`/`_trigram_match_expr` stay private
to `SqliteBackend`; `scoring.rrf_merge`, min-max normalisation, `effective_score`, filtering, note
auto-include, session recording are backend-independent policy → shared (a `HybridSearchMixin`/free
function taking the three score dicts) so a new backend implements only the three score methods and
inherits identical fusion.

### 5.2 Factory + config
`StorageSettings(BaseSettings, env_prefix="MINTMORY_STORAGE_")`: `backend` enum (sqlite default,
postgres), sqlite `db_path` (falls back to `MINTMORY_DB` then `~/.mintmory/memories.db`),
`busy_timeout_ms` (absorbs `MINTMORY_SQLITE_BUSY_TIMEOUT_MS`, alias kept), postgres `dsn`,
`pool_min/pool_max`. `build_storage(settings, *, embedder) -> StorageBackend` dispatches; Postgres
imports lazily (`mintmory-core[postgres]` optional extra → `psycopg[binary,pool]`, `pgvector`),
preserving the zero-dependency default install.

### 5.3 The 7 call sites after the refactor
API/MCP/CLI portable sites → `build_storage(...)`; the 3 history sites → `SqliteBackend(...)`
**explicitly** (SQLite-by-design: Hermes guard, `0o600`, file semantics); keep
`StorageAdapter = SqliteBackend` alias for one release. The API's no-embedder / CLI-embedder
asymmetry becomes explicit + configurable; preserving it exactly is part of Phase 0's contract.

## 6. Hard problems & mitigations

- **6.1 FTS ranking parity** (`ts_rank` ≠ `bm25`, Snowball ≠ porter, prefix/compound logic → tsquery
  `:*`). Smaller than it looks: in the **multi-source** path fusion is weighted RRF (rank-order
  only — `scoring.rrf_merge` consumes only `sorted()` rank) then min-max normalised, so parity means
  "similar top-K per source," not score equality. **One caveat:** `search()` bypasses RRF when only a
  single source returns hits (`storage.py:852-853`), feeding that source's *raw* bm25/cosine/trigram
  scores through the order-preserving min-max (`storage.py:864-870`) into `effective_score`, where
  relevance *spacing* — not just rank — competes additively against `usefulness*0.3 + recency`. So a
  PG backend's `ts_rank` distribution *shape* can shift final tie-breaks in the one-source case. The
  precise claim is "rank-order in the multi-source path; single-source relies on order-preserving
  normalisation with bounded, golden-set-covered residual spacing effects." Mitigation: accept
  bounded drift in the spec; a **golden-set search test** (~100 memories, "query Q returns M in top
  K", thresholded e.g. recall@5 ≥ 0.9 vs SQLite); keep every capability test from `test_search.py` as
  MUST-pass.
- **6.2 Vector parity + ANN.** Phase 2 ships **exact scan only** = identical semantics at MintMory's
  scale; HNSW later with its own recall test. Mixed-dimension embeddings (SQLite skips NULL
  distances, locked by `test_search.py`): enforce fixed dim per DB in PG (cleaner) OR untyped
  `vector` column — **human decision** (§8).
- **6.3 Transactions / isolation / pooling / event loop.** Read-modify-write races
  (`apply_feedback`, `update_memory`) become real → rewrite hot mutators as atomic SQL
  (`SET x = LEAST(10, x + $1)`) or `SELECT ... FOR UPDATE`. **Atomic `apply_feedback` is not
  sufficient on its own:** `update_memory` (`storage.py:518-596`) reads the full record and writes
  back *all* columns — including `usefulness_score`, `staleness_score`, `reinforcement_count`, and
  `retrieval_count`. Under multi-writer it would clobber a concurrent atomic increment from
  `apply_feedback` OR from `record_query_results`' retrieval bump (`storage.py:1190`, already
  atomic). So Phase 2 must ALSO narrow `update_memory`'s UPDATE to the caller-supplied columns (or
  at minimum exclude the counter columns from its write set); otherwise the atomicity of the
  counters is undermined. The remaining content/metadata fields stay last-writer-wins (already true
  across processes sharing one SQLite file). Port stays **sync** (keeps SQLite trivial) — this also
  sidesteps the shared-single-`sqlite3.Connection`-across-threads hazard; the API offloads to a
  thread only in Postgres mode (SQLite's local calls are fast enough to stay inline) via
  `anyio.to_thread` in Phase 2. A fully-async port is rejected (would asyncify core + CLI for no
  SQLite benefit). **Pool sizing:** the anyio thread-limiter (default 40) must be aligned with
  `pool_max` × uvicorn workers so offloaded calls never starve threads or exhaust the pool (a Phase 2
  config guard).
- **6.4 Migrations.** `executescript(schema.sql)` + 3 try/except Python migrations is unacceptable
  for PG. **Alembic for Postgres only;** SQLite keeps its self-healing mechanism (load-bearing for
  local UX). PG migrations run as a Helm pre-install/upgrade hook Job (or init container with
  `pg_advisory_lock`), never in `initialise()`.
- **6.5 Data migration from an existing SQLite file.** One-shot
  `mintmory migrate-storage --from sqlite:PATH --to postgres:DSN`: stream in FK order, convert
  bools/timestamps/json/embeddings, verify with row counts + checksums; tsvector regenerates
  automatically. **Dual-write rejected** — single-writer origin makes a brief write-freeze copy
  trivially safe. Note: TEXT timestamps compare lexicographically today; ISO-8601 makes that ≡
  temporal so timestamptz agrees — conformance still pins boundary cases (naive-UTC `_utcnow`).
- **6.6 Backend conformance suite.** Parametrize the storage-behavior tests over a `backend` fixture
  (`sqlite` always; `postgres` when `MINTMORY_TEST_PG_DSN` set — CI `postgres:16`+pgvector service
  container; locally auto-skips). Backend-specific legs stay separate. **Must be green on SQLite
  alone before any Phase 2 code exists** — it defines the port's semantics executably.
- **6.7 Residual.** `get_stats` top-concepts Python counting — port as-is, don't "improve" in SQL.
  Trigram availability degradation has no PG analogue (contract: "substring search best-effort").
  `GET /images/jobs?include_bytes=true` needs on-pod files — a pre-existing limitation to list in
  the Phase 4 validation checklist, not worsened. **Observability:** a networked backend adds new
  failure/latency surface (DB-call latency, pool saturation, transient outages) absent for a local
  file — Phase 2 should hang spans/metrics on the existing `telemetry.traced` shim for DB calls +
  pool stats, so a slow/failing PG is diagnosable.

## 7. Phased decomposition (the epic)

- **Phase 0 — Extract the port + `build_storage()` (PURE REFACTOR).** *Implement first.* Absorb the
  API-reachable raw-SQL/private leaks into named methods (verbatim SQL relocation); `manifest_get` →
  `ManifestEntry`; define `StorageBackend`, rename `StorageAdapter` → `SqliteBackend` (+ alias);
  `connect()`/`transaction()` stay SQLite-only; `StorageSettings` + factory; swap portable call
  sites, pin history sites. **Exit:** all existing tests pass with mechanical edits only; mypy/ruff
  clean; grep proves no module outside storage/history/cochange/CLI touches `.connect()` or `_`
  members; API/MCP/CLI byte-identical. **Risk: Low** (pure motion; copy-verbatim rule guards the
  dreaming/session SQL).
- **Phase 1 — Backend conformance test harness.** Parametrized `backend` fixture; extract
  backend-agnostic tests; golden-set retrieval corpus + thresholded recall; CI matrix (sqlite always;
  PG container wired, allowed-empty until Phase 2). **Exit:** conformance green on SQLite; documented
  MUST-vs-capability matrix. **Risk: Low.**
- **Phase 2 — `PostgresBackend`.** `[postgres]` extra; Alembic initial schema (jsonb, boolean,
  timestamptz, generated tsvector + GIN, pg_trgm, `vector` column, same CHECKs + partial indexes);
  the three score methods (tsquery/similarity/`<=>` exact scan); shared fusion; atomic
  `apply_feedback`; API `to_thread` offload. **Exit:** conformance + golden set green on PG in CI;
  `/readyz` survives PG outage (503, no crash-loop); soak: 2 API processes + 1 PG under concurrent
  writes, zero integrity errors. **Risk: Medium-High.**
- **Phase 3 — Migration tooling.** `mintmory migrate-storage` streaming copy + type conversion +
  dimension-policy enforcement + row-count/checksum report + `--dry-run`; K8s runbook. **Exit:**
  round-trip test (migrate fixture, run read-suite on PG, diff vs SQLite); idempotent re-run
  detection. **Risk: Low-Medium.**
- **Phase 4 — Helm chart HA relaxation + validation.** `storage.backend` + DSN secret-ref;
  conditional schema (sqlite → today's constraints; postgres → replicaCount N, RollingUpdate,
  `persistence.enabled:false`); migration Job hook; PDB + anti-affinity; CNPG BYO docs; validation:
  3 replicas under k6 load through a rolling update (zero 5xx), kill-a-pod, PG failover with CNPG.
  **Exit:** documented green validation run on a real cluster; README single-writer section becomes
  mode-conditional. **Risk: Medium.**

Only 0→1→2 are strictly ordered; 3 and 4 depend on 2 but not each other.

## 8. Recommendation & open questions

**Recommended: PostgreSQL** (+ pgvector exact-scan, tsvector, pg_trgm) — the only candidate that
removes rather than relocates the single-writer constraint; RRF fusion makes lexical parity bounded
and testable; exact-scan pgvector gives semantics-identical vector search with an ANN upgrade path.
libSQL is the fallback if the requirement is ever softened to "rolling updates + read scaling."

**Decisions a human must make before Phase 2:**

1. **DB access layer:** raw psycopg3 + hand-written SQL (mirrors today, minimal deps) vs SQLAlchemy
   Core. Recommendation: psycopg3 + standalone Alembic.
2. **PG FTS engine:** built-in tsvector/ts_rank (zero extra deps, ~85% parity) vs ParadeDB `pg_search`
   (true BM25, non-contrib, constrains managed-PG). Recommendation: built-in; revisit only if the
   golden set fails.
3. **Embedding-dimension policy:** enforce fixed dim per DB (`vector(512)`) vs replicate SQLite's
   mixed-dim tolerance. Recommendation: enforce fixed — changes `test_search.py`'s mixed-dim contract
   for PG, needs an explicit spec call.
4. **History/cochange scope:** confirm they stay `SqliteBackend`-pinned (this design assumes yes).
5. **Chart posture for PG:** BYO DSN only vs optional CNPG vs recipe-only. Recommendation: BYO DSN +
   documented CNPG recipe; never vendor a StatefulSet PG.
6. **Auth:** confirm edge-auth-only remains the policy with N shared-DB replicas.
</content>
