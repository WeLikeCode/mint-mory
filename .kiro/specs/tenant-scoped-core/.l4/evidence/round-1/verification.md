# Verification: kiro:tenant-scoped-core: NEEDS_HUMAN (round 1)

traceability: 32/32 criteria covered by a discriminating test

- Base: `47bb91111d99442cc9d5ab63a9396eae5c569a5d`
- Head: `02ab864e2a9d3ea00bd73d604c19be1c215bd669`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 2 call(s), judged in 2 parts, prompt sha256 `58467cbf34045a3c2e2b51595a3ca3e97fc2d55b2570a54c4cb7d8f60431e15e`
  - part 1: 13 file(s), 118390 characters, profile claude-judge, reply valid
  - part 2: 6 file(s), 22734 characters, profile claude-judge, reply valid
- Judge replies of claude-judge (this unit, all rounds): valid 2, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $1.3392

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.0 | base staging@47bb91111d contained |
| 1 | integrity | ok | 149.7 | 10 sub-checks (+3 unfrozen by human answers); scope: 24 changed file(s) |
| 2 | build | ok | 3.6 |  |
| 3 | tests | ok | 66.1 |  |
| 4 | traceability | ok | 0.1 | 32/32 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 7.6 | 31/32 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 59.1 | 2 call(s) |
| 10 | aggregation | ok | 0.0 | NEEDS_HUMAN |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261020T1032Z-59e4/028-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261020T1032Z-59e4/029-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261020T1032Z-59e4/030-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261020T1032Z-59e4/031-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261020T1032Z-59e4/032-test.log |

## Files by part

- part 1: packages/api/src/mintmory/api/app.py (4140 characters)
- part 1: packages/api/tests/test_tenancy_api_errors.py (5187 characters)
- part 1: packages/api/tests/test_tenancy_dreaming_api_transport.py (6618 characters)
- part 1: packages/core/src/mintmory/core/cochange.py (3157 characters)
- part 1: packages/core/tests/test_tenancy_core_full_gate.py (8044 characters)
- part 1: packages/core/tests/test_tenancy_core_functions.py (20732 characters)
- part 1: packages/core/src/mintmory/core/dreaming.py (18493 characters)
- part 1: packages/core/tests/test_tenancy_dreaming.py (18366 characters)
- part 1: packages/core/tests/test_tenancy_dreaming_entrypoints.py (18937 characters)
- part 1: packages/mcp/tests/test_tenancy_dreaming_mcp_transport.py (6633 characters)
- part 1: packages/core/src/mintmory/core/llm.py (1698 characters)
- part 1: packages/cli/src/mintmory/cli/main.py (2869 characters)
- part 1: packages/cli/tests/test_tenancy_core_create_paths.py (3516 characters)
- part 2: packages/cli/tests/test_tenancy_dreaming_cli_transport.py (5659 characters)
- part 2: packages/core/src/mintmory/core/notes.py (2923 characters)
- part 2: packages/mcp/src/mintmory/mcp/server.py (2765 characters)
- part 2: packages/core/src/mintmory/core/session.py (3253 characters)
- part 2: .kiro/specs/tenant-scoped-core/tasks.md (2606 characters)
- part 2: packages/core/src/mintmory/core/vision.py (5528 characters)

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 9 test file(s) compared with the base |
| red-green freeze | ok | 5 task(s): red and green compared (+3 unfrozen by human answers) |
| test path freeze | ok | 5 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 6 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2190 of 2190 base tests pass on the unit's code with its 6 test and support files at the base (base: base worktree) |

## Pre-existing tests changed with an allowance (L4-VER-031)

- packages/api/tests/test_tenancy_dreaming_api_transport.py kept at head for the run (task 3: unfrozen by Q-002, Q-003, Q-004)
- packages/cli/tests/test_tenancy_dreaming_cli_transport.py kept at head for the run (task 3: unfrozen by Q-002, Q-003, Q-004)
- packages/mcp/tests/test_tenancy_dreaming_mcp_transport.py kept at head for the run (task 3: unfrozen by Q-002, Q-003, Q-004)

## Tests unfrozen by human answers (allowed, L4-IMP-002)

- packages/api/tests/test_tenancy_dreaming_api_transport.py (task 3, unfrozen by Q-002, Q-003, Q-004 (human))
- packages/cli/tests/test_tenancy_dreaming_cli_transport.py (task 3, unfrozen by Q-002, Q-003, Q-004 (human))
- packages/mcp/tests/test_tenancy_dreaming_mcp_transport.py (task 3, unfrozen by Q-002, Q-003, Q-004 (human))

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-49f64902 | Req 1.1 | covered | packages.core.tests.test_tenancy_dreaming::test_engine_stores_its_tenant (passed, zero_value) | - | 0.94 |
| C-8b56effb | Req 1.2 | covered | packages.core.tests.test_tenancy_dreaming::test_engine_confines_every_read_and_write_to_its_tenant (passed, zero_value) | - | 0.87 |
| C-3b1be517 | Req 1.3 | covered | packages.core.tests.test_tenancy_dreaming::test_scenario_b_cross_tenant_contradiction_is_skipped (passed, zero_value) | - | 0.90 |
| C-180a8a6f | Req 1.4 | covered | packages.core.tests.test_tenancy_dreaming::test_summary_jobs_and_apply_summary_use_the_engine_tenant (passed, zero_value) | - | 0.92 |
| C-8bf5b256 | Req 1.5 | covered | packages.core.tests.test_tenancy_dreaming::test_legacy_engine_may_attempt_a_cross_tenant_link_and_add_link_refuses (passed, zero_value); packages.core.tests.test_tenancy_dreaming::test_legacy_engine_stores_none_and_stamps_global_writes (passed, zero_value) | - | 0.91 |
| C-86ecfcef | Req 1.6 | covered | packages.core.tests.test_tenancy_dreaming::test_build_conflict_resolver_lookups_are_tenant_scoped (passed, zero_value); packages.core.tests.test_tenancy_dreaming::test_build_dreaming_engine_passes_tenant_to_the_engine (passed, zero_value) | - | 0.93 |
| C-1db051ad | Req 1.7 | covered | packages.core.tests.test_tenancy_dreaming::test_scenario_a_linking_and_summaries_stay_inside_the_tenant (passed, zero_value) | - | 0.95 |
| C-cd24da0d | Req 1.8 | covered | packages.core.tests.test_tenancy_dreaming::test_scenario_b_cross_tenant_contradiction_is_skipped (passed, zero_value) | - | 0.90 |
| C-443639c5 | Req 2.1 | covered | packages.core.tests.test_tenancy_dreaming_entrypoints::test_dreaming_module_defines_the_per_tenant_entry_point_surface (passed, zero_value) | - | 0.90 |
| C-61979b79 | Req 2.2 | covered | packages.core.tests.test_tenancy_dreaming_entrypoints::test_dream_all_tenants_records_a_run_failure_and_continues (passed, zero_value); packages.core.tests.test_tenancy_dreaming_entrypoints::test_dream_all_tenants_runs_active_tenants_with_their_intensity (passed, zero_value) | - | 0.86 |
| C-6d7b9d0d | Req 2.3 | covered | packages.core.tests.test_tenancy_dreaming_entrypoints::test_total_sums_metrics_and_concatenates_anomalies_in_tenant_order (passed, zero_value) | - | 0.92 |
| C-bb56329e | Req 2.4 | covered | packages.core.tests.test_tenancy_dreaming_entrypoints::test_dream_failed_error_message_sorts_tenants_and_keeps_failed (passed, zero_value) | - | 0.92 |
| C-ac42fe75 | Req 2.5 | covered | packages.core.tests.test_tenancy_dreaming_entrypoints::test_run_dream_concrete_tenant_validates_before_running (passed, zero_value); packages.core.tests.test_tenancy_dreaming_entrypoints::test_run_dream_without_a_tenant_returns_the_total (passed, zero_value) | - | 0.64 |
| C-d95fbef7 | Req 2.6 | covered | packages.core.tests.test_tenancy_dreaming_entrypoints::test_one_tenant_run_dream_parity_with_the_legacy_engine (passed, zero_value) | - | 0.93 |
| C-dc6f014f | Req 2.7 | covered | packages.core.tests.test_tenancy_dreaming_entrypoints::test_dream_all_tenants_records_a_factory_failure_and_run_dream_raises (passed, zero_value); packages.core.tests.test_tenancy_dreaming_entrypoints::test_dream_all_tenants_runs_active_tenants_with_their_intensity (passed, zero_value) | - | 0.95 |
| C-7881686c | Req 3.1 | covered | packages.api.tests.test_tenancy_dreaming_api_transport::test_dream_runs_each_tenant_without_cross_tenant_links (passed, red_assertion); packages.cli.tests.test_tenancy_dreaming_cli_transport::test_dream_runs_each_tenant_without_cross_tenant_links (passed, red_assertion); packages.mcp.tests.test_tena... | - | 0.77 |
| C-d9c39ea3 | Req 3.2 | covered | packages.api.tests.test_tenancy_dreaming_api_transport::test_dream_runs_each_tenant_without_cross_tenant_links (passed, red_assertion); packages.cli.tests.test_tenancy_dreaming_cli_transport::test_dream_runs_each_tenant_without_cross_tenant_links (passed, red_assertion); packages.mcp.tests.test_tena... | - | 0.78 |
| C-63860dbc | Req 3.3 | covered | packages.api.tests.test_tenancy_dreaming_api_transport::test_dream_failure_returns_500_detail (passed, red_assertion); packages.cli.tests.test_tenancy_dreaming_cli_transport::test_dream_failure_reports_error_on_stderr (passed, red_assertion); packages.mcp.tests.test_tenancy_dreaming_mcp_transport::t... | - | 0.93 |
| C-a0213e6c | Req 4.1 | covered | packages.api.tests.test_tenancy_dreaming_api_transport::test_summary_routes_stay_on_the_global_tenant (passed, red_assertion); packages.cli.tests.test_tenancy_dreaming_cli_transport::test_summary_commands_stay_on_the_global_tenant (passed, red_assertion); packages.mcp.tests.test_tenancy_dreaming_mcp... | - | 0.86 |
| C-051abf8f | Req 4.2 | covered | packages.api.tests.test_tenancy_dreaming_api_transport::test_image_jobs_use_the_global_default (passed, red_assertion); packages.mcp.tests.test_tenancy_dreaming_mcp_transport::test_image_jobs_use_the_global_default (passed, red_assertion) | - | 0.90 |
| C-18514cb1 | Req 5.1 | covered | packages.core.tests.test_tenancy_core_functions::test_create_note_stamps_and_anchors_inside_its_tenant (passed, zero_value) | - | 0.90 |
| C-abd8e186 | Req 5.2 | covered | packages.core.tests.test_tenancy_core_functions::test_notes_list_passes_the_tenant_to_the_storage (passed, zero_value) | - | 0.94 |
| C-3b007667 | Req 5.3 | covered | packages.core.tests.test_tenancy_core_functions::test_image_jobs_lists_only_the_requested_tenant (passed, pre_satisfied) | - | 0.92 |
| C-5e505f8c | Req 5.4 | covered | packages.core.tests.test_tenancy_core_functions::test_caption_pending_images_forwards_the_tenant (passed, pre_satisfied); packages.core.tests.test_tenancy_core_functions::test_image_caption_put_archives_prior_description_inside_the_tenant (passed, pre_satisfied); packages.core.tests.test_tenancy_cor... | - | 0.90 |
| C-5d0cf777 | Req 5.5 | covered | packages.core.tests.test_tenancy_core_functions::test_apply_feedback_scoped_rejects_a_foreign_session_before_scoring (passed, zero_value); packages.core.tests.test_tenancy_core_functions::test_apply_feedback_scoped_rejects_an_inactive_session_tenant (passed, zero_value); packages.core.tests.test_ten... | - | - |
| C-aa16078a | Req 5.6 | covered | packages.core.tests.test_tenancy_core_functions::test_changed_with_is_confined_to_the_tenant (passed, zero_value); packages.core.tests.test_tenancy_core_functions::test_documents_timeline_is_confined_to_the_tenant (passed, zero_value) | - | 0.89 |
| C-af9d319a | Req 5.7 | covered | packages.cli.tests.test_tenancy_core_create_paths::test_index_tree_and_cli_ingest_write_global_records (passed, pre_satisfied) | - | 0.82 |
| C-e138c61a | Req 5.8 | covered | packages.core.tests.test_tenancy_core_functions::test_create_note_leaves_the_note_when_the_tenant_is_deactivated_mid_run (passed, zero_value) | - | 0.84 |
| C-1c14608f | Req 6.1 | covered | packages.api.tests.test_tenancy_api_errors::test_search_is_unscoped_and_creates_are_stamped_global (passed, pre_satisfied) | - | 0.79 |
| C-48ed16ae | Req 6.2 | covered | packages.api.tests.test_tenancy_api_errors::test_tenant_errors_map_to_http_statuses[<lambda>-403_0] (passed, red_assertion); packages.api.tests.test_tenancy_api_errors::test_tenant_errors_map_to_http_statuses[<lambda>-403_1] (passed, red_assertion); packages.api.tests.test_tenancy_api_errors::test_t... | - | 0.94 |
| C-8308a89a | Req 6.3 | covered | packages.api.tests.test_tenancy_api_errors::test_cross_tenant_link_archive_and_inactive_patch_examples (passed, red_assertion) | - | 0.92 |
| C-61a564ed | Req 7.1 | covered | packages.core.tests.test_tenancy_core_full_gate::test_existing_callers_can_keep_omitting_the_tenant (passed, pre_satisfied); packages.core.tests.test_tenancy_core_full_gate::test_global_only_database_keeps_existing_default_core_reads (passed, pre_satisfied); packages.core.tests.test_tenancy_core_ful... | - | 0.82 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `.kiro/specs/tenant-scoped-core/.l4/ledger/r-20261020T0514Z-8813.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/tenant-scoped-core/.l4/ledger/r-20261020T0522Z-d787.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/tenant-scoped-core/.l4/ledger/r-20261020T0729Z-c0e2.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/tenant-scoped-core/.l4/ledger/r-20261020T1032Z-59e4.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/tenant-scoped-core/questions.md` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/tenant-scoped-core/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/api/src/mintmory/api/app.py` | api | relevant | named in the spec |
| `packages/api/tests/test_tenancy_api_errors.py` |  | relevant | new test file |
| `packages/api/tests/test_tenancy_dreaming_api_transport.py` |  | relevant | new test file |
| `packages/cli/src/mintmory/cli/main.py` | cli | relevant | named in the spec |
| `packages/cli/tests/test_tenancy_core_create_paths.py` |  | relevant | new test file |
| `packages/cli/tests/test_tenancy_dreaming_cli_transport.py` |  | relevant | new test file |
| `packages/core/src/mintmory/core/cochange.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/dreaming.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/llm.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/notes.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/session.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/vision.py` | core | relevant | named in the spec |
| `packages/core/tests/test_tenancy_core_full_gate.py` |  | relevant | new test file |
| `packages/core/tests/test_tenancy_core_functions.py` |  | relevant | new test file |
| `packages/core/tests/test_tenancy_dreaming.py` |  | relevant | new test file |
| `packages/core/tests/test_tenancy_dreaming_entrypoints.py` |  | relevant | new test file |
| `packages/mcp/src/mintmory/mcp/server.py` | mcp | relevant | named in the spec |
| `packages/mcp/tests/test_tenancy_dreaming_mcp_transport.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

2247 of 2361 passed, 0 failed, 0 errored, 114 skipped.
57 of 57 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-49f64902 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8b56effb | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3b1be517 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-180a8a6f | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8bf5b256 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-86ecfcef | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1db051ad | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-cd24da0d | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-443639c5 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-61979b79 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6d7b9d0d | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-bb56329e | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ac42fe75 | ok | 0.640 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d95fbef7 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-dc6f014f | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7881686c | ok | 0.770 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d9c39ea3 | ok | 0.780 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-63860dbc | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a0213e6c | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-051abf8f | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-18514cb1 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-abd8e186 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3b007667 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5e505f8c | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5d0cf777 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-aa16078a | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-af9d319a | ok | 0.820 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e138c61a | ok | 0.840 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1c14608f | ok | 0.790 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-48ed16ae | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8308a89a | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-61a564ed | ok | 0.820 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-49f64902 | Req 1.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-8b56effb | Req 1.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-3b1be517 | Req 1.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-180a8a6f | Req 1.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-8bf5b256 | Req 1.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-86ecfcef | Req 1.6 | pass | pass | the judge passed it and a discriminating test passes |
| C-1db051ad | Req 1.7 | pass | pass | the judge passed it and a discriminating test passes |
| C-cd24da0d | Req 1.8 | pass | pass | the judge passed it and a discriminating test passes |
| C-443639c5 | Req 2.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-61979b79 | Req 2.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-6d7b9d0d | Req 2.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-bb56329e | Req 2.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-ac42fe75 | Req 2.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-d95fbef7 | Req 2.6 | pass | pass | the judge passed it and a discriminating test passes |
| C-dc6f014f | Req 2.7 | pass | pass | the judge passed it and a discriminating test passes |
| C-7881686c | Req 3.1 | insufficient_evidence | needs_human | the judge answered insufficient_evidence |
| C-d9c39ea3 | Req 3.2 | insufficient_evidence | needs_human | the judge answered insufficient_evidence |
| C-63860dbc | Req 3.3 | insufficient_evidence | needs_human | the judge answered insufficient_evidence |
| C-a0213e6c | Req 4.1 | insufficient_evidence | needs_human | the judge answered insufficient_evidence |
| C-051abf8f | Req 4.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-18514cb1 | Req 5.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-abd8e186 | Req 5.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-3b007667 | Req 5.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-5e505f8c | Req 5.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-5d0cf777 | Req 5.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-aa16078a | Req 5.6 | pass | pass | the judge passed it and a discriminating test passes |
| C-af9d319a | Req 5.7 | pass | pass | the judge passed it and a discriminating test passes |
| C-e138c61a | Req 5.8 | pass | pass | the judge passed it and a discriminating test passes |
| C-1c14608f | Req 6.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-48ed16ae | Req 6.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-8308a89a | Req 6.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-61a564ed | Req 7.1 | pass | pass | the judge passed it and a discriminating test passes |

## Findings

None.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.api.tests.test_tenancy_api_errors::test_cross_tenant_link_archive_and_inactive_patch_examples` (task 5): passed
- `packages.api.tests.test_tenancy_api_errors::test_search_is_unscoped_and_creates_are_stamped_global` (task 5): passed
- `packages.api.tests.test_tenancy_api_errors::test_tenant_errors_map_to_http_statuses[<lambda>-403_0]` (task 5): passed
- `packages.api.tests.test_tenancy_api_errors::test_tenant_errors_map_to_http_statuses[<lambda>-403_1]` (task 5): passed
- `packages.api.tests.test_tenancy_api_errors::test_tenant_errors_map_to_http_statuses[<lambda>-404]` (task 5): passed
- `packages.api.tests.test_tenancy_api_errors::test_tenant_errors_map_to_http_statuses[<lambda>-409_0]` (task 5): passed
- `packages.api.tests.test_tenancy_api_errors::test_tenant_errors_map_to_http_statuses[<lambda>-409_1]` (task 5): passed
- `packages.api.tests.test_tenancy_api_errors::test_tenant_errors_map_to_http_statuses[<lambda>-409_2]` (task 5): passed
- `packages.api.tests.test_tenancy_api_errors::test_tenant_errors_map_to_http_statuses[<lambda>-422]` (task 5): passed
- `packages.api.tests.test_tenancy_api_errors::test_tenant_errors_map_to_http_statuses[<lambda>-501]` (task 5): passed
- `packages.api.tests.test_tenancy_api_errors::test_tenant_errors_map_to_http_statuses[<lambda>-503]` (task 5): passed
- `packages.api.tests.test_tenancy_dreaming_api_transport::test_dream_failure_returns_500_detail` (task 3): passed
- `packages.api.tests.test_tenancy_dreaming_api_transport::test_dream_runs_each_tenant_without_cross_tenant_links` (task 3): passed
- `packages.api.tests.test_tenancy_dreaming_api_transport::test_image_jobs_use_the_global_default` (task 3): passed
- `packages.api.tests.test_tenancy_dreaming_api_transport::test_summary_routes_stay_on_the_global_tenant` (task 3): passed
- `packages.cli.tests.test_tenancy_core_create_paths::test_index_tree_and_cli_ingest_write_global_records` (task 4): passed
- `packages.cli.tests.test_tenancy_dreaming_cli_transport::test_dream_failure_reports_error_on_stderr` (task 3): passed
- `packages.cli.tests.test_tenancy_dreaming_cli_transport::test_dream_runs_each_tenant_without_cross_tenant_links` (task 3): passed
- `packages.cli.tests.test_tenancy_dreaming_cli_transport::test_summary_commands_stay_on_the_global_tenant` (task 3): passed
- `packages.core.tests.test_tenancy_core_full_gate::test_existing_callers_can_keep_omitting_the_tenant` (task 6): passed
- `packages.core.tests.test_tenancy_core_full_gate::test_global_only_database_keeps_existing_default_core_reads` (task 6): passed
- `packages.core.tests.test_tenancy_core_full_gate::test_tenancy_core_gate_commands_pass_without_external_services` (task 6): passed
- `packages.core.tests.test_tenancy_core_full_gate::test_tenancy_core_gate_declares_required_commands_and_coverage_floor` (task 6): passed
- `packages.core.tests.test_tenancy_core_functions::test_apply_feedback_scoped_rejects_a_foreign_session_before_scoring` (task 4): passed
- `packages.core.tests.test_tenancy_core_functions::test_apply_feedback_scoped_rejects_an_inactive_session_tenant` (task 4): passed
- `packages.core.tests.test_tenancy_core_functions::test_apply_feedback_scoped_validates_every_id_before_scoring` (task 4): passed
- `packages.core.tests.test_tenancy_core_functions::test_caption_pending_images_forwards_the_tenant` (task 4): passed
- `packages.core.tests.test_tenancy_core_functions::test_changed_with_is_confined_to_the_tenant` (task 4): passed
- `packages.core.tests.test_tenancy_core_functions::test_create_note_leaves_the_note_when_the_tenant_is_deactivated_mid_run` (task 4): passed
- `packages.core.tests.test_tenancy_core_functions::test_create_note_stamps_and_anchors_inside_its_tenant` (task 4): passed
- `packages.core.tests.test_tenancy_core_functions::test_documents_timeline_is_confined_to_the_tenant` (task 4): passed
- `packages.core.tests.test_tenancy_core_functions::test_image_caption_put_archives_prior_description_inside_the_tenant` (task 4): passed
- `packages.core.tests.test_tenancy_core_functions::test_image_caption_put_resolves_and_writes_inside_the_tenant` (task 4): passed
- `packages.core.tests.test_tenancy_core_functions::test_image_jobs_lists_only_the_requested_tenant` (task 4): passed
- `packages.core.tests.test_tenancy_core_functions::test_notes_list_passes_the_tenant_to_the_storage` (task 4): passed
- `packages.core.tests.test_tenancy_dreaming::test_build_conflict_resolver_lookups_are_tenant_scoped` (task 1): passed
- `packages.core.tests.test_tenancy_dreaming::test_build_dreaming_engine_passes_tenant_to_the_engine` (task 1): passed
- `packages.core.tests.test_tenancy_dreaming::test_engine_confines_every_read_and_write_to_its_tenant` (task 1): passed
- `packages.core.tests.test_tenancy_dreaming::test_engine_stores_its_tenant` (task 1): passed
- `packages.core.tests.test_tenancy_dreaming::test_legacy_engine_may_attempt_a_cross_tenant_link_and_add_link_refuses` (task 1): passed
- `packages.core.tests.test_tenancy_dreaming::test_legacy_engine_stores_none_and_stamps_global_writes` (task 1): passed
- `packages.core.tests.test_tenancy_dreaming::test_scenario_a_linking_and_summaries_stay_inside_the_tenant` (task 1): passed
- `packages.core.tests.test_tenancy_dreaming::test_scenario_b_cross_tenant_contradiction_is_skipped` (task 1): passed
- `packages.core.tests.test_tenancy_dreaming::test_summary_jobs_and_apply_summary_use_the_engine_tenant` (task 1): passed
- `packages.core.tests.test_tenancy_dreaming_entrypoints::test_dream_all_tenants_records_a_factory_failure_and_run_dream_raises` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_entrypoints::test_dream_all_tenants_records_a_run_failure_and_continues` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_entrypoints::test_dream_all_tenants_runs_active_tenants_with_their_intensity` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_entrypoints::test_dream_failed_error_message_sorts_tenants_and_keeps_failed` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_entrypoints::test_dreaming_module_defines_the_per_tenant_entry_point_surface` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_entrypoints::test_one_tenant_run_dream_parity_with_the_legacy_engine` (task 2): passed

## Guard events

- guard.violation: packages/core/src/mintmory/core/dreaming.py
- guard.violation: packages/core/src/mintmory/core/dreaming.py
- guard.violation: packages/core/src/mintmory/core/dreaming.py
- guard.violation: packages/core/src/mintmory/core/dreaming.py
- guard.violation: packages/core/src/mintmory/core/dreaming.py
- guard.violation: packages/core/src/mintmory/core/notes.py
- guard.violation: packages/core/src/mintmory/core/notes.py
- guard.violation: packages/core/src/mintmory/core/notes.py
- guard.violation: packages/core/src/mintmory/core/cochange.py
- guard.violation: packages/core/src/mintmory/core/cochange.py
- guard.violation: packages/core/src/mintmory/core/notes.py
- guard.violation: packages/core/src/mintmory/core/notes.py
- guard.violation: packages/core/src/mintmory/core/session.py
- guard.violation: packages/core/src/mintmory/core/notes.py
