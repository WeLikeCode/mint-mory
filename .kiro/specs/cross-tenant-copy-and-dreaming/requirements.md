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
- **What travels.** Selected memories + their attached notes. A concept link is
  copied only when both of its endpoints are included in the same copy. Derived
  `memory_summaries` are NOT copied — dreaming regenerates them in the
  destination.
- **New ids + provenance.** Copies get new ids in the destination; provenance is
  stamped in `metadata` (`copied_from_tenant`, `source_memory_id`). Embedding /
  FTS are (re)built so copies are searchable in the destination.
- **Duplicates.** Exact-content duplicates already present in the destination are
  skipped by default (using the existing `memory_exists_with_content` check) and
  counted in the report; a `force` option creates them anyway.
- **Transports.** Exposed as an MCP tool available only to global-scope agents,
  plus a CLI command. REST API is out of scope for this ticket.
- **Dreaming scope.** Dreaming accepts a tenant scope. Named-scope → that tenant
  only. Global-scope → every tenant, processed independently. The hard rule in
  all cases: no cross-tenant linking, contradiction resolution, or summary
  sharing.

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
   from a defined baseline (design specifies: reset feedback/retrieval counters;
   preserve `category`, `source`, `is_note`, `confidence`, validity window).

### Requirement 3 — Selection

**User story:** As an operator, I want to choose what to copy, so I can move a
single note, a set of memories, or a whole category.

#### Acceptance Criteria
1. The copy operation SHALL accept a source tenant, a destination tenant, and a
   selection consisting of explicit memory ids and/or a `MemoryFilter`
   (category, `is_note`, entity, active/stale flags).
2. WHEN explicit ids are given THEN only memories in the source tenant with those
   ids SHALL be eligible (ids absent from the source tenant SHALL be reported as
   skipped/not-found, never silently pulled from another tenant).
3. WHEN a filter is given THEN only memories in the source tenant matching the
   filter SHALL be eligible.
4. WHEN the source and destination tenants are the same THEN the operation SHALL
   be rejected with a clear error (no-op copy).
5. WHEN the destination tenant does not exist THEN the operation SHALL be rejected
   (no implicit tenant creation), consistent with the `multi-tenancy` FK rule.

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
1. The `DreamingEngine` SHALL accept a tenant scope, and every step (anomaly
   detection, concept linking, summary generation, contradiction resolution,
   archival, rehabilitation) SHALL operate only on rows of that tenant.
2. WHEN dreaming runs under tenant `T` THEN it SHALL NOT create a link between a
   `T` memory and a non-`T` memory, SHALL NOT resolve a `T` memory against a
   non-`T` memory, and SHALL NOT read/write another tenant's summaries.
3. WHEN a named-scope MCP/CLI caller runs dreaming THEN it SHALL dream only its
   own tenant.
4. WHEN a global-scope caller runs dreaming THEN the system SHALL process every
   tenant independently (one tenant-scoped pass per tenant) and SHALL aggregate
   the per-tenant `DreamReport`s into the returned result.
5. Dreaming SHALL remain idempotent per tenant: a second scoped run on the same
   tenant SHALL produce the same result (0 new links/summaries), preserving the
   `multi-tenancy` per-tenant uniqueness constraints.
6. WHEN only the `global` tenant exists (today's state) THEN a global dreaming
   run SHALL behave exactly as today.

### Requirement 7 — Transport surface

**User story:** As an operator, I want to invoke copy and tenant-scoped dreaming
through MCP and the CLI, consistent with the existing surface.

#### Acceptance Criteria
1. An MCP tool (e.g. `tenant_copy`) SHALL expose the copy operation and SHALL be
   available ONLY to global-scope agents (named scope → clear error).
2. A CLI command SHALL expose the copy operation as a global/admin command
   (source, destination, selection, `--force`).
3. The existing `memory_dream` MCP tool and the CLI `dream` command SHALL honour
   the caller's tenant scope (named → own tenant; global → all tenants,
   independently).
4. All copy/dream tools SHALL go through core functions (no domain logic in the
   transport layer) and return JSON-safe reports.

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
