# Design — Multi-Tenancy 7/10: cross-tenant copy

## Grounding (base branch + units 1–6)

- Notes are `MemoryRecord(is_note=True)` linked to the memory they annotate by a
  `ConceptLink(link_type=ANNOTATES, source_memory_id=<note>,
  target_memory_id=<memory>)`; `notes.create_note` also stores
  `metadata["anchor_memory_id"]`. Notes never annotate notes
  (`_resolve_anchor` excludes notes as candidates), so one expansion level is
  complete.
- `MemoryFilter` fields: `category`, `source`, `verified_only`, `active_only`
  (default True), `exclude_stale` (default True), `entity`, `min_usefulness`,
  `max_staleness`; it has no tenant and no `is_note` field.
- After `multi-tenancy-writes`, every public write joins an open
  `store.transaction()`; after `multi-tenancy-reads`, `list_memories`,
  `memory_exists_with_content`, `get_annotating_notes` and `get_links` take a
  tenant.

## Algorithm

```python
def copy_between_tenants(store, *, source_tenant, dest_tenant, memory_ids=None,
                         filter=None, all_active=False, force=False) -> CopyReport:
    _validate(...)                                  # R2, raises before any read of rows
    report = CopyReport(source_tenant=source_tenant, dest_tenant=dest_tenant)
    with store.transaction():
        selected = _select(store, ...)              # R3.1–R3.3, counts not-found
        plan: list[MemoryRecord] = []               # source records to copy, in order
        seen: set[str] = set()
        planned_contents: set[str] = set()
        def consider(rec: MemoryRecord) -> bool:     # True when rec will be copied
            if rec.id in seen: return False
            seen.add(rec.id)
            if not force and (rec.content in planned_contents or
                              store.memory_exists_with_content(rec.content, tenant_id=dest_tenant)):
                _count_duplicate(report, rec); return False
            planned_contents.add(rec.content)
            report.id_map[rec.id] = str(uuid.uuid4()); plan.append(rec); return True
        for rec in selected:
            consider(rec)
        for rec in list(plan):                      # one level of attached notes
            for note in store.get_annotating_notes(rec.id, COPY_MAX, tenant_id=source_tenant):
                if note.is_active and note.superseded_by is None:
                    consider(note)
        if len(plan) > COPY_MAX: raise CopySelectionError(...)
        for rec in plan:
            store.add_memory(record=_copy_record(rec, report.id_map, source_tenant, dest_tenant))
            _count_copied(report, rec)
        done: set[str] = set()
        for src_id in report.id_map:
            for link in store.get_links(src_id, tenant_id=source_tenant):
                if link.id in done: continue
                done.add(link.id)
                if link.source_memory_id in report.id_map and link.target_memory_id in report.id_map:
                    store.add_link(_copy_link(link, report.id_map, dest_tenant))
                    report.links_copied += 1
    return report
```

New ids are assigned while planning, before any write, which is what lets
`anchor_memory_id` and link endpoints be rewritten regardless of order (R5.1,
R5.4). The `for rec in list(plan)` loop iterates a snapshot so notes appended
during expansion are not expanded again (one level).

## Why the whole operation is in one transaction

`store.transaction()` (re-entrant, `multi-tenancy-writes`) makes every
`add_memory` / `add_link` inside the block join one SQLite transaction; FTS5,
trigram and embedding writes are part of the same database and roll back with
the rows. Holding the selection reads inside the block also holds the
transaction lock, so in one process no other writer interleaves with the copy.

## Transports

- MCP (`server.py`): the scope check is the first statement; then
  `MemoryFilter.model_validate(filter) if filter is not None else None`; then
  `copy_between_tenants(_get_store(), …)`. Errors propagate as tool errors.
- CLI (`main.py`): `@tenant_app.command("copy")`; refuses a named `--tenant` with
  `ScopeRequiredError("tenant copy", T)` through `_fail`; builds the filter only
  from `--category` (`_parse_category`) and `--entity`; prints a table with one
  row per counter or `report.model_dump_json()` with `--json`.

## Tests

`packages/core/tests/test_transfer.py` (R9.1–R9.9),
`packages/mcp/tests/test_tenancy_copy_mcp.py` and
`packages/cli/tests/test_cli_tenant_copy.py` (R9.10),
`tests/integration/test_tenancy_copy.py` (R9.11). The seed of R9.1 is built with
`add_memory(record=MemoryRecord(id=…, tenant_id="acme", …))` and `add_link`.

## Risks

- A link created to a pre-existing destination row → impossible by
  construction: only ids in `id_map` (records written by this copy) are used.
- An oversized selection holding the lock for long → `COPY_MAX`.
