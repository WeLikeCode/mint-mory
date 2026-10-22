# Verification: openspec:add-recurrent-tree-indexing: FAIL (round 3)

traceability: 8/14 criteria covered by a discriminating test

- Base: `0aaa527e1cec8c429d0e8c3210abf61d3bcd14ef`
- Head: `b434bd217b14127ddbeeacb7c3bab820331613de`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `bbd21d96e7c639c32cc98b1150d8e0a553eb3fc68e780519691e87fd6800d038`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 1, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.4623

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.3 | base merged: staging@0aaa527e1c as b434bd217b (1 commit) |
| 1 | integrity | ok | 0.2 | 7 sub-checks; scope: 14 changed file(s) |
| 2 | build | ok | 17.1 |  |
| 3 | tests | ok | 50.6 |  |
| 4 | traceability | ok | 0.1 | 8/14 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 1.6 | 14/14 criteria judged by jev |
| 9 | judge | ok | 15.3 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | FAIL |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261017T1027Z-b735/001-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261017T1027Z-b735/002-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261017T1027Z-b735/003-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261017T1027Z-b735/004-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261017T1027Z-b735/005-test.log |

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
| C-b54f84ac | ingestion › Online-only-safe tree indexing › Placeholder files are indexed without download | uncovered | - | - | 0.08 |
| C-1ccce576 | ingestion › Metadata + folder-context records › An image is indexed by metadata and neighbours | uncovered | - | - | 0.05 |
| C-99b1ee27 | ingestion › Incremental, idempotent runs › Re-run skips unchanged and updates changed | uncovered | - | - | 0.04 |
| C-4a833fcd | ingestion › Bounded, opt-in content extraction › Content pass respects the budget | uncovered | - | - | 0.03 |
| C-1474f431 | ingestion › Scoping, exclusions, and collection tagging › Excluded files and folders are skipped | uncovered | - | - | 0.04 |
| C-475f20f9 | ingestion › Scoping, exclusions, and collection tagging › Without --exclude, artifacts are indexed as metadata | uncovered | - | - | 0.04 |
| C-0c4d71c5 | ingestion › Default text-content pass skips online-only files › An online-only text file is not read by default | covered | packages.cli.tests.test_cli::test_index_tree_text_content_skips_online_only_file (passed, red_assertion) | - | 0.93 |
| C-70797ec0 | ingestion › Default text-content pass skips online-only files › The count is per run and the row is shown only when non-zero | covered | packages.cli.tests.test_cli::test_index_tree_online_only_skip_counted_per_run (passed, red_assertion) | - | 0.85 |
| C-62e431f2 | ingestion › Default text-content pass skips online-only files › The budgeted content pass can still fetch it on request (fresh DB) | covered | packages.cli.tests.test_cli::test_index_tree_content_pass_reads_online_only_text_on_request (passed, red_assertion) | - | 0.88 |
| C-85ba8c03 | ingestion › One counting rule for text-skipped-online-only › Read is not counted; stopped by the budget or unchanged is counted | covered | packages.cli.tests.test_cli::test_index_tree_budget_exhausted_online_only_text_counted (passed, red_assertion); packages.cli.tests.test_cli::test_index_tree_online_only_skip_counted_per_run (passed, red_assertion) | - | 0.87 |
| C-1935acc7 | ingestion › A metadata row is upgraded by a later content run without --force › Default run, then a content run, upgrades the file without --force | covered | packages.cli.tests.test_cli::test_index_tree_content_run_upgrades_metadata_row_without_force (passed, red_assertion) | - | 0.90 |
| C-5cd92e1a | ingestion › A metadata row is upgraded by a later content run without --force › A content row is not downgraded by a later default run | covered | packages.cli.tests.test_cli::test_index_tree_content_run_upgrades_metadata_row_without_force (passed, red_assertion) | - | 0.72 |
| C-4c28579c | ingestion › A metadata row is upgraded by a later content run without --force › Budget exhausted, online-only text falls back to metadata | covered | packages.cli.tests.test_cli::test_index_tree_budget_exhausted_online_only_text_counted (passed, red_assertion) | - | 0.91 |
| C-de4a2e51 | ingestion › A metadata row is upgraded by a later content run without --force › Empty tree | covered | packages.cli.tests.test_cli::test_index_tree_empty_tree_has_no_online_only_row (passed, red_assertion) | - | 0.92 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `openspec/changes/add-recurrent-tree-indexing/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-recurrent-tree-indexing/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-recurrent-tree-indexing/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-recurrent-tree-indexing/.l4/evidence/round-2/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-recurrent-tree-indexing/.l4/evidence/round-2/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-recurrent-tree-indexing/.l4/evidence/round-2/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-recurrent-tree-indexing/.l4/ledger/r-20261017T0835Z-8265.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-recurrent-tree-indexing/.l4/ledger/r-20261017T0922Z-5dcd.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-recurrent-tree-indexing/.l4/ledger/r-20261017T1026Z-6dcc.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-recurrent-tree-indexing/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-recurrent-tree-indexing/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-recurrent-tree-indexing/verification.md` |  | none | exempt: harness, spec or documentation path |
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
| C-b54f84ac | ok | 0.080 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1ccce576 | ok | 0.050 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-99b1ee27 | ok | 0.040 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-4a833fcd | ok | 0.030 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1474f431 | ok | 0.040 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-475f20f9 | ok | 0.040 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0c4d71c5 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-70797ec0 | ok | 0.850 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-62e431f2 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-85ba8c03 | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1935acc7 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5cd92e1a | ok | 0.720 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-4c28579c | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-de4a2e51 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Human verdicts

- Q-001 accept C-b54f84ac by human: satisfied as it stands. test_is_online_only_detects_placeholder (packages/core/tests/test_tree_index.py) proves placeholder detection; the default text pass no longer reads an online-only file (task 2.2 guard, proven by the new test_index_tree_text_content_skips_online_only_file: the extract_markdow...
- Q-002 accept C-1ccce576 by human: satisfied as it stands. test_render_file_record_includes_type_location_and_siblings asserts the name, the type label, the size, the folder location, the sibling names and the mtime date; test_render_file_record_flags_online_only asserts the online-only flag; test_index_tree_metadata_only_indexes_eve...
- Q-003 accept C-99b1ee27 by human: satisfied as it stands. test_index_tree_is_idempotent shows a second run over an unchanged tree adds no memory; test_index_tree_reindexes_changed_file shows the changed a.md has exactly one active record and the old one archived (replaced, not duplicated); index_tree calls store.manifest_upsert for ...
- Q-004 accept C-4a833fcd by human: satisfied as it stands. index_tree stops binary and content reads once the --max-download-mb budget is spent (budget_hit), the remaining files fall back to metadata-only, and the report prints the row budget: reached - remaining files metadata-only. The new test_index_tree_budget_exhausted_online_on...
- Q-005 accept C-1474f431 by human: satisfied as it stands. --exclude is a comma-separated glob list (main.py splits it on commas and strips each glob); test_iter_dir_groups_exclude_folder_and_suffix proves Personal/** prunes the whole subtree and *.dll drops the suffix at the walk; test_index_tree_exclude_prunes_subtree proves the ex...
- Q-006 accept C-475f20f9 by human: satisfied as it stands. test_iter_dir_groups_yields_all_files_by_default shows the default walk yields build.dll with every other file (no default denylist), and index_tree renders every non-text file the same way as a metadata + folder-context record (test_render_file_record_includes_type_location_...
- Q-007 reject F-b34b9dc3 by human: the finding is right. Task 2.3 also asks to update the --text-content help text and the index_tree docstring to say that online-only files are skipped by this pass; the unit diff changes neither (only the counter and the report row). WHEN mintmory index-tree --help is shown THEN the --text-content h...

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-b54f84ac | ingestion › Online-only-safe tree indexing › Placeholder files are indexed without download | insufficient_evidence | pass | accepted by human: satisfied as it stands. test_is_online_only_detects_placeholder (packages/core/tests/test_tree_index.py) proves placeholder detection; the default text pass no longer reads an online-only file (task 2.2 guard, proven by the new test_index_tree_text_content_skips_online_only_file: ... |
| C-1ccce576 | ingestion › Metadata + folder-context records › An image is indexed by metadata and neighbours | insufficient_evidence | pass | accepted by human: satisfied as it stands. test_render_file_record_includes_type_location_and_siblings asserts the name, the type label, the size, the folder location, the sibling names and the mtime date; test_render_file_record_flags_online_only asserts the online-only flag; test_index_tree_metada... |
| C-99b1ee27 | ingestion › Incremental, idempotent runs › Re-run skips unchanged and updates changed | insufficient_evidence | pass | accepted by human: satisfied as it stands. test_index_tree_is_idempotent shows a second run over an unchanged tree adds no memory; test_index_tree_reindexes_changed_file shows the changed a.md has exactly one active record and the old one archived (replaced, not duplicated); index_tree calls store.m... |
| C-4a833fcd | ingestion › Bounded, opt-in content extraction › Content pass respects the budget | insufficient_evidence | pass | accepted by human: satisfied as it stands. index_tree stops binary and content reads once the --max-download-mb budget is spent (budget_hit), the remaining files fall back to metadata-only, and the report prints the row budget: reached - remaining files metadata-only. The new test_index_tree_budget_... |
| C-1474f431 | ingestion › Scoping, exclusions, and collection tagging › Excluded files and folders are skipped | insufficient_evidence | pass | accepted by human: satisfied as it stands. --exclude is a comma-separated glob list (main.py splits it on commas and strips each glob); test_iter_dir_groups_exclude_folder_and_suffix proves Personal/** prunes the whole subtree and *.dll drops the suffix at the walk; test_index_tree_exclude_prunes_su... |
| C-475f20f9 | ingestion › Scoping, exclusions, and collection tagging › Without --exclude, artifacts are indexed as metadata | insufficient_evidence | pass | accepted by human: satisfied as it stands. test_iter_dir_groups_yields_all_files_by_default shows the default walk yields build.dll with every other file (no default denylist), and index_tree renders every non-text file the same way as a metadata + folder-context record (test_render_file_record_incl... |
| C-0c4d71c5 | ingestion › Default text-content pass skips online-only files › An online-only text file is not read by default | pass | pass | the judge passed it and a discriminating test passes |
| C-70797ec0 | ingestion › Default text-content pass skips online-only files › The count is per run and the row is shown only when non-zero | pass | pass | the judge passed it and a discriminating test passes |
| C-62e431f2 | ingestion › Default text-content pass skips online-only files › The budgeted content pass can still fetch it on request (fresh DB) | pass | pass | the judge passed it and a discriminating test passes |
| C-85ba8c03 | ingestion › One counting rule for text-skipped-online-only › Read is not counted; stopped by the budget or unchanged is counted | pass | pass | the judge passed it and a discriminating test passes |
| C-1935acc7 | ingestion › A metadata row is upgraded by a later content run without --force › Default run, then a content run, upgrades the file without --force | pass | pass | the judge passed it and a discriminating test passes |
| C-5cd92e1a | ingestion › A metadata row is upgraded by a later content run without --force › A content row is not downgraded by a later default run | pass | pass | the judge passed it and a discriminating test passes |
| C-4c28579c | ingestion › A metadata row is upgraded by a later content run without --force › Budget exhausted, online-only text falls back to metadata | pass | pass | the judge passed it and a discriminating test passes |
| C-de4a2e51 | ingestion › A metadata row is upgraded by a later content run without --force › Empty tree | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [major, judge] Task 2.3 help text and docstring not updated: Task 2.3 requires the --text-content help and index_tree docstring to state online-only files are skipped; the diff changes neither.
- [major, human] task 2.3 is ticked as already satisfied, but its text is not done: Counter and row present, but --text-content help text and index_tree docstring not updated in the diff. [rejected by human (the finding is right. Task 2.3 also asks to update the --text-content help text and the index_tree docstring to say that online-only files are skipped by this pass; the unit diff changes neither (only the counter and the report row). WHEN mintmory index-tree --help is shown THEN the --text-content help says that online-only files are skipped by the inline text pass, and the index_tree docstring says the same.)]

## Fix unit

Fix unit 1 is created for these tasks:
- F-b34b9dc3 task 2.3 is ticked as already satisfied, but its text is not done

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.cli.tests.test_cli::test_index_tree_budget_exhausted_online_only_text_counted` (task 2.1): passed
- `packages.cli.tests.test_cli::test_index_tree_content_pass_reads_online_only_text_on_request` (task 2.1): passed
- `packages.cli.tests.test_cli::test_index_tree_content_run_upgrades_metadata_row_without_force` (task 2.1): passed
- `packages.cli.tests.test_cli::test_index_tree_empty_tree_has_no_online_only_row` (task 2.1): passed
- `packages.cli.tests.test_cli::test_index_tree_online_only_skip_counted_per_run` (task 2.1): passed
- `packages.cli.tests.test_cli::test_index_tree_text_content_skips_online_only_file` (task 2.1): passed
