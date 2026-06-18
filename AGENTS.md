# MintMory — Agent Guide

Read this file in full before touching any code. It exists so that parallel
Claude agents can work on MintMory without corrupting each other's invariants.

---

## 1. Project Overview

MintMory is a **typed memory system for LLM agents**, modelled after the
Palantir Foundry Ontology layer. The core insight from Palantir's design is
that data is most useful when typed, linked, and queryable — not stored as raw
blobs. MintMory applies that to agent working memory:

| Palantir concept | MintMory equivalent |
|---|---|
| Object type | `MemoryCategory` (8 values) |
| Object instance | `MemoryRecord` |
| Link type | `ConceptLinkType` (11 values) |
| Object-backed link | `ConceptLink` |
| Decision lineage | `QuerySession` + `QueryResult` |
| Action type | MCP tool / API endpoint / CLI command |
| ObjectSet filter | `MemoryFilter` + `SearchAroundSpec` |

### Three transports, one domain model

All three transports call the same `packages/core` functions. Nothing is
duplicated:

- **stdio** — `mintmory-cli` (Typer). Direct human-in-the-loop or scripting.
- **MCP** — `mintmory-mcp` (fastmcp). Used by Claude Code, Cursor, Open WebUI.
  Supports stdio and SSE sub-transports.
- **HTTP REST** — `mintmory-api` (FastAPI). Used by external services,
  dashboards, webhook receivers.

### Storage

SQLite + `sqlite-vec` + FTS5. No external vector DB, no Redis, no Postgres.
A single `.db` file on disk contains every table. WAL mode allows concurrent
reads during a dreaming run.

### Passive feedback loop

Every `SearchRequest` creates a `QuerySession`. When the session concludes,
the LLM submits a `QueryFeedback` (listing useful and stale memory IDs). The
feedback is applied to `usefulness_score` and `staleness_score` columns on
`MemoryRecord`. No human is needed.

### Dreaming

A background process that consolidates memory while the agent is idle:

- **Light**: anomaly detection → concept linking → summary generation
- **Full**: light + contradiction resolution + archival + rehabilitation

All dreaming steps are idempotent (see §4 invariants).

---

## 2. Monorepo Structure

```
MintMory/
├── pyproject.toml              # workspace root — dev deps, pytest config, ruff, mypy
├── packages/
│   ├── core/                   # mintmory-core — the only package with domain logic
│   │   ├── src/mintmory/core/
│   │   │   ├── types.py        # Pydantic models + enums — THE source of truth
│   │   │   ├── schema.sql      # DDL derived from types.py
│   │   │   ├── storage.py      # StorageAdapter (SQLite CRUD, FTS, vector search)
│   │   │   ├── embedder.py     # EmbedderProtocol + local/OpenAI implementations
│   │   │   ├── entity.py       # Regex entity extraction
│   │   │   ├── scoring.py      # effective_score calculation, staleness updates
│   │   │   ├── dreaming.py     # DreamingEngine (light + full cycle)
│   │   │   └── session.py      # QuerySession lifecycle + feedback application
│   │   └── tests/
│   │       ├── test_schema.py  # DDL compliance — MUST always pass
│   │       ├── test_storage.py # CRUD, FTS, vector search
│   │       ├── test_scoring.py # effective_score formula
│   │       ├── test_dreaming.py # idempotency, step ordering
│   │       └── test_session.py # feedback loop
│   ├── mcp/                    # mintmory-mcp — fastmcp server
│   │   ├── src/mintmory/mcp/
│   │   │   ├── server.py       # FastMCP instance, tool registrations
│   │   │   └── tools.py        # @mcp.tool() wrappers calling core
│   │   └── tests/
│   │       └── test_tools.py   # tool input/output shapes
│   ├── api/                    # mintmory-api — FastAPI REST server
│   │   ├── src/mintmory/api/
│   │   │   ├── main.py         # FastAPI app, lifespan, route mounts
│   │   │   ├── routes/         # one file per resource group
│   │   │   └── schemas.py      # request/response Pydantic adapters (thin)
│   │   └── tests/
│   │       └── test_routes.py  # httpx TestClient, spec conformance
│   └── cli/                    # mintmory-cli — Typer commands
│       ├── src/mintmory/cli/
│       │   └── main.py
│       └── tests/
│           └── test_cli.py
├── tests/integration/          # cross-package: real SQLite file, canned LLM responses
├── docs/
│   ├── architecture/           # ADRs
│   ├── research/               # FEATURES.md (living spec), TYPED_SCHEMA.md, etc.
│   └── openapi/
│       └── mintmory.yaml       # OpenAPI 3.1 spec — derived from types.py
└── scripts/                    # dev tooling: seed_db.py, run_dreamd.py, benchmark.py
```

### What to touch for each type of change

| Change type | Files to touch |
|---|---|
| Add a new field to `MemoryRecord` | `types.py` → `schema.sql` → `openapi/mintmory.yaml` |
| Add a new `ConceptLinkType` | `types.py` (enum) → `schema.sql` (CHECK constraint) → `openapi/mintmory.yaml` |
| Add a new MCP tool | `packages/mcp/src/mintmory/mcp/tools.py` + test |
| Add a new API route | `packages/api/src/mintmory/api/routes/` + test |
| Change scoring formula | `packages/core/src/mintmory/core/scoring.py` + `FEATURES.md` |
| Change dreaming step | `packages/core/src/mintmory/core/dreaming.py` + idempotency test |
| Change contradiction prompt | `types.py` (ConflictCheckResult) + `FEATURES.md` |

---

## 3. Source of Truth Hierarchy

When `types.py`, `schema.sql`, and `openapi/mintmory.yaml` disagree, this is
the resolution order:

```
types.py  >  schema.sql  >  openapi/mintmory.yaml
```

**Never modify `schema.sql` or `openapi.yaml` to fix a conflict without first
updating `types.py`.** The schema compliance tests enforce this: they load
`types.py` enums and assert that every CHECK constraint value in `schema.sql`
matches the corresponding Python enum member.

Practical implications:
- If you add `OBSERVED = "observed"` to `MemoryCategory`, the next step is to
  add `'observed'` to the `schema.sql` CHECK constraint, then add it to the
  OpenAPI enum. Do them in that order.
- If `openapi.yaml` omits a field that exists in `types.py`, the spec is wrong
  — fix the spec, not the Pydantic model.

---

## 4. Key Invariants

These must never be violated. Each has a test that guards it.

### 4.1 Contradiction detection prompt schema

`CONTRADICTION_DETECTION_PROMPT` expects the LLM to return JSON matching
`ConflictCheckResult`:

```python
# CORRECT (widemem audit finding — verified in types.py)
class ConflictDetail(BaseModel):
    new_fact: str
    existing_memory_id: str
    existing_content: str
    type: Literal["contradiction", "ambiguity"]
    question: Optional[str] = None  # only for ambiguity

class ConflictCheckResult(BaseModel):
    has_conflict: bool
    conflicts: list[ConflictDetail]
```

**WRONG field names that must never appear in any prompt or code:**
- `is_contradiction` (wrong — use `has_conflict`)
- `contradicts_memory_ids` (wrong — use `conflicts[].existing_memory_id`)

These wrong names came from an early research draft (FEATURES.md v0). They are
corrected in `types.py` and in `docs/research/FEATURES.md`. Any code that uses
the wrong names is a bug.

### 4.2 ConceptLinkType is a closed enum

The 11 link types in `ConceptLinkType` are the complete set:

```
relates_to, contradicts, refines, supersedes, enables,
depends_on, similar_to, part_of, uses, before, valid_until
```

Adding a new link type requires:
1. Adding the member to `ConceptLinkType` in `types.py`
2. Adding the string value to the `link_type CHECK` constraint in `schema.sql`
3. Adding it to the `link_type` enum in `openapi/mintmory.yaml`
4. Running `test_schema.py` to confirm the three stay in sync

Partial updates (e.g., adding to Python but not SQL) will cause FK violations
at runtime and CHECK constraint failures in the schema compliance tests.

### 4.3 Score caps

`usefulness_score` and `staleness_score` are always in `[0.0, 10.0]`.

- The `MemoryRecord` Pydantic model enforces `ge=0.0, le=10.0`.
- The SQL schema enforces `CHECK (usefulness_score >= 0.0 AND usefulness_score <= 10.0)`.
- Any update path (QueryFeedback, dreaming rehabilitation) must clamp before
  writing. Use `min(score, 10.0)` and `max(score, 0.0)` — never write a
  raw LLM-returned float without clamping.

### 4.4 Dreaming idempotency

Running the dreaming engine twice on the same database must produce the same
result. This means:

- Step 1 (anomaly detection): pure read, no writes.
- Step 2 (concept linking): use `INSERT OR IGNORE` (the UNIQUE constraint on
  `(source_memory_id, target_memory_id, link_type)` handles deduplication).
- Step 3 (summary generation): update existing row if `concept` matches
  (`INSERT OR REPLACE` on the UNIQUE `concept` column).
- Step 4 (contradiction resolution, full only): resolving an already-resolved
  contradiction is a no-op — check `flagged_for_review = 0` before acting.
- Step 5 (archival): archiving an already-archived memory is a no-op —
  check `is_archived = 0` before acting.
- Step 6 (rehabilitation): rehabilitating an already-active memory is a
  no-op — check `is_stale = 1` before acting.

The idempotency test in `test_dreaming.py` runs the full dream twice and
asserts `DreamReport` fields are identical on the second run.

### 4.5 SQLite foreign keys are ON

`PRAGMA foreign_keys = ON` is set in schema.sql and must be re-asserted in
every new database connection in `StorageAdapter`. SQLite does not persist
pragma state across connections. A missing `PRAGMA foreign_keys = ON` in a
test fixture is a silent source of FK corruption.

### 4.6 FTS5 trigger synchronisation

The three FTS5 triggers (`memories_fts_insert`, `memories_fts_update`,
`memories_fts_delete`) keep `memories_fts` in sync automatically. Never
write directly to `memories_fts` in application code — only through the
`memories` table. The schema compliance test checks that all three triggers
exist.

---

## 5. Agentic Development Rules

### 5.1 Spec-first

Before writing any code for a task, read the relevant spec files:

```
packages/core/src/mintmory/core/types.py      # always
packages/core/src/mintmory/core/schema.sql    # for storage changes
docs/openapi/mintmory.yaml                    # for API/MCP interface changes
docs/research/FEATURES.md                     # for feature context
```

Do not infer types from the task description. Read the actual types.

### 5.2 TDD — tests before implementation

1. Write the failing test first (in the appropriate `tests/` directory).
2. Run it: `uv run pytest packages/core/tests/test_xyz.py -x` — confirm it
   fails for the right reason.
3. Implement the feature until the test passes.
4. Run the full suite: `uv run pytest` — confirm nothing regressed.

No agent may mark a task complete if the test gate has not been run.

### 5.3 Schema compliance tests are non-negotiable

`packages/core/tests/test_schema.py` tests:
- Every `MemoryCategory` value appears in the `memories.category CHECK` constraint.
- Every `ConceptLinkType` value appears in the `concept_links.link_type CHECK` constraint.
- Every `MemorySource` value appears in the `memories.source CHECK` constraint.
- Every `LinkSource` value appears in the `concept_links.source CHECK` constraint.
- All six expected tables exist.
- All three FTS5 triggers exist.

These tests MUST always pass. If you break them, stop and fix the DDL
before proceeding.

### 5.4 No modification of types.py without updating schema.sql and openapi.yaml

This is enforced by the schema compliance tests and by the source of truth
hierarchy (§3). Violating it creates a split-brain state that is difficult to
recover.

### 5.5 Mypy and ruff must pass

```bash
uv run mypy packages/          # strict mode
uv run ruff check packages/
uv run ruff format --check packages/
```

A PR that introduces mypy errors or ruff violations will not be merged,
regardless of whether tests pass.

---

## 6. Parallel Agent Patterns

### 6.1 Package dependency order

```
core  →  mcp
      →  api
      →  cli
```

`mcp`, `api`, and `cli` all depend on `core`. They do NOT depend on each other.
`mcp` and `api` can be developed in parallel once `core` has a stable interface.

### 6.2 Spawning parallel tasks

When the orchestrator dispatches tasks for independent packages:

```
Task A: implement StorageAdapter in packages/core   (no deps, do first)
Task B: implement MCP tools in packages/mcp         (depends on Task A)
Task C: implement API routes in packages/api        (depends on Task A)
```

B and C may be dispatched in parallel once A's test gate is confirmed green.
The gate is: `uv run pytest packages/core/tests/ --tb=short -q` exits 0.

### 6.3 Files to read before starting each task type

| Task type | Mandatory reads before starting |
|---|---|
| Core storage | `types.py`, `schema.sql` |
| Entity extraction | `types.py` (entity_ids field), `FEATURES.md §Entity Extraction` |
| Scoring | `types.py` (effective_score method), `FEATURES.md §Scoring` |
| Dreaming | `types.py` (DreamIntensity, DreamReport, AnomalyReport), `FEATURES.md §Dreaming` |
| MCP tools | `types.py`, `FEATURES.md §MCP Tools`, `ADR-0001` |
| API routes | `types.py`, `openapi/mintmory.yaml`, `FEATURES.md §HTTP API` |
| CLI commands | `types.py`, `FEATURES.md §CLI` |
| Conflict detection | `types.py` (ConflictCheckResult, ConflictDetail) — pay close attention to §4.1 |

### 6.4 Task completion gate

A task is done when:
1. The test command for the affected package exits 0.
2. `uv run mypy packages/{package}/` exits 0.
3. `uv run ruff check packages/{package}/` exits 0.

"The implementation is written" is NOT the completion gate. Tests must run.

---

## 7. Testing Philosophy

### Unit tests (packages/\*/tests/test\_\*.py)

- No real SQLite file — use `:memory:` via `sqlite3.connect(":memory:")`
- No real embedding model — use a mock `EmbedderProtocol` that returns a
  fixed zero vector of the correct dimension (384 for all-MiniLM-L6-v2)
- No LLM calls — mock any function that calls an external LLM
- Fast: entire unit suite should run in < 5 seconds

Example fixture:

```python
import sqlite3
import pytest
from mintmory.core.storage import StorageAdapter

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    adapter = StorageAdapter(conn)
    adapter.initialise()   # runs schema.sql
    yield adapter
    conn.close()
```

### Integration tests (tests/integration/)

- Real SQLite file in a `tmp_path` fixture (pytest's built-in)
- Real entity extraction (regex, no LLM)
- Canned LLM responses: patch the LLM call with a dict fixture, not a real
  API call
- Covers the full add → search → feedback loop
- Slower: may take up to 30 seconds

### Live session tests (manual)

Defined per milestone (M3, M4, M7). A human runs Claude Code with the MCP
server installed and validates qualitative behaviour. Live session tests are
NOT automated and are NOT part of CI. They are documented in
`docs/live-sessions/`.

---

## 8. Measurement and Quality Signals

### What healthy looks like

| Signal | Healthy | Warning |
|---|---|---|
| Schema compliance tests | 100% pass | Any failure |
| Unit test coverage | >= 80% | < 80% |
| p50 add latency | < 50 ms | > 100 ms |
| p50 search latency (FTS only) | < 20 ms | > 50 ms |
| p50 search latency (vector) | < 100 ms | > 200 ms |
| Dreaming idempotency (2nd run new_links) | 0 | > 0 |
| Staleness detection accuracy (spot-check) | >= 0.7 F1 | < 0.5 F1 |
| Graph edge precision (spot-check) | >= 0.6 | < 0.4 |
| Rehabilitation rate (7-day test) | rehabilitated > archived | rehabilitated == 0 |

### How to run measurements

```bash
# Schema compliance
uv run pytest packages/core/tests/test_schema.py -v

# Full test suite with coverage
uv run pytest --cov=packages --cov-report=term-missing

# Idempotency check (dreaming)
uv run pytest packages/core/tests/test_dreaming.py::test_dream_idempotency -v

# p50 latency benchmark
uv run python scripts/benchmark.py --operations add,search --percentiles 50,95,99

# 7-day staleness simulation
uv run python scripts/staleness_sim.py --days 7
```

### What a failing measurement signals

- **Schema compliance failure**: types.py / schema.sql / openapi.yaml are out
  of sync. Fix the DDL.
- **Dreaming idempotency failure (new_links > 0 on 2nd run)**: The concept
  linking step is not using `INSERT OR IGNORE`. Fix the upsert.
- **p50 add > 100 ms**: Likely the embedding call is blocking the main thread.
  Move to `asyncio.to_thread`.
- **Staleness F1 < 0.5**: The staleness score update formula is miscalibrated.
  Check the `staleness_weight` in `scoring.py`.

---

## 9. Git Workflow

### Branch naming

```
feature/MM-{task-number}-{short-description}
fix/MM-{task-number}-{short-description}
chore/MM-{task-number}-{short-description}
```

Examples:
- `feature/MM-12-storage-adapter`
- `fix/MM-17-idempotency-bug`
- `chore/MM-3-ruff-config`

### Commit message format

```
MM-{N}: {imperative sentence}
```

Examples:
- `MM-12: implement StorageAdapter with WAL and FTS5`
- `MM-17: fix dreaming concept linking to use INSERT OR IGNORE`
- `MM-3: configure ruff with ANN and B rule sets`

One sentence. Imperative mood. No trailing period. No `Co-Authored-By` trailers.

### PR requirements

Before opening a PR, confirm all of the following pass locally:

```bash
uv run pytest                     # all tests, coverage >= 80%
uv run mypy packages/             # strict, zero errors
uv run ruff check packages/       # zero violations
uv run ruff format --check packages/
```

A PR that fails any of these will not be merged. Do not open it until they
pass.

### Branch lifetime

Feature branches are deleted after merge. Never push directly to `main`.
Main is always green (all CI checks passing).

---

## 10. Quick-Reference Checklists

### Before writing any code

- [ ] Read `types.py` fully
- [ ] Read `schema.sql` if touching storage
- [ ] Read `FEATURES.md` for the feature being implemented
- [ ] Check §4 invariants for anything that might be affected

### Before opening a PR

- [ ] `uv run pytest` exits 0
- [ ] Coverage >= 80% for touched packages
- [ ] `uv run mypy packages/` exits 0
- [ ] `uv run ruff check packages/` exits 0
- [ ] `schema.sql` CHECK constraints match `types.py` enums
- [ ] `openapi.yaml` updated if types changed
- [ ] `FEATURES.md` updated if behaviour changed
