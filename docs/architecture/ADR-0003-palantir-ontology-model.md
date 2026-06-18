# ADR-0003: Palantir Foundry Ontology as the Conceptual Model

**Status:** Accepted  
**Date:** 2026-06-15  
**Deciders:** MintMory core team  
**Supersedes:** (none — domain model decision)

---

## Context

LLM agent memory systems in the literature (MemGPT, Mem0, widemem, Memori) share a common limitation: they treat memory as a flat or lightly-structured key-value store. Retrieval is either pure vector similarity or keyword search; there is no typed schema enforcing what a memory *is* and how it *relates* to other memories. This leads to:

- **Undetected contradictions:** two `fact` memories can assert opposite things; the system has no schema-level concept of contradiction.
- **Opaque provenance:** the system cannot answer "which memories influenced this response?"
- **No lifecycle semantics:** there is no distinction between a `temporal` memory (valid until a date) and an `identity` memory (persistent, high-importance); both decay equally.
- **No traversal:** you cannot ask "give me all memories that this memory *enables*" because links are untyped or absent.

Palantir Foundry's Ontology layer addresses all four problems in the context of enterprise data, and its conceptual model maps cleanly to agent memory.

### The Palantir Ontology Model (Relevant Subset)

Palantir Foundry organises enterprise knowledge into:

| Palantir Concept | Description |
|-----------------|-------------|
| **Object Type** | A typed class of entities with a fixed schema (properties) |
| **Link Type** | A typed directed (or undirected) relationship between Object Types, with its own properties |
| **Action Type** | A structured mutation operation on the Ontology (with parameter schema, pre/post conditions) |
| **Decision Lineage** | Audit trail tracing which Objects and Links contributed to a downstream decision |

---

## Decision

**Model MintMory's domain using Palantir Foundry Ontology concepts as the design language**, mapping them as follows:

### Mapping Table

| Palantir Ontology | MintMory Equivalent | Implementation |
|-------------------|---------------------|----------------|
| Object Type | `MemoryCategory` enum (8 values) | `memories` table rows with `category` column |
| Object Property | Memory fields: `content`, `importance`, `confidence`, `decay_rate`, `expires_at`, `metadata` | SQLite columns + JSON metadata blob |
| Link Type | `ConceptLinkType` enum (11 values) | `concept_links` table rows with `link_type` column |
| Link Property | Link fields: `strength`, `confidence`, `created_by`, `metadata` | SQLite columns on `concept_links` |
| Action Type | Dreaming operations: `link_orphans`, `resolve_contradictions`, `archive`, `rehabilitate` | Async functions in `core/dreaming.py` |
| Decision Lineage | `QuerySession` + `useful_ids` / `stale_ids` LLM self-assessment | `query_sessions` table |

### Memory Categories (Object Types)

Defined in `core/types.py` as `MemoryCategory(str, Enum)`:

| Category | Palantir Analogy | Semantics | Default Decay Rate |
|----------|-----------------|-----------|-------------------|
| `identity` | Core entity properties | Who the agent is, its name, role, persistent self-knowledge | 0.0001 (near-permanent) |
| `preference` | User preference Object | Likes, dislikes, interaction style preferences | 0.005 |
| `skill` | Capability Object | Procedural knowledge, how-to instructions | 0.002 |
| `context` | Session Object | Current task, active project, short-horizon context | 0.05 |
| `fact` | Fact Object | Objective, verifiable assertions about the world | 0.01 |
| `episodic` | Event Object | What happened in a past interaction | 0.02 |
| `temporal` | Time-bounded Object | Information valid until `expires_at`; auto-archived after expiry | 0.1 |
| `relationship` | Relationship Object | Knowledge about other entities, people, or agents | 0.008 |

### ConceptLink Types (Link Types)

Defined in `core/types.py` as `ConceptLinkType(str, Enum)`. See ADR-0005 for the full 11-type rationale. The Ontology framing:

- **Directed:** All 11 link types are directed (source → target). The direction is semantically significant: `A supersedes B` ≠ `B supersedes A`.
- **Properties on the link:** `strength` (float, 0–1) represents how confident the system is that this link is valid. `confidence` captures the classifier certainty during dreaming. `created_by` distinguishes system-generated vs. LLM-generated vs. user-asserted links.
- **Traversal queries:** Because link types are stored as a column, graph traversal is a SQL CTE: `WITH RECURSIVE reachable AS (SELECT target_id FROM concept_links WHERE source_id = :start AND link_type = 'enables' ...)`.

### Action Types (Dreaming Operations)

Each dreaming operation maps to a Palantir Action Type:

| Dreaming Action | Palantir Action Analogy | Trigger |
|----------------|------------------------|---------|
| `anomaly_detection` | Validate Object constraints | Light and full dream |
| `link_orphans` | Enrich Object with Link Types | Light and full dream |
| `generate_summaries` | Derive Property on Object | Light dream |
| `resolve_contradictions` | Merge conflicting Objects | Full dream only |
| `archive_decayed` | Archive Object | Full dream only |
| `rehabilitate_archived` | Restore Object | Full dream only |

The dreaming daemon (`core/dreamd.py`) runs on a configurable interval (default: light dream every 30 min, full dream every 6 h), implemented as a `asyncio.TaskGroup` background coroutine. This matches Memori's background loop pattern.

### Decision Lineage (QuerySession)

Every MCP `retrieve_memories` or API `GET /memories/search` call creates a `QuerySession` row. After the LLM agent uses the retrieved memories, it calls `close_session` with:

- `useful_ids`: list of memory IDs that were actually helpful
- `stale_ids`: list of memory IDs that were incorrect or outdated
- `confidence_rating`: float, the agent's self-assessed confidence in its response

This passive self-assessment (borrowed from the MEMTIER paper) feeds back into:
- `importance` boosting for `useful_ids` (reinforcement)
- `has_conflict = TRUE` flagging for `stale_ids` (queued for dreaming)
- Category-level analytics for the measurement framework

---

## Rationale

### Why Palantir and not RDF / OWL?

RDF/OWL provides similar expressiveness but comes with:
- SPARQL query overhead (no native SQLite SPARQL engine)
- Heavyweight tooling (Jena, Stardog) incompatible with the portability goal
- Steep learning curve for contributors unfamiliar with semantic web conventions

The Palantir Ontology model achieves 90% of the semantic richness with plain SQL columns and a Python enum. It is conceptually accessible to any Python developer without ontology training.

### Why not a pure graph database (Neo4j, Memgraph)?

Graph databases are excellent for deep traversal but poor for:
- The forgetting curve aggregations (weighted averages over all memories by category)
- Full-text search (FTS5 has no equivalent in Cypher)
- Portability (both require running a daemon)

The hybrid approach — relational rows for Object properties, edge table for Link Types — gives SQL-accessible graph semantics without sacrificing portability or SQL expressiveness.

### Type safety in Python

`MemoryCategory` and `ConceptLinkType` as `str, Enum` subclasses mean:
- They serialise to JSON as plain strings (no custom serialiser needed)
- SQLite stores them as TEXT (no integer codes that obscure schema dumps)
- mypy enforces that only valid values are used at type-check time

---

## Consequences

### Positive

- **Typed schema enables contradiction detection:** two memories with `category='fact'` and a `contradicts` link between them can be automatically identified and queued for LLM resolution.
- **Graph traversal in SQL:** `WITH RECURSIVE` CTEs over `concept_links` provide multi-hop reachability queries without a graph database.
- **Decision audit trail:** `QuerySession` gives a complete lineage of which memories contributed to which LLM responses — directly analogous to Palantir's Decision Lineage.
- **Category-specific dreaming:** light dreams can target only `temporal` memories for expiry checking and `context` memories for rapid decay, without scanning the full corpus.
- **Documentation vocabulary:** saying "this is a Link Type with source Object Type `fact` and target Object Type `fact`" gives contributors immediate conceptual grounding.

### Negative / Risks

- **Palantir is proprietary:** developers unfamiliar with Foundry need the mapping table above to understand the terminology. The system-design.md always includes this table as a quick reference.
- **11 link types increase classification complexity:** the dreaming LLM prompt must reliably assign one of 11 types. Mitigation: staged rollout starting with 4 types (see ADR-0005).
- **`metadata` JSON column is a schema escape hatch:** it undermines the typed model if overused. Policy: only use `metadata` for fields that are genuinely not known at schema design time (e.g., source URL, agent ID, external reference). Core semantic fields must be proper columns.

### Neutral

- The Ontology model is a *design language*, not a runtime library. MintMory does not import any Palantir SDK. The concepts map to plain Python dataclasses and SQLite tables.

---

## References

- Palantir Foundry Ontology documentation (public): https://www.palantir.com/docs/foundry/ontology/
- KGFoller (arxiv): knowledge graph construction for LLM memory (Link Type inspiration)
- AgentKB (arxiv): agent knowledge base with typed relations
- StructGPT (arxiv): structured reasoning over typed knowledge graphs
- Memento (arxiv): time-aware memory with Decision Lineage concepts
- Memori (open source): category-based memory storage (pattern borrowed)
