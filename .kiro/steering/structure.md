# Structure

uv workspace monorepo. Packages depend only on `core`:

```
core  ->  mcp
      ->  api
      ->  cli
      meta   (aggregator / distribution package)
```

`mcp`, `api`, and `cli` do not depend on each other and can be developed in
parallel once `core` has a stable interface.

## Packages

```
packages/
├── core/   mintmory-core — the only package with domain logic
│   └── src/mintmory/core/
│       ├── types.py            Pydantic models + enums — SOURCE OF TRUTH
│       ├── schema.sql          SQLite DDL (derived from types.py)
│       ├── schema_postgres.sql Postgres DDL
│       ├── storage.py          StorageAdapter (SQLite CRUD, FTS, vector)
│       ├── storage_postgres.py Postgres storage backend
│       ├── storage_factory.py  backend selection
│       ├── hybrid_search.py    FTS + vector hybrid search
│       ├── embedder.py         EmbedderProtocol + implementations
│       ├── entities.py         entity extraction
│       ├── scoring.py          effective_score + staleness updates
│       ├── dreaming.py         DreamingEngine (light + full)
│       ├── session.py          QuerySession lifecycle + feedback
│       ├── cochange.py         co-change analysis
│       ├── tree_index.py       recurrent tree indexing
│       ├── telemetry.py        telemetry
│       ├── migrate.py          schema migrations
│       ├── prompts.py / llm.py / vision.py / notes.py / conversion.py / config.py / ports.py
│       └── tests/
├── mcp/    mintmory-mcp — fastmcp server (server.py, tools.py)
├── api/    mintmory-api — FastAPI REST (main.py, routes/, schemas.py)
├── cli/    mintmory-cli — Typer (main.py)
└── meta/   distribution/aggregator package
```

Cross-package integration tests live in `tests/integration/` (real SQLite file,
canned LLM responses). Docs and specs live in `docs/` and `openspec/`.

Note: `AGENTS.md` predates some `core` modules. The file list above reflects
what is actually on disk; `AGENTS.md` lists a smaller historical subset and
calls the extraction module `entity.py` (the real file is `entities.py`).

## Source-of-truth hierarchy

```
types.py  >  schema.sql  >  docs/openapi/mintmory.yaml
```

Never edit `schema.sql` or the OpenAPI spec to resolve a conflict without first
updating `types.py`. Schema compliance tests enforce that enum values in
`types.py` match the CHECK constraints in `schema.sql`.

## What to touch per change

| Change | Files |
|---|---|
| New `MemoryRecord` field | `types.py` -> `schema.sql` (+ `schema_postgres.sql`) -> `docs/openapi/mintmory.yaml` |
| New `ConceptLinkType` | `types.py` enum -> `schema.sql` CHECK -> OpenAPI enum -> run `test_schema.py` |
| New MCP tool | `packages/mcp/.../tools.py` + test |
| New API route | `packages/api/.../routes/` + test |
| Scoring change | `packages/core/.../scoring.py` + `docs/research/FEATURES.md` |
| Dreaming step change | `packages/core/.../dreaming.py` + idempotency test |
