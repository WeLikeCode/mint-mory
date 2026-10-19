# Verification: openspec:add-local-observability-stack: FAIL (round 3)

traceability: not checked (an earlier step failed)

- Base: `f29487b0b8be568c91a2d400927d43a372d26eca`
- Head: `223efa565f7c69c50d577b18e75f2575591dbc8e`
- Implementer profiles: deepseek
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | failed | 0.9 | base merged: staging@f29487b0b8 as 223efa565f (1 commit); Feedback FB-001 (tests): Remove the three @pytest.mark.skipif(shutil.which(...) is None, ...) |
| 1 | integrity | not_run | 0.0 | an earlier step failed |
| 2 | build | not_run | 0.0 | an earlier step failed |
| 3 | tests | not_run | 0.0 | an earlier step failed |
| 4 | traceability | not_run | 0.0 | an earlier step failed |
| 4a | audit sampling | not_run | 0.0 | an earlier step failed |
| 5 | ui test generation | not_run | 0.0 | an earlier step failed |
| 6 | quality | not_run | 0.0 | an earlier step failed |
| 8 | s1 judge | not_run | 0.0 | an earlier step failed |
| 9 | judge | not_run | 0.0 | an earlier step failed |
| 10 | aggregation | ok | 0.0 | FAIL |

## Criteria

None judged.

## Findings

- [major, feedback] Feedback FB-001 (tests): Remove the three @pytest.mark.skipif(shutil.which(...) is None, ...): Remove the three @pytest.mark.skipif(shutil.which(...) is None, ...) markers and keep the tests as they are. helm and docker are on the gate runner: the gates already ran these three tests and they passed (the skipped count stayed 114). L4's integrity check refuses any added skip or xfail marker (blocker F-5758ac1b), whatever the spec text says; the spec's 'skipped otherwise' note is outdated.

## Fix unit

Fix unit 2 is created for these tasks:
- F-f5fcb85c Feedback FB-001 (tests): Remove the three @pytest.mark.skipif(shutil.which(...) is None, ...)

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.cli.tests.test_cli::test_doctor_telemetry_endpoint_it_cannot_parse` (task 2.1): not in the report
- `packages.cli.tests.test_cli::test_doctor_telemetry_hides_credentials` (task 2.1): not in the report
- `packages.cli.tests.test_cli::test_doctor_telemetry_sdk_missing_and_hides_headers` (task 2.1): not in the report
- `packages.cli.tests.test_cli::test_doctor_telemetry_survives_a_failing_status` (task 2.1): not in the report
- `packages.cli.tests.test_cli::test_doctor_telemetry_without_a_collector` (task 2.1): not in the report
- `tests.integration.test_helm_telemetry::test_configmap_guards_sampler_variables_on_their_otel_values` (task 3.1): not in the report
- `tests.integration.test_helm_telemetry::test_configmap_renders_disabled_in_the_else_branch` (task 3.1): not in the report
- `tests.integration.test_helm_telemetry::test_helm_template_defaults_disable_telemetry` (task 3.1): not in the report
- `tests.integration.test_helm_telemetry::test_helm_template_renders_sampler_values` (task 3.1): not in the report
- `tests.integration.test_helm_telemetry::test_schema_declares_sampler_settings_as_strings` (task 3.1): not in the report
- `tests.integration.test_helm_telemetry::test_values_yaml_declares_empty_sampler_settings` (task 3.1): not in the report
- `tests.integration.test_observability_guide::test_guide_has_its_own_and_the_parts_headings` (task 4.1): not in the report
- `tests.integration.test_observability_guide::test_guide_has_the_local_stack_command_and_phase_query` (task 4.1): not in the report
- `tests.integration.test_observability_guide::test_guide_names_every_variable` (task 4.1): not in the report
- `tests.integration.test_observability_guide::test_readme_links_to_the_guide_and_the_stack_readme` (task 4.1): not in the report
- `tests.integration.test_observability_stack::test_api_profile_is_wired_to_the_collector` (task 1.1): not in the report
- `tests.integration.test_observability_stack::test_collector_metrics_pipeline_is_scraped_by_prometheus` (task 1.1): not in the report
- `tests.integration.test_observability_stack::test_collector_otlp_receiver_listens_on_grpc_and_http` (task 1.1): not in the report
- `tests.integration.test_observability_stack::test_collector_traces_pipeline_exports_to_jaeger` (task 1.1): not in the report
- `tests.integration.test_observability_stack::test_docker_compose_config_accepts_the_stack` (task 1.1): not in the report
- `tests.integration.test_observability_stack::test_env_example_documents_every_compose_variable` (task 1.1): not in the report
- `tests.integration.test_observability_stack::test_jaeger_serves_ui_without_publishing_its_otlp_ports` (task 1.1): not in the report
- `tests.integration.test_observability_stack::test_stack_defines_collector_jaeger_and_prometheus` (task 1.1): not in the report
- `tests.integration.test_observability_stack::test_stack_images_are_pinned_and_not_latest` (task 1.1): not in the report
- `tests.integration.test_observability_stack::test_stack_published_ports_are_configurable_and_on_loopback` (task 1.1): not in the report
- `tests.integration.test_observability_stack_readme::test_stack_readme_documents_the_viewers_and_api_profile` (task 1.6): not in the report
- `tests.integration.test_observability_stack_readme::test_stack_readme_gives_the_quick_start_command` (task 1.6): not in the report

## Guard events

- guard.test_tamper: tests/integration/test_helm_telemetry.py
- guard.test_tamper: tests/integration/test_observability_stack.py
