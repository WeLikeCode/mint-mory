# Requirements — Multi-Tenancy 7/10: cross-tenant copy

> **Depends on:** `multi-tenancy-writes` (re-entrant `store.transaction()`, the
> write guard, same-tenant `add_link`), `multi-tenancy-reads`
> (`get_memory(id, tenant_id)`, `list_memories(filter, *, tenant_id, limit)`,
> `memory_exists_with_content(content, tenant_id)`,
> `get_annotating_notes(memory_id, cap, tenant_id)`, `get_links(memory_id,
> link_type=None, tenant_id=None)`), `tenant-scoped-mcp` (`_scope_tenant`,
> `TOOL_TENANT_SCOPE`, the tool-parameter test), `multi-tenancy-cli` (the root
> `--tenant`, `_read_tenant()`, the `tenant` group, `_tenant_errors()`) and
> `multi-tenancy` (`validate_tenant_id`, `get_tenant`, `TENANT_GLOBAL`,
> `ScopeRequiredError(operation, scope)`, `TenantNotFoundError`,
> `TenantInactiveError`). Adds `packages/core/src/mintmory/core/transfer.py`, one
> MCP tool and one CLI command. No schema, OpenAPI or REST change.

## Introduction

Copy (never move) memories, their attached notes and the links among the copied
records from one tenant into another, as one atomic operation available only to
the global scope. The source is never modified. Summaries, sessions and query
results are never copied (dreaming regenerates summaries in the destination).

## Requirements

### Requirement 1 — Core function and report (`transfer.py`)

#### Acceptance Criteria

1. `transfer.py` SHALL define:

   ```python
   COPY_MAX: Final[int] = 10_000

   class CopySelectionError(ValueError): ...

   class CopyReport(BaseModel):
       source_tenant: str
       dest_tenant: str
       memories_copied: int = 0             # copied records with is_note False
       memories_skipped_duplicate: int = 0
       memories_skipped_not_found: int = 0
       notes_copied: int = 0                # copied records with is_note True
       notes_skipped_duplicate: int = 0
       links_copied: int = 0                # every link created, ANNOTATES included
       id_map: dict[str, str] = Field(default_factory=dict)  # source id -> new id

   def copy_between_tenants(store: StorageBackend, *, source_tenant: str,
       dest_tenant: str, memory_ids: list[str] | None = None,
       filter: MemoryFilter | None = None, all_active: bool = False,
       force: bool = False) -> CopyReport: ...
   ```

   `CopyReport` lives in `transfer.py`, not `types.py`: it is neither stored nor
   served by the HTTP API.

### Requirement 2 — Validation (first failure wins, nothing written)

#### Acceptance Criteria

1. In this order: (a) `validate_tenant_id` on both ids → `InvalidTenantIdError`;
   (b) `source_tenant == dest_tenant` → `CopySelectionError("source and
   destination are the same tenant")`; (c) `all_active` with `memory_ids` or a
   `filter` → `CopySelectionError("all_active cannot be combined with memory_ids
   or filter")`; (d) `filter == MemoryFilter()` → `CopySelectionError("empty
   filter: use all_active=True to copy every active memory")`; (e) no
   `memory_ids` (None or empty), no `filter` and not `all_active` →
   `CopySelectionError("empty selection: pass memory_ids, filter or
   all_active=True")`; (f) more than `COPY_MAX` distinct ids →
   `CopySelectionError(f"selection exceeds {COPY_MAX} memories")`; (g)
   `get_tenant(source_tenant)` is `None` → `TenantNotFoundError(source_tenant)`;
   (h) `get_tenant(dest_tenant)` is `None` → `TenantNotFoundError(dest_tenant)`,
   inactive → `TenantInactiveError(dest_tenant)`. An inactive source is allowed
   (reads of an inactive tenant are permitted).
2. A whole-tenant copy is requested only by `all_active=True`; an empty filter is
   rejected so that `{}` from a JSON client is never read as "copy everything".

### Requirement 3 — Selection (reads confined to the source tenant)

#### Acceptance Criteria

1. Explicit ids, in input order without repeats: `get_memory(id,
   tenant_id=source_tenant)`; a `None` result or a row that is archived,
   inactive or superseded (`superseded_by` set) counts once in
   `memories_skipped_not_found` and is never read from another tenant.
2. `filter`: `list_memories(filter, tenant_id=source_tenant, limit=COPY_MAX +
   1)`; `all_active`: the same with `MemoryFilter(exclude_stale=False)` (every
   active, non-archived memory, stale ones included). Rows that are inactive or
   superseded are dropped. More than `COPY_MAX` rows →
   `CopySelectionError(f"selection exceeds {COPY_MAX} memories")`.
3. The selection `S` is the id rows then the filter rows, de-duplicated by source
   id (first occurrence wins).
4. Attached notes (one level): for each record of `S` that will be copied, every
   note of `get_annotating_notes(record.id, COPY_MAX, tenant_id=source_tenant)`
   not yet seen joins the copy. A note reached twice, or both selected and
   attached, is handled once. More than `COPY_MAX` records in total →
   `CopySelectionError(f"selection exceeds {COPY_MAX} memories")`.

### Requirement 4 — Duplicates

#### Acceptance Criteria

1. Unless `force`, a record whose exact content exists in the destination
   (`memory_exists_with_content(content, tenant_id=dest_tenant)`) SHALL be
   skipped and counted in `memories_skipped_duplicate` or
   `notes_skipped_duplicate` by its `is_note`.
2. A skipped record gets no link and its attached notes are not expanded: copy
   never references or modifies a row that already exists in the destination.
3. With `force=True` duplicates are copied.
4. Re-running the same copy without `force` SHALL create no record.

### Requirement 5 — What a copied record contains

#### Acceptance Criteria

1. New `id` (uuid4, assigned before any write so references can be rewritten),
   `tenant_id = dest_tenant`, `created_at = updated_at = now`.
2. Copied: `content`, `category`, `source`, `verified`, `is_note`, `confidence`,
   `valid_from`, `valid_until`, `entity_ids`.
3. Reset: `usefulness_score = staleness_score = 0`, `reinforcement_count =
   retrieval_count = 0`, `is_stale = False`, `is_active = True`, `is_archived =
   False`, `superseded_by = None`, `flagged_for_review = False`, `contradicts_ids
   = []`, `last_accessed_at = None`.
4. `metadata = {**source.metadata, "copied_from_tenant": source_tenant,
   "source_memory_id": source.id}` (these two keys overwrite existing values; all
   other keys are copied verbatim); `metadata["anchor_memory_id"]`, when present,
   becomes `id_map[old]`, or the key is removed when that memory is not copied.
5. Each record is written with `store.add_memory(record=…)`, so it is indexed as
   any write to that store (FTS5, trigram, and a vector only if the store has an
   embedder); the copy never embeds itself and never copies raw embeddings.

### Requirement 6 — Links

#### Acceptance Criteria

1. For each copied source id, every link of `get_links(id,
   tenant_id=source_tenant)` whose two endpoints are both copied SHALL be created
   once (by link id) with `add_link(ConceptLink(source_memory_id=id_map[s],
   target_memory_id=id_map[t], link_type, entity, strength, confidence, source,
   verified, tenant_id=dest_tenant))` and counted in `links_copied`; a link with
   one endpoint outside the copy is not created. This includes the `ANNOTATES`
   link of an attached note.

### Requirement 7 — Atomicity, isolation and failures

#### Acceptance Criteria

1. The whole operation (selection reads, duplicate checks, writes) SHALL run
   inside one `with store.transaction():`; on any exception it rolls back,
   writes nothing in the destination, and the exception propagates; the report is
   returned only after the commit.
2. The source tenant's rows SHALL be identical (`model_dump()`) before and after.
3. A destination deactivated by another process during the copy makes the next
   `add_memory` raise `TenantInactiveError` and the whole copy rolls back; within
   one process the copy holds the transaction lock, so the deactivation waits.
   Two concurrent copies in one process run one after the other; across processes
   duplicates are possible and a re-run without `force` adds none.
4. On Postgres the function uses only Protocol methods; until
   `multi-tenancy-postgres-writes` and `multi-tenancy-postgres-reads` land,
   `transaction()` / `list_memories` raise `TenancyNotSupportedError` before any
   write, so the copy fails closed there.

### Requirement 8 — Transports (global scope only)

#### Acceptance Criteria

1. MCP tool `tenant_copy(source_tenant: str, dest_tenant: str, memory_ids:
   list[str] | None = None, filter: dict[str, Any] | None = None, all_active: bool
   = False, force: bool = False) -> dict[str, Any]`: when `_scope_tenant !=
   TENANT_GLOBAL` it raises `ScopeRequiredError("tenant_copy", _scope_tenant)`
   before any read; `filter` is parsed with `MemoryFilter.model_validate` (an
   invalid key or value is a tool error; `{}` hits R2.1(d)); it returns
   `CopyReport.model_dump(mode="json")`. `TOOL_TENANT_SCOPE["tenant_copy"] =
   "copy"`; the tool-parameter test allows exactly `{"source_tenant",
   "dest_tenant"}` for it (they name the copy endpoints and never change the
   scope); `test_all_tools_registered` gains `tenant_copy`.
2. CLI `mintmory tenant copy SOURCE DEST [--id ID]... [--category C] [--entity
   E] [--all-active] [--force] [--json]`: with a named root `--tenant T` it
   prints `error: tenant copy requires the global scope; this process is scoped to
   tenant 'T'` and exits 1; `--id` is repeatable; a filter is built only when
   `--category` or `--entity` is given (`MemoryFilter(category=…, entity=…)`);
   ids and filter combine as a union; it prints the report counters as a table,
   or the report JSON with `--json`; `CopySelectionError` and `TenantError` print
   `error: <message>` to stderr and exit 1.

### Requirement 9 — Tests

#### Acceptance Criteria

1. Seed: tenant `acme` with m1 "Alice works at Acme" and m2 "Bob works at Acme"
   (facts), a `relates_to` link m1→m2 (strength 0.7), a note n1 "Alice prefers
   mornings" annotating m1 (`ANNOTATES` n1→m1, `metadata={"anchor_memory_id":
   m1}`), an archived m3, a summary for `acme`; empty tenant `beta`.
2. `memory_ids=[m1, m2]` → `memories_copied == 2`, `notes_copied == 1`,
   `links_copied == 2`, three `beta` rows with provenance, the n1 copy's
   `anchor_memory_id == id_map[m1]`, no `beta` summary, `acme` unchanged,
   `search(SearchRequest(query="Alice"), tenant_id="beta")` finds the m1 copy.
3. `memory_ids=[m1]` → 1 memory, 1 note, 1 link (the `relates_to` is not copied).
4. Repeating R9.2 → `memories_skipped_duplicate == 2`,
   `notes_skipped_duplicate == 0` (n1 is not expanded from a skipped m1, R4.2),
   nothing copied; with `force=True` → m1, m2 and n1 are copied again.
5. `memory_ids=[m3, "nope", <a global id>]` → `memories_skipped_not_found == 3`.
6. `all_active=True` → m1, m2 and n1 each copied once (`notes_copied == 1`).
7. Each rejection of R2.1 with its type and message; `TenantInactiveError` for an
   inactive `beta`.
8. Atomicity: monkeypatch `store.add_link` to raise `RuntimeError("boom")` →
   `RuntimeError`, and `list_memories(MemoryFilter(active_only=False,
   exclude_stale=False), tenant_id="beta") == []`.
9. `monkeypatch.setattr(transfer, "COPY_MAX", 2)` with `all_active=True` over
   three memories → `CopySelectionError("selection exceeds 2 memories")`.
10. MCP: named scope → `ToolError` with `requires the global scope`, nothing
    written; global scope → report JSON. CLI: R8.2 happy path, `--json`, named
    `--tenant` refusal, empty selection exit 1.
11. Integration (`tests/integration/test_tenancy_copy.py`): copy R9.2 through the
    CLI, then `mintmory --tenant beta dream` runs inside `beta` only: no link
    joins a `beta` and an `acme` memory and every `acme` row is unchanged.

### Requirement 10 — Gates

#### Acceptance Criteria

1. The `.l4/config.yaml` gates SHALL pass with coverage ≥ 80%. No test needs
   Postgres, Docker or a network service.
