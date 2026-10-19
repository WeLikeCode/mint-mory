# Verification: kiro:multi-tenancy: PASS (round 2)

traceability: 35/36 criteria covered by a discriminating test

- Base: `b956492330760c0aa94f022b598e7ffad24ceef8`
- Head: `c4777739bbe278f854a9c02fc6b413b3b5d2d24f`
- Implementer profiles: deepseek, deepseek-free, glm-free, glm
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `3f658e9ef4d47bbf15907180dbe007ee5d8ee44763de66f0cb326158c4059b9a`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), deepseek-free deepseek (declared), glm-free zhipu (declared), glm zhipu (declared)
- Cost: $0.7446

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | reused | 0.0 | reused (round 1) |
| 1 | integrity | reused | 0.0 | reused (round 1) |
| 2 | build | reused | 0.0 | reused (round 1) |
| 3 | tests | reused | 0.0 | reused (round 1) |
| 4 | traceability | reused | 0.0 | reused (round 1) |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | reused | 0.0 | reused (round 1) |
| 8 | s1 judge | reused | 0.0 | reused (round 1) |
| 9 | judge | reused | 0.0 | reused (round 1) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261019T1722Z-e4be/026-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261019T1722Z-e4be/027-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261019T1722Z-e4be/028-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261019T1722Z-e4be/029-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261019T1722Z-e4be/030-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 11 test file(s) compared with the base |
| red-green freeze | ok | 7 task(s): red and green compared (+1 unfrozen by human answers) |
| test path freeze | ok | 7 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 8 task(s); red tests passing at head: step 3 |

## Tests unfrozen by human answers (allowed, L4-IMP-002)

- packages/core/tests/test_tenant_directory.py (task 5, unfrozen by Q-001 (human))

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-0a1cfe6b | Req 1.1 | covered | packages.core.tests.test_tenant_types::test_tenant_constants_match_the_contract (passed, zero_value); packages.core.tests.test_tenant_types::test_validate_tenant_id_rejects_invalid_ids (passed, zero_value); packages.core.tests.test_tenant_types::test_validate_tenant_id_returns_valid_ids_unchanged (p... | - | 0.94 |
| C-edc43a92 | Req 1.2 | covered | packages.core.tests.test_tenant_types::test_tenant_model_defaults (passed, zero_value); packages.core.tests.test_tenant_types::test_tenant_model_validates_id (passed, zero_value) | - | 0.88 |
| C-ee05ebb1 | Req 1.3 | covered | packages.core.tests.test_tenant_types::test_cross_tenant_link_error_message_and_attributes (passed, zero_value); packages.core.tests.test_tenant_types::test_invalid_tenant_id_error_message_and_attribute (passed, zero_value); packages.core.tests.test_tenant_types::test_protected_tenant_error_message ... | - | 0.93 |
| C-bdfc8484 | Req 1.4 | covered | packages.core.tests.test_tenant_types::test_concept_link_tenant_default_and_validation (passed, zero_value); packages.core.tests.test_tenant_types::test_core_request_models_keep_no_tenant_field (passed, zero_value); packages.core.tests.test_tenant_types::test_http_request_bodies_gain_no_tenant_field... | - | 0.89 |
| C-59ef9e7c | Req 1.5 | covered | packages.core.tests.test_tenant_types::test_core_request_models_keep_no_tenant_field (passed, zero_value); packages.core.tests.test_tenant_types::test_http_request_bodies_gain_no_tenant_field (passed, zero_value) | - | 0.89 |
| C-b3eb1490 | Req 2.1 | covered | packages.core.tests.test_tenant_schema::test_fresh_schema_creates_and_seeds_tenants (passed, zero_value); packages.core.tests.test_tenant_schema::test_tenants_table_is_created_before_memories_and_reseed_is_idempotent (passed, zero_value) | - | 0.95 |
| C-90e130ca | Req 2.2 | covered | packages.core.tests.test_tenant_schema::test_six_tables_have_tenant_id_as_last_column (passed, zero_value) | - | 0.92 |
| C-b6f54c67 | Req 2.3 | covered | packages.core.tests.test_tenant_schema::test_concept_links_uniqueness_is_per_tenant (passed, zero_value); packages.core.tests.test_tenant_schema::test_index_manifest_primary_key_is_tenant_and_path (passed, zero_value); packages.core.tests.test_tenant_schema::test_memory_summaries_unique_per_tenant_c... | - | 0.93 |
| C-d0373dab | Req 2.4 | covered | packages.core.tests.test_tenant_schema::test_schema_sql_declares_no_index_over_tenant_id (passed, zero_value) | - | 0.90 |
| C-c842fbe1 | Req 2.5 | covered | packages.core.tests.test_tenant_schema::test_fts_and_trigram_triggers_stay_unchanged (passed, zero_value) | - | 0.87 |
| C-879ba6ee | Req 3.1 | covered | packages.core.tests.test_tenant_migration::test_initialise_runs_tenant_migration_after_index_mode_vision (passed, zero_value) | - | 0.88 |
| C-e80f6d60 | Req 3.2 | covered | packages.core.tests.test_tenant_migration::test_plan_adds_columns_before_rebuilds_before_indexes (passed, zero_value); packages.core.tests.test_tenant_migration::test_plan_right_after_schema_on_a_new_file_is_the_three_tenant_indexes (passed, zero_value); packages.core.tests.test_tenant_migration::te... | - | - |
| C-557d75d1 | Req 3.3 | covered | packages.core.tests.test_tenant_migration::test_ensure_tenant_columns_executes_nothing_when_the_second_plan_is_empty (passed, zero_value); packages.core.tests.test_tenant_migration::test_ensure_tenant_columns_recomputes_the_plan_inside_the_transaction (passed, zero_value); packages.core.tests.test_t... | - | 0.90 |
| C-44253807 | Req 3.4 | covered | packages.core.tests.test_tenant_migration::test_failed_migration_rolls_back_and_raises_tenant_migration_error (passed, zero_value) | - | 0.88 |
| C-00ad76d3 | Req 3.5 | covered | packages.core.tests.test_tenant_migration::test_pre_tenancy_database_migrates_rows_and_matches_a_fresh_database (passed, zero_value); packages.core.tests.test_tenant_migration::test_second_initialise_returns_an_empty_plan_and_changes_no_schema (passed, zero_value) | - | 0.93 |
| C-2710c07f | Req 3.6 | covered | packages.core.tests.test_tenant_migration::test_pre_tenancy_database_migrates_rows_and_matches_a_fresh_database (passed, zero_value) | - | 0.89 |
| C-c9473b02 | Req 3.7 | covered | packages.core.tests.test_tenant_migration::test_failed_migration_rolls_back_and_raises_tenant_migration_error (passed, zero_value) | - | 0.92 |
| C-b58c85ff | Req 3.8 | covered | packages.core.tests.test_tenant_migration::test_concurrent_start_recomputes_the_plan_inside_the_transaction (passed, zero_value) | - | 0.91 |
| C-970f835b | Req 4.1 | covered | packages.core.tests.test_tenant_persistence::test_update_memory_does_not_write_tenant_id (passed, red_assertion) | packages.core.tests.test_tenant_persistence::test_memory_tenant_id_persists_and_round_trips (it traces 4 criteria (verifier.max_criteria_per_test=3)) | 0.78 |
| C-5939ff59 | Req 4.2 | covered | packages.core.tests.test_tenant_persistence::test_link_tenant_id_persists_and_round_trips (passed, red_assertion); packages.core.tests.test_tenant_persistence::test_session_and_query_result_tenant_id_persist (passed, red_assertion) | packages.core.tests.test_tenant_persistence::test_memory_tenant_id_persists_and_round_trips (it traces 4 criteria (verifier.max_criteria_per_test=3)) | 0.92 |
| C-619bc1e6 | Req 4.3 | covered | packages.core.tests.test_tenant_keys::test_get_summary_filters_by_tenant (passed, zero_value) | - | 0.81 |
| C-a41e591b | Req 4.4 | covered | packages.core.tests.test_tenant_keys::test_upsert_summary_keys_by_tenant_and_concept (passed, zero_value) | - | 0.91 |
| C-5b9008af | Req 4.5 | covered | packages.core.tests.test_tenant_keys::test_manifest_entry_carries_tenant_id (passed, zero_value); packages.core.tests.test_tenant_keys::test_manifest_methods_scope_to_tenant (passed, zero_value) | - | 0.88 |
| C-877680dc | Req 4.6 | uncovered | - | packages.core.tests.test_tenant_persistence::test_memory_tenant_id_persists_and_round_trips (it traces 4 criteria (verifier.max_criteria_per_test=3)) | 0.07 |
| C-03910be6 | Req 4.7 | covered | packages.core.tests.test_tenant_persistence::test_tenant_writes_target_an_existing_directory_row (passed, red_assertion) | packages.core.tests.test_tenant_persistence::test_memory_tenant_id_persists_and_round_trips (it traces 4 criteria (verifier.max_criteria_per_test=3)) | 0.13 |
| C-13c99d09 | Req 5.1 | covered | packages.core.tests.test_tenant_directory::test_create_tenant_defaults_name_to_empty (passed, zero_value); packages.core.tests.test_tenant_directory::test_create_tenant_from_two_backends_leaves_one_row (passed, zero_value); packages.core.tests.test_tenant_directory::test_create_tenant_is_idempotent_... | - | 0.94 |
| C-ef053fe0 | Req 5.2 | covered | packages.core.tests.test_tenant_directory::test_get_tenant_reads_inactive_flag (passed, zero_value); packages.core.tests.test_tenant_directory::test_get_tenant_returns_none_for_unknown_or_invalid_id (passed, zero_value); packages.core.tests.test_tenant_directory::test_get_tenant_returns_stored_tenan... | - | 0.90 |
| C-e39615c9 | Req 5.3 | covered | packages.core.tests.test_tenant_directory::test_list_tenants_on_fresh_database_returns_only_global (passed, zero_value); packages.core.tests.test_tenant_directory::test_list_tenants_orders_all_tenants_by_id (passed, zero_value); packages.core.tests.test_tenant_directory::test_seeded_global_row_has_s... | - | 0.92 |
| C-0df6c3f3 | Req 5.4 | covered | packages.core.tests.test_tenant_directory::test_set_tenant_active_can_reactivate (passed, zero_value); packages.core.tests.test_tenant_directory::test_set_tenant_active_cannot_deactivate_global (passed, zero_value); packages.core.tests.test_tenant_directory::test_set_tenant_active_global_true_return... | - | 0.93 |
| C-c089869a | Req 5.5 | covered | packages.core.tests.test_tenant_directory::test_seeded_global_row_has_sentinel_fields_and_timestamps (passed, zero_value) | - | 0.85 |
| C-eed56474 | Req 6.1 | covered | packages.core.tests.test_pg_tenancy::test_protocol_declares_tenant_directory_methods (passed, zero_value); packages.core.tests.test_pg_tenancy::test_protocol_tenant_signatures_and_manifest_entry (passed, zero_value) | - | 0.92 |
| C-a7f825e4 | Req 6.2 | covered | packages.core.tests.test_pg_tenancy::test_pg_add_link_tenancy (passed, zero_value); packages.core.tests.test_pg_tenancy::test_pg_add_memory_tenancy (passed, zero_value); packages.core.tests.test_pg_tenancy::test_pg_create_session_tenancy (passed, zero_value); packages.core.tests.test_pg_tenancy::tes... | - | - |
| C-0e897873 | Req 6.3 | covered | packages.core.tests.test_pg_tenancy::test_pg_add_link_tenancy (passed, zero_value); packages.core.tests.test_pg_tenancy::test_pg_add_memory_tenancy (passed, zero_value); packages.core.tests.test_pg_tenancy::test_pg_create_session_tenancy (passed, zero_value); packages.core.tests.test_pg_tenancy::tes... | - | - |
| C-27174f33 | Req 7.1 | covered | packages.core.tests.test_tenant_schema_gate::test_schema_gate_asserts_exactly_one_global_tenant_row (passed, red_assertion); packages.core.tests.test_tenant_schema_gate::test_schema_gate_lists_tenants_and_tenant_id_columns (passed, red_assertion); packages.core.tests.test_tenant_schema_gate::test_sc... | - | 0.79 |
| C-58364fba | Req 7.2 | covered | packages.core.tests.test_openapi_tenancy::test_openapi_response_schemas_declare_tenant_id (passed, red_assertion); packages.core.tests.test_openapi_tenancy::test_openapi_tenant_id_is_only_on_the_four_response_schemas (passed, red_assertion) | - | 0.90 |
| C-d424e27b | Req 8.1 | covered | packages.core.tests.test_tenant_full_gate::test_full_gate_config_declares_every_required_gate (passed, pre_satisfied); packages.core.tests.test_tenant_full_gate::test_full_gate_lint_and_typecheck_commands_pass (passed, pre_satisfied); packages.core.tests.test_tenant_full_gate::test_full_gate_tenant_... | - | 0.80 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `.kiro/specs/multi-tenancy/.l4/ledger/r-20261019T1234Z-49e3.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy/.l4/ledger/r-20261019T1436Z-22a5.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy/.l4/ledger/r-20261019T1437Z-76f9.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy/.l4/ledger/r-20261019T1645Z-97d7.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy/.l4/ledger/r-20261019T1722Z-e4be.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy/questions.md` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `docs/openapi/mintmory.yaml` |  | none | exempt: harness, spec or documentation path |
| `packages/core/src/mintmory/core/ports.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/schema.sql` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/storage.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/storage_postgres.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/types.py` | core | relevant | named in the spec |
| `packages/core/tests/fixtures/pre_tenancy_schema.sql` |  | relevant | new test file |
| `packages/core/tests/test_openapi_tenancy.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_tenancy.py` |  | relevant | new test file |
| `packages/core/tests/test_schema.py` |  | relevant | named in the spec |
| `packages/core/tests/test_tenant_directory.py` |  | relevant | new test file |
| `packages/core/tests/test_tenant_full_gate.py` |  | relevant | new test file |
| `packages/core/tests/test_tenant_keys.py` |  | relevant | new test file |
| `packages/core/tests/test_tenant_migration.py` |  | relevant | new test file |
| `packages/core/tests/test_tenant_persistence.py` |  | relevant | new test file |
| `packages/core/tests/test_tenant_schema.py` |  | relevant | new test file |
| `packages/core/tests/test_tenant_schema_gate.py` |  | relevant | new test file |
| `packages/core/tests/test_tenant_types.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

2062 of 2176 passed, 0 failed, 0 errored, 114 skipped.
90 of 90 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-0a1cfe6b | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-edc43a92 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ee05ebb1 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-bdfc8484 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-59ef9e7c | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b3eb1490 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-90e130ca | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b6f54c67 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d0373dab | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c842fbe1 | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-879ba6ee | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e80f6d60 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-557d75d1 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-44253807 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-00ad76d3 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2710c07f | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c9473b02 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b58c85ff | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-970f835b | ok | 0.780 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5939ff59 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-619bc1e6 | ok | 0.810 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a41e591b | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5b9008af | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-877680dc | ok | 0.070 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-03910be6 | ok | 0.130 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-13c99d09 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ef053fe0 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e39615c9 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0df6c3f3 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c089869a | ok | 0.850 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-eed56474 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a7f825e4 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-0e897873 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-27174f33 | ok | 0.790 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-58364fba | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d424e27b | ok | 0.800 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Human verdicts

- Q-003 accept C-877680dc by human: Req 4.6 is an invariant over the existing suite. The tests gate ran the whole suite green in round 1 (step 3 ok), and the only pre-existing test file the unit changed is packages/core/tests/test_schema.py, with 65 added lines and none removed: the R7.1 additions accepted in Q-002. No other existing ...
- Q-004 accept H-e0757174 by human: the cut fell inside test files only. The judge's diff after the harness exclusions is 158,407 characters; every production file (ports.py, schema.sql, storage.py, storage_postgres.py, types.py, the OpenAPI yaml) and the pre-tenancy fixture lie before 120,000 and were judged. The unseen part is the t...

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-0a1cfe6b | Req 1.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-edc43a92 | Req 1.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-ee05ebb1 | Req 1.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-bdfc8484 | Req 1.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-59ef9e7c | Req 1.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-b3eb1490 | Req 2.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-90e130ca | Req 2.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-b6f54c67 | Req 2.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-d0373dab | Req 2.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-c842fbe1 | Req 2.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-879ba6ee | Req 3.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-e80f6d60 | Req 3.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-557d75d1 | Req 3.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-44253807 | Req 3.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-00ad76d3 | Req 3.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-2710c07f | Req 3.6 | pass | pass | the judge passed it and a discriminating test passes |
| C-c9473b02 | Req 3.7 | pass | pass | the judge passed it and a discriminating test passes |
| C-b58c85ff | Req 3.8 | pass | pass | the judge passed it and a discriminating test passes |
| C-970f835b | Req 4.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-5939ff59 | Req 4.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-619bc1e6 | Req 4.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-a41e591b | Req 4.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-5b9008af | Req 4.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-877680dc | Req 4.6 | pass | pass | accepted by human: Req 4.6 is an invariant over the existing suite. The tests gate ran the whole suite green in round 1 (step 3 ok), and the only pre-existing test file the unit changed is packages/core/tests/test_schema.py, with 65 added lines and none removed: the R7.1 additions accepted in Q-002.... |
| C-03910be6 | Req 4.7 | pass | pass | the judge passed it and a discriminating test passes |
| C-13c99d09 | Req 5.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-ef053fe0 | Req 5.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-e39615c9 | Req 5.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-0df6c3f3 | Req 5.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-c089869a | Req 5.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-eed56474 | Req 6.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-a7f825e4 | Req 6.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-0e897873 | Req 6.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-27174f33 | Req 7.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-58364fba | Req 7.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-d424e27b | Req 8.1 | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, deterministic] a test is ignored as evidence (criterion C-970f835b): packages.core.tests.test_tenant_persistence::test_memory_tenant_id_persists_and_round_trips: it traces 4 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-5939ff59): packages.core.tests.test_tenant_persistence::test_memory_tenant_id_persists_and_round_trips: it traces 4 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-877680dc): packages.core.tests.test_tenant_persistence::test_memory_tenant_id_persists_and_round_trips: it traces 4 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-03910be6): packages.core.tests.test_tenant_persistence::test_memory_tenant_id_persists_and_round_trips: it traces 4 criteria (verifier.max_criteria_per_test=3)
- [minor, judge] Postgres get_tenant with invalid id (spec gap) (criterion C-a7f825e4): PostgresBackend.get_tenant returns None for any non-'global' id including invalid ones; unpinned but consistent.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.core.tests.test_openapi_tenancy::test_openapi_response_schemas_declare_tenant_id` (task 7): passed
- `packages.core.tests.test_openapi_tenancy::test_openapi_tenant_id_is_only_on_the_four_response_schemas` (task 7): passed
- `packages.core.tests.test_pg_tenancy::test_pg_add_link_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_add_memory_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_create_session_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_create_tenant_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_summary_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_tenant_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_list_tenants_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_manifest_delete_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_manifest_get_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_manifest_paths_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_manifest_upsert_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_record_query_results_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_require_global_tenant_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_set_tenant_active_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_upsert_summary_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_protocol_declares_tenant_directory_methods` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_protocol_tenant_signatures_and_manifest_entry` (task 6): passed
- `packages.core.tests.test_tenant_directory::test_create_tenant_defaults_name_to_empty` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_create_tenant_from_two_backends_leaves_one_row` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_create_tenant_is_idempotent_and_keeps_existing_name` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_create_tenant_persists_and_returns_stored_row` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_create_tenant_validates_id_before_inserting` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_get_tenant_reads_inactive_flag` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_get_tenant_returns_none_for_unknown_or_invalid_id` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_get_tenant_returns_stored_tenant` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_list_tenants_on_fresh_database_returns_only_global` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_list_tenants_orders_all_tenants_by_id` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_seeded_global_row_has_sentinel_fields_and_timestamps` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_set_tenant_active_can_reactivate` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_set_tenant_active_cannot_deactivate_global` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_set_tenant_active_global_true_returns_unchanged` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_set_tenant_active_invalid_id_is_unknown` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_set_tenant_active_unknown_id_raises_not_found` (task 5): passed
- `packages.core.tests.test_tenant_directory::test_set_tenant_active_updates_flag_and_timestamp` (task 5): passed
- `packages.core.tests.test_tenant_full_gate::test_full_gate_config_declares_every_required_gate` (task 8): passed
- `packages.core.tests.test_tenant_full_gate::test_full_gate_lint_and_typecheck_commands_pass` (task 8): passed
- `packages.core.tests.test_tenant_full_gate::test_full_gate_tenant_foundation_round_trips` (task 8): passed
- `packages.core.tests.test_tenant_keys::test_get_summary_filters_by_tenant` (task 2): passed
- `packages.core.tests.test_tenant_keys::test_manifest_entry_carries_tenant_id` (task 2): passed
- `packages.core.tests.test_tenant_keys::test_manifest_methods_scope_to_tenant` (task 2): passed
- `packages.core.tests.test_tenant_keys::test_upsert_summary_keys_by_tenant_and_concept` (task 2): passed
- `packages.core.tests.test_tenant_migration::test_concurrent_start_recomputes_the_plan_inside_the_transaction` (task 3): passed
- `packages.core.tests.test_tenant_migration::test_ensure_tenant_columns_executes_nothing_when_the_second_plan_is_empty` (task 3): passed
- `packages.core.tests.test_tenant_migration::test_ensure_tenant_columns_recomputes_the_plan_inside_the_transaction` (task 3): passed
- `packages.core.tests.test_tenant_migration::test_ensure_tenant_columns_returns_on_an_empty_plan_without_a_transaction` (task 3): passed
- `packages.core.tests.test_tenant_migration::test_failed_migration_rolls_back_and_raises_tenant_migration_error` (task 3): passed
- `packages.core.tests.test_tenant_migration::test_initialise_runs_tenant_migration_after_index_mode_vision` (task 3): passed
- `packages.core.tests.test_tenant_migration::test_plan_adds_columns_before_rebuilds_before_indexes` (task 3): passed

## Guard events

- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage_postgres.py
- guard.violation: packages/core/src/mintmory/core/storage_postgres.py
- guard.violation: packages/core/src/mintmory/core/storage_postgres.py
- guard.violation: packages/core/src/mintmory/core/storage_postgres.py
- guard.violation: packages/core/src/mintmory/core/storage_postgres.py
- guard.violation: packages/core/src/mintmory/core/storage_postgres.py
- guard.violation: packages/core/src/mintmory/core/storage_postgres.py
- guard.violation: packages/core/src/mintmory/core/storage_postgres.py
- guard.violation: packages/core/src/mintmory/core/storage_postgres.py
- guard.violation: packages/core/src/mintmory/core/storage_postgres.py
- guard.test_tamper: packages/core/tests/test_schema.py
