# Verification: openspec:fix-markdown-cleanup-fences: PASS (round 1)

traceability: 10/10 criteria covered by a discriminating test

- Base: `af23b1b30712c77ec962d8a03569194345468f2e`
- Head: `6ec0ca82318b2c7e4f1bb9355bafb6d803876633`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `501386a7022c5682642c6643611417ca3bb32457e9cfe683d5d9eccfbff670a4`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.4330

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.4 | base staging@af23b1b307 contained |
| 1 | integrity | ok | 0.1 | 7 sub-checks; scope: 4 changed file(s) |
| 2 | build | ok | 0.9 |  |
| 3 | tests | ok | 49.0 |  |
| 4 | traceability | ok | 0.1 | 10/10 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 0.8 | 10/10 criteria judged by jev |
| 9 | judge | ok | 23.6 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261016T0357Z-f572/079-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261016T0357Z-f572/080-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261016T0357Z-f572/081-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261016T0357Z-f572/082-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261016T0357Z-f572/083-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 1 test file(s) compared with the base |
| red-green freeze | ok | 1 task(s): red and green compared |
| test path freeze | ok | 1 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 6 task(s); red tests passing at head: step 3 |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-0c0ba143 | ingestion › Fenced code blocks survive markdown cleanup byte-identical › Fenced content is kept, the prose around it is cleaned | covered | packages.core.tests.test_conversion::test_clean_markdown_fence_prose_around_block_is_cleaned (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_keeps_fenced_content_and_cleans_prose (passed, zero_value); packages.core.tests.test_conversion::test_clean_markdown_prose_cl... | - | 0.59 |
| C-d06cb587 | ingestion › Fenced code blocks survive markdown cleanup byte-identical › Line endings are still normalised inside a fence | covered | packages.core.tests.test_conversion::test_clean_markdown_crlf_in_fence_normalised_spaces_preserved (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_fence_line_endings_normalised_spaces_kept (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_mark... | - | 0.96 |
| C-99501760 | ingestion › Fenced code blocks survive markdown cleanup byte-identical › Fence grammar | covered | packages.core.tests.test_conversion::test_clean_markdown_fence_grammar (passed, zero_value); packages.core.tests.test_conversion::test_clean_markdown_fence_grammar_character_and_length (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_fence_opening_and_closing_grammar... | - | 0.93 |
| C-637d6041 | ingestion › Fenced code blocks survive markdown cleanup byte-identical › An unterminated fence runs to the end of the text | covered | packages.core.tests.test_conversion::test_clean_markdown_fence_without_closer_reaches_last_line (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_unclosed_fence_spans_to_final_line (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_unter... | - | 0.85 |
| C-279cc124 | ingestion › Fenced code blocks survive markdown cleanup byte-identical › A comment is removed only within one run of non-fenced lines | covered | packages.core.tests.test_conversion::test_clean_markdown_comment_broken_by_fence_left_intact (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_comment_crossing_fence_boundary_survives (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_co... | - | 0.95 |
| C-bd2b7567 | ingestion › Fenced code blocks survive markdown cleanup byte-identical › An unterminated fence keeps its trailing blank lines | covered | packages.core.tests.test_conversion::test_clean_markdown_unclosed_fence_preserves_unique_trailing_blanks (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_unclosed_fence_retains_trailing_blanks (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_m... | - | 0.86 |
| C-202c649c | ingestion › Fenced code blocks survive markdown cleanup byte-identical › Blank runs before a fence still collapse | covered | packages.core.tests.test_conversion::test_clean_markdown_blank_lines_before_fence_collapse_to_one (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_blank_run_before_opening_fence_collapses (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdo... | - | 0.92 |
| C-67b0056e | ingestion › Fenced code blocks survive markdown cleanup byte-identical › A removed comment that exposes an opener needs only one pass | covered | packages.core.tests.test_conversion::test_clean_markdown_comment_removal_exposing_fence_is_stable (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_comment_removal_may_expose_fence_in_one_pass (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_ma... | - | 0.91 |
| C-13d0e1ab | ingestion › Fenced code blocks survive markdown cleanup byte-identical › A second pass changes the first pass's output | covered | packages.core.tests.test_conversion::test_clean_markdown_fixed_point_after_second_pass (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_repeated_pass_reaches_fixed_point (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_second_pass_cha... | - | 0.88 |
| C-c9868a1c | ingestion › Fenced code blocks survive markdown cleanup byte-identical › Idempotent with fences, unchanged without | covered | packages.core.tests.test_conversion::test_clean_markdown_fence_passes_are_idempotent (passed, pre_satisfied); packages.core.tests.test_conversion::test_clean_markdown_is_idempotent_with_fences (passed, zero_value); packages.core.tests.test_conversion::test_clean_markdown_with_fences_idempotent (pass... | - | 0.89 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `openspec/changes/fix-markdown-cleanup-fences/.l4/ledger/r-20261016T0357Z-f572.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-markdown-cleanup-fences/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/core/src/mintmory/core/conversion.py` | core | relevant | named in the spec |
| `packages/core/tests/test_conversion.py` |  | relevant | named in the spec |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

1586 of 1700 passed, 0 failed, 0 errored, 114 skipped.
62 of 62 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-0c0ba143 | ok | 0.590 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d06cb587 | ok | 0.960 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-99501760 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-637d6041 | ok | 0.850 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-279cc124 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-bd2b7567 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-202c649c | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-67b0056e | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-13d0e1ab | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c9868a1c | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-0c0ba143 | ingestion › Fenced code blocks survive markdown cleanup byte-identical › Fenced content is kept, the prose around it is cleaned | pass | pass | the judge passed it and a discriminating test passes |
| C-d06cb587 | ingestion › Fenced code blocks survive markdown cleanup byte-identical › Line endings are still normalised inside a fence | pass | pass | the judge passed it and a discriminating test passes |
| C-99501760 | ingestion › Fenced code blocks survive markdown cleanup byte-identical › Fence grammar | pass | pass | the judge passed it and a discriminating test passes |
| C-637d6041 | ingestion › Fenced code blocks survive markdown cleanup byte-identical › An unterminated fence runs to the end of the text | pass | pass | the judge passed it and a discriminating test passes |
| C-279cc124 | ingestion › Fenced code blocks survive markdown cleanup byte-identical › A comment is removed only within one run of non-fenced lines | pass | pass | the judge passed it and a discriminating test passes |
| C-bd2b7567 | ingestion › Fenced code blocks survive markdown cleanup byte-identical › An unterminated fence keeps its trailing blank lines | pass | pass | the judge passed it and a discriminating test passes |
| C-202c649c | ingestion › Fenced code blocks survive markdown cleanup byte-identical › Blank runs before a fence still collapse | pass | pass | the judge passed it and a discriminating test passes |
| C-67b0056e | ingestion › Fenced code blocks survive markdown cleanup byte-identical › A removed comment that exposes an opener needs only one pass | pass | pass | the judge passed it and a discriminating test passes |
| C-13d0e1ab | ingestion › Fenced code blocks survive markdown cleanup byte-identical › A second pass changes the first pass's output | pass | pass | the judge passed it and a discriminating test passes |
| C-c9868a1c | ingestion › Fenced code blocks survive markdown cleanup byte-identical › Idempotent with fences, unchanged without | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Tab-indented fence lines unspecified (spec gap) (criterion C-99501760): Fence regexes allow only spaces for indentation; a tab-indented ``` is not a fence. Spec does not pin this.
- [minor, judge] Redundant duplicate tests: Many near-identical tests re-pin the same scenarios under different names.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.core.tests.test_conversion::test_clean_markdown_blank_lines_before_fence_collapse_to_one` (task 2.2): passed
- `packages.core.tests.test_conversion::test_clean_markdown_blank_run_before_opening_fence_collapses` (task 2.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_collapses_blank_run_before_fence` (task 1.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_comment_broken_by_fence_left_intact` (task 2.2): passed
- `packages.core.tests.test_conversion::test_clean_markdown_comment_crossing_fence_boundary_survives` (task 2.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_comment_removal_exposing_fence_is_stable` (task 2.2): passed
- `packages.core.tests.test_conversion::test_clean_markdown_comment_removal_may_expose_fence_in_one_pass` (task 2.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_comment_spanning_a_fence_is_not_removed` (task 1.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_crlf_in_fence_normalised_spaces_preserved` (task 2.2): passed
- `packages.core.tests.test_conversion::test_clean_markdown_fence_grammar` (task 1.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_fence_grammar_character_and_length` (task 2.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_fence_line_endings_normalised_spaces_kept` (task 2.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_fence_opening_and_closing_grammar` (task 2.2): passed
- `packages.core.tests.test_conversion::test_clean_markdown_fence_passes_are_idempotent` (task 2.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_fence_prose_around_block_is_cleaned` (task 2.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_fence_without_closer_reaches_last_line` (task 2.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_fixed_point_after_second_pass` (task 2.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_is_idempotent_with_fences` (task 1.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_keeps_fenced_content_and_cleans_prose` (task 1.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_normalises_line_endings_inside_fence` (task 1.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_prose_cleanup_outside_fences_keeps_block` (task 2.2): passed
- `packages.core.tests.test_conversion::test_clean_markdown_removed_comment_exposing_opener_needs_one_pass` (task 1.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_repeated_pass_reaches_fixed_point` (task 2.2): passed
- `packages.core.tests.test_conversion::test_clean_markdown_second_pass_changes_first_pass_output` (task 1.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_unclosed_fence_preserves_unique_trailing_blanks` (task 2.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_unclosed_fence_retains_trailing_blanks` (task 2.2): passed
- `packages.core.tests.test_conversion::test_clean_markdown_unclosed_fence_spans_to_final_line` (task 2.2): passed
- `packages.core.tests.test_conversion::test_clean_markdown_unterminated_fence_keeps_trailing_blank_lines` (task 1.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_unterminated_fence_runs_to_end_of_text` (task 1.1): passed
- `packages.core.tests.test_conversion::test_clean_markdown_with_fences_idempotent` (task 2.2): passed
- `packages.core.tests.test_conversion::test_extract_markdown_markitdown_path_keeps_fenced_content` (task 2.3): passed
- `packages.core.tests.test_conversion::test_extract_markdown_text_path_blank_run_before_fence_collapses` (task 2.3): passed
- `packages.core.tests.test_conversion::test_extract_markdown_text_path_comment_exposing_opener_needs_one_pass` (task 2.3): passed
- `packages.core.tests.test_conversion::test_extract_markdown_text_path_comment_split_by_fence_survives` (task 2.3): passed
- `packages.core.tests.test_conversion::test_extract_markdown_text_path_fence_cleanup_is_idempotent` (task 2.3): passed
- `packages.core.tests.test_conversion::test_extract_markdown_text_path_fence_grammar` (task 2.3): passed
- `packages.core.tests.test_conversion::test_extract_markdown_text_path_keeps_fenced_content` (task 2.3): passed
- `packages.core.tests.test_conversion::test_extract_markdown_text_path_normalises_crlf_inside_fence` (task 2.3): passed
- `packages.core.tests.test_conversion::test_extract_markdown_text_path_second_pass_reaches_fixed_point` (task 2.3): passed
- `packages.core.tests.test_conversion::test_extract_markdown_text_path_unterminated_fence_keeps_trailing_blanks` (task 2.3): passed
- `packages.core.tests.test_conversion::test_extract_markdown_text_path_unterminated_fence_runs_to_end` (task 2.3): passed
- `packages.core.tests.test_conversion::test_extract_markdown_unknown_suffix_path_keeps_fenced_content` (task 2.3): passed
- `packages.core.tests.test_conversion::test_gate_blank_runs_before_fence_still_collapse` (task 3.1): passed
- `packages.core.tests.test_conversion::test_gate_comment_removed_only_within_one_run_of_non_fenced_lines` (task 3.1): passed
- `packages.core.tests.test_conversion::test_gate_fence_grammar` (task 3.1): passed
- `packages.core.tests.test_conversion::test_gate_fenced_content_kept_prose_around_cleaned` (task 3.1): passed
- `packages.core.tests.test_conversion::test_gate_idempotent_with_fences_unchanged_without` (task 3.1): passed
- `packages.core.tests.test_conversion::test_gate_line_endings_normalised_inside_fence` (task 3.1): passed
- `packages.core.tests.test_conversion::test_gate_removed_comment_exposing_opener_needs_one_pass` (task 3.1): passed
- `packages.core.tests.test_conversion::test_gate_second_pass_changes_first_pass_output` (task 3.1): passed
