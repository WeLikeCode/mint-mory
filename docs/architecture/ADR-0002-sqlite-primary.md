# ADR-0002: SQLite + sqlite-vec as the Sole Storage Engine

**Status:** Accepted  
**Date:** 2026-06-15  
**Deciders:** MintMory core team  
**Supersedes:** (none — primary storage decision)

---

## Context

MintMory needs to persist four categories of data simultaneously:

1. **Memory objects** — typed, categorised text blobs with metadata (importance, decay, timestamps)
2. **ConceptLinks** — typed directed edges between memories with metadata (strength, confidence, created_by)
3. **Dense vectors** — 384-dim float32 embeddings for similarity search
4. **Full-text search indexes** — keyword recall on memory content for hybrid search

Additionally, the **dreaming process** needs to run complex multi-table SQL queries (join memories → links → contradictions, aggregate by category, rank by decay score) that are natural in relational SQL but painful across a graph DB + vector DB combination.

### Portability Goal

MintMory must be fully self-contained and portable: a single `~/.mintmory/memory.db` file is the entire knowledge base. No daemon processes (Postgres, Redis, Chroma, Qdrant) must be running for basic operation. This makes it deployable inside a Claude Code hook, a CI runner, or a Docker container without a compose file.

### Prior Art Failures Observed

The `widemem` reference implementation (examined during research) used **FAISS** (in-process C++ library) as its vector store alongside SQLite for metadata:

- **WM-1:** FAISS index serialisation to disk was done via `faiss.write_index` on process exit. A SIGKILL during dreaming left the FAISS `.index` file and the SQLite metadata file in diverged state — memories existed in SQLite with no corresponding vector, causing silent retrieval failures.
- **WM-2:** FAISS does not support deletion by ID without a full index rebuild. When `widemem` archived old memories, the vector slots became orphaned stale entries that skewed cosine similarity results for months.

Both bugs stem from the two-database split. A single file eliminates the consistency boundary.

### Alternatives Considered

| Option | Portability | SQL Dreaming | Vector Search | Durability | Verdict |
|--------|-------------|--------------|---------------|------------|---------|
| **SQLite + sqlite-vec (chosen)** | Single file | Native | Cosine/L2 via KNN | WAL, ACID | Accepted |
| SQLite + FAISS | Single file (fragile) | Native | Fast ANN | Split state (WM-1, WM-2) | Rejected |
| SQLite + pgvector (Postgres) | Requires daemon | Native on SQLite side, foreign on PG | Excellent | Two daemons | Rejected |
| Chroma (embedded) | Python lib, no daemon | No — Chroma is key-value | Excellent | Separate `.chroma/` directory | Rejected |
| Qdrant embedded | Rust binary | No | Excellent | Separate directory | Rejected |
| DuckDB + VSS | Single file | Excellent | Good | Single file | Deferred (phase 2 alternative) |

---

## Decision

**Use SQLite (WAL mode) with the `sqlite-vec` extension as the sole storage engine.** No external vector database. No external relational database. One file.

### Storage Layout (authoritative — see `schema.sql`)

```sql
-- Core memory objects
CREATE TABLE memories (
    id          TEXT PRIMARY KEY,          -- UUID v4
    content     TEXT NOT NULL,
    category    TEXT NOT NULL,             -- one of 8 MemoryCategory values
    importance  REAL NOT NULL DEFAULT 0.5, -- [0.0, 1.0]
    confidence  REAL NOT NULL DEFAULT 1.0, -- [0.0, 1.0]
    decay_rate  REAL NOT NULL DEFAULT 0.01,-- per-day exponential decay
    access_count INTEGER NOT NULL DEFAULT 0,
    has_conflict BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TEXT NOT NULL,             -- ISO-8601 UTC
    last_accessed TEXT,
    expires_at  TEXT,                      -- NULL = no expiry
    source_session TEXT,                   -- FK → query_sessions.id (nullable)
    metadata    TEXT                       -- JSON blob for extension fields
);

-- Full-text search (FTS5, porter stemmer)
CREATE VIRTUAL TABLE memories_fts USING fts5(
    content,
    content=memories,
    content_rowid=rowid,
    tokenize='porter ascii'
);

-- Typed directed edges
CREATE TABLE concept_links (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_id       TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    link_type       TEXT NOT NULL,         -- one of 11 ConceptLinkType values
    strength        REAL NOT NULL DEFAULT 1.0,
    confidence      REAL NOT NULL DEFAULT 1.0,
    created_by      TEXT NOT NULL DEFAULT 'dreaming', -- 'dreaming' | 'llm' | 'user'
    created_at      TEXT NOT NULL,
    metadata        TEXT                   -- JSON
);

-- Dense vectors (sqlite-vec virtual table)
CREATE VIRTUAL TABLE memory_vectors USING vec0(
    memory_id TEXT PRIMARY KEY,
    embedding FLOAT[384]                   -- all-MiniLM-L6-v2 dims; change to 1536 for OpenAI
);

-- Session tracking for LLM self-assessment
CREATE TABLE query_sessions (
    id              TEXT PRIMARY KEY,
    query_text      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    useful_ids      TEXT,                  -- JSON array of memory IDs
    stale_ids       TEXT,                  -- JSON array of memory IDs
    confidence_rating REAL,               -- LLM self-assessed [0.0, 1.0]
    closed_at       TEXT
);
```

### Key Indexes

```sql
CREATE INDEX idx_memories_category   ON memories(category);
CREATE INDEX idx_memories_importance ON memories(importance DESC);
CREATE INDEX idx_memories_decay      ON memories(decay_rate, last_accessed);
CREATE INDEX idx_memories_expires    ON memories(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_concept_links_source ON concept_links(source_id, link_type);
CREATE INDEX idx_concept_links_target ON concept_links(target_id, link_type);
```

### SQLite PRAGMA Configuration

Applied at connection open time in `core/db.py`:

```python
PRAGMAS = [
    "PRAGMA journal_mode=WAL",          # concurrent reads during dreaming writes
    "PRAGMA synchronous=NORMAL",        # fsync on WAL checkpoint, not every write
    "PRAGMA foreign_keys=ON",
    "PRAGMA cache_size=-32000",         # 32 MB page cache
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=134217728",       # 128 MB mmap
]
```

WAL mode is critical: the dreaming daemon holds a write transaction for minutes during full-dream cycles while simultaneous MCP reads must not block.

---

## Rationale

### sqlite-vec vs FAISS

`sqlite-vec` is an SQLite extension that adds a `vec0` virtual table. Vectors are stored inside the SQLite WAL file alongside all other data. A KNN query looks like:

```sql
SELECT memory_id, distance
FROM memory_vectors
WHERE embedding MATCH :query_vec
  AND k = 20
ORDER BY distance;
```

Because the vector index lives in the same WAL transaction as the memory row, there is no split-state risk. Insertions, deletions, and queries are all ACID.

At 100k memories × 384 dims × 4 bytes = ~154 MB of raw vector data. SQLite handles this comfortably on a laptop; `sqlite-vec`'s flat scan is fast enough at this scale. For >500k memories, a Diskann or HNSW index can be swapped in behind the `VectorBackend` protocol seam without changing the domain layer.

### The Pluggable Backend Seam

Even though SQLite is the only storage engine today, the `StorageBackend` protocol is defined in `core/storage.py` with methods `store`, `retrieve`, `search_fts`, `search_vector`, and `execute_dreaming_query`. This seam means a future `DuckDBBackend` or `PostgresBackend` can be plugged in without changing any tool handler or API route.

---

## Consequences

### Positive

- **Zero external dependencies** for storage: `pip install mintmory-core` and you have a working system.
- **ACID dreaming:** contradiction resolution writes happen in a single SQLite transaction; on crash, the WAL rolls back consistently.
- **SQL expressiveness:** the search-around query, forgetting curve updates, and contradiction detection are all straightforward CTEs (see system-design.md).
- **Backup is `cp`:** copying `~/.mintmory/memory.db` is a complete backup.
- **FTS5 + vector in one query:** hybrid search (keyword boost + cosine similarity) joins `memories_fts` and `memory_vectors` in a single SQL query with no inter-service network hop.

### Negative / Risks

- **Vector search ceiling:** `sqlite-vec` performs a flat scan (O(n)). Measured benchmarks show ~50 ms for 100k vectors at 384 dims on Apple M-series. At 500k+ memories, response times degrade; mitigation is the `VectorBackend` seam and documentation of the threshold.
- **Concurrent writes blocked:** SQLite WAL allows one writer at a time. The dreaming daemon and an MCP `store_memory` call cannot write simultaneously without queuing. Mitigation: dreaming writes are batched in large transactions; MCP writes are sub-millisecond. A `threading.Lock` in `core/db.py` serialises access.
- **No replication:** SQLite is single-node. If MintMory is ever deployed as a multi-agent shared memory service, a migration to Postgres (via the `StorageBackend` seam) is required.

### Neutral

- The `sqlite-vec` extension must be loaded at connection time: `conn.load_extension("vec0")`. The uv environment ships `sqlite-vec` as a Python package (`pip install sqlite-vec`) that exposes the `.so`/`.dylib` path via `sqlite_vec.loadable_path()`.

---

## References

- [sqlite-vec GitHub](https://github.com/asg017/sqlite-vec)
- widemem source: FAISS durability bugs WM-1 and WM-2 (internal research notes)
- Memori: WAL mode + background loop (borrowed pattern)
- SQLite WAL documentation: https://www.sqlite.org/wal.html
- FSFM (arxiv): forgetting taxonomy informed the `decay_rate` column design
