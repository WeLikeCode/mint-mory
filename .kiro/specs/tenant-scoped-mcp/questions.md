# Questions — tenant-scoped-mcp

<!-- l4:questions v1
How to answer: write under "### Answer" and set **Status** to `answered`.
To accept the clarifier's suggestion as-is, set **Status** to `accepted`.
Status values: open · answered · accepted · answered-by-clarifier · dismissed · superseded
Kind values: technical · product · ambiguous · verdict · harness. For a `verdict` question, start the answer with `accept` or
`reject`, then give your reason; for a `harness` question, with `accept` or `retry`.
Do not change question IDs. Commit and push to the l4/… branch to resume the run. -->

<!-- l4:index:start -->
| ID | Status | Blocking | Kind | Question |
|----|--------|----------|------|----------|
| Q-001 | open | 4 | technical | packages/mcp/tests/test_tools.py:51 test_all_tools_registered does not include the required tenant tools |
<!-- l4:index:end -->

---

## Q-001: packages/mcp/tests/test_tools.py:51 test_all_tools_registered does not include the required tenant tools

- **Status:** open
- **Blocking tasks:** 4
- **Kind:** technical
- **Asked:** 2026-10-20T23:49Z by deepseek, run r-20261020T2148Z-440a, task 4

### Context
Criteria R2.2/C-6530b3da and the red test test_mcp_tenancy_directory.py require tenant_create and tenant_list to be registered, and the task text says test_all_tools_registered gains them. The frozen legacy test packages/mcp/tests/test_tools.py:51 asserts names == the old 18-tool set without tenant_create/tenant_list, so no server implementation can make both tests pass. The previous attempt was rejected for editing this frozen file.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/mcp/tests/test_tools.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit tenant-scoped-mcp`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/mcp/tests/test_tools.py`: add `"tenant_create",` and `"tenant_list",` to the expected set in `test_all_tools_registered`.
2. Leave test_tools.py frozen and withdraw the requirement that tenant_create and tenant_list be registered.

### Clarifier suggestion
Edit `packages/mcp/tests/test_tools.py`: add `"tenant_create",` and `"tenant_list",` to the expected set in `test_all_tools_registered`.

### Answer
<!-- write below this line -->
