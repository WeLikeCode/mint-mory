# Verification: openspec:add-telemetry-boundary-tracing: NEEDS_HUMAN (round 1)

traceability: 24/24 criteria covered by a discriminating test

- Base: `a424242ebe35f197f4950cbe2e4bc79cdb84025b`
- Head: `0d56fcce2308fe775f90ecef38323480f43131a9`
- Implementer profiles: deepseek, glm, deepseek-free, glm-free
- Judge: claude-judge (claude-sonnet-5-5), 2 call(s), prompt sha256 `1953c995a9b8648877650316bb10b15cc45dfe363d59673ba39a3ff7db4dff5c`
- Judge replies of claude-judge (this unit, all rounds): valid 0, repaired 0, retried 1, discarded 0; this round: retried
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared), glm-free zhipu (declared)
- Cost: $1.3640

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.5 | base merged: staging@a424242ebe as 0d56fcce23 (8 commits) |
| 1 | integrity | ok | 0.6 | 7 sub-checks (+1 unfrozen by human answers); scope: 25 changed file(s) |
| 2 | build | ok | 1.1 |  |
| 3 | tests | ok | 75.4 |  |
| 4 | traceability | ok | 0.1 | 24/24 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 2.1 | 24/24 criteria judged by jev |
| 9 | judge | ok | 40.2 | 2 call(s) |
| 10 | aggregation | ok | 0.0 | NEEDS_HUMAN |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261018T1738Z-091b/046-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261018T1738Z-091b/047-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261018T1738Z-091b/048-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261018T1738Z-091b/049-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261018T1738Z-091b/050-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 8 test file(s) compared with the base |
| red-green freeze | ok | 6 task(s): red and green compared (+1 unfrozen by human answers) |
| test path freeze | ok | 6 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | ok | 4 new suppression(s), 4 declared |
| tdd history | ok | 12 task(s); red tests passing at head: step 3 |

Declared suppressions:
- packages/api/src/mintmory/api/telemetry_middleware.py:41 # noqa: BLE001 (declared: deliberate broad catch: one telemetry step must never alter the request)
- packages/core/src/mintmory/core/telemetry.py:1120 # noqa: BLE001 (declared: Broad except is the point: a header injection helper must never raise into the caller.)
- packages/core/src/mintmory/core/telemetry.py:1138 # noqa: BLE001 (declared: Broad except is the point: context extraction must never raise into the caller.)
- packages/core/src/mintmory/core/telemetry.py:1166 # noqa: BLE001 (declared: record_histogram must never raise into the caller (spec: Middleware telemetry never alters a request).)

## Tests unfrozen by human answers (allowed, L4-IMP-002)

- packages/api/tests/test_telemetry_http.py (task 2.1, unfrozen by Q-001 (human))

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-dc87542c | observability › HTTP server spans continue the caller's trace › Incoming traceparent is continued | covered | packages.api.tests.test_telemetry_http::test_incoming_traceparent_is_continued (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_continue_the_incoming_traceparent (passed, zero_value); packages.core.tests.test_observability_distributed_tracing_docs::test_sectio... | - | 0.75 |
| C-30744114 | observability › HTTP server spans continue the caller's trace › Route template, not the raw path, names the span | covered | packages.api.tests.test_telemetry_http::test_route_template_names_the_span_not_the_raw_path (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_keep_the_route_template_not_the_raw_path (passed, zero_value) | - | 0.87 |
| C-7507adff | observability › How the middleware ends the server span › No route, and a method mismatch | covered | packages.api.tests.test_telemetry_http::test_no_route_and_method_mismatch (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_name_no_route_and_a_method_mismatch (passed, zero_value) | - | 0.89 |
| C-d6238220 | observability › How the middleware ends the server span › A route that raises before the response starts | covered | packages.api.tests.test_telemetry_http::test_route_raising_before_the_response_starts (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_mark_a_route_that_raises_before_the_response (passed, zero_value) | - | 0.89 |
| C-85b39250 | observability › How the middleware ends the server span › An exception after the response started | covered | packages.api.tests.test_telemetry_http::test_exception_after_the_response_started (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_handle_an_exception_after_the_response_started (passed, zero_value) | - | 0.93 |
| C-be1a4b66 | observability › How the middleware ends the server span › A 5xx answer without an exception | covered | packages.api.tests.test_telemetry_http::test_5xx_answer_without_an_exception (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_mark_a_5xx_answer_without_an_exception (passed, zero_value) | - | 0.93 |
| C-7ec77600 | observability › How the middleware ends the server span › A cancelled request, and no response at all | covered | packages.api.tests.test_telemetry_http::test_cancelled_request_and_no_response_at_all (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_leave_a_cancelled_and_a_silent_request_unmarked (passed, zero_value) | - | 0.94 |
| C-1420ab97 | observability › Middleware telemetry never alters a request › A malformed traceparent starts a new trace | covered | packages.api.tests.test_telemetry_http::test_malformed_traceparent_starts_a_new_trace (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_let_a_malformed_traceparent_start_a_new_trace (passed, zero_value); packages.core.tests.test_telemetry_header_helpers::test_e... | - | 0.88 |
| C-a2f61e7e | observability › Middleware telemetry never alters a request › A failing histogram record leaves the response unchanged | covered | packages.api.tests.test_telemetry_http::test_failing_histogram_record_leaves_the_response_unchanged (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_keep_the_response_when_the_histogram_record_fails (passed, zero_value); packages.core.tests.test_telemetry_reco... | - | 0.90 |
| C-5fd2f50f | observability › Middleware telemetry never alters a request › Failing span updates leave the response unchanged | covered | packages.api.tests.test_telemetry_http::test_failing_span_updates_leave_the_response_unchanged (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_keep_the_response_when_span_updates_fail (passed, zero_value) | - | 0.94 |
| C-d3c89585 | observability › Excluded HTTP paths › Health probes are not traced | covered | packages.api.tests.test_telemetry_http::test_health_probes_are_not_traced (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_skip_health_probes (passed, zero_value) | - | 0.86 |
| C-6b05011d | observability › Excluded HTTP paths › Excluded by the environment | covered | packages.api.tests.test_telemetry_http::test_excluded_by_the_environment (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_skip_paths_excluded_by_the_environment (passed, zero_value) | - | 0.91 |
| C-512ddc0c | observability › Excluded HTTP paths › A bad exclusion pattern is skipped | covered | packages.api.tests.test_telemetry_http::test_a_bad_exclusion_pattern_is_skipped (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_skip_a_bad_exclusion_pattern (passed, zero_value) | - | 0.74 |
| C-7409b7a7 | observability › HTTP server duration metric › Request duration recorded | covered | packages.api.tests.test_telemetry_http::test_request_duration_recorded (passed, zero_value); packages.api.tests.test_telemetry_http_middleware::test_safe_steps_record_the_request_duration (passed, zero_value); packages.core.tests.test_telemetry_record_histogram::test_record_histogram_drops_none_attr... | - | 0.89 |
| C-7d4fc8c6 | observability › MCP tool calls are traced once › The verified FastMCP version is installed | covered | packages.mcp.tests.test_telemetry_mcp::test_fastmcp_version_is_the_verified_one (passed, pre_satisfied, accepted by an agent through Q-005: the check was inconclusive) | - | 0.89 |
| C-811d0420 | observability › MCP tool calls are traced once › Tool call is one span with core spans below it | covered | packages.mcp.tests.test_telemetry_mcp::test_history_tool_call_is_one_server_span (passed, pre_satisfied); packages.mcp.tests.test_telemetry_mcp::test_tool_call_is_one_server_span_with_core_spans_below_it (passed, pre_satisfied) | - | 0.84 |
| C-313b2e72 | observability › MCP tool calls are traced once › A failing tool is marked | covered | packages.mcp.tests.test_telemetry_mcp::test_failing_tool_is_marked (passed, pre_satisfied) | - | 0.93 |
| C-b03582ac | observability › MCP tool calls are traced once › Tool arguments never reach telemetry | covered | packages.mcp.tests.test_telemetry_mcp::test_tool_arguments_never_reach_telemetry (passed, pre_satisfied) | - | 0.75 |
| C-da502b68 | observability › MCP tool calls are traced once › Context in `_meta` is continued | covered | packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_continues_a_trace (passed, red_assertion); packages.mcp.tests.test_telemetry_mcp::test_meta_traceparent_is_continued (passed, pre_satisfied) | - | 0.77 |
| C-fa4bc29e | observability › MCP tool calls are traced once › Tool spans follow a new init | covered | packages.mcp.tests.test_telemetry_mcp::test_tool_spans_follow_a_new_init (passed, pre_satisfied) | - | 0.91 |
| C-83e1a4e6 | observability › Outbound calls carry the trace context › LLM endpoint receives traceparent | covered | packages.core.tests.test_telemetry_header_helpers::test_inject_trace_headers_writes_the_current_span_into_the_carrier (passed, zero_value); packages.core.tests.test_telemetry_outbound::test_chat_endpoint_receives_the_span_traceparent (passed, red_assertion) | packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends (it traces 4 criteria (verifier.max_criteria_per_test=3)) | 0.94 |
| C-9970c315 | observability › Outbound calls carry the trace context › tracestate is forwarded, baggage is not | covered | packages.core.tests.test_telemetry_header_helpers::test_inject_trace_headers_forwards_tracestate_and_never_baggage (passed, zero_value); packages.core.tests.test_telemetry_outbound::test_chat_forwards_tracestate_and_never_baggage (passed, red_assertion) | packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends (it traces 4 criteria (verifier.max_criteria_per_test=3)) | 0.95 |
| C-d1b2babd | observability › Outbound calls carry the trace context › Embedding endpoints receive traceparent | covered | packages.core.tests.test_telemetry_outbound::test_embedding_endpoints_receive_the_embed_span_traceparent (passed, red_assertion) | packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends (it traces 4 criteria (verifier.max_criteria_per_test=3)) | 0.95 |
| C-c2076c0f | observability › Outbound calls carry the trace context › No header when telemetry is off | covered | packages.core.tests.test_telemetry_header_helpers::test_inject_trace_headers_off_leaves_the_carrier_untouched (passed, zero_value); packages.core.tests.test_telemetry_outbound::test_no_traceparent_when_telemetry_is_off (passed, red_assertion) | packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends (it traces 4 criteria (verifier.max_criteria_per_test=3)) | 0.94 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `docs/OBSERVABILITY.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-boundary-tracing/.l4/ledger/r-20261017T1947Z-9dba.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-boundary-tracing/.l4/ledger/r-20261017T2040Z-8cd4.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-boundary-tracing/.l4/ledger/r-20261018T1547Z-a017.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-boundary-tracing/.l4/ledger/r-20261018T1548Z-8982.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-boundary-tracing/.l4/ledger/r-20261018T1601Z-d1c5.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-boundary-tracing/.l4/ledger/r-20261018T1618Z-6c11.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-boundary-tracing/.l4/ledger/r-20261018T1632Z-40bf.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-boundary-tracing/.l4/ledger/r-20261018T1715Z-2ba2.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-boundary-tracing/.l4/ledger/r-20261018T1738Z-091b.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-boundary-tracing/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-boundary-tracing/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `packages/api/src/mintmory/api/app.py` | api | relevant | named in the spec |
| `packages/api/src/mintmory/api/telemetry_middleware.py` | api | relevant | module `api` is named in the spec |
| `packages/api/tests/test_telemetry_http.py` |  | relevant | new test file |
| `packages/api/tests/test_telemetry_http_middleware.py` |  | relevant | new test file |
| `packages/core/src/mintmory/core/embedder.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/llm.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/telemetry.py` | core | relevant | named in the spec |
| `packages/core/tests/test_observability_distributed_tracing_docs.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_embedder_network.py` |  | none | imports no module of the repository |
| `packages/core/tests/test_telemetry_header_helpers.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_outbound.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_record_histogram.py` |  | relevant | new test file |
| `packages/mcp/tests/test_telemetry_mcp.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

1914 of 2028 passed, 0 failed, 0 errored, 114 skipped.
51 of 51 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-dc87542c | ok | 0.750 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-30744114 | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7507adff | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d6238220 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-85b39250 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-be1a4b66 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7ec77600 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1420ab97 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a2f61e7e | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5fd2f50f | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d3c89585 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6b05011d | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-512ddc0c | ok | 0.740 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7409b7a7 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7d4fc8c6 | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-811d0420 | ok | 0.840 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-313b2e72 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b03582ac | ok | 0.750 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-da502b68 | ok | 0.770 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-fa4bc29e | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-83e1a4e6 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9970c315 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d1b2babd | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c2076c0f | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
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
- [minor, judge] Route object without path attribute not handled (spec gap) (criterion C-7507adff): In the middleware finally block, route.path is read outside _safe; a scope route lacking path would raise AttributeError.

## Needs a human

- the diff is longer than 120000 characters: the judge saw only the start

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.api.tests.test_telemetry_http::test_5xx_answer_without_an_exception` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_a_bad_exclusion_pattern_is_skipped` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_cancelled_request_and_no_response_at_all` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_exception_after_the_response_started` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_excluded_by_the_environment` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_failing_histogram_record_leaves_the_response_unchanged` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_failing_span_updates_leave_the_response_unchanged` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_health_probes_are_not_traced` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_incoming_traceparent_is_continued` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_malformed_traceparent_starts_a_new_trace` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_no_route_and_method_mismatch` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_request_duration_recorded` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_route_raising_before_the_response_starts` (task 2.1): passed
- `packages.api.tests.test_telemetry_http::test_route_template_names_the_span_not_the_raw_path` (task 2.1): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_continue_the_incoming_traceparent` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_handle_an_exception_after_the_response_started` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_keep_the_response_when_span_updates_fail` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_keep_the_response_when_the_histogram_record_fails` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_keep_the_route_template_not_the_raw_path` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_leave_a_cancelled_and_a_silent_request_unmarked` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_let_a_malformed_traceparent_start_a_new_trace` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_mark_a_5xx_answer_without_an_exception` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_mark_a_route_that_raises_before_the_response` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_name_no_route_and_a_method_mismatch` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_record_the_request_duration` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_skip_a_bad_exclusion_pattern` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_skip_health_probes` (task 2.2): passed
- `packages.api.tests.test_telemetry_http_middleware::test_safe_steps_skip_paths_excluded_by_the_environment` (task 2.2): passed
- `packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_continues_a_trace` (task 5.1): passed
- `packages.core.tests.test_observability_distributed_tracing_docs::test_section_4_documents_what_mintmory_sends` (task 5.1): passed
- `packages.core.tests.test_telemetry_header_helpers::test_extract_context_of_a_valid_traceparent_carries_its_trace` (task 1.1): passed
- `packages.core.tests.test_telemetry_header_helpers::test_extract_context_of_garbage_starts_a_new_trace` (task 1.1): passed
- `packages.core.tests.test_telemetry_header_helpers::test_inject_trace_headers_forwards_tracestate_and_never_baggage` (task 1.1): passed
- `packages.core.tests.test_telemetry_header_helpers::test_inject_trace_headers_off_leaves_the_carrier_untouched` (task 1.1): passed
- `packages.core.tests.test_telemetry_header_helpers::test_inject_trace_headers_writes_the_current_span_into_the_carrier` (task 1.1): passed
- `packages.core.tests.test_telemetry_outbound::test_chat_endpoint_receives_the_span_traceparent` (task 4.1): passed
- `packages.core.tests.test_telemetry_outbound::test_chat_forwards_tracestate_and_never_baggage` (task 4.1): passed
- `packages.core.tests.test_telemetry_outbound::test_embedding_endpoints_receive_the_embed_span_traceparent` (task 4.1): passed
- `packages.core.tests.test_telemetry_outbound::test_no_traceparent_when_telemetry_is_off` (task 4.1): passed
- `packages.core.tests.test_telemetry_record_histogram::test_record_histogram_drops_none_attributes` (task 1.3): passed
- `packages.core.tests.test_telemetry_record_histogram::test_record_histogram_exports_the_seconds_unit_and_explicit_bounds` (task 1.3): passed
- `packages.core.tests.test_telemetry_record_histogram::test_record_histogram_is_a_no_op_when_metrics_are_off` (task 1.3): passed
- `packages.core.tests.test_telemetry_record_histogram::test_record_histogram_never_raises` (task 1.3): passed
- `packages.core.tests.test_telemetry_record_histogram::test_record_histogram_passes_unit_and_boundaries_to_the_factory` (task 1.3): passed
- `packages.mcp.tests.test_telemetry_mcp::test_failing_tool_is_marked` (task 3.1): passed
- `packages.mcp.tests.test_telemetry_mcp::test_fastmcp_version_is_the_verified_one` (task 3.1): passed
- `packages.mcp.tests.test_telemetry_mcp::test_history_tool_call_is_one_server_span` (task 3.1): passed
- `packages.mcp.tests.test_telemetry_mcp::test_meta_traceparent_is_continued` (task 3.1): passed
- `packages.mcp.tests.test_telemetry_mcp::test_tool_arguments_never_reach_telemetry` (task 3.1): passed
- `packages.mcp.tests.test_telemetry_mcp::test_tool_call_is_one_server_span_with_core_spans_below_it` (task 3.1): passed
