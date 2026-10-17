# Verification: openspec:add-telemetry-entry-points: PASS (round 1)

traceability: 8/8 criteria covered by a discriminating test

- Base: `0628584c680d3c1811e20668b27c84fec8d2118f`
- Head: `05a7345eac5b4c3c674d22177db5ee06ec662266`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `fcbcc8411956c892fd1311ad6f2f3c302ba6850b1a1c878c04d86bc8c40a7ffd`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.4801

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.4 | base staging@0628584c68 contained |
| 1 | integrity | ok | 0.4 | 7 sub-checks; scope: 17 changed file(s) |
| 2 | build | ok | 0.9 |  |
| 3 | tests | ok | 58.8 |  |
| 4 | traceability | ok | 0.1 | 8/8 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 0.7 | 8/8 criteria judged by jev |
| 9 | judge | ok | 12.7 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261017T0212Z-9f3b/043-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261017T0212Z-9f3b/044-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261017T0212Z-9f3b/045-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261017T0212Z-9f3b/046-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261017T0212Z-9f3b/047-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 9 test file(s) compared with the base |
| red-green freeze | ok | 3 task(s): red and green compared |
| test path freeze | ok | 3 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | ok | 4 new suppression(s), 4 declared |
| tdd history | ok | 7 task(s); red tests passing at head: step 3 |

Declared suppressions:
- packages/cli/tests/test_telemetry_cli.py:127 # noqa: B010 (declared: setattr with a constant name builds the fake uvicorn ModuleType that monkeypatch.setitem injects)
- packages/cli/tests/test_telemetry_cli.py:135 # noqa: B010 (declared: setattr with a constant name builds the fake mintmory.mcp.server ModuleType that monkeypatch.setitem injects)
- packages/cli/tests/test_telemetry_cli_entry_point.py:128 # noqa: B010 (declared: setattr with a constant name builds the fake uvicorn ModuleType that monkeypatch.setitem injects into sys.modules)
- packages/cli/tests/test_telemetry_cli_entry_point.py:136 # noqa: B010 (declared: setattr with a constant name builds the fake mintmory.mcp.server ModuleType that monkeypatch.setitem injects into sys.mo)

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-5d7fad0c | deployment › Telemetry activation at API startup › OTel stays off by default | covered | packages.api.tests.test_api_telemetry_gate::test_gate_api_uses_noop_shim_without_a_collector (passed, pre_satisfied); packages.api.tests.test_health_and_otel::test_api_startup_stays_off_by_default (passed, red_assertion); packages.api.tests.test_telemetry_deployment_entry_point::test_api_lifespan_ke... | - | 0.94 |
| C-59ff07c0 | deployment › Telemetry activation at API startup › OTel activates when enabled | covered | packages.api.tests.test_api_telemetry_gate::test_gate_api_enables_telemetry_when_configured (passed, pre_satisfied); packages.api.tests.test_health_and_otel::test_api_startup_activates_when_enabled (passed, red_assertion); packages.api.tests.test_telemetry_deployment_entry_point::test_api_lifespan_e... | - | 0.94 |
| C-5fc161bb | deployment › Telemetry activation at API startup › Shutdown flushes with a bound | covered | packages.api.tests.test_api_telemetry_gate::test_gate_api_shutdown_flushes_then_closes_store (passed, pre_satisfied); packages.api.tests.test_health_and_otel::test_lifespan_flushes_telemetry_before_closing_store (passed, red_assertion); packages.api.tests.test_telemetry_deployment_entry_point::test_... | - | 0.95 |
| C-ce57c578 | observability › Every entry point initialises telemetry once › CLI command is traced | covered | packages.cli.tests.test_cli_telemetry_gate::test_gate_cli_add_command_exports_span_as_cli_service (passed, pre_satisfied); packages.cli.tests.test_telemetry_cli::test_cli_command_is_traced (passed, red_assertion); packages.cli.tests.test_telemetry_cli_entry_point::test_add_span_reaches_the_collector... | - | 0.94 |
| C-5fc9c6f2 | observability › Every entry point initialises telemetry once › A telemetry failure does not stop a command | covered | packages.cli.tests.test_cli_telemetry_gate::test_gate_cli_command_survives_telemetry_init_failure (passed, pre_satisfied); packages.cli.tests.test_telemetry_cli::test_telemetry_failure_does_not_stop_a_command (passed, red_assertion); packages.cli.tests.test_telemetry_cli_entry_point::test_bad_otlp_t... | - | 0.94 |
| C-28b6e3fb | observability › Every entry point initialises telemetry once › An invalid unrelated setting does not break help | covered | packages.cli.tests.test_cli_telemetry_gate::test_gate_cli_help_survives_unrelated_invalid_setting (passed, pre_satisfied); packages.cli.tests.test_telemetry_cli::test_invalid_unrelated_setting_does_not_break_help (passed, red_assertion); packages.cli.tests.test_telemetry_cli_entry_point::test_unrela... | - | 0.90 |
| C-f0a8c0a2 | observability › Every entry point initialises telemetry once › serve and mcp-serve leave init to their servers | covered | packages.cli.tests.test_cli_telemetry_gate::test_gate_cli_serve_commands_do_not_initialise_telemetry (passed, pre_satisfied); packages.cli.tests.test_telemetry_cli::test_serve_and_mcp_serve_leave_init_to_their_servers (passed, red_assertion); packages.cli.tests.test_telemetry_cli_entry_point::test_s... | - | 0.93 |
| C-97901dac | observability › Every entry point initialises telemetry once › Stdio MCP servers initialise telemetry | covered | packages.mcp.tests.test_mcp_telemetry_gate::test_gate_history_mcp_server_main_initialises_and_serves (passed, pre_satisfied); packages.mcp.tests.test_mcp_telemetry_gate::test_gate_mcp_server_main_initialises_and_serves (passed, pre_satisfied); packages.mcp.tests.test_telemetry_entry_points::test_his... | packages.mcp.tests.test_telemetry_init::test_main_initialises_telemetry_before_serving (no proof that it discriminates (no red, audit or generated record)) | 0.92 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `openspec/changes/add-telemetry-entry-points/.l4/ledger/r-20261017T0137Z-49a4.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-entry-points/.l4/ledger/r-20261017T0212Z-9f3b.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-entry-points/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-entry-points/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/api/src/mintmory/api/app.py` | api | relevant | named in the spec |
| `packages/api/tests/test_api_telemetry_gate.py` |  | relevant | new test file |
| `packages/api/tests/test_health_and_otel.py` |  | relevant | named in the spec |
| `packages/api/tests/test_telemetry_deployment_entry_point.py` |  | relevant | new test file |
| `packages/cli/src/mintmory/cli/main.py` | cli | relevant | named in the spec |
| `packages/cli/tests/test_cli_telemetry_gate.py` |  | relevant | new test file |
| `packages/cli/tests/test_telemetry_cli.py` |  | relevant | new test file |
| `packages/cli/tests/test_telemetry_cli_entry_point.py` |  | relevant | new test file |
| `packages/mcp/src/mintmory/mcp/history_server.py` | mcp | relevant | named in the spec |
| `packages/mcp/src/mintmory/mcp/server.py` | mcp | relevant | named in the spec |
| `packages/mcp/tests/test_mcp_telemetry_gate.py` |  | relevant | new test file |
| `packages/mcp/tests/test_telemetry_entry_points.py` |  | relevant | new test file |
| `packages/mcp/tests/test_telemetry_init.py` |  | relevant | named in the spec |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

1761 of 1875 passed, 0 failed, 0 errored, 114 skipped.
26 of 26 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-5d7fad0c | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-59ff07c0 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5fc161bb | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ce57c578 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5fc9c6f2 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-28b6e3fb | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-f0a8c0a2 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-97901dac | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-5d7fad0c | deployment › Telemetry activation at API startup › OTel stays off by default | pass | pass | the judge passed it and a discriminating test passes |
| C-59ff07c0 | deployment › Telemetry activation at API startup › OTel activates when enabled | pass | pass | the judge passed it and a discriminating test passes |
| C-5fc161bb | deployment › Telemetry activation at API startup › Shutdown flushes with a bound | pass | pass | the judge passed it and a discriminating test passes |
| C-ce57c578 | observability › Every entry point initialises telemetry once › CLI command is traced | pass | pass | the judge passed it and a discriminating test passes |
| C-5fc9c6f2 | observability › Every entry point initialises telemetry once › A telemetry failure does not stop a command | pass | pass | the judge passed it and a discriminating test passes |
| C-28b6e3fb | observability › Every entry point initialises telemetry once › An invalid unrelated setting does not break help | pass | pass | the judge passed it and a discriminating test passes |
| C-f0a8c0a2 | observability › Every entry point initialises telemetry once › serve and mcp-serve leave init to their servers | pass | pass | the judge passed it and a discriminating test passes |
| C-97901dac | observability › Every entry point initialises telemetry once › Stdio MCP servers initialise telemetry | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, deterministic] a test is ignored as evidence (criterion C-97901dac): packages.mcp.tests.test_telemetry_init::test_main_initialises_telemetry_before_serving: no proof that it discriminates (no red, audit or generated record)
- [minor, judge] Duplicate re-pinned test modules: Three sets of near-identical tests (gate, entry_point, original) per scenario add maintenance noise without extra coverage.
- [minor, judge] Unspecified: callback runs for bare subcommand groups like history (spec gap) (criterion C-ce57c578): The spec does not pin behaviour for the history subcommand group.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.api.tests.test_api_telemetry_gate::test_gate_api_enables_telemetry_when_configured` (task 2.1): passed
- `packages.api.tests.test_api_telemetry_gate::test_gate_api_shutdown_flushes_then_closes_store` (task 2.1): passed
- `packages.api.tests.test_api_telemetry_gate::test_gate_api_uses_noop_shim_without_a_collector` (task 2.1): passed
- `packages.api.tests.test_health_and_otel::test_api_startup_activates_when_enabled` (task 1.3): passed
- `packages.api.tests.test_health_and_otel::test_api_startup_stays_off_by_default` (task 1.3): passed
- `packages.api.tests.test_health_and_otel::test_lifespan_flushes_telemetry_before_closing_store` (task 1.3): passed
- `packages.api.tests.test_telemetry_deployment_entry_point::test_api_lifespan_enables_telemetry_when_configured` (task 1.6): passed
- `packages.api.tests.test_telemetry_deployment_entry_point::test_api_lifespan_flushes_telemetry_then_closes_store` (task 1.6): passed
- `packages.api.tests.test_telemetry_deployment_entry_point::test_api_lifespan_keeps_telemetry_a_noop_without_a_collector` (task 1.6): passed
- `packages.cli.tests.test_cli_telemetry_gate::test_gate_cli_add_command_exports_span_as_cli_service` (task 2.1): passed
- `packages.cli.tests.test_cli_telemetry_gate::test_gate_cli_command_survives_telemetry_init_failure` (task 2.1): passed
- `packages.cli.tests.test_cli_telemetry_gate::test_gate_cli_help_survives_unrelated_invalid_setting` (task 2.1): passed
- `packages.cli.tests.test_cli_telemetry_gate::test_gate_cli_serve_commands_do_not_initialise_telemetry` (task 2.1): passed
- `packages.cli.tests.test_telemetry_cli::test_cli_command_is_traced` (task 1.1): passed
- `packages.cli.tests.test_telemetry_cli::test_invalid_unrelated_setting_does_not_break_help` (task 1.1): passed
- `packages.cli.tests.test_telemetry_cli::test_serve_and_mcp_serve_leave_init_to_their_servers` (task 1.1): passed
- `packages.cli.tests.test_telemetry_cli::test_telemetry_failure_does_not_stop_a_command` (task 1.1): passed
- `packages.cli.tests.test_telemetry_cli_entry_point::test_add_span_reaches_the_collector_under_the_cli_service_name` (task 1.2): passed
- `packages.cli.tests.test_telemetry_cli_entry_point::test_bad_otlp_timeout_still_lets_add_succeed` (task 1.2): passed
- `packages.cli.tests.test_telemetry_cli_entry_point::test_serve_commands_defer_telemetry_to_their_servers` (task 1.2): passed
- `packages.cli.tests.test_telemetry_cli_entry_point::test_unrelated_invalid_setting_does_not_break_command_help` (task 1.2): passed
- `packages.mcp.tests.test_mcp_telemetry_gate::test_gate_history_mcp_server_main_initialises_and_serves` (task 2.1): passed
- `packages.mcp.tests.test_mcp_telemetry_gate::test_gate_mcp_server_main_initialises_and_serves` (task 2.1): passed
- `packages.mcp.tests.test_telemetry_entry_points::test_history_mcp_server_main_initialises_telemetry_with_its_service_name` (task 1.4): passed
- `packages.mcp.tests.test_telemetry_entry_points::test_mcp_server_main_initialises_telemetry_with_its_service_name` (task 1.4): passed
- `packages.mcp.tests.test_telemetry_init::test_history_main_initialises_telemetry_before_serving` (task 1.5): passed

## Guard events

- guard.test_tamper: packages/mcp/tests/test_telemetry_init.py
