# Verification: openspec:add-recurrent-tree-indexing: NEEDS_HUMAN (round 1)

traceability: 8/14 criteria covered by a discriminating test

- Base: `9ec57437a6164921ff21b462601696127b5c96d4`
- Head: `d680d4283cd4824fc4510ec1f4022e77f8c74fb6`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 2 call(s), prompt sha256 `131f2d213f94cb55d42a6602a58fe44e4c6fbfd8febcfcd3a012aaada5b299fa`
- Judge replies of claude-judge (this unit, all rounds): valid 0, repaired 0, retried 1, discarded 0; this round: retried
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.8607

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.3 | base staging@9ec57437a6 contained |
| 1 | integrity | ok | 0.1 | 7 sub-checks; scope: 4 changed file(s) |
| 2 | build | ok | 0.8 |  |
| 3 | tests | ok | 52.5 |  |
| 4 | traceability | ok | 0.1 | 8/14 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 1.1 | 14/14 criteria judged by jev |
| 9 | judge | ok | 26.2 | 2 call(s) |
| 10 | aggregation | ok | 0.0 | NEEDS_HUMAN |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261017T0835Z-8265/046-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261017T0835Z-8265/047-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261017T0835Z-8265/048-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261017T0835Z-8265/049-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261017T0835Z-8265/050-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 1 test file(s) compared with the base |
| red-green freeze | ok | 1 task(s): red and green compared |
| test path freeze | ok | 1 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 4 task(s); red tests passing at head: step 3 |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-b54f84ac | ingestion › Online-only-safe tree indexing › Placeholder files are indexed without download | uncovered | - | - | 0.24 |
| C-1ccce576 | ingestion › Metadata + folder-context records › An image is indexed by metadata and neighbours | uncovered | - | - | 0.11 |
| C-99b1ee27 | ingestion › Incremental, idempotent runs › Re-run skips unchanged and updates changed | uncovered | - | - | 0.12 |
| C-4a833fcd | ingestion › Bounded, opt-in content extraction › Content pass respects the budget | uncovered | - | - | 0.20 |
| C-1474f431 | ingestion › Scoping, exclusions, and collection tagging › Excluded files and folders are skipped | uncovered | - | - | 0.12 |
| C-475f20f9 | ingestion › Scoping, exclusions, and collection tagging › Without --exclude, artifacts are indexed as metadata | uncovered | - | - | 0.15 |
| C-0c4d71c5 | ingestion › Default text-content pass skips online-only files › An online-only text file is not read by default | covered | packages.cli.tests.test_cli::test_index_tree_text_content_skips_online_only_file (passed, red_assertion) | - | 0.94 |
| C-70797ec0 | ingestion › Default text-content pass skips online-only files › The count is per run and the row is shown only when non-zero | covered | packages.cli.tests.test_cli::test_index_tree_online_only_skip_counted_per_run (passed, red_assertion) | - | 0.87 |
| C-62e431f2 | ingestion › Default text-content pass skips online-only files › The budgeted content pass can still fetch it on request (fresh DB) | covered | packages.cli.tests.test_cli::test_index_tree_content_pass_reads_online_only_text_on_request (passed, red_assertion) | - | 0.89 |
| C-85ba8c03 | ingestion › One counting rule for text-skipped-online-only › Read is not counted; stopped by the budget or unchanged is counted | covered | packages.cli.tests.test_cli::test_index_tree_budget_exhausted_online_only_text_counted (passed, red_assertion); packages.cli.tests.test_cli::test_index_tree_online_only_skip_counted_per_run (passed, red_assertion) | - | 0.90 |
| C-1935acc7 | ingestion › A metadata row is upgraded by a later content run without --force › Default run, then a content run, upgrades the file without --force | covered | packages.cli.tests.test_cli::test_index_tree_content_run_upgrades_metadata_row_without_force (passed, red_assertion) | - | 0.87 |
| C-5cd92e1a | ingestion › A metadata row is upgraded by a later content run without --force › A content row is not downgraded by a later default run | covered | packages.cli.tests.test_cli::test_index_tree_content_run_upgrades_metadata_row_without_force (passed, red_assertion) | - | 0.78 |
| C-4c28579c | ingestion › A metadata row is upgraded by a later content run without --force › Budget exhausted, online-only text falls back to metadata | covered | packages.cli.tests.test_cli::test_index_tree_budget_exhausted_online_only_text_counted (passed, red_assertion) | - | 0.92 |
| C-de4a2e51 | ingestion › A metadata row is upgraded by a later content run without --force › Empty tree | covered | packages.cli.tests.test_cli::test_index_tree_empty_tree_has_no_online_only_row (passed, red_assertion) | - | 0.91 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `openspec/changes/add-recurrent-tree-indexing/.l4/ledger/r-20261017T0835Z-8265.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-recurrent-tree-indexing/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/cli/src/mintmory/cli/main.py` | cli | relevant | named in the spec |
| `packages/cli/tests/test_cli.py` |  | relevant | named in the spec |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

1802 of 1916 passed, 0 failed, 0 errored, 114 skipped.
6 of 6 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-b54f84ac | ok | 0.240 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1ccce576 | ok | 0.110 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-99b1ee27 | ok | 0.120 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-4a833fcd | ok | 0.200 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1474f431 | ok | 0.120 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-475f20f9 | ok | 0.150 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0c4d71c5 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-70797ec0 | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-62e431f2 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-85ba8c03 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1935acc7 | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5cd92e1a | ok | 0.780 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-4c28579c | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-de4a2e51 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-b54f84ac | ingestion › Online-only-safe tree indexing › Placeholder files are indexed without download | insufficient_evidence | needs_human | uncovered: no adequate discriminating test traces it |
| C-1ccce576 | ingestion › Metadata + folder-context records › An image is indexed by metadata and neighbours | insufficient_evidence | needs_human | uncovered: no adequate discriminating test traces it |
| C-99b1ee27 | ingestion › Incremental, idempotent runs › Re-run skips unchanged and updates changed | insufficient_evidence | needs_human | uncovered: no adequate discriminating test traces it |
| C-4a833fcd | ingestion › Bounded, opt-in content extraction › Content pass respects the budget | insufficient_evidence | needs_human | uncovered: no adequate discriminating test traces it |
| C-1474f431 | ingestion › Scoping, exclusions, and collection tagging › Excluded files and folders are skipped | insufficient_evidence | needs_human | uncovered: no adequate discriminating test traces it |
| C-475f20f9 | ingestion › Scoping, exclusions, and collection tagging › Without --exclude, artifacts are indexed as metadata | insufficient_evidence | needs_human | uncovered: no adequate discriminating test traces it |
| C-0c4d71c5 | ingestion › Default text-content pass skips online-only files › An online-only text file is not read by default | pass | pass | the judge passed it and a discriminating test passes |
| C-70797ec0 | ingestion › Default text-content pass skips online-only files › The count is per run and the row is shown only when non-zero | pass | pass | the judge passed it and a discriminating test passes |
| C-62e431f2 | ingestion › Default text-content pass skips online-only files › The budgeted content pass can still fetch it on request (fresh DB) | pass | pass | the judge passed it and a discriminating test passes |
| C-85ba8c03 | ingestion › One counting rule for text-skipped-online-only › Read is not counted; stopped by the budget or unchanged is counted | pass | pass | the judge passed it and a discriminating test passes |
| C-1935acc7 | ingestion › A metadata row is upgraded by a later content run without --force › Default run, then a content run, upgrades the file without --force | pass | pass | the judge passed it and a discriminating test passes |
| C-5cd92e1a | ingestion › A metadata row is upgraded by a later content run without --force › A content row is not downgraded by a later default run | pass | pass | the judge passed it and a discriminating test passes |
| C-4c28579c | ingestion › A metadata row is upgraded by a later content run without --force › Budget exhausted, online-only text falls back to metadata | pass | pass | the judge passed it and a discriminating test passes |
| C-de4a2e51 | ingestion › A metadata row is upgraded by a later content run without --force › Empty tree | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Help text and docstring not updated: Task 2.3 asks for --text-content help and index_tree docstring to mention online-only skipping; the diff does not change them.
- [minor, judge] Six section-1 criteria have no discriminating test (criterion C-b54f84ac): Gate traceability marks them uncovered; not judged from the diff.
- [major, judge] task 2.3 is ticked as already satisfied, but its text is not done: Counter, placement after want_binary and conditional report row are in the diff (main.py), but the task also requires updating the --text-content help text and index_tree docstring, and the diff does not change them (implementer admits this).

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.cli.tests.test_cli::test_index_tree_budget_exhausted_online_only_text_counted` (task 2.1): passed
- `packages.cli.tests.test_cli::test_index_tree_content_pass_reads_online_only_text_on_request` (task 2.1): passed
- `packages.cli.tests.test_cli::test_index_tree_content_run_upgrades_metadata_row_without_force` (task 2.1): passed
- `packages.cli.tests.test_cli::test_index_tree_empty_tree_has_no_online_only_row` (task 2.1): passed
- `packages.cli.tests.test_cli::test_index_tree_online_only_skip_counted_per_run` (task 2.1): passed
- `packages.cli.tests.test_cli::test_index_tree_text_content_skips_online_only_file` (task 2.1): passed
