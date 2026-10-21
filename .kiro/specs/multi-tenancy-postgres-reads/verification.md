# Verification: kiro:multi-tenancy-postgres-reads: PASS (round 1)

traceability: 9/9 criteria covered by a discriminating test

- Base: `3fce39cca0b6bfa066a0589f0aba92dbaf13050e`
- Head: `2fbd18a1504b248b9e9f647832b011354e6217f7`
- Implementer profiles: deepseek, glm
- Judge: claude-judge (claude-sonnet-5-5), 2 call(s), prompt sha256 `35bc35cd259dccbfefa7d1ba500c281da195bb3a42c2f7cb1ae72d15e97b79ad`
- Judge replies of claude-judge (this unit, all rounds): valid 0, repaired 0, retried 1, discarded 0; this round: retried
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared)
- Cost: $1.5303

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.0 | base staging@3fce39cca0 contained |
| 1 | integrity | ok | 267.1 | 10 sub-checks (+1 unfrozen by human answers); scope: 13 changed file(s) |
| 2 | build | ok | 6.9 |  |
| 3 | tests | ok | 119.9 |  |
| 4 | traceability | ok | 0.1 | 9/9 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 0.4 | 5/9 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 37.9 | 2 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261021T2150Z-8d11/076-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261021T2150Z-8d11/077-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261021T2150Z-8d11/078-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261021T2150Z-8d11/079-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261021T2150Z-8d11/080-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 7 test file(s) compared with the base (+30 allowed, listed) |
| red-green freeze | ok | 1 task(s): red and green compared (+1 unfrozen by human answers) |
| test path freeze | ok | 1 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 5 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2545 of 2545 base tests pass on the unit's code with its 4 test and support files at the base (base: base worktree) |

## Pre-existing tests changed with an allowance (L4-VER-031)

- packages/core/tests/test_pg_tenancy.py::test_pg_anchor_candidates_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_find_image_file_record_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_annotating_descriptions_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_annotating_notes_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_anomaly_flagged_ids_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_anomaly_high_staleness_useful_ids_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_anomaly_never_accessed_ids_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_existing_relates_to_pairs_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_flagged_memories_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_high_staleness_useful_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_links_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_memory_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_never_accessed_stale_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_rehabilitable_rows_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_session_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_stale_archivable_ids_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_stats_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_get_summary_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_list_active_memory_ids_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_list_image_file_records_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_list_memories_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_list_notes_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_list_summaries_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_manifest_get_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_manifest_paths_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_memory_exists_with_content_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_require_global_tenant_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_search_around_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py::test_pg_search_tenancy changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy_columns.py::test_guards_stay_on_record_writes_and_keyed_methods_before_pool_access changed (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy.py kept at head for the run (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy_columns.py kept at head for the run (task 1: unfrozen by Q-001, Q-002, Q-003)
- packages/core/tests/test_pg_tenancy_reads.py kept at head for the run (task 1: unfrozen by Q-001)

## Tests unfrozen by human answers (allowed, L4-IMP-002)

- packages/core/tests/test_pg_tenancy_reads.py (task 1, unfrozen by Q-001, Q-002, Q-003 (human))

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-8a7e36a7 | Req 1.1 | covered | packages.core.tests.test_pg_tenancy_reads::test_pg_fts_scores_adds_tenant_predicate (passed, zero_value); packages.core.tests.test_pg_tenancy_reads::test_pg_load_memories_adds_tenant_predicate (passed, zero_value); packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_kee... | - | - |
| C-0887e505 | Req 1.2 | covered | packages.core.tests.test_pg_tenancy_reads::test_pg_keyed_read_keeps_tenant_predicate_without_guard[get_summary--] (passed, zero_value); packages.core.tests.test_pg_tenancy_reads::test_pg_keyed_read_keeps_tenant_predicate_without_guard[manifest_get--] (passed, zero_value); packages.core.tests.test_pg... | - | - |
| C-c717092d | Req 1.3 | covered | packages.core.tests.test_pg_tenancy_reads::test_pg_fts_scores_adds_tenant_predicate (passed, zero_value); packages.core.tests.test_pg_tenancy_reads::test_pg_load_memories_adds_tenant_predicate (passed, zero_value); packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_kee... | - | - |
| C-f2076555 | Req 2.1 | covered | packages.core.tests.test_pg_tenancy_search::test_pg_search_inactive_tenant_returns_results_without_recording (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_search::test_pg_search_passes_tenant_to_phases_and_callables (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_search::... | - | 0.91 |
| C-eeb31841 | Req 2.2 | covered | packages.core.tests.test_pg_tenancy_search::test_pg_search_active_tenant_records_session_and_results (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_search::test_pg_search_inactive_tenant_returns_results_without_recording (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_sear... | - | 0.92 |
| C-66dbed8a | Req 3.1 | covered | packages.core.tests.test_pg_tenancy_list_reads::test_pg_list_memories_builds_exact_tenant_scoped_select (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_list_reads::test_pg_list_memories_filters_then_limits_the_rows (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_list_reads:... | - | 0.90 |
| C-badf241c | Req 3.2 | covered | packages.core.tests.test_pg_tenancy_list_reads::test_pg_list_memories_builds_exact_tenant_scoped_select (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_list_reads::test_pg_list_memories_filters_then_limits_the_rows (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_list_reads:... | - | 0.94 |
| C-8a45446f | Req 4.1 | covered | packages.core.tests.conformance.test_conformance_tenancy_reads::test_conformance_get_memory_is_tenant_scoped[sqlite] (passed, pre_satisfied); packages.core.tests.conformance.test_conformance_tenancy_reads::test_conformance_get_stats_is_tenant_scoped[sqlite] (passed, pre_satisfied); packages.core.tes... | - | - |
| C-f4fb9aab | Req 5.1 | covered | packages.core.tests.test_pg_tenancy_reads_full_gate::test_reads_full_gate_declares_required_commands_and_coverage_floor (passed, pre_satisfied); packages.core.tests.test_pg_tenancy_reads_full_gate::test_reads_full_gate_lint_and_typecheck_commands_pass (passed, pre_satisfied); packages.core.tests.tes... | - | 0.84 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `.kiro/specs/multi-tenancy-postgres-reads/.l4/ledger/r-20261021T2100Z-e2d8.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres-reads/.l4/ledger/r-20261021T2131Z-5a19.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres-reads/.l4/ledger/r-20261021T2150Z-8d11.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres-reads/questions.md` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-postgres-reads/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/core/src/mintmory/core/storage_postgres.py` | core | relevant | named in the spec |
| `packages/core/tests/conformance/test_conformance_tenancy_reads.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_tenancy.py` |  | relevant | named in the spec |
| `packages/core/tests/test_pg_tenancy_columns.py` |  | none | imports no module of the repository |
| `packages/core/tests/test_pg_tenancy_list_reads.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_tenancy_reads.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_tenancy_reads_full_gate.py` |  | relevant | new test file |
| `packages/core/tests/test_pg_tenancy_search.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

2594 of 2705 passed, 0 failed, 0 errored, 111 skipped.
49 of 49 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-8a7e36a7 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-0887e505 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-c717092d | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-f2076555 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-eeb31841 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-66dbed8a | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-badf241c | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8a45446f | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-f4fb9aab | ok | 0.840 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-8a7e36a7 | Req 1.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-0887e505 | Req 1.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-c717092d | Req 1.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-f2076555 | Req 2.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-eeb31841 | Req 2.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-66dbed8a | Req 3.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-badf241c | Req 3.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-8a45446f | Req 4.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-f4fb9aab | Req 5.1 | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Postgres conformance leg removed from collection via pytest_generate_tests hack (criterion C-8a45446f): The conformance file mutates fixturedef.params via a private pytest attribute to drop the postgres leg without a DSN; fragile but avoids a skip.
- [minor, judge] Explicit tenant_id="global" on a read (spec gap) (criterion C-8a7e36a7): A read with tenant_id="global" is confined with tenant_id = %s like any concrete tenant; only None is unscoped. The spec does not state this.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.core.tests.conformance.test_conformance_tenancy_reads::test_conformance_get_memory_is_tenant_scoped[sqlite]` (task 4): passed
- `packages.core.tests.conformance.test_conformance_tenancy_reads::test_conformance_get_stats_is_tenant_scoped[sqlite]` (task 4): passed
- `packages.core.tests.conformance.test_conformance_tenancy_reads::test_conformance_list_memories_is_tenant_scoped[sqlite]` (task 4): passed
- `packages.core.tests.conformance.test_conformance_tenancy_reads::test_conformance_search_around_is_tenant_scoped[sqlite]` (task 4): passed
- `packages.core.tests.conformance.test_conformance_tenancy_reads::test_conformance_search_is_tenant_scoped[sqlite]` (task 4): passed
- `packages.core.tests.conformance.test_conformance_tenancy_reads::test_conformance_search_under_inactive_tenant_returns_no_session[sqlite]` (task 4): passed
- `packages.core.tests.test_pg_tenancy_list_reads::test_pg_list_memories_builds_exact_tenant_scoped_select` (task 3): passed
- `packages.core.tests.test_pg_tenancy_list_reads::test_pg_list_memories_filters_then_limits_the_rows` (task 3): passed
- `packages.core.tests.test_pg_tenancy_list_reads::test_pg_list_memories_negative_limit_raises_before_any_statement` (task 3): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_fts_scores_adds_tenant_predicate` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_keyed_read_keeps_tenant_predicate_without_guard[get_summary--]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_keyed_read_keeps_tenant_predicate_without_guard[manifest_get--]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_keyed_read_keeps_tenant_predicate_without_guard[manifest_paths--]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_load_memories_adds_tenant_predicate` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[anchor_candidates]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[find_image_file_record]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_annotating_descriptions]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_annotating_notes]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_anomaly_flagged_ids]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_anomaly_high_staleness_useful_ids]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_anomaly_never_accessed_ids]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_existing_relates_to_pairs]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_flagged_memories]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_high_staleness_useful]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_links]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_memory]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_never_accessed_stale]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_rehabilitable_rows]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_session]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_stale_archivable_ids]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[get_stats]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[list_active_memory_ids]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[list_image_file_records]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[list_notes]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[list_summaries]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[memory_exists_with_content]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_read_adds_tenant_predicate_and_keeps_none_sql[search_around]` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_require_global_tenant_is_deleted` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_trigram_scores_wraps_or_clauses_for_tenant` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads::test_pg_vector_scores_adds_tenant_predicate` (task 1): passed
- `packages.core.tests.test_pg_tenancy_reads_full_gate::test_reads_full_gate_declares_required_commands_and_coverage_floor` (task 5): passed
- `packages.core.tests.test_pg_tenancy_reads_full_gate::test_reads_full_gate_lint_and_typecheck_commands_pass` (task 5): passed
- `packages.core.tests.test_pg_tenancy_reads_full_gate::test_reads_full_gate_needs_no_external_service_and_adds_no_skips` (task 5): passed
- `packages.core.tests.test_pg_tenancy_reads_full_gate::test_reads_full_gate_tenant_read_runs_on_the_fake_pool` (task 5): passed
- `packages.core.tests.test_pg_tenancy_search::test_pg_search_active_tenant_records_session_and_results` (task 2): passed
- `packages.core.tests.test_pg_tenancy_search::test_pg_search_inactive_tenant_returns_results_without_recording` (task 2): passed
- `packages.core.tests.test_pg_tenancy_search::test_pg_search_passes_tenant_to_phases_and_callables` (task 2): passed
- `packages.core.tests.test_pg_tenancy_search::test_pg_search_unknown_tenant_records_nothing` (task 2): passed
- `packages.core.tests.test_pg_tenancy_search::test_pg_search_without_tenant_records_a_global_unscoped_session` (task 2): passed

## Guard events

- guard.test_tamper: packages/core/tests/test_pg_tenancy.py
- guard.test_tamper: packages/core/tests/test_pg_tenancy_columns.py
