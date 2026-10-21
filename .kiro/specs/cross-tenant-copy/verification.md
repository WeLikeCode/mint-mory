# Verification: kiro:cross-tenant-copy: NEEDS_HUMAN (round 1)

traceability: 35/35 criteria covered by a discriminating test

- Base: `146d99b529fb4619ee641f4ccaa174a3f488e9b0`
- Head: `e8ce98629cb9eb90a9c5a7cdbf75cf186f5d90fd`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 2 call(s), prompt sha256 `e40f051e7c918ba7c771e2a444968ec285ae8a246209b4de0a7fd27289c14c47`
- Judge replies of claude-judge (this unit, all rounds): valid 0, repaired 0, retried 1, discarded 0; this round: retried
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $1.6663

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.0 | base merged: staging@146d99b529 as e8ce98629c (1 commit) |
| 1 | integrity | ok | 252.4 | 10 sub-checks (+1 unfrozen by human answers); scope: 18 changed file(s) |
| 2 | build | ok | 6.7 |  |
| 3 | tests | ok | 118.3 |  |
| 4 | traceability | ok | 0.2 | 35/35 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 2.8 | 32/35 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 80.5 | 2 call(s) |
| 10 | aggregation | ok | 0.0 | NEEDS_HUMAN |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261021T0641Z-9d5b/030-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261021T0641Z-9d5b/031-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261021T0641Z-9d5b/032-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261021T0641Z-9d5b/033-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261021T0641Z-9d5b/034-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 8 test file(s) compared with the base (+3 allowed, listed) |
| red-green freeze | ok | 5 task(s): red and green compared (+1 unfrozen by human answers) |
| test path freeze | ok | 5 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 6 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2328 of 2328 base tests pass on the unit's code with its 5 test and support files at the base (base: base worktree) |

## Pre-existing tests changed with an allowance (L4-VER-031)

- packages/mcp/tests/test_mcp_tenancy_directory.py::test_no_tool_exposes_a_tenant_selector changed (task 4: unfrozen by Q-001, Q-002)
- packages/mcp/tests/test_mcp_tenancy_directory.py::test_tool_inventory_matches_declared_tenant_scope changed (task 4: unfrozen by Q-001, Q-002)
- packages/mcp/tests/test_tools.py::test_all_tools_registered changed (task 4: unfrozen by Q-001, Q-002)
- packages/cli/tests/test_cli_tenant_copy.py kept at head for the run (task 5: unfrozen by Q-003)
- packages/mcp/tests/test_mcp_tenancy_directory.py kept at head for the run (task 4: unfrozen by Q-001, Q-002)
- packages/mcp/tests/test_tools.py kept at head for the run (task 4: unfrozen by Q-001, Q-002)

## Tests unfrozen by human answers (allowed, L4-IMP-002)

- packages/cli/tests/test_cli_tenant_copy.py (task 5, unfrozen by Q-003 (human))

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-66378bd9 | Req 1.1 | covered | packages.core.tests.test_transfer::test_transfer_module_defines_report_error_and_entry_point (passed, zero_value) | - | 0.60 |
| C-21e82523 | Req 2.1 | covered | packages.core.tests.test_transfer::test_all_active_conflicts_with_ids_or_filter (passed, zero_value); packages.core.tests.test_transfer::test_all_active_with_empty_memory_ids_passes_validation (passed, zero_value); packages.core.tests.test_transfer::test_copy_max_boundary_counts_distinct_ids (passed... | - | - |
| C-18841969 | Req 2.2 | covered | packages.core.tests.test_transfer::test_all_active_with_empty_memory_ids_passes_validation (passed, zero_value); packages.core.tests.test_transfer::test_empty_filter_is_rejected (passed, zero_value); packages.core.tests.test_transfer::test_non_empty_filter_passes_validation (passed, zero_value) | - | 0.90 |
| C-0380775d | Req 3.1 | covered | packages.core.tests.test_transfer_selection::test_explicit_ids_copy_in_input_order_and_count_unfit_rows_once (passed, red_assertion); packages.core.tests.test_transfer_selection::test_unknown_archived_and_global_ids_count_as_not_found (passed, red_assertion) | - | 0.90 |
| C-3affbf7d | Req 3.2 | covered | packages.core.tests.test_transfer_selection::test_all_active_cap_applies_after_superseded_rows_are_dropped (passed, red_assertion); packages.core.tests.test_transfer_selection::test_all_active_includes_stale_rows_and_drops_superseded (passed, red_assertion); packages.core.tests.test_transfer_selecti... | - | 0.92 |
| C-d9e27376 | Req 3.3 | covered | packages.core.tests.test_transfer_selection::test_explicit_ids_copy_in_input_order_and_count_unfit_rows_once (passed, red_assertion); packages.core.tests.test_transfer_selection::test_id_rows_come_before_filter_rows_and_dedupe_first_occurrence (passed, red_assertion) | - | 0.90 |
| C-93dcf70e | Req 3.4 | covered | packages.core.tests.test_transfer_selection::test_attached_note_selected_and_attached_is_copied_once (passed, red_assertion); packages.core.tests.test_transfer_selection::test_inactive_and_superseded_attached_notes_are_ignored_and_uncounted (passed, red_assertion); packages.core.tests.test_transfer_... | - | 0.87 |
| C-7c07d4ec | Req 4.1 | covered | packages.core.tests.test_transfer_selection::test_existing_destination_content_skips_record_and_expands_no_note (passed, red_assertion); packages.core.tests.test_transfer_selection::test_force_copies_duplicates_and_destination_check_sees_archived_and_inactive (passed, red_assertion); packages.core.t... | - | 0.93 |
| C-dde5363b | Req 4.2 | covered | packages.core.tests.test_transfer_selection::test_existing_destination_content_skips_record_and_expands_no_note (passed, red_assertion) | - | 0.91 |
| C-1e794dc0 | Req 4.3 | covered | packages.core.tests.test_transfer_selection::test_force_copies_duplicates_and_destination_check_sees_archived_and_inactive (passed, red_assertion); packages.core.tests.test_transfer_selection::test_force_copies_in_plan_duplicates_too (passed, red_assertion) | - | 0.94 |
| C-8b953633 | Req 4.4 | covered | packages.core.tests.test_transfer_selection::test_rerunning_the_same_copy_creates_no_record (passed, red_assertion) | - | 0.92 |
| C-1dcc08a5 | Req 5.1 | covered | packages.core.tests.test_transfer_selection::test_every_copy_gets_a_fresh_uuid_dest_tenant_and_now_timestamps (passed, red_assertion) | - | 0.91 |
| C-b9c11bfc | Req 5.2 | covered | packages.core.tests.test_transfer_selection::test_copied_record_keeps_copied_fields (passed, red_assertion) | - | 0.88 |
| C-53994c9f | Req 5.3 | covered | packages.core.tests.test_transfer_selection::test_copied_record_state_is_reset (passed, red_assertion) | - | 0.86 |
| C-28775698 | Req 5.4 | covered | packages.core.tests.test_transfer_selection::test_metadata_anchor_is_removed_when_anchor_memory_is_not_copied (passed, red_assertion); packages.core.tests.test_transfer_selection::test_metadata_merge_overwrites_provenance_and_rewrites_the_anchor (passed, red_assertion) | - | 0.92 |
| C-b418242c | Req 5.5 | covered | packages.core.tests.test_transfer_selection::test_copies_are_written_through_add_memory (passed, red_assertion); packages.core.tests.test_transfer_selection::test_seeded_copy_reports_places_provenance_and_search_finds_it (passed, red_assertion) | - | 0.86 |
| C-65fb9501 | Req 6.1 | covered | packages.core.tests.test_transfer_links::test_copied_links_are_recreated_once_with_rewritten_endpoints (passed, red_assertion); packages.core.tests.test_transfer_links::test_link_to_a_skipped_duplicate_is_not_created (passed, red_assertion); packages.core.tests.test_transfer_links::test_link_with_en... | - | 0.92 |
| C-49684d62 | Req 7.1 | covered | packages.core.tests.test_transfer_links::test_failing_add_link_rolls_everything_back (passed, red_assertion); packages.core.tests.test_transfer_selection::test_exception_during_writes_rolls_back_the_destination (passed, red_assertion) | - | 0.85 |
| C-ba8edb36 | Req 7.2 | covered | packages.core.tests.test_transfer_selection::test_seeded_copy_reports_places_provenance_and_search_finds_it (passed, red_assertion); packages.core.tests.test_transfer_selection::test_source_rows_are_identical_after_all_active_copy (passed, red_assertion) | - | 0.92 |
| C-854a40b8 | Req 7.3 | covered | packages.core.tests.test_transfer_links::test_concurrent_copies_in_one_process_are_serialised (passed, pre_satisfied); packages.core.tests.test_transfer_links::test_destination_deactivated_between_writes_rolls_back (passed, pre_satisfied) | - | 0.88 |
| C-ae539615 | Req 7.4 | covered | packages.core.tests.test_transfer_links::test_postgres_copy_fails_closed_before_any_write (passed, pre_satisfied) | - | 0.89 |
| C-3a04fd3e | Req 8.1 | covered | packages.mcp.tests.test_tenancy_copy_mcp::test_global_scope_tenant_copy_returns_the_report_json (passed, zero_value); packages.mcp.tests.test_tenancy_copy_mcp::test_tenant_copy_empty_filter_is_a_selection_error (passed, zero_value); packages.mcp.tests.test_tenancy_copy_mcp::test_tenant_copy_invalid_... | - | - |
| C-2f599c95 | Req 8.2 | covered | packages.cli.tests.test_cli_tenant_copy::test_category_and_entity_filters_union_with_explicit_ids (passed, red_assertion); packages.cli.tests.test_cli_tenant_copy::test_copied_rows_are_visible_in_the_destination_tenant (passed, red_assertion); packages.cli.tests.test_cli_tenant_copy::test_empty_sele... | - | - |
| C-fd8b39a5 | Req 9.1 | covered | tests.integration.test_tenancy_copy::test_r9_1_seed_is_copied_by_the_cli_then_beta_dream_stays_inside_beta (passed, pre_satisfied) | - | 0.77 |
| C-38635874 | Req 9.2 | covered | packages.core.tests.test_transfer_links::test_copied_links_are_recreated_once_with_rewritten_endpoints (passed, red_assertion); packages.core.tests.test_transfer_selection::test_copied_record_keeps_copied_fields (passed, red_assertion); packages.core.tests.test_transfer_selection::test_copied_record... | - | 0.82 |
| C-ebb2acbb | Req 9.3 | covered | packages.core.tests.test_transfer_links::test_link_with_endpoint_outside_the_copy_is_not_created (passed, red_assertion) | - | 0.62 |
| C-38e5f134 | Req 9.4 | covered | packages.core.tests.test_transfer_selection::test_force_recopies_m1_m2_and_n1 (passed, red_assertion); packages.core.tests.test_transfer_selection::test_rerunning_the_same_copy_creates_no_record (passed, red_assertion) | - | 0.80 |
| C-02945d2c | Req 9.5 | covered | packages.core.tests.test_transfer_selection::test_inactive_and_superseded_attached_notes_are_ignored_and_uncounted (passed, red_assertion); packages.core.tests.test_transfer_selection::test_two_source_records_with_the_same_content_copies_one_and_counts_one_duplicate (passed, red_assertion); packages... | - | 0.88 |
| C-c38088c4 | Req 9.6 | covered | packages.core.tests.test_transfer_selection::test_all_active_copies_m1_m2_and_n1_each_once (passed, red_assertion); packages.core.tests.test_transfer_selection::test_all_active_includes_stale_rows_and_drops_superseded (passed, red_assertion) | - | 0.93 |
| C-63f0307a | Req 9.7 | covered | packages.core.tests.test_transfer::test_all_active_conflicts_with_ids_or_filter (passed, zero_value); packages.core.tests.test_transfer::test_empty_filter_is_rejected (passed, zero_value); packages.core.tests.test_transfer::test_empty_selection_is_rejected (passed, zero_value); packages.core.tests.t... | - | 0.88 |
| C-ad2c5b13 | Req 9.8 | covered | packages.core.tests.test_transfer_links::test_failing_add_link_rolls_everything_back (passed, red_assertion) | - | 0.89 |
| C-7b613be5 | Req 9.9 | covered | packages.core.tests.test_transfer_selection::test_all_active_over_the_patched_cap_is_rejected (passed, red_assertion) | - | 0.95 |
| C-654ba513 | Req 9.10 | covered | packages.cli.tests.test_cli_tenant_copy::test_empty_selection_prints_a_selection_error_and_exits_one (passed, red_assertion); packages.cli.tests.test_cli_tenant_copy::test_named_root_tenant_refuses_copy_with_global_scope_message (passed, red_assertion); packages.cli.tests.test_cli_tenant_copy::test_... | - | 0.94 |
| C-86c2ff91 | Req 9.11 | covered | tests.integration.test_tenancy_copy::test_r9_1_seed_is_copied_by_the_cli_then_beta_dream_stays_inside_beta (passed, pre_satisfied) | - | 0.90 |
| C-00790979 | Req 10.1 | covered | tests.integration.test_tenancy_copy::test_configured_gates_pass_and_the_copy_flow_needs_no_external_service (passed, pre_satisfied) | - | 0.87 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `.kiro/specs/cross-tenant-copy/.l4/ledger/r-20261021T0202Z-9e81.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/cross-tenant-copy/.l4/ledger/r-20261021T0354Z-5218.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/cross-tenant-copy/.l4/ledger/r-20261021T0355Z-3d98.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/cross-tenant-copy/.l4/ledger/r-20261021T0612Z-645f.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/cross-tenant-copy/.l4/ledger/r-20261021T0641Z-9d5b.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/cross-tenant-copy/questions.md` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/cross-tenant-copy/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/cli/src/mintmory/cli/main.py` | cli | relevant | named in the spec |
| `packages/cli/tests/test_cli_tenant_copy.py` |  | relevant | new test file |
| `packages/core/src/mintmory/core/transfer.py` | core | relevant | named in the spec |
| `packages/core/tests/test_transfer.py` |  | relevant | new test file |
| `packages/core/tests/test_transfer_links.py` |  | relevant | new test file |
| `packages/core/tests/test_transfer_selection.py` |  | relevant | new test file |
| `packages/mcp/src/mintmory/mcp/server.py` | mcp | relevant | named in the spec |
| `packages/mcp/tests/test_mcp_tenancy_directory.py` |  | none | imports no module of the repository |
| `packages/mcp/tests/test_tenancy_copy_mcp.py` |  | relevant | new test file |
| `packages/mcp/tests/test_tools.py` |  | none | imports no module of the repository |
| `tests/integration/test_tenancy_copy.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

2394 of 2508 passed, 0 failed, 0 errored, 114 skipped.
66 of 66 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-66378bd9 | ok | 0.600 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-21e82523 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-18841969 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0380775d | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3affbf7d | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d9e27376 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-93dcf70e | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7c07d4ec | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-dde5363b | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1e794dc0 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8b953633 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1dcc08a5 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b9c11bfc | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-53994c9f | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-28775698 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b418242c | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-65fb9501 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-49684d62 | ok | 0.850 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ba8edb36 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-854a40b8 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ae539615 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3a04fd3e | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-2f599c95 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-fd8b39a5 | ok | 0.770 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-38635874 | ok | 0.820 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ebb2acbb | ok | 0.620 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-38e5f134 | ok | 0.800 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-02945d2c | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c38088c4 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-63f0307a | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ad2c5b13 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7b613be5 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-654ba513 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-86c2ff91 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-00790979 | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-66378bd9 | Req 1.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-21e82523 | Req 2.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-18841969 | Req 2.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-0380775d | Req 3.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-3affbf7d | Req 3.2 | fail | needs_human | judge fail counted as insufficient_evidence: counterexample unexecuted (not executed in M0: the verifier worktree is M1 (verifier 1.5)) |
| C-d9e27376 | Req 3.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-93dcf70e | Req 3.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-7c07d4ec | Req 4.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-dde5363b | Req 4.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-1e794dc0 | Req 4.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-8b953633 | Req 4.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-1dcc08a5 | Req 5.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-b9c11bfc | Req 5.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-53994c9f | Req 5.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-28775698 | Req 5.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-b418242c | Req 5.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-65fb9501 | Req 6.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-49684d62 | Req 7.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-ba8edb36 | Req 7.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-854a40b8 | Req 7.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-ae539615 | Req 7.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-3a04fd3e | Req 8.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-2f599c95 | Req 8.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-fd8b39a5 | Req 9.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-38635874 | Req 9.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-ebb2acbb | Req 9.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-38e5f134 | Req 9.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-02945d2c | Req 9.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-c38088c4 | Req 9.6 | pass | pass | the judge passed it and a discriminating test passes |
| C-63f0307a | Req 9.7 | pass | pass | the judge passed it and a discriminating test passes |
| C-ad2c5b13 | Req 9.8 | pass | pass | the judge passed it and a discriminating test passes |
| C-7b613be5 | Req 9.9 | pass | pass | the judge passed it and a discriminating test passes |
| C-654ba513 | Req 9.10 | pass | pass | the judge passed it and a discriminating test passes |
| C-86c2ff91 | Req 9.11 | pass | pass | the judge passed it and a discriminating test passes |
| C-00790979 | Req 10.1 | pass | pass | the judge passed it and a discriminating test passes |
- C-3affbf7d: counterexample unexecuted (not executed in M0: the verifier worktree is M1 (verifier 1.5))

## Findings

- [major, judge] R3.2 cap on filter/all_active rows is not enforced before duplicate skipping (criterion C-3affbf7d): _select never compares the remaining filter or all_active rows against COPY_MAX. Only len(plan) is checked, after duplicates are skipped. test_skipped_duplicates_do_not_count_toward_copy_max encodes this behaviour, which contradicts R3.2.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.cli.tests.test_cli_tenant_copy::test_category_and_entity_filters_union_with_explicit_ids` (task 5): passed
- `packages.cli.tests.test_cli_tenant_copy::test_copied_rows_are_visible_in_the_destination_tenant` (task 5): passed
- `packages.cli.tests.test_cli_tenant_copy::test_empty_selection_prints_a_selection_error_and_exits_one` (task 5): passed
- `packages.cli.tests.test_cli_tenant_copy::test_force_flag_recopies_duplicate_content` (task 5): passed
- `packages.cli.tests.test_cli_tenant_copy::test_named_root_tenant_refuses_copy_with_global_scope_message` (task 5): passed
- `packages.cli.tests.test_cli_tenant_copy::test_tenant_copy_json_prints_exactly_the_report_model_json` (task 5): passed
- `packages.cli.tests.test_cli_tenant_copy::test_tenant_copy_prints_a_metric_table_in_report_field_order` (task 5): passed
- `packages.cli.tests.test_cli_tenant_copy::test_tenant_error_prints_error_and_exits_one` (task 5): passed
- `packages.core.tests.test_transfer::test_all_active_conflicts_with_ids_or_filter` (task 1): passed
- `packages.core.tests.test_transfer::test_all_active_with_empty_memory_ids_passes_validation` (task 1): passed
- `packages.core.tests.test_transfer::test_copy_max_boundary_counts_distinct_ids` (task 1): passed
- `packages.core.tests.test_transfer::test_empty_filter_is_rejected` (task 1): passed
- `packages.core.tests.test_transfer::test_empty_selection_is_rejected` (task 1): passed
- `packages.core.tests.test_transfer::test_inactive_destination_tenant_is_rejected` (task 1): passed
- `packages.core.tests.test_transfer::test_inactive_source_tenant_is_allowed` (task 1): passed
- `packages.core.tests.test_transfer::test_invalid_tenant_ids_are_rejected_first` (task 1): passed
- `packages.core.tests.test_transfer::test_non_empty_filter_passes_validation` (task 1): passed
- `packages.core.tests.test_transfer::test_same_source_and_destination_rejected` (task 1): passed
- `packages.core.tests.test_transfer::test_selection_over_copy_max_is_rejected` (task 1): passed
- `packages.core.tests.test_transfer::test_source_tenant_is_checked_before_destination` (task 1): passed
- `packages.core.tests.test_transfer::test_transfer_module_defines_report_error_and_entry_point` (task 1): passed
- `packages.core.tests.test_transfer_links::test_concurrent_copies_in_one_process_are_serialised` (task 3): passed
- `packages.core.tests.test_transfer_links::test_copied_links_are_recreated_once_with_rewritten_endpoints` (task 3): passed
- `packages.core.tests.test_transfer_links::test_destination_deactivated_between_writes_rolls_back` (task 3): passed
- `packages.core.tests.test_transfer_links::test_failing_add_link_rolls_everything_back` (task 3): passed
- `packages.core.tests.test_transfer_links::test_link_to_a_skipped_duplicate_is_not_created` (task 3): passed
- `packages.core.tests.test_transfer_links::test_link_with_endpoint_outside_the_copy_is_not_created` (task 3): passed
- `packages.core.tests.test_transfer_links::test_postgres_copy_fails_closed_before_any_write` (task 3): passed
- `packages.core.tests.test_transfer_selection::test_all_active_cap_applies_after_superseded_rows_are_dropped` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_all_active_copies_m1_m2_and_n1_each_once` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_all_active_includes_stale_rows_and_drops_superseded` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_all_active_over_the_patched_cap_is_rejected` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_attached_note_selected_and_attached_is_copied_once` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_copied_record_keeps_copied_fields` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_copied_record_state_is_reset` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_copies_are_written_through_add_memory` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_every_copy_gets_a_fresh_uuid_dest_tenant_and_now_timestamps` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_exception_during_writes_rolls_back_the_destination` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_existing_destination_content_skips_record_and_expands_no_note` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_explicit_ids_copy_in_input_order_and_count_unfit_rows_once` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_filter_selects_matching_rows_and_drops_superseded` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_filter_with_exclude_stale_false_keeps_stale_rows` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_force_copies_duplicates_and_destination_check_sees_archived_and_inactive` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_force_copies_in_plan_duplicates_too` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_force_recopies_m1_m2_and_n1` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_id_rows_come_before_filter_rows_and_dedupe_first_occurrence` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_inactive_and_superseded_attached_notes_are_ignored_and_uncounted` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_metadata_anchor_is_removed_when_anchor_memory_is_not_copied` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_metadata_merge_overwrites_provenance_and_rewrites_the_anchor` (task 2): passed
- `packages.core.tests.test_transfer_selection::test_note_duplicate_is_counted_in_notes_skipped_duplicate` (task 2): passed

## Guard events

- guard.violation: packages/core/src/mintmory/core/transfer.py
- guard.test_tamper: packages/core/tests/test_transfer.py
- guard.violation: packages/core/src/mintmory/core/transfer.py
- guard.violation: packages/core/src/mintmory/core/transfer.py
- guard.violation: packages/mcp/src/mintmory/mcp/server.py
- guard.test_tamper: packages/mcp/tests/test_mcp_tenancy_directory.py
- guard.test_tamper: packages/mcp/tests/test_tools.py
