# Design — Cross-Tenant Copy & Per-Tenant Dreaming

> **Depends on:** the `multi-tenancy` spec (`.kiro/specs/multi-tenancy/`) and the
> `tenant-scoped-mcp` spec (`.kiro/specs/tenant-scoped-mcp/`). Both must be
> implemented first. This design assumes the `tenant_id` data model + storage
> scoping (from `multi-tenancy`) and the connection-level `global`-vs-named scope
> and `_effective_tenant()` / `_scope_tenant` holder (from `tenant-scoped-mcp`)
> already exist.

## Overview

Two capabilities, both expressed as pure `core` functions wrapped by thin
transport handlers:

1. **Cross-tenant copy** — a new `core` module function that, given source
   tenant, destination tenant, and a selection, creates new destination-tenant
   records (memories + their notes + endpoint-included links) with new ids and
   provenance, skipping exact-content duplicates by default. The source is never
   modified. Gated to global scope at the transport layer.

2. **Per-tenant dreaming** — `DreamingEngine` gains a tenant scope so every step
   runs within one tenant. A global caller loops all tenants. Reuses the
   `multi-tenancy` tenant arg already added to the storage dreaming helpers.

No new tables or columns are introduced; copy reuses existing write paths and
dreaming reuses the already-tenant-aware storage helpers.

### Grounding notes (verified against current code)

- `DreamingEngine.__init__(adapter, summarizer=None, conflict_resolver=None,
  link_settings=None, summary_settings=None)`; public entrypoints `run_light()`
  and `run_full()`; step methods `detect_anomalies`, `create_concept_links`,
  `generate_summaries`, `resolve_contradictions`, `archive_stale`,
  `rehabilitate`. Each step calls storage helper queries — these are the methods
  the `multi-tenancy` spec adds a `tenant_id` argument to.
- Storage already exposes `memory_exists_with_content` (used here, scoped to the
  destination by the `multi-tenancy` tenant predicate), `add_memory`, `add_link`,
  `get_links`, and the ANNOTATES note helpers (`get_annotating_notes`).
- MCP holds `_scope_tenant` + `_effective_tenant()` (from `tenant-scoped-mcp`);
  the copy tool reads `_scope_tenant` to enforce global-only.
- The CLI resolves a `--tenant` per `multi-tenancy`; it adds an admin copy
  command here.

---

## Cross-tenant copy

### New core function

A new function in a small `core` module (e.g. `core/transfer.py`):

```python
class CopyReport(BaseModel):
    source_tenant: str
    dest_tenant: str
    memories_copied: int = 0
    memories_skipped_duplicate: int = 0
    memories_skipped_not_found: int = 0
    notes_copied: int = 0
    links_copied: int = 0

def copy_between_tenants(
    store: StorageBackend,
    *,
    source_tenant: str,
    dest_tenant: str,
    memory_ids: list[str] | None = None,
    filter: MemoryFilter | None = None,
    force: bool = False,
    embedder: EmbedderProtocol | None = None,
) -> CopyReport: ...
```

`CopyReport` is a new type in `types.py` (source of truth); since it is not a
table, it adds no schema/CHECK surface.

### Algorithm

1. **Validate.** Reject if `source_tenant == dest_tenant` (Req 3.4). Reject if
   `store.get_tenant(dest_tenant) is None` (Req 3.5). (Source existence is
   implied by having rows; an empty source yields an all-zero report.)
2. **Resolve selection** within the source tenant only:
   - If `memory_ids` given: fetch each via a destination-safe scoped get on the
     source tenant; ids not present in the source → `memories_skipped_not_found`.
   - If `filter` given: scoped search/list in the source tenant.
   - The selection set `S` is the union, de-duplicated by source id.
3. **Copy memories.** For each memory `m` in `S`:
   - If not `force` and `store.memory_exists_with_content(m.content,
     tenant_id=dest_tenant)` → `memories_skipped_duplicate`, continue.
   - Build a new `MemoryRecord`: new id (default factory), `tenant_id =
     dest_tenant`, copy `content, category, source, is_note, confidence,
     valid_from, valid_until, entity_ids`; **reset** feedback/state counters
     (`usefulness_score=0, staleness_score=0, reinforcement_count=0,
     retrieval_count=0, is_stale=False, is_active=True, is_archived=False,
     superseded_by=None, flagged_for_review=False, contradicts_ids=[]`);
     `metadata = {**m.metadata, "copied_from_tenant": source_tenant,
     "source_memory_id": m.id}`.
   - `store.add_memory(new)` (re-embeds / re-indexes via the normal write path →
     Req 2.4). Record mapping `src_id -> new_id`.
4. **Copy notes.** For each copied memory, fetch its ANNOTATES notes in the
   source (`get_annotating_notes` scoped to source). Copy each note like step 3
   (new id, provenance) and create an ANNOTATES link from the new note to the new
   memory in the destination. Count `notes_copied`.
5. **Copy endpoint-included links.** For links among `S` (both endpoints mapped
   in `src_id -> new_id`): create an equivalent destination link via
   `store.add_link` with a new id, `tenant_id = dest_tenant`, preserving
   `link_type/strength/confidence/entity`. Single-endpoint links are skipped
   (Req 4.3). The `multi-tenancy` cross-tenant-link ban guarantees Req 4.4.
6. **Return** the `CopyReport`.

Summaries are never touched (Req 4.5). Idempotency (Req 5.4): on a second run the
content-duplicate check skips already-copied memories, so no new duplicates.

### Scope enforcement

The core function is scope-agnostic (it takes explicit source/dest). Enforcement
that **only global scope may call it** lives in the transports:
- MCP `tenant_copy` tool: `if _scope_tenant != TENANT_GLOBAL: raise <global
  required>` before calling `copy_between_tenants` (Req 1.2). No per-call scope
  argument can bypass this (Req 1.3).
- CLI copy command: available only when the resolved scope is global (or framed
  as an explicit admin command).

---

## Per-tenant dreaming

### Engine change

Add a tenant scope to `DreamingEngine` so each step passes it to the
already-tenant-aware storage helpers (from `multi-tenancy`):

```python
def __init__(self, adapter, summarizer=None, conflict_resolver=None,
             link_settings=None, summary_settings=None,
             tenant_id: str | None = None) -> None:
    ...
    self.tenant_id = tenant_id  # None = today's global behaviour
```

Every step method forwards `self.tenant_id` to its storage helper
(`detect_anomalies`, `create_concept_links`, `generate_summaries`,
`resolve_contradictions`, `archive_stale`, `rehabilitate`). Because the
`multi-tenancy` spec made those helpers filter by tenant when given one and
behave exactly as today when `None`, a `None` engine is today's engine
(Req 6.6), and a scoped engine is confined (Req 6.1, 6.2).

Per-tenant idempotency (Req 6.5) follows from the per-tenant UNIQUE constraints
(`(tenant_id, concept)` and `(tenant_id, source, target, link_type)`) already
added by `multi-tenancy` — `INSERT OR IGNORE` / `ON CONFLICT` dedupe within the
tenant.

### Global run = iterate tenants

A helper orchestrates a global run without cross-tenant mixing:

```python
def dream_all_tenants(store, *, intensity, **engine_kwargs) -> dict[str, DreamReport]:
    reports = {}
    for t in store.list_tenants():
        engine = DreamingEngine(store, tenant_id=t.id, **engine_kwargs)
        reports[t.id] = engine.run_full() if intensity is FULL else engine.run_light()
    return reports
```

Each tenant gets its own engine with its own scope, so no step ever sees two
tenants at once (Req 6.4). The aggregate is returned to the caller.

### Resolving which path to take

- Named-scope caller (`_effective_tenant()` == `T`): construct
  `DreamingEngine(store, tenant_id=T)` and run once (Req 6.3).
- Global-scope caller (`_effective_tenant()` is `None`): call
  `dream_all_tenants(...)` (Req 6.4). When only `global` exists this is a single
  pass over `global` == today (Req 6.6).

---

## Transport surface

### MCP (`tenant-scoped-mcp` server)
- New tool `tenant_copy(source_tenant, dest_tenant, memory_ids=None,
  filter=None, force=False)` → global-scope-only guard → `copy_between_tenants`
  → `CopyReport.model_dump(mode="json")`.
- Existing `memory_dream` tool: branch on `_effective_tenant()` — named → single
  scoped engine; global → `dream_all_tenants`, returning the aggregate reports.

### CLI (`main.py`)
- `tenant copy <source> <dest> [--id ... | --category ... | --note] [--force]`
  (global/admin command) → `copy_between_tenants`.
- Existing `dream` command honours the resolved `--tenant`: named → scoped
  engine; global/absent → `dream_all_tenants`.

### Core
- `copy_between_tenants` + `CopyReport` in `core/transfer.py` / `types.py`.
- `DreamingEngine(tenant_id=...)` + `dream_all_tenants` in `dreaming.py`.
- No REST API changes in this ticket.

---

## Testing strategy

Copy (unit, `:memory:`, mock embedder, two tenants seeded):
- Global-only: named-scope `tenant_copy` rejected, no writes; global allowed.
- Copy leaves source intact (ids/flags/content unchanged in source).
- New ids + `metadata` provenance; copy searchable under dest scope.
- Notes travel and re-anchor; endpoint-included links copied; single-endpoint
  links skipped; no cross-tenant link exists; summaries never copied.
- Duplicate skip by default + `force` creates; report counts correct;
  re-run idempotent for content.
- `source == dest` rejected; missing dest rejected.

Dreaming (unit):
- Scoped engine touches only its tenant (seed memories in two tenants; assert no
  cross-tenant links/resolution/summaries).
- Per-tenant idempotency: second scoped run → 0 new links/summaries.
- `dream_all_tenants` iterates every tenant and aggregates reports.
- Single-`global`-tenant parity: global run equals today's `run_full`/`run_light`
  output shape.

Integration (`tests/integration/`): global-scope end-to-end copy of a note +
linked memories across tenants, then a scoped dream in the destination; assert
isolation throughout.

Gate: `uv run pytest` (≥ 80%), `uv run mypy packages/`, `uv run ruff check
packages/` all exit 0.

---

## Risks and mitigations

- **Link copied with a missing endpoint** → build the `src_id -> new_id` map
  first, then only copy links whose both endpoints are in the map.
- **Duplicate check not scoped to dest** → always pass `tenant_id=dest_tenant`
  to `memory_exists_with_content`; covered by test.
- **Cross-tenant leak during a global dream** → never share an engine across
  tenants; one `DreamingEngine(tenant_id=T)` per tenant; assert in tests.
- **Provenance overwriting user metadata** → merge (`{**m.metadata, ...}`) with
  reserved keys documented; do not clobber unrelated keys.
- **Copy scope bypass** → enforcement is in the transport using `_scope_tenant`
  (not a per-call argument), matching `tenant-scoped-mcp` Req 4.
