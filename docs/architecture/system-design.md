# MintMory System Design Document

**Version:** 1.0  
**Date:** 2026-06-15  
**Status:** Authoritative — Sonnet agents implementing tasks must read this document before writing code.  
**Ground truth files:** `packages/core/src/mintmory_core/types.py`, `packages/core/src/mintmory_core/schema.sql`

---

## 1. Overview

MintMory is a **Palantir-Ontology-inspired typed memory system for LLM agents**. It stores memories as typed objects connected by typed directed links, searches them via hybrid full-text + vector similarity, and autonomously maintains graph consistency via a background dreaming process.

### Design Goals

| Goal | How Achieved |
|------|-------------|
| Zero external dependencies | SQLite + sqlite-vec only; local sentence-transformers |
| Three transport surfaces | stdio (CLI), MCP via fastmcp, HTTP REST via FastAPI |
| Typed semantics | 8 memory categories × 11 link types (Palantir Ontology model) |
| Self-maintaining | Dreaming daemon: light every 30 min, full every 6 h |
| LLM-driven feedback | QuerySession + passive self-assessment (useful/stale/confidence) |
| Portability | Single `~/.mintmory/memory.db` file; `cp` = backup |

### Non-Goals (v1)

- Multi-node replication or sharding
- >500k memories (see vector search ceiling in ADR-0002)
- Real-time WebSocket push notifications
- Fine-tuned classification models (dreaming uses prompt-engineered LLM calls)

---

## 2. Palantir Ontology Mapping

This table is the single authoritative reference for the conceptual model. Every function, table, and enum in the codebase maps to one cell in this table.

| Palantir Concept | MintMory Implementation | Python Type | SQLite Storage |
|-----------------|------------------------|-------------|----------------|
| Object Type | `MemoryCategory` | `MemoryCategory(str, Enum)` in `types.py` | `memories.category TEXT` |
| Object Instance | `Memory` | `@dataclass Memory` in `types.py` | Row in `memories` table |
| Object Property | Memory fields | Typed dataclass fields | SQLite columns |
| Link Type | `ConceptLinkType` | `ConceptLinkType(str, Enum)` in `types.py` | `concept_links.link_type TEXT` |
| Link Instance | `ConceptLink` | `@dataclass ConceptLink` in `types.py` | Row in `concept_links` table |
| Link Property | `strength`, `confidence`, `created_by` | Typed dataclass fields | SQLite columns |
| Action Type | Dreaming operations | Async functions in `dreaming.py` | Executed in transactions |
| Decision Lineage | `QuerySession` | `@dataclass QuerySession` in `types.py` | Row in `query_sessions` table |

### Memory Categories (Object Types)

```
identity    preference    skill    context
fact        episodic      temporal  relationship
```

Decay rates ordered slowest → fastest:
`identity (0.0001) < skill (0.002) < preference (0.005) < relationship (0.008) < fact (0.01) < episodic (0.02) < preference (0.005) < context (0.05) < temporal (0.1)`

### ConceptLink Types (Link Types)

```
Associative:  relates_to   similar_to
Epistemic:    contradicts  refines    supersedes
Causal:       enables      depends_on  uses
Compositional: part_of
Temporal:     before       valid_until
```

---

## 3. Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          MintMory System                                 │
│                                                                           │
│  ┌─────────────┐    ┌──────────────────┐    ┌──────────────────────┐    │
│  │  CLI        │    │  MCP Server      │    │  FastAPI HTTP        │    │
│  │ (stdio)     │    │  (fastmcp)       │    │  REST API            │    │
│  │             │    │                  │    │                      │    │
│  │ mintmory-cli│    │ mintmory-mcp     │    │ mintmory-api         │    │
│  │ (Typer)     │    │ FastMCP app      │    │ FastAPI app          │    │
│  └──────┬──────┘    └────────┬─────────┘    └──────────┬───────────┘    │
│         │                   │                          │                 │
│         └───────────────────┴──────────────────────────┘                │
│                             │                                            │
│                    ┌────────▼─────────┐                                  │
│                    │  mintmory-core   │                                  │
│                    │                  │                                  │
│                    │  ┌────────────┐  │                                  │
│                    │  │MemoryStore │  │  ← domain facade                │
│                    │  └─────┬──────┘  │                                  │
│                    │        │         │                                  │
│                    │  ┌─────▼──────┐  │  ┌──────────────────────────┐  │
│                    │  │  DB Layer  │  │  │  Embedding Pipeline      │  │
│                    │  │ (db.py)    │  │  │                          │  │
│                    │  │            │  │  │  EmbedderProtocol        │  │
│                    │  │  SQLite    │◄─┼──┤  LocalEmbedder (default) │  │
│                    │  │  WAL mode  │  │  │  OpenAIEmbedder (opt.)   │  │
│                    │  │            │  │  └──────────────────────────┘  │
│                    │  │  ┌───────┐ │  │                                  │
│                    │  │  │FTS5   │ │  │  ┌──────────────────────────┐  │
│                    │  │  │index  │ │  │  │  Dreaming Daemon         │  │
│                    │  │  └───────┘ │  │  │  (dreamd.py)             │  │
│                    │  │  ┌───────┐ │  │  │                          │  │
│                    │  │  │vec0   │ │  │  │  asyncio.TaskGroup       │  │
│                    │  │  │index  │ │  │  │  light: 30 min interval  │  │
│                    │  │  └───────┘ │  │  │  full:   6 h interval    │  │
│                    │  └────────────┘  │  └──────────────────────────┘  │
│                    └──────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────────┘

External agents / users:
  Claude Code ──MCP stdio──► mintmory-mcp
  External service ──HTTP──► mintmory-api
  Developer ──shell──► mintmory-cli
```

---

## 4. Storage Layout

All schema is authoritative in `packages/core/src/mintmory_core/schema.sql`. The tables below are the summary.

### Tables

#### `memories` — Core Object Store

```sql
CREATE TABLE memories (
    id            TEXT PRIMARY KEY,          -- UUID v4, e.g. "a1b2c3d4-..."
    content       TEXT NOT NULL,             -- raw text, max 4096 chars
    category      TEXT NOT NULL,             -- MemoryCategory enum value
    importance    REAL NOT NULL DEFAULT 0.5, -- [0.0, 1.0]
    confidence    REAL NOT NULL DEFAULT 1.0, -- [0.0, 1.0]
    decay_rate    REAL NOT NULL DEFAULT 0.01,-- per-day exponential coefficient
    access_count  INTEGER NOT NULL DEFAULT 0,
    has_conflict  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TEXT NOT NULL,             -- ISO-8601 UTC
    last_accessed TEXT,
    expires_at    TEXT,                      -- NULL = no expiry
    source_session TEXT REFERENCES query_sessions(id),
    metadata      TEXT                       -- JSON blob
);
```

#### `memories_fts` — Full-Text Search Virtual Table

```sql
CREATE VIRTUAL TABLE memories_fts USING fts5(
    content,
    content=memories,
    content_rowid=rowid,
    tokenize='porter ascii'
);

-- Triggers to keep FTS in sync:
CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content)
    VALUES('delete', old.rowid, old.content);
END;
CREATE TRIGGER memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content)
    VALUES('delete', old.rowid, old.content);
    INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
END;
```

#### `concept_links` — Typed Edge Table

```sql
CREATE TABLE concept_links (
    id          TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_id   TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    link_type   TEXT NOT NULL,              -- ConceptLinkType enum value
    strength    REAL NOT NULL DEFAULT 1.0,
    confidence  REAL NOT NULL DEFAULT 1.0,
    created_by  TEXT NOT NULL DEFAULT 'dreaming',
    created_at  TEXT NOT NULL,
    metadata    TEXT                        -- JSON: includes LLM rationale
);
```

#### `memory_vectors` — Dense Vector Index

```sql
-- Created with dimension from embedder.dimensions (384 for local, 1536 for OpenAI)
CREATE VIRTUAL TABLE memory_vectors USING vec0(
    memory_id TEXT PRIMARY KEY,
    embedding FLOAT[384]
);
```

#### `query_sessions` — Decision Lineage

```sql
CREATE TABLE query_sessions (
    id                TEXT PRIMARY KEY,
    query_text        TEXT NOT NULL,
    retrieved_ids     TEXT,               -- JSON array, all retrieved memory IDs
    created_at        TEXT NOT NULL,
    useful_ids        TEXT,               -- JSON array, LLM-assessed useful
    stale_ids         TEXT,               -- JSON array, LLM-assessed stale/wrong
    confidence_rating REAL,               -- LLM self-rating [0.0, 1.0]
    closed_at         TEXT
);
```

#### `schema_meta` — Configuration Validation

```sql
CREATE TABLE schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Initial rows: embedding_model, embedding_dims, schema_version
```

### Indexes

```sql
CREATE INDEX idx_memories_category    ON memories(category);
CREATE INDEX idx_memories_importance  ON memories(importance DESC);
CREATE INDEX idx_memories_decay       ON memories(decay_rate, last_accessed);
CREATE INDEX idx_memories_expires     ON memories(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_memories_conflict    ON memories(has_conflict) WHERE has_conflict = TRUE;
CREATE INDEX idx_links_source         ON concept_links(source_id, link_type);
CREATE INDEX idx_links_target         ON concept_links(target_id, link_type);
CREATE INDEX idx_links_type           ON concept_links(link_type, strength DESC);
```

---

## 5. Transport Layer

### 5.1 MCP Transport (Primary — LLM Agents)

The MCP server (`packages/mcp/`) uses `fastmcp` and exposes tools that Claude Code and other MCP-capable LLM hosts call directly.

**Startup (stdio):**

```bash
# In claude_desktop_config.json or .mcp.json:
{
  "mcpServers": {
    "mintmory": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/MintMory", "mintmory-mcp"]
    }
  }
}
```

**Core MCP Tools:**

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `store_memory` | Store a new memory | `content`, `category`, `importance`, `metadata` |
| `retrieve_memories` | Hybrid search + graph traversal | `query`, `category_filter`, `limit`, `session_id` |
| `search_around` | Expand from anchor memories via links | `memory_ids`, `link_types`, `depth`, `limit` |
| `create_link` | Assert an explicit link | `source_id`, `target_id`, `link_type`, `strength` |
| `close_session` | Submit LLM self-assessment | `session_id`, `useful_ids`, `stale_ids`, `confidence_rating` |
| `get_memory` | Retrieve a single memory by ID | `memory_id` |
| `update_memory` | Update content or metadata | `memory_id`, `content`, `importance` |
| `list_memories` | Paginated listing by category | `category`, `limit`, `offset` |
| `dream_status` | Check dreaming daemon state | (none) |

### 5.2 HTTP REST Transport (External Services)

The FastAPI app (`packages/api/`) mounts the same domain functions as the MCP server. Route prefix: `/api/v1`.

**Key Routes:**

```
POST   /api/v1/memories              → store_memory
GET    /api/v1/memories/search       → retrieve_memories (query params)
GET    /api/v1/memories/{id}         → get_memory
PATCH  /api/v1/memories/{id}         → update_memory
DELETE /api/v1/memories/{id}         → archive memory (soft delete)
POST   /api/v1/memories/search-around → search_around
GET    /api/v1/links                 → list links (filtered)
POST   /api/v1/links                 → create_link
POST   /api/v1/sessions              → open query session
PATCH  /api/v1/sessions/{id}/close  → close_session
GET    /api/v1/dream/status          → dream_status
POST   /api/v1/dream/trigger         → trigger immediate dream (admin)
```

### 5.3 stdio / CLI Transport (Developer)

The CLI (`packages/cli/`) uses Typer and calls `MemoryStore` directly in-process (no network hop).

```bash
mintmory store "Python 3.12 requires GIL" --category fact --importance 0.8
mintmory search "GIL Python" --limit 5
mintmory dream --type light
mintmory show <memory_id>
mintmory links list --source <memory_id>
mintmory session close <session_id> --useful id1,id2 --stale id3
```

---

## 6. Dreaming Process

The dreaming daemon (`packages/core/src/mintmory_core/dreamd.py`) runs as a background `asyncio.TaskGroup` coroutine. It is started by both `mintmory-mcp` and `mintmory-api` on server startup. The CLI triggers dreaming synchronously via `mintmory dream`.

### Light Dream (Every 30 Minutes, ~2–10 s)

**Step 1: Anomaly Detection**
- Query memories where `importance < 0.1 AND access_count = 0 AND created_at < now() - 7 days`
- Flag them `has_conflict = TRUE` with metadata `{"anomaly": "orphaned_low_importance"}`
- Also: find memories where `expires_at < now()` and mark `category = 'temporal'` for archival

**Step 2: Orphan Linking**
- Find memories with no incoming or outgoing `concept_links` rows (orphan nodes)
- Embed each orphan and run KNN search (k=10) against `memory_vectors`
- For pairs with cosine similarity > 0.75: create `similar_to` link (strength = cosine score)
- For pairs where the new memory's content semantically updates the old (detected via LLM prompt): create `supersedes` or `refines` link

**Step 3: Summary Generation**
- For each `category` with >20 memories and no existing summary: generate a synthetic summary memory
- Category: `fact`; content: LLM-generated summary of the cluster; `importance = 0.9`; `metadata: {"generated_by": "dreaming", "covers_ids": [...]}`

### Full Dream (Every 6 Hours, ~30–120 s)

Runs all 3 light dream steps, then:

**Step 4: Contradiction Resolution**
- Query `SELECT * FROM memories WHERE has_conflict = TRUE` joined to `concept_links WHERE link_type = 'contradicts'`
- Batch into LLM prompt (max 5 conflict pairs per call): structured prompt with both memory contents + conflict type
- LLM returns one of: `{"action": "supersede", "keep_id": "...", "archive_id": "..."}` | `{"action": "merge", "new_content": "..."}` | `{"action": "coexist", "rationale": "..."}`
- Apply action atomically in a single SQLite transaction

**Step 5: Archival**
- Compute effective importance score for all memories (see Scoring Formula, section 8)
- Archive memories where `effective_score < 0.05 AND category NOT IN ('identity', 'skill')`
- Archival = set `metadata.archived = true`, `metadata.archived_at = now()`, remove from `memory_vectors` (to save vector scan time)
- Archived memories remain queryable via `GET /api/v1/memories/{id}` but not returned by search

**Step 6: Rehabilitation**
- Query archived memories with `access_count` increments (LLM or user explicitly referenced them)
- If an archived memory has been explicitly fetched >2 times since archival: un-archive, re-embed, re-insert into `memory_vectors`
- This models the FSFM "rehabilitation" tier in the forgetting taxonomy

### Dreaming State Machine

```
              ┌─────────────────────────────────┐
              │                                 │
   startup ──►│  IDLE (waiting for interval)    │
              │                                 │
              └──────────────┬──────────────────┘
                             │ interval fires
                             ▼
              ┌─────────────────────────────────┐
              │  RUNNING (light or full)         │
              │                                 │
              │  Step 1: Anomaly Detection       │
              │  Step 2: Orphan Linking          │
              │  Step 3: Summary Generation      │
              │  [full only:]                   │
              │  Step 4: Contradiction Resolve   │
              │  Step 5: Archival                │
              │  Step 6: Rehabilitation          │
              └──────────────┬──────────────────┘
                             │
                    ┌────────┴────────┐
                    │ success         │ error
                    ▼                 ▼
              ┌──────────┐    ┌───────────────┐
              │  IDLE    │    │ ERROR (logged) │
              │          │    │ retry next     │
              └──────────┘    │ interval       │
                              └───────────────┘
```

---

## 7. Search-Around Query Model

The `search_around` operation is the graph traversal primitive. It starts from one or more **anchor memories** and expands along typed `concept_links` to return a semantically enriched result set.

### SQL Implementation

```sql
-- Parameters:
--   :anchor_ids  → JSON array of seed memory IDs, e.g. '["id1","id2"]'
--   :link_types  → JSON array of link types to follow, e.g. '["enables","depends_on"]'
--   :depth       → integer, max traversal hops (1 or 2 in v1)
--   :limit       → integer, max total results

WITH anchor_memories AS (
    -- Start: the explicitly requested memories
    SELECT
        m.id,
        m.content,
        m.category,
        m.importance,
        m.confidence,
        m.decay_rate,
        m.last_accessed,
        m.has_conflict,
        m.expires_at,
        m.metadata,
        0       AS hop,
        1.0     AS traversal_strength,
        NULL    AS via_link_type,
        m.id    AS anchor_id
    FROM memories m
    WHERE m.id IN (SELECT value FROM json_each(:anchor_ids))
),

one_hop AS (
    -- Hop 1: follow outgoing links from anchors
    SELECT
        m.id,
        m.content,
        m.category,
        m.importance,
        m.confidence,
        m.decay_rate,
        m.last_accessed,
        m.has_conflict,
        m.expires_at,
        m.metadata,
        1               AS hop,
        cl.strength     AS traversal_strength,
        cl.link_type    AS via_link_type,
        a.id            AS anchor_id
    FROM anchor_memories a
    JOIN concept_links cl
        ON cl.source_id = a.id
        AND (
            json_array_length(:link_types) = 0
            OR cl.link_type IN (SELECT value FROM json_each(:link_types))
        )
    JOIN memories m ON m.id = cl.target_id
    WHERE m.id NOT IN (SELECT id FROM anchor_memories)
),

two_hop AS (
    -- Hop 2: follow links from hop-1 results (only when :depth >= 2)
    SELECT
        m.id,
        m.content,
        m.category,
        m.importance,
        m.confidence,
        m.decay_rate,
        m.last_accessed,
        m.has_conflict,
        m.expires_at,
        m.metadata,
        2                                       AS hop,
        cl.strength * h1.traversal_strength    AS traversal_strength,
        cl.link_type                            AS via_link_type,
        h1.anchor_id                            AS anchor_id
    FROM one_hop h1
    JOIN concept_links cl
        ON cl.source_id = h1.id
        AND (
            json_array_length(:link_types) = 0
            OR cl.link_type IN (SELECT value FROM json_each(:link_types))
        )
    JOIN memories m ON m.id = cl.target_id
    WHERE m.id NOT IN (SELECT id FROM anchor_memories)
      AND m.id NOT IN (SELECT id FROM one_hop)
      AND :depth >= 2
),

all_results AS (
    SELECT * FROM anchor_memories
    UNION ALL
    SELECT * FROM one_hop
    UNION ALL
    SELECT * FROM two_hop
)

SELECT
    id,
    content,
    category,
    importance,
    confidence,
    decay_rate,
    last_accessed,
    has_conflict,
    expires_at,
    metadata,
    hop,
    traversal_strength,
    via_link_type,
    anchor_id,
    -- Composite rank: anchor memories first, then by hop and strength
    (1.0 - hop * 0.3) * traversal_strength * importance AS rank_score
FROM all_results
WHERE (metadata IS NULL OR json_extract(metadata, '$.archived') IS NULL)
ORDER BY rank_score DESC
LIMIT :limit;
```

### Hybrid Search (FTS5 + Vector)

The standard `retrieve_memories` call runs both FTS5 and vector search and merges results by score:

```sql
-- Step 1: FTS5 keyword recall (returns bm25 scores)
SELECT m.id, bm25(memories_fts) AS fts_score
FROM memories_fts
JOIN memories m ON m.rowid = memories_fts.rowid
WHERE memories_fts MATCH :query_fts
  AND (json_array_length(:categories) = 0
       OR m.category IN (SELECT value FROM json_each(:categories)))
ORDER BY fts_score
LIMIT :fts_limit;

-- Step 2: Vector KNN (runs via sqlite-vec, Python-side)
-- SELECT memory_id, distance FROM memory_vectors
-- WHERE embedding MATCH :query_vec AND k = :vec_limit
-- ORDER BY distance;

-- Step 3: Merge in Python (RRF — Reciprocal Rank Fusion)
-- final_score(id) = 1/(k + fts_rank) + 1/(k + vec_rank)
-- where k=60 (standard RRF constant)
-- Deduplicate, sort by final_score DESC, return top :limit
```

---

## 8. Embedding Pipeline

### Store Path

```
caller: store_memory(content, category, ...)
  │
  ├─ validate content (non-empty, max 512 tokens)
  ├─ truncate to 512 tokens if needed (log warning)
  ├─ generate UUID v4 → memory_id
  ├─ INSERT INTO memories (id, content, category, ...)
  ├─ FTS5 trigger fires automatically → memories_fts updated
  ├─ embedder.embed(content) → np.ndarray shape (dims,)
  ├─ INSERT INTO memory_vectors (memory_id, embedding)
  └─ return memory_id
```

### Query Path

```
caller: retrieve_memories(query, category_filter, limit)
  │
  ├─ open QuerySession → session_id
  ├─ embedder.embed(query) → query_vec
  ├─ FTS5 search: bm25 scores for top 50 results
  ├─ Vector KNN: top 50 by cosine distance
  ├─ RRF merge → top :limit results
  ├─ increment access_count for returned memories
  ├─ record retrieved_ids in query_sessions
  └─ return memories + session_id
```

### Batch Embedding (Dreaming)

During orphan linking, the dreaming process embeds multiple memories at once:

```python
orphan_contents = [m.content for m in orphan_memories]
vectors = embedder.embed_batch(orphan_contents)  # single model.encode() call
# sqlite-vec supports batch upsert via executemany:
conn.executemany(
    "INSERT OR REPLACE INTO memory_vectors(memory_id, embedding) VALUES (?, ?)",
    [(m.id, v.tobytes()) for m, v in zip(orphan_memories, vectors)]
)
```

---

## 9. Scoring Formula

The **effective importance score** determines which memories are surfaced in search and which are archived. It combines:

1. **Base importance** (`I` ∈ [0, 1]): set at store time, adjusted by session feedback
2. **Temporal decay** (`D`): exponential decay using `decay_rate` and days since `last_accessed`
3. **Recency boost** (`R`): access frequency reward
4. **Confidence** (`C` ∈ [0, 1]): degraded by conflict flags

### Formula

```
effective_score = I × C × exp(-decay_rate × days_since_access) × (1 + log1p(access_count) × 0.1)
```

Where:
- `days_since_access = (now - last_accessed).days` (0 if never accessed = created_at used)
- `log1p(access_count) × 0.1` is the recency boost (caps at ~0.23 for 10 accesses)
- `C` is reduced to `0.5` if `has_conflict = TRUE` and the memory has an unresolved `contradicts` link

### SQL Equivalent (used in dreaming archival query)

```sql
SELECT
    id,
    importance
    * confidence
    * exp(-decay_rate * CAST(
          (julianday('now') - julianday(COALESCE(last_accessed, created_at)))
          AS REAL))
    * (1.0 + log(1.0 + access_count) * 0.1)
    * CASE WHEN has_conflict = TRUE THEN 0.5 ELSE 1.0 END
    AS effective_score
FROM memories
WHERE metadata IS NULL OR json_extract(metadata, '$.archived') IS NULL
ORDER BY effective_score ASC;
```

This formula is borrowed from widemem's exponential decay approach, extended with the confidence penalty and access frequency boost.

### Session Feedback Adjustment

When `close_session` is called:
- For each `id` in `useful_ids`: `UPDATE memories SET importance = MIN(1.0, importance + 0.05), access_count = access_count + 1`
- For each `id` in `stale_ids`: `UPDATE memories SET has_conflict = TRUE, importance = MAX(0.0, importance - 0.1)`
- If `confidence_rating < 0.5`: batch all retrieved memories' confidences down by 0.05

---

## 10. Measurement Framework

MintMory tracks its own effectiveness to feed back into dreaming and scoring.

### Metrics Collected

| Metric | Source | Aggregation |
|--------|--------|-------------|
| Session useful rate | `query_sessions.useful_ids` length / `retrieved_ids` length | Per-day rolling mean |
| Session stale rate | `query_sessions.stale_ids` length / `retrieved_ids` length | Per-day rolling mean |
| Mean confidence rating | `query_sessions.confidence_rating` | Per-category mean |
| Dreaming link creation rate | `concept_links` rows with `created_by='dreaming'` | Per-dream-cycle count |
| Contradiction resolution rate | Resolved `contradicts` links / total `contradicts` links | Per-full-dream |
| Archival rate | Archived memories / total memories | Per-full-dream |
| Vector search latency | Timed in `MemoryStore.retrieve()` | p50, p95 ms |
| FTS search latency | Timed in `MemoryStore.retrieve()` | p50, p95 ms |

### Dashboard Query

```sql
-- Summary stats for the measurement dashboard:
SELECT
    COUNT(*) AS total_memories,
    SUM(CASE WHEN metadata IS NOT NULL
             AND json_extract(metadata, '$.archived') IS NOT NULL THEN 1 ELSE 0 END) AS archived,
    SUM(CASE WHEN has_conflict = TRUE THEN 1 ELSE 0 END) AS conflicted,
    AVG(importance) AS avg_importance,
    AVG(confidence) AS avg_confidence,
    category,
    COUNT(*) AS category_count
FROM memories
GROUP BY category;

-- Session effectiveness:
SELECT
    DATE(created_at) AS day,
    COUNT(*) AS sessions,
    AVG(
        CASE WHEN useful_ids IS NOT NULL AND retrieved_ids IS NOT NULL
             THEN json_array_length(useful_ids) * 1.0 / NULLIF(json_array_length(retrieved_ids), 0)
             ELSE NULL END
    ) AS avg_useful_rate,
    AVG(confidence_rating) AS avg_confidence
FROM query_sessions
WHERE closed_at IS NOT NULL
GROUP BY day
ORDER BY day DESC
LIMIT 30;
```

### YMYL Classifier (Phase 2)

Borrowed from widemem: memories tagged `category='fact'` with content matching a YMYL pattern (health, finance, legal) are assigned `confidence = 0.5` at store time and require explicit confirmation before being returned with `importance > 0.8`. Implementation is gated behind a config flag `[safety] ymyl_classifier = true` (default: false in v1).

---

## 11. Implementation Notes for Sonnet Agents

These are concrete conventions that all task-implementing agents must follow:

### File Layout

```
packages/core/src/mintmory_core/
  __init__.py
  types.py          ← all dataclasses and enums (ground truth)
  schema.sql        ← DDL (ground truth)
  db.py             ← connection management, PRAGMA setup, sqlite-vec load
  store.py          ← MemoryStore facade (all domain operations)
  embeddings.py     ← EmbedderProtocol + LocalEmbedder + OpenAIEmbedder
  dreaming.py       ← all 6 dreaming steps as async functions
  dreamd.py         ← asyncio daemon loop
  scoring.py        ← effective_score() Python function
  config.py         ← pydantic-settings config model

packages/mcp/src/mintmory_mcp/
  __init__.py
  server.py         ← FastMCP app + all @mcp.tool() decorators
  __main__.py       ← entry point: server.mcp.run()

packages/api/src/mintmory_api/
  __init__.py
  main.py           ← FastAPI app factory
  routes/
    memories.py
    links.py
    sessions.py
    dream.py
  deps.py           ← FastAPI dependency injection (MemoryStore singleton)

packages/cli/src/mintmory_cli/
  __init__.py
  main.py           ← Typer app
  __main__.py
```

### Testing Conventions

- Every function in `store.py` has a unit test using an in-memory SQLite DB (`":memory:"`)
- MCP tool tests use `fastmcp.testing.MCPTestClient`
- API route tests use `httpx.AsyncClient` with `app` fixture
- Dreaming tests use a `FakeEmbedder` that returns deterministic unit vectors
- Integration tests in `tests/` use a real `tmp_path` SQLite file and real `LocalEmbedder`

### Error Handling Conventions

- Domain errors: raise `MintMoryError` subclasses defined in `types.py`
- MCP tool errors: caught by fastmcp and returned as MCP error responses (do not let unhandled exceptions propagate)
- Dreaming errors: logged at ERROR level, daemon continues to next cycle (never crash the daemon)
- DB errors: let SQLite `OperationalError` propagate to the MCP/API layer; it will surface as a 500 or MCP error

### Concurrency Conventions

- `MemoryStore` is **not** thread-safe. Callers must hold the `threading.Lock` exported from `db.py` before calling any write method.
- The dreaming daemon acquires the same lock for the duration of each dream step.
- FastAPI uses a single-worker process in development; production `uvicorn` with `--workers 1` (SQLite single-writer constraint).
- MCP stdio transport is inherently single-threaded (one JSON-RPC request at a time over stdio).

---

## 12. Open Questions / Future Work

| Item | Status | Notes |
|------|--------|-------|
| spaCy entity extraction (Phase 2) | Deferred | Mem0-inspired; adds 4-type NER to auto-tag `relationship` memories |
| DuckDB backend | Deferred | For >500k memory deployments; requires `StorageBackend` protocol |
| Multi-agent shared memory | Deferred | Requires Postgres backend + conflict-free replicated data types |
| YMYL classifier | Deferred | Phase 2; config flag exists in schema |
| Web UI (memory graph visualiser) | Deferred | pnpm workspace alongside Python monorepo |
| Embedding fine-tuning | Deferred | Domain-specific fine-tune of all-MiniLM on agent memory content |
| `after` link type | Deferred | Inverse of `before`; omitted from v1 to reduce LLM classification burden; `before` is bidirectionally queryable |

---

*This document is the primary reference for all implementation tasks. If a detail in this document conflicts with a task brief, this document wins. If this document conflicts with `types.py` or `schema.sql`, those source files win (they are the ground truth).*
