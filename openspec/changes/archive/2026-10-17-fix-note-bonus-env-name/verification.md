# Verification: openspec:fix-note-bonus-env-name: PASS (round 1)

traceability: 5/5 criteria covered by a discriminating test

- Base: `788adf714706d466ffc81fb700014cda202a3b36`
- Head: `a29d7d09ebdd1b6692f02cf78c6d4c98fe0b4aed`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `ed9891af13944a1daef49395f36ab16ed1fe86294ab538862e91567fc7b2d219`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.4218

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.3 | base staging@788adf7147 contained |
| 1 | integrity | ok | 0.1 | 7 sub-checks; scope: 6 changed file(s) |
| 2 | build | ok | 0.8 |  |
| 3 | tests | ok | 61.2 |  |
| 4 | traceability | ok | 0.0 | 5/5 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 0.6 | 4/5 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 14.7 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261017T0237Z-d577/088-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261017T0237Z-d577/089-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261017T0237Z-d577/090-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261017T0237Z-d577/091-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261017T0237Z-d577/092-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 2 test file(s) compared with the base |
| red-green freeze | ok | 2 task(s): red and green compared |
| test path freeze | ok | 2 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 5 task(s); red tests passing at head: step 3 |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-4685d347 | notes › Note bonus is read from the documented MINTMORY_NOTE_BONUS › The documented name sets the bonus | covered | packages.core.tests.test_config.TestNoteSettingsBonusEnvGateContract::test_gate_documented_name_reaches_note_and_load_settings (passed, pre_satisfied); packages.core.tests.test_config.TestNoteSettingsBonusEnvGateContract::test_gate_legacy_name_still_works_and_documented_name_wins (passed, pre_satisf... | - | - |
| C-f1c5c1d6 | notes › Note bonus is read from the documented MINTMORY_NOTE_BONUS › The legacy name still works | covered | packages.core.tests.test_config.TestNoteSettingsBonusEnvGateContract::test_gate_legacy_name_still_works_and_documented_name_wins (passed, pre_satisfied); packages.core.tests.test_config.TestNoteSettingsBonusNameContract::test_legacy_bonus_name_is_still_an_alias_for_the_field (passed, pre_satisfied);... | - | 0.90 |
| C-6b919649 | notes › Note bonus is read from the documented MINTMORY_NOTE_BONUS › The documented name wins when both are set | covered | packages.core.tests.test_config.TestNoteSettingsBonusEnvGateContract::test_gate_documented_name_beats_legacy_alias (passed, pre_satisfied); packages.core.tests.test_config.TestNoteSettingsBonusNameContract::test_documented_bonus_name_beats_legacy_when_both_are_present (passed, pre_satisfied); packag... | - | 0.91 |
| C-e838bc72 | notes › Note bonus is read from the documented MINTMORY_NOTE_BONUS › Defaults, bounds and construction by field name | covered | packages.core.tests.test_config.TestNoteSettingsBonusEnvGateContract::test_gate_default_bounds_and_field_name_construction (passed, pre_satisfied); packages.core.tests.test_config.TestNoteSettingsBonusNameContract::test_bonus_default_bounds_and_keyword_construction (passed, pre_satisfied); packages.... | - | 0.91 |
| C-9d99d712 | notes › Note bonus is read from the documented MINTMORY_NOTE_BONUS › The other note knobs are unaffected | covered | packages.core.tests.test_config.TestNoteSettingsBonusEnvGateContract::test_gate_other_note_knobs_keep_their_names (passed, pre_satisfied); packages.core.tests.test_config.TestNoteSettingsBonusNameContract::test_other_note_knobs_are_unaffected_by_the_bonus_alias (passed, pre_satisfied); packages.core... | - | 0.76 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `docs/EXPERIMENTS.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-note-bonus-env-name/.l4/ledger/r-20261017T0237Z-d577.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/fix-note-bonus-env-name/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/core/src/mintmory/core/config.py` | core | relevant | named in the spec |
| `packages/core/tests/test_config.py` |  | relevant | named in the spec |
| `packages/core/tests/test_note_bonus_docs.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

1782 of 1896 passed, 0 failed, 0 errored, 114 skipped.
21 of 21 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-4685d347 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-f1c5c1d6 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6b919649 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e838bc72 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9d99d712 | ok | 0.760 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-4685d347 | notes › Note bonus is read from the documented MINTMORY_NOTE_BONUS › The documented name sets the bonus | pass | pass | the judge passed it and a discriminating test passes |
| C-f1c5c1d6 | notes › Note bonus is read from the documented MINTMORY_NOTE_BONUS › The legacy name still works | pass | pass | the judge passed it and a discriminating test passes |
| C-6b919649 | notes › Note bonus is read from the documented MINTMORY_NOTE_BONUS › The documented name wins when both are set | pass | pass | the judge passed it and a discriminating test passes |
| C-e838bc72 | notes › Note bonus is read from the documented MINTMORY_NOTE_BONUS › Defaults, bounds and construction by field name | pass | pass | the judge passed it and a discriminating test passes |
| C-9d99d712 | notes › Note bonus is read from the documented MINTMORY_NOTE_BONUS › The other note knobs are unaffected | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Redundant duplicate test classes: Four test classes in test_config.py assert the same contract and are mostly copies of each other. This inflates the suite and adds maintenance cost.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.core.tests.test_config.TestNoteSettingsBonusEnvGateContract::test_gate_default_bounds_and_field_name_construction` (task 4.1): passed
- `packages.core.tests.test_config.TestNoteSettingsBonusEnvGateContract::test_gate_documented_name_beats_legacy_alias` (task 4.1): passed
- `packages.core.tests.test_config.TestNoteSettingsBonusEnvGateContract::test_gate_documented_name_reaches_note_and_load_settings` (task 4.1): passed
- `packages.core.tests.test_config.TestNoteSettingsBonusEnvGateContract::test_gate_legacy_name_still_works_and_documented_name_wins` (task 4.1): passed
- `packages.core.tests.test_config.TestNoteSettingsBonusEnvGateContract::test_gate_other_note_knobs_keep_their_names` (task 4.1): passed
- `packages.core.tests.test_config.TestNoteSettingsBonusNameContract::test_bonus_default_bounds_and_keyword_construction` (task 2.1): passed
- `packages.core.tests.test_config.TestNoteSettingsBonusNameContract::test_documented_bonus_name_beats_legacy_when_both_are_present` (task 2.1): passed
- `packages.core.tests.test_config.TestNoteSettingsBonusNameContract::test_documented_bonus_name_is_read_by_note_and_load_settings` (task 2.1): passed
- `packages.core.tests.test_config.TestNoteSettingsBonusNameContract::test_legacy_bonus_name_is_still_an_alias_for_the_field` (task 2.1): passed
- `packages.core.tests.test_config.TestNoteSettingsBonusNameContract::test_other_note_knobs_are_unaffected_by_the_bonus_alias` (task 2.1): passed
- `packages.core.tests.test_config.TestNoteSettingsEnvNames::test_defaults_bounds_and_field_name_construction` (task 1.1): passed
- `packages.core.tests.test_config.TestNoteSettingsEnvNames::test_documented_name_sets_bonus` (task 1.1): passed
- `packages.core.tests.test_config.TestNoteSettingsEnvNames::test_documented_name_wins_when_both_set` (task 1.1): passed
- `packages.core.tests.test_config.TestNoteSettingsEnvNames::test_legacy_name_works_and_documented_name_wins` (task 1.1): passed
- `packages.core.tests.test_config.TestNoteSettingsEnvNames::test_other_note_knobs_unaffected` (task 1.1): passed
- `packages.core.tests.test_config.TestNoteSettingsReadmeDocumentedBonusName::test_default_bounds_and_keyword_construction` (task 3.1): passed
- `packages.core.tests.test_config.TestNoteSettingsReadmeDocumentedBonusName::test_documented_variable_wins_when_both_are_present` (task 3.1): passed
- `packages.core.tests.test_config.TestNoteSettingsReadmeDocumentedBonusName::test_legacy_alias_works_and_loses_to_the_documented_name` (task 3.1): passed
- `packages.core.tests.test_config.TestNoteSettingsReadmeDocumentedBonusName::test_other_note_knobs_unaffected_by_the_bonus_names` (task 3.1): passed
- `packages.core.tests.test_config.TestNoteSettingsReadmeDocumentedBonusName::test_readme_documented_variable_reaches_note_and_load_settings` (task 3.1): passed
- `packages.core.tests.test_note_bonus_docs.TestNoteBonusDocumentedInExperiments::test_experiments_documents_the_variable_config_reads` (task 3.2): passed
