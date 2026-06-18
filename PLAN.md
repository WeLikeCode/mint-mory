# MintMory Implementation Plan (authoritative for the build)

This is the execution contract for implementing the MintMory openspecs. Every
implementation agent MUST read this file **and** `AGENTS.md` before writing code.
It records design decisions that resolve real divergences between the spec
documents, so that parallel agents do not re-derive conflicting designs.

---

## 0. Source-of-truth hierarchy (and STALE documents)

Authoritative, in order:

1. `packages/core/src/mintmory/core/types.py`   (Pydantic models + enums)
2. `packages/core/src/mintmory/core/schema.sql` (DDL, enforced by `test_schema.py`)
3. `docs/openapi/mintmory.yaml`                  (HTTP contract)
4. `docs/research/FEATURES.md` (v2.0 corrected)  (behaviour spec)
5. `ROADMAP.md`, `AGENTS.md`                      (milestones, invariants, workflow)

**STALE — do NOT follow where they conflict with the above:**

- `docs/architecture/system-design.md`
- `docs/architecture/ADR-0002-sqlite-primary.md` (schema section)
- `docs/architecture/ADR-0004-pluggable-embeddings.md` (schema/`schema_meta` section)

These three describe a pre-correction schema (`importance`, `decay_rate`,
`access_count`, `has_conflict`, a `memory_vectors` vec0 table, a `schema_meta`
table, `source_id`/`target_id` columns, `/api/v1/...` routes, and MCP tools named
`store_memory`/`retrieve_memories`). **None of that exists in the current
schema.** The real schema uses `usefulness_score`/`staleness_score`, an
`embedding BLOB` column directly on `memories`, `source_memory_id`/
`target_memory_id`, and the routes/tools defined in `openapi/mintmory.yaml` and
the existing stub files. ADR-0004's *embedding-provider protocol* design (the
`EmbedderProtocol`, `LocalEmbedder`, `OpenAIEmbedder`, L2-normalisation, `[local]`
extra) IS still authoritative — only its schema/`schema_meta` snippets are stale.

---

## 1. Resolved API contracts (these override stub signatures where noted)

The pre-written, executable tests are the strongest contract. Two resolutions:

### 1a. `StorageAdapter.add_memory`

The integration test calls `store.add_memory(**{"content":..., "category":...,
"source":..., "confidence":..., "verified":...})` and expects a `MemoryRecord`
back. The transport layers prefer passing a built `MemoryRecord`. Support both:

```python
def add_memory(self, record: MemoryRecord | None = None, **fields: Any) -> MemoryRecord:
    """If `record` is None, build MemoryRecord(**fields). Always run entity
    extraction to populate entity_ids; compute + store an embedding iff an
    embedder is configured; persist; return the stored record (round-trip
    fidelity: every field preserved)."""
```

- `category`/`source` may arrive as raw strings (from kwargs) or enum members —
  Pydantic coerces strings to enums, so build via `MemoryRecord` and rely on it.
- Entity extraction: call `extract_entities(record.content)` and set
  `entity_ids` if the caller did not already supply a non-empty list.

### 1b. Feedback: a per-memory primitive (storage) + a session orchestrator (session.py)

The integration test calls `store.apply_feedback(memory_id, useful=True,
stale=False)`. So **storage owns a per-memory primitive** (this REPLACES the
session-shaped stub signature currently in `storage.py`):

```python
def apply_feedback(self, memory_id: str, useful: bool, stale: bool) -> None:
    """useful -> usefulness_score += USEFUL_INCREMENT (cap 10), reinforcement_count += 1.
       stale  -> staleness_score  += STALE_INCREMENT  (cap 10).
       set is_stale = True when staleness_score >= STALENESS_THRESHOLD (7.0).
       always refresh updated_at. Use scoring.increment_usefulness/staleness."""
```

The **session-level** feedback (ROADMAP M3) lives in `core/session.py` and calls
the storage primitive per id:

```python
def apply_feedback(adapter, session_id, useful_ids, stale_ids,
                   confidence_rating, reasoning) -> QuerySession:
    """For each id in useful_ids: adapter.apply_feedback(id, useful=True, stale=False).
       For each id in stale_ids:  adapter.apply_feedback(id, useful=False, stale=True).
       Update query_sessions row (confidence_rating, reasoning, useful_ids,
       stale_ids, concluded=True) and the matching query_results flags. Idempotent:
       if already concluded, raise/return per caller's needs (API maps to 409)."""
```

Constants (add to `scoring.py` if missing, values from FEATURES.md §6):
`USEFUL_INCREMENT = 0.5`, `STALE_INCREMENT = 1.0`, `STALENESS_THRESHOLD = 7.0`,
`ARCHIVE_THRESHOLD = 9.0`, `REHAB_DELTA = 2.0`.

---

## 2. Embedding (ADR-0004, optional/lazy — keeps tests fast)

`core/embedder.py` (new): `EmbedderProtocol` (runtime_checkable), `LocalEmbedder`
(lazy `import sentence_transformers`, 384 dims, L2-normalised), `OpenAIEmbedder`
(lazy `import openai`, 1536 dims), `create_embedder(provider, ...)` factory, and a
test-friendly `HashEmbedder`/`FakeEmbedder` (deterministic, dependency-free,
configurable dim, default 384) for use as the default in tests.

- `StorageAdapter.__init__(self, db_path=":memory:", embedder: EmbedderProtocol | None = None)`.
- If `embedder is None`: store `embedding = NULL`, and search is **FTS-only**
  (no vector phase). Never require sentence-transformers to run the test suite.
- sqlite-vec: load best-effort in `connect()`:
  ```python
  try:
      self._conn.enable_load_extension(True); import sqlite_vec
      sqlite_vec.load(self._conn); self._conn.enable_load_extension(False)
      self._vec_loaded = True
  except Exception: self._vec_loaded = False
  ```
  Vector search uses `vec_distance_cosine(embedding, ?)` only when both an
  embedder is present AND `_vec_loaded`. Otherwise degrade to FTS-only. Tests
  must pass with or without the extension.

---

## 3. Search & search-around (storage)

- `search(request: SearchRequest, query_embedding=None) -> SearchResponse`:
  1. FTS5: `SELECT rowid ... FROM memories_fts WHERE memories_fts MATCH ?`
     (sanitise the query: quote terms / wrap to avoid FTS syntax errors).
  2. Vector (only if embedder+vec available): rank by `vec_distance_cosine`.
  3. Merge via `scoring.rrf_merge` (when both present) else use whichever ran.
  4. Apply `MemoryFilter` (category/source/verified/active/exclude_stale/entity/
     min_usefulness/max_staleness) + `include_archived` + base active/archived rules.
  5. Compute `effective_score` per candidate (`scoring.effective_score`); sort desc; `limit`.
  6. If `search_around`: union in `search_around(anchor_ids, spec)` results;
     populate `SearchResponse.search_around_ids` (OR semantics — anchors always kept).
  7. Create a `QuerySession` (via `create_session`) and `record_query_results`;
     return its id as `SearchResponse.session_id`.
  8. Bump `retrieval_count` / `last_accessed_at` for returned memories.
- `search_around(anchor_ids, spec) -> list[str]`: recursive CTE over
  `concept_links`, honouring `spec.link_types` (empty = all), `spec.depth` (1–3),
  `spec.min_strength`; follow source→target, and for `SYMMETRIC_LINK_TYPES` also
  target→source; exclude anchors from the returned ids; dedup. See the SQL
  sketch in `storage.py` docstring and FEATURES.md §11.1.

---

## 4. File / module ownership (prevents parallel-edit conflicts)

One owner per file. Agents in the same stage touch DISJOINT files.

| File | Owner stage | Notes |
|---|---|---|
| `core/entities.py` | DONE (orchestrator) | phrase+token extraction — already fixed |
| `core/scoring.py` | DONE (+ add constants if needed) | formulas exist |
| `core/embedder.py` (new) | Stage 1 | embeddings, lazy/optional |
| `core/storage.py` | Stage 1 | ALL CRUD, search, search_around, links, sessions storage, summaries storage, stats, dreaming helpers |
| `core/session.py` (new) | Stage 2 | session lifecycle + session-level feedback + CONTRADICTION_DETECTION_PROMPT + FEEDBACK_PROMPT |
| `core/dreaming.py` (new) | Stage 2 | DreamingEngine.run_light/run_full, steps 1–6, idempotent |
| `mcp/.../server.py` (+ tools) | Stage 3 | implement tool bodies over core |
| `api/.../app.py` (+ schemas) | Stage 3 | implement route bodies; conform to openapi.yaml |
| `cli/.../main.py` | Stage 3 | implement commands over core |
| `scripts/run_dreamd.py` (new) | Stage 2/3 | async loop calling run_full on interval |

Tests: each owner writes the matching `test_*.py` in its package's `tests/`.
Do NOT edit another stage's files. `types.py`/`schema.sql` are FROZEN unless a
schema change is genuinely required — if so, update **types.py → schema.sql →
openapi.yaml** in that order and keep `test_schema.py` green (AGENTS.md §3/§5.4).

---

## 5. Stage plan (each stage = one parallel workflow; gate verified between stages)

- **Stage 1 — core foundation** (parallel): `storage.py` (+tests) ‖ `embedder.py` (+tests).
  Gate: `uv run pytest -o addopts="" packages/core/tests/ tests/integration/ -q` exits 0.
- **Stage 2 — core logic** (parallel): `session.py` (+tests) ‖ `dreaming.py` (+tests) ‖ `scripts/run_dreamd.py`.
  Gate: full `packages/core/tests/` green incl. dreaming idempotency.
- **Stage 3 — transports** (parallel): `mcp` (+tests) ‖ `api` (+tests) ‖ `cli` (+tests).
  Gate: each package's tests green.
- **Stage 4 — quality**: `uv run pytest` (coverage ≥ 80), `uv run mypy packages/`,
  `uv run ruff check packages/`, `uv run ruff format --check packages/` all clean.

---

## 6. Hard invariants (AGENTS.md §4 — every agent re-checks before "done")

1. Score caps `[0,10]` — clamp before every write (`min(x,10.0)`, `max(x,0.0)`).
2. `ConflictCheckResult` uses `has_conflict` + `conflicts[].existing_memory_id`.
   NEVER `is_contradiction` / `contradicts_memory_ids`.
3. `PRAGMA foreign_keys = ON` on every adapter connection.
4. Dreaming idempotent: `INSERT OR IGNORE` (links), `INSERT OR REPLACE` on
   `concept` (summaries), guard flags before mutate (steps 4–6). Second
   `run_light`/`run_full` on an unchanged DB → `new_links == 0`, `new_summaries == 0`.
5. Never write `memories_fts` directly — only through `memories` (triggers sync it).
6. `ConceptLinkType` is a closed 11-value enum; symmetric set = {relates_to,
   contradicts, similar_to}.

## 7. Test/run conventions

- Unit tests use `:memory:` or `tmp_path` + a `FakeEmbedder` (no model, no network, no LLM).
- LLM-dependent paths (contradiction resolution, summary generation, session
  feedback prompts) take an injectable callable; tests pass a canned function.
- During development run subsets with `-o addopts=""` to bypass the global
  `--cov-fail-under=80` gate; the FINAL Stage-4 run must pass it for real.
- Commit style (AGENTS.md §9): `MM-{N}: imperative`. No `Co-Authored-By` trailers.
</content>
</invoke>
