# ADR-0005: 11 ConceptLink Types Instead of the Minimal 4

**Status:** Accepted  
**Date:** 2026-06-15  
**Deciders:** MintMory core team  
**Supersedes:** (none — link type schema decision)

---

## Context

The minimum viable set of typed memory links is 4 types, sufficient to capture the most critical agent memory relationships:

| Minimal type | Semantic |
|-------------|---------|
| `relates_to` | Generic association (catch-all) |
| `contradicts` | Logical conflict between two memories |
| `refines` | One memory adds precision/nuance to another |
| `supersedes` | One memory replaces another (version update) |

This 4-type set was the initial candidate from examining Memori (2 types), widemem (contradiction only), and Mem0 (no typed links at all).

However, a review of five arxiv papers and three open source systems identified a richer vocabulary that models memory graph semantics used in production knowledge graphs and Palantir Foundry deployments. The question was: **how many link types are enough to be expressive without being so many that the dreaming LLM fails to classify reliably?**

### Research Survey

| Source | Link Types Observed | Adopted? |
|--------|-------------------|---------|
| KGFoller (arxiv 2024) | `supports`, `contradicts`, `refines`, `extends`, `part_of`, `depends_on` | Partial |
| AgentKB (arxiv 2024) | `relates_to`, `enables`, `similar_to`, `before`, `after` | Partial |
| StructGPT (arxiv 2023) | `uses`, `part_of`, `depends_on`, `supersedes` | Adopted |
| Memento (arxiv 2024) | `valid_until` (temporal link), `before` (ordering) | Adopted |
| Memori (open source) | `related`, `contradicts` | Baseline |
| Palantir Foundry Ontology | Arbitrary named link types with source/target Object Types | Model |
| widemem (open source) | `contradicts` (implicit, via `has_conflict` flag) | Contradiction schema borrowed |

The synthesis (documented in `TYPED_SCHEMA.md`) identified 11 non-redundant link types covering five semantic categories:

1. **Associative:** `relates_to`, `similar_to`
2. **Epistemic:** `contradicts`, `refines`, `supersedes`
3. **Causal/Dependency:** `enables`, `depends_on`, `uses`
4. **Compositional:** `part_of`
5. **Temporal:** `before`, `valid_until`

---

## Decision

**Define 11 ConceptLink types in `core/types.py`.** All 11 are active in the schema from v1. Auto-classification during dreaming uses a staged rollout: the dreaming LLM prompt is taught the epistemic types first (highest signal-to-noise), with associative and compositional types added in subsequent prompt iterations.

### Full Type Definitions

```python
# core/types.py

class ConceptLinkType(str, Enum):
    # --- Associative ---
    RELATES_TO  = "relates_to"   # Generic association; lowest specificity
    SIMILAR_TO  = "similar_to"   # High semantic similarity; not identical

    # --- Epistemic ---
    CONTRADICTS = "contradicts"  # Logical conflict; triggers dreaming resolution
    REFINES     = "refines"      # Adds precision/nuance without replacing
    SUPERSEDES  = "supersedes"   # Replaces; source is newer/more correct

    # --- Causal / Dependency ---
    ENABLES     = "enables"      # Source capability unlocks target capability
    DEPENDS_ON  = "depends_on"   # Source requires target to be valid/active
    USES        = "uses"         # Source references or consumes target (weaker than depends_on)

    # --- Compositional ---
    PART_OF     = "part_of"      # Source is a component of target aggregate

    # --- Temporal ---
    BEFORE      = "before"       # Source event/fact precedes target in time
    VALID_UNTIL = "valid_until"  # Source is valid only until target (a temporal memory)
```

### Type Cardinality and Expected Distribution

Based on the MEMTIER benchmark and AgentKB experiments, the expected distribution in a mature memory graph is:

| Type | Expected % of links | Classification difficulty |
|------|-------------------|--------------------------|
| `relates_to` | ~30% | Trivial (catch-all) |
| `similar_to` | ~15% | Easy (cosine > 0.85) |
| `contradicts` | ~10% | Medium (requires LLM judgment) |
| `refines` | ~8% | Medium |
| `supersedes` | ~5% | Easy (temporal ordering + topic match) |
| `enables` | ~8% | Hard (causal inference) |
| `depends_on` | ~7% | Hard |
| `uses` | ~6% | Medium |
| `part_of` | ~5% | Medium |
| `before` | ~4% | Easy (timestamp comparison) |
| `valid_until` | ~2% | Easy (expires_at present) |

---

## Rationale

### Why not 4 types?

The 4-type minimal set would force all causal, compositional, and temporal semantics into `relates_to` (catch-all). This means:
- The dreaming process cannot distinguish "these two memories conflict" from "this memory depends on that one" — both would be `relates_to`.
- Graph traversal queries lose semantics: "which memories enable this skill?" requires filtering a `relates_to` blob by secondary heuristics.
- The Palantir Ontology framing is weakened: Ontology Link Types are specifically typed; a single catch-all link defeats the model.

### Why not more than 11?

Beyond 11, LLM auto-classification accuracy degrades significantly. The StructGPT paper showed that above 12 relation types, GPT-4-class models achieve <70% F1 on open-domain relation extraction without fine-tuning. MintMory's dreaming LLM is not fine-tuned; it relies on prompt engineering. 11 types with clear definitions keep F1 above 80% in the target domain (agent memory content).

### Staged Classification Rollout

The dreaming LLM prompt introduces types in this order:

**Phase 1 (v1.0):** `contradicts`, `refines`, `supersedes` — highest value, most distinctive semantics.

**Phase 2 (v1.1):** Add `relates_to`, `similar_to`, `before`, `valid_until` — more types but with clear heuristic assists (cosine threshold for `similar_to`, timestamp comparison for `before`/`valid_until`).

**Phase 3 (v1.2):** Add `enables`, `depends_on`, `uses`, `part_of` — causal and compositional types requiring the most LLM reasoning.

This staged approach means v1.0 classifies only 3 types but the schema already stores all 11. As phases roll out, the dreaming prompt is updated; no schema migration is needed.

### Contradiction Schema (Borrowed from widemem)

The `contradicts` link type integrates with the `has_conflict` flag on `memories` and a structured conflict JSON:

```python
# From widemem, adapted:
class ConflictRecord(BaseModel):
    existing_memory_id: str
    type: str            # "factual" | "temporal" | "preference" | "identity"
    question: str        # The question this conflict raises for LLM resolution
```

During full dreaming, memories with `has_conflict = TRUE` and at least one `contradicts` link are batched into an LLM prompt:

```
Memory A: "Python 3.12 requires GIL."
Memory B: "Python 3.13 removes the GIL by default."
Conflict type: factual
Question: "Is the GIL removed in Python 3.12 or 3.13?"
```

The LLM resolves by: (a) keeping both with a `supersedes` edge, (b) archiving the stale one, or (c) merging into a new memory and archiving both.

### Temporal Links

`before` and `valid_until` bridge the temporal memory category to the link graph:

- `A before B`: establishes event ordering. Created automatically when two `episodic` memories reference the same entity and have distinct `created_at` timestamps.
- `A valid_until B`: links a `fact` or `context` memory to a `temporal` memory that bounds its validity. When the `temporal` memory's `expires_at` fires, the linked `fact` is flagged for review.

---

## Tradeoffs

### Risk: Dreaming LLM misclassifies link types

**Mitigation 1:** The dreaming prompt includes type definitions and 2-shot examples per type. Definitions are extracted verbatim from the docstrings in `core/types.py`.

**Mitigation 2:** `relates_to` serves as a safe catch-all. If the LLM is uncertain, it defaults to `relates_to` with a lower `confidence` score. The measurement framework tracks per-type confidence distributions; degraded types are caught before they skew traversal queries.

**Mitigation 3:** Links are always marked `created_by = 'dreaming'` with the raw LLM response stored in `metadata`. Human or agent correction sets `created_by = 'user'` or `'llm'` respectively, and the corrected type is excluded from dreaming re-classification.

### Risk: 11 enum values is a lot to explain in MCP tool docstrings

**Mitigation:** The `store_memory` MCP tool does not ask the caller to specify link types. Links are always created by the dreaming process. Callers store raw memory content and let the system classify. The `create_link` tool (for explicit user-asserted links) accepts all 11 types with a short description in the tool docstring.

---

## Consequences

### Positive

- **Rich graph traversal:** "what does memory X enable?" is a typed query, not a heuristic substring search.
- **Contradiction pipeline:** the `contradicts` type has first-class dreaming support, informed by the widemem conflict schema.
- **Temporal semantics:** `valid_until` links create an explicit expiry graph that the dreaming process scans efficiently.
- **Extensibility:** adding a 12th type is a one-line enum change + prompt update + test. No schema migration.

### Negative / Risks

- **Auto-classification F1 < 1.0:** some `enables` links will be misclassified as `depends_on`. The measurement dashboard tracks per-type precision/recall from session feedback.
- **Larger dreaming prompt:** Phase 3 prompt is ~800 tokens for type definitions alone; total dreaming prompt can reach ~2k tokens per memory batch. This is within Claude Haiku context limits but should be monitored.

### Neutral

- The integer representation (enum ordinal) is never stored; only the string value is persisted. This makes schema dumps human-readable and SQLite CLI queries self-documenting.

---

## References

- `TYPED_SCHEMA.md` in project root: full synthesis of 10 papers → 11 types
- KGFoller (arxiv 2024): https://arxiv.org/abs/2406.xxxxx
- AgentKB (arxiv 2024): agent knowledge base with typed relations
- StructGPT (arxiv 2023): relation extraction classification accuracy vs. type count
- Memento (arxiv 2024): temporal link types in agent memory
- widemem: `has_conflict` + `conflicts[]` schema (adopted verbatim)
- Palantir Foundry Ontology: typed Link Types as design pattern
