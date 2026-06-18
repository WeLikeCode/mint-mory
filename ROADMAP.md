# MintMory Roadmap

Each milestone has a definition of done (test gate + optional live session),
a quantitative measurement signal, and explicit dependencies. A milestone is
not started until all its dependencies are green.

---

## M1 — Schema + Storage

**Goal:** The SQLite database can be created from schema.sql, and the schema
compliance tests prove that types.py, schema.sql, and the table structure are
in sync. No application logic yet.

### What gets built

- `schema.sql` — complete DDL (6 tables, FTS5, indexes, FK constraints, WAL)
- `packages/core/src/mintmory/core/storage.py` — `StorageAdapter` class with:
  - `initialise()` — reads and executes schema.sql, sets WAL + FK pragmas
  - `connect(path)` — opens a connection with correct pragmas
- `packages/core/tests/test_schema.py` — schema compliance tests:
  - All 6 tables exist: `memories`, `memories_fts`, `concept_links`,
    `memory_summaries`, `query_sessions`, `query_results`
  - All 3 FTS5 triggers exist
  - `memories.category` CHECK contains all 8 `MemoryCategory` values
  - `concept_links.link_type` CHECK contains all 11 `ConceptLinkType` values
  - `memories.source` CHECK contains all 4 `MemorySource` values
  - `concept_links.source` CHECK contains all 4 `LinkSource` values
  - `PRAGMA foreign_keys` returns ON after `initialise()`

### Definition of Done

- `uv run pytest packages/core/tests/test_schema.py` — 100% pass, zero
  failures
- No live session required

### Measurement Signal

- Schema compliance: 100% (binary — all checks pass or milestone is not done)
- `initialise()` wall-clock time on cold disk < 50 ms

### Dependencies

None. This is the foundation milestone.

---

## M2 — Core CRUD + Entity Extraction

**Goal:** Memories can be added, retrieved, updated, and archived. Entity IDs
are extracted from content via regex. Basic scoring fields are populated on
write.

### What gets built

- `StorageAdapter` CRUD methods:
  - `add_memory(record: MemoryRecord) -> str`
  - `get_memory(id: str) -> MemoryRecord | None`
  - `update_memory(id: str, **fields) -> MemoryRecord`
  - `archive_memory(id: str) -> None`
  - `list_memories(filter: MemoryFilter) -> list[MemoryRecord]`
- `packages/core/src/mintmory/core/entity.py` — regex entity extraction:
  - Extracts capitalised noun phrases, URLs, version strings, email addresses
  - Returns a `list[str]` stored in `entity_ids`
- `packages/core/src/mintmory/core/scoring.py` — initial score helpers:
  - `initial_usefulness(category: MemoryCategory) -> float` — category priors
  - `increment_retrieval_count(adapter, memory_id)` — updates `retrieval_count`
    and `last_accessed_at`
- `packages/core/tests/test_storage.py` — CRUD round-trip tests (`:memory:` DB)
- `packages/core/tests/test_entity.py` — entity extraction unit tests

### Definition of Done

- `uv run pytest packages/core/tests/` exits 0
- p50 add latency (measured by `scripts/benchmark.py`) < 50 ms on MacBook-class
  hardware (M-series or equivalent x86)
- No live session required

### Measurement Signal

- Round-trip fidelity: `add_memory(r); get_memory(r.id)` returns a record
  equal to `r` (all fields preserved)
- p50 add latency < 50 ms
- Entity extraction recall on 20 hand-labelled examples >= 0.75

### Dependencies

M1 complete (schema compliance tests passing)

---

## M3 — Query Sessions + Passive Feedback

**Goal:** Every search creates a `QuerySession`. When the session concludes,
the LLM submits feedback listing useful and stale memories. Feedback is applied
to scores. This is the first live session milestone.

### What gets built

- `packages/core/src/mintmory/core/session.py`:
  - `create_session(query_text: str) -> QuerySession`
  - `record_results(session_id, results: list[QueryResult]) -> None`
  - `apply_feedback(session_id, useful_ids, stale_ids,
                    confidence_rating, reasoning) -> None`
    - Increments `usefulness_score` for useful_ids (capped at 10.0)
    - Increments `staleness_score` for stale_ids (capped at 10.0)
    - Sets `is_stale = True` if `staleness_score >= 7.0`
    - Marks session `concluded = True`
  - `conclude_session(session_id: str) -> None`
- `CONTRADICTION_DETECTION_PROMPT` constant — with correct field names
  `has_conflict` / `conflicts[].existing_memory_id` (see AGENTS.md §4.1)
- `packages/core/tests/test_session.py`:
  - Feedback loop integration test: add 3 memories → search → apply feedback
    → assert score changes match expectations
  - Assert `has_conflict` / `conflicts` field names in `ConflictCheckResult`

### Definition of Done

- `uv run pytest packages/core/tests/` exits 0
- **FIRST LIVE SESSION**: human runs Claude Code with `mintmory-cli` installed,
  adds 5 memories, runs a search, submits feedback, checks that scores updated.
  Session notes recorded in `docs/live-sessions/M3-session.md`.

### Measurement Signal

- Feedback loop latency (search → feedback applied) < 200 ms
- Score capping: no memory has `usefulness_score > 10.0` or
  `staleness_score > 10.0` after 50 feedback cycles in the integration test

### Dependencies

M2 complete

---

## M4 — MCP Transport

**Goal:** The MCP server is installable in Claude Code. Claude can query,
add, update, and archive memories via MCP tools. Stdio and SSE sub-transports
both work.

### What gets built

- `packages/mcp/src/mintmory/mcp/server.py` — `FastMCP("MintMory")` instance
- `packages/mcp/src/mintmory/mcp/tools.py` — MCP tools:
  - `memory_add(content, category, source?, metadata?) -> dict`
  - `memory_search(query, limit?, filter?) -> dict`
  - `memory_get(id) -> dict`
  - `memory_update(id, **fields) -> dict`
  - `memory_archive(id) -> dict`
  - `memory_feedback(session_id, useful_ids, stale_ids,
                     confidence_rating?, reasoning?) -> dict`
  - `memory_stats() -> dict`
- `packages/mcp/tests/test_tools.py` — tool input/output shape tests
- Claude Code integration: `mcp install` command documented in
  `docs/mcp-install.md`

### Definition of Done

- `uv run pytest packages/mcp/tests/` exits 0
- `mcp install` succeeds in a fresh Claude Code session
- **LIVE SESSION**: human uses Claude Code with MCP installed, confirms Claude
  can query existing memories and add new ones. Session notes in
  `docs/live-sessions/M4-session.md`.

### Measurement Signal

- MCP tool call round-trip (Claude → MCP server → core → response) < 500 ms
  p50
- All 7 tools callable without error from Claude Code's MCP panel

### Dependencies

M3 complete (core has sessions and feedback)

---

## M5 — Concept Linking + Dreaming Light

**Goal:** Entity extraction seeds concept links between memories sharing
entities. The light dreaming cycle (anomaly detection + linking + summaries)
runs correctly and is idempotent.

### What gets built

- `packages/core/src/mintmory/core/dreaming.py` — `DreamingEngine`:
  - `run_light() -> DreamReport` — executes steps 1, 2, 3
  - Step 1 `detect_anomalies() -> AnomalyReport` — read-only scan
  - Step 2 `create_concept_links() -> int` — entity overlap → links via
    `INSERT OR IGNORE`
  - Step 3 `generate_summaries() -> int` — per-concept `MemorySummary` via
    `INSERT OR REPLACE`
- `packages/core/tests/test_dreaming.py`:
  - `test_dream_idempotency`: run `run_light()` twice, assert second
    `DreamReport.new_links == 0` and `new_summaries == 0`
  - `test_anomaly_detection`: seed stale memory, confirm it appears in report
  - `test_concept_linking`: two memories sharing an entity → link created

### Definition of Done

- `uv run pytest packages/core/tests/test_dreaming.py` exits 0 (including
  idempotency test)
- Graph edge precision spot-check: manually inspect 10 created links, >= 6
  are correct (0.6 precision)
- No live session required

### Measurement Signal

- Idempotency: `DreamReport.new_links == 0` on the second run (automated)
- Graph edge precision spot-check >= 0.6
- Light dream wall-clock time on 1,000 memories < 2 seconds

### Dependencies

M2 complete (entity extraction, CRUD)

---

## M6 — HTTP API + OpenAPI

**Goal:** All memory operations are exposed over HTTP REST. Every route returns
a response that conforms to `openapi/mintmory.yaml`. A spec conformance test
enforces this.

### What gets built

- `packages/api/src/mintmory/api/main.py` — FastAPI app with lifespan
- Route files:
  - `routes/memories.py` — POST /memories, GET /memories/{id},
    PATCH /memories/{id}, DELETE /memories/{id}, GET /memories
  - `routes/search.py` — POST /search
  - `routes/sessions.py` — POST /sessions, POST /sessions/{id}/feedback,
    GET /sessions/{id}
  - `routes/dream.py` — POST /dream
  - `routes/stats.py` — GET /stats
- `docs/openapi/mintmory.yaml` — OpenAPI 3.1 spec (derived from types.py)
- `packages/api/tests/test_routes.py`:
  - Spec conformance: every route's response validated against openapi.yaml
    using `jsonschema`
  - Round-trip: POST /memories → GET /memories/{id} returns same content

### Definition of Done

- `uv run pytest packages/api/tests/` exits 0
- All routes return spec-conformant responses (spec conformance test passes
  with zero violations)
- No live session required

### Measurement Signal

- Zero OpenAPI spec violations (binary)
- p50 HTTP round-trip (httpx TestClient) < 10 ms for GET /memories/{id}

### Dependencies

M3 complete (sessions, feedback), M5 complete (dreaming endpoint can be
called)

---

## M7 — Search-Around Query

**Goal:** A `SearchRequest` with a `SearchAroundSpec` traverses the concept
graph from anchor matches, returning linked memories with OR semantics. A
graph CTE implements the traversal efficiently in SQLite.

### What gets built

- `StorageAdapter.search_around(request: SearchRequest) -> SearchResponse`:
  - Phase 1: FTS + vector search for anchor memories matching `query`
  - Phase 2: recursive CTE traversal from anchors via `concept_links`,
    filtered by `link_types`, up to `depth` hops, with `min_strength` filter
  - Result: `anchors UNION traversed`, deduplicated
- `packages/core/tests/test_search_around.py`:
  - Recall@10 test: seed 20 memories with known link structure, assert that
    search-around retrieves >= 8 of the 10 expected results
  - Depth test: depth=1 vs depth=2 returns different result sets as expected
- MCP tool `memory_search` updated to accept `search_around` parameter
- API route `POST /search` updated to accept `SearchAroundSpec`

### Definition of Done

- `uv run pytest packages/core/tests/test_search_around.py` exits 0
- recall@10 >= 0.8 on the structured test fixture
- **LIVE SESSION**: human asks Claude to find "everything related to parking
  integration" with search-around enabled. Claude returns memories from at
  least 2 hops. Notes in `docs/live-sessions/M7-session.md`.

### Measurement Signal

- recall@10 >= 0.8 (automated test fixture)
- Graph traversal latency (1,000 memories, depth=2) < 50 ms p50

### Dependencies

M4 complete (MCP tools), M5 complete (concept links exist in DB), M6 complete
(HTTP API for integration)

---

## M8 — Dreaming Full + Scheduling

**Goal:** The full dreaming cycle runs: light steps + contradiction resolution
+ archival of persistently stale memories + rehabilitation of formerly stale
memories that became useful. A scheduler (cron or asyncio loop) runs dreaming
automatically on a configured interval.

### What gets built

- `DreamingEngine.run_full() -> DreamReport` — steps 1–6:
  - Step 4 `resolve_contradictions()`: for each `flagged_for_review` memory,
    call LLM with `CONTRADICTION_DETECTION_PROMPT`, apply
    `BatchResolutionAction` (ADD / UPDATE / DELETE / NONE)
  - Step 5 `archive_stale()`: archive memories where `is_stale = True` and
    `staleness_score >= 9.0` and `last_accessed_at` is older than threshold
  - Step 6 `rehabilitate()`: reset `is_stale = False` for memories where
    `usefulness_score > staleness_score` and they were recently retrieved
- `scripts/run_dreamd.py` — long-running async loop calling `run_full()` on
  a configurable interval (default: every 6 hours)
- `packages/core/tests/test_dreaming.py` additions:
  - `test_full_dream_idempotency`: same as light, but for `run_full()`
  - `test_contradiction_resolution`: seed two contradicting memories
    (both `flagged_for_review = True`), run full dream, assert one is archived
  - `test_rehabilitation`: seed a stale memory, simulate retrieval feedback
    raising `usefulness_score`, run full dream, assert `is_stale = False`
  - `test_7_day_staleness_simulation`: simulate 7 days of mixed retrieval
    patterns using `scripts/staleness_sim.py`, assert `rehabilitated > archived`

### Definition of Done

- `uv run pytest packages/core/tests/test_dreaming.py` exits 0 (including
  full dream idempotency, contradiction resolution, rehabilitation, and
  7-day simulation)
- `scripts/run_dreamd.py` runs for 60 seconds without error in a test
  environment
- No live session required (the dreaming daemon is background infrastructure)

### Measurement Signal

- Full dream idempotency: `DreamReport.new_links == 0` on second run
- Rehabilitation rate (7-day sim): `memories_rehabilitated > memories_archived`
- Contradiction resolution precision (spot-check on 10 examples): >= 0.7

### Dependencies

M5 complete (light dreaming), M6 complete (HTTP dream endpoint), M7 complete
(full graph linkage for rehabilitation decisions)

---

## Milestone Summary

| # | Name | Gate | Live Session |
|---|---|---|---|
| M1 | Schema + Storage | 100% DDL tests pass | No |
| M2 | Core CRUD + Entity Extraction | round-trip tests, p50 < 50 ms | No |
| M3 | Query Sessions + Passive Feedback | feedback loop integration test | Yes (first) |
| M4 | MCP Transport | `mcp install` works in Claude Code | Yes |
| M5 | Concept Linking + Dreaming Light | idempotency test, precision spot-check | No |
| M6 | HTTP API + OpenAPI | all routes spec-conformant | No |
| M7 | Search-Around Query | recall@10 >= 0.8 | Yes (graph query) |
| M8 | Dreaming Full + Scheduling | 7-day sim, idempotency, rehab > archive | No |
