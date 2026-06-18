# MintMory Feature Specification

**Version:** 2.0 (corrected)  
**Correction log:**
- v1.0: original research draft — contained wrong contradiction prompt field
  names (`is_contradiction`, `contradicts_memory_ids`) and only 4 ConceptLink
  types. Source: LLM-Memory research project.
- v2.0: corrected per widemem audit finding. Field names changed to
  `has_conflict` / `conflicts[].existing_memory_id`. ConceptLink types
  expanded from 4 to 11. Schema updated to match schema.sql exactly (6 tables).
  Scoring formula made explicit. SearchAroundSpec added.

This document is the **living specification** for what MintMory does. New
contributors should read this before reading any code. When this document
conflicts with code, treat this as the intended behaviour and file a bug
against the code.

---

## 1. System Overview

MintMory is a typed, queryable, self-improving memory layer for LLM agents.
It draws from three design lineages:

1. **Palantir Foundry Ontology** — every piece of information has an explicit
   type (object type), explicit relationships (link types), and explicit
   provenance. The Ontology is queryable at the type level, not just at the
   content level.

2. **Academic memory systems** — MoPA (2210.05359), Recall-and-Reflect
   (2311.03363), AgentKB (2312.06066), Memento (2310.08721), widemem
   (2606.12945), MEMTIER, MemGPT. Key findings incorporated:
   - Typed categories improve retrieval precision vs flat storage
   - Passive self-assessment (no user feedback required) is sufficient for
     staleness detection
   - Graph-structured linking enables search-around queries that flat vector
     search cannot express
   - Dreaming (offline consolidation) reduces contradiction accumulation

3. **SQLite + sqlite-vec** — No external vector DB. All storage in a single
   `.db` file with WAL mode. FTS5 for keyword search, sqlite-vec for semantic
   search. Simple, auditable, portable.

### Transport summary

| Transport | Package | Use case |
|---|---|---|
| stdio | `mintmory-cli` | Scripts, human-in-the-loop |
| MCP stdio | `mintmory-mcp` | Claude Code, Cursor (default) |
| MCP SSE | `mintmory-mcp` | Open WebUI, remote MCP clients |
| HTTP REST | `mintmory-api` | External services, dashboards |

---

## 2. Memory Categories

Eight orthogonal categories. Every `MemoryRecord` has exactly one.

| Category | Value | What belongs here |
|---|---|---|
| Identity | `identity` | Persistent facts about the user or agent: name, role, preferences that don't change session-to-session |
| Preference | `preference` | Stated or inferred preferences: "prefers TypeScript over Python", "dislikes long explanations" |
| Skill | `skill` | How to do something: procedures, recipes, tool usage patterns, debugging workflows |
| Context | `context` | Current working context: active project, open ticket, current goal for this session |
| Fact | `fact` | World-state facts: configuration values, URLs, API endpoints, version numbers |
| Episodic | `episodic` | Something that happened in a specific past session: "fixed the auth bug in session 2026-06-10" |
| Temporal | `temporal` | Time-bounded fact: "deploy freeze until 2026-06-20", "sprint ends Friday" |
| Relationship | `relationship` | A typed link between two named entities, stored as a `ConceptLink` rather than as free text |

**Design note:** `relationship` is included for completeness but most
inter-memory relationships should be expressed as `ConceptLink` instances
rather than as `MemoryRecord` instances. A `MemoryRecord` with
`category = "relationship"` is appropriate only when the relationship itself
needs a textual description (e.g., "Alice is Bob's manager, and this matters
because they share a budget").

---

## 3. ConceptLink Types

Eleven typed relationship categories. Every `ConceptLink` has exactly one.
Symmetric types (noted below) do not require a separate reverse edge.

| Type | Value | Direction | Meaning |
|---|---|---|---|
| Relates to | `relates_to` | symmetric | General connection, no specific semantic direction |
| Contradicts | `contradicts` | symmetric | The two memories cannot both be true simultaneously |
| Refines | `refines` | A → B: B refines A | B adds specificity to A; A is more general |
| Supersedes | `supersedes` | A → B: A supersedes B | A replaces B completely; B is now outdated |
| Enables | `enables` | A → B: A enables B | A made B possible; without A, B could not exist |
| Depends on | `depends_on` | A → B: A depends on B | A requires B to function |
| Similar to | `similar_to` | symmetric | A and B are analogous but not identical |
| Part of | `part_of` | A → B: A is part of B | A is a component or subset of B |
| Uses | `uses` | A → B: A uses B | A actively invokes or consumes B |
| Before | `before` | A → B: A precedes B | A occurred or must occur before B (temporal) |
| Valid until | `valid_until` | A → B: A is valid until B | A's validity is bounded by the time encoded in B's metadata |

Symmetric types: `relates_to`, `contradicts`, `similar_to`. For these, the
dreaming engine creates a single edge rather than two.

---

## 4. SQLite Schema

Six tables. The authoritative DDL is in
`packages/core/src/mintmory/core/schema.sql`. This section describes the
purpose of each table.

```
memories          — primary object store (one row per MemoryRecord)
memories_fts      — FTS5 virtual table mirroring memories.content
concept_links     — typed edges between memories (ConceptLink rows)
memory_summaries  — LLM-generated per-concept synthesis (MemorySummary rows)
query_sessions    — audit log of every search query (QuerySession rows)
query_results     — which memories were retrieved per session (QueryResult rows)
```

### memories

Primary store. All columns map 1:1 to `MemoryRecord` fields in `types.py`.

Notable columns:

- `embedding BLOB` — 384-dim float32 vector produced by
  `sentence-transformers/all-MiniLM-L6-v2` (or override provider).
  Stored natively; queried via `sqlite-vec` extension functions.
- `entity_ids TEXT DEFAULT '[]'` — JSON array of extracted entity strings.
  Used by concept linking (Step 2 of dreaming) to find memories sharing
  an entity.
- `usefulness_score REAL DEFAULT 0.0 CHECK (<= 10.0)` — increased by
  `QueryFeedback.useful_ids`. Capped at 10.0.
- `staleness_score REAL DEFAULT 0.0 CHECK (<= 10.0)` — increased by
  `QueryFeedback.stale_ids` and by time decay. Capped at 10.0.
- `flagged_for_review INTEGER DEFAULT 0` — set to 1 when a contradiction is
  detected at add time. Dreaming Step 4 processes these.
- `contradicts_ids TEXT DEFAULT '[]'` — JSON array of memory IDs that
  contradict this record.

### concept_links

Typed edge store. The UNIQUE constraint on
`(source_memory_id, target_memory_id, link_type)` ensures idempotent inserts
(`INSERT OR IGNORE`). Cascade deletes on both ends: deleting a memory
removes its links.

### memory_summaries

One row per concept (UNIQUE on `concept`). Updated by dreaming Step 3.
`is_current = 0` when any linked memory becomes stale — a downstream
signal that the summary needs regeneration.

### query_sessions

Every `SearchRequest` creates a row here. The `concluded` flag is set when
`QueryFeedback` is submitted. Unconcluded sessions older than 24 hours are
considered abandoned and excluded from feedback processing.

### query_results

Junction table: which memories were retrieved in which session, their
relevance scores, and whether they were marked useful or stale by the LLM.

---

## 5. Memory Lifecycle

```
           add_memory()
               │
               ▼
    ┌──────────────────────┐
    │     MemoryRecord     │
    │   is_active = True   │
    │   is_stale = False   │
    │   is_archived = False│
    └──────────┬───────────┘
               │
     ┌─────────┴──────────┐
     │ QueryFeedback marks │
     │ stale_ids           │
     └─────────┬──────────┘
               │ staleness_score increases
               ▼
    ┌──────────────────────┐
    │   is_stale = True    │◄─── dreaming Step 6 can
    │ (staleness >= 7.0)   │     rehabilitate if
    └──────────┬───────────┘     usefulness > staleness
               │ staleness >= 9.0 AND not recently accessed
               ▼
    ┌──────────────────────┐
    │   is_archived = True │
    │  (dreaming Step 5)   │
    └──────────────────────┘
```

Archived memories are excluded from search by default. They can be included
by setting `SearchRequest.include_archived = True`.

---

## 6. Scoring Formula

### effective_score

Used to rank retrieved memories for display:

```
effective_score = base_relevance
               + usefulness_score * USEFULNESS_WEIGHT
               - staleness_score  * STALENESS_WEIGHT
               + recency_bonus
```

Where:

```
USEFULNESS_WEIGHT = 0.3
STALENESS_WEIGHT  = 0.2
recency_bonus     = 0.1 * exp(-decay_rate * days_since_last_access)
decay_rate        = 0.01
```

`base_relevance` is the raw similarity score from FTS5 (BM25, negated and
normalised) or cosine similarity from sqlite-vec, normalised to [0, 1].

`days_since_last_access` is 0 if `last_accessed_at` is NULL (never accessed),
producing a maximum recency_bonus of 0.1 for new memories.

### usefulness_score update (on feedback)

```python
new_usefulness = min(current_usefulness + USEFUL_INCREMENT, 10.0)
USEFUL_INCREMENT = 0.5   # per feedback cycle where memory was in useful_ids
```

### staleness_score update (on feedback)

```python
new_staleness = min(current_staleness + STALE_INCREMENT, 10.0)
STALE_INCREMENT = 1.0   # per feedback cycle where memory was in stale_ids
```

### staleness threshold

`is_stale` is set to `True` when `staleness_score >= 7.0`. This threshold is
a configuration constant (`STALENESS_THRESHOLD`), not hard-coded in SQL.

---

## 7. QuerySession and Passive Self-Assessment

### Purpose

Every `SearchRequest` is associated with a `QuerySession`. At the end of a
session (when the LLM has finished using the retrieved memories to answer a
query), the LLM itself submits a `QueryFeedback` — without prompting the user.

This is "passive" feedback: the user never sees it. The LLM reflects on which
memories were actually useful, which were stale, and how confident it was.

### Session lifecycle

1. `create_session(query_text)` — creates a `QuerySession` row.
2. `record_results(session_id, results)` — records which memories were
   retrieved and at what relevance score.
3. _(agent uses retrieved memories to respond to the user)_
4. `apply_feedback(session_id, useful_ids, stale_ids, confidence_rating,
   reasoning)` — updates scores, marks session concluded.

### Feedback prompt

The LLM is prompted (internally, not shown to user):

```
You just answered a query using the following memories. 
Which memories were actually useful in forming your answer?
Which were stale or incorrect?
Rate your confidence (1=very low, 5=very high).

Memories retrieved:
{list of memory content + IDs}

Your answer:
{the answer you just gave}

Return JSON: {
  "useful_ids": [...],
  "stale_ids": [...],
  "confidence_rating": N,
  "reasoning": "..."
}
```

This prompt is separate from `CONTRADICTION_DETECTION_PROMPT`.

---

## 8. Contradiction Detection

### Prompt schema (CORRECTED — widemem audit)

When a new memory is added, its content is checked against existing memories
for contradictions. The LLM returns:

```json
{
  "has_conflict": true,
  "conflicts": [
    {
      "new_fact": "The deploy freeze ends June 20.",
      "existing_memory_id": "mem_abc123",
      "existing_content": "The deploy freeze ends June 25.",
      "type": "contradiction",
      "question": null
    },
    {
      "new_fact": "Alice is the tech lead.",
      "existing_memory_id": "mem_def456",
      "existing_content": "Alice is the engineering manager.",
      "type": "ambiguity",
      "question": "Is Alice's role tech lead or engineering manager, or have both changed?"
    }
  ]
}
```

**Critical:** The top-level field is `has_conflict` (boolean), NOT
`is_contradiction`. The list field is `conflicts`, and each element has
`existing_memory_id` (string), NOT `contradicts_memory_ids` (list). Any code
or prompt using the old field names is a bug.

### Conflict types

- `contradiction` — the two facts are mutually exclusive. One must be wrong.
- `ambiguity` — the facts are possibly compatible but unclear. A clarifying
  question is generated.

### On detection

When `has_conflict = True`:
- The new memory is stored with `flagged_for_review = True`
- `contradicts_ids` is populated with `[c.existing_memory_id for c in conflicts]`
- The conflicting existing memories are also updated to set
  `flagged_for_review = True` (bidirectional flag)

Dreaming Step 4 (full intensity only) processes all flagged memories and
resolves them.

---

## 9. Dreaming Process

Dreaming is an offline consolidation pass run by `DreamingEngine`. It is
always idempotent: running it twice produces the same result.

### Light intensity (Steps 1–3)

**Step 1: Anomaly detection** (read-only)

Produces an `AnomalyReport`:
- `high_staleness_useful`: memories where `staleness_score >= 6.0` AND
  `usefulness_score >= 5.0` (contradictory signals — needs review)
- `never_accessed`: active memories where `retrieval_count = 0` AND
  `created_at` older than 7 days
- `contradictions`: memories where `flagged_for_review = True`

No writes in this step.

**Step 2: Concept linking**

For each pair of active memories sharing an entity (from `entity_ids`):
- If no link exists for this `(source, target, relates_to)` triple:
  `INSERT OR IGNORE INTO concept_links ...`
- `source = 'extraction'`, `strength = 0.5`

The UNIQUE constraint on `(source_memory_id, target_memory_id, link_type)`
makes this idempotent. A second run inserts nothing.

**Step 3: Summary generation**

For each entity that appears in >= 3 active memories:
- Collect all memory content sharing that entity
- Call LLM to generate a synthesis paragraph
- `INSERT OR REPLACE INTO memory_summaries (concept, summary_text, ...)` —
  idempotent via UNIQUE on `concept`

### Full intensity (Steps 1–6 = light + Steps 4–6)

**Step 4: Contradiction resolution**

For each memory where `flagged_for_review = True`:
- Call LLM with `CONTRADICTION_DETECTION_PROMPT` (correct schema: `has_conflict`,
  `conflicts[].existing_memory_id`)
- Receive a list of `BatchResolutionAction` items
- Apply each action:
  - `ADD`: add a new memory to replace the conflicting content
  - `UPDATE`: update the flagged memory's content
  - `DELETE`: archive the memory
  - `NONE`: clear the flag (conflict was false-positive)
- Clear `flagged_for_review` after resolution

Idempotency: check `flagged_for_review = 1` before processing. Already-cleared
memories are skipped.

**Step 5: Archival**

For memories where `is_stale = True` AND `staleness_score >= 9.0` AND
`last_accessed_at < (now - 30 days)` (or never accessed):
- Set `is_archived = True`, `is_active = False`

Idempotency: check `is_archived = 0` before processing.

**Step 6: Rehabilitation**

For memories where `is_stale = True` AND `usefulness_score > staleness_score`
AND `retrieval_count` increased in the last 7 days:
- Set `is_stale = False`
- Decrease `staleness_score` by a rehabilitation delta (default: 2.0, capped
  at 0.0)

Idempotency: check `is_stale = 1` before processing. Already-healthy memories
are skipped.

---

## 10. Entity Extraction

Entities are extracted from `MemoryRecord.content` at add time using regex
patterns. The results are stored in `entity_ids` (JSON array of strings).

### Extraction patterns (ordered by priority)

1. **URLs** — `https?://[^\s]+`
2. **Version strings** — `v?\d+\.\d+(\.\d+)?(-[a-zA-Z0-9]+)?`
3. **Email addresses** — `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`
4. **Capitalised noun phrases** — sequences of 1–4 capitalised words that are
   not at the start of a sentence (heuristic to exclude sentence-initial words)
5. **Quoted strings** — content inside double quotes

Entities are lowercased and deduplicated before storage.

### Use in concept linking

During dreaming Step 2, memories sharing one or more entity IDs are linked
with `link_type = 'relates_to'`. More specific link types (`contradicts`,
`supersedes`) are inferred by the LLM during Step 4 (contradiction resolution)
when scores warrant.

---

## 11. Search

### SearchRequest fields

```
query          — text to search (required)
search_around  — optional SearchAroundSpec for graph traversal
filter         — optional MemoryFilter for post-retrieval filtering
limit          — max results (1–100, default 10)
include_archived — whether to include archived memories (default false)
```

### Search pipeline

1. **FTS5 keyword search** — `SELECT rowid FROM memories_fts WHERE content MATCH ?`
   using BM25 ranking.
2. **Vector search** — `SELECT id FROM memories ORDER BY vec_distance_cosine(embedding, ?) LIMIT ?`
   using sqlite-vec.
3. **Merge** — union of FTS5 and vector results, deduplicated by `id`.
4. **Filter** — apply `MemoryFilter` predicates.
5. **Score** — compute `effective_score` for each candidate.
6. **Search-around** (if `SearchAroundSpec` is present) — see §11.1.
7. **Sort** by `effective_score DESC`.
8. **Limit** and return as `SearchResponse`.

### 11.1 SearchAroundSpec — graph traversal

`SearchAroundSpec` enables "search in search OR scoped by relationships":

```
link_types    — list of ConceptLinkType to traverse (empty = all)
depth         — max hops from anchor memories (1–3)
min_strength  — minimum link strength to follow (0.0–1.0)
```

**Algorithm:**

Phase 1: run the standard search pipeline to find anchor memories.

Phase 2: from each anchor, traverse `concept_links` up to `depth` hops:

```sql
WITH RECURSIVE traversal(id, depth) AS (
    SELECT source_memory_id, 0 FROM concept_links
    WHERE target_memory_id IN ({anchor_ids})
      AND ({link_type_filter})
      AND strength >= {min_strength}
    UNION ALL
    SELECT cl.source_memory_id, t.depth + 1
    FROM concept_links cl
    JOIN traversal t ON cl.target_memory_id = t.id
    WHERE t.depth < {max_depth}
      AND ({link_type_filter})
      AND cl.strength >= {min_strength}
)
SELECT DISTINCT id FROM traversal
```

Phase 3: result = anchors UNION traversed_memories. The `SearchResponse`
includes `search_around_ids` listing the IDs that came from graph traversal
(not from the base query), so callers can distinguish.

**OR semantics:** the base query results are always included even if
`search_around` adds nothing. Graph traversal augments; it does not filter.

---

## 12. MCP Tools

The MCP server exposes these tools. All accept and return JSON.

| Tool | Description | Key parameters |
|---|---|---|
| `memory_add` | Add a new memory | `content`, `category`, `source?`, `metadata?` |
| `memory_search` | Search memories | `query`, `limit?`, `filter?`, `search_around?` |
| `memory_get` | Get by ID | `id` |
| `memory_update` | Update fields | `id`, any updatable field |
| `memory_archive` | Archive a memory | `id` |
| `memory_feedback` | Submit session feedback | `session_id`, `useful_ids`, `stale_ids`, `confidence_rating?`, `reasoning?` |
| `memory_stats` | Get system stats | (none) |

The MCP server is built with `fastmcp`. The same tool definitions are
accessible via:
- `mcp run` (stdio, for Claude Code)
- `mcp run --transport sse --port 8001` (SSE, for Open WebUI)
- Mounted inside FastAPI at `/mcp` (HTTP MCP)

---

## 13. HTTP API (REST)

All routes conform to `docs/openapi/mintmory.yaml`.

| Method | Path | Description |
|---|---|---|
| POST | `/memories` | Add a memory |
| GET | `/memories/{id}` | Get by ID |
| PATCH | `/memories/{id}` | Update fields |
| DELETE | `/memories/{id}` | Archive |
| GET | `/memories` | List with filter |
| POST | `/search` | Search (full SearchRequest) |
| POST | `/sessions` | Create query session |
| POST | `/sessions/{id}/feedback` | Submit feedback |
| GET | `/sessions/{id}` | Get session + results |
| POST | `/dream` | Trigger a dream run |
| GET | `/stats` | Get MemoryStats |

---

## 14. MemoryStats

Returned by `GET /stats` and the `memory_stats` MCP tool:

```json
{
  "total_memories": 1000,
  "active": 940,
  "stale": 45,
  "archived": 15,
  "concept_links": 3200,
  "memory_summaries": 87,
  "avg_usefulness_score": 3.2,
  "avg_staleness_score": 1.1,
  "top_concepts": [
    ["parking integration", 23],
    ["deploy freeze", 17],
    ["auth module", 14]
  ]
}
```

`top_concepts` is sorted by frequency (number of memories sharing the concept)
and truncated to the top 20.

---

## 15. Embedding Provider

Pluggable via `EmbeddingProvider` enum:

| Provider | Value | Model | Dimension | Notes |
|---|---|---|---|---|
| Local (default) | `local` | all-MiniLM-L6-v2 | 384 | No API key needed; ~90 MB download |
| OpenAI | `openai` | text-embedding-3-small | 1536 | Requires `OPENAI_API_KEY` |
| Anthropic | `anthropic` | (future) | TBD | Not yet implemented |

Provider is configured at `StorageAdapter` initialisation time. Switching
providers invalidates existing embeddings (different dimensions). A migration
script (`scripts/reembed.py`) re-embeds all memories with the new provider.

The `EmbedderProtocol` (defined in `embedder.py`) allows injecting a mock
embedder in tests:

```python
class EmbedderProtocol(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...
```

---

## 16. Configuration

All configuration via environment variables or a `mintmory.toml` file. Key
settings:

| Variable | Default | Description |
|---|---|---|
| `MINTMORY_DB_PATH` | `~/.mintmory/memory.db` | SQLite database path |
| `MINTMORY_EMBEDDING_PROVIDER` | `local` | `local`, `openai`, `anthropic` |
| `OPENAI_API_KEY` | (none) | Required for `openai` provider |
| `MINTMORY_DREAM_INTERVAL_HOURS` | `6` | How often `run_dreamd.py` runs |
| `MINTMORY_STALENESS_THRESHOLD` | `7.0` | Score at which `is_stale` is set |
| `MINTMORY_ARCHIVE_THRESHOLD` | `9.0` | Score at which archival happens |
| `MINTMORY_FTS_WEIGHT` | `0.5` | Weight of FTS score in merged ranking |
| `MINTMORY_VEC_WEIGHT` | `0.5` | Weight of vector score in merged ranking |
| `MINTMORY_MCP_PORT` | `8001` | Port for SSE transport |
| `MINTMORY_API_PORT` | `8000` | Port for HTTP REST server |

---

## Appendix A: Known Errors in v1.0 Draft (for reference)

This section documents what was wrong in the original research draft so that
future contributors do not re-introduce these mistakes.

### A.1 Wrong contradiction prompt field names

The v1.0 draft had:
```json
{ "is_contradiction": true, "contradicts_memory_ids": ["mem_abc"] }
```

The correct schema (verified against widemem/retrieval/prompts.py) is:
```json
{ "has_conflict": true, "conflicts": [{"existing_memory_id": "mem_abc", ...}] }
```

This matters because any code parsing the LLM's JSON response with the wrong
field names will silently fail to detect contradictions.

### A.2 Only 4 ConceptLink types

The v1.0 draft listed: `relates_to`, `contradicts`, `refines`, `supersedes`.

The correct set is 11 types: adds `enables`, `depends_on`, `similar_to`,
`part_of`, `uses`, `before`, `valid_until`.

The missing types cover temporal relationships (`before`, `valid_until`),
compositional relationships (`part_of`, `uses`), causal relationships
(`enables`, `depends_on`), and similarity (`similar_to`).

### A.3 Wrong schema (5 tables, missing query_results)

The v1.0 draft had 5 tables and omitted `query_results`. The correct schema
has 6 tables:
```
memories, memories_fts, concept_links, memory_summaries,
query_sessions, query_results
```

`query_results` is essential for the passive feedback loop — without it,
there is no record of which specific memories were retrieved in a session.

### A.4 Scoring formula not specified

The v1.0 draft mentioned "a composite score" without specifying the formula.
The correct formula is in §6 of this document.
