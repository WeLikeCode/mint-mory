# Verification: kiro:multi-tenancy-cli: FAIL (round 2)

traceability: 18/29 criteria covered by a discriminating test

- Base: `7ae2320de153d99a3aef4d11ef87be3d8b8e4aac`
- Head: `94313f9136fc2dd29a20297c1b77f66ff332bf60`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 2 call(s), prompt sha256 `e37586fd16f8e5ce34a08d6c6e260c6478e36f138a973e80d885d596ff30fd02`
- Judge replies of claude-judge (this unit, all rounds): valid 0, repaired 0, retried 2, discarded 0; this round: retried
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $1.3142

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.0 | base merged: staging@7ae2320de1 as 94313f9136 (2 commits) |
| 1 | integrity | ok | 229.9 | 10 sub-checks; scope: 16 changed file(s) |
| 2 | build | ok | 7.0 |  |
| 3 | tests | ok | 97.9 |  |
| 4 | traceability | ok | 0.2 | 18/29 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 4.2 | 29/29 criteria judged by jev |
| 9 | judge | ok | 54.6 | 2 call(s) |
| 10 | aggregation | ok | 0.0 | FAIL |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261020T1856Z-351e/005-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261020T1856Z-351e/006-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261020T1856Z-351e/007-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261020T1856Z-351e/008-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261020T1856Z-351e/009-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 4 test file(s) compared with the base |
| red-green freeze | ok | 2 task(s): red and green compared |
| test path freeze | ok | 2 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 5 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2247 of 2247 base tests pass on the unit's code with its 4 test and support files at the base (base: base worktree) |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-59ce4fbd | Req 1.1 | covered | packages.cli.tests.test_cli_tenancy_root::test_tenant_option_goes_before_the_command (passed, zero_value) | - | 0.87 |
| C-81db0c61 | Req 1.2 | covered | packages.cli.tests.test_cli_tenancy_root::test_invalid_tenant_is_rejected_before_any_command (passed, zero_value); packages.cli.tests.test_cli_tenancy_root::test_refusals_and_validation_happen_before_the_command (passed, zero_value); packages.cli.tests.test_cli_tenancy_root::test_tenant_scope_maps_a... | - | 0.85 |
| C-041d227d | Req 1.3 | covered | packages.cli.tests.test_cli_tenancy_root::test_tenant_scope_maps_absent_empty_global_and_named (passed, zero_value) | - | 0.81 |
| C-bfe27132 | Req 1.4 | covered | packages.cli.tests.test_cli_tenancy_root::test_help_documents_the_tenant_option (passed, zero_value) | - | 0.89 |
| C-cf987871 | Req 2.1 | covered | packages.cli.tests.test_cli_tenancy::test_add_search_and_stats_use_the_selected_tenant (passed, red_assertion); packages.cli.tests.test_cli_tenancy::test_docs_commands_are_read_tenant_scoped (passed, red_assertion) | packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests... | 0.84 |
| C-8610aa4b | Req 2.2 | uncovered | - | packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3)) | 0.18 |
| C-92f6541b | Req 2.3 | uncovered | - | packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled (it traces 7 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests... | 0.24 |
| C-b86d1447 | Req 2.4 | uncovered | - | packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.te... | 0.25 |
| C-20bd1e63 | Req 3.1 | covered | packages.cli.tests.test_cli_tenancy_root::test_doctor_refuses_a_named_tenant (passed, zero_value); packages.cli.tests.test_cli_tenancy_root::test_history_refuses_a_named_tenant (passed, zero_value); packages.cli.tests.test_cli_tenancy_root::test_index_tree_refuses_a_named_tenant (passed, zero_value)... | - | 0.94 |
| C-7760785e | Req 3.2 | covered | packages.cli.tests.test_cli_tenancy::test_valid_tenant_option_does_not_change_the_tenant_directory (passed, pre_satisfied); packages.cli.tests.test_cli_tenancy_root::test_valid_tenant_does_not_change_the_tenant_directory (passed, zero_value) | - | 0.91 |
| C-c35d15c6 | Req 4.1 | covered | packages.cli.tests.test_cli_tenancy::test_tenant_create_reports_created_again_and_invalid_ids (passed, pre_satisfied); packages.cli.tests.test_cli_tenancy::test_tenant_list_reports_fresh_global_and_created_tenants (passed, pre_satisfied) | - | 0.88 |
| C-58023183 | Req 4.2 | covered | packages.cli.tests.test_cli_tenancy::test_tenant_list_reports_fresh_global_and_created_tenants (passed, pre_satisfied) | - | 0.87 |
| C-8e7b8062 | Req 5.1 | covered | packages.cli.tests.test_cli_tenancy_root::test_tenant_migration_error_is_reported (passed, zero_value); packages.cli.tests.test_cli_tenancy_root::test_tenant_not_found_from_a_write_is_reported (passed, zero_value) | packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled (it traces 7 criteria (verifier.max_criteria_per_test=3)) | 0.76 |
| C-5dc41637 | Req 5.2 | uncovered | - | packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.te... | 0.08 |
| C-a79e558d | Req 6.1 | covered | packages.cli.tests.test_cli_tenancy::test_tenant_create_reports_created_again_and_invalid_ids (passed, pre_satisfied); packages.cli.tests.test_cli_tenancy::test_tenant_list_reports_fresh_global_and_created_tenants (passed, pre_satisfied) | - | 0.94 |
| C-46c6afc8 | Req 6.2 | covered | packages.cli.tests.test_cli_tenancy::test_add_search_and_stats_use_the_selected_tenant (passed, red_assertion); packages.cli.tests.test_cli_tenancy::test_docs_commands_are_read_tenant_scoped (passed, red_assertion) | packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3)); packages.cli.tests... | 0.80 |
| C-f10d86d5 | Req 6.3 | covered | packages.cli.tests.test_cli_tenancy::test_add_search_and_stats_use_the_selected_tenant (passed, red_assertion) | - | 0.90 |
| C-17c1d2d1 | Req 6.4 | uncovered | - | packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled (it traces 7 criteria (verifier.max_criteria_per_test=3)) | 0.15 |
| C-8fa7e2dd | Req 6.5 | covered | packages.cli.tests.test_cli_tenancy_root::test_refusals_and_validation_happen_before_the_command (passed, zero_value) | - | 0.91 |
| C-29450002 | Req 6.6 | uncovered | - | packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3)) | 0.10 |
| C-f9c22bd5 | Req 6.7 | uncovered | - | packages.cli.tests.test_cli_tenancy::test_note_and_notes_are_tenant_scoped (it traces 5 criteria (verifier.max_criteria_per_test=3)) | 0.18 |
| C-fbe84147 | Req 6.8 | uncovered | - | packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3)) | 0.27 |
| C-0459af16 | Req 6.9 | uncovered | - | packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3)) | 0.24 |
| C-5cf1ac32 | Req 6.10 | uncovered | - | packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant (it traces 6 criteria (verifier.max_criteria_per_test=3)) | 0.25 |
| C-a9f24733 | Req 6.11 | uncovered | - | packages.cli.tests.test_cli_tenancy::test_vision_run_and_caption_put_use_the_write_tenant (it traces 5 criteria (verifier.max_criteria_per_test=3)) | 0.32 |
| C-dc6d50e5 | Req 6.12 | covered | packages.cli.tests.test_cli_tenancy::test_docs_commands_are_read_tenant_scoped (passed, red_assertion) | - | 0.86 |
| C-74d42dd9 | Req 6.13 | covered | tests.integration.test_tenancy_cli::test_cli_tenancy_sequence_on_one_sqlite_file (passed, pre_satisfied) | - | 0.90 |
| C-769977e3 | Req 6.14 | covered | tests.integration.test_tenancy_cli::test_cli_tenancy_sequence_on_one_sqlite_file (passed, pre_satisfied) | - | 0.73 |
| C-88762101 | Req 7.1 | covered | packages.cli.tests.test_cli_tenancy_gate::test_gate_full_cli_tenancy_flow_and_coverage_floor (passed, pre_satisfied) | - | 0.81 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `.kiro/specs/multi-tenancy-cli/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-cli/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-cli/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-cli/.l4/ledger/r-20261020T1121Z-d7e0.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-cli/.l4/ledger/r-20261020T1159Z-9e37.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-cli/.l4/ledger/r-20261020T1312Z-7b7c.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-cli/.l4/ledger/r-20261020T1313Z-2c93.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-cli/.l4/ledger/r-20261020T1331Z-b7dd.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-cli/questions.md` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-cli/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-cli/verification.md` |  | none | exempt: harness, spec or documentation path |
| `packages/cli/src/mintmory/cli/main.py` | cli | relevant | named in the spec |
| `packages/cli/tests/test_cli_tenancy.py` |  | relevant | new test file |
| `packages/cli/tests/test_cli_tenancy_gate.py` |  | relevant | new test file |
| `packages/cli/tests/test_cli_tenancy_root.py` |  | relevant | new test file |
| `tests/integration/test_tenancy_cli.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

2275 of 2389 passed, 0 failed, 0 errored, 114 skipped.
28 of 28 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-59ce4fbd | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-81db0c61 | ok | 0.850 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-041d227d | ok | 0.810 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-bfe27132 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-cf987871 | ok | 0.840 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8610aa4b | ok | 0.180 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-92f6541b | ok | 0.240 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b86d1447 | ok | 0.250 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-20bd1e63 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7760785e | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c35d15c6 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-58023183 | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8e7b8062 | ok | 0.760 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5dc41637 | ok | 0.080 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a79e558d | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-46c6afc8 | ok | 0.800 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f10d86d5 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-17c1d2d1 | ok | 0.150 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8fa7e2dd | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-29450002 | ok | 0.100 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f9c22bd5 | ok | 0.180 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-fbe84147 | ok | 0.270 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0459af16 | ok | 0.240 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5cf1ac32 | ok | 0.250 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a9f24733 | ok | 0.320 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-dc6d50e5 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-74d42dd9 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-769977e3 | ok | 0.730 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-88762101 | ok | 0.810 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Human verdicts

- Q-002 accept C-8610aa4b by human: main.py:335 passes _read_tenant() to run_dream; dreaming.py:1066-1083 dreams each active tenant separately and prints total(); --tenant T runs only T (a CliRunner probe: --tenant acme dream made only acme links)
- Q-003 accept C-92f6541b by human: tenant nope search / summary-jobs / image-jobs exit 0 with empty results (test_cli_tenancy.py 179-185, 440-442, 480-482; confirmed by a CliRunner probe)
- Q-004 accept C-b86d1447 by human: _check_write_tenant (main.py:102) runs before any store work in add, ingest, note, summary-put, image-caption-put and vision-run (main.py:263, 485, 1248, 1369, 1488, 1534); dream gets the check from run_dream (dreaming.py:1076-1079); all exit 1 for a missing or inactive tenant
- Q-005 accept C-5dc41637 by human: the tenant check precedes every write; 14 refused writes left memories, concept links and summaries unchanged (probe); tests 204, 245-249, 311-315, 448-451
- Q-006 accept C-17c1d2d1 by human: test_missing_and_inactive_tenants_are_handled (test_cli_tenancy.py:170-206) asserts every clause (stderr text, no new row, the acme row still readable after deactivation) and passes
- Q-007 accept C-29450002 by human: ingest dedup is scoped to the write tenant (main.py:524-525); the test at 221-239 ends with rows [acme, global], which fails both if the repeat stored a row and if the acme copy suppressed the global one
- Q-008 accept C-f9c22bd5 by human: test 265-305 asserts the note is stamped acme, exactly one ANNOTATES link to the acme memory and none to the global one, and both the scoped and unscoped notes listings show it
- Q-009 accept C-fbe84147 by human: test 330-397 passes; a probe also confirmed --tenant acme dream made no global link, the unscoped dream added the global link, and no link crossed tenants
- Q-010 accept C-0459af16 by human: test 413-452 covers the jobs listing, the summary stored with tenant_id acme, and --tenant nope summary-jobs giving [] with exit 0
- Q-011 reject C-5cf1ac32 by human: R6.10 (requirements.md:171) requires exit 1; main.py:1497-1498 turns the KeyError into typer.BadParameter (exit 2) and test_cli_tenancy.py:500 asserts only != 0. WHEN image-caption-put is given an id or path with no active image file-record in the selected tenant THEN it prints 'error: no active ima...
- Q-012 accept C-a9f24733 by human: test 522-555 asserts the recorded tenant_id == acme and that --tenant nope vision-run and image-caption-put both exit 1 with 'not found'
- Q-013 reject F-2192b892 by human: R6.10 (requirements.md:171) requires exit 1; main.py:1497-1498 turns the KeyError into typer.BadParameter (exit 2) and test_cli_tenancy.py:500 asserts only != 0. WHEN image-caption-put is given an id or path with no active image file-record in the selected tenant THEN it prints 'error: no active ima...

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-59ce4fbd | Req 1.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-81db0c61 | Req 1.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-041d227d | Req 1.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-bfe27132 | Req 1.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-cf987871 | Req 2.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-8610aa4b | Req 2.2 | pass | pass | accepted by human: main.py:335 passes _read_tenant() to run_dream; dreaming.py:1066-1083 dreams each active tenant separately and prints total(); --tenant T runs only T (a CliRunner probe: --tenant acme dream made only acme links) |
| C-92f6541b | Req 2.3 | pass | pass | accepted by human: tenant nope search / summary-jobs / image-jobs exit 0 with empty results (test_cli_tenancy.py 179-185, 440-442, 480-482; confirmed by a CliRunner probe) |
| C-b86d1447 | Req 2.4 | pass | pass | accepted by human: _check_write_tenant (main.py:102) runs before any store work in add, ingest, note, summary-put, image-caption-put and vision-run (main.py:263, 485, 1248, 1369, 1488, 1534); dream gets the check from run_dream (dreaming.py:1076-1079); all exit 1 for a missing or inactive tenant |
| C-20bd1e63 | Req 3.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-7760785e | Req 3.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-c35d15c6 | Req 4.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-58023183 | Req 4.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-8e7b8062 | Req 5.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-5dc41637 | Req 5.2 | pass | pass | accepted by human: the tenant check precedes every write; 14 refused writes left memories, concept links and summaries unchanged (probe); tests 204, 245-249, 311-315, 448-451 |
| C-a79e558d | Req 6.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-46c6afc8 | Req 6.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-f10d86d5 | Req 6.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-17c1d2d1 | Req 6.4 | pass | pass | accepted by human: test_missing_and_inactive_tenants_are_handled (test_cli_tenancy.py:170-206) asserts every clause (stderr text, no new row, the acme row still readable after deactivation) and passes |
| C-8fa7e2dd | Req 6.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-29450002 | Req 6.6 | pass | pass | accepted by human: ingest dedup is scoped to the write tenant (main.py:524-525); the test at 221-239 ends with rows [acme, global], which fails both if the repeat stored a row and if the acme copy suppressed the global one |
| C-f9c22bd5 | Req 6.7 | pass | pass | accepted by human: test 265-305 asserts the note is stamped acme, exactly one ANNOTATES link to the acme memory and none to the global one, and both the scoped and unscoped notes listings show it |
| C-fbe84147 | Req 6.8 | pass | pass | accepted by human: test 330-397 passes; a probe also confirmed --tenant acme dream made no global link, the unscoped dream added the global link, and no link crossed tenants |
| C-0459af16 | Req 6.9 | pass | pass | accepted by human: test 413-452 covers the jobs listing, the summary stored with tenant_id acme, and --tenant nope summary-jobs giving [] with exit 0 |
| C-5cf1ac32 | Req 6.10 | fail | fail | rejected by human: R6.10 (requirements.md:171) requires exit 1; main.py:1497-1498 turns the KeyError into typer.BadParameter (exit 2) and test_cli_tenancy.py:500 asserts only != 0. WHEN image-caption-put is given an id or path with no active image file-record in the selected tenant THEN it prints 'e... |
| C-a9f24733 | Req 6.11 | pass | pass | accepted by human: test 522-555 asserts the recorded tenant_id == acme and that --tenant nope vision-run and image-caption-put both exit 1 with 'not found' |
| C-dc6d50e5 | Req 6.12 | pass | pass | the judge passed it and a discriminating test passes |
| C-74d42dd9 | Req 6.13 | pass | pass | the judge passed it and a discriminating test passes |
| C-769977e3 | Req 6.14 | pass | pass | the judge passed it and a discriminating test passes |
| C-88762101 | Req 7.1 | pass | pass | the judge passed it and a discriminating test passes |
- C-5cf1ac32: counterexample unexecuted (not executed in M0: the verifier worktree is M1 (verifier 1.5))

## Findings

- [minor, deterministic] a test is ignored as evidence (criterion C-cf987871): packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-cf987871): packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant: it traces 6 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-cf987871): packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-cf987871): packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-cf987871): packages.cli.tests.test_cli_tenancy::test_note_and_notes_are_tenant_scoped: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-cf987871): packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant: it traces 6 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-cf987871): packages.cli.tests.test_cli_tenancy::test_vision_run_and_caption_put_use_the_write_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-8610aa4b): packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-92f6541b): packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant: it traces 6 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-92f6541b): packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-92f6541b): packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant: it traces 6 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-b86d1447): packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant: it traces 6 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-b86d1447): packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-b86d1447): packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-b86d1447): packages.cli.tests.test_cli_tenancy::test_note_and_notes_are_tenant_scoped: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-b86d1447): packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant: it traces 6 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-b86d1447): packages.cli.tests.test_cli_tenancy::test_vision_run_and_caption_put_use_the_write_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-8e7b8062): packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-8e7b8062): packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-5dc41637): packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant: it traces 6 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-5dc41637): packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-5dc41637): packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-5dc41637): packages.cli.tests.test_cli_tenancy::test_note_and_notes_are_tenant_scoped: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-5dc41637): packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant: it traces 6 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-5dc41637): packages.cli.tests.test_cli_tenancy::test_vision_run_and_caption_put_use_the_write_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-46c6afc8): packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-46c6afc8): packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant: it traces 6 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-46c6afc8): packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-46c6afc8): packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-46c6afc8): packages.cli.tests.test_cli_tenancy::test_note_and_notes_are_tenant_scoped: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-46c6afc8): packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant: it traces 6 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-46c6afc8): packages.cli.tests.test_cli_tenancy::test_vision_run_and_caption_put_use_the_write_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-17c1d2d1): packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled: it traces 7 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-29450002): packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-f9c22bd5): packages.cli.tests.test_cli_tenancy::test_note_and_notes_are_tenant_scoped: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-fbe84147): packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-0459af16): packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant: it traces 6 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-5cf1ac32): packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant: it traces 6 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-a9f24733): packages.cli.tests.test_cli_tenancy::test_vision_run_and_caption_put_use_the_write_tenant: it traces 5 criteria (verifier.max_criteria_per_test=3)
- [major, human] Global image-caption-put exits 2, not 1 (spec gap) (criterion C-5cf1ac32): R6.10 requires exit 1 for a global image-caption-put on a tenant image. The code keeps the BadParameter path (exit 2) and the test was loosened to != 0. [rejected by human (R6.10 (requirements.md:171) requires exit 1; main.py:1497-1498 turns the KeyError into typer.BadParameter (exit 2) and test_cli_tenancy.py:500 asserts only != 0. WHEN image-caption-put is given an id or path with no active image file-record in the selected tenant THEN it prints 'error: no active image file-record found ...' to stderr and exits 1.)]
- [minor, judge] tenant list prints an extra count line (spec gap) (criterion C-c35d15c6): Table output adds a '[dim]N tenant(s)[/dim]' line that the spec does not mention.

## Fix unit

Fix unit 1 is created for these tasks:
- F-2192b892 Global image-caption-put exits 2, not 1

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.cli.tests.test_cli_tenancy::test_add_search_and_stats_use_the_selected_tenant` (task 2): passed
- `packages.cli.tests.test_cli_tenancy::test_docs_commands_are_read_tenant_scoped` (task 2): passed
- `packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant` (task 2): passed
- `packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant` (task 2): passed
- `packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant` (task 2): passed
- `packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled` (task 2): passed
- `packages.cli.tests.test_cli_tenancy::test_note_and_notes_are_tenant_scoped` (task 2): passed
- `packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant` (task 2): passed
- `packages.cli.tests.test_cli_tenancy::test_tenant_create_reports_created_again_and_invalid_ids` (task 3): passed
- `packages.cli.tests.test_cli_tenancy::test_tenant_list_reports_fresh_global_and_created_tenants` (task 3): passed
- `packages.cli.tests.test_cli_tenancy::test_valid_tenant_option_does_not_change_the_tenant_directory` (task 3): passed
- `packages.cli.tests.test_cli_tenancy::test_vision_run_and_caption_put_use_the_write_tenant` (task 2): passed
- `packages.cli.tests.test_cli_tenancy_gate::test_gate_full_cli_tenancy_flow_and_coverage_floor` (task 5): passed
- `packages.cli.tests.test_cli_tenancy_root::test_doctor_refuses_a_named_tenant` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_help_documents_the_tenant_option` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_history_refuses_a_named_tenant` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_index_tree_refuses_a_named_tenant` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_invalid_tenant_is_rejected_before_any_command` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_mcp_serve_refuses_a_named_tenant` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_migrate_storage_refuses_a_named_tenant` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_refusals_and_validation_happen_before_the_command` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_serve_refuses_a_named_tenant_but_runs_unscoped` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_tenant_migration_error_is_reported` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_tenant_not_found_from_a_write_is_reported` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_tenant_option_goes_before_the_command` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_tenant_scope_maps_absent_empty_global_and_named` (task 1): passed
- `packages.cli.tests.test_cli_tenancy_root::test_valid_tenant_does_not_change_the_tenant_directory` (task 1): passed
- `tests.integration.test_tenancy_cli::test_cli_tenancy_sequence_on_one_sqlite_file` (task 4): passed
