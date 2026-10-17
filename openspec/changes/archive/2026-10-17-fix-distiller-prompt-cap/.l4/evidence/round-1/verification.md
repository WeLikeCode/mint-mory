# Verification: openspec:fix-distiller-prompt-cap: NEEDS_HUMAN (round 1)

traceability: 8/8 criteria covered by a discriminating test

- Base: `0675e362d93eecbae4efd7603228835bab6a2f0f`
- Head: `bd0f0715f31e947a7ece1cb6ed9cab85b2d067e3`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `9a133ff9a5e882915570eb337aa4904acd46d5717981e95789d7569db3b50167`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.4482

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.3 | base merged: staging@0675e362d9 as bd0f0715f3 (1 commit) |
| 1 | integrity | ok | 0.1 | 7 sub-checks; scope: 6 changed file(s) |
| 2 | build | ok | 0.7 |  |
| 3 | tests | ok | 45.6 |  |
| 4 | traceability | ok | 0.0 | 8/8 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 1.0 | 8/8 criteria judged by jev |
| 9 | judge | ok | 18.6 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | NEEDS_HUMAN |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261017T0636Z-f428/085-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261017T0636Z-f428/086-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261017T0636Z-f428/087-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261017T0636Z-f428/088-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261017T0636Z-f428/089-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 1 test file(s) compared with the base |
| red-green freeze | ok | 1 task(s): red and green compared |
| test path freeze | ok | 1 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 10 task(s); red tests passing at head: step 3 |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-203b5e3e | agent-history › Bounded LLM distiller prompt › A huge segment yields a bounded, ask-preserving prompt | covered | packages.core.tests.test_history_distill_phase2::test_huge_segment_prompt_is_bounded_and_ask_preserving (passed, red_assertion) | - | 0.88 |
| C-05c7c216 | agent-history › Bounded LLM distiller prompt › User turns alone exceed the cap (the review fixture) | covered | packages.core.tests.test_history_distill_phase2::test_elide_transcript_user_turns_alone_over_cap (passed, red_assertion) | - | 0.91 |
| C-0840957b | agent-history › Bounded LLM distiller prompt › The drop path counts its markers | covered | packages.core.tests.test_history_distill_phase2::test_elide_transcript_drop_path_counts_markers (passed, red_assertion) | - | 0.88 |
| C-42290229 | agent-history › Bounded LLM distiller prompt › Many single-turn gaps | covered | packages.core.tests.test_history_distill_phase2::test_elide_transcript_many_single_turn_gaps (passed, red_assertion) | - | 0.88 |
| C-6ca7055a | agent-history › Bounded LLM distiller prompt › The first and last turns alone exceed the cap | covered | packages.core.tests.test_history_distill_phase2::test_elide_transcript_first_and_last_over_cap_shortened (passed, red_assertion) | - | 0.92 |
| C-ecdd32b9 | agent-history › Bounded LLM distiller prompt › Turns between an oversized first and last turn become one marker | covered | packages.core.tests.test_history_distill_phase2::test_elide_transcript_first_and_last_over_cap_with_middle_turns (passed, red_assertion) | - | 0.93 |
| C-9cade05a | agent-history › Bounded LLM distiller prompt › Text within the cap is unchanged | covered | packages.core.tests.test_history_distill_phase2::test_elide_transcript_within_cap_unchanged (passed, red_assertion) | - | 0.91 |
| C-5bd97470 | agent-history › Bounded LLM distiller prompt › The whole prompt is bounded by the cap plus the template | covered | packages.core.tests.test_history_distill_phase2::test_prompt_bounded_by_cap_plus_template (passed, red_assertion) | - | 0.90 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `openspec/changes/fix-distiller-prompt-cap/.l4/ledger/r-20261017T0339Z-f7e2.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-distiller-prompt-cap/.l4/ledger/r-20261017T0635Z-5e30.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-distiller-prompt-cap/.l4/ledger/r-20261017T0636Z-f428.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-distiller-prompt-cap/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/core/src/mintmory/core/history/distill.py` | core | relevant | named in the spec |
| `packages/core/tests/test_history_distill_phase2.py` |  | relevant | named in the spec |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

1790 of 1904 passed, 0 failed, 0 errored, 114 skipped.
8 of 8 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-203b5e3e | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-05c7c216 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0840957b | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-42290229 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6ca7055a | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ecdd32b9 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9cade05a | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5bd97470 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-203b5e3e | agent-history › Bounded LLM distiller prompt › A huge segment yields a bounded, ask-preserving prompt | pass | pass | the judge passed it and a discriminating test passes |
| C-05c7c216 | agent-history › Bounded LLM distiller prompt › User turns alone exceed the cap (the review fixture) | pass | pass | the judge passed it and a discriminating test passes |
| C-0840957b | agent-history › Bounded LLM distiller prompt › The drop path counts its markers | pass | pass | the judge passed it and a discriminating test passes |
| C-42290229 | agent-history › Bounded LLM distiller prompt › Many single-turn gaps | pass | pass | the judge passed it and a discriminating test passes |
| C-6ca7055a | agent-history › Bounded LLM distiller prompt › The first and last turns alone exceed the cap | pass | pass | the judge passed it and a discriminating test passes |
| C-ecdd32b9 | agent-history › Bounded LLM distiller prompt › Turns between an oversized first and last turn become one marker | pass | pass | the judge passed it and a discriminating test passes |
| C-9cade05a | agent-history › Bounded LLM distiller prompt › Text within the cap is unchanged | pass | pass | the judge passed it and a discriminating test passes |
| C-5bd97470 | agent-history › Bounded LLM distiller prompt › The whole prompt is bounded by the cap plus the template | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Old loose test not tightened (criterion C-5bd97470): test_prompt_bounded_when_user_turns_alone_exceed_budget still uses the 12000+4000 tolerance; the diff only adds a new test instead of replacing the assertion as the spec and task 1.2 say, though tasks.md ticks 1.2.
- [minor, judge] Caps below 100 unpinned (spec gap) (criterion C-6ca7055a): No test for max_prompt_chars < 100; the final guard only slices to the cap.
- [major, judge] task 1.2 is ticked as already satisfied, but its text is not done: Diff does not modify the 12000 + 4000 assertion in test_prompt_bounded_when_user_turns_alone_exceed_budget; only a new test was added.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.core.tests.test_history_distill_phase2::test_elide_transcript_drop_path_counts_markers` (task 1.1): passed
- `packages.core.tests.test_history_distill_phase2::test_elide_transcript_first_and_last_over_cap_shortened` (task 1.1): passed
- `packages.core.tests.test_history_distill_phase2::test_elide_transcript_first_and_last_over_cap_with_middle_turns` (task 1.1): passed
- `packages.core.tests.test_history_distill_phase2::test_elide_transcript_many_single_turn_gaps` (task 1.1): passed
- `packages.core.tests.test_history_distill_phase2::test_elide_transcript_user_turns_alone_over_cap` (task 1.1): passed
- `packages.core.tests.test_history_distill_phase2::test_elide_transcript_within_cap_unchanged` (task 1.1): passed
- `packages.core.tests.test_history_distill_phase2::test_huge_segment_prompt_is_bounded_and_ask_preserving` (task 1.1): passed
- `packages.core.tests.test_history_distill_phase2::test_prompt_bounded_by_cap_plus_template` (task 1.1): passed

## Guard events

- guard.secret: packages/core/tests/test_history_distill_phase2.py
