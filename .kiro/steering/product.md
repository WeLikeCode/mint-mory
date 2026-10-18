# Product

MintMory is a typed memory system for LLM agents, modelled on the Palantir
Foundry Ontology layer: memory is typed, linked, and queryable rather than
stored as raw blobs.

## Core domain

- `MemoryRecord` — a typed memory, classified by `MemoryCategory`.
- `ConceptLink` — a typed edge between memories, typed by `ConceptLinkType`
  (a closed enum — see invariants).
- `QuerySession` + `QueryResult` — decision lineage for every search.
- `MemoryFilter` + `SearchAroundSpec` — the query/traversal surface.

All domain types live in `packages/core/src/mintmory/core/types.py`, which is
the single source of truth for the data model.

## Transports

Three transports share one domain model in `packages/core`; none duplicate
domain logic:

- CLI (`mintmory-cli`, Typer) — human / scripting.
- MCP (`mintmory-mcp`, fastmcp) — Claude Code, Cursor, Open WebUI (stdio + SSE).
- HTTP REST (`mintmory-api`, FastAPI) — external services, dashboards, webhooks.

## Feedback loop

Every search opens a `QuerySession`. On conclusion the LLM submits
`QueryFeedback` (useful vs stale memory IDs), which adjusts `usefulness_score`
and `staleness_score` on the affected records. No human in the loop.

## Dreaming

A background consolidation process run while the agent is idle:

- Light: anomaly detection -> concept linking -> summary generation.
- Full: light + contradiction resolution + archival + rehabilitation.

Every dreaming step is idempotent — running a dream twice on the same database
produces the same result.

## Authority

`AGENTS.md` at the repo root is the full agent guide and remains authoritative.
This steering summarises it; when they disagree, AGENTS.md wins.
