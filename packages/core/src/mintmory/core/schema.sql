-- MintMory SQLite Schema — Source of Truth
--
-- This file is the authoritative DDL. It is:
--   1. Executed to create the database (storage.py → StorageAdapter.initialise())
--   2. Used in schema compliance tests (tests/test_schema.py)
--   3. Cross-referenced with types.py — every column must map to a Pydantic field
--
-- Conventions:
--   • IDs are TEXT (UUID/ULID strings — sortable, readable, no collision)
--   • Booleans stored as INTEGER (0/1) — SQLite has no native BOOL
--   • JSON arrays stored as TEXT — deserialised by Pydantic field_validator
--   • All timestamps stored as TEXT in ISO-8601 UTC (e.g. "2026-06-15T14:30:00Z")
--   • WAL mode enabled for concurrent read + single-write
--   • FTS5 virtual table mirrors memories.content for full-text search
--
-- Design reference:
--   Memori's basic.sql (FTS5 + WAL pattern, memory_relationships DDL as column template)
--   Palantir Ontology mapping (PALANTIR.md §7)
--   FEATURES.md corrected schema
--   TYPED_SCHEMA.md (11 ConceptLinkType values)

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- memories — primary object store (Palantir: Object instances)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memories (
    id                  TEXT PRIMARY KEY,
    content             TEXT NOT NULL CHECK (length(content) >= 1 AND length(content) <= 10000),
    category            TEXT NOT NULL CHECK (category IN (
                            'identity','preference','skill','context',
                            'fact','episodic','temporal','relationship'
                        )),
    entity_ids          TEXT NOT NULL DEFAULT '[]',     -- JSON array of strings
    embedding           BLOB,                           -- float32 vector (sqlite-vec)

    -- Provenance (Palantir: Properties)
    confidence          REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    source              TEXT NOT NULL DEFAULT 'agent'
                            CHECK (source IN ('user','agent','document','inference')),
    verified            INTEGER NOT NULL DEFAULT 0,
    valid_from          TEXT,                           -- ISO-8601 or NULL
    valid_until         TEXT,                           -- ISO-8601 or NULL

    -- Session feedback scores (updated by QuerySession feedback cycle)
    usefulness_score    REAL NOT NULL DEFAULT 0.0 CHECK (usefulness_score >= 0.0 AND usefulness_score <= 10.0),
    staleness_score     REAL NOT NULL DEFAULT 0.0 CHECK (staleness_score >= 0.0 AND staleness_score <= 10.0),
    reinforcement_count INTEGER NOT NULL DEFAULT 0 CHECK (reinforcement_count >= 0),
    retrieval_count     INTEGER NOT NULL DEFAULT 0 CHECK (retrieval_count >= 0),

    -- State flags
    is_stale            INTEGER NOT NULL DEFAULT 0,
    is_active           INTEGER NOT NULL DEFAULT 1,
    is_archived         INTEGER NOT NULL DEFAULT 0,
    superseded_by       TEXT REFERENCES memories(id) ON DELETE SET NULL,
    flagged_for_review  INTEGER NOT NULL DEFAULT 0,
    contradicts_ids     TEXT NOT NULL DEFAULT '[]',     -- JSON array of memory IDs
    is_note             INTEGER NOT NULL DEFAULT 0,      -- user-authored note overlay (0/1)

    -- Timestamps
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    last_accessed_at    TEXT,

    -- Extensible metadata
    metadata            TEXT NOT NULL DEFAULT '{}'      -- JSON object
);

-- ---------------------------------------------------------------------------
-- FTS5 virtual table — full-text search on content
-- Memori pattern: triggers keep the index in sync automatically
-- ---------------------------------------------------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
USING fts5(content, content='memories', content_rowid='rowid', tokenize='porter unicode61');

CREATE TRIGGER IF NOT EXISTS memories_fts_insert AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_fts_update AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
    INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_fts_delete AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
END;

-- ---------------------------------------------------------------------------
-- concept_links — typed edges between memory nodes (Palantir: Link types)
--
-- Column design inspired by Memori's removed memory_relationships table
-- (base_queries.py EntityQueries) — column names and indexes preserved.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS concept_links (
    id                  TEXT PRIMARY KEY,
    source_memory_id    TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_memory_id    TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    link_type           TEXT NOT NULL CHECK (link_type IN (
                            'relates_to','contradicts','refines','supersedes',
                            'enables','depends_on','similar_to','part_of',
                            'uses','before','valid_until','annotates'
                        )),
    entity              TEXT NOT NULL DEFAULT '',  -- shared entity that triggered this link

    -- Object-backed link metadata (Palantir: Links with metadata)
    strength            REAL NOT NULL DEFAULT 0.5 CHECK (strength >= 0.0 AND strength <= 1.0),
    confidence          REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    source              TEXT NOT NULL DEFAULT 'dreaming'
                            CHECK (source IN ('extraction','inference','dreaming','user')),
    verified            INTEGER NOT NULL DEFAULT 0,

    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,

    UNIQUE (source_memory_id, target_memory_id, link_type)
);

-- ---------------------------------------------------------------------------
-- memory_summaries — per-concept LLM-generated synthesis (dreaming Step 3)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_summaries (
    id              TEXT PRIMARY KEY,
    concept         TEXT NOT NULL UNIQUE,
    summary_text    TEXT NOT NULL,
    memory_count    INTEGER NOT NULL DEFAULT 0,
    is_current      INTEGER NOT NULL DEFAULT 1,
    generated_at    TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- index_manifest — per-path state for recurrent tree indexing
-- (change-detection + idempotent re-runs; openspec: add-recurrent-tree-indexing)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS index_manifest (
    path          TEXT PRIMARY KEY,           -- absolute source file path
    collection    TEXT NOT NULL,              -- source-root id, e.g. 'onedrive:ExampleOrg'
    size          INTEGER NOT NULL,
    mtime         REAL NOT NULL,
    content_hash  TEXT,                        -- NULL until content is downloaded+hashed
    index_mode    TEXT NOT NULL DEFAULT 'metadata' CHECK (index_mode IN ('metadata','content','vision')),
    memory_ids    TEXT NOT NULL DEFAULT '[]',  -- JSON array of memory ids for this path
    online_only   INTEGER NOT NULL DEFAULT 0,
    last_seen     TEXT NOT NULL                -- ISO-8601 UTC of the last run that saw this path
);

CREATE INDEX IF NOT EXISTS idx_manifest_collection
    ON index_manifest(collection);

-- ---------------------------------------------------------------------------
-- query_sessions — decision lineage (Palantir: Decision Lineage)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS query_sessions (
    id                  TEXT PRIMARY KEY,
    query_text          TEXT NOT NULL,
    created_at          TEXT NOT NULL,

    -- Post-session LLM passive self-assessment fields
    confidence_rating   INTEGER CHECK (confidence_rating BETWEEN 1 AND 5),
    reasoning           TEXT,
    useful_ids          TEXT NOT NULL DEFAULT '[]',  -- JSON array
    stale_ids           TEXT NOT NULL DEFAULT '[]',  -- JSON array
    concluded           INTEGER NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- query_results — which memories were retrieved per session
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS query_results (
    session_id          TEXT NOT NULL REFERENCES query_sessions(id) ON DELETE CASCADE,
    memory_id           TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relevance_score     REAL NOT NULL DEFAULT 0.0,
    was_accessed        INTEGER NOT NULL DEFAULT 0,
    was_useful          INTEGER NOT NULL DEFAULT 0,
    was_stale           INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (session_id, memory_id)
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- memories — primary access patterns
CREATE INDEX IF NOT EXISTS idx_memories_active
    ON memories(is_active, is_archived);

CREATE INDEX IF NOT EXISTS idx_memories_stale
    ON memories(is_stale, staleness_score);

CREATE INDEX IF NOT EXISTS idx_memories_category
    ON memories(category, is_active);

CREATE INDEX IF NOT EXISTS idx_memories_flagged
    ON memories(flagged_for_review)
    WHERE flagged_for_review = 1;

CREATE INDEX IF NOT EXISTS idx_memories_usefulness
    ON memories(usefulness_score DESC, staleness_score ASC)
    WHERE is_active = 1 AND is_archived = 0;

CREATE INDEX IF NOT EXISTS idx_memories_note
    ON memories(is_note, valid_from)
    WHERE is_note = 1;

-- concept_links — graph traversal (source → target, target → source, by type)
CREATE INDEX IF NOT EXISTS idx_links_source
    ON concept_links(source_memory_id, link_type);

CREATE INDEX IF NOT EXISTS idx_links_target
    ON concept_links(target_memory_id, link_type);

CREATE INDEX IF NOT EXISTS idx_links_type_strength
    ON concept_links(link_type, strength DESC);

CREATE INDEX IF NOT EXISTS idx_links_entity
    ON concept_links(entity)
    WHERE entity != '';

-- query_sessions — feedback backlog
CREATE INDEX IF NOT EXISTS idx_sessions_concluded
    ON query_sessions(concluded, created_at);

-- query_results — session lookup
CREATE INDEX IF NOT EXISTS idx_results_session
    ON query_results(session_id);

CREATE INDEX IF NOT EXISTS idx_results_memory
    ON query_results(memory_id);
