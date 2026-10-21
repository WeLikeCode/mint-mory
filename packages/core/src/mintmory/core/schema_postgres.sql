-- MintMory PostgreSQL Schema — Phase 2
--
-- Executed by PostgresBackend.initialise() under pg_advisory_lock (idempotent).
-- All statements use IF NOT EXISTS so repeated calls are safe.
--
-- Design reference: design.md §2.3, §6.1–6.5, §8 locked decisions.
-- Mirrors schema.sql (SQLite) with PostgreSQL-native types:
--   TEXT → TEXT (same)
--   INTEGER bool → BOOLEAN
--   REAL → FLOAT (= double precision)
--   TEXT JSON → JSONB
--   TEXT timestamps → TIMESTAMP (naive UTC)
--   sqlite-vec BLOB → pgvector vector (unconstrained dimension)
--   FTS5 virtual table → generated tsvector column + GIN index
--   trigram → pg_trgm GIN index on content

-- Extensions are installed by PostgresBackend._ensure_extensions() before
-- this script runs.  A DBA must pre-install them on managed Postgres
-- (RDS/CloudSQL) where the app role lacks CREATE privilege.

-- ---------------------------------------------------------------------------
-- tenants — the tenant directory (created first: the other tables' tenant_id
-- foreign key targets this table, so it must exist before any insert)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP NOT NULL,
    updated_at  TIMESTAMP NOT NULL
);

INSERT INTO tenants (id, name, is_active, created_at, updated_at)
VALUES ('global', 'Global (default) tenant', TRUE, '1970-01-01 00:00:00', '1970-01-01 00:00:00')
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- memories — primary object store
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memories (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id),
    content             TEXT NOT NULL CHECK (length(content) >= 1 AND length(content) <= 10000),
    category            TEXT NOT NULL CHECK (category IN (
                            'identity','preference','skill','context',
                            'fact','episodic','temporal','relationship'
                        )),
    entity_ids          JSONB NOT NULL DEFAULT '[]',
    embedding           vector,              -- unconstrained: any dimension (design §6.2)

    -- Provenance
    confidence          FLOAT NOT NULL DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    source              TEXT NOT NULL DEFAULT 'agent'
                            CHECK (source IN ('user','agent','document','inference')),
    verified            BOOLEAN NOT NULL DEFAULT FALSE,
    valid_from          TIMESTAMP,           -- naive UTC (design §6.5)
    valid_until         TIMESTAMP,

    -- Session feedback scores
    usefulness_score    FLOAT NOT NULL DEFAULT 0.0 CHECK (usefulness_score >= 0.0 AND usefulness_score <= 10.0),
    staleness_score     FLOAT NOT NULL DEFAULT 0.0 CHECK (staleness_score >= 0.0 AND staleness_score <= 10.0),
    reinforcement_count INTEGER NOT NULL DEFAULT 0 CHECK (reinforcement_count >= 0),
    retrieval_count     INTEGER NOT NULL DEFAULT 0 CHECK (retrieval_count >= 0),

    -- State flags
    is_stale            BOOLEAN NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    is_archived         BOOLEAN NOT NULL DEFAULT FALSE,
    superseded_by       TEXT REFERENCES memories(id) ON DELETE SET NULL,
    flagged_for_review  BOOLEAN NOT NULL DEFAULT FALSE,
    contradicts_ids     JSONB NOT NULL DEFAULT '[]',
    is_note             BOOLEAN NOT NULL DEFAULT FALSE,

    -- Timestamps (naive UTC — no tzinfo stored)
    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL,
    last_accessed_at    TIMESTAMP,

    -- Extensible metadata
    metadata            JSONB NOT NULL DEFAULT '{}',

    -- Generated tsvector column for FTS (design §6.1)
    -- STORED means it is physically persisted and indexed.
    content_tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

-- GIN index for tsvector FTS
CREATE INDEX IF NOT EXISTS idx_memories_fts
    ON memories USING GIN (content_tsv);

-- GIN index for trigram substring search (design §2.3)
CREATE INDEX IF NOT EXISTS idx_memories_trgm
    ON memories USING GIN (content gin_trgm_ops);

-- Standard B-tree access pattern indexes (mirrors schema.sql)
CREATE INDEX IF NOT EXISTS idx_memories_active
    ON memories(is_active, is_archived);

CREATE INDEX IF NOT EXISTS idx_memories_stale
    ON memories(is_stale, staleness_score);

CREATE INDEX IF NOT EXISTS idx_memories_category
    ON memories(category, is_active);

CREATE INDEX IF NOT EXISTS idx_memories_flagged
    ON memories(flagged_for_review)
    WHERE flagged_for_review = TRUE;

CREATE INDEX IF NOT EXISTS idx_memories_usefulness
    ON memories(usefulness_score DESC, staleness_score ASC)
    WHERE is_active = TRUE AND is_archived = FALSE;

CREATE INDEX IF NOT EXISTS idx_memories_note
    ON memories(is_note, valid_from)
    WHERE is_note = TRUE;

-- ---------------------------------------------------------------------------
-- concept_links — typed edges between memory nodes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS concept_links (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id),
    source_memory_id    TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    target_memory_id    TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    link_type           TEXT NOT NULL CHECK (link_type IN (
                            'relates_to','contradicts','refines','supersedes',
                            'enables','depends_on','similar_to','part_of',
                            'uses','before','valid_until','annotates'
                        )),
    entity              TEXT NOT NULL DEFAULT '',

    strength            FLOAT NOT NULL DEFAULT 0.5 CHECK (strength >= 0.0 AND strength <= 1.0),
    confidence          FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    source              TEXT NOT NULL DEFAULT 'dreaming'
                            CHECK (source IN ('extraction','inference','dreaming','user')),
    verified            BOOLEAN NOT NULL DEFAULT FALSE,

    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL,

    CONSTRAINT concept_links_tenant_unique
        UNIQUE (tenant_id, source_memory_id, target_memory_id, link_type)
);

CREATE INDEX IF NOT EXISTS idx_links_source
    ON concept_links(source_memory_id, link_type);

CREATE INDEX IF NOT EXISTS idx_links_target
    ON concept_links(target_memory_id, link_type);

CREATE INDEX IF NOT EXISTS idx_links_type_strength
    ON concept_links(link_type, strength DESC);

CREATE INDEX IF NOT EXISTS idx_links_entity
    ON concept_links(entity)
    WHERE entity != '';

-- ---------------------------------------------------------------------------
-- memory_summaries — per-concept LLM-generated synthesis
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_summaries (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id),
    concept         TEXT NOT NULL,
    summary_text    TEXT NOT NULL,
    memory_count    INTEGER NOT NULL DEFAULT 0,
    is_current      BOOLEAN NOT NULL DEFAULT TRUE,
    generated_at    TIMESTAMP NOT NULL,

    CONSTRAINT memory_summaries_tenant_concept_key UNIQUE (tenant_id, concept)
);

-- ---------------------------------------------------------------------------
-- index_manifest — per-path state for recurrent tree indexing
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS index_manifest (
    path          TEXT NOT NULL,
    tenant_id     TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id),
    collection    TEXT NOT NULL,
    size          INTEGER NOT NULL,
    mtime         FLOAT NOT NULL,
    content_hash  TEXT,
    index_mode    TEXT NOT NULL DEFAULT 'metadata'
                      CHECK (index_mode IN ('metadata','content','vision')),
    memory_ids    TEXT NOT NULL DEFAULT '[]',   -- TEXT JSON (Protocol: memory_ids: str)
    online_only   BOOLEAN NOT NULL DEFAULT FALSE,
    last_seen     TEXT NOT NULL,                 -- ISO-8601 UTC string

    PRIMARY KEY (tenant_id, path)
);

CREATE INDEX IF NOT EXISTS idx_manifest_collection
    ON index_manifest(collection);

-- ---------------------------------------------------------------------------
-- query_sessions — decision lineage
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS query_sessions (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id),
    query_text          TEXT NOT NULL,
    created_at          TIMESTAMP NOT NULL,

    confidence_rating   INTEGER CHECK (confidence_rating BETWEEN 1 AND 5),
    reasoning           TEXT,
    useful_ids          JSONB NOT NULL DEFAULT '[]',
    stale_ids           JSONB NOT NULL DEFAULT '[]',
    concluded           BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_sessions_concluded
    ON query_sessions(concluded, created_at);

-- ---------------------------------------------------------------------------
-- query_results — which memories were retrieved per session
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS query_results (
    session_id          TEXT NOT NULL REFERENCES query_sessions(id) ON DELETE CASCADE,
    tenant_id           TEXT NOT NULL DEFAULT 'global' REFERENCES tenants(id),
    memory_id           TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relevance_score     FLOAT NOT NULL DEFAULT 0.0,
    was_accessed        BOOLEAN NOT NULL DEFAULT FALSE,
    was_useful          BOOLEAN NOT NULL DEFAULT FALSE,
    was_stale           BOOLEAN NOT NULL DEFAULT FALSE,

    PRIMARY KEY (session_id, memory_id)
);

CREATE INDEX IF NOT EXISTS idx_results_session
    ON query_results(session_id);

CREATE INDEX IF NOT EXISTS idx_results_memory
    ON query_results(memory_id);
