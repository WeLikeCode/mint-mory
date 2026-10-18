# Tasks — Cross-Tenant Copy & Per-Tenant Dreaming

> **Depends on:** the `multi-tenancy` spec (`.kiro/specs/multi-tenancy/`) and the
> `tenant-scoped-mcp` spec (`.kiro/specs/tenant-scoped-mcp/`). Both must be
> implemented first — this spec assumes the `tenant_id` data model + storage
> scoping (incl. the tenant arg on dreaming helper queries and per-tenant UNIQUE
> constraints) and the connection-level `global`-vs-named scope
> (`_scope_tenant` / `_effective_tenant()`) already exist. Do not start these
> tasks until both specs are complete.

Each task is TDD: write the failing test first, confirm it fails for the right
reason, implement, then run the gate. Per-task gate (from `tech.md`): the
affected package's tests exit 0, `uv run mypy packages/<pkg>/` exits 0,
`uv run ruff check packages/<pkg>/` exits 0. Full gate before PR:
`uv run pytest` (coverage ≥ 80%), `uv run mypy packages/`,
`uv run ruff check packages/`.

---

- [ ] 1. `CopyReport`, `DreamAllReport` types (`types.py`)
  - Add `CopyReport` (source/dest + count fields incl. `notes_skipped_duplicate`)
    and `DreamAllReport` (`per_tenant: dict[str, DreamReport]`,
    `skipped_inactive`, `failed`, `.single` accessor that raises `ValueError`
    when `len(per_tenant) != 1`). `ScopeRequiredError` is already defined by
    `multi-tenancy` — import it, do not redefine.
  - Unit tests: defaults + round-trip `model_dump(mode="json")`; `.single`
    returns the sole report and raises when 0 or ≥2 entries.
  - _Requirements: 5.3, 6.4, 6.6_

- [ ] 2. Core copy function — memories, atomic (`core/transfer.py`)
  - Implement `copy_between_tenants(...)` inside one storage transaction.
    Validation: empty selection (no ids, no filter) rejected; `filter.tenant_id`
    ≠ source rejected; `source == dest` rejected; missing source / missing dest →
    `TenantNotFoundError`; inactive dest → `TenantInactiveError`.
  - Memory copy loop using committed reads (`get_memory(id,
    tenant_id=source)` for ids; confined list for filter; union de-duped via
    `copy_map`): exact field mapping (copy vs reset per design), provenance in
    `metadata`, re-index via `add_memory`. Duplicate skip by default
    (`memory_exists_with_content(content, tenant_id=dest)`); `force` overrides;
    populate counts. Roll back entirely on any error.
  - Tests: source untouched; field mapping; searchable under dest scope; dup
    skip + force; all rejection cases; not-found ids counted; content-idempotent
    re-run; atomicity (mid-copy failure → zero dest rows).
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 5.1, 5.2, 5.4_

- [ ] 3. Core copy function — notes and links (`core/transfer.py`)
  - Within the same transaction: copy each copied memory's ANNOTATES notes (new
    id + provenance, re-anchored), copying a record that is both selected and an
    annotation exactly once (via `copy_map`). Then copy only endpoint-included
    links (both ends in `copy_map`; new id, `tenant_id = dest`, preserving
    link_type/strength/confidence/entity); skip single-endpoint links; never copy
    summaries.
  - Tests: notes travel + re-anchor; both-endpoint link copied; one-endpoint
    skipped; no cross-tenant link; double-selected note copied once; summaries
    excluded; report counts.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.3_

- [ ] 4. Tenant-scoped `DreamingEngine` (`dreaming.py`)
  - Add `tenant_id: str | None = None` to `__init__`; forward it from every step
    to the tenant-aware helpers for READS, and stamp/confine WRITES: `add_link`
    and `upsert_summary` receive the tenant; resolution/archival/rehabilitation
    updates target only tenant rows. `None` = today (writes stamp `"global"`).
  - Tests: scoped engine touches only its tenant (no cross-tenant links/
    resolution/summaries) and stamps writes with the tenant; per-tenant
    idempotency (2nd run → 0 new); `None` engine parity with today.
  - _Requirements: 6.1, 6.2, 6.5, 6.6_

- [ ] 5. Global dreaming orchestrator (`dreaming.py`)
  - Implement `dream_all_tenants(store, *, intensity, **engine_kwargs) ->
    DreamAllReport`: one `DreamingEngine(tenant_id=t.id)` per tenant; no engine
    shared across tenants.
  - Tests: iterates every tenant; single-`global` → `.single` equals today's
    `run_full`/`run_light` mutations and report.
  - _Requirements: 6.4, 6.6_

- [ ] 6. MCP transport: `tenant_copy` + final `memory_dream` wiring
  - Add `tenant_copy(source_tenant, dest_tenant, memory_ids=None, filter=None,
    force=False)` (JSON `filter` → `MemoryFilter`) with a global-scope-only guard
    (`ScopeRequiredError` when `_scope_tenant != TENANT_GLOBAL`), delegating to
    `copy_between_tenants`; return JSON-safe `CopyReport`. The source/dest args
    never change `_scope_tenant`.
  - REWIRE `memory_dream` (replacing the interim `tenant-scoped-mcp` wiring):
    named → single `DreamingEngine(tenant_id=T)` → `DreamReport`; global →
    `dream_all_tenants` → `DreamAllReport`. Assert single-`global` serialises
    like today via `.single`.
  - Tests: named-scope copy → `ScopeRequiredError`, no writes; global copy works;
    `memory_dream` scoping for named vs global.
  - _Requirements: 1.1, 1.2, 1.3, 6.3, 6.4, 7.1, 7.3, 7.4_

- [ ] 7. CLI transport: `tenant copy` + scope-aware `dream`
  - Add `tenant copy <source> <dest> [--id ... | --category ... | --note]
    [--force]`, allowed only when `--tenant` is absent/`global` (else
    `ScopeRequiredError`, non-zero exit) → `copy_between_tenants`.
  - Rewire `dream` to honour `--tenant`: named → scoped engine (one report);
    global/absent → `dream_all_tenants`.
  - Tests: copy happy path + scope rejection + bad-selection rejection; dream
    scoping.
  - _Requirements: 7.2, 7.3, 7.4_

- [ ] 8. Integration + full gate (`tests/integration/`)
  - Global-scope end-to-end: copy a note + its linked memories across tenants,
    then run a scoped dream in the destination; assert isolation throughout and
    that the source tenant is unchanged.
  - Run the full gate: `uv run pytest` (coverage ≥ 80%), `uv run mypy
    packages/`, `uv run ruff check packages/` — all exit 0.
  - _Requirements: 8.1, 8.2, 8.3_
