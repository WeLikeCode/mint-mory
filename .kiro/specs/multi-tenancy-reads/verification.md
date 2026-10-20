# Verification: kiro:multi-tenancy-reads: PASS (round 1)

traceability: 22/22 criteria covered by a discriminating test

- Base: `628f23ef05819993917978e8b768171a94ab2674`
- Head: `bf77c3bd20441ffd04a20a8d4f1fc4680f18158f`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 3 call(s), judged in 2 parts, prompt sha256 `dd33aa1deabda11b2a37e8d416ebde0118d0d155276811ce0855add93b8980d9`
  - part 1: 8 file(s), 118901 characters, profile claude-judge, reply valid
  - part 2: 4 file(s), 33828 characters, profile claude-judge, reply retried
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 1, discarded 0; this round: retried
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $1.8758

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.0 | base merged: staging@628f23ef05 as bf77c3bd20 (1 commit) |
| 1 | integrity | ok | 126.2 | 10 sub-checks (+1 unfrozen by human answers); scope: 16 changed file(s) |
| 2 | build | ok | 3.5 |  |
| 3 | tests | ok | 54.8 |  |
| 4 | traceability | ok | 0.1 | 22/22 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 6.4 | 19/22 criteria judged by jev; the state does not fit 450 tokens even without the excerpt |
| 9 | judge | ok | 72.7 | 3 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261020T0218Z-fb76/122-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261020T0218Z-fb76/123-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261020T0218Z-fb76/124-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261020T0218Z-fb76/125-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261020T0218Z-fb76/126-test.log |

## Files by part

- part 1: packages/core/src/mintmory/core/hybrid_search.py (3567 characters)
- part 1: packages/core/tests/test_tenancy_search_reads.py (17505 characters)
- part 1: packages/core/tests/test_pg_tenancy.py (13241 characters)
- part 1: packages/core/src/mintmory/core/ports.py (9511 characters)
- part 1: packages/core/tests/test_tenancy_dreaming_reads.py (14091 characters)
- part 1: packages/core/tests/test_tenancy_reads.py (16260 characters)
- part 1: packages/core/tests/test_tenancy_reads_full_gate.py (7023 characters)
- part 1: packages/core/src/mintmory/core/storage.py (37703 characters)
- part 2: packages/core/tests/test_tenancy_list_reads.py (5359 characters)
- part 2: packages/core/tests/test_tenancy_sql_parity.py (13100 characters)
- part 2: packages/core/src/mintmory/core/storage_postgres.py (12878 characters)
- part 2: .kiro/specs/multi-tenancy-reads/tasks.md (2491 characters)

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
| tdd history | ok | 7 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2123 of 2123 base tests pass on the unit's code with its 6 test and support files at the base (base: base worktree) |

## Pre-existing tests changed with an allowance (L4-VER-031)

- packages/core/tests/test_tenancy_search_reads.py kept at head for the run (task 3: unfrozen by Q-001, Q-002, Q-003)

## Tests unfrozen by human answers (allowed, L4-IMP-002)

- packages/core/tests/test_tenancy_search_reads.py (task 3, unfrozen by Q-001, Q-002, Q-003 (human))

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-91dbbaaa | Req 1.1 | covered | packages.core.tests.test_tenancy_dreaming_reads::test_dreaming_read_signatures_declare_trailing_tenant_id (passed, zero_value); packages.core.tests.test_tenancy_dreaming_reads::test_get_anomaly_flagged_ids_is_tenant_scoped (passed, zero_value); packages.core.tests.test_tenancy_dreaming_reads::test_g... | - | - |
| C-a614e704 | Req 1.2 | covered | packages.core.tests.test_tenancy_reads::test_get_memory_is_tenant_scoped (passed, zero_value) | - | 0.78 |
| C-2f90553d | Req 1.3 | covered | packages.core.tests.test_tenancy_reads::test_get_stats_is_tenant_scoped (passed, zero_value) | - | 0.82 |
| C-826339bd | Req 1.4 | covered | packages.core.tests.test_tenancy_reads::test_list_summaries_is_tenant_scoped (passed, zero_value) | - | 0.78 |
| C-51a6a3d3 | Req 2.1 | covered | packages.core.tests.test_tenancy_search_reads::test_anchor_candidates_is_tenant_scoped_without_side_effects (passed, zero_value); packages.core.tests.test_tenancy_search_reads::test_phase_scores_and_load_memories_are_tenant_scoped (passed, zero_value); packages.core.tests.test_tenancy_search_reads::... | - | 0.90 |
| C-dea5cddd | Req 2.2 | covered | packages.core.tests.test_tenancy_sql_parity::test_scoped_reads_put_tenant_predicate_in_every_select (passed, pre_satisfied); packages.core.tests.test_tenancy_sql_parity::test_unscoped_reads_emit_todays_sql_without_tenant_predicate (passed, pre_satisfied) | - | 0.95 |
| C-35f462ba | Req 3.1 | covered | packages.core.tests.test_tenancy_search_reads::test_phase_scores_and_load_memories_are_tenant_scoped (passed, zero_value); packages.core.tests.test_tenancy_search_reads::test_search_scopes_results_session_and_sql_over_shared_entity (passed, zero_value) | - | 0.85 |
| C-791d3b0d | Req 3.2 | covered | packages.core.tests.test_tenancy_search_reads::test_fuse_and_search_stamps_tenant_and_drops_foreign_rows (passed, zero_value) | - | 0.89 |
| C-e72eb814 | Req 3.3 | covered | packages.core.tests.test_tenancy_search_reads::test_fuse_and_search_without_recording_returns_results_and_empty_session (passed, zero_value) | - | 0.84 |
| C-60cdc81b | Req 3.4 | covered | packages.core.tests.test_tenancy_search_reads::test_search_confined_to_inactive_or_missing_tenant_writes_nothing (passed, zero_value) | - | 0.93 |
| C-756ad7a3 | Req 3.5 | covered | packages.core.tests.test_tenancy_search_reads::test_unscoped_search_records_global_session_and_bumps_active_only (passed, zero_value) | - | 0.91 |
| C-ff7699dc | Req 3.6 | covered | packages.core.tests.test_tenancy_search_reads::test_search_confined_to_inactive_or_missing_tenant_writes_nothing (passed, zero_value); packages.core.tests.test_tenancy_search_reads::test_search_scopes_results_session_and_sql_over_shared_entity (passed, zero_value); packages.core.tests.test_tenancy_s... | - | 0.91 |
| C-1ee5de05 | Req 3.7 | covered | packages.core.tests.test_tenancy_search_reads::test_search_around_with_foreign_anchor_returns_only_tenant_rows (passed, zero_value) | - | 0.93 |
| C-42824265 | Req 3.8 | covered | packages.core.tests.test_tenancy_search_reads::test_anchor_candidates_is_tenant_scoped_without_side_effects (passed, zero_value) | - | 0.83 |
| C-12e05552 | Req 4.1 | covered | packages.core.tests.test_tenancy_list_reads::test_list_memories_is_tenant_scoped (passed, zero_value); packages.core.tests.test_tenancy_list_reads::test_list_memories_limit_semantics (passed, zero_value) | - | 0.66 |
| C-d318e454 | Req 4.2 | covered | packages.core.tests.test_tenancy_list_reads::test_list_memories_is_tenant_scoped (passed, zero_value) | - | 0.72 |
| C-96f1f808 | Req 4.3 | covered | packages.core.tests.test_tenancy_list_reads::test_memory_exists_with_content_is_scoped_for_the_copy (passed, pre_satisfied) | - | 0.72 |
| C-588818fc | Req 5.1 | covered | packages.core.tests.test_pg_tenancy::test_protocol_declares_tenant_read_signatures (passed, zero_value) | - | 0.67 |
| C-c6d483c5 | Req 5.2 | covered | packages.core.tests.test_pg_tenancy::test_pg_anchor_candidates_tenancy (passed, zero_value); packages.core.tests.test_pg_tenancy::test_pg_find_image_file_record_tenancy (passed, zero_value); packages.core.tests.test_pg_tenancy::test_pg_get_annotating_descriptions_tenancy (passed, zero_value); packag... | - | - |
| C-da381c66 | Req 5.3 | covered | packages.core.tests.test_pg_tenancy::test_pg_anchor_candidates_tenancy (passed, zero_value); packages.core.tests.test_pg_tenancy::test_pg_find_image_file_record_tenancy (passed, zero_value); packages.core.tests.test_pg_tenancy::test_pg_get_annotating_descriptions_tenancy (passed, zero_value); packag... | - | - |
| C-3028dfd4 | Req 6.1 | covered | packages.core.tests.test_tenancy_reads_full_gate::test_existing_callers_without_a_tenant_keep_unscoped_reads (passed, pre_satisfied); packages.core.tests.test_tenancy_reads_full_gate::test_existing_read_callers_can_keep_omitting_the_tenant (passed, pre_satisfied) | - | 0.82 |
| C-5ed1b587 | Req 6.2 | covered | packages.core.tests.test_tenancy_reads_full_gate::test_tenancy_reads_gate_commands_pass_without_external_services (passed, pre_satisfied); packages.core.tests.test_tenancy_reads_full_gate::test_tenancy_reads_gate_declares_every_required_command (passed, pre_satisfied) | - | 0.78 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `.kiro/specs/multi-tenancy-reads/.l4/ledger/r-20261019T2004Z-0e3d.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-reads/.l4/ledger/r-20261020T0204Z-bf5f.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-reads/.l4/ledger/r-20261020T0218Z-fb76.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-reads/questions.md` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/multi-tenancy-reads/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/core/src/mintmory/core/hybrid_search.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/ports.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/storage.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/storage_postgres.py` | core | relevant | named in the spec |
| `packages/core/tests/test_pg_tenancy.py` |  | relevant | named in the spec |
| `packages/core/tests/test_tenancy_dreaming_reads.py` |  | relevant | new test file |
| `packages/core/tests/test_tenancy_list_reads.py` |  | relevant | new test file |
| `packages/core/tests/test_tenancy_reads.py` |  | relevant | new test file |
| `packages/core/tests/test_tenancy_reads_full_gate.py` |  | relevant | new test file |
| `packages/core/tests/test_tenancy_search_reads.py` |  | relevant | new test file |
| `packages/core/tests/test_tenancy_sql_parity.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

2190 of 2304 passed, 0 failed, 0 errored, 114 skipped.
67 of 67 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-91dbbaaa | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-a614e704 | ok | 0.780 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2f90553d | ok | 0.820 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-826339bd | ok | 0.780 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-51a6a3d3 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-dea5cddd | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-35f462ba | ok | 0.850 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-791d3b0d | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e72eb814 | ok | 0.840 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-60cdc81b | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-756ad7a3 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ff7699dc | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1ee5de05 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-42824265 | ok | 0.830 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-12e05552 | ok | 0.660 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d318e454 | ok | 0.720 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-96f1f808 | ok | 0.720 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-588818fc | ok | 0.670 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c6d483c5 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-da381c66 | unavailable | - | - | jev | the state does not fit 450 tokens even without the excerpt |
| C-3028dfd4 | ok | 0.820 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5ed1b587 | ok | 0.780 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-91dbbaaa | Req 1.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-a614e704 | Req 1.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-2f90553d | Req 1.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-826339bd | Req 1.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-51a6a3d3 | Req 2.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-dea5cddd | Req 2.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-35f462ba | Req 3.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-791d3b0d | Req 3.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-e72eb814 | Req 3.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-60cdc81b | Req 3.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-756ad7a3 | Req 3.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-ff7699dc | Req 3.6 | pass | pass | the judge passed it and a discriminating test passes |
| C-1ee5de05 | Req 3.7 | pass | pass | the judge passed it and a discriminating test passes |
| C-42824265 | Req 3.8 | pass | pass | the judge passed it and a discriminating test passes |
| C-12e05552 | Req 4.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-d318e454 | Req 4.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-96f1f808 | Req 4.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-588818fc | Req 5.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-c6d483c5 | Req 5.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-da381c66 | Req 5.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-3028dfd4 | Req 6.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-5ed1b587 | Req 6.2 | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Postgres guard runs before empty-anchor early return (spec gap) (criterion C-c6d483c5): Postgres search_around calls the guard before the empty-anchor early return, so a non-global tenant raises even with no anchors.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.core.tests.test_pg_tenancy::test_pg_anchor_candidates_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_find_image_file_record_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_annotating_descriptions_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_annotating_notes_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_anomaly_flagged_ids_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_anomaly_high_staleness_useful_ids_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_anomaly_never_accessed_ids_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_existing_relates_to_pairs_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_flagged_memories_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_high_staleness_useful_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_links_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_memory_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_never_accessed_stale_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_rehabilitable_rows_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_session_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_stale_archivable_ids_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_get_stats_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_list_active_memory_ids_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_list_image_file_records_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_list_memories_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_list_notes_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_list_summaries_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_memory_exists_with_content_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_search_around_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_pg_search_tenancy` (task 6): passed
- `packages.core.tests.test_pg_tenancy::test_protocol_declares_tenant_read_signatures` (task 6): passed
- `packages.core.tests.test_tenancy_dreaming_reads::test_dreaming_read_signatures_declare_trailing_tenant_id` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_reads::test_get_anomaly_flagged_ids_is_tenant_scoped` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_reads::test_get_anomaly_high_staleness_useful_ids_is_tenant_scoped` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_reads::test_get_anomaly_never_accessed_ids_is_tenant_scoped` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_reads::test_get_existing_relates_to_pairs_is_tenant_scoped` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_reads::test_get_flagged_memories_is_tenant_scoped` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_reads::test_get_high_staleness_useful_is_tenant_scoped` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_reads::test_get_never_accessed_stale_is_tenant_scoped` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_reads::test_get_rehabilitable_rows_is_tenant_scoped` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_reads::test_get_stale_archivable_ids_is_tenant_scoped` (task 2): passed
- `packages.core.tests.test_tenancy_dreaming_reads::test_list_active_memory_ids_is_tenant_scoped` (task 2): passed
- `packages.core.tests.test_tenancy_list_reads::test_list_memories_is_tenant_scoped` (task 4): passed
- `packages.core.tests.test_tenancy_list_reads::test_list_memories_limit_semantics` (task 4): passed
- `packages.core.tests.test_tenancy_list_reads::test_memory_exists_with_content_is_scoped_for_the_copy` (task 4): passed
- `packages.core.tests.test_tenancy_reads::test_find_image_file_record_is_tenant_scoped` (task 1): passed
- `packages.core.tests.test_tenancy_reads::test_get_annotating_descriptions_is_tenant_scoped` (task 1): passed
- `packages.core.tests.test_tenancy_reads::test_get_annotating_notes_is_tenant_scoped` (task 1): passed
- `packages.core.tests.test_tenancy_reads::test_get_links_is_tenant_scoped` (task 1): passed
- `packages.core.tests.test_tenancy_reads::test_get_memory_is_tenant_scoped` (task 1): passed
- `packages.core.tests.test_tenancy_reads::test_get_session_is_tenant_scoped` (task 1): passed
- `packages.core.tests.test_tenancy_reads::test_get_stats_is_tenant_scoped` (task 1): passed
- `packages.core.tests.test_tenancy_reads::test_list_image_file_records_is_tenant_scoped` (task 1): passed
- `packages.core.tests.test_tenancy_reads::test_list_notes_is_tenant_scoped` (task 1): passed
- `packages.core.tests.test_tenancy_reads::test_list_summaries_is_tenant_scoped` (task 1): passed

## Guard events

- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
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
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/storage.py
- guard.violation: packages/core/src/mintmory/core/ports.py
- guard.violation: packages/core/src/mintmory/core/ports.py
