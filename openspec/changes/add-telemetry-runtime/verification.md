# Verification: openspec:add-telemetry-runtime: FAIL (round 4)

traceability: 31/31 criteria covered by a discriminating test

- Base: `d5f2b35378596939289aa86b4e0ccb1057b71d9f`
- Head: `d80b5d4bd4fb32036d482b4e531e975299129af2`
- Implementer profiles: deepseek
- Judge: claude-judge (claude-sonnet-5-5), 1 call(s), prompt sha256 `b96cf941ff4657bdf5bb858511f7b592cef4c3d870cdc3afb0d01b7c3a0d4885`
- Judge replies of claude-judge (this unit, all rounds): valid 2, repaired 0, retried 0, discarded 0; this round: valid
- independence: declared (unverified): claude-judge anthropic (served claude-sonnet-5-5), deepseek deepseek (declared)
- Cost: $0.6876

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | ok | 0.8 | base merged: staging@d5f2b35378 as d80b5d4bd4 (2 commits) |
| 1 | integrity | ok | 1.1 | 7 sub-checks (+2 unfrozen by human answers); scope: 68 changed file(s) |
| 2 | build | ok | 0.9 |  |
| 3 | tests | ok | 57.4 |  |
| 4 | traceability | ok | 0.2 | 31/31 criteria covered |
| 4a | audit sampling | not_run | 0.0 | roles.verifier_agent is empty |
| 5 | ui test generation | not_run | 0.0 | verifier.playwright.enabled is off |
| 6 | quality | ok | 0.0 | diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other |
| 8 | s1 judge | ok | 2.8 | 31/31 criteria judged by jev |
| 9 | judge | ok | 24.3 | 1 call(s) |
| 10 | aggregation | ok | 0.0 | FAIL |

## Gates

| Gate | Status | Command | Log |
|---|---|---|---|
| setup | pass | `uv sync --frozen --extra cochange --extra otel --extra postgres` | .l4-out/gates/r-20261016T1948Z-479c/013-setup.log |
| lint | pass | `.venv/bin/ruff check --extend-exclude .l4 .` | .l4-out/gates/r-20261016T1948Z-479c/014-lint.log |
| lint | pass | `.venv/bin/ruff format --check .` | .l4-out/gates/r-20261016T1948Z-479c/015-lint.log |
| typecheck | pass | `.venv/bin/mypy packages` | .l4-out/gates/r-20261016T1948Z-479c/016-typecheck.log |
| test | pass | `.venv/bin/pytest -q --junitxml=.l4-out/junit.xml` | .l4-out/gates/r-20261016T1948Z-479c/017-test.log |

## Integrity

| Check | Status | Note |
|---|---|---|
| protected paths | ok | no protected path differs from the base |
| pre-existing tests | ok | 29 test file(s) compared with the base |
| red-green freeze | ok | 12 task(s): red and green compared (+2 unfrozen by human answers) |
| test path freeze | ok | 12 harness step commit(s) checked |
| content scan | ok | no result-manipulating construct in the changed support and runner files |
| suppressions | ok | 5 new suppression(s), 5 declared |
| tdd history | ok | 25 task(s); red tests passing at head: step 3 |

Declared suppressions:
- packages/core/src/mintmory/core/telemetry.py:335 # noqa: BLE001 (declared: The span guard must swallow any exporter exception to return FAILURE and never block or raise.)
- packages/core/src/mintmory/core/telemetry.py:380 # noqa: BLE001 (declared: The metric guard must swallow any exporter exception to return FAILURE and never block or raise.)
- packages/core/src/mintmory/core/telemetry.py:576 # noqa: BLE001 (declared: init_telemetry must catch any exception while building providers, tear down and return False.)
- packages/core/src/mintmory/core/telemetry.py:740 # noqa: BLE001 (declared: mark_error must never raise even if importing opentelemetry.trace fails, so the import is guarded by a broad except.)
- packages/core/src/mintmory/core/telemetry.py:749 # noqa: BLE001 (declared: mark_error must never raise while marking a span, so the status/attribute calls are guarded by a broad except.)

## Tests unfrozen by human answers (allowed, L4-IMP-002)

- conftest.py (task 1.1, unfrozen by Q-001 (human))
- conftest.py (task 1.2, unfrozen by Q-003 (human))

## Traceability

| Id | Criterion | State | Tests (status, proof) | Not evidence | S1 p |
|---|---|---|---|---|---|
| C-2190b9f3 | observability › Telemetry enablement modes › Auto with no collector stays off | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_auto_without_collector_stays_off_in_a_fresh_process (passed, pre_satisfied); packages.core.tests.test_telemetry_enablement::test_auto_without_a_collector_stays_off_in_a_fresh_process (passed, zero_value); packages.core.tests.test_telemetr... | - | 0.94 |
| C-aba1a372 | observability › Telemetry enablement modes › Auto turns on with a collector | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_auto_turns_on_with_a_collector (passed, pre_satisfied); packages.core.tests.test_telemetry_enablement::test_auto_with_a_reachable_endpoint_turns_on_and_probes (passed, zero_value); packages.core.tests.test_telemetry_enablement::test_auto_... | - | 0.91 |
| C-9d8f8f9c | observability › Telemetry enablement modes › Explicit off wins | covered | packages.api.tests.test_health_and_otel_runtime::test_explicit_false_enabled_returns_false_without_probing (passed, pre_satisfied); packages.core.tests.test_telemetry_acceptance_gate::test_gate_explicit_off_wins (passed, pre_satisfied); packages.core.tests.test_telemetry_enablement::test_explicit_of... | - | 0.90 |
| C-ead28cef | observability › Telemetry enablement modes › SDK missing | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_sdk_missing_warns_only_with_a_hint (passed, pre_satisfied); packages.core.tests.test_telemetry_enablement::test_sdk_missing_stays_off_and_warns_only_with_a_hint (passed, zero_value); packages.core.tests.test_telemetry_helpers::test_resolv... | - | 0.91 |
| C-4d7716fe | observability › Exporter selection and endpoint resolution › Console output never reaches stdout | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_console_output_never_reaches_stdout (passed, pre_satisfied); packages.core.tests.test_telemetry_enablement::test_console_exporter_writes_to_stderr_never_stdout (passed, zero_value) | - | 0.91 |
| C-6fc7f4c6 | observability › Exporter selection and endpoint resolution › One signal switched off | covered | packages.api.tests.test_health_and_otel_runtime::test_configured_otlp_span_exporter_chain_ends_at_the_otlp_http_exporter (passed, pre_satisfied); packages.core.tests.test_telemetry_acceptance_gate::test_gate_one_signal_switched_off_builds_no_provider_for_it[console-none-metric] (passed, pre_satisfie... | - | 0.95 |
| C-690840ae | observability › Exporter selection and endpoint resolution › Both signals off | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_both_signals_off_returns_false_without_a_warning (passed, pre_satisfied); packages.core.tests.test_telemetry_enablement::test_both_signals_off_returns_false_without_a_warning (passed, zero_value) | - | 0.91 |
| C-5412bab8 | observability › Export never blocks or floods when the collector is absent › Export runs off the caller's thread | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_export_runs_off_the_calling_thread (passed, pre_satisfied); packages.core.tests.test_telemetry_resilience::test_export_runs_off_the_caller_thread (passed, zero_value); packages.core.tests.test_telemetry_timeouts::test_a_per_signal_timeout... | - | 0.91 |
| C-18efd0f6 | observability › Export never blocks or floods when the collector is absent › Unreachable collector logs once | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_unreachable_collector_logs_once (passed, pre_satisfied); packages.core.tests.test_telemetry_resilience::test_unreachable_collector_warns_once_and_mutes_the_exporter_logger (passed, zero_value); packages.core.tests.test_telemetry_timeouts:... | - | 0.92 |
| C-cd710a4c | observability › Export never blocks or floods when the collector is absent › Once per signal per streak | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_guard_logs_once_per_signal_per_streak (passed, pre_satisfied); packages.core.tests.test_telemetry_guards::test_guards_keep_inner_and_the_metric_guard_is_a_metric_exporter (passed, red_assertion); packages.core.tests.test_telemetry_resilie... | - | 0.90 |
| C-e1c42220 | observability › Invalid MintMory telemetry settings fall back › Bad MintMory values fall back | covered | packages.api.tests.test_health_and_otel_runtime::test_enabled_setting_normalises_booleans_and_case (passed, pre_satisfied); packages.core.tests.test_otel_settings::test_bad_mintmory_values_fall_back_with_one_warning_each (passed, red_assertion); packages.core.tests.test_otel_settings::test_boolean_a... | - | 0.74 |
| C-3852f755 | observability › Invalid standard OpenTelemetry variables fall back › Bad standard values fall back | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_bad_standard_values_fall_back (passed, pre_satisfied); packages.core.tests.test_telemetry_resilience::test_bad_standard_values_fall_back (passed, zero_value) | - | 0.88 |
| C-c724dabe | observability › Telemetry init never raises › An exporter cannot be built | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_init_failure_turns_telemetry_off (passed, pre_satisfied); packages.core.tests.test_telemetry_init_failure::test_a_failed_build_after_the_tracer_is_up_tears_everything_down (passed, pre_satisfied); packages.core.tests.test_telemetry_resili... | - | 0.86 |
| C-044e54eb | observability › Telemetry init never raises › Another settings group is invalid | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_another_settings_group_is_invalid (passed, pre_satisfied); packages.core.tests.test_telemetry_init_failure::test_init_does_not_read_another_settings_group (passed, pre_satisfied); packages.core.tests.test_telemetry_resilience::test_init_i... | - | 0.66 |
| C-b7126d33 | observability › Bounded flush on exit › Exit is bounded when export hangs | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_exit_is_bounded_when_export_hangs (passed, pre_satisfied); packages.core.tests.test_telemetry_shutdown::test_shutdown_is_bounded_when_a_provider_shutdown_hangs (passed, pre_satisfied); packages.core.tests.test_telemetry_teardown::test_tea... | - | 0.84 |
| C-16b8c487 | observability › Bounded flush on exit › Pending spans are delivered on exit | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_pending_spans_are_delivered_on_exit (passed, pre_satisfied); packages.core.tests.test_telemetry_exporters::test_otlp_exporters_default_to_the_local_collector_with_signal_paths (passed, red_assertion); packages.core.tests.test_telemetry_ex... | - | 0.88 |
| C-1d2bd9a4 | observability › Bounded flush on exit › The exporter logger level is restored | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_exporter_logger_level_is_restored (passed, pre_satisfied); packages.core.tests.test_telemetry_logger_level::test_otlp_exporter_logger_is_critical_while_running_and_restored_after_shutdown (passed, pre_satisfied); packages.core.tests.test_... | - | 0.94 |
| C-fa66b065 | observability › Bounded flush on exit › One atexit hook, none from the SDK | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_one_atexit_hook_none_from_the_sdk (passed, pre_satisfied); packages.core.tests.test_telemetry_shutdown::test_a_false_init_registers_no_atexit_hook (passed, pre_satisfied); packages.core.tests.test_telemetry_shutdown::test_one_atexit_hook_... | - | 0.94 |
| C-a58004cf | observability › Resource identifies the process › The caller's default name | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_resource_uses_the_callers_default_name (passed, pre_satisfied); packages.core.tests.test_telemetry_resource::test_service_name_resolution_order (passed, pre_satisfied); packages.core.tests.test_telemetry_resource::test_service_version_is_... | - | 0.87 |
| C-a556a3c6 | observability › Resource identifies the process › Standard variables win | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_standard_variables_win (passed, pre_satisfied); packages.core.tests.test_telemetry_resource::test_parsed_attributes_overlay_mintmory_defaults (passed, pre_satisfied); packages.core.tests.test_telemetry_resource::test_resource_attributes_f... | - | 0.94 |
| C-19d78666 | observability › Sampling and propagation follow the OpenTelemetry environment › Context propagates by default | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_context_propagates_by_default (passed, pre_satisfied); packages.core.tests.test_telemetry_resource_sampling::test_context_propagates_by_default (passed, pre_satisfied) | - | 0.75 |
| C-50f410cd | observability › Sampling and propagation follow the OpenTelemetry environment › Sampling switched off | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_sampling_switched_off (passed, pre_satisfied); packages.core.tests.test_telemetry_resource_sampling::test_sampler_always_off_exports_nothing_while_the_default_exports (passed, pre_satisfied) | - | 0.94 |
| C-1457e823 | observability › Exported spans carry no exception message › A library's exception is scrubbed | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_library_exception_is_scrubbed (passed, pre_satisfied); packages.core.tests.test_telemetry_scrubbing::test_library_span_exception_is_scrubbed (passed, red_assertion); packages.core.tests.test_telemetry_scrubbing::test_mintmory_span_excepti... | - | 0.92 |
| C-65be7944 | observability › One error-marking helper › Marking a span on and off | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_marking_a_span_off (passed, pre_satisfied); packages.core.tests.test_telemetry_acceptance_gate::test_gate_marking_a_span_on (passed, pre_satisfied); packages.core.tests.test_telemetry_mark_error::test_mark_error_on_a_noop_span_does_nothin... | - | 0.93 |
| C-e8aa74fe | observability › Telemetry test seam › Injection beats the suite's off default | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_injection_beats_the_suites_off_default (passed, pre_satisfied); packages.core.tests.test_telemetry_seam_and_globals::test_injection_beats_the_sdk_kill_switch (passed, pre_satisfied); packages.core.tests.test_telemetry_seam_and_globals::te... | - | 0.89 |
| C-90d20140 | observability › Telemetry test seam › Single injection builds no network exporter | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_single_injection_builds_no_network_exporter (passed, pre_satisfied); packages.core.tests.test_telemetry_seam_and_globals::test_single_injection_builds_no_network_exporter (passed, pre_satisfied) | - | 0.80 |
| C-29c6c2b6 | observability › Shared telemetry test fixtures › A CLI-package test uses the receiver | covered | packages.cli.tests.test_telemetry_acceptance_gate::test_gate_cli_package_test_uses_the_shared_receiver (passed, pre_satisfied); packages.cli.tests.test_telemetry_shared_fixtures::test_cli_tests_can_request_the_shared_telemetry_fixtures (passed, red_assertion); packages.cli.tests.test_telemetry_share... | - | 0.83 |
| C-59c09ecd | observability › Global providers and repeated init › A second init changes nothing | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_a_second_init_changes_nothing (passed, pre_satisfied); packages.core.tests.test_telemetry_global_providers::test_a_second_init_keeps_the_first_provider_and_tracer (passed, pre_satisfied); packages.core.tests.test_telemetry_global_provider... | - | 0.91 |
| C-836e8777 | observability › Global providers and repeated init › Re-initialisation after shutdown | covered | packages.core.tests.test_telemetry_acceptance_gate::test_gate_reinitialisation_after_shutdown (passed, pre_satisfied); packages.core.tests.test_telemetry_global_providers::test_reinit_after_shutdown_installs_a_new_global_provider (passed, pre_satisfied); packages.core.tests.test_telemetry_seam_and_g... | - | 0.93 |
| C-248f68ba | observability › _sdk_available must catch ImportError and ValueError from — feedback FB-001 › _sdk_available must catch ImportError and ValueError from | covered | packages.core.tests.test_telemetry_sdk_probe::test_module_not_found_from_find_spec_is_caught_and_warns_once (passed, red_assertion); packages.core.tests.test_telemetry_sdk_probe::test_value_error_from_find_spec_is_caught_and_auto_stays_silent (passed, red_assertion) | - | 0.88 |
| C-0f789a7e | observability › _build_meter_provider must wrap the configured metric exporter with — feedback FB-002 › _build_meter_provider must wrap the configured metric exporter with | covered | packages.core.tests.test_telemetry_metric_guard_wiring::test_metric_guard_wraps_the_console_exporter (passed, red_assertion); packages.core.tests.test_telemetry_metric_guard_wiring::test_metric_guard_wraps_the_otlp_exporter (passed, red_assertion); packages.core.tests.test_telemetry_metric_guard_wir... | - | 0.91 |

## Evidence

### Needs attention

- diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Files

| Path | Module | Label | Why |
|---|---|---|---|
| `conftest.py` |  | relevant | named in the spec |
| `openspec/changes/add-telemetry-runtime-fix-1/.l4/fix.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime-fix-1/.openspec.yaml` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime-fix-1/proposal.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime-fix-1/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime-fix-1/specs/observability/spec.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime-fix-1/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/evidence/round-1/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/evidence/round-1/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/evidence/round-1/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/evidence/round-2/evidence.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/evidence/round-2/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/evidence/round-2/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/evidence/round-3/verdict.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/evidence/round-3/verification.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T0449Z-8f57.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T0514Z-60f2.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T0849Z-8d03.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T0920Z-ec4a.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1105Z-f391.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1106Z-95fb.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1215Z-283b.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1216Z-4b11.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1441Z-49c5.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1442Z-fd5b.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1648Z-22fc.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1654Z-e095.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1655Z-d3d9.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1726Z-3acd.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1743Z-fc64.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1744Z-ea0a.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1947Z-81dc.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/ledger/r-20261016T1948Z-479c.jsonl` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/.l4/review-accepted.json` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/feedback.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/questions.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/tasks.md` |  | none | exempt: harness, spec or documentation path |
| `openspec/changes/add-telemetry-runtime/verification.md` |  | none | exempt: harness, spec or documentation path |
| `packages/api/tests/test_health_and_otel.py` |  | relevant | named in the spec |
| `packages/api/tests/test_health_and_otel_runtime.py` |  | relevant | new test file |
| `packages/cli/tests/test_telemetry_acceptance_gate.py` |  | relevant | new test file |
| `packages/cli/tests/test_telemetry_shared_fixtures.py` |  | relevant | new test file |
| `packages/core/src/mintmory/core/config.py` | core | relevant | named in the spec |
| `packages/core/src/mintmory/core/telemetry.py` | core | relevant | named in the spec |
| `packages/core/tests/test_otel_settings.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_acceptance_gate.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_enablement.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_exporters.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_global_providers.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_guards.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_helpers.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_init_failure.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_logger_level.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_mark_error.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_mark_error_span.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_metric_guard_wiring.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_resilience.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_resource.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_resource_sampling.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_scrubbing.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_scrubbing_wiring.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_sdk_probe.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_seam_and_globals.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_shutdown.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_suite_defaults.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_teardown.py` |  | relevant | new test file |
| `packages/core/tests/test_telemetry_timeouts.py` |  | relevant | new test file |
| `packages/mcp/tests/test_telemetry_init_runtime.py` |  | relevant | new test file |

### Changed functions

Diff coverage not measured: pytest-cov is active; two coverage measurements would corrupt each other

### Tests

1711 of 1825 passed, 0 failed, 0 errored, 114 skipped.
125 of 125 new tests passed.
Skipped in files the unit did not touch: `packages.core.tests.conformance.test_backend::test_anchor_candidates_limit_honoured[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_returns_sorted_scored_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_anchor_candidates_side_effect_free[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_archived_notes_excluded[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_not_counted_in_total_found[postgres]`, `packages.core.tests.conformance.test_backend::test_auto_include_populates_notes_on_results[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_stale_flags_not_penalises[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_note_useful_still_increments[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_increments_staleness[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_stale_threshold_sets_is_stale[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_staleness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_useful_increments_score_and_count[postgres]`, `packages.core.tests.conformance.test_backend::test_feedback_usefulness_cap_at_ten[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_active_match[postgres]`, `packages.core.tests.conformance.test_backend::test_find_image_file_record_returns_none_for_miss[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_cap_zero_returns_empty[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_honours_cap[postgres]`, `packages.core.tests.conformance.test_backend::test_get_annotating_descriptions_returns_description[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_flagged_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_high_staleness_useful_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_anomaly_never_accessed_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_get_existing_relates_to_pairs[postgres]`, `packages.core.tests.conformance.test_backend::test_get_flagged_memories_returns_flagged[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_high_staleness_useful_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_excludes_notes[postgres]`, `packages.core.tests.conformance.test_backend::test_get_never_accessed_stale_returns_target[postgres]`, `packages.core.tests.conformance.test_backend::test_get_rehabilitable_rows[postgres]`, `packages.core.tests.conformance.test_backend::test_get_stale_archivable_ids[postgres]`, `packages.core.tests.conformance.test_backend::test_link_add_get_basic[postgres]`, `packages.core.tests.conformance.test_backend::test_link_dedup_insert_or_ignore[postgres]`, `packages.core.tests.conformance.test_backend::test_link_filter_by_type[postgres]`, `packages.core.tests.conformance.test_backend::test_link_symmetric_both_ends_reachable[postgres]`, `packages.core.tests.conformance.test_backend::test_list_active_memory_ids_includes_only_active[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_excludes_kind_tagged[postgres]`, `packages.core.tests.conformance.test_backend::test_list_image_file_records_returns_ext_records[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_includes_archived_when_flag_set[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_includes_past_due[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_overdue_not_in_upcoming[postgres]`, `packages.core.tests.conformance.test_backend::test_list_notes_returns_plain_note[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_delete_removes_path[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_paths_returns_tracked_set[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_get_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_manifest_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_add_get_round_trip_all_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_archive[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_defaults_after_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_entity_extraction_on_add[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_false_for_missing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_exists_true_for_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_get_nonexistent_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supersede[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_supplied_entities_preserved[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_content_reextracts_entities[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_missing_id_raises_key_error[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_partial_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_memory_update_refreshes_updated_at[postgres]`, `packages.core.tests.conformance.test_backend::test_mixed_dimension_embedding_survival[postgres]`, `packages.core.tests.conformance.test_backend::test_ping_returns_true[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_1[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_depth_2[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_directional_not_reversed[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_empty_anchors[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_link_type_filter[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_min_strength_filters[postgres]`, `packages.core.tests.conformance.test_backend::test_search_around_symmetric_reverse[postgres]`, `packages.core.tests.conformance.test_backend::test_search_basic_fts_finds_relevant[postgres]`, `packages.core.tests.conformance.test_backend::test_search_bumps_retrieval_count[postgres]`, `packages.core.tests.conformance.test_backend::test_search_creates_query_session[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_archived_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_excludes_stale_by_default[postgres]`, `packages.core.tests.conformance.test_backend::test_search_prefix_matches_compound_word[postgres]`, `packages.core.tests.conformance.test_backend::test_search_respects_limit[postgres]`, `packages.core.tests.conformance.test_backend::test_search_space_split_compound_matches[postgres]`, `packages.core.tests.conformance.test_backend::test_session_create_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_session_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_session_mark_concluded[postgres]`, `packages.core.tests.conformance.test_backend::test_session_record_query_results[postgres]`, `packages.core.tests.conformance.test_backend::test_session_update_feedback_sets_fields[postgres]`, `packages.core.tests.conformance.test_backend::test_stats_counts_correct[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_get_missing_returns_none[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_list_returns_all[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_and_get[postgres]`, `packages.core.tests.conformance.test_backend::test_summary_upsert_replaces_existing[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_finds_infix_substring[postgres]`, `packages.core.tests.conformance.test_backend::test_trigram_substring_match[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_available_returns_bool[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_memory_exists_with_content[postgres]`, `packages.core.tests.conformance.test_backend::test_vector_search_returns_non_empty_results[postgres]`, `packages.core.tests.conformance.test_backend::test_write_on_one_handle_visible_on_second[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_corpus_all_memories_searchable[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_recall_at_k[postgres]`, `packages.core.tests.conformance.test_golden_retrieval::test_golden_retrieval_total_found_consistent[postgres]`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_reports_src_counts`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_dry_run_writes_nothing`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_no_row_duplication_after_force`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_with_force_succeeds`, `packages.core.tests.test_migrate.TestMigrationIdempotency::test_second_run_without_force_raises`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_embedding_vector_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_migration_report_all_ok`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_links`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_memory_round_trip`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_session`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_get_summary`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_list_notes`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_manifest_get`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_pg_search_returns_expected`, `packages.core.tests.test_migrate.TestMigrationRoundTrip::test_superseded_by_round_trip`, `packages.core.tests.test_pg_soak::test_pg_apply_feedback_lost_update_invariant`, `packages.core.tests.test_pg_soak::test_pg_soak_concurrent`, `tests.integration.test_round_trip.TestM3Sessions::test_session_feedback_updates_scores`

## S1 (recorded for calibration, never decides)

| Criterion | Status | p | Model | Engine | Note |
|---|---|---|---|---|---|
| C-2190b9f3 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-aba1a372 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-9d8f8f9c | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-ead28cef | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-4d7716fe | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-6fc7f4c6 | ok | 0.950 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-690840ae | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-5412bab8 | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-18efd0f6 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-cd710a4c | ok | 0.900 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e1c42220 | ok | 0.740 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-3852f755 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-c724dabe | ok | 0.860 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-044e54eb | ok | 0.660 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-b7126d33 | ok | 0.840 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-16b8c487 | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1d2bd9a4 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-fa66b065 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a58004cf | ok | 0.870 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-a556a3c6 | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-19d78666 | ok | 0.750 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-50f410cd | ok | 0.940 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-1457e823 | ok | 0.920 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-65be7944 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-e8aa74fe | ok | 0.890 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-90d20140 | ok | 0.800 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-29c6c2b6 | ok | 0.830 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-59c09ecd | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-836e8777 | ok | 0.930 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-248f68ba | ok | 0.880 | jev-1.13.0 | jev | evidence cut to fit the budget |
| C-0f789a7e | ok | 0.910 | jev-1.13.0 | jev | evidence cut to fit the budget |

## Human verdicts

- Q-004 reject H-e0757174 by human: Two spec violations in the production code, both reproduced by a reviewer; the gates passed because the tests stub these code paths. (1) init_telemetry() raises ModuleNotFoundError when the opentelemetry package is not installed: _sdk_available calls importlib.util.find_spec("opentelemetry.sdk"), wh...

## Criteria

| Id | Criterion | Judge | Result | Reason |
|---|---|---|---|---|
| C-2190b9f3 | observability › Telemetry enablement modes › Auto with no collector stays off | pass | pass | the judge passed it and a discriminating test passes |
| C-aba1a372 | observability › Telemetry enablement modes › Auto turns on with a collector | pass | pass | the judge passed it and a discriminating test passes |
| C-9d8f8f9c | observability › Telemetry enablement modes › Explicit off wins | pass | pass | the judge passed it and a discriminating test passes |
| C-ead28cef | observability › Telemetry enablement modes › SDK missing | pass | pass | the judge passed it and a discriminating test passes |
| C-4d7716fe | observability › Exporter selection and endpoint resolution › Console output never reaches stdout | pass | pass | the judge passed it and a discriminating test passes |
| C-6fc7f4c6 | observability › Exporter selection and endpoint resolution › One signal switched off | pass | pass | the judge passed it and a discriminating test passes |
| C-690840ae | observability › Exporter selection and endpoint resolution › Both signals off | pass | pass | the judge passed it and a discriminating test passes |
| C-5412bab8 | observability › Export never blocks or floods when the collector is absent › Export runs off the caller's thread | pass | pass | the judge passed it and a discriminating test passes |
| C-18efd0f6 | observability › Export never blocks or floods when the collector is absent › Unreachable collector logs once | pass | pass | the judge passed it and a discriminating test passes |
| C-cd710a4c | observability › Export never blocks or floods when the collector is absent › Once per signal per streak | pass | pass | the judge passed it and a discriminating test passes |
| C-e1c42220 | observability › Invalid MintMory telemetry settings fall back › Bad MintMory values fall back | pass | pass | the judge passed it and a discriminating test passes |
| C-3852f755 | observability › Invalid standard OpenTelemetry variables fall back › Bad standard values fall back | pass | pass | the judge passed it and a discriminating test passes |
| C-c724dabe | observability › Telemetry init never raises › An exporter cannot be built | pass | pass | the judge passed it and a discriminating test passes |
| C-044e54eb | observability › Telemetry init never raises › Another settings group is invalid | pass | pass | the judge passed it and a discriminating test passes |
| C-b7126d33 | observability › Bounded flush on exit › Exit is bounded when export hangs | pass | pass | the judge passed it and a discriminating test passes |
| C-16b8c487 | observability › Bounded flush on exit › Pending spans are delivered on exit | pass | pass | the judge passed it and a discriminating test passes |
| C-1d2bd9a4 | observability › Bounded flush on exit › The exporter logger level is restored | pass | pass | the judge passed it and a discriminating test passes |
| C-fa66b065 | observability › Bounded flush on exit › One atexit hook, none from the SDK | pass | pass | the judge passed it and a discriminating test passes |
| C-a58004cf | observability › Resource identifies the process › The caller's default name | pass | pass | the judge passed it and a discriminating test passes |
| C-a556a3c6 | observability › Resource identifies the process › Standard variables win | pass | pass | the judge passed it and a discriminating test passes |
| C-19d78666 | observability › Sampling and propagation follow the OpenTelemetry environment › Context propagates by default | pass | pass | the judge passed it and a discriminating test passes |
| C-50f410cd | observability › Sampling and propagation follow the OpenTelemetry environment › Sampling switched off | pass | pass | the judge passed it and a discriminating test passes |
| C-1457e823 | observability › Exported spans carry no exception message › A library's exception is scrubbed | pass | pass | the judge passed it and a discriminating test passes |
| C-65be7944 | observability › One error-marking helper › Marking a span on and off | pass | pass | the judge passed it and a discriminating test passes |
| C-e8aa74fe | observability › Telemetry test seam › Injection beats the suite's off default | pass | pass | the judge passed it and a discriminating test passes |
| C-90d20140 | observability › Telemetry test seam › Single injection builds no network exporter | pass | pass | the judge passed it and a discriminating test passes |
| C-29c6c2b6 | observability › Shared telemetry test fixtures › A CLI-package test uses the receiver | pass | pass | the judge passed it and a discriminating test passes |
| C-59c09ecd | observability › Global providers and repeated init › A second init changes nothing | pass | pass | the judge passed it and a discriminating test passes |
| C-836e8777 | observability › Global providers and repeated init › Re-initialisation after shutdown | pass | pass | the judge passed it and a discriminating test passes |
| C-248f68ba | observability › _sdk_available must catch ImportError and ValueError from — feedback FB-001 › _sdk_available must catch ImportError and ValueError from | pass | pass | the judge passed it and a discriminating test passes |
| C-0f789a7e | observability › _build_meter_provider must wrap the configured metric exporter with — feedback FB-002 › _build_meter_provider must wrap the configured metric exporter with | pass | pass | the judge passed it and a discriminating test passes |

## Findings

- [minor, judge] Unspecified: init with an injected exporter while the SDK is missing (spec gap) (criterion C-e8aa74fe): With injection and no SDK, init returns False silently with no WARNING.
- [minor, judge] Unspecified: a valid multi-item OTEL_TRACES_EXPORTER list (spec gap) (criterion C-3852f755): A fully valid list such as console,otlp is not defined by the spec. The code uses the first known item only when the list is unknown, and an exact single token otherwise.
- [major, human] Rejected hold: the diff is longer than 120000 characters: the judge saw only the start: A hold the human rejected without a fix the harness can derive. Hold: the diff is longer than 120000 characters: the judge saw only the start [rejected by human (Two spec violations in the production code, both reproduced by a reviewer; the gates passed because the tests stub these code paths. (1) init_telemetry() raises ModuleNotFoundError when the opentelemetry package is not installed: _sdk_available calls importlib.util.find_spec("opentelemetry.sdk"), which raises when the parent package is missing (telemetry.py around 668-670, reached from _resolve_state and init_telemetry outside the try...

## Fix unit

Escalated: no finding of this round can be converted into a fix task
- not converted: H-e0757174: a rejected hold with no reason, or of a kind no fix can be derived from: the human decides it

## Feedback

- FB-001: judged addressed, pending a PASS round: telemetry.py _sdk_available catches (ImportError, ValueError); test_telemetry_sdk_probe tests do not stub it.
- FB-002: judged addressed, pending a PASS round: telemetry.py _build_meter_provider wraps the exporter with _guarded_metric_exporter_class()(exporter); api test unwraps captured[-1]._inner.

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.api.tests.test_health_and_otel_runtime::test_configured_otlp_span_exporter_chain_ends_at_the_otlp_http_exporter` (task 7.1): passed
- `packages.api.tests.test_health_and_otel_runtime::test_enabled_setting_normalises_booleans_and_case` (task 7.1): passed
- `packages.api.tests.test_health_and_otel_runtime::test_explicit_false_enabled_returns_false_without_probing` (task 7.1): passed
- `packages.cli.tests.test_telemetry_acceptance_gate::test_gate_cli_package_test_uses_the_shared_receiver` (task 9.1): passed
- `packages.cli.tests.test_telemetry_shared_fixtures::test_cli_tests_can_request_the_shared_telemetry_fixtures` (task 1.2): passed
- `packages.cli.tests.test_telemetry_shared_fixtures::test_closed_port_is_a_loopback_port_nobody_listens_on` (task 1.2): passed
- `packages.cli.tests.test_telemetry_shared_fixtures::test_otlp_receiver_records_a_post_and_decodes_the_exported_spans` (task 1.2): passed
- `packages.core.tests.test_otel_settings::test_bad_mintmory_values_fall_back_with_one_warning_each` (task 2.1): passed
- `packages.core.tests.test_otel_settings::test_boolean_and_case_are_normalised` (task 2.1): passed
- `packages.core.tests.test_otel_settings::test_defaults_are_auto_otlp_no_service_name_and_three_seconds` (task 2.1): passed
- `packages.core.tests.test_otel_settings::test_non_positive_or_non_numeric_timeout_falls_back_to_three[-1]` (task 2.1): passed
- `packages.core.tests.test_otel_settings::test_non_positive_or_non_numeric_timeout_falls_back_to_three[0]` (task 2.1): passed
- `packages.core.tests.test_otel_settings::test_non_positive_or_non_numeric_timeout_falls_back_to_three[abc]` (task 2.1): passed
- `packages.core.tests.test_otel_settings::test_valid_values_are_kept` (task 2.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_a_second_init_changes_nothing` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_another_settings_group_is_invalid` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_auto_turns_on_with_a_collector` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_auto_without_collector_stays_off_in_a_fresh_process` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_bad_mintmory_values_fall_back` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_bad_standard_values_fall_back` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_both_signals_off_returns_false_without_a_warning` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_console_output_never_reaches_stdout` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_context_propagates_by_default` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_exit_is_bounded_when_export_hangs` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_explicit_off_wins` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_export_runs_off_the_calling_thread` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_exporter_logger_level_is_restored` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_guard_logs_once_per_signal_per_streak` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_init_failure_turns_telemetry_off` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_injection_beats_the_suites_off_default` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_library_exception_is_scrubbed` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_marking_a_span_off` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_marking_a_span_on` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_one_atexit_hook_none_from_the_sdk` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_one_signal_switched_off_builds_no_provider_for_it[console-none-metric]` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_one_signal_switched_off_builds_no_provider_for_it[none-console-tracer]` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_pending_spans_are_delivered_on_exit` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_reinitialisation_after_shutdown` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_reset_telemetry_restores_the_noop_shim` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_resource_uses_the_callers_default_name` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_sampling_switched_off` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_sdk_missing_warns_only_with_a_hint` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_single_injection_builds_no_network_exporter` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_standard_variables_win` (task 9.1): passed
- `packages.core.tests.test_telemetry_acceptance_gate::test_gate_unreachable_collector_logs_once` (task 9.1): passed
- `packages.core.tests.test_telemetry_enablement::test_auto_with_a_reachable_endpoint_turns_on_and_probes` (task 3.1): passed
- `packages.core.tests.test_telemetry_enablement::test_auto_with_an_endpoint_variable_turns_on_and_skips_the_probe` (task 3.1): passed
- `packages.core.tests.test_telemetry_enablement::test_auto_without_a_collector_stays_off_in_a_fresh_process` (task 3.1): passed
- `packages.core.tests.test_telemetry_enablement::test_both_signals_off_returns_false_without_a_warning` (task 3.1): passed
- `packages.core.tests.test_telemetry_enablement::test_console_exporter_writes_to_stderr_never_stdout` (task 3.1): passed

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
