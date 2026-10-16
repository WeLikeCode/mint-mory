# Questions — add-telemetry-runtime-fix-1

<!-- l4:questions v1
How to answer: write under "### Answer" and set **Status** to `answered`.
To accept the clarifier's suggestion as-is, set **Status** to `accepted`.
Status values: open · answered · accepted · answered-by-clarifier · dismissed · superseded
Kind values: technical · product · ambiguous · verdict. For a `verdict` question, start the answer with `accept` or
`reject`, then give your reason.
Do not change question IDs. Commit and push to the l4/… branch to resume the run. -->

<!-- l4:index:start -->
| ID | Status | Blocking | Kind | Question |
|----|--------|----------|------|----------|
| Q-001 | open | 1.2 | technical | packages/api/tests/test_health_and_otel.py:135 still asserts the reader got the raw OTLP exporter; FB-002 requires the guard, so it must unwrap `_inner` |
<!-- l4:index:end -->

---

## Q-001: packages/api/tests/test_health_and_otel.py:135 still asserts the reader got the raw OTLP exporter; FB-002 requires the guard, so it must unwrap `_inner`

- **Status:** open
- **Blocking tasks:** 1.2
- **Kind:** technical
- **Asked:** 2026-10-16T17:17Z by deepseek, run r-20261016T1655Z-d3d9, task 1.2

### Context
The red test packages/core/tests/test_telemetry_metric_guard_wiring.py and criterion C-0f789a7e require `_build_meter_provider` to hand `PeriodicExportingMetricReader` a `_GuardedMetricExporter` wrapping the configured exporter. That makes `captured[-1]` (the exporter passed to the reader) the guard, so `packages/api/tests/test_health_and_otel.py::test_telemetry_metric_exporter_matches_configured_exporter` fails: line 135 asserts `isinstance(captured[-1], me_mod.OTLPMetricExporter)` and line 139 asserts `isinstance(captured[-1], export_mod.ConsoleMetricExporter)`. Feedback FB-002 and task 7.1 explicitly state this test must unwrap `_inner` to the OTLP/console metric exporter, but the test was frozen before that edit and green may not change test files. The prior green attempt was rejected for exactly this reason.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_telemetry_metric_guard_wiring.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit add-telemetry-runtime-fix-1`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/api/tests/test_health_and_otel.py`: change line 135 to `assert isinstance(captured[-1]._inner, me_mod.OTLPMetricExporter)` and line 139 to `assert isinstance(captured[-1]._inner, export_mod.ConsoleMetricExporter)`.
2. Move this test edit into the red step for task 1.2 and re-run green with the file unfrozen.

### Clarifier suggestion
Edit `packages/api/tests/test_health_and_otel.py`: change line 135 to `assert isinstance(captured[-1]._inner, me_mod.OTLPMetricExporter)` and line 139 to `assert isinstance(captured[-1]._inner, export_mod.ConsoleMetricExporter)`.

### Answer
<!-- write below this line -->
