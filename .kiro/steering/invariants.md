# Invariants

Hard rules. Each is guarded by a test. Violating one is a bug, not a style
choice. Source: `AGENTS.md` §4–§5.

## Contradiction detection schema

The contradiction prompt expects JSON matching `ConflictCheckResult` /
`ConflictDetail` in `types.py`. Correct fields:

- `ConflictCheckResult`: `has_conflict: bool`, `conflicts: list[ConflictDetail]`.
- `ConflictDetail`: `new_fact`, `existing_memory_id`, `existing_content`,
  `type: Literal["contradiction", "ambiguity"]`, `question: Optional[str]`.

Never use these wrong names (from an obsolete draft): `is_contradiction`
(use `has_conflict`), `contradicts_memory_ids` (use
`conflicts[].existing_memory_id`).

## ConceptLinkType is a closed enum

The complete set is the 12 members in `types.py`: `relates_to, contradicts,
refines, supersedes, enables, depends_on, similar_to, part_of, uses, before,
valid_until, annotates`. (`AGENTS.md` says "11" and omits `annotates` — that
count is stale; `types.py` is the source of truth and `schema.sql` matches it.)

Adding one requires, in order: `types.py` enum -> `schema.sql` `link_type`
CHECK -> OpenAPI `link_type` enum -> run `test_schema.py`. Partial updates
cause runtime FK/CHECK failures.

## Score caps

`usefulness_score` and `staleness_score` stay in `[0.0, 10.0]`, enforced by
Pydantic (`ge=0.0, le=10.0`) and a SQL CHECK. Every write path (QueryFeedback,
rehabilitation) must clamp with `min(score, 10.0)` / `max(score, 0.0)` — never
write a raw LLM float unclamped.

## Dreaming idempotency

A full dream run twice on the same DB yields identical `DreamReport` fields.

- Anomaly detection: read-only, no writes.
- Concept linking: `INSERT OR IGNORE` (UNIQUE on
  `(source_memory_id, target_memory_id, link_type)`).
- Summary generation: `INSERT OR REPLACE` on the UNIQUE `concept` column.
- Contradiction resolution: no-op if `flagged_for_review = 0`.
- Archival: no-op if `is_archived = 0`.
- Rehabilitation: no-op if `is_stale = 1`.

## SQLite foreign keys

`PRAGMA foreign_keys = ON` does not persist across connections. Re-assert it in
every new connection in `StorageAdapter`, including test fixtures — a missing
pragma silently corrupts FKs.

## FTS5 triggers

`memories_fts` is kept in sync by three triggers (`memories_fts_insert`,
`memories_fts_update`, `memories_fts_delete`). Never write to `memories_fts`
directly — only via the `memories` table.

## Schema compliance is non-negotiable

`packages/core/tests/test_schema.py` asserts every `MemoryCategory`,
`ConceptLinkType`, `MemorySource`, and `LinkSource` value is present in the
matching `schema.sql` CHECK constraint, and that all expected tables and the
three FTS5 triggers exist. If it fails, fix the DDL before anything else.

## Working rules

- Spec-first: read `types.py` (always), `schema.sql` (storage changes), the
  OpenAPI spec (interface changes), and `docs/research/FEATURES.md` (feature
  context) before writing code. Read the real types; do not infer them.
- TDD: write the failing test, confirm it fails for the right reason,
  implement, then run `uv run pytest`.
- Never change `types.py` without updating `schema.sql` and the OpenAPI spec.
