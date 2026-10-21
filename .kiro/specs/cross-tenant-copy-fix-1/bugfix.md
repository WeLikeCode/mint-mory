# Bugfix Requirements Document

## Bug Analysis

### Current Behavior (Defect)

1.1 Decided by human in Q-005: confirmed against the code: _select (transfer.py:72-109) has no R3.2 check on the remaining filter/all_active rows; only len(plan) is checked at :247 after duplicate skipping (R3.4). Add the R3.2 check in _select after superseded rows are dropped. WHEN all_active or a filter selects more than COPY_MAX non-superseded rows in the source tenant, even if some of them are duplicates in the destination THEN copy_between_tenants raises CopySelectionError("selection exceeds {COPY_MAX} memories") before any write and the destination is unchanged; Q-004: R3.2 is not implemented. _select (packages/core/src/mintmory/core/transfer.py:72-109) never compares the remaining filter/all_active rows with COPY_MAX; the only cap check is len(plan) at :247, after duplicates are skipped, which is R3.4's rule (records to copy). test_skipped_duplicates_do_not_count_toward_copy_max (packages/core/tests/test_transfer_selection.py) encodes the wrong rule: all_active with COPY_MAX=2 over 3 active rows must raise under R3.2; keep R3.4's point there with a selection that passes R3.2 (rows <= COPY_MAX) and a duplicate skipped. WHEN all_active or a filter selects more than COPY_MAX non-superseded rows in the source tenant, even if some of them are duplicates in the destination THEN copy_between_tenants raises CopySelectionError("selection exceeds {COPY_MAX} memories") before any write and the destination is unchanged. _select never compares the remaining filter or all_active rows against COPY_M... (R3.2 cap on filter/all_active rows is not enforced before duplicate skipping; F-37e92031)

### Expected Behavior (Correct)

2.1 `filter`: `list_memories(filter.model_copy(update={"active_only": True}), tenant_id=source_tenant)` (no limit); `all_active`: the same with `MemoryFilter(exclude_stale=False)` (every active, non-archived memory, stale ones included). Rows with `superseded_by` set are then dropped (a superseded row is not always archived: `update_memory(id, superseded_by=X)` leaves it active), and only then, more than `COPY_MAX` remaining rows → `CopySelectionError(f"selection exceeds {COPY_MAX} memories")`. Dropped rows are counted nowhere. (parent Req 3.2, C-3affbf7d)
2.2 WHEN all_active or a filter selects more than COPY_MAX non-superseded rows in the source tenant, even if some of them are duplicates in the destination THEN copy_between_tenants raises CopySelectionError("selection exceeds {COPY_MAX} memories") before any write and the destination is unchanged

### Unchanged Behavior (Regression Prevention)

The system SHALL CONTINUE TO satisfy every other acceptance criterion of cross-tenant-copy.
