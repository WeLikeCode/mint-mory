# Verification: kiro:multi-tenancy-postgres: PASS (round 1)

traceability: 23/23 criteria covered by a discriminating test

- Base: `bc8df7cc8b253b845be2786229014df03114b384`
- Head: `eb30775c1f826736d0c46bf1aecf04a710f722f2`
- Implementer profiles: glm, glm-free, deepseek
- Judge: claude-judge (claude-sonnet-5-5), 2 call(s), prompt sha256 `f8677470a9fd2179a9a99d5874dbdac3cea2c7b85b13b58a21309f034a5ce010`
- Judge replies of claude-judge (this unit, all rounds): valid 0, repaired 0, retried 1, discarded 0; this round: retried
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), glm zhipu (declared), glm-free zhipu (declared), deepseek deepseek (declared)
- Cost: $1.5484

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.0 | base staging@bc8df7cc8b contained |
| 1 | integrity | ok | 278.2 | 10 sub-checks (+1 unfrozen by human answers); scope: 16 changed file(s) |
| 2 | build | ok | 7.1 |  |
| 3 | tests | ok | 127.7 |  |
| 4 | traceability | ok | 0.2 | 23/23 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 1.4 | 17/23 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 45.1 | 2 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261021T1611Z-9810/113-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261021T1611Z-9810/114-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261021T1611Z-9810/115-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261021T1611Z-9810/116-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261021T1611Z-9810/117-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 7 test file(s) compared with the base |
| red-green freeze | ok | 5 task(s): red and green compared (+1 unfrozen by human answers) |
| test path freeze | ok | 5 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 6 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2396 of 2396 base tests pass on the unit's code with its 6 test and support files at the base (base: base worktree) |

## Pre-existing tests changed with an allowance (L4-VER-031)

- packages/core/tests/pg_fakes.py kept at head for the run (task 1: unfrozen by Q-001)

## Tests unfrozen by human answers (allowed, L4-IMP-002)

- packages/core/tests/pg_fakes.py (task 1, unfrozen by Q-001 (human))

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-68b825d2 | Req 1.1 | covered | packages.core.tests.test_pg_schema::test_pg_schema_creates_and_seeds_tenants_before_memories (passed, red_assertion) | - | 0.70 |
| C-289a314a | Req 1.2 | covered | packages.core.tests.test_pg_schema::test_pg_schema_declares_no_tenant_index_and_keeps_fts_and_trigram (passed, red_assertion); packages.core.tests.test_pg_schema::test_pg_schema_six_tables_declare_tenant_id_reference (passed, red_assertion) | - | 0.92 |
| C-7ab96287 | Req 1.3 | covered | packages.core.tests.test_pg_schema::test_pg_schema_tenant_keys_replace_global_keys (passed, red_assertion) | - | 0.73 |
| C-d01718dd | Req 1.4 | covered | packages.core.tests.test_pg_schema::test_pg_schema_declares_no_tenant_index_and_keeps_fts_and_trigram (passed, red_assertion) | - | 0.92 |
| C-2623c583 | Req 1.5 | covered | packages.core.tests.test_pg_schema::test_pg_schema_parses_every_create_table_block (passed, red_assertion) | - | 0.90 |
| C-3b4448d0 | Req 2.1 | covered | packages.core.tests.test_pg_tenant_migration::test_plan_migrated_snapshot_is_empty_and_old_keys_with_columns_are_partial (passed, zero_value); packages.core.tests.test_pg_tenant_migration::test_plan_missing_key_entries_add_new_keys_without_dropping_anything (passed, zero_value); packages.core.tests.... | - | - |
| C-38951bfc | Req 2.2 | covered | packages.core.tests.test_pg_tenant_migration::test_ensure_tenant_columns_reads_the_catalog_and_executes_the_plan (passed, zero_value); packages.core.tests.test_pg_tenant_migration::test_initialise_runs_ddl_catalog_and_plan_in_the_advisory_locked_transaction (passed, zero_value); packages.core.tests.... | - | - |
| C-8b92f6fb | Req 2.3 | covered | packages.core.tests.test_pg_tenant_migration::test_initialise_wraps_catalog_failures_but_propagates_lock_failures (passed, zero_value); packages.core.tests.test_pg_tenant_migration::test_initialise_wraps_migration_failures_and_rolls_back (passed, zero_value) | - | 0.91 |
| C-e1fe91f9 | Req 2.4 | covered | packages.core.tests.test_pg_tenant_migration::test_initialise_runs_ddl_catalog_and_plan_in_the_advisory_locked_transaction (passed, zero_value); packages.core.tests.test_pg_tenant_migration::test_pg_catalog_snapshot_turns_dict_rows_into_plan_inputs (passed, zero_value); packages.core.tests.test_pg_t... | - | - |
| C-73647c35 | Req 3.1 | covered | packages.core.tests.test_pg_tenancy_columns::test_add_link_insert_includes_tenant_id (passed, red_assertion); packages.core.tests.test_pg_tenancy_columns::test_add_memory_insert_includes_tenant_id (passed, red_assertion); packages.core.tests.test_pg_tenancy_columns::test_create_session_insert_includ... | - | - |
| C-faabc87f | Req 3.2 | covered | packages.core.tests.test_pg_tenancy_columns::test_add_link_conflict_target_is_per_tenant (passed, red_assertion); packages.core.tests.test_pg_tenancy_columns::test_get_summary_looks_up_by_concept_and_tenant (passed, red_assertion); packages.core.tests.test_pg_tenancy_columns::test_manifest_delete_fi... | - | 0.93 |
| C-d4a710f6 | Req 3.3 | covered | packages.core.tests.test_pg_tenancy_columns::test_guards_stay_on_record_writes_and_keyed_methods_before_pool_access (passed, red_assertion) | - | 0.87 |
| C-536811bb | Req 3.4 | covered | packages.core.tests.test_pg_tenancy_columns::test_truncate_all_deletes_non_global_tenants_after_the_truncate (passed, red_assertion) | - | 0.79 |
| C-9a6d3abf | Req 3.5 | covered | packages.core.tests.test_pg_tenancy_columns::test_add_link_conflict_target_is_per_tenant (passed, red_assertion); packages.core.tests.test_pg_tenancy_columns::test_add_link_insert_includes_tenant_id (passed, red_assertion); packages.core.tests.test_pg_tenancy_columns::test_add_memory_insert_includes... | - | - |
| C-457d193a | Req 4.1 | covered | packages.core.tests.test_migrate_tenancy::test_checksums_include_tenant_id (passed, zero_value); packages.core.tests.test_migrate_tenancy::test_fk_order_starts_with_tenants (passed, zero_value); packages.core.tests.test_migrate_tenancy::test_index_manifest_primary_key_is_per_tenant (passed, zero_val... | - | 0.92 |
| C-2eb283b3 | Req 4.2 | covered | packages.core.tests.test_migrate_tenancy::test_insert_concept_links_batch_carries_tenant_id_and_per_tenant_conflict (passed, zero_value); packages.core.tests.test_migrate_tenancy::test_insert_index_manifest_batch_carries_tenant_id_and_per_tenant_conflict (passed, zero_value); packages.core.tests.tes... | - | 0.94 |
| C-d39187cd | Req 4.3 | covered | packages.core.tests.test_migrate_tenancy::test_insert_tenants_batch_dry_run_or_no_rows_writes_nothing (passed, zero_value); packages.core.tests.test_migrate_tenancy::test_insert_tenants_batch_sql_and_params (passed, zero_value); packages.core.tests.test_migrate_tenancy::test_pg_truncate_all_clears_t... | - | 0.89 |
| C-455cf2dc | Req 4.4 | covered | packages.core.tests.test_migrate_tenancy::test_pre_tenancy_source_raises_before_dry_run (passed, zero_value); packages.core.tests.test_migrate_tenancy::test_source_with_unknown_tenant_raises_before_dry_run (passed, zero_value) | - | 0.90 |
| C-fec13454 | Req 4.5 | covered | packages.core.tests.test_migrate_tenancy::test_checksums_include_tenant_id (passed, zero_value) | - | 0.92 |
| C-56611860 | Req 4.6 | covered | packages.core.tests.test_migrate_tenancy::test_checksums_include_tenant_id (passed, zero_value); packages.core.tests.test_migrate_tenancy::test_dry_run_lists_tenants_first_with_its_row_count (passed, zero_value); packages.core.tests.test_migrate_tenancy::test_insert_concept_links_batch_carries_tenan... | - | 0.93 |
| C-0a8c52fb | Req 5.1 | covered | packages.core.tests.test_pg_fakes::test_fake_connection_counts_commits_and_rollbacks (passed, red_assertion); packages.core.tests.test_pg_fakes::test_fake_connection_default_responder_returns_no_rows_and_armed_responder_does (passed, red_assertion); packages.core.tests.test_pg_fakes::test_fake_conne... | - | - |
| C-85f83635 | Req 6.1 | covered | packages.core.tests.test_pg_tenancy_gate::test_gate_config_declares_required_commands_and_coverage_floor (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_gate::test_gate_lint_and_typecheck_commands_pass (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_gate::test_postgres_gate... | - | 0.72 |
| C-40adad36 | Req 6.2 | covered | packages.core.tests.test_pg_tenancy_gate::test_initialise_first_start_adds_tenant_indexes_and_later_start_finds_none (passed, pre_satisfied) | - | 0.51 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `.kiro/specs/multi-tenancy-postgres/.l4/ledger/r-20261021T0822Z-f473.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres/.l4/ledger/r-20261021T0948Z-a2ec.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres/.l4/ledger/r-20261021T0949Z-2268.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres/.l4/ledger/r-20261021T1611Z-9810.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres/questions.md` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/core/src/mintmory/core/migrate.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/schema_postgres.sql` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/storage_postgres.py` | core | relevant | named in the spec |
| `packages/core/tests/pg_fakes.py` |  | relevant | new test file |
| `packages/core/tests/test_migrate_tenancy.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_fakes.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_schema.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_tenancy_columns.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_tenancy_gate.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_tenant_migration.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

2464 of 2578 passed, 0 failed, 0 errored, 114 skipped.
68 of 68 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-68b825d2 | ok | 0.700 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-289a314a | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7ab96287 | ok | 0.730 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d01718dd | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2623c583 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3b4448d0 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-38951bfc | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-8b92f6fb | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e1fe91f9 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-73647c35 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-faabc87f | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d4a710f6 | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-536811bb | ok | 0.790 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9a6d3abf | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-457d193a | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2eb283b3 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d39187cd | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-455cf2dc | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-fec13454 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-56611860 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0a8c52fb | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-85f83635 | ok | 0.720 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-40adad36 | ok | 0.510 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-68b825d2 | Req 1.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-289a314a | Req 1.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-7ab96287 | Req 1.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-d01718dd | Req 1.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-2623c583 | Req 1.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-3b4448d0 | Req 2.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-38951bfc | Req 2.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-8b92f6fb | Req 2.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-e1fe91f9 | Req 2.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-73647c35 | Req 3.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-faabc87f | Req 3.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-d4a710f6 | Req 3.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-536811bb | Req 3.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-9a6d3abf | Req 3.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-457d193a | Req 4.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-2eb283b3 | Req 4.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-d39187cd | Req 4.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-455cf2dc | Req 4.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-fec13454 | Req 4.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-56611860 | Req 4.6 | pass | pass | the judge passed it and a discriminating test passes |
| C-0a8c52fb | Req 5.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-85f83635 | Req 6.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-40adad36 | Req 6.2 | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Other _row_to_memory callers unverified (spec gap) (criterion C-73647c35): Only two JOIN selects were visibly updated to include tenant_id; other SELECTs feeding _row_to_memory are not shown and not tested with the fake pool.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.core.tests.test_migrate_tenancy::test_checksums_include_tenant_id` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_dry_run_lists_tenants_first_with_its_row_count` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_fk_order_starts_with_tenants` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_index_manifest_primary_key_is_per_tenant` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_insert_concept_links_batch_carries_tenant_id_and_per_tenant_conflict` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_insert_index_manifest_batch_carries_tenant_id_and_per_tenant_conflict` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_insert_memories_batch_carries_tenant_id` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_insert_memory_summaries_batch_carries_tenant_id` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_insert_query_results_batch_carries_tenant_id` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_insert_query_sessions_batch_carries_tenant_id` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_insert_tenants_batch_dry_run_or_no_rows_writes_nothing` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_insert_tenants_batch_sql_and_params` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_pg_truncate_all_clears_tenants_too` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_pre_tenancy_source_raises_before_dry_run` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_six_source_column_tuples_end_with_tenant_id` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_source_with_unknown_tenant_raises_before_dry_run` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_tenants_registered_in_table_insert_fn` (task 5): passed
- `packages.core.tests.test_migrate_tenancy::test_tenants_table_metadata_is_complete` (task 5): passed
- `packages.core.tests.test_pg_fakes::test_fake_connection_counts_commits_and_rollbacks` (task 1): passed
- `packages.core.tests.test_pg_fakes::test_fake_connection_default_responder_returns_no_rows_and_armed_responder_does` (task 1): passed
- `packages.core.tests.test_pg_fakes::test_fake_connection_execute_records_sql_and_params_and_returns_cursor` (task 1): passed
- `packages.core.tests.test_pg_fakes::test_fake_connection_fail_on_raises_after_recording_the_statement` (task 1): passed
- `packages.core.tests.test_pg_fakes::test_fake_connection_responder_rows_are_read_exactly_as_the_backend_reads_them` (task 1): passed
- `packages.core.tests.test_pg_fakes::test_fake_cursor_execute_records_in_owning_connection_and_ignores_row_factory` (task 1): passed
- `packages.core.tests.test_pg_fakes::test_fake_cursor_executemany_records_one_entry_per_parameter_set` (task 1): passed
- `packages.core.tests.test_pg_fakes::test_fake_cursor_reads_rows_and_is_a_context_manager` (task 1): passed
- `packages.core.tests.test_pg_fakes::test_fake_pool_close_does_nothing_and_the_pool_still_yields` (task 1): passed
- `packages.core.tests.test_pg_fakes::test_fake_pool_factory_makes_a_new_connection_per_checkout` (task 1): passed
- `packages.core.tests.test_pg_fakes::test_fake_pool_rolls_back_and_reraises_on_exception` (task 1): passed
- `packages.core.tests.test_pg_fakes::test_fake_pool_yields_given_connection_and_counts_checkouts` (task 1): passed
- `packages.core.tests.test_pg_schema::test_pg_schema_creates_and_seeds_tenants_before_memories` (task 2): passed
- `packages.core.tests.test_pg_schema::test_pg_schema_declares_no_tenant_index_and_keeps_fts_and_trigram` (task 2): passed
- `packages.core.tests.test_pg_schema::test_pg_schema_parses_every_create_table_block` (task 2): passed
- `packages.core.tests.test_pg_schema::test_pg_schema_six_tables_declare_tenant_id_reference` (task 2): passed
- `packages.core.tests.test_pg_schema::test_pg_schema_tenant_keys_replace_global_keys` (task 2): passed
- `packages.core.tests.test_pg_tenancy_columns::test_add_link_conflict_target_is_per_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_add_link_insert_includes_tenant_id` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_add_memory_insert_includes_tenant_id` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_create_session_insert_includes_tenant_id` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_get_session_returns_the_stored_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_get_summary_looks_up_by_concept_and_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_get_summary_returns_the_stored_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_guards_stay_on_record_writes_and_keyed_methods_before_pool_access` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_manifest_delete_filters_by_path_and_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_manifest_get_looks_up_by_path_and_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_manifest_get_returns_the_stored_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_manifest_paths_filters_by_collection_and_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_manifest_upsert_conflict_target_is_per_tenant` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_manifest_upsert_insert_includes_tenant_id` (task 4): passed
- `packages.core.tests.test_pg_tenancy_columns::test_record_query_results_insert_includes_tenant_id` (task 4): passed

## Guard events

- guard.test_tamper: packages/core/tests/pg_fakes.py
- guard.test_tamper: packages/core/tests/pg_fakes.py
- guard.test_tamper: packages/core/tests/pg_fakes.py
