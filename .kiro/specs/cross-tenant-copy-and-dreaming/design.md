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
- `multi-tenancy` committed these signatures this spec relies on:
  `get_memory(id, tenant_id=None)`, `get_annotating_notes(memory_id,
  tenant_id=None)`, `get_links(id, tenant_id=None)`,
  `memory_exists_with_content(content, tenant_id=None)`, `add_memory`, `add_link`
  (with the same-tenant rule), and `tenant_id` on every dreaming helper. It also
  provides the `TenantError` types and a `transaction()` context on the SQLite
  backend (Postgres provides an equivalent) used for the atomic copy.
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
    memories_copied: int = 0            # records written where is_note == False
    memories_skipped_duplicate: int = 0
    memories_skipped_not_found: int = 0
    notes_copied: int = 0              # records written where is_note == True
    notes_skipped_duplicate: int = 0
    links_copied: int = 0              # NON-ANNOTATES links from step 5 only

def copy_between_tenants(
    store: StorageBackend,
    *,
    source_tenant: str,
    dest_tenant: str,
    memory_ids: list[str] | None = None,
    filter: MemoryFilter | None = None,  # None distinct from MemoryFilter() (empty)
    force: bool = False,
) -> CopyReport: ...
```

`CopyReport` is a new type in `types.py`; not a table, so no schema surface.

Counting rules (single source of truth — the counters partition by the written
record's `is_note` flag, so no record is counted twice):
- Every newly written record increments exactly ONE of `memories_copied`
  (`is_note == False`) or `notes_copied` (`is_note == True`), keyed by its source
  id in `copy_map` so it is written/counted at most once even if it is reached
  both as a selected memory and as an annotation.
- `links_copied` counts ONLY the step-5 NON-ANNOTATES links. ANNOTATES links are
  created as part of copying a note (step 4) and are implied by `notes_copied`;
  step 5 skips `link_type == ANNOTATES`, so no ANNOTATES link is double-created or
  double-counted.
- A content-duplicate note already in the destination increments
  `notes_skipped_duplicate`; its ANNOTATES link to the destination's existing
  twin of the memory IS still created (so the annotation is preserved) but is not
  counted in `links_copied`.
- A memory skipped as a duplicate does NOT get its notes/links copied (its
  destination twin is the pre-existing row; copy never mutates existing rows).
- No `embedder` parameter: copies index through the normal `add_memory` path,
  which owns embedding; the copy function never embeds directly.

### Atomicity mechanism

`multi-tenancy` exposes a `transaction()` context on the SQLite backend plus
`_on_conn` write variants that run on a provided connection WITHOUT committing
(Req 5.8). `copy_between_tenants` opens one `store.transaction()` and performs
every insert on it, so a failure rolls the whole copy back (no partial copy).
(The Postgres `transaction()` + `_on_conn` equivalents are delivered by
`multi-tenancy-postgres`; since this spec depends on `multi-tenancy` — not
directly on the Postgres unit — the copy function targets the `StorageBackend`
Protocol's `transaction()`, which `multi-tenancy` adds to `ports.py` and the
SQLite backend, and which the Postgres backend implements when that unit lands.)
Embedding happens in-process via the store's embedder (no external call in the
default config), inside the transaction boundary. If the backend cannot provide a
single-transaction guarantee, the function MUST raise rather than partial-copy.

### Algorithm (one `store.transaction()` — all-or-nothing, Req 2 atomicity)

1. **Validate** (checked in this precedence; first failure wins):
   - source/dest id fails the charset → `InvalidTenantIdError`.
   - `source_tenant == dest_tenant` → `ValueError("source == dest")`.
   - `memory_ids is None and filter is None and not all_active` →
     `ValueError("empty selection")`.
   - `filter is not None and filter.tenant_id not in (None, source_tenant)` →
     `ValueError("filter tenant conflicts with source")`.
   - `store.get_tenant(source_tenant) is None` → `TenantNotFoundError`.
   - `store.get_tenant(dest_tenant) is None` → `TenantNotFoundError`; dest
     inactive → `TenantInactiveError`.
   (The three `ValueError` cases are plain `ValueError` with distinct messages;
   the tenant cases use the typed `multi-tenancy` errors. Tests assert on type +
   message.)
2. **Resolve selection** within the source tenant only (committed
   `multi-tenancy` reads):
   - ids → `store.get_memory(id, tenant_id=source_tenant)` each; `None`, or a row
     that is archived/inactive/superseded → `memories_skipped_not_found` (never
     resurrect, Req 3.7).
   - filter / `all_active` → `store.list_memories(filter or MemoryFilter(),
     tenant_id=source_tenant, limit=COPY_MAX)` (active, non-archived rows). If the
     result hits `COPY_MAX`, raise (no silent truncation, Req 3.8).
   - `S` = union de-duped by source id; `copy_map: src_id -> new_id` also prevents
     double-copying a record that is both a selected memory and an attached note.
3. **Copy memories.** For each `m` in `S` not already in `copy_map`:
   - If not `force` and `store.memory_exists_with_content(m.content,
     tenant_id=dest_tenant)` → `memories_skipped_duplicate`, continue.
   - Build the destination `MemoryRecord` per the exact field mapping in the
     requirements (copy content/category/source/is_note/confidence/validity/
     entity_ids; reset counters/flags/last_accessed_at; fresh id/created_at/
     updated_at; `tenant_id = dest_tenant`; merge provenance into `metadata`).
   - `store.add_memory(new)` (re-embeds / re-indexes via the normal write path →
     Req 2.4). Record `copy_map[m.id] = new.id`; `memories_copied += 1`.
4. **Copy notes.** For each copied memory, `store.get_annotating_notes(
   memory_id, tenant_id=source_tenant)`. For each note not already in `copy_map`
   (so a note selected directly AND as an annotation is copied once), copy it
   like step 3, then create an ANNOTATES link from the new note to the new
   memory in the destination. `notes_copied` counts distinct notes copied.
5. **Copy endpoint-included links.** For source links among `S` where BOTH
   endpoints are in `copy_map`: `store.add_link(ConceptLink(..., tenant_id=
   dest_tenant, source=copy_map[src], target=copy_map[tgt], ...))`, preserving
   `link_type/strength/confidence/entity`. Single-endpoint links are skipped
   (Req 4.3). The `multi-tenancy` same-tenant rule makes Req 4.4 hold.
6. **Commit** the transaction and **return** `CopyReport`. On any exception the
   transaction rolls back (no partial copy) and the error propagates.

Summaries are never touched (Req 4.5). Idempotency (Req 5.4): on a second run the
content-duplicate check skips already-copied memories, so no new duplicates.

### Scope enforcement

The core function is scope-agnostic. `ScopeRequiredError` is defined in
`multi-tenancy` (the error table reserves it; it lives in `types.py` with the
other `TenantError` subtypes and has the 403 HTTP mapping) — this spec does NOT
redefine it, it just raises it. Enforcement that **only global scope may call
it** lives in the transports:
- MCP `tenant_copy`: `if _scope_tenant != TENANT_GLOBAL: raise ScopeRequiredError`
  before calling the core function. The `source`/`dest` args name endpoints only;
  they never change `_scope_tenant`. This spec updates the `tenant-scoped-mcp`
  Req 4b inventory allow-list to include `tenant_copy`.
- CLI `tenant copy`: allowed only when the resolved `--tenant` is absent/`global`;
  under a named `--tenant` it exits non-zero with `ScopeRequiredError`.

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

Every step forwards `self.tenant_id`:
- **Reads** (anomaly getters, candidate scans, `list_active_memory_ids`,
  `get_rehabilitable_rows`, etc.) pass `tenant_id=self.tenant_id` to the
  tenant-aware helpers.
- **Writes** (step 2 `add_link`, step 3 `upsert_summary`, step 4 resolution
  updates, step 5/6 archive/rehabilitate updates) MUST stamp/confine to the
  tenant: links are created with `tenant_id=self.tenant_id`; summaries upserted
  with `tenant_id=self.tenant_id` (keyed on the per-tenant `(tenant_id,
  concept)` unique); archival/rehabilitation/resolution updates target only rows
  of `self.tenant_id`. When `tenant_id is None`, every write stamps `"global"` /
  updates all rows exactly as today.

Because `multi-tenancy` made the helpers filter by tenant when given one and
behave exactly as today when `None`, a `None` engine is today's engine (Req 6.6)
and a scoped engine is confined (Req 6.1, 6.2).

Per-tenant idempotency (Req 6.5) follows from the per-tenant UNIQUE constraints
(`(tenant_id, concept)` and `(tenant_id, source, target, link_type)`) from
`multi-tenancy` — `INSERT OR IGNORE` / `ON CONFLICT` dedupe within the tenant.

### Global run = iterate tenants

A helper orchestrates a global run without cross-tenant mixing:

```python
from mintmory.core.types import DreamIntensity, DreamReport

class DreamAllReport(BaseModel):
    """Aggregate of per-tenant dream runs (new additive shape)."""
    per_tenant: dict[str, DreamReport] = Field(default_factory=dict)
    skipped_inactive: list[str] = Field(default_factory=list)
    failed: dict[str, str] = Field(default_factory=dict)  # tenant_id -> error

    @property
    def single(self) -> DreamReport:
        """The sole report (single-tenant / today case)."""
        if len(self.per_tenant) != 1:
            raise ValueError("single requires exactly one tenant report")
        return next(iter(self.per_tenant.values()))

def dream_all_tenants(
    store, *, intensity: DreamIntensity, **engine_kwargs
) -> DreamAllReport:
    rep = DreamAllReport()
    for t in store.list_tenants():
        if not t.is_active:
            rep.skipped_inactive.append(t.id)   # dreaming writes; inactive = RO
            continue
        engine = DreamingEngine(store, tenant_id=t.id, **engine_kwargs)
        try:
            rep.per_tenant[t.id] = (
                engine.run_full() if intensity is DreamIntensity.FULL
                else engine.run_light()
            )
        except Exception as e:  # one tenant's failure does not abort the run
            rep.failed[t.id] = str(e)
    return rep
```

Each tenant gets its own engine, so no step sees two tenants at once (Req 6.4).
Inactive tenants are skipped (dreaming writes); a failing tenant is recorded and
the run continues. `intensity` is the existing `DreamIntensity` enum.

Engine `tenant_id` semantics for dreaming specifically: a dreaming engine scoped
to tenant `X` (including `"global"`) passes `X` to BOTH the read helpers and the
write calls. This is the ONE deliberate exception to the "never pass literal
`global` to a read" rule: `dream_all_tenants` builds `DreamingEngine(
tenant_id="global")` for the global tenant so that the global tenant dreams only
over its own rows (never linking global memories to a named tenant's). The
exception is sound because dreaming must stay within one tenant; it does not
apply to ordinary reads, which still use `None` for "all rows".

### Resolving which path to take

- Named-scope caller (`_effective_tenant()` == `T`): `DreamingEngine(store,
  tenant_id=T).run_full()/run_light()` → one `DreamReport` (Req 6.3).
- Global-scope caller (`_effective_tenant()` is `None`): `dream_all_tenants(...)`
  → `DreamAllReport` (Req 6.4). Single-`global` DB → `.single` == today (Req 6.6).

---

## Transport surface

### MCP (`tenant-scoped-mcp` server)
- New tool `tenant_copy(source_tenant: str, dest_tenant: str, memory_ids:
  list[str] | None = None, filter: dict | None = None, all_active: bool = False,
  force: bool = False)`. The JSON `filter` dict is parsed into a `MemoryFilter`;
  `all_active=True` = whole-tenant copy (avoids the ambiguous empty `{}`).
  Global-scope-only guard (`ScopeRequiredError` otherwise) → `copy_between_tenants`
  → `CopyReport.model_dump(mode="json")`. This spec adds `tenant_copy` to the
  `tenant-scoped-mcp` Req 4b inventory allow-list.
- `memory_dream` tool — **this spec owns its final wiring** (replacing the
  `tenant-scoped-mcp` stub). The output rule keys PURELY on scope (Req 6.6):
  - named scope `T` → `DreamingEngine(tenant_id=T).run_*()` → return the bare
    `DreamReport` JSON.
  - global scope → ALWAYS `dream_all_tenants(...)` → return the `DreamAllReport`
    JSON, even when `global` is the only tenant. Never calls `.single`; never
    keys on tenant counts.
  A test asserts: named → `DreamReport`; global (one-tenant DB) → `DreamAllReport`
  whose `per_tenant["global"]` equals today's mutations; global (multi-tenant) →
  `DreamAllReport` with an entry per active tenant and `failed`/`skipped_inactive`
  populated as appropriate.

### CLI (`main.py`)
- `tenant copy <source> <dest> [--id ID]... [--category C] [--note] [--entity E]
  [--all-active] [--force]` — `--id` repeatable; filters + ids combine as a
  UNION; `--all-active` = whole-tenant. Global/admin command, allowed only when
  `--tenant` is absent/`global` (`ScopeRequiredError` under a named `--tenant`);
  no selectors and no `--all-active` → empty-selection rejection.
- `dream` command honours the resolved `--tenant`: named → scoped engine
  (one report); global/absent → `dream_all_tenants` (aggregate).

### Core
- `copy_between_tenants` + `CopyReport` in `core/transfer.py` (+ `CopyReport` in
  `types.py`). `ScopeRequiredError` already exists in `types.py` (defined by
  `multi-tenancy`); this spec imports it.
- `DreamingEngine(tenant_id=...)`, `dream_all_tenants`, `DreamAllReport` in
  `dreaming.py` / `types.py`.
- No REST API changes in this ticket.

### Ownership vs `tenant-scoped-mcp` (resolves the duplicate-scope finding)
`tenant-scoped-mcp` deliberately left `memory_dream`'s global behaviour and the
`DreamingEngine` scope to THIS spec; it only passed `_effective_tenant()` into
the then-existing dreaming helpers as interim behaviour. This spec defines the
engine scope + the global loop and rewires `memory_dream`/`dream` to them. There
is one owner for the final behaviour (here); no double implementation.

---

## Testing strategy

Copy (unit, `:memory:`, mock embedder, two tenants seeded):
- Global-only: named-scope `tenant_copy` raises `ScopeRequiredError`, no writes;
  global allowed.
- Copy leaves source intact (ids/flags/content unchanged in source).
- Field mapping: copied fields preserved, counters/flags reset, new id/timestamps,
  `metadata` provenance; copy searchable under dest scope.
- Notes travel and re-anchor; a record that is both a selected memory and an
  attached note is copied exactly once (count == 1).
- Endpoint-included links copied; single-endpoint links skipped; no cross-tenant
  link exists; summaries never copied.
- Duplicate skip by default + `force` creates; report counts correct; re-run
  idempotent for content.
- Rejections: empty selection (no ids, no filter); `filter.tenant_id` ≠ source;
  `source == dest`; missing/inactive dest; missing source — each with the stated
  error.
- Atomicity: inject a failure mid-copy (e.g. one `add_memory` raises) and assert
  the destination has zero new rows (full rollback).

Dreaming (unit):
- Scoped engine touches only its tenant (seed memories in two tenants; assert no
  cross-tenant links/resolution/summaries); writes stamped with the tenant.
- Per-tenant idempotency: second scoped run → 0 new links/summaries.
- `dream_all_tenants` iterates every tenant and returns a `DreamAllReport`.
- Single-`global`-tenant parity: `dream_all_tenants(...).single` equals today's
  `run_full`/`run_light` mutations and report shape.

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
