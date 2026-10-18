# Requirements — Cross-Tenant Copy & Per-Tenant Dreaming

> **Depends on:** the `multi-tenancy` spec (`.kiro/specs/multi-tenancy/`) and the
> `tenant-scoped-mcp` spec (`.kiro/specs/tenant-scoped-mcp/`). Both must be
> implemented first. `multi-tenancy` provides the `Tenant` model, the `tenants`
> table, the `tenant_id` columns, and the storage-level tenant scoping (the
> tenant predicate in candidate SQL + `search_around`, and the tenant arg on the
> dreaming helper queries). `tenant-scoped-mcp` provides the connection-level
> scope (`global` vs named) that gates who may perform a cross-tenant copy. This
> spec builds on both and does not re-specify them.

## Introduction

This feature adds two related capabilities on top of the tenancy foundation:

1. **Cross-tenant copy** — copy (never move; the source is untouched) memories,
   their notes, and the concept links between copied memories, from one tenant
   into another. This is a **global-scope-only** operation: only an agent with
   global access may copy across tenants. A named-tenant (hard-isolated) agent
   cannot.

2. **Per-tenant dreaming** — dreaming today runs globally. This change scopes a
   dreaming run to a tenant so consolidation (linking, summaries, contradiction
   resolution, archival, rehabilitation) happens **within one tenant only** and
   never crosses tenant boundaries. A global-scope dreaming run processes each
   tenant independently; a named-scope run processes only its own tenant.

Both capabilities preserve backwards compatibility: with a single `global`
tenant (today's state), a global dreaming run behaves exactly as today, and copy
simply has one tenant to work with.

### Decisions (locked)

- **Copy, not move.** Source records remain in the origin tenant; new rows are
  created in the destination.
- **Selection.** A copy specifies source tenant, destination tenant, and a
  selection: explicit memory ids and/or a filter (category, `is_note`, entity).
  **If BOTH `memory_ids` and `filter` are omitted, the operation is rejected**
  with a clear error (an empty selection is a mistake, not "copy the whole
  tenant"); a whole-tenant copy must be requested explicitly with an empty-but-
  present filter (`MemoryFilter()` matching all active rows). When both are
  given, the selection is their **union**, de-duplicated by source id.
- **What travels.** Selected memories + their attached notes. A concept link is
  copied only when both of its endpoints are included in the same copy. Derived
  `memory_summaries` are NOT copied — dreaming regenerates them in the
  destination.
- **New ids + provenance.** Copies get new ids in the destination; provenance is
  stamped in `metadata` (`copied_from_tenant`, `source_memory_id`). Embedding /
  FTS are (re)built so copies are searchable in the destination.
- **Field mapping (exact).** The destination copy COPIES `content`, `category`,
  `source`, `is_note`, `confidence`, `valid_from`, `valid_until`, `entity_ids`,
  and merges provenance into `metadata`. It RESETS `usefulness_score=0`,
  `staleness_score=0`, `reinforcement_count=0`, `retrieval_count=0`,
  `is_stale=False`, `is_active=True`, `is_archived=False`, `superseded_by=None`,
  `flagged_for_review=False`, `contradicts_ids=[]`, `last_accessed_at=None`. It
  SETS fresh `id`, `created_at`, `updated_at` (now) and `tenant_id=destination`.
- **Atomicity.** The whole copy runs in a single storage transaction: on any
  error it rolls back entirely and raises, leaving the destination unchanged
  (no partial copy). The report is returned only on success.
- **Duplicates.** Exact-content duplicates already present in the destination are
  skipped by default (via `memory_exists_with_content(content,
  tenant_id=destination)`) and counted; `force=true` copies them anyway. A note
  that is BOTH selected as a memory AND an attached note of another selected
  memory is copied exactly once (tracked by source id in the copy map) and
  re-anchored; the counts reflect one copy.
- **Transports.** Exposed as an MCP tool available only to global-scope agents,
  plus a CLI command. REST API is out of scope for this ticket.
- **Dreaming scope (reconciled with `tenant-scoped-mcp`).** Dreaming is always
  per-tenant once tenancy exists. This spec OWNS and defines: the
  `DreamingEngine(tenant_id=...)` scope, the `dream_all_tenants` orchestrator, and
  the final `memory_dream` / CLI `dream` wiring where **global = iterate every
  tenant independently** and **named = that tenant only**. `tenant-scoped-mcp`
  intentionally left `memory_dream`'s global behaviour to this spec and only
  passes the connection scope; there is therefore no contradiction — this spec
  replaces that interim wiring. The hard rule: no cross-tenant linking,
  contradiction resolution, or summary sharing.

### Out of scope

- Moving/deleting source data (this is copy-only).
- Copying across different databases/backends (same store only).
- Copying derived summaries, query sessions, or query results.
- Authn/authz beyond the existing global-vs-named scope distinction.
- Cross-tenant dreaming (explicitly forbidden, not merely unimplemented).

---

## Glossary

- **Copy operation** — a global-scope action producing new records in a
  destination tenant from a selection in a source tenant; the source is unchanged.
- **Endpoint-included link** — a concept link whose source AND target memories
  are both part of the same copy selection.
- **Per-tenant dreaming** — a dreaming run whose every step is confined to one
  tenant's rows.
- **Global dreaming run** — a dreaming invocation by a global-scope caller that
  iterates every tenant and dreams each independently.

---

## Requirements

### Requirement 1 — Copy is global-scope only

**User story:** As an operator with a global-scope agent, I want to copy data
between tenants, while named-tenant agents cannot, so cross-tenant movement is a
deliberate, privileged-by-scope action.

#### Acceptance Criteria
1. WHEN a global-scope caller invokes the copy operation THEN the system SHALL
   perform the copy.
2. WHEN a named-tenant-scope caller invokes the copy operation THEN the system
   SHALL reject it with a clear "requires global scope" error and SHALL make no
   changes.
3. The scope check SHALL reuse the `tenant-scoped-mcp` connection scope (global
   vs named); the copy tool SHALL NOT accept a per-call argument that bypasses it.

### Requirement 2 — Copy semantics (copy, not move)

**User story:** As an operator, I want copy to leave the source intact and
produce independent records in the destination, so I never risk the origin data.

#### Acceptance Criteria
1. WHEN a copy completes THEN every selected source record SHALL remain unchanged
   in the source tenant (same id, same `tenant_id`, same content and flags).
2. WHEN a memory is copied THEN a NEW record SHALL be created in the destination
   tenant with a new id and `tenant_id = destination`.
3. WHEN a memory is copied THEN the destination copy SHALL carry provenance in
   `metadata`: `copied_from_tenant = <source>` and `source_memory_id = <source id>`.
4. WHEN a memory is copied THEN the destination copy SHALL be indexed
   (embedding / FTS / trigram) so it is retrievable by a scoped search in the
   destination tenant.
5. WHEN the destination copy is created THEN its score/state fields SHALL start
   from a defined baseline (design §field mapping: reset feedback/retrieval
   counters and state flags; preserve `category`, `source`, `is_note`,
   `confidence`, validity window).
6. Indexing (Req 2.4) SHALL be whatever `add_memory` on the destination store
   produces: if the store was built with an embedder, the copy gets a vector; if
   not (e.g. the MCP server builds its store with no embedder), the copy is
   FTS/trigram-indexed only — exactly as any memory added through that store.
   "Indexed" means "indexed consistently with how this store indexes any write";
   the copy function never embeds directly and never copies raw source
   embeddings. A test asserts the copy is retrievable by the store's own search.
7. Selection SHALL only copy memories that are active and not archived: a
   `MemoryFilter()` whole-tenant selection matches active, non-archived rows, and
   explicit ids that resolve to an archived/inactive/superseded memory SHALL be
   counted as `memories_skipped_not_found` (a copy never resurrects an archived
   or superseded memory). This makes the reset of `is_archived`/`superseded_by`
   safe.
8. The filter list path SHALL be bounded: `list_memories` is called with an
   explicit limit; if a whole-tenant copy would exceed it, the operation SHALL
   raise rather than silently truncate (a partial "whole-tenant" copy is an
   error, not a silent success).

### Requirement 3 — Selection

**User story:** As an operator, I want to choose what to copy, so I can move a
single note, a set of memories, or a whole category.

#### Acceptance Criteria
1. The copy operation SHALL accept a source tenant, a destination tenant, and a
   selection consisting of explicit memory ids and/or a `MemoryFilter`. When both
   are given the selection is their union de-duplicated by source id.
2. WHEN neither `memory_ids` nor `filter` is provided THEN the operation SHALL be
   rejected with a clear error (empty selection). A whole-tenant copy requires an
   explicit `MemoryFilter()`.
3. WHEN a `MemoryFilter` carries its own `tenant_id` that differs from
   `source_tenant` THEN the operation SHALL be rejected with a clear error (the
   filter SHALL NOT redirect the source); internally the source read is confined
   to `source_tenant` regardless of the filter's `tenant_id`.
4. WHEN explicit ids are given THEN only source-tenant memories with those ids
   SHALL be eligible; ids absent from the source tenant SHALL be counted as
   `memories_skipped_not_found`, never pulled from another tenant.
5. WHEN a filter is given THEN only source-tenant memories matching it SHALL be
   eligible.
6. WHEN `source_tenant == dest_tenant` THEN the operation SHALL be rejected with
   a clear error (no-op copy).
7. WHEN `dest_tenant` does not exist THEN the operation SHALL be rejected with
   `TenantNotFoundError` (no implicit creation). WHEN `dest_tenant` is inactive
   THEN it SHALL be rejected with `TenantInactiveError` (copy is a write). WHEN
   `source_tenant` does not exist THEN the operation SHALL be rejected with
   `TenantNotFoundError` (not an all-zero report, so a typo is caught).

### Requirement 4 — Notes and links travel with their memory

**User story:** As an operator, I want a copied memory to bring its notes and the
links among copied memories, so the copied subset is coherent in the destination.

#### Acceptance Criteria
1. WHEN a memory is copied THEN its attached notes (ANNOTATES-linked note records
   in the source tenant) SHALL also be copied into the destination tenant with
   new ids and provenance, and re-anchored to the destination copy.
2. WHEN both endpoints of a source concept link are included in the same copy
   selection THEN an equivalent link SHALL be created in the destination between
   the two destination copies (new link id, `tenant_id = destination`,
   preserving `link_type`, `strength`, `confidence`, `entity`).
3. WHEN only one endpoint of a source link is included THEN that link SHALL NOT
   be copied (no dangling or cross-tenant link).
4. The destination SHALL never contain a concept link whose endpoints are in
   different tenants (consistent with the `multi-tenancy` cross-tenant-link ban).
5. `memory_summaries` SHALL NOT be copied.

### Requirement 5 — Duplicate handling

**User story:** As an operator, I want copy to avoid creating exact duplicates in
the destination by default, so repeated copies are safe.

#### Acceptance Criteria
1. WHEN a selected memory's exact content already exists in the destination
   tenant (per `memory_exists_with_content` scoped to the destination) THEN the
   copy SHALL skip it by default and count it as skipped.
2. WHEN `force = true` is supplied THEN the duplicate SHALL be copied anyway.
3. WHEN the operation completes THEN it SHALL return a report: counts of
   memories copied, memories skipped (duplicate / not-found), notes copied, and
   links copied.
4. Re-running the same copy with defaults SHALL be effectively idempotent for
   content (no new duplicate memories created on the second run).

### Requirement 6 — Dreaming is tenant-scoped

**User story:** As an operator, I want dreaming to consolidate within one tenant
at a time, so tenants never get linked, merged, or contradicted against each
other.

#### Acceptance Criteria
1. The `DreamingEngine` SHALL accept `tenant_id: str | None = None`, and every
   step SHALL pass it to the `multi-tenancy` tenant-aware storage helpers, so
   steps operate only on that tenant's rows (or all rows when `None`).
2. WHEN dreaming runs under tenant `T` THEN it SHALL NOT create a link between a
   `T` memory and a non-`T` memory, SHALL NOT resolve a `T` memory against a
   non-`T` memory, and SHALL NOT read/write another tenant's summaries. Records
   the engine writes under scope `T` (links, summaries, resolution/archival
   updates) SHALL be stamped / confined to `tenant_id = T`: `add_link` and
   `upsert_summary` receive `T`; updates target only `T` rows.
3. WHEN a named-scope caller runs dreaming THEN it SHALL dream only its tenant
   (`DreamingEngine(tenant_id=T)`).
4. WHEN a global-scope caller runs dreaming across a multi-tenant DB THEN the
   system SHALL call `dream_all_tenants`, which runs one
   `DreamingEngine(tenant_id=t.id)` per ACTIVE tenant and returns a
   `DreamAllReport` holding `per_tenant: dict[str, DreamReport]` (one entry per
   active tenant). Inactive tenants SHALL be skipped (dreaming writes, and an
   inactive tenant is read-only); a per-tenant pass that raises SHALL be recorded
   and the run SHALL continue to the next tenant. `DreamAllReport` is the single
   public aggregate type (no bare `dict` is returned).
5. Dreaming SHALL remain idempotent per tenant: a second scoped run SHALL produce
   0 new links/summaries, preserving the `multi-tenancy` per-tenant uniqueness.
6. WHEN only the `global` tenant exists (today's state) THEN a global dreaming
   run SHALL be behaviourally identical to today in its MUTATIONS: exactly one
   tenant-scoped pass over `global` producing the same links/summaries/
   resolutions/archival as today's un-tenanted `run_full`/`run_light`.
   The RETURN shape is decided PURELY BY SCOPE (no dependence on tenant counts,
   eliminating the single-vs-aggregate ambiguity):
   - named scope `T` → the tool/command returns a bare `DreamReport` JSON (one
     `DreamingEngine(tenant_id=T)` run).
   - global scope → the tool/command ALWAYS returns `DreamAllReport` JSON (the
     `dream_all_tenants` aggregate), even when `global` is the only tenant. So a
     one-tenant DB returns `{"per_tenant": {"global": {...}}, "skipped_inactive":
     [], "failed": {}}`. `.single` is an internal convenience ONLY (e.g. tests
     asserting the sole report equals today); it is never the tool's return rule.
   This is the one output rule; it never keys on `len(list_tenants())` or
   `len(per_tenant)`.

### Requirement 7 — Transport surface

**User story:** As an operator, I want to invoke copy and tenant-scoped dreaming
through MCP and the CLI, consistent with the existing surface.

#### Acceptance Criteria
1. An MCP tool `tenant_copy(source_tenant: str, dest_tenant: str, memory_ids:
   list[str] | None = None, filter: dict | None = None, all_active: bool = False,
   force: bool = False)` SHALL expose the copy operation and SHALL be available
   ONLY when the process scope (`_scope_tenant`) is `global`; a named scope SHALL
   raise `ScopeRequiredError` and make no changes. The MCP `filter` is a JSON
   dict parsed into a `MemoryFilter`; `all_active: true` requests a whole-tenant
   copy (equivalent to an empty `MemoryFilter()` matching all active, non-archived
   memories) so the ambiguous "empty `{}`" case is avoided. `source_tenant`/
   `dest_tenant` name the copy endpoints and do NOT change the process scope. This
   spec SHALL update the `tenant-scoped-mcp` Req 4b tool inventory/allow-list so
   `tenant_copy` is a known tool whose only tenant-named parameters are the
   copy endpoints (not a scope selector), keeping the inventory test green.
2. A CLI command `tenant copy <source> <dest> [--id ID]... [--category C]
   [--note] [--entity E] [--all-active] [--force]` SHALL expose the copy. `--id`
   is repeatable; filter flags combine with ids as a UNION; `--all-active`
   requests the whole-tenant copy. It is a global/admin command: allowed only
   when the CLI's resolved `--tenant` is absent/`global`; under a named `--tenant`
   it SHALL exit non-zero with `ScopeRequiredError`. No selectors AND no
   `--all-active` → the empty-selection rejection.
3. The `memory_dream` MCP tool and CLI `dream` command SHALL honour the caller's
   scope using this spec's wiring: named → `DreamingEngine(tenant_id=T)`; global
   → `dream_all_tenants`. This REPLACES the `tenant-scoped-mcp` interim wiring AND
   updates its tests/inventory accordingly (so no test still asserts the old
   refusal/behaviour).
4. All copy/dream tools SHALL go through core functions and return JSON-safe
   reports: `CopyReport.model_dump(mode="json")`; for dream, per the one output
   rule in Req 6.6 — `DreamReport` JSON for named and single-`global`, and
   `DreamAllReport.model_dump(mode="json")` for multi-tenant global. The bare
   `dict` is never returned; `DreamAllReport` is the only aggregate type.

### Requirement 8 — Tests and gate

**User story:** As a maintainer, I want the feature verified and the project
gates green.

#### Acceptance Criteria
1. Tests SHALL cover: global-only copy enforcement; copy leaves source intact;
   new ids + provenance; notes and endpoint-included links travel; single-endpoint
   links do not; summaries excluded; duplicate skip + `force`; same-tenant and
   missing-destination rejections; copy report counts.
2. Tests SHALL cover: tenant-scoped dreaming confinement (no cross-tenant links/
   resolution/summaries), per-tenant idempotency, global run iterates all
   tenants, and single-`global`-tenant parity with today.
3. The full gate SHALL pass: `uv run pytest` (coverage ≥ 80%),
   `uv run mypy packages/`, `uv run ruff check packages/` all exit 0.
