# Questions — add-telemetry-runtime

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
| Q-001 | accepted | 1.1 | technical | packages/core/tests/test_telemetry_suite_defaults.py:19 — the required root conftest.py default is restored by the green guard |
<!-- l4:index:end -->

---

## Q-001: packages/core/tests/test_telemetry_suite_defaults.py:19 — the required root conftest.py default is restored by the green guard

- **Status:** accepted
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-10-16T05:08Z by deepseek, run r-20261016T0449Z-8f57, task 1.1

### Context
Line 19 asserts os.environ.get('MINTMORY_OTEL_ENABLED') == 'false'. The 'Shared telemetry test fixtures' requirement and task 1.1 say the root conftest.py SHALL give every package's tests MINTMORY_OTEL_ENABLED=false, beside the busy-timeout line. The previous green attempt added exactly os.environ.setdefault('MINTMORY_OTEL_ENABLED', 'false') plus the autouse telemetry.reset_telemetry() fixture to conftest.py; the harness logged guard.violation path=conftest.py phase=green (ledger seq 49) and restored conftest.py before the pytest gate, so the test can never pass in green. It cannot be moved into production code either: setting MINTMORY_OTEL_ENABLED from mintmory.core.telemetry would defeat the 'auto' enablement mode the spec requires for real users and is not the design's location ('Test fixtures live in the root conftest.py'). The sibling red test test_reset_telemetry_restores_the_noop_shim is implementable in telemetry.py and is not blocked; only the environment-default assertion is.

Harness note: the red tests of this task are frozen. To let the next green change `packages/core/tests/test_telemetry_suite_defaults.py`, set **Status** to `accepted` to take option 1, which names the file, or write an answer that names its path, then commit and push. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `conftest.py`: add `os.environ.setdefault("MINTMORY_OTEL_ENABLED", "false")` beside the busy-timeout line and the autouse `telemetry.reset_telemetry()` fixture, and unfreeze `conftest.py` for task 1.1.
2. Edit `packages/core/tests/test_telemetry_suite_defaults.py`: drop the line 19 `os.environ` assertion (the root conftest.py cannot be changed) and unfreeze that test file for task 1.1.

### Clarifier suggestion
Edit `conftest.py`: add `os.environ.setdefault("MINTMORY_OTEL_ENABLED", "false")` beside the busy-timeout line and the autouse `telemetry.reset_telemetry()` fixture, and unfreeze `conftest.py` for task 1.1.

### Answer
<!-- write below this line -->
