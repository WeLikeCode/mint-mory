# Verification: openspec:add-telemetry-boundary-tracing-followup-1: PASS (round 1)

traceability: 26/26 criteria covered by a discriminating test

- Base: `bf6b735983b8640876f469eafeaff9ddb5c92612`
- Head: `e9ca959da221acfb4eea0a3a4ac63cd3a6c5f274`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 2 call(s), prompt sha256 `df032d531dd0d2f121728b57c0f6d5cd41becc99b28e067bebae59abbaddbfd2`
- Judge replies of claude-judge (this unit, all rounds): valid 0, repaired 0, retried 1, discarded 0; this round: retried
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $1.0530

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.4 | base merged: staging@bf6b735983 as e9ca959da2 (6 commits) |
| 1 | integrity | ok | 0.3 | 7 sub-checks; scope: 17 changed file(s) |
| 2 | build | ok | 2.6 |  |
| 3 | tests | ok | 77.4 |  |
| 4 | traceability | ok | 0.2 | 26/26 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 3.4 | 26/26 criteria judged by jev |
| 9 | judge | ok | 40.8 | 2 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261019T0900Z-de8f/073-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261019T0900Z-de8f/074-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261019T0900Z-de8f/075-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261019T0900Z-de8f/076-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261019T0900Z-de8f/077-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 7 test file(s) compared with the base |
| red-green freeze | ok | 2 task(s): red and green compared |
| test path freeze | ok | 5 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 2 task(s); red tests passing at head: step 3 |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-76dc3cd2 | observability › Guard route.path and the status comparison in the middleware's finally — feedback FB-001 › Guard route.path and the status comparison in the middleware's finally | covered | packages.api.tests.test_telemetry_http_middleware::test_a_non_int_response_status_does_not_replace_the_app_outcome (passed, red_assertion); packages.api.tests.test_telemetry_http_middleware::test_a_route_without_a_path_does_not_replace_the_app_outcome (passed, red_assertion); packages.api.tests.test... | - | 0.94 |
| C-8c8c8cf4 | observability › Telemetry must not change what an LLM call raises: reading — feedback FB-002 › Telemetry must not change what an LLM call raises: reading | covered | packages.core.tests.test_telemetry_llm_errors::test_malformed_port_raises_the_pre_telemetry_exception[99999] (passed, red_assertion); packages.core.tests.test_telemetry_llm_errors::test_malformed_port_raises_the_pre_telemetry_exception[abc] (passed, red_assertion) | - | 0.93 |
| C-dc87542c | observability › HTTP server spans continue the caller's trace › Incoming traceparent is continued | covered | packages.api.tests.test_telemetry_http::test_incoming_traceparent_is_continued (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_continue_the_incoming_traceparent (passed, pass_to_pass); packages.core.tests.test_observability_distributed_tracing_docs::test_se... | - | 0.81 |
| C-30744114 | observability › HTTP server spans continue the caller's trace › Route template, not the raw path, names the span | covered | packages.api.tests.test_telemetry_http::test_route_template_names_the_span_not_the_raw_path (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_keep_the_route_template_not_the_raw_path (passed, pass_to_pass) | - | 0.91 |
| C-7507adff | observability › How the middleware ends the server span › No route, and a method mismatch | covered | packages.api.tests.test_telemetry_http::test_no_route_and_method_mismatch (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_name_no_route_and_a_method_mismatch (passed, pass_to_pass) | - | 0.91 |
| C-d6238220 | observability › How the middleware ends the server span › A route that raises before the response starts | covered | packages.api.tests.test_telemetry_http::test_route_raising_before_the_response_starts (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_mark_a_route_that_raises_before_the_response (passed, pass_to_pass) | - | 0.92 |
| C-85b39250 | observability › How the middleware ends the server span › An exception after the response started | covered | packages.api.tests.test_telemetry_http::test_exception_after_the_response_started (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_handle_an_exception_after_the_response_started (passed, pass_to_pass) | - | 0.94 |
| C-be1a4b66 | observability › How the middleware ends the server span › A 5xx answer without an exception | covered | packages.api.tests.test_telemetry_http::test_5xx_answer_without_an_exception (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_mark_a_5xx_answer_without_an_exception (passed, pass_to_pass) | - | 0.91 |
| C-7ec77600 | observability › How the middleware ends the server span › A cancelled request, and no response at all | covered | packages.api.tests.test_telemetry_http::test_cancelled_request_and_no_response_at_all (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_leave_a_cancelled_and_a_silent_request_unmarked (passed, pass_to_pass) | - | 0.94 |
| C-1420ab97 | observability › Middleware telemetry never alters a request › A malformed traceparent starts a new trace | covered | packages.api.tests.test_telemetry_http::test_malformed_traceparent_starts_a_new_trace (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_let_a_malformed_traceparent_start_a_new_trace (passed, pass_to_pass); packages.core.tests.test_telemetry_header_helpers::te... | - | 0.88 |
| C-a2f61e7e | observability › Middleware telemetry never alters a request › A failing histogram record leaves the response unchanged | covered | packages.api.tests.test_telemetry_http::test_failing_histogram_record_leaves_the_response_unchanged (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_keep_the_response_when_the_histogram_record_fails (passed, pass_to_pass); packages.core.tests.test_telemetry_... | - | 0.93 |
| C-5fd2f50f | observability › Middleware telemetry never alters a request › Failing span updates leave the response unchanged | covered | packages.api.tests.test_telemetry_http::test_failing_span_updates_leave_the_response_unchanged (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_keep_the_response_when_span_updates_fail (passed, pass_to_pass) | - | 0.94 |
| C-d3c89585 | observability › Excluded HTTP paths › Health probes are not traced | covered | packages.api.tests.test_telemetry_http::test_health_probes_are_not_traced (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_skip_health_probes (passed, pass_to_pass) | - | 0.91 |
| C-6b05011d | observability › Excluded HTTP paths › Excluded by the environment | covered | packages.api.tests.test_telemetry_http::test_excluded_by_the_environment (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_skip_paths_excluded_by_the_environment (passed, pass_to_pass) | - | 0.86 |
| C-512ddc0c | observability › Excluded HTTP paths › A bad exclusion pattern is skipped | covered | packages.api.tests.test_telemetry_http::test_a_bad_exclusion_pattern_is_skipped (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_skip_a_bad_exclusion_pattern (passed, pass_to_pass) | - | 0.83 |
| C-7409b7a7 | observability › HTTP server duration metric › Request duration recorded | covered | packages.api.tests.test_telemetry_http::test_request_duration_recorded (passed, pass_to_pass); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_record_the_request_duration (passed, pass_to_pass); packages.core.tests.test_telemetry_record_histogram::test_record_histogram_drops_none_... | - | 0.89 |
| C-7d4fc8c6 | observability › MCP tool calls are traced once › The verified FastMCP version is installed | covered | packages.mcp.tests.test_telemetry_mcp::test_fastmcp_version_is_the_verified_one (passed, pass_to_pass) | - | 0.58 |
| C-811d0420 | observability › MCP tool calls are traced once › Tool call is one span with core spans below it | covered | packages.mcp.tests.test_telemetry_mcp::test_history_tool_call_is_one_server_span (passed, pass_to_pass); packages.mcp.tests.test_telemetry_mcp::test_tool_call_is_one_server_span_with_core_spans_below_it (passed, pass_to_pass) | - | 0.76 |
| C-313b2e72 | observability › MCP tool calls are traced once › A failing tool is marked | covered | packages.mcp.tests.test_telemetry_mcp::test_failing_tool_is_marked (passed, pass_to_pass) | - | 0.81 |
| C-b03582ac | observability › MCP tool calls are traced once › Tool arguments never reach telemetry | covered | packages.mcp.tests.test_telemetry_mcp::test_tool_arguments_never_reach_telemetry (passed, pass_to_pass) | - | 0.85 |
| C-da502b68 | observability › MCP tool calls are traced once › Context in `_meta` is continued | covered | packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_continues_a_trace (passed, pass_to_pass); packages.mcp.tests.test_telemetry_mcp::test_meta_traceparent_is_continued (passed, pass_to_pass) | - | 0.86 |
| C-fa4bc29e | observability › MCP tool calls are traced once › Tool spans follow a new init | covered | packages.mcp.tests.test_telemetry_mcp::test_tool_spans_follow_a_new_init (passed, pass_to_pass) | - | 0.81 |
| C-83e1a4e6 | observability › Outbound calls carry the trace context › LLM endpoint receives traceparent | covered | packages.core.tests.test_telemetry_header_helpers::test_inject_trace_headers_writes_the_current_span_into_the_carrier (passed, pass_to_pass); packages.core.tests.test_telemetry_outbound::test_chat_endpoint_receives_the_span_traceparent (passed, pass_to_pass) | packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends (it traces 4 criteria (verifier.max_criteria_per_test=3)) | 0.92 |
| C-9970c315 | observability › Outbound calls carry the trace context › tracestate is forwarded, baggage is not | covered | packages.core.tests.test_telemetry_header_helpers::test_inject_trace_headers_forwards_tracestate_and_never_baggage (passed, pass_to_pass); packages.core.tests.test_telemetry_outbound::test_chat_forwards_tracestate_and_never_baggage (passed, pass_to_pass) | packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends (it traces 4 criteria (verifier.max_criteria_per_test=3)) | 0.94 |
| C-d1b2babd | observability › Outbound calls carry the trace context › Embedding endpoints receive traceparent | covered | packages.core.tests.test_telemetry_outbound::test_embedding_endpoints_receive_the_embed_span_traceparent (passed, pass_to_pass) | packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends (it traces 4 criteria (verifier.max_criteria_per_test=3)) | 0.94 |
| C-c2076c0f | observability › Outbound calls carry the trace context › No header when telemetry is off | covered | packages.core.tests.test_telemetry_header_helpers::test_inject_trace_headers_off_leaves_the_carrier_untouched (passed, pass_to_pass); packages.core.tests.test_telemetry_outbound::test_no_traceparent_when_telemetry_is_off (passed, pass_to_pass) | packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends (it traces 4 criteria (verifier.max_criteria_per_test=3)) | 0.92 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

Scope not judged: the spec names no path or module in backticks: nothing to compare against

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

1957 of 2071 passed, 0 failed, 0 errored, 114 skipped.
13 of 13 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-76dc3cd2 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8c8c8cf4 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-dc87542c | ok | 0.810 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-30744114 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7507adff | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d6238220 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-85b39250 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-be1a4b66 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7ec77600 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1420ab97 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a2f61e7e | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5fd2f50f | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d3c89585 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6b05011d | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-512ddc0c | ok | 0.830 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7409b7a7 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7d4fc8c6 | ok | 0.580 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-811d0420 | ok | 0.760 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-313b2e72 | ok | 0.810 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b03582ac | ok | 0.850 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-da502b68 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-fa4bc29e | ok | 0.810 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-83e1a4e6 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9970c315 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d1b2babd | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c2076c0f | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-76dc3cd2 | observability › Guard route.path and the status comparison in the middleware's finally — feedback FB-001 › Guard route.path and the status comparison in the middleware's finally | pass | pass | the judge passed it and a discriminating test passes |
| C-8c8c8cf4 | observability › Telemetry must not change what an LLM call raises: reading — feedback FB-002 › Telemetry must not change what an LLM call raises: reading | pass | pass | the judge passed it and a discriminating test passes |
| C-dc87542c | observability › HTTP server spans continue the caller's trace › Incoming traceparent is continued | pass | pass | the judge passed it and a discriminating test passes |
| C-30744114 | observability › HTTP server spans continue the caller's trace › Route template, not the raw path, names the span | pass | pass | the judge passed it and a discriminating test passes |
| C-7507adff | observability › How the middleware ends the server span › No route, and a method mismatch | pass | pass | the judge passed it and a discriminating test passes |
| C-d6238220 | observability › How the middleware ends the server span › A route that raises before the response starts | pass | pass | the judge passed it and a discriminating test passes |
| C-85b39250 | observability › How the middleware ends the server span › An exception after the response started | pass | pass | the judge passed it and a discriminating test passes |
| C-be1a4b66 | observability › How the middleware ends the server span › A 5xx answer without an exception | pass | pass | the judge passed it and a discriminating test passes |
| C-7ec77600 | observability › How the middleware ends the server span › A cancelled request, and no response at all | pass | pass | the judge passed it and a discriminating test passes |
| C-1420ab97 | observability › Middleware telemetry never alters a request › A malformed traceparent starts a new trace | pass | pass | the judge passed it and a discriminating test passes |
| C-a2f61e7e | observability › Middleware telemetry never alters a request › A failing histogram record leaves the response unchanged | pass | pass | the judge passed it and a discriminating test passes |
| C-5fd2f50f | observability › Middleware telemetry never alters a request › Failing span updates leave the response unchanged | pass | pass | the judge passed it and a discriminating test passes |
| C-d3c89585 | observability › Excluded HTTP paths › Health probes are not traced | pass | pass | the judge passed it and a discriminating test passes |
| C-6b05011d | observability › Excluded HTTP paths › Excluded by the environment | pass | pass | the judge passed it and a discriminating test passes |
| C-512ddc0c | observability › Excluded HTTP paths › A bad exclusion pattern is skipped | pass | pass | the judge passed it and a discriminating test passes |
| C-7409b7a7 | observability › HTTP server duration metric › Request duration recorded | pass | pass | the judge passed it and a discriminating test passes |
| C-7d4fc8c6 | observability › MCP tool calls are traced once › The verified FastMCP version is installed | pass | pass | the judge passed it and a discriminating test passes |
| C-811d0420 | observability › MCP tool calls are traced once › Tool call is one span with core spans below it | pass | pass | the judge passed it and a discriminating test passes |
| C-313b2e72 | observability › MCP tool calls are traced once › A failing tool is marked | pass | pass | the judge passed it and a discriminating test passes |
| C-b03582ac | observability › MCP tool calls are traced once › Tool arguments never reach telemetry | pass | pass | the judge passed it and a discriminating test passes |
| C-da502b68 | observability › MCP tool calls are traced once › Context in `_meta` is continued | pass | pass | the judge passed it and a discriminating test passes |
| C-fa4bc29e | observability › MCP tool calls are traced once › Tool spans follow a new init | pass | pass | the judge passed it and a discriminating test passes |
| C-83e1a4e6 | observability › Outbound calls carry the trace context › LLM endpoint receives traceparent | pass | pass | the judge passed it and a discriminating test passes |
| C-9970c315 | observability › Outbound calls carry the trace context › tracestate is forwarded, baggage is not | pass | pass | the judge passed it and a discriminating test passes |
| C-d1b2babd | observability › Outbound calls carry the trace context › Embedding endpoints receive traceparent | pass | pass | the judge passed it and a discriminating test passes |
| C-c2076c0f | observability › Outbound calls carry the trace context › No header when telemetry is off | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, deterministic] a test is ignored as evidence (criterion C-83e1a4e6): packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends: it traces 4 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-9970c315): packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends: it traces 4 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-d1b2babd): packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends: it traces 4 criteria (verifier.max_criteria_per_test=3)
- [minor, deterministic] a test is ignored as evidence (criterion C-c2076c0f): packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends: it traces 4 criteria (verifier.max_criteria_per_test=3)
- [minor, judge] Non-int status silently dropped (spec gap) (criterion C-76dc3cd2): A non-int status becomes None, so no status attribute is set. A bool passes the int guard.

## Feedback

- FB-001: addressed at e9ca959da2: telemetry_middleware.py finally block: route.path read through _safe(getattr...) with an isinstance str check, and status guarded by isinstance int. Tests in test_telemetry_http_middleware.py.
- FB-002: addressed at e9ca959da2: llm.py: `try: port = parsed.port except ValueError: port = None`. test_telemetry_llm_errors.py covers abc and 99999.
- FB-003: addressed at e9ca959da2: test_telemetry_outbound_current_context.py attaches the caller context as current around the chat request and around inject_trace_headers, and asserts no baggage header.
- FB-004: addressed at e9ca959da2: test_telemetry_mcp_tool_arguments_exported.py asserts exported spans and the tools/call SERVER spans exist before checking that the sentinels are absent.
- FB-005: addressed at e9ca959da2: The four items are covered by test_telemetry_http_middleware_specific_failures.py (specific exception classes), test_telemetry_outbound_embed_batch_headers.py (embed_batch extra_headers, and the off switch of inject_trace_headers) and test_telemetry_llm_default_port.py (80/443).

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.api.tests.test_telemetry_http_middleware::test_a_non_int_response_status_does_not_replace_the_app_outcome` (task 1.1): passed
- `packages.api.tests.test_telemetry_http_middleware::test_a_route_without_a_path_does_not_replace_the_app_outcome` (task 1.1): passed
- `packages.api.tests.test_telemetry_http_middleware::test_a_route_without_a_path_keeps_the_apps_exception` (task 1.1): passed
- `packages.core.tests.test_telemetry_llm_errors::test_malformed_port_raises_the_pre_telemetry_exception[99999]` (task 1.2): passed
- `packages.core.tests.test_telemetry_llm_errors::test_malformed_port_raises_the_pre_telemetry_exception[abc]` (task 1.2): passed
