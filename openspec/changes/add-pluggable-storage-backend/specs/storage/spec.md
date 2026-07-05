# Capability: storage (delta)

These requirements define the **end-state contract** of the pluggable storage backend.
They are specified now (design); they are delivered by the phased epic in `tasks.md`,
each phase as its own OpenSpec change. Nothing is implemented by this change.

## ADDED Requirements

### Requirement: Storage backend port
The persistence layer SHALL be reachable through a single `StorageBackend` port
(Protocol) that all application code (REST API, MCP, CLI) depends on instead of the
concrete SQLite adapter. The port SHALL expose the domain operations (memory CRUD,
links, search, sessions, summaries, feedback, stats, index manifest, dreaming
queries) without exposing any backend driver object. Raw driver access (`connect()`,
a driver `transaction()` yielding a live connection, and private helpers) SHALL NOT
be part of the port; code that requires it SHALL depend explicitly on the SQLite
backend instead.

#### Scenario: Application code depends only on the port
- **GIVEN** the REST API, MCP server, and CLI
- **WHEN** they obtain a storage handle
- **THEN** they interact with it only through `StorageBackend` methods, and no module
  outside the SQLite backend (and the explicitly SQLite-only history/cochange local
  features) accesses a raw `sqlite3.Connection` or a private adapter member.

#### Scenario: Readiness uses a port method
- **GIVEN** the API `/readyz` endpoint
- **WHEN** it checks storage health
- **THEN** it calls a `ping()` port method rather than executing raw SQL on a driver
  connection.

### Requirement: Backend selection with SQLite default
The active backend SHALL be selectable via configuration
(`MINTMORY_STORAGE_BACKEND`), defaulting to `sqlite`. When unset or `sqlite`, behaviour
SHALL be byte-for-byte identical to the current single-file SQLite adapter, and the
default install SHALL require no additional dependencies. Non-default backends SHALL
ship as optional extras so the zero-dependency local experience is preserved.

#### Scenario: Default is unchanged SQLite
- **GIVEN** no `MINTMORY_STORAGE_BACKEND` is set
- **WHEN** the CLI, MCP, or API opens storage
- **THEN** a single-file SQLite database is used with the current schema and behaviour,
  and no extra dependency is required to install or run.

#### Scenario: Selecting a backend requires only config
- **GIVEN** the optional backend extra is installed
- **WHEN** `MINTMORY_STORAGE_BACKEND=postgres` and a DSN are provided
- **THEN** the factory constructs the Postgres backend and application code is unchanged.

### Requirement: Hybrid search behind the port
Hybrid search SHALL be encapsulated behind the port — lexical full-text,
substring/trigram, vector similarity, and their RRF fusion — so that backend-specific
ranking mechanisms do not leak to callers. The fusion, normalisation, filtering, note
auto-include, and session-recording policy SHALL be backend-independent; a backend
SHALL implement only its own lexical, substring, and vector score sources.

#### Scenario: Callers see backend-independent search
- **GIVEN** two backends implementing different lexical/vector engines
- **WHEN** a caller invokes `search()` with the same request
- **THEN** the caller receives the same shape of result through identical fusion and
  scoring policy, with only bounded, backend-specific relevance-ordering differences.

### Requirement: Backend conformance suite
A backend-agnostic conformance test suite SHALL define the port's behavioural semantics
and SHALL be runnable against any backend. It SHALL pass against SQLite before any
non-SQLite backend implementation exists, and SHALL include a thresholded golden-set
retrieval test (recall@K against the SQLite baseline) rather than exact-score
assertions.

#### Scenario: Conformance defines semantics before a second backend
- **GIVEN** only the SQLite backend exists
- **WHEN** the conformance suite runs
- **THEN** it passes on SQLite, and a later backend is considered correct only when it
  passes the same suite (behavioural invariants MUST-pass; capability-gated features
  such as substring or vector search declared explicitly).

### Requirement: PostgreSQL high-availability backend
A PostgreSQL backend SHALL be provided that supports multiple concurrent writers so the
REST API can run as N stateless replicas. It SHALL reproduce the conformance suite's
behaviour using a vector-similarity index (exact scan, semantics-equivalent to today;
approximate ANN indexing optional and separately validated), a full-text index for
lexical search, and a substring index — the specific Postgres extensions are a Phase 2
decision (see design §8), not fixed by this contract. Schema changes SHALL be applied by
a real migration tool at deploy time (not per-replica at startup), and read-modify-write
operations SHALL be concurrency-safe against lost updates.

#### Scenario: Multiple API replicas share one Postgres
- **GIVEN** `MINTMORY_STORAGE_BACKEND=postgres` and several API replicas
- **WHEN** they concurrently add, update, and search memories
- **THEN** all operations succeed with no data-integrity errors, and schema migrations
  are applied once at deploy time rather than raced by each replica at startup.

#### Scenario: Readiness degrades safely on database outage
- **GIVEN** the Postgres backend
- **WHEN** the database is temporarily unreachable
- **THEN** `/readyz` reports not-ready (503) without crash-looping the pod, and recovers
  when the database returns.

### Requirement: Storage migration tooling
A one-shot migration command SHALL copy an existing SQLite database into a target
backend with type conversion and verification, without requiring dual-write. It SHALL
report per-table row counts and content checksums and support a dry run.

#### Scenario: SQLite database migrates to Postgres with verification
- **GIVEN** an existing SQLite `memories.db`
- **WHEN** `mintmory migrate-storage --from sqlite:PATH --to postgres:DSN` runs
- **THEN** all tables are copied in referential order with correct type conversions,
  row counts and checksums are reported, and re-running detects an already-migrated
  target rather than duplicating data.

### Requirement: HA-capable Helm deployment for external backends
When configured for an external multi-writer backend, the Helm chart SHALL relax the
SQLite single-writer constraints — allowing more than one replica, `RollingUpdate`, and
no persistent volume — while retaining all single-writer constraints when the backend is
SQLite. The chart SHALL default to a bring-your-own database DSN held in a Secret and
SHALL run schema migrations as a deploy-time job rather than in application startup.

#### Scenario: Postgres mode enables multi-replica rolling updates
- **GIVEN** the chart with `storage.backend: postgres` and a DSN secret
- **WHEN** it is templated and deployed
- **THEN** it permits `replicaCount` greater than 1 with a `RollingUpdate` strategy and
  no ReadWriteOnce PVC; and with `storage.backend: sqlite` the single-writer guardrails
  (replicas 1, `Recreate`, RWO PVC) remain enforced.
</content>
