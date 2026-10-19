# Verification: openspec:deployment-hardening: PASS (round 1)

traceability: 8/8 criteria covered by a discriminating test

- Base: `a83c6bf80ecb58c14d7e39ad2cf381f011b9fd18`
- Head: `ed21d669aad9d79b62c162791a453954d322c91c`
- Implementer profiles: deepseek, glm, deepseek-free, glm-free
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `25b482cdc7a9b27217f8a6fdf0659477653c98a3dd2845215a2f3a450fac7d15`
- Judge replies of claude-judge (this unit, all rounds): valid 1, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared), glm zhipu (declared), deepseek-free deepseek (declared), glm-free zhipu (declared)
- Cost: $0.5024

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.2 | base merged: staging@a83c6bf80e as ed21d669aa (6 commits) |
| 1 | integrity | ok | 0.1 | 7 sub-checks; scope: 13 changed file(s) |
| 2 | build | ok | 0.7 |  |
| 3 | tests | ok | 52.2 |  |
| 4 | traceability | ok | 0.0 | 8/8 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 5.1 | 8/8 criteria judged by jev |
| 9 | judge | ok | 14.7 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | PASS |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261019T1043Z-a8f9/084-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261019T1043Z-a8f9/085-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261019T1043Z-a8f9/086-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261019T1043Z-a8f9/087-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261019T1043Z-a8f9/088-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 2 test file(s) compared with the base |
| red-green freeze | ok | 4 task(s): red and green compared |
| test path freeze | ok | 4 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | skipped | no new suppression comment |
| tdd history | ok | 6 task(s); red tests passing at head: step 3 |

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-d321fc4b | deployment › Published container image › The chart's default tag tracks the release version | covered | tests.integration.test_bump_version::test_bump_chart_rewrites_app_version_only (passed, zero_value); tests.integration.test_bump_version::test_bump_main_rewrites_chart_and_pyprojects (passed, zero_value); tests.integration.test_bump_version::test_chart_app_version_matches_package_version (passed, ze... | - | 0.94 |
| C-e656ed0f | deployment › Published container image › bump_version.py updates the chart through main() | covered | tests.integration.test_bump_version::test_bump_chart_fails_without_double_quoted_app_version (passed, zero_value); tests.integration.test_bump_version::test_bump_main_rewrites_chart_and_pyprojects (passed, zero_value) | - | 0.91 |
| C-1997c052 | deployment › Published container image › A Chart without a double-quoted appVersion fails the bump and writes nothing | covered | tests.integration.test_bump_version::test_bump_chart_fails_without_double_quoted_app_version (passed, zero_value); tests.integration.test_bump_version::test_bump_main_writes_nothing_when_chart_unparseable (passed, zero_value) | - | 0.83 |
| C-ce80d78d | deployment › Published container image › A bad version argument is rejected | covered | tests.integration.test_bump_version::test_bump_chart_fails_without_double_quoted_app_version (passed, zero_value); tests.integration.test_bump_version::test_bump_main_rejects_bad_version (passed, zero_value) | - | 0.63 |
| C-ce708748 | deployment › Selectable ingress authentication mode › oauth2-proxy mode wires external auth without app changes | covered | tests.integration.test_deploy_hardening::test_oauth2proxy_render_wires_external_auth (passed, red_assertion) | - | 0.86 |
| C-a45cc480 | deployment › oauth2-proxy pods have their own selector labels › The rendered selectors are disjoint | covered | tests.integration.test_deploy_hardening::test_oauth2proxy_render_selectors_disjoint (passed, red_assertion) | - | 0.91 |
| C-3ebe6ecd | deployment › oauth2-proxy pods have their own selector labels › The postgres-mode PodDisruptionBudget does not cover oauth2-proxy | covered | tests.integration.test_deploy_hardening::test_postgres_pdb_does_not_select_oauth2proxy (passed, red_assertion) | - | 0.92 |
| C-2f129c5f | deployment › oauth2-proxy pods have their own selector labels › The README documents the tag scheme and the upgrade step | covered | tests.integration.test_deploy_hardening::test_chart_readme_documents_tag_scheme_and_upgrade_step (passed, red_assertion) | - | 0.93 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `deploy/helm/mintmory/README.md` |  | none | exempt: harness, spec or documentation path |
| `deploy/helm/mintmory/templates/_helpers.tpl` | deploy | relevant | named in the spec |
| `deploy/helm/mintmory/templates/oauth2proxy-deployment.yaml` | deploy | relevant | named in the spec |
| `deploy/helm/mintmory/templates/oauth2proxy-service.yaml` | deploy | relevant | named in the spec |
| `openspec/changes/deployment-hardening/.l4/ledger/r-20261019T0440Z-a1ca.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/deployment-hardening/.l4/ledger/r-20261019T0455Z-0039.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/deployment-hardening/.l4/ledger/r-20261019T0900Z-d56c.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/deployment-hardening/.l4/ledger/r-20261019T1043Z-a8f9.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/deployment-hardening/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/deployment-hardening/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `scripts/bump_version.py` | scripts | relevant | named in the spec |
| `tests/integration/test_bump_version.py` |  | relevant | named in the spec |
| `tests/integration/test_deploy_hardening.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

1955 of 2069 passed, 0 failed, 0 errored, 114 skipped.
11 of 11 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-d321fc4b | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e656ed0f | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1997c052 | ok | 0.830 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ce80d78d | ok | 0.630 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ce708748 | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a45cc480 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3ebe6ecd | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-2f129c5f | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-d321fc4b | deployment › Published container image › The chart's default tag tracks the release version | pass | pass | the judge passed it and a discriminating test passes |
| C-e656ed0f | deployment › Published container image › bump_version.py updates the chart through main() | pass | pass | the judge passed it and a discriminating test passes |
| C-1997c052 | deployment › Published container image › A Chart without a double-quoted appVersion fails the bump and writes nothing | pass | pass | the judge passed it and a discriminating test passes |
| C-ce80d78d | deployment › Published container image › A bad version argument is rejected | pass | pass | the judge passed it and a discriminating test passes |
| C-ce708748 | deployment › Selectable ingress authentication mode › oauth2-proxy mode wires external auth without app changes | pass | pass | the judge passed it and a discriminating test passes |
| C-a45cc480 | deployment › oauth2-proxy pods have their own selector labels › The rendered selectors are disjoint | pass | pass | the judge passed it and a discriminating test passes |
| C-3ebe6ecd | deployment › oauth2-proxy pods have their own selector labels › The postgres-mode PodDisruptionBudget does not cover oauth2-proxy | pass | pass | the judge passed it and a discriminating test passes |
| C-2f129c5f | deployment › oauth2-proxy pods have their own selector labels › The README documents the tag scheme and the upgrade step | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] README substring check is weak (criterion C-2f129c5f): 'oauth2-proxy Deployment' is satisfied by prose only; the test cannot show the instruction is accurate.
- [minor, judge] Chart written before pyprojects (spec gap) (criterion C-1997c052): main writes the chart before the pyprojects; a failing pyproject write leaves the chart bumped alone. The spec does not cover this.

## New tests (red then green, `task.red_ok` in the ledger)

- `tests.integration.test_bump_version::test_bump_chart_fails_without_double_quoted_app_version` (task 5.6): passed
- `tests.integration.test_bump_version::test_bump_chart_rewrites_app_version_only` (task 5.6): passed
- `tests.integration.test_bump_version::test_bump_main_rejects_bad_version` (task 5.6): passed
- `tests.integration.test_bump_version::test_bump_main_rewrites_chart_and_pyprojects` (task 5.6): passed
- `tests.integration.test_bump_version::test_bump_main_writes_nothing_when_chart_unparseable` (task 5.6): passed
- `tests.integration.test_bump_version::test_chart_app_version_matches_package_version` (task 5.6): passed
- `tests.integration.test_deploy_hardening::test_chart_readme_documents_tag_scheme_and_upgrade_step` (task 5.7): passed
- `tests.integration.test_deploy_hardening::test_ci_validates_oauth2proxy_render` (task 4.1): passed
- `tests.integration.test_deploy_hardening::test_oauth2proxy_render_selectors_disjoint` (task 5.1): passed
- `tests.integration.test_deploy_hardening::test_oauth2proxy_render_wires_external_auth` (task 5.1): passed
- `tests.integration.test_deploy_hardening::test_postgres_pdb_does_not_select_oauth2proxy` (task 5.1): passed

## Guard events

- guard.violation: .github/workflows/ci.yml
