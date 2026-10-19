# Verification: kiro:multi-tenancy-writes: PASS (round 1)

traceability: 26/26 criteria covered by a discriminating test

- Base: `5d73c5c56746a639ee128bd0e3975a20243fbe65`
- Head: `250da7e6e883224c27a38a2aa4971969e08225cc`
- Implementer profiles: deepseek, glm
- Judge: claude-judge (claude-sonnet-5-5), 2 call(s), prompt sha256 `10b2bb037f2682032c45302d76d24d5b1a597931f89843fbced6b82352bc9daf`
- Judge replies of claude-judge (this unit, all rounds): valid 0, repaired 0, retried 1, discarded 0; this round: retried
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared)
- Cost: $1.3360

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.0 | base staging@5d73c5c567 contained |
| 1 | integrity | ok | 0.3 | 7 sub-checks; scope: 14 changed file(s) |
| 2 | build | ok | 1.1 |  |
| 3 | tests | ok | 82.7 |  |
| 4 | traceability | ok | 0.1 | 26/26 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 2.5 | 24/26 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 46.4 | 2 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261019T1928Z-bd5a/044-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261019T1928Z-bd5a/045-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261019T1928Z-bd5a/046-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261019T1928Z-bd5a/047-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261019T1928Z-bd5a/048-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 7 test file(s) compared with the base |
| red-green freeze | ok | 4 task(s): red and green compared |
| test path freeze | ok | 4 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 5 task(s); red tests passing at head: step 3 |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-5419350d | Req 1.1 | covered | packages.core.tests.test_tenancy_write_guard::test_assert_tenant_writable_accepts_active_tenants (passed, zero_value); packages.core.tests.test_tenancy_write_guard::test_assert_tenant_writable_rejects_missing_and_inactive (passed, zero_value) | - | 0.91 |
| C-2812d3f2 | Req 1.2 | covered | packages.core.tests.test_tenancy_write_guard::test_add_link_rejects_inactive_link_tenant (passed, zero_value); packages.core.tests.test_tenancy_write_guard::test_add_link_rejects_missing_link_tenant (passed, zero_value); packages.core.tests.test_tenancy_write_guard::test_add_memory_builds_the_record... | - | - |
| C-0ff47353 | Req 1.3 | covered | packages.core.tests.test_tenancy_write_guard::test_add_memory_guard_from_record_rejects_inactive_and_missing (passed, zero_value); packages.core.tests.test_tenancy_write_guard::test_add_memory_guard_holds_on_a_migrated_database (passed, zero_value); packages.core.tests.test_tenancy_write_guard::test... | - | 0.93 |
| C-16655ef4 | Req 1.4 | covered | packages.core.tests.test_tenancy_write_guard::test_bump_retrieval_skips_inactive_tenant_rows (passed, zero_value) | - | 0.82 |
| C-eded8e54 | Req 1.5 | covered | packages.core.tests.test_tenancy_write_guard::test_reads_of_inactive_tenant_rows_are_not_guarded (passed, zero_value) | - | 0.94 |
| C-1d1a6032 | Req 1.6 | covered | packages.core.tests.test_tenancy_write_guard::test_guard_and_write_share_one_locked_transaction (passed, zero_value) | - | 0.76 |
| C-b08b76d6 | Req 1.7 | covered | packages.core.tests.test_tenancy_write_guard::test_guard_runs_before_the_sql_write_on_a_duplicate_key (passed, zero_value); packages.core.tests.test_tenancy_write_guard::test_missing_rows_keep_their_missing_row_outcome (passed, zero_value) | - | 0.78 |
| C-4389e90a | Req 2.1 | covered | packages.core.tests.test_tenancy_references::test_add_link_cross_tenant_endpoints (passed, red_assertion); packages.core.tests.test_tenancy_references::test_add_link_link_tenant_must_match_its_endpoints (passed, red_assertion) | - | 0.85 |
| C-056266db | Req 2.2 | covered | packages.core.tests.test_tenancy_references::test_record_query_results_cross_tenant_rules (passed, red_assertion); packages.core.tests.test_tenancy_references::test_record_query_results_validates_the_batch_before_inserting (passed, red_assertion) | - | 0.88 |
| C-4789c501 | Req 2.3 | covered | packages.core.tests.test_tenancy_references::test_supersede_memory_requires_the_same_tenant (passed, red_assertion) | - | 0.80 |
| C-24b01ee5 | Req 2.4 | covered | packages.core.tests.test_tenancy_references::test_add_memory_superseded_by_requires_the_same_tenant (passed, red_assertion); packages.core.tests.test_tenancy_references::test_update_memory_superseded_by_requires_the_same_tenant (passed, red_assertion) | - | 0.91 |
| C-bcdf64ef | Req 2.5 | covered | packages.core.tests.test_tenancy_references::test_update_memory_rejects_a_tenant_change (passed, red_assertion) | - | 0.75 |
| C-561f5d0e | Req 2.6 | covered | packages.core.tests.test_tenancy_references::test_soft_references_are_not_checked_by_storage (passed, red_assertion) | - | 0.87 |
| C-86e4552e | Req 2.7 | covered | packages.core.tests.test_tenancy_references::test_add_link_cross_tenant_endpoints (passed, red_assertion); packages.core.tests.test_tenancy_references::test_add_link_link_tenant_must_match_its_endpoints (passed, red_assertion); packages.core.tests.test_tenancy_references::test_record_query_results_c... | - | - |
| C-3810642f | Req 3.1 | covered | packages.core.tests.test_pg_tenancy::test_pg_apply_feedback_tenancy (passed, zero_value); packages.core.tests.test_pg_tenancy::test_pg_archive_memory_tenancy (passed, zero_value); packages.core.tests.test_pg_tenancy::test_pg_supersede_memory_tenancy (passed, zero_value); packages.core.tests.test_ten... | - | 0.89 |
| C-18bbe618 | Req 3.2 | covered | packages.core.tests.test_tenancy_id_writes::test_none_acts_on_the_stored_row_and_keeps_missing_row_outcomes (passed, zero_value) | - | 0.93 |
| C-a7082d94 | Req 3.3 | covered | packages.core.tests.test_tenancy_id_writes::test_concrete_tenant_requires_the_row_in_that_tenant (passed, zero_value); packages.core.tests.test_tenancy_id_writes::test_none_acts_on_the_stored_row_and_keeps_missing_row_outcomes (passed, zero_value) | - | 0.87 |
| C-44a91f81 | Req 3.4 | covered | packages.core.tests.test_pg_tenancy::test_pg_update_memory_tenancy (passed, zero_value); packages.core.tests.test_tenancy_id_writes::test_id_only_writes_never_change_the_stored_tenant (passed, zero_value) | - | 0.91 |
| C-24839466 | Req 3.5 | covered | packages.core.tests.test_tenancy_id_writes::test_archive_with_a_concrete_tenant_keeps_foreign_rows_active (passed, zero_value) | - | 0.75 |
| C-7ea843d6 | Req 4.1 | covered | packages.core.tests.test_tenancy_writes::test_nested_transactions_commit_once (passed, red_assertion); packages.core.tests.test_tenancy_writes::test_transaction_outermost_sets_depth_and_locks_reentrantly (passed, red_assertion) | - | 0.90 |
| C-95cabe80 | Req 4.2 | covered | packages.core.tests.test_tenancy_writes::test_composed_writes_roll_back_together (passed, red_assertion); packages.core.tests.test_tenancy_writes::test_nested_exception_caught_inside_outer_commits_survivors (passed, red_assertion); packages.core.tests.test_tenancy_writes::test_nested_transactions_co... | - | 0.89 |
| C-7b243e91 | Req 4.3 | covered | packages.core.tests.test_tenancy_writes::test_second_thread_waits_for_outermost_transaction (passed, red_assertion) | - | 0.92 |
| C-2ae7611a | Req 4.4 | covered | packages.core.tests.test_tenancy_writes::test_ports_docstring_excludes_only_connect_from_the_protocol (passed, red_assertion); packages.core.tests.test_tenancy_writes::test_protocol_declares_transaction_context_manager (passed, red_assertion) | - | 0.88 |
| C-74b68113 | Req 4.5 | covered | packages.core.tests.test_pg_tenancy::test_pg_transaction_tenancy (passed, red_assertion); packages.core.tests.test_tenancy_writes::test_ports_docstring_excludes_only_connect_from_the_protocol (passed, red_assertion) | - | 0.75 |
| C-59232fa4 | Req 5.1 | covered | packages.core.tests.test_tenancy_writes_full_gate::test_global_only_database_keeps_existing_write_contracts (passed, pre_satisfied) | - | 0.89 |
| C-3e681376 | Req 5.2 | covered | packages.core.tests.test_tenancy_writes_full_gate::test_tenancy_writes_gate_declares_required_commands_and_coverage_floor (passed, pre_satisfied); packages.core.tests.test_tenancy_writes_full_gate::test_tenancy_writes_lint_and_typecheck_commands_pass (passed, pre_satisfied); packages.core.tests.test... | - | 0.84 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `.kiro/specs/multi-tenancy-writes/.l4/ledger/r-20261019T1754Z-ec85.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-writes/.l4/ledger/r-20261019T1928Z-bd5a.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-writes/questions.md` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-writes/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/core/src/mintmory/core/ports.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/storage.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/storage_postgres.py` | core | relevant | named in the spec |
| `packages/core/tests/test_pg_tenancy.py` |  | relevant | named in the spec |
| `packages/core/tests/test_tenancy_id_writes.py` |  | relevant | new test file |
| `packages/core/tests/test_tenancy_references.py` |  | relevant | new test file |
| `packages/core/tests/test_tenancy_write_guard.py` |  | relevant | new test file |
| `packages/core/tests/test_tenancy_writes.py` |  | relevant | new test file |
| `packages/core/tests/test_tenancy_writes_full_gate.py` |  | relevant | new test file |
| `packages/core/tests/test_tenant_persistence.py` |  | none | imports no module of the repository |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

2123 of 2237 passed, 0 failed, 0 errored, 114 skipped.
61 of 61 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-5419350d | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2812d3f2 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-0ff47353 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-16655ef4 | ok | 0.820 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-eded8e54 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1d1a6032 | ok | 0.760 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b08b76d6 | ok | 0.780 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-4389e90a | ok | 0.850 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-056266db | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-4789c501 | ok | 0.800 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-24b01ee5 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-bcdf64ef | ok | 0.750 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-561f5d0e | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-86e4552e | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-3810642f | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-18bbe618 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a7082d94 | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-44a91f81 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-24839466 | ok | 0.750 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7ea843d6 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-95cabe80 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7b243e91 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2ae7611a | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-74b68113 | ok | 0.750 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-59232fa4 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3e681376 | ok | 0.840 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-5419350d | Req 1.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-2812d3f2 | Req 1.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-0ff47353 | Req 1.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-16655ef4 | Req 1.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-eded8e54 | Req 1.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-1d1a6032 | Req 1.6 | pass | pass | the judge passed it and a discriminating test passes |
| C-b08b76d6 | Req 1.7 | pass | pass | the judge passed it and a discriminating test passes |
| C-4389e90a | Req 2.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-056266db | Req 2.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-4789c501 | Req 2.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-24b01ee5 | Req 2.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-bcdf64ef | Req 2.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-561f5d0e | Req 2.6 | pass | pass | the judge passed it and a discriminating test passes |
| C-86e4552e | Req 2.7 | pass | pass | the judge passed it and a discriminating test passes |
| C-3810642f | Req 3.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-18bbe618 | Req 3.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-a7082d94 | Req 3.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-44a91f81 | Req 3.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-24839466 | Req 3.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-7ea843d6 | Req 4.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-95cabe80 | Req 4.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-7b243e91 | Req 4.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-2ae7611a | Req 4.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-74b68113 | Req 4.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-59232fa4 | Req 5.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-3e681376 | Req 5.2 | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] add_link with missing endpoint still runs tenant guard on link.tenant_id (spec gap) (criterion C-4389e90a): When an endpoint is missing, the reference checks are skipped but _assert_tenant_writable(link.tenant_id) still runs, so a missing or inactive link tenant raises a tenant error rather than the FK IntegrityError. Same for record_query_results.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.core.tests.test_pg_tenancy::test_pg_apply_feedback_tenancy` (task 4): passed
- `packages.core.tests.test_pg_tenancy::test_pg_archive_memory_tenancy` (task 4): passed
- `packages.core.tests.test_pg_tenancy::test_pg_supersede_memory_tenancy` (task 4): passed
- `packages.core.tests.test_pg_tenancy::test_pg_transaction_tenancy` (task 1): passed
- `packages.core.tests.test_pg_tenancy::test_pg_update_memory_tenancy` (task 4): passed
- `packages.core.tests.test_tenancy_id_writes::test_archive_with_a_concrete_tenant_keeps_foreign_rows_active` (task 4): passed
- `packages.core.tests.test_tenancy_id_writes::test_concrete_tenant_requires_the_row_in_that_tenant` (task 4): passed
- `packages.core.tests.test_tenancy_id_writes::test_id_only_write_signatures` (task 4): passed
- `packages.core.tests.test_tenancy_id_writes::test_id_only_writes_never_change_the_stored_tenant` (task 4): passed
- `packages.core.tests.test_tenancy_id_writes::test_none_acts_on_the_stored_row_and_keeps_missing_row_outcomes` (task 4): passed
- `packages.core.tests.test_tenancy_references::test_add_link_cross_tenant_endpoints` (task 3): passed
- `packages.core.tests.test_tenancy_references::test_add_link_link_tenant_must_match_its_endpoints` (task 3): passed
- `packages.core.tests.test_tenancy_references::test_add_memory_superseded_by_requires_the_same_tenant` (task 3): passed
- `packages.core.tests.test_tenancy_references::test_record_query_results_cross_tenant_rules` (task 3): passed
- `packages.core.tests.test_tenancy_references::test_record_query_results_validates_the_batch_before_inserting` (task 3): passed
- `packages.core.tests.test_tenancy_references::test_soft_references_are_not_checked_by_storage` (task 3): passed
- `packages.core.tests.test_tenancy_references::test_supersede_memory_requires_the_same_tenant` (task 3): passed
- `packages.core.tests.test_tenancy_references::test_update_memory_rejects_a_tenant_change` (task 3): passed
- `packages.core.tests.test_tenancy_references::test_update_memory_superseded_by_requires_the_same_tenant` (task 3): passed
- `packages.core.tests.test_tenancy_write_guard::test_add_link_rejects_inactive_link_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_add_link_rejects_missing_link_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_add_memory_builds_the_record_from_fields_before_guarding` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_add_memory_guard_from_record_rejects_inactive_and_missing` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_add_memory_guard_holds_on_a_migrated_database` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_apply_feedback_rejects_inactive_stored_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_apply_feedback_rejects_missing_stored_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_archive_memory_rejects_inactive_stored_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_archive_memory_rejects_missing_stored_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_assert_tenant_writable_accepts_active_tenants` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_assert_tenant_writable_rejects_missing_and_inactive` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_bump_retrieval_skips_inactive_tenant_rows` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_create_session_rejects_inactive_and_missing_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_guard_and_write_share_one_locked_transaction` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_guard_runs_before_the_sql_write_on_a_duplicate_key` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_manifest_delete_rejects_inactive_tenant_without_deleting` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_manifest_delete_rejects_missing_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_manifest_upsert_rejects_inactive_and_missing_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_mark_session_concluded_rejects_inactive_stored_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_mark_session_concluded_rejects_missing_stored_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_missing_rows_keep_their_missing_row_outcome` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_reads_of_inactive_tenant_rows_are_not_guarded` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_record_query_results_rejects_inactive_result_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_record_query_results_rejects_missing_result_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_supersede_memory_rejects_inactive_stored_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_supersede_memory_rejects_missing_stored_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_update_memory_rejects_inactive_stored_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_update_memory_rejects_missing_stored_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_update_session_feedback_rejects_inactive_stored_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_update_session_feedback_rejects_missing_stored_tenant` (task 2): passed
- `packages.core.tests.test_tenancy_write_guard::test_upsert_summary_rejects_inactive_and_missing_tenant` (task 2): passed

## Guard events

- guard.violation: packages/core/src/mintmory/core/storage_postgres.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/storage_postgres.py
