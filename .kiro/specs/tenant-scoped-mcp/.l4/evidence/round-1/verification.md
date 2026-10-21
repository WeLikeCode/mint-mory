# Verification: kiro:tenant-scoped-mcp: PASS (round 1)

traceability: 25/25 criteria covered by a discriminating test

- Base: `14bde5a778bc68a9a0d08404c16e119a3215417d`
- Head: `86c82e75441197b6ad1501b6e9c477c861a64b7c`
- Implementer profiles: deepseek, glm, deepseek-free
- Judge: claude-judge (claude-sonnet-5-5), 2 call(s), prompt sha256 `b91f9e435980dbfa9d68eabc6ee22f53dca669fecf2cec84c2003eb2843f3cb5`
- Judge replies of claude-judge (this unit, all rounds): valid 0, repaired 0, retried 1, discarded 0; this round: retried
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared)
- Cost: $1.4230

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.0 | base staging@14bde5a778 contained |
| 1 | integrity | ok | 202.1 | 10 sub-checks; scope: 14 changed file(s) |
| 2 | build | ok | 4.5 |  |
| 3 | tests | ok | 94.6 |  |
| 4 | traceability | ok | 0.1 | 25/25 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 3.9 | 25/25 criteria judged by jev |
| 9 | judge | ok | 47.8 | 2 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261020T2352Z-c165/058-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261020T2352Z-c165/059-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261020T2352Z-c165/060-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261020T2352Z-c165/061-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261020T2352Z-c165/062-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 8 test file(s) compared with the base (+1 allowed, listed) |
| red-green freeze | ok | 5 task(s): red and green compared |
| test path freeze | ok | 5 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| gate configuration | skipped | no gate or runner configuration file changed |
| test awareness | ok | no production line reacts to the test run |
| suppressions | ok | 1 new suppression(s), 1 declared |
| tdd history | ok | 6 task(s); red tests passing at head: step 3 |
| pre-existing tests still pass | ok | 2281 of 2281 base tests pass on the unit's code with its 7 test and support files at the base (base: base worktree) |

Declared suppressions:
- packages/mcp/tests/test_mcp_tenancy_capabilities.py:48 # type: ignore[union-attr] (declared: read_resource content items are typed as TextResourceContents | BlobResourceContents; this test reads the text variant, )

## Pre-existing tests changed with an allowance (L4-VER-031)

- packages/mcp/tests/test_tools.py::test_all_tools_registered changed (task 4: unfrozen by Q-001)
- packages/mcp/tests/test_tools.py kept at head for the run (task 4: unfrozen by Q-001)

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-782096db | Req 1.1 | covered | packages.mcp.tests.test_mcp_tenancy::test_mcp_settings_defaults_to_empty_tenant (passed, zero_value); packages.mcp.tests.test_mcp_tenancy::test_mcp_settings_reads_tenant_from_prefixed_env (passed, zero_value) | - | 0.97 |
| C-8da08d08 | Req 1.2 | covered | packages.mcp.tests.test_mcp_tenancy::test_main_cli_tenant_overrides_env (passed, zero_value); packages.mcp.tests.test_mcp_tenancy::test_main_inactive_tenant_starts_and_warns (passed, zero_value); packages.mcp.tests.test_mcp_tenancy::test_main_invalid_tenant_exits_one_without_running (passed, zero_va... | - | 0.92 |
| C-3f8c9acb | Req 1.3 | covered | packages.mcp.tests.test_mcp_tenancy::test_bootstrap_scope_global_needs_no_tenant_row (passed, zero_value); packages.mcp.tests.test_mcp_tenancy::test_bootstrap_scope_missing_tenant_raises_and_never_creates_it (passed, zero_value); packages.mcp.tests.test_mcp_tenancy::test_bootstrap_scope_rejects_inva... | - | 0.92 |
| C-5a923d15 | Req 1.4 | covered | packages.mcp.tests.test_mcp_tenancy::test_main_cli_tenant_overrides_env (passed, zero_value); packages.mcp.tests.test_mcp_tenancy::test_main_inactive_tenant_starts_and_warns (passed, zero_value); packages.mcp.tests.test_mcp_tenancy::test_main_invalid_tenant_exits_one_without_running (passed, zero_va... | - | 0.90 |
| C-70a0d49a | Req 1.5 | covered | packages.mcp.tests.test_mcp_tenancy::test_effective_tenant_maps_global_to_none_and_named_scope_to_itself (passed, zero_value); packages.mcp.tests.test_mcp_tenancy::test_scope_tenant_defaults_to_global_at_import (passed, zero_value) | - | 0.83 |
| C-f37e9647 | Req 1.6 | covered | packages.mcp.tests.test_mcp_tenancy::test_main_cli_tenant_overrides_env (passed, zero_value); packages.mcp.tests.test_mcp_tenancy::test_main_inactive_tenant_starts_and_warns (passed, zero_value); packages.mcp.tests.test_mcp_tenancy::test_main_invalid_tenant_exits_one_without_running (passed, zero_va... | - | 0.95 |
| C-3a9634d3 | Req 2.1 | covered | packages.mcp.tests.test_mcp_tenancy::test_read_tools_pass_the_resolved_tenant[acme-acme] (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy::test_read_tools_pass_the_resolved_tenant[global-None] (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy_writes::test_create_modify_and_dre... | - | 0.88 |
| C-6530b3da | Req 2.2 | covered | packages.mcp.tests.test_mcp_tenancy_directory::test_tool_inventory_matches_declared_tenant_scope (passed, red_assertion) | - | 0.87 |
| C-64910e2d | Req 2.3 | covered | packages.mcp.tests.test_mcp_tenancy_writes::test_tenant_error_from_a_tool_surfaces_as_a_tool_error (passed, red_assertion) | - | 0.92 |
| C-8b67e092 | Req 3.1 | covered | packages.mcp.tests.test_mcp_tenancy::test_named_scope_reads_are_confined_to_the_tenant (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy_writes::test_global_scope_reads_span_tenants_and_creates_stay_global (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy_writes::test_global_sc... | - | 0.89 |
| C-8f404a82 | Req 3.2 | covered | packages.mcp.tests.test_mcp_tenancy_writes::test_named_scope_scenario_reads_writes_and_dream_stay_in_tenant (passed, red_assertion) | - | 0.93 |
| C-38da7fdc | Req 4.1 | covered | packages.mcp.tests.test_mcp_tenancy::test_global_scope_reads_span_every_tenant (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy_writes::test_global_scope_reads_span_tenants_and_creates_stay_global (passed, red_assertion) | - | 0.83 |
| C-8d39f34c | Req 4.2 | covered | packages.mcp.tests.test_mcp_tenancy_writes::test_global_scope_scenario_spans_tenants_and_dreams_each (passed, red_assertion) | - | 0.91 |
| C-606a0944 | Req 5.1 | covered | packages.mcp.tests.test_mcp_tenancy_directory::test_tenant_create_in_global_scope_returns_the_stored_tenant (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy_directory::test_tenant_create_in_named_scope_does_not_change_the_scope (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy... | - | 0.92 |
| C-294c313a | Req 5.2 | covered | packages.mcp.tests.test_mcp_tenancy_directory::test_tenant_list_returns_every_tenant_in_global_scope (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy_directory::test_tenant_list_returns_every_tenant_in_named_scope (passed, red_assertion) | - | 0.85 |
| C-d8d0a9d2 | Req 5.3 | covered | packages.mcp.tests.test_mcp_tenancy_directory::test_tenant_create_in_global_scope_returns_the_stored_tenant (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy_directory::test_tenant_create_in_named_scope_does_not_change_the_scope (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy... | - | 0.92 |
| C-aa92a5b1 | Req 6.1 | covered | packages.mcp.tests.test_mcp_tenancy_directory::test_no_tool_exposes_a_tenant_selector (passed, red_assertion) | - | 0.93 |
| C-d9314674 | Req 7.1 | covered | packages.mcp.tests.test_mcp_tenancy_capabilities::test_capabilities_fallback_global_scope (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy_capabilities::test_capabilities_fallback_named_scope (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy_capabilities::test_capabilities_glo... | - | 0.93 |
| C-e0e1d349 | Req 7.2 | covered | packages.mcp.tests.test_mcp_tenancy_capabilities::test_instructions_end_with_tenancy_sentence (passed, red_assertion) | - | 0.94 |
| C-e9fa90c0 | Req 8.1 | covered | packages.mcp.tests.test_mcp_tenancy_writes::test_deactivated_named_scope_serves_reads_and_writes_raise (passed, red_assertion); packages.mcp.tests.test_mcp_tenancy_writes::test_global_scope_modification_of_inactive_tenant_row_is_rejected (passed, red_assertion) | - | 0.91 |
| C-3d329b68 | Req 8.2 | covered | packages.mcp.tests.test_mcp_tenancy_writes::test_global_scope_modification_of_inactive_tenant_row_is_rejected (passed, red_assertion) | - | 0.90 |
| C-c92a2d86 | Req 8.3 | covered | packages.mcp.tests.test_mcp_tenancy_directory::test_concurrent_tenant_create_returns_the_same_single_row (passed, red_assertion) | - | 0.89 |
| C-ac779f2c | Req 9.1 | covered | packages.mcp.tests.test_mcp_tenancy_fixtures::test_acme_client_fixture_bootstraps_the_named_scope (passed, pre_satisfied); packages.mcp.tests.test_mcp_tenancy_fixtures::test_acme_client_fixture_teardown_restores_scope_and_store (passed, pre_satisfied); packages.mcp.tests.test_mcp_tenancy_fixtures::t... | - | 0.89 |
| C-7b6a9a1f | Req 9.2 | covered | tests.integration.test_tenancy_mcp_integration::test_one_sqlite_file_switches_between_acme_and_global (passed, pre_satisfied) | - | 0.92 |
| C-533591f4 | Req 9.3 | covered | tests.integration.test_tenancy_mcp_gates::test_scoped_tenancy_runs_on_sqlite_without_network (passed, pre_satisfied) | - | 0.60 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `.kiro/specs/tenant-scoped-mcp/.l4/ledger/r-20261020T2148Z-440a.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/tenant-scoped-mcp/.l4/ledger/r-20261020T2352Z-c165.jsonl` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/tenant-scoped-mcp/questions.md` |  | none | exempt: harness, spec or documentation path |
| `.kiro/specs/tenant-scoped-mcp/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/core/src/mintmory/core/config.py` | core | relevant | named in the spec |
| `packages/mcp/src/mintmory/mcp/server.py` | mcp | relevant | named in the spec |
| `packages/mcp/tests/test_mcp_tenancy.py` |  | relevant | new test file |
| `packages/mcp/tests/test_mcp_tenancy_capabilities.py` |  | relevant | new test file |
| `packages/mcp/tests/test_mcp_tenancy_directory.py` |  | relevant | new test file |
| `packages/mcp/tests/test_mcp_tenancy_fixtures.py` |  | relevant | new test file |
| `packages/mcp/tests/test_mcp_tenancy_writes.py` |  | relevant | new test file |
| `packages/mcp/tests/test_tools.py` |  | relevant | named in the spec |
| `tests/integration/test_tenancy_mcp_gates.py` |  | relevant | new test file |
| `tests/integration/test_tenancy_mcp_integration.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

2328 of 2442 passed, 0 failed, 0 errored, 114 skipped.
47 of 47 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-782096db | ok | 0.970 | jev-1.13.0 | jev | - |
| C-8da08d08 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3f8c9acb | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5a923d15 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-70a0d49a | ok | 0.830 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f37e9647 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3a9634d3 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6530b3da | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-64910e2d | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8b67e092 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8f404a82 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-38da7fdc | ok | 0.830 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8d39f34c | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-606a0944 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-294c313a | ok | 0.850 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d8d0a9d2 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-aa92a5b1 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d9314674 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e0e1d349 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e9fa90c0 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3d329b68 | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c92a2d86 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ac779f2c | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7b6a9a1f | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-533591f4 | ok | 0.600 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-782096db | Req 1.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-8da08d08 | Req 1.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-3f8c9acb | Req 1.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-5a923d15 | Req 1.4 | pass | pass | the judge passed it and a discriminating test passes |
| C-70a0d49a | Req 1.5 | pass | pass | the judge passed it and a discriminating test passes |
| C-f37e9647 | Req 1.6 | pass | pass | the judge passed it and a discriminating test passes |
| C-3a9634d3 | Req 2.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-6530b3da | Req 2.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-64910e2d | Req 2.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-8b67e092 | Req 3.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-8f404a82 | Req 3.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-38da7fdc | Req 4.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-8d39f34c | Req 4.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-606a0944 | Req 5.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-294c313a | Req 5.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-d8d0a9d2 | Req 5.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-aa92a5b1 | Req 6.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-d9314674 | Req 7.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-e0e1d349 | Req 7.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-e9fa90c0 | Req 8.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-3d329b68 | Req 8.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-c92a2d86 | Req 8.3 | pass | pass | the judge passed it and a discriminating test passes |
| C-ac779f2c | Req 9.1 | pass | pass | the judge passed it and a discriminating test passes |
| C-7b6a9a1f | Req 9.2 | pass | pass | the judge passed it and a discriminating test passes |
| C-533591f4 | Req 9.3 | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Empty --tenant falls through to env/global (spec gap) (criterion C-8da08d08): `args.tenant or McpSettings().tenant or TENANT_GLOBAL` treats `--tenant ''` as unset; not pinned by a scenario.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.mcp.tests.test_mcp_tenancy::test_bootstrap_scope_global_needs_no_tenant_row` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_bootstrap_scope_missing_tenant_raises_and_never_creates_it` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_bootstrap_scope_rejects_invalid_id_before_opening_the_store` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_bootstrap_scope_sets_an_existing_active_tenant` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_bootstrap_scope_warns_and_continues_for_inactive_tenant` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_effective_tenant_maps_global_to_none_and_named_scope_to_itself` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_global_scope_reads_span_every_tenant` (task 2): passed
- `packages.mcp.tests.test_mcp_tenancy::test_main_cli_tenant_overrides_env` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_main_inactive_tenant_starts_and_warns` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_main_invalid_tenant_exits_one_without_running` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_main_missing_tenant_exits_one_without_running` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_main_sse_bootstraps_then_runs_on_the_requested_port` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_main_uses_existing_tenant_from_env` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_main_without_option_or_env_uses_global_scope` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_mcp_settings_defaults_to_empty_tenant` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_mcp_settings_reads_tenant_from_prefixed_env` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy::test_named_scope_reads_are_confined_to_the_tenant` (task 2): passed
- `packages.mcp.tests.test_mcp_tenancy::test_read_tools_pass_the_resolved_tenant[acme-acme]` (task 2): passed
- `packages.mcp.tests.test_mcp_tenancy::test_read_tools_pass_the_resolved_tenant[global-None]` (task 2): passed
- `packages.mcp.tests.test_mcp_tenancy::test_scope_tenant_defaults_to_global_at_import` (task 1): passed
- `packages.mcp.tests.test_mcp_tenancy_capabilities::test_capabilities_fallback_global_scope` (task 5): passed
- `packages.mcp.tests.test_mcp_tenancy_capabilities::test_capabilities_fallback_named_scope` (task 5): passed
- `packages.mcp.tests.test_mcp_tenancy_capabilities::test_capabilities_global_scope_reports_global_and_not_scoped` (task 5): passed
- `packages.mcp.tests.test_mcp_tenancy_capabilities::test_capabilities_named_scope_reports_tenant_and_scoped` (task 5): passed
- `packages.mcp.tests.test_mcp_tenancy_capabilities::test_instructions_end_with_tenancy_sentence` (task 5): passed
- `packages.mcp.tests.test_mcp_tenancy_directory::test_concurrent_tenant_create_returns_the_same_single_row` (task 4): passed
- `packages.mcp.tests.test_mcp_tenancy_directory::test_no_tool_exposes_a_tenant_selector` (task 4): passed
- `packages.mcp.tests.test_mcp_tenancy_directory::test_tenant_create_in_global_scope_returns_the_stored_tenant` (task 4): passed
- `packages.mcp.tests.test_mcp_tenancy_directory::test_tenant_create_in_named_scope_does_not_change_the_scope` (task 4): passed
- `packages.mcp.tests.test_mcp_tenancy_directory::test_tenant_create_invalid_id_surfaces_as_a_tool_error` (task 4): passed
- `packages.mcp.tests.test_mcp_tenancy_directory::test_tenant_create_is_idempotent_and_keeps_the_existing_row` (task 4): passed
- `packages.mcp.tests.test_mcp_tenancy_directory::test_tenant_list_returns_every_tenant_in_global_scope` (task 4): passed
- `packages.mcp.tests.test_mcp_tenancy_directory::test_tenant_list_returns_every_tenant_in_named_scope` (task 4): passed
- `packages.mcp.tests.test_mcp_tenancy_directory::test_tool_inventory_matches_declared_tenant_scope` (task 4): passed
- `packages.mcp.tests.test_mcp_tenancy_fixtures::test_acme_client_fixture_bootstraps_the_named_scope` (task 6): passed
- `packages.mcp.tests.test_mcp_tenancy_fixtures::test_acme_client_fixture_teardown_restores_scope_and_store` (task 6): passed
- `packages.mcp.tests.test_mcp_tenancy_fixtures::test_mcp_client_fixture_starts_in_the_global_scope` (task 6): passed
- `packages.mcp.tests.test_mcp_tenancy_writes::test_create_modify_and_dream_tools_pass_the_resolved_tenant` (task 3): passed
- `packages.mcp.tests.test_mcp_tenancy_writes::test_deactivated_named_scope_serves_reads_and_writes_raise` (task 3): passed
- `packages.mcp.tests.test_mcp_tenancy_writes::test_global_scope_modification_of_inactive_tenant_row_is_rejected` (task 3): passed
- `packages.mcp.tests.test_mcp_tenancy_writes::test_global_scope_reads_span_tenants_and_creates_stay_global` (task 3): passed
- `packages.mcp.tests.test_mcp_tenancy_writes::test_global_scope_scenario_spans_tenants_and_dreams_each` (task 3): passed
- `packages.mcp.tests.test_mcp_tenancy_writes::test_named_scope_scenario_reads_writes_and_dream_stay_in_tenant` (task 3): passed
- `packages.mcp.tests.test_mcp_tenancy_writes::test_named_scope_writes_are_stamped_and_foreign_ids_are_not_found` (task 3): passed
- `packages.mcp.tests.test_mcp_tenancy_writes::test_tenant_error_from_a_tool_surfaces_as_a_tool_error` (task 3): passed
- `tests.integration.test_tenancy_mcp_gates::test_scoped_tenancy_runs_on_sqlite_without_network` (task 6): passed
- `tests.integration.test_tenancy_mcp_integration::test_one_sqlite_file_switches_between_acme_and_global` (task 6): passed

## Guard events

- guard.test_tamper: packages/mcp/tests/test_tools.py
