# Verification: openspec:add-telemetry-runtime: FAIL (round 3)

traceability: not checked (an earlier step failed)

- Base: `cbc196ba65882aef229321f0f1a4adbe2ba728e8`
- Head: `0cbb5261db6245367e2aefd8f7242ab052fbb178`
- Implementer profiles: deepseek
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | failed | 0.4 | base staging@cbc196ba65 contained; Feedback FB-001 (behaviour): _sdk_available must catch ImportError and ValueError from; Feedback FB-002 (behaviour): _build_meter_provider must wrap the configured metric exporter with |
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

- [major, feedback] Feedback FB-001 (behaviour): _sdk_available must catch ImportError and ValueError from: _sdk_available must catch ImportError and ValueError from importlib.util.find_spec and return False; add a test that does not stub _sdk_available (monkeypatch importlib.util.find_spec to raise ModuleNotFoundError)
- [major, feedback] Feedback FB-002 (behaviour): _build_meter_provider must wrap the configured metric exporter with: _build_meter_provider must wrap the configured metric exporter with _GuardedMetricExporter as the span exporter is wrapped, keeping the reader's temporality; packages/api/tests/test_health_and_otel.py must unwrap _inner to the OTLP metric exporter (task 7.1)

## Fix unit

Fix unit 1 is created for these tasks:
- F-e875fe5d Feedback FB-001 (behaviour): _sdk_available must catch ImportError and ValueError from
- F-a9f95a8b Feedback FB-002 (behaviour): _build_meter_provider must wrap the configured metric exporter with

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.api.tests.test_health_and_otel_runtime::test_configured_otlp_span_exporter_chain_ends_at_the_otlp_http_exporter` (task 7.1): not in the report
- `packages.api.tests.test_health_and_otel_runtime::test_enabled_setting_normalises_booleans_and_case` (task 7.1): not in the report
- `packages.api.tests.test_health_and_otel_runtime::test_explicit_false_enabled_returns_false_without_probing` (task 7.1): not in the report
- `packages.cli.tests.test_telemetry_acceptance_gate::test_gate_cli_package_test_uses_the_shared_receiver` (task 9.1): not in the report
- `packages.cli.tests.test_telemetry_shared_fixtures::test_cli_tests_can_request_the_shared_telemetry_fixtures` (task 1.2): not in the report
- `packages.cli.tests.test_telemetry_shared_fixtures::test_closed_port_is_a_loopback_port_nobody_listens_on` (task 1.2): not in the report
- `packages.cli.tests.test_telemetry_shared_fixtures::test_otlp_receiver_records_a_post_and_decodes_the_exported_spans` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings::test_bad_mintmory_values_fall_back_with_one_warning_each` (task 2.1): not in the report
- `packages.core.tests.test_otel_settings::test_boolean_and_case_are_normalised` (task 2.1): not in the report
- `packages.core.tests.test_otel_settings::test_defaults_are_auto_otlp_no_service_name_and_three_seconds` (task 2.1): not in the report
- `packages.core.tests.test_otel_settings::test_non_positive_or_non_numeric_timeout_falls_back_to_three[-1]` (task 2.1): not in the report
- `packages.core.tests.test_otel_settings::test_non_positive_or_non_numeric_timeout_falls_back_to_three[0]` (task 2.1): not in the report
- `packages.core.tests.test_otel_settings::test_non_positive_or_non_numeric_timeout_falls_back_to_three[abc]` (task 2.1): not in the report
- `packages.core.tests.test_otel_settings::test_valid_values_are_kept` (task 2.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_a_second_init_changes_nothing` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_another_settings_group_is_invalid` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_auto_turns_on_with_a_collector` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_auto_without_collector_stays_off_in_a_fresh_process` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_bad_mintmory_values_fall_back` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_bad_standard_values_fall_back` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_both_signals_off_returns_false_without_a_warning` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_console_output_never_reaches_stdout` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_context_propagates_by_default` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_exit_is_bounded_when_export_hangs` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_explicit_off_wins` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_export_runs_off_the_calling_thread` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_exporter_logger_level_is_restored` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_guard_logs_once_per_signal_per_streak` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_init_failure_turns_telemetry_off` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_injection_beats_the_suites_off_default` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_library_exception_is_scrubbed` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_marking_a_span_off` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_marking_a_span_on` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_one_atexit_hook_none_from_the_sdk` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_one_signal_switched_off_builds_no_provider_for_it[console-none-metric]` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_one_signal_switched_off_builds_no_provider_for_it[none-console-tracer]` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_pending_spans_are_delivered_on_exit` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_reinitialisation_after_shutdown` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_reset_telemetry_restores_the_noop_shim` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_resource_uses_the_callers_default_name` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_sampling_switched_off` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_sdk_missing_warns_only_with_a_hint` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_single_injection_builds_no_network_exporter` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_standard_variables_win` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_unreachable_collector_logs_once` (task 9.1): not in the report
- `packages.core.tests.test_telemetry_enablement::test_auto_with_a_reachable_endpoint_turns_on_and_probes` (task 3.1): not in the report
- `packages.core.tests.test_telemetry_enablement::test_auto_with_an_endpoint_variable_turns_on_and_skips_the_probe` (task 3.1): not in the report
- `packages.core.tests.test_telemetry_enablement::test_auto_without_a_collector_stays_off_in_a_fresh_process` (task 3.1): not in the report
- `packages.core.tests.test_telemetry_enablement::test_both_signals_off_returns_false_without_a_warning` (task 3.1): not in the report
- `packages.core.tests.test_telemetry_enablement::test_console_exporter_writes_to_stderr_never_stdout` (task 3.1): not in the report

## Guard events

- guard.violation: conftest.py
- guard.violation: conftest.py
- guard.violation: conftest.py
- guard.violation: packages/core/src/mintmory/core/telemetry.py
- guard.violation: packages/core/src/mintmory/core/telemetry.py
