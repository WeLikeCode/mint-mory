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

- [ ] 1. `CopyReport` type (`types.py`)
  - Add the `CopyReport` Pydantic model (source/dest tenant + the count fields).
    Non-table type (no schema/CHECK surface).
  - Unit test: defaults and round-trip `model_dump(mode="json")`.
  - _Requirements: 5.3_

- [ ] 2. Core copy function — memories only (`core/transfer.py`)
  - Implement `copy_between_tenants(...)` validation (reject `source == dest`;
    reject missing dest tenant) and the memory copy loop: selection resolution
    (ids and/or filter, source-tenant only), new id + `tenant_id = dest`,
    provenance in `metadata`, field reset per design, re-index via `add_memory`.
  - Duplicate handling: skip exact-content dupes in dest by default
    (`memory_exists_with_content` scoped to dest); `force` creates anyway;
    populate the report counts.
  - Tests: source untouched; new ids + provenance; searchable under dest scope;
    dup skip + force; same-tenant/missing-dest rejections; not-found ids counted;
    content-idempotent on re-run.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.2, 5.4_

- [ ] 3. Core copy function — notes and links (`core/transfer.py`)
  - Copy each copied memory's ANNOTATES notes (new id + provenance, re-anchored
    to the dest copy). Build the `src_id -> new_id` map, then copy only
    endpoint-included concept links (new id, `tenant_id = dest`, preserving
    link_type/strength/confidence/entity); skip single-endpoint links; never
    copy summaries.
  - Tests: notes travel + re-anchor; both-endpoint link copied; one-endpoint link
    skipped; no cross-tenant link exists; summaries excluded; report counts.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.3_

- [ ] 4. Tenant-scoped `DreamingEngine` (`dreaming.py`)
  - Add `tenant_id: str | None = None` to `__init__`; forward it from every step
    method (`detect_anomalies`, `create_concept_links`, `generate_summaries`,
    `resolve_contradictions`, `archive_stale`, `rehabilitate`) to the
    tenant-aware storage helpers. `None` = today's behaviour.
  - Tests: scoped engine touches only its tenant (no cross-tenant links/
    resolution/summaries); per-tenant idempotency (2nd run → 0 new); `None`
    engine parity with today.
  - _Requirements: 6.1, 6.2, 6.5, 6.6_

- [ ] 5. Global dreaming orchestrator (`dreaming.py`)
  - Implement `dream_all_tenants(store, *, intensity, **engine_kwargs) ->
    dict[str, DreamReport]`: one `DreamingEngine(tenant_id=t.id)` per tenant,
    aggregated reports; no engine shared across tenants.
  - Tests: iterates every tenant; single-`global` parity with a single
    `run_full`/`run_light`.
  - _Requirements: 6.4, 6.6_

- [ ] 6. MCP transport: `tenant_copy` + scope-aware `memory_dream`
  - Add `tenant_copy(source_tenant, dest_tenant, memory_ids=None, filter=None,
    force=False)` with a global-scope-only guard (reject when `_scope_tenant !=
    TENANT_GLOBAL`), delegating to `copy_between_tenants`; return JSON-safe
    `CopyReport`.
  - Update `memory_dream`: named scope → single `DreamingEngine(tenant_id=T)`;
    global scope → `dream_all_tenants`, returning aggregate reports.
  - Tests: named-scope copy rejected (no writes); global copy works;
    `memory_dream` scoping for named vs global.
  - _Requirements: 1.1, 1.2, 1.3, 6.3, 6.4, 7.1, 7.3, 7.4_

- [ ] 7. CLI transport: `tenant copy` + scope-aware `dream`
  - Add `tenant copy <source> <dest> [--id ... | --category ... | --note]
    [--force]` as a global/admin command → `copy_between_tenants`.
  - Update the `dream` command to honour the resolved `--tenant`: named → scoped
    engine; global/absent → `dream_all_tenants`.
  - Tests: copy command happy path + rejections; dream command scoping.
  - _Requirements: 7.2, 7.3, 7.4_

- [ ] 8. Integration + full gate (`tests/integration/`)
  - Global-scope end-to-end: copy a note + its linked memories across tenants,
    then run a scoped dream in the destination; assert isolation throughout and
    that the source tenant is unchanged.
  - Run the full gate: `uv run pytest` (coverage ≥ 80%), `uv run mypy
    packages/`, `uv run ruff check packages/` — all exit 0.
  - _Requirements: 8.1, 8.2, 8.3_
