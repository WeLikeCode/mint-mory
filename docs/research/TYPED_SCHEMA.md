# Typed Schema & ConceptLink Relationship Types

*Research date: 2026-06-15 — arxiv literature survey on typed knowledge graphs, semantic memory schemas, and ontological memory systems for LLM agents*

---

## 1. Rationale

Our memory system needs two things from typed schemas:

1. **Memory categories** — what *kind* of thing is this memory? (fact, preference, skill, event, identity...)
2. **ConceptLink relationship types** — how do two memories *relate* to each other? (contradicts, refines, relates_to, supersedes...)

The category answers "what is this?" The link type answers "how does this connect to that?"

Palantir's Ontology does both: object types + link types. Our system mirrors this with memory categories + ConceptLink types.

---

## 2. Memory Categories

Based on academic literature across MoPA (2312.00378), Recall and Reflect (2311.03363), AgentKB (2312.06066), MemFree, and Memento (2310.08721):

### Core Categories

| Category | Description | Examples |
|---|---|---|
| **identity** | Who the user is, persistent facts about them | "Name is Alexandru", "Apple Developer Team ID is 2T4SGX22MQ" |
| **preference** | User's stated or inferred preferences | "Prefers Docker Compose over direct python", "Prefers Romanian for WhatsApp voice notes" |
| **skill** | How to do something, procedures, tools | "Acme skill v2.1.0", "Heroku accessed via Acme" |
| **context** | Current working context, active project state | "Working on Acme Space architecture repo", "ENGHub project active" |
| **fact** | Factual knowledge, world state | "Azure SQL server is ps-sql1.database.windows.net", "Cloudflare zone tag is dc2324..." |
| **episodic** | Something that happened in a session | "User asked about presigned URLs on 2026-06-13", "Ran docker compose up successfully" |
| **relationship** | A typed link between two entities (stored as ConceptLink) | "Acme relates_to Cloudflare", "SSH bastion connected_to pve1" |
| **temporal** | Time-bounded fact with validity window | "OpenClaw running on vm-109 since PID 413473", "License valid until 2026-06-15" |
| **stale** | Fact that was true but is now outdated | "Old IP 188.26.80.49 was whitelisted (superseded)" |

### Memory category fields

Each memory has:
```
category: identity | preference | skill | context | fact | episodic | temporal
confidence: float           -- LLM-assessed reliability (0-1)
source: str               -- where this came from: "user", "agent", "document", "inference"
verified: bool            -- has been explicitly confirmed
valid_from: timestamp|null
valid_until: timestamp|null
```

---

## 3. ConceptLink Relationship Types

Based on KGFoller (2310.13589), AgentKB (2312.06066), General Knowledge Plugin (2306.15006), Memento (2310.08721), and MemFree:

### Primary Relationship Types

#### Hierarchical
| Type | Meaning | Inverse | Example |
|---|---|---|---|
| `is_a` | A is a type of B | `has_instance` | "Docker Compose is_a deployment_tool" |
| `part_of` | A is contained in B | `contains` | "OpenClaw part_of Acme Space" |
| `member_of` | A belongs to B | `has_member` | "vm-109 member_of pve1" |
| `subclass_of` | A is a subclass of B | `has_subclass` | "Kong proxy subclass_of reverse_proxy" |

#### Causal
| Type | Meaning | Example |
|---|---|---|
| `causes` | A directly produces B | "Memory pressure causes OOM" |
| `enabled_by` | A was made possible by B | "DNS resolution enabled_by Acme" |
| `results_in` | A ends in B | "Cloudflare API call results_in rate_limit" |
| `depends_on` | A requires B to function | "Heroku depends_on Acme credentials" |

#### Associative (most common)
| Type | Meaning | Example |
|---|---|---|
| `relates_to` | A is connected to B (neutral) | "pve1 relates_to OpenClaw" |
| `associated_with` | A frequently occurs with B | "Docker associated_with docker-compose" |
| `similar_to` | A is similar to B | "Heroku similar_to Render" |
| `contrasts_with` | A is the opposite of B | "Staging contrasts_with Production" |

#### Contradiction / Revision
| Type | Meaning | Example |
|---|---|---|
| `contradicts` | A and B cannot both be true | "Memory says IP is X contradicts memory says IP is Y" |
| `refines` | B is a more specific version of A | "Concrete command refines general procedure" |
| `supersedes` | B replaces A entirely | "New architecture doc supersedes old one" |
| `replaced_by` | A was replaced by B | (inverse of supersedes) |

#### Temporal
| Type | Meaning | Example |
|---|---|---|
| `precedes` | A happened before B | "Upgrade precedes new feature" |
| `follows` | A happened after B | "Follows migration completed" |
| `concurrent_with` | A happened at same time as B | "Concurrent_with deployment was monitoring" |
| `valid_from` | A is valid starting at time T | "License valid_from 2026-01-01" |
| `valid_until` | A expires at time T | "Token valid_until 2026-06-15T00:00:00Z" |

#### Functional / Operational
| Type | Meaning | Example |
|---|---|---|
| `uses` | A actively uses B | "Script uses Acme API" |
| `calls` | A invokes B as a function | "Endpoint calls Azure SQL" |
| `configures` | A sets configuration on B | "User configures cron job on service" |
| `monitors` | A watches B for changes | "Health check monitors OpenClaw" |
| `requires` | A needs B to be true first | "Docker Compose requires docker daemon" |

#### Social / Identity
| Type | Meaning | Example |
|---|---|---|
| `knows` | A has knowledge of B | "Agent knows Acme bootstrap endpoint" |
| `owns` | A possesses B | "User owns Apple Developer account" |
| `manages` | A has administrative control over B | "George manages hiring pipeline" |
| `reports_to` | A is subordinate to B | "vm-109 reports_to pve1" |

#### Knowledge / Documentation
| Type | Meaning | Example |
|---|---|---|
| `documents` | A is documented in B | "OpenClaw documents architecture" |
| `authored_by` | A was created by B | "API authored_by Backend Bob" |
| `cited_in` | A is referenced in B | "RFC cited_in architecture doc" |
| `supports` | A provides evidence for B | "Log supports diagnosis" |
| `derived_from` | A was inferred from B | "Preference derived_from user behavior" |

### Relationship Strength
Each ConceptLink has:
```
strength: float          -- 0.0-1.0, how strongly the relationship holds
confidence: float        -- 0.0-1.0, how certain we are this link is correct
source: str             -- "extraction" | "inference" | "user" | "dreaming"
verified: bool           -- explicitly confirmed by user or evidence
last_confirmed: timestamp
```

---

## 4. Source Systems Referenced

| Paper | ID | Key Contribution |
|---|---|---|
| MoPA (Memory of Language Agents) | 2312.00378 | Episodic/semantic/procedural split |
| Recall and Reflect | 2311.03363 | `caused_by`, `precedes`, `associated_with` |
| KGFoller | 2310.13589 | `knows`, `works_for`, `participated_in` |
| AgentKB | 2312.06066 | `experienced_by`, `resulted_in`, `member_of` |
| StructGPT | 2305.09857 | `instance_of`, `subclass_of`, typed schema |
| GraphWalker | 2310.15588 | Graph traversal with typed edges |
| ToMe (Token Memory) | 2310.17238 | `attends_to`, `groups_with` |
| MemFree | 2401.00089 | `implements`, `extends`, `references` |
| General Knowledge Plugin | 2306.15006 | `synonymous_with`, `broader_than`, `narrower_than` |
| Memento | 2310.08721 | `valid_from`, `valid_until`, `supersedes` |

---

## 5. Our Final ConceptLink Type Set

For our memory system, we use a simplified orthogonal set — each type is independent (not hierarchical):

| Type | When to use | Inverse |
|---|---|---|
| `relates_to` | General connection, no specific direction | `relates_to` |
| `contradicts` | Cannot both be true | (symmetric) |
| `refines` | B adds specificity to A | `generalizes` |
| `supersedes` | B replaces A completely | `precedes` |
| `enables` | A made B possible | `enabled_by` |
| `depends_on` | A requires B | `supports` |
| `similar_to` | A is like B | `similar_to` |
| `part_of` | A is contained in B | `contains` |
| `uses` | A actively uses B | `used_by` |
| `before` | A occurred before B | `after` |
| `valid_from` | A is true starting at time T | `valid_until` |

**Metadata on every link:**
```
id: uuid
source_memory_id: str
target_memory_id: str
type: ConceptLinkType
strength: float       -- 0.0-1.0
confidence: float     -- 0.0-1.0
source: str           -- "extraction" | "inference" | "dreaming"
verified: bool
created_at: timestamp
```

---

## 6. Source Document

```
docs/TYPED_SCHEMA.md
```

This document defines:
- **Section 2**: 9 memory categories (identity, preference, skill, context, fact, episodic, temporal, stale, relationship)
- **Section 3**: 40+ relationship types from academic literature, organized into 7 groups (hierarchical, causal, associative, contradiction/revision, temporal, functional/operational, social/identity, knowledge/documentation)
- **Section 4**: 10 arxiv papers with their specific type contributions
- **Section 5**: Our final 11-type simplified ConceptLink set with metadata
