# Palantir Architecture: Handling Chaotic Data

*Research date: 2026-06-15 — Palantir Foundry / AIP documentation and AIP platform research*

---

## Executive Summary

Palantir Foundry transforms chaotic, multi-source enterprise data into a queryable semantic layer called the **Ontology**. The core innovation: the Ontology is not a passive schema but an **active model of enterprise knowledge** that integrates data, logic, action, and security into a unified representation usable by both humans and AI agents.

---

## 1. The Ontology — Core Abstraction

### What is the Ontology?

The Ontology maps raw chaotic data to real-world business concepts:

| Raw Data | Ontology Representation |
|---|---|
| Database rows | **Objects** (instances of object types) |
| Database columns | **Properties** (characteristics) |
| Foreign keys / join tables | **Links** (typed relationships) |
| Stored procedures | **Functions** and **Action types** |

### Ontology vs Traditional Schema

| Aspect | Traditional Schema | Palantir Ontology |
|---|---|---|
| Purpose | Data storage structure | Enterprise knowledge representation |
| Passive/Active | Passive (read-only) | Active (reads AND writes) |
| Relationships | Foreign keys (implied) | First-class typed links with cardinality |
| Business Logic | Stored procedures | Functions integrated into the layer |
| Actions | Not modeled | Action types with security attached |
| Security | Database-level | Fine-grained on every element |
| Change Tracking | Separate audit logs | Built-in decision lineage |
| Multi-modal | Tables only | Tables + files + streams + images |
| AI Integration | None | LLMs reason over full Ontology |

The Ontology is **decision-centric** — it models actual enterprise decisions, not just data structures.

---

## 2. Data Integration: From Chaos to Structure

### How chaotic data enters

Raw data enters through **Connectors** (JDBC, REST APIs, cloud storage, SAP, Workday, FTP, streams). The platform stores data in **Datasets** — an abstraction that handles both:
- **Structured tabular data** (rows/columns)
- **Unstructured files** (images, PDFs, audio stored as collections)

**Transforms** (SQL, Python, Java) process and clean data. Complete **data lineage** is maintained — tracking how every dataset was produced, from raw source to Ontology object.

### Two-layer architecture

```
DATA LAYER                    ONTOLOGY LAYER
Raw datasets           →      Objects
Connectors                    Properties
Transforms                    Links
Lineage tracking              Actions
                                 ↓
                    Applications consume both layers
```

The Ontology does NOT replace the data layer — it wraps it with semantic meaning while data remains in its original backing store.

---

## 3. Knowledge Graph: Typed Relationships

### Link Types

Links define relationships between object types with four attributes:

1. **Source / Target Object Types** — what is being connected
2. **Cardinality** — ONE-TO-ONE, ONE-TO-MANY, MANY-TO-ONE, MANY-TO-MANY
3. **Key** — which properties on each side are used for linking
4. **Object-backed Links** — the relationship itself can have metadata (e.g., "started_at", "relationship_type")

### Search-Around Pattern

Starting from one object, you traverse links to find related objects:

```typescript
// Find all employees who report to a specific manager
const reports = await Objects.search()
    .employee([manager])
    .searchAroundDirectReport();
```

This is the key graph traversal primitive — you don't write joins manually, you navigate relationships semantically.

---

## 4. Search and Retrieval

### ObjectSet API

The primary query mechanism — a lazy collection of object instances with:

- **Filter**: `exactMatch`, `hasProperty`, `matchAnyToken`, `contains`
- **Order/Limit**: `.orderByRelevance().take(10)`
- **Aggregate**: `.groupBy().aggregate({ "max": prop.max() })`
- **Temporal**: `.atTimestamp(datetime)` — state at a point in time

### Semantic Search with Embeddings

Vector similarity search for natural language queries:

```typescript
const embedding = await TextEmbedding.createEmbeddings({ inputs: [query] });
return Objects.search().objectApiName()
    .nearestNeighbors(obj => obj.embeddings.near(embedding, { kValue: 5 }))
    .orderByRelevance().take(kValue);
```

### Time-Series Search

```python
fts.search.series(
    query=(ontology("sector") == "Technology"),
    object_types=["stock"],
    property_type_id="price"
)
```

---

## 5. Palantir AIP — LLMs + Ontology

### Three-platform architecture

| Platform | Role |
|---|---|
| **Apollo** | Infrastructure orchestration, zero-downtime upgrades |
| **Foundry** | Core data operations, Ontology development |
| **AIP** | LLM connectivity, agent tools, AI-enabled applications |

### How LLMs use the Ontology

The Ontology serves as the **grounding layer** for LLMs:

1. **Object types** → schema for AI entity understanding (what is this thing?)
2. **Links** → context for relationship traversal (what is it connected to?)
3. **Actions** → enable AI agents to make changes (what can it do?)
4. **Functions** → server-side logic AI can invoke (complex computations)
5. **Decision lineage** → captures AI actions and reasoning (who decided what, when)

The LLM never queries raw data directly — it reasons over the Ontology, which maps back to the backing datasources.

---

## 6. Key Architectural Principles

### Principle 1: Ontology as Nouns, Actions as Verbs

The Ontology models **nouns** (objects, properties, links) and **verbs** (actions, functions). Every business concept is both:
- A **thing** you can query (via objects and links)
- A **capability** you can invoke (via actions)

### Principle 2: Backing Datasources

Properties in the Ontology **reference** backing datasources — they don't copy or store data directly. This means:
- The Ontology is always in sync with source data
- No data duplication
- Security policies can be enforced at the Ontology layer while data stays in place

### Principle 3: Decision Lineage

Every action in the Ontology captures:
- When it happened
- Which data version was used
- Which application/user/AI performed it
- What the downstream implications were

### Principle 4: Four-Fold Integration

Data + Logic + Action + Security unified in one layer. No other system handles all four.

---

## 7. What This Means for Our Memory System

The Palantir Ontology model directly informs our memory design:

### Our memory system mapped to Palantir concepts

| Palantir Concept | Our Memory Equivalent |
|---|---|
| Object type | Memory category (fact, preference, skill, context) |
| Object instance | Single MemoryRecord |
| Property | Memory field (content, usefulness_score, staleness_score) |
| Link type | ConceptLink (relates_to / contradicts / refines / supersedes) |
| Action type | memory:query, memory:dream, memory:feedback skills |
| Function | Scoring computation, entity extraction, summarization |
| Backing datasource | SQLite file (our raw data source) |
| Decision lineage | query_sessions audit log (who queried what, when) |

### The key insight from Palantir

**Don't copy data into a new store — wrap the raw store with a semantic layer that adds meaning.**

Our SQLite is the backing datasource. The semantic layer is:
- Entity extraction → what concepts exist
- ConceptLink → typed relationships between memories
- Usefulness/staleness scores → behavioral metadata on relationships
- Dreaming → the consolidation/ontology update process

The memories themselves stay in SQLite. The Ontology is the layer that makes them queryable by meaning, not just by keyword.

### The LLM grounding problem

Palantir's most important insight: **LLMs need a typed schema to reason over, not raw unstructured text.**

When an LLM queries our memory system, it should reason over:
- Object types (what categories of memories exist)
- Links (which memories relate to which concepts)
- Actions (what can it do with memories)
- Not raw memory content directly

This is exactly what our `memory:peek` (concept overview) and `memory:stats` (health dashboard) skills provide — structured Schema information the LLM can use to formulate precise queries.

---

## 8. Summary: How Palantir Makes Chaotic Data Searchable

1. **Raw data stays raw** — stored in original format and location
2. **Connectors ingest** — bringing data into the platform's data layer
3. **Transforms clean** — SQL/Python transforms with full lineage
4. **Ontology wraps** — maps raw tables to real-world objects, columns to properties, foreign keys to typed links
5. **ObjectSet API queries** — users/applications search via object types and their relationships, not raw SQL
6. **LLMs ground** — reason over the Ontology schema, not raw data

The Ontology is the semantic index on top of chaotic data. It doesn't change the data — it adds a queryable semantic skin over it.

---

## Key Sources

- Palantir Foundry documentation (via Context7)
- Palantir AIP platform documentation
- Palantir Ontology platform documentation (object types, links, actions, functions)
- Palantir knowledge graph and search documentation
