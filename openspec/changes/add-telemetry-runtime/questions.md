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
| Q-002 | open | 1.1 | technical | packages/core/tests/test_telemetry_suite_defaults.py:19 — the required root conftest.py default is a test-support file the green freeze always restores |
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

---

## Q-002: packages/core/tests/test_telemetry_suite_defaults.py:19 — the required root conftest.py default is a test-support file the green freeze always restores

- **Status:** open
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-10-16T05:24Z by deepseek, run r-20261016T0514Z-60f2, task 1.1

### Context
The red test test_suite_runs_with_otel_disabled_by_default asserts os.environ.get('MINTMORY_OTEL_ENABLED') == 'false'. Spec 'Shared telemetry test fixtures' and task 1.1 place that default in the root conftest.py, beside the existing busy-timeout setdefault. But the harness freezes **/conftest.py as a test-support file and restore_frozen/revert_unsnapshotted put it back after every green step; unfrozen() only grants kind=='test' files, so an answer naming conftest.py is recorded as 'kept'. Q-001's accepted option 1 named conftest.py, so nothing was unfrozen: run r-20261016T0514Z-60f2 seq 29 logged guard.violation path=conftest.py and the test failed with None != 'false'. Setting MINTMORY_OTEL_ENABLED from mintmory.core.telemetry is not allowed (it defeats the spec's 'auto' mode) and a new test module or test config is frozen too. So the assertion can only pass if the frozen test file itself is changed, which a human answer unfreezes by naming it.

Harness note: the red tests of this task are frozen. To let the next green change `packages/core/tests/test_telemetry_suite_defaults.py`, set **Status** to `accepted` to take option 1, which names the file, or write an answer that names its path, then commit and push. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_telemetry_suite_defaults.py`: replace the body of `test_suite_runs_with_otel_disabled_by_default` with a docstring and `pass`, and drop the now-unused `import os`; the root `conftest.py` default cannot be set in green because the harness restores that test-support file, so the suite default moves to the harness/CI environment and the red proof for task 1.1 becomes `test_reset_telemetry_restores_the_noop_shim`
2. Edit `packages/core/tests/test_telemetry_suite_defaults.py`: change the line-19 assertion to `assert os.environ.get("MINTMORY_OTEL_ENABLED", "false").lower() in {"false", "0"}` so it passes whether the default is unset or 'false', keeping the assertion and the `import os`

### Clarifier suggestion
Edit `packages/core/tests/test_telemetry_suite_defaults.py`: replace the body of `test_suite_runs_with_otel_disabled_by_default` with a docstring and `pass`, and drop the now-unused `import os`; the root `conftest.py` default cannot be set in green because the harness restores that test-support file, so the suite default moves to the harness/CI environment and the red proof for task 1.1 becomes `test_reset_telemetry_restores_the_noop_shim`

### Answer
<!-- write below this line -->
