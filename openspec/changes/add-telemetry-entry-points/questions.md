# Questions — add-telemetry-entry-points

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
| Q-001 | open | 1.4 | technical | packages/mcp/tests/test_telemetry_init.py:25 rejects the new init_telemetry signature |
<!-- l4:index:end -->

---

## Q-001: packages/mcp/tests/test_telemetry_init.py:25 rejects the new init_telemetry signature

- **Status:** open
- **Blocking tasks:** 1.4
- **Kind:** technical
- **Asked:** 2026-10-17T02:08Z by deepseek, run r-20261017T0137Z-49a4, task 1.4

### Context
test_main_initialises_telemetry_before_serving replaces server.init_telemetry with `_fake_init_telemetry(settings: Any = None) -> bool`. Task 1.4 (tasks.md) and observability 'Every entry point initialises telemetry once' require mintmory.mcp.server.main() to call `init_telemetry(default_service_name="mintmory-mcp")` with no settings, so the fake receives an unexpected keyword `default_service_name` and raises TypeError, breaking a test that passed before this green step. tasks.md 1.5 already specifies the fix for this fake, but the green phase freezes every test file (the harness reverted my earlier edit to it), so the production change cannot pass the gate without this unfreeze.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/mcp/tests/test_telemetry_init.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit add-telemetry-entry-points`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/mcp/tests/test_telemetry_init.py`: change line 25 ` def _fake_init_telemetry(settings: Any = None) -> bool:` to ` def _fake_init_telemetry(settings: Any = None, **kwargs: Any) -> bool:`
2. Unfreeze the whole file for task 1.4 so I can apply tasks.md 1.5's changes (accept **kwargs, assert settings is None and kwargs["default_service_name"] == "mintmory-mcp", and add the history server test)

### Clarifier suggestion
Edit `packages/mcp/tests/test_telemetry_init.py`: change line 25 `    def _fake_init_telemetry(settings: Any = None) -> bool:` to `    def _fake_init_telemetry(settings: Any = None, **kwargs: Any) -> bool:`

### Answer
<!-- write below this line -->
