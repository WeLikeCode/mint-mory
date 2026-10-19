# Verification: openspec:add-local-observability-stack: PASS (round 6)

traceability: 15/15 criteria covered by a discriminating test

- Base: `f29487b0b8be568c91a2d400927d43a372d26eca`
- Head: `5e51fdc0edc95ce0bd889a538c31f298b3a19436`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `8385dd6a6c6b93714e83ff88d99d542afec741ecefaa6c252422251785a500bb`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.6149

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 1.6 | base staging@f29487b0b8 contained |
| 1 | integrity | ok | 0.6 | 7 sub-checks; scope: 53 changed file(s) |
| 2 | build | ok | 19.1 |  |
| 3 | tests | ok | 74.0 |  |
| 4 | traceability | ok | 177.4 | 15/15 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 1.2 | 15/15 criteria judged by jev |
| 9 | judge | ok | 27.6 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261019T0432Z-4d29/001-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261019T0432Z-4d29/002-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261019T0432Z-4d29/003-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261019T0432Z-4d29/004-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261019T0432Z-4d29/005-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 6 test file(s) compared with the base |
| red-green freeze | ok | 5 task(s): red and green compared |
| test path freeze | ok | 8 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | ok | 1 new suppression(s), 1 declared |
| tdd history | ok | 14 task(s); red tests passing at head: step 3 |

Declared suppressions:
- packages/cli/src/mintmory/cli/main.py:480 # noqa: BLE001 (declared: doctor must report telemetry status, not raise; matches the surrounding doctor rows.)

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-1ee679bf | observability › Local observability stack › Stack definition is pinned and configurable | covered | tests.integration.test_observability_stack::test_jaeger_serves_ui_without_publishing_its_otlp_ports (passed, red_assertion); tests.integration.test_observability_stack::test_stack_defines_collector_jaeger_and_prometheus (passed, red_assertion); tests.integration.test_observability_stack::test_stack_... | - | 0.93 |
| C-59c20d3b | observability › Local observability stack › Collector routes each signal | covered | tests.integration.test_observability_stack::test_collector_metrics_pipeline_is_scraped_by_prometheus (passed, red_assertion); tests.integration.test_observability_stack::test_collector_otlp_receiver_listens_on_grpc_and_http (passed, red_assertion); tests.integration.test_observability_stack::test_co... | - | 0.92 |
| C-44862bf2 | observability › Local observability stack › The environment example documents every variable | covered | tests.integration.test_observability_stack::test_env_example_documents_every_compose_variable (passed, red_assertion) | - | 0.82 |
| C-d797e1ac | observability › Local observability stack › Compose accepts the file | covered | tests.integration.test_observability_stack::test_docker_compose_config_accepts_the_stack (passed, red_assertion) | tests.integration.test_observability_toolchain::test_docker_compose_config_accepts_the_stack_without_a_skip (passes against the zero values and on the base) | 0.95 |
| C-990f7ec4 | observability › MintMory API service in the local stack › API profile is wired to the collector | covered | tests.integration.test_observability_stack::test_api_profile_is_wired_to_the_collector (passed, red_assertion) | - | 0.72 |
| C-2b1a1bac | observability › Telemetry status in doctor › Doctor without a collector | covered | packages.cli.tests.test_cli::test_doctor_telemetry_without_a_collector (passed, zero_value) | - | 0.91 |
| C-93f4f5b3 | observability › Telemetry status in doctor › Doctor with an endpoint it cannot parse | covered | packages.cli.tests.test_cli::test_doctor_telemetry_endpoint_it_cannot_parse (passed, zero_value) | - | 0.85 |
| C-8b3b5845 | observability › Telemetry status in doctor › Doctor hides credentials in the endpoint | covered | packages.cli.tests.test_cli::test_doctor_telemetry_hides_credentials (passed, zero_value) | - | 0.93 |
| C-db0580b1 | observability › Telemetry status in doctor › Doctor survives a failing status | covered | packages.cli.tests.test_cli::test_doctor_telemetry_survives_a_failing_status (passed, zero_value) | - | 0.83 |
| C-92d621b6 | observability › Telemetry status in doctor › Doctor shows SDK missing and hides headers | covered | packages.cli.tests.test_cli::test_doctor_telemetry_sdk_missing_and_hides_headers (passed, zero_value) | - | 0.93 |
| C-ed7d7932 | observability › Helm telemetry settings › Sampler values are rendered | covered | tests.integration.test_helm_telemetry::test_configmap_guards_sampler_variables_on_their_otel_values (passed, red_assertion); tests.integration.test_helm_telemetry::test_schema_declares_sampler_settings_as_strings (passed, red_assertion); tests.integration.test_helm_telemetry::test_values_yaml_declar... | - | 0.88 |
| C-7836148e | observability › Helm telemetry settings › Rendered with helm | covered | tests.integration.test_helm_telemetry::test_helm_template_defaults_disable_telemetry (passed, red_assertion); tests.integration.test_helm_telemetry::test_helm_template_renders_sampler_values (passed, red_assertion) | tests.integration.test_observability_toolchain::test_helm_template_renders_disabled_telemetry_without_a_skip (passes against the zero values and on the base); tests.integration.test_observability_toolchain::test_helm_template_renders_sampler_values_without_a_skip (passes against the zero values and ... | 0.93 |
| C-c7f1a358 | observability › Helm telemetry settings › Disabled means disabled | covered | tests.integration.test_helm_telemetry::test_configmap_renders_disabled_in_the_else_branch (passed, red_assertion) | - | 0.92 |
| C-3a8ae0df | observability › Observability guide › Guide names every variable | covered | tests.integration.test_observability_guide::test_guide_names_every_variable (passed, red_assertion) | - | 0.95 |
| C-6509c282 | observability › Observability guide › Guide has its parts and links | covered | tests.integration.test_observability_guide::test_guide_has_its_own_and_the_parts_headings (passed, red_assertion); tests.integration.test_observability_guide::test_guide_has_the_local_stack_command_and_phase_query (passed, red_assertion); tests.integration.test_observability_guide::test_readme_links... | - | 0.92 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `README.md` |  | none | exempt: harness, spec or documentation path |
| `deploy/helm/mintmory/templates/configmap.yaml` | deploy | relevant | named in the spec |
| `deploy/helm/mintmory/values.schema.json` | deploy | relevant | named in the spec |
| `deploy/helm/mintmory/values.yaml` | deploy | relevant | named in the spec |
| `deploy/observability/.env.example` | deploy | relevant | named in the spec |
| `deploy/observability/README.md` |  | none | exempt: harness, spec or documentation path |
| `deploy/observability/compose.yaml` | deploy | relevant | named in the spec |
| `deploy/observability/otel-collector.yaml` | deploy | relevant | named in the spec |
| `deploy/observability/prometheus.yml` | deploy | relevant | named in the spec |
| `docs/OBSERVABILITY.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-2/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-2/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-2/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-2/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-2/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-3/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-3/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-3/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack-fix-3/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-2/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-2/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-2/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-3/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-3/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-4/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-4/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-4/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-5/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-5/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/evidence/round-5/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/ledger/r-20261018T1817Z-6a4b.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/ledger/r-20261018T1950Z-d34c.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/ledger/r-20261018T1952Z-fb34.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/ledger/r-20261018T2054Z-83ab.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/.l4/ledger/r-20261019T0431Z-30b7.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/feedback.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-local-observability-stack/verification.md` |  | none | exempt: harness, spec or documentation path |
| `packages/cli/src/mintmory/cli/main.py` | cli | relevant | named in the spec |
| `packages/cli/tests/test_cli.py` |  | relevant | named in the spec |
| `packages/core/src/mintmory/core/telemetry.py` | core | relevant | named in the spec |
| `tests/integration/test_helm_telemetry.py` |  | relevant | new test file |
| `tests/integration/test_observability_guide.py` |  | relevant | new test file |
| `tests/integration/test_observability_stack.py` |  | relevant | new test file |
| `tests/integration/test_observability_stack_readme.py` |  | relevant | new test file |
| `tests/integration/test_observability_toolchain.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

1944 of 2058 passed, 0 failed, 0 errored, 114 skipped.
30 of 30 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-1ee679bf | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-59c20d3b | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-44862bf2 | ok | 0.820 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-d797e1ac | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-990f7ec4 | ok | 0.720 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2b1a1bac | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-93f4f5b3 | ok | 0.850 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-8b3b5845 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-db0580b1 | ok | 0.830 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-92d621b6 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ed7d7932 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-7836148e | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c7f1a358 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3a8ae0df | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6509c282 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-1ee679bf | observability › Local observability stack › Stack definition is pinned and configurable | pass | pass | the judge passed it and a discriminating test passes |
| C-59c20d3b | observability › Local observability stack › Collector routes each signal | pass | pass | the judge passed it and a discriminating test passes |
| C-44862bf2 | observability › Local observability stack › The environment example documents every variable | pass | pass | the judge passed it and a discriminating test passes |
| C-d797e1ac | observability › Local observability stack › Compose accepts the file | pass | pass | the judge passed it and a discriminating test passes |
| C-990f7ec4 | observability › MintMory API service in the local stack › API profile is wired to the collector | pass | pass | the judge passed it and a discriminating test passes |
| C-2b1a1bac | observability › Telemetry status in doctor › Doctor without a collector | pass | pass | the judge passed it and a discriminating test passes |
| C-93f4f5b3 | observability › Telemetry status in doctor › Doctor with an endpoint it cannot parse | pass | pass | the judge passed it and a discriminating test passes |
| C-8b3b5845 | observability › Telemetry status in doctor › Doctor hides credentials in the endpoint | pass | pass | the judge passed it and a discriminating test passes |
| C-db0580b1 | observability › Telemetry status in doctor › Doctor survives a failing status | pass | pass | the judge passed it and a discriminating test passes |
| C-92d621b6 | observability › Telemetry status in doctor › Doctor shows SDK missing and hides headers | pass | pass | the judge passed it and a discriminating test passes |
| C-ed7d7932 | observability › Helm telemetry settings › Sampler values are rendered | pass | pass | the judge passed it and a discriminating test passes |
| C-7836148e | observability › Helm telemetry settings › Rendered with helm | pass | pass | the judge passed it and a discriminating test passes |
| C-c7f1a358 | observability › Helm telemetry settings › Disabled means disabled | pass | pass | the judge passed it and a discriminating test passes |
| C-3a8ae0df | observability › Observability guide › Guide names every variable | pass | pass | the judge passed it and a discriminating test passes |
| C-6509c282 | observability › Observability guide › Guide has its parts and links | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, deterministic] a test is ignored as evidence (criterion C-d797e1ac): tests.integration.test_observability_toolchain::test_docker_compose_config_accepts_the_stack_without_a_skip: passes against the zero values and on the base
- [minor, deterministic] a test is ignored as evidence (criterion C-7836148e): tests.integration.test_observability_toolchain::test_helm_template_renders_disabled_telemetry_without_a_skip: passes against the zero values and on the base
- [minor, deterministic] a test is ignored as evidence (criterion C-7836148e): tests.integration.test_observability_toolchain::test_helm_template_renders_sampler_values_without_a_skip: passes against the zero values and on the base
- [minor, judge] Guide shows otel.enabled as a quoted string (criterion C-6509c282): docs/OBSERVABILITY.md Production says `otel.enabled: "true"`, but the schema declares enabled as boolean, so a quoted value would be rejected.
- [minor, judge] Stale docstrings and duplicate tests (criterion C-7836148e): test_helm_telemetry.py and test_observability_stack.py docstrings still say helm/docker checks run only where the tool exists; test_observability_toolchain.py duplicates the three command tests.
- [minor, judge] Host case and IPv6 in endpoint (spec gap) (criterion C-8b3b5845): Host is kept as written via netloc; behaviour for uppercase hosts or IPv6 brackets is unpinned by scenarios.

## Feedback

- FB-001: addressed at 5e51fdc0ed: tests/integration/test_helm_telemetry.py and test_observability_stack.py in the diff have no skipif markers and no shutil import; the three tests are plain and passed in the gate.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.cli.tests.test_cli::test_doctor_telemetry_endpoint_it_cannot_parse` (task 2.1): passed
- `packages.cli.tests.test_cli::test_doctor_telemetry_hides_credentials` (task 2.1): passed
- `packages.cli.tests.test_cli::test_doctor_telemetry_sdk_missing_and_hides_headers` (task 2.1): passed
- `packages.cli.tests.test_cli::test_doctor_telemetry_survives_a_failing_status` (task 2.1): passed
- `packages.cli.tests.test_cli::test_doctor_telemetry_without_a_collector` (task 2.1): passed
- `tests.integration.test_helm_telemetry::test_configmap_guards_sampler_variables_on_their_otel_values` (task 3.1): passed
- `tests.integration.test_helm_telemetry::test_configmap_renders_disabled_in_the_else_branch` (task 3.1): passed
- `tests.integration.test_helm_telemetry::test_helm_template_defaults_disable_telemetry` (task 3.1): passed
- `tests.integration.test_helm_telemetry::test_helm_template_renders_sampler_values` (task 3.1): passed
- `tests.integration.test_helm_telemetry::test_schema_declares_sampler_settings_as_strings` (task 3.1): passed
- `tests.integration.test_helm_telemetry::test_values_yaml_declares_empty_sampler_settings` (task 3.1): passed
- `tests.integration.test_observability_guide::test_guide_has_its_own_and_the_parts_headings` (task 4.1): passed
- `tests.integration.test_observability_guide::test_guide_has_the_local_stack_command_and_phase_query` (task 4.1): passed
- `tests.integration.test_observability_guide::test_guide_names_every_variable` (task 4.1): passed
- `tests.integration.test_observability_guide::test_readme_links_to_the_guide_and_the_stack_readme` (task 4.1): passed
- `tests.integration.test_observability_stack::test_api_profile_is_wired_to_the_collector` (task 1.1): passed
- `tests.integration.test_observability_stack::test_collector_metrics_pipeline_is_scraped_by_prometheus` (task 1.1): passed
- `tests.integration.test_observability_stack::test_collector_otlp_receiver_listens_on_grpc_and_http` (task 1.1): passed
- `tests.integration.test_observability_stack::test_collector_traces_pipeline_exports_to_jaeger` (task 1.1): passed
- `tests.integration.test_observability_stack::test_docker_compose_config_accepts_the_stack` (task 1.1): passed
- `tests.integration.test_observability_stack::test_env_example_documents_every_compose_variable` (task 1.1): passed
- `tests.integration.test_observability_stack::test_jaeger_serves_ui_without_publishing_its_otlp_ports` (task 1.1): passed
- `tests.integration.test_observability_stack::test_stack_defines_collector_jaeger_and_prometheus` (task 1.1): passed
- `tests.integration.test_observability_stack::test_stack_images_are_pinned_and_not_latest` (task 1.1): passed
- `tests.integration.test_observability_stack::test_stack_published_ports_are_configurable_and_on_loopback` (task 1.1): passed
- `tests.integration.test_observability_stack_readme::test_stack_readme_documents_the_viewers_and_api_profile` (task 1.6): passed
- `tests.integration.test_observability_stack_readme::test_stack_readme_gives_the_quick_start_command` (task 1.6): passed

## Guard events

- guard.test_tamper: tests/integration/test_helm_telemetry.py
- guard.test_tamper: tests/integration/test_observability_stack.py
- guard.test_tamper: tests/integration/test_helm_telemetry.py
- guard.test_tamper: tests/integration/test_observability_stack.py
- guard.test_tamper: tests/integration/test_helm_telemetry.py
- guard.test_tamper: tests/integration/test_observability_stack.py
