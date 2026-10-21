# Verification: kiro:multi-tenancy-postgres-writes: PASS (round 1)

traceability: 23/23 criteria covered by a discriminating test

- Base: `bd85b698f3eed08f755ae4261c627ca2ae93fb39`
- Head: `7694a4f1db53f898ad8aa7dccab13bb98f9d6929`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 3 call(s), judged in 2 parts, prompt sha256 `c14a5b51f2b3844ff370a925bdfab836a8c7dbda79086224c151c16165423319`
  - part 1: 5 file(s), 94322 characters, profile claude-judge, reply valid
  - part 2: 4 file(s), 38497 characters, profile claude-judge, reply retried
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 1, discarded 0; this round: retried
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $2.1579

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.0 | base merged: staging@bd85b698f3 as 7694a4f1db (1 commit) |
| 1 | integrity | ok | 269.6 | 10 sub-checks; scope: 14 changed file(s) |
| 2 | build | ok | 6.8 |  |
| 3 | tests | ok | 121.5 |  |
| 4 | traceability | ok | 0.2 | 23/23 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 2.1 | 17/23 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 82.3 | 3 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261021T1934Z-fb51/052-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261021T1934Z-fb51/053-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261021T1934Z-fb51/054-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261021T1934Z-fb51/055-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261021T1934Z-fb51/056-test.log |

## Files by part

- part 1: packages/core/tests/test_pg_tenancy.py (20392 characters)
- part 1: packages/core/tests/test_pg_tenancy_columns.py (4527 characters)
- part 1: packages/core/src/mintmory/core/storage_postgres.py (43649 characters)
- part 1: packages/core/tests/conformance/test_conformance_tenancy_writes.py (6653 characters)
- part 1: packages/core/tests/test_pg_tenancy_references_idwrites.py (19101 characters)
- part 2: packages/core/tests/test_pg_tenancy_writes.py (30008 characters)
- part 2: packages/core/tests/test_pg_tenancy_writes_gate.py (4627 characters)
- part 2: .kiro/specs/multi-tenancy-postgres-writes/tasks.md (2006 characters)
- part 2: packages/core/tests/test_transfer_links.py (1856 characters)

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 7 test file(s) compared with the base (+37 allowed, listed) |
| red-green freeze | ok | 3 task(s): red and green compared |
| test path freeze | ok | 3 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 6 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2464 of 2464 base tests pass on the unit's code with its 4 test and support files at the base (base: base worktree) |

## Pre-existing tests changed with an allowance (L4-VER-031)

- packages/core/tests/test_pg_tenancy.py::test_pg_add_link_tenancy changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_add_memory_tenancy changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_apply_feedback_tenancy changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_archive_memory_tenancy changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_create_session_tenancy changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_create_tenant_tenancy changed (task 2: unfrozen by Q-003; task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_tenant_tenancy changed (task 2: unfrozen by Q-003; task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_list_tenants_tenancy changed (task 2: unfrozen by Q-003; task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_manifest_delete_tenancy changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_manifest_upsert_tenancy changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_record_query_results_tenancy changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_set_tenant_active_tenancy changed (task 2: unfrozen by Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_supersede_memory_tenancy changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_transaction_tenancy changed (task 1: unfrozen by Q-001, Q-002)
- packages/core/tests/test_pg_tenancy.py::test_pg_update_memory_tenancy changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy.py::test_pg_upsert_summary_tenancy changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_add_link_conflict_target_is_per_tenant changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_add_link_insert_includes_tenant_id changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_add_memory_insert_includes_tenant_id changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_create_session_insert_includes_tenant_id changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_get_session_returns_the_stored_tenant changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_get_summary_looks_up_by_concept_and_tenant changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_get_summary_returns_the_stored_tenant changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_guards_stay_on_record_writes_and_keyed_methods_before_pool_access changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_manifest_delete_filters_by_path_and_tenant changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_manifest_get_looks_up_by_path_and_tenant changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_manifest_get_returns_the_stored_tenant changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_manifest_paths_filters_by_collection_and_tenant changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_manifest_upsert_conflict_target_is_per_tenant changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_manifest_upsert_insert_includes_tenant_id changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_record_query_results_insert_includes_tenant_id changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_row_to_link_returns_the_stored_tenant changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_row_to_memory_returns_the_stored_tenant changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_truncate_all_deletes_non_global_tenants_after_the_truncate changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_upsert_summary_conflict_target_is_per_tenant changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py::test_upsert_summary_insert_includes_tenant_id changed (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_transfer_links.py::test_postgres_copy_fails_closed_before_any_write changed (task 1: unfrozen by Q-001, Q-002)
- packages/core/tests/test_pg_tenancy.py kept at head for the run (task 1: unfrozen by Q-001, Q-002; task 2: unfrozen by Q-003; task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_pg_tenancy_columns.py kept at head for the run (task 3: unfrozen by Q-004, Q-005)
- packages/core/tests/test_transfer_links.py kept at head for the run (task 1: unfrozen by Q-001, Q-002)

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-f55a34a6 | Req 1.1 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_create_tenant_inserts_then_selects_and_returns_row (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::test_pg_create_tenant_returns_the_existing_row_on_conflict (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::... | packages.core.tests.test_pg_tenancy::test_pg_create_tenant_tenancy (no proof that it discriminates (no red, audit or generated record)) | 0.91 |
| C-c0d003ce | Req 1.2 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_get_tenant_selects_and_maps_the_row (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::test_pg_list_tenants_reads_every_row_ordered_by_id (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::test_pg_set_tenant_acti... | packages.core.tests.test_pg_tenancy::test_pg_get_tenant_tenancy (no proof that it discriminates (no red, audit or generated record)); packages.core.tests.test_pg_tenancy::test_pg_list_tenants_tenancy (no proof that it discriminates (no red, audit or generated record)); packages.core.tests.test_pg_te... | 0.95 |
| C-edb554ee | Req 1.3 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_set_tenant_active_cannot_deactivate_global (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::test_pg_set_tenant_active_updates_flag_and_returns_updated_row (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::test... | packages.core.tests.test_pg_tenancy::test_pg_set_tenant_active_tenancy (no proof that it discriminates (no red, audit or generated record)) | 0.77 |
| C-9e1dc670 | Req 2.1 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_assert_tenant_writable_selects_on_the_given_connection (passed, zero_value); packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[add_link] (passed, zero_value); packages.core.tests.test_pg_tenancy_writes... | - | - |
| C-4f87b6ae | Req 2.2 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[add_link] (passed, zero_value); packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[add_memory] (passed, zero_value); packages.core.tests.test_pg_tenancy_writ... | packages.core.tests.test_pg_tenancy_columns::test_guards_stay_on_record_writes_and_keyed_methods_before_pool_access (no proof that it discriminates (no red, audit or generated record)) | - |
| C-d09bf668 | Req 2.3 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_write_lookup_helpers_read_single_column_rows (passed, zero_value) | - | 0.66 |
| C-f0e033f2 | Req 2.4 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_tenant_deactivated_after_the_guard_still_writes (passed, zero_value) | - | 0.91 |
| C-ce6c1aac | Req 3.1 | covered | packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_add_link_missing_endpoint_keeps_the_foreign_key_error (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_add_link_rejects_cross_tenant_endpoints (passed, pre_satisfied); packages.core.tests.test_p... | - | - |
| C-f3e0c70c | Req 3.2 | covered | packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_apply_feedback_foreign_tenant_raises_key_error (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_apply_feedback_without_tenant_acts_by_id (passed, pre_satisfied); packages.core.tests.test_pg_tena... | - | 0.95 |
| C-f97c4a2c | Req 4.1 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_nested_transaction_joins_the_outer_block (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::test_pg_transaction_commits_two_writes_once (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::test_pg_transaction_no_lo... | - | 0.92 |
| C-fd67032b | Req 4.2 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_get_memory_inside_transaction_uses_the_bound_connection (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::test_pg_search_phases_inside_transaction_use_the_bound_connection (passed, red_assertion) | - | 0.89 |
| C-68061c64 | Req 4.3 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_search_phases_inside_transaction_use_the_bound_connection (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::test_pg_transaction_rolls_back_once_and_reraises (passed, red_assertion) | - | 0.88 |
| C-0940d0a8 | Req 4.4 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_add_memory_from_thread_gets_its_own_connection (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::test_pg_tx_conn_is_a_per_instance_context_var (passed, red_assertion) | - | 0.79 |
| C-ae2a0704 | Req 4.5 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_add_memory_from_thread_gets_its_own_connection (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::test_pg_get_memory_inside_transaction_uses_the_bound_connection (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes:... | - | 0.94 |
| C-15dbdabf | Req 5.1 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[add_link] (passed, zero_value); packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[add_memory] (passed, zero_value); packages.core.tests.test_pg_tenancy_writ... | - | - |
| C-8d3fb08f | Req 5.2 | covered | packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_add_link_rejects_cross_tenant_endpoints (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_add_link_requires_the_link_tenant_to_match_its_endpoints (passed, pre_satisfied); packages.core.tests.tes... | - | - |
| C-98cd17f1 | Req 5.3 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_bump_retrieval_only_updates_active_tenants (passed, zero_value) | - | 0.90 |
| C-be5b17eb | Req 5.4 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_create_tenant_inserts_then_selects_and_returns_row (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::test_pg_create_tenant_returns_the_existing_row_on_conflict (passed, red_assertion); packages.core.tests.test_pg_tenancy_writes::... | packages.core.tests.test_pg_tenancy::test_pg_create_tenant_tenancy (no proof that it discriminates (no red, audit or generated record)); packages.core.tests.test_pg_tenancy::test_pg_get_tenant_tenancy (no proof that it discriminates (no red, audit or generated record)); packages.core.tests.test_pg_t... | 0.87 |
| C-1b7a83e9 | Req 5.5 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_active_tenant_write_inserts_t1_and_commits_once[add_link-concept_links] (passed, zero_value); packages.core.tests.test_pg_tenancy_writes::test_pg_active_tenant_write_inserts_t1_and_commits_once[add_memory-memories] (passed, zero_value); packages.co... | packages.core.tests.test_pg_tenancy::test_pg_add_link_tenancy (no proof that it discriminates (no red, audit or generated record)); packages.core.tests.test_pg_tenancy::test_pg_add_memory_tenancy (no proof that it discriminates (no red, audit or generated record)); packages.core.tests.test_pg_tenanc... | - |
| C-d07310eb | Req 5.6 | covered | packages.core.tests.test_pg_tenancy_writes::test_pg_active_tenant_write_inserts_t1_and_commits_once[add_link-concept_links] (passed, zero_value); packages.core.tests.test_pg_tenancy_writes::test_pg_active_tenant_write_inserts_t1_and_commits_once[add_memory-memories] (passed, zero_value); packages.co... | - | 0.95 |
| C-3f98f2b5 | Req 5.7 | covered | packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_record_query_results_validates_the_batch_before_inserting (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_supersede_memory_concrete_tenant_requires_both_rows (passed, pre_satisfied); packages.c... | - | 0.76 |
| C-8b29b13f | Req 6.1 | covered | packages.core.tests.test_pg_tenancy_writes_gate::test_writes_gate_config_declares_required_commands_and_coverage_floor (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_writes_gate::test_writes_gate_lint_and_typecheck_commands_pass (passed, pre_satisfied); packages.core.tests.test_pg_tena... | - | 0.81 |
| C-9a8a10e6 | Req 7.1 | covered | packages.core.tests.conformance.test_conformance_tenancy_writes::test_archive_memory_in_another_tenant_raises_key_error[sqlite] (passed, pre_satisfied); packages.core.tests.conformance.test_conformance_tenancy_writes::test_cross_tenant_add_link_raises[sqlite] (passed, pre_satisfied); packages.core.t... | - | 0.67 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `.kiro/specs/multi-tenancy-postgres-writes/.l4/ledger/r-20261021T1803Z-808e.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres-writes/.l4/ledger/r-20261021T1832Z-8b02.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres-writes/.l4/ledger/r-20261021T1911Z-621f.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres-writes/.l4/ledger/r-20261021T1934Z-fb51.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres-writes/questions.md` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres-writes/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/core/src/mintmory/core/storage_postgres.py` | core | relevant | named in the spec |
| `packages/core/tests/conformance/test_conformance_tenancy_writes.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_tenancy.py` |  | relevant | named in the spec |
| `packages/core/tests/test_pg_tenancy_columns.py` |  | none | imports no module of the repository |
| `packages/core/tests/test_pg_tenancy_references_idwrites.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_tenancy_writes.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_tenancy_writes_gate.py` |  | relevant | new test file |
| `packages/core/tests/test_transfer_links.py` |  | none | imports no module of the repository |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

2545 of 2656 passed, 0 failed, 0 errored, 111 skipped.
81 of 81 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-f55a34a6 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c0d003ce | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-edb554ee | ok | 0.770 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9e1dc670 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-4f87b6ae | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-d09bf668 | ok | 0.660 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f0e033f2 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ce6c1aac | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-f3e0c70c | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f97c4a2c | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-fd67032b | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-68061c64 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0940d0a8 | ok | 0.790 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ae2a0704 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-15dbdabf | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-8d3fb08f | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-98cd17f1 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-be5b17eb | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1b7a83e9 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-d07310eb | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3f98f2b5 | ok | 0.760 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8b29b13f | ok | 0.810 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9a8a10e6 | ok | 0.670 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-f55a34a6 | Req 1.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-c0d003ce | Req 1.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-edb554ee | Req 1.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-9e1dc670 | Req 2.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-4f87b6ae | Req 2.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-d09bf668 | Req 2.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-f0e033f2 | Req 2.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-ce6c1aac | Req 3.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-f3e0c70c | Req 3.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-f97c4a2c | Req 4.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-fd67032b | Req 4.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-68061c64 | Req 4.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-0940d0a8 | Req 4.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-ae2a0704 | Req 4.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-15dbdabf | Req 5.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-8d3fb08f | Req 5.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-98cd17f1 | Req 5.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-be5b17eb | Req 5.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-1b7a83e9 | Req 5.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-d07310eb | Req 5.6 | pass | pass | the judge passed it and a discriminating test passes |
| C-3f98f2b5 | Req 5.7 | pass | pass | the judge passed it and a discriminating test passes |
| C-8b29b13f | Req 6.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-9a8a10e6 | Req 7.1 | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, deterministic] a test is ignored as evidence (criterion C-f55a34a6): packages.core.tests.test_pg_tenancy::test_pg_create_tenant_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-c0d003ce): packages.core.tests.test_pg_tenancy::test_pg_get_tenant_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-c0d003ce): packages.core.tests.test_pg_tenancy::test_pg_list_tenants_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-c0d003ce): packages.core.tests.test_pg_tenancy::test_pg_set_tenant_active_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-edb554ee): packages.core.tests.test_pg_tenancy::test_pg_set_tenant_active_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-4f87b6ae): packages.core.tests.test_pg_tenancy_columns::test_guards_stay_on_record_writes_and_keyed_methods_before_pool_access: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-be5b17eb): packages.core.tests.test_pg_tenancy::test_pg_create_tenant_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-be5b17eb): packages.core.tests.test_pg_tenancy::test_pg_get_tenant_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-be5b17eb): packages.core.tests.test_pg_tenancy::test_pg_list_tenants_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_add_link_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_add_memory_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_apply_feedback_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_archive_memory_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_create_session_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_create_tenant_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_get_tenant_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_list_tenants_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_manifest_delete_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_manifest_upsert_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_record_query_results_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_set_tenant_active_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_supersede_memory_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_transaction_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_update_memory_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, deterministic] a test is ignored as evidence (criterion C-1b7a83e9): packages.core.tests.test_pg_tenancy::test_pg_upsert_summary_tenancy: no proof that it discriminates (no red, audit or generated record)
- [minor, judge] Conformance test mutates fixture params via private pytest internals (criterion C-9a8a10e6): test_conformance_tenancy_writes.py defines pytest_generate_tests, which edits fixturedef.params (via _arg2fixturedefs) to drop the postgres leg. This depends on pytest internals and sidesteps the fixture's own skip. It works on SQLite in this run.
- [minor, judge] archive_memory on a missing id with no tenant is a silent no-op (spec gap) (criterion C-f3e0c70c): No criterion pins this. The code does nothing and raises nothing, and test_pg_archive_memory_without_tenant_acts_by_id asserts it.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.core.tests.conformance.test_conformance_tenancy_writes::test_archive_memory_in_another_tenant_raises_key_error[sqlite]` (task 5): passed
- `packages.core.tests.conformance.test_conformance_tenancy_writes::test_cross_tenant_add_link_raises[sqlite]` (task 5): passed
- `packages.core.tests.conformance.test_conformance_tenancy_writes::test_transaction_that_raises_leaves_no_memory_rows[sqlite]` (task 5): passed
- `packages.core.tests.conformance.test_conformance_tenancy_writes::test_write_to_inactive_tenant_raises_and_writes_nothing[sqlite]` (task 5): passed
- `packages.core.tests.conformance.test_conformance_tenancy_writes::test_write_to_missing_tenant_raises_and_writes_nothing[sqlite]` (task 5): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_add_link_missing_endpoint_keeps_the_foreign_key_error` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_add_link_rejects_cross_tenant_endpoints` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_add_link_requires_the_link_tenant_to_match_its_endpoints` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_add_memory_missing_superseded_by_keeps_the_foreign_key_error` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_add_memory_superseded_by_requires_the_same_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_apply_feedback_foreign_tenant_raises_key_error` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_apply_feedback_without_tenant_acts_by_id` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_archive_memory_foreign_tenant_raises_key_error` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_archive_memory_without_tenant_acts_by_id` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_record_query_results_global_session_may_reference_any_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_record_query_results_missing_session_keeps_the_foreign_key_error` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_record_query_results_rejects_a_cross_tenant_memory` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_record_query_results_rejects_a_foreign_result_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_record_query_results_validates_the_batch_before_inserting` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_supersede_memory_concrete_tenant_requires_both_rows` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_supersede_memory_missing_by_id_keeps_the_foreign_key_error` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_supersede_memory_rejects_a_cross_tenant_by_id` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_supersede_memory_without_tenant_acts_by_id` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_update_memory_keeps_tenant_id_immutable` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_update_memory_missing_superseded_by_keeps_the_foreign_key_error` (task 4): passed
- `packages.core.tests.test_pg_tenancy_references_idwrites::test_pg_update_memory_superseded_by_requires_the_same_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_active_tenant_write_inserts_t1_and_commits_once[add_link-concept_links]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_active_tenant_write_inserts_t1_and_commits_once[add_memory-memories]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_active_tenant_write_inserts_t1_and_commits_once[manifest_upsert-index_manifest]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_active_tenant_write_inserts_t1_and_commits_once[upsert_summary-memory_summaries]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_add_memory_from_thread_gets_its_own_connection` (task 1): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_assert_tenant_writable_selects_on_the_given_connection` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_bump_retrieval_only_updates_active_tenants` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_create_tenant_inserts_then_selects_and_returns_row` (task 2): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_create_tenant_returns_the_existing_row_on_conflict` (task 2): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_create_tenant_validates_the_id_before_any_sql` (task 2): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_get_memory_inside_transaction_uses_the_bound_connection` (task 1): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_get_tenant_selects_and_maps_the_row` (task 2): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[add_link]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[add_memory]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[apply_feedback]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[archive_memory]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[create_session]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[manifest_delete]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[manifest_upsert]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[mark_session_concluded]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[record_query_results]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[supersede_memory]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[update_memory]` (task 3): passed
- `packages.core.tests.test_pg_tenancy_writes::test_pg_guarded_write_inactive_tenant_writes_nothing[update_session_feedback]` (task 3): passed

## Guard events

- guard.test_tamper: packages/core/tests/test_pg_tenancy.py
