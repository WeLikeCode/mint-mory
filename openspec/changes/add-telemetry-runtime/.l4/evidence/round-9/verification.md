# Verification: openspec:add-telemetry-runtime: FAIL (round 9)

traceability: not checked (an earlier step failed)

- Base: `e3703e558fc3365ae0eacccb9ee4d1ea326e6236`
- Head: `38ab359278c48e5dfe4574e2936848e2f1edf439`
- Implementer profiles: deepseek
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | failed | 0.8 | base staging@e3703e558f contained; Feedback FB-005 (refactor): span, add_count and record_value read _tracer and _meter once; Feedback FB-006 (behaviour): an injected exporter without the SDK says why telemetry is off |
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

- [major, feedback] Feedback FB-005 (refactor): span, add_count and record_value read _tracer and _meter once: span(), add_count() and record_value() check _enabled and _tracer or _meter, then read the module global again to use it, and _instrument() reads _meter once more. A shutdown_telemetry() on another thread between the check and the use sets the global to None, and the call raises AttributeError ('NoneType' object has no attribute 'start_as_current_span' or 'create_counter'), although telemetry must never break its caller. Read each global once into a local and use only the local: span() reads _tracer once; add_count() and record_value() read _meter once and pass it to _instrument(), which takes...
- [major, feedback] Feedback FB-006 (behaviour): an injected exporter without the SDK says why telemetry is off: init_telemetry() with span_exporter or metric_reader returns False silently when the OpenTelemetry SDK is missing. The caller asked for telemetry with its own exporter, so say why it is off, as the MINTMORY_OTEL_ENABLED=true branch already does: one WARNING on mintmory.telemetry that names the missing SDK and the extra to install.

## Fix unit

Fix unit 3 is created for these tasks:
- F-64545f65 Feedback FB-005 (refactor): span, add_count and record_value read _tracer and _meter once
- F-27a3cee6 Feedback FB-006 (behaviour): an injected exporter without the SDK says why telemetry is off

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
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[0-false0]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[0-false1]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[1-true0]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[1-true1]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[F-false]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[N-false]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[NO-false]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[OFF-false]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[ON-true]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[T-true]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[Y-true]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[YES-true]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[f-false]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[n-false]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[no-false]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[off-false]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[on-true]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[t-true]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[y-true]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_boolean_spelling_maps_without_a_warning[yes-true]` (task 1.2): not in the report
- `packages.core.tests.test_otel_settings_enabled_spellings::test_modes_keep_meaning_and_invalid_values_fall_back` (task 1.2): not in the report
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

## Guard events

- guard.violation: conftest.py
- guard.violation: conftest.py
- guard.violation: conftest.py
- guard.violation: packages/core/src/mintmory/core/telemetry.py
- guard.violation: packages/core/src/mintmory/core/telemetry.py
- guard.test_tamper: packages/api/tests/test_health_and_otel.py
- guard.test_tamper: packages/api/tests/test_health_and_otel.py
- guard.test_tamper: packages/api/tests/test_health_and_otel.py
- guard.test_tamper: packages/api/tests/test_health_and_otel.py
- guard.test_tamper: packages/api/tests/test_health_and_otel.py
- guard.test_tamper: packages/api/tests/test_health_and_otel.py
- guard.test_tamper: packages/api/tests/test_health_and_otel.py
