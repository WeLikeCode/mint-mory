# Questions — cross-tenant-copy

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
| Q-001 | accepted | 4 | technical | packages/mcp/tests/test_mcp_tenancy_directory.py:87-115 and :257 omit tenant_copy from the frozen expected inventory |
| Q-002 | accepted | 4 | technical | packages/mcp/tests/test_tools.py:51-72 omits tenant_copy from the frozen registered-tool names |
| Q-003 | open | 5 | technical | packages/cli/tests/test_cli_tenant_copy.py:272 asserts an empty id_map after a successful copy |
<!-- l4:index:end -->

---

## Q-001: packages/mcp/tests/test_mcp_tenancy_directory.py:87-115 and :257 omit tenant_copy from the frozen expected inventory

- **Status:** accepted
- **Blocking tasks:** 4
- **Kind:** technical
- **Asked:** 2026-10-21T06:08Z by deepseek, run r-20261021T0355Z-3d98, task 4

### Context
The red suite requires server.TOOL_TENANT_SCOPE["tenant_copy"] == "copy" and the tool to be registered, and R8.1 says this unit updates this test in place. The frozen file still expects the old inventory (no tenant_copy), the old value-kind set ({read, create, modify, dream, directory}), and tenant_properties == {"tenant_create": {"tenant_id"}}; test_tool_inventory_matches_declared_tenant_scope and test_no_tool_exposes_a_tenant_selector therefore fail as soon as tenant_copy is registered, so green cannot both implement R8.1 and keep this file passing.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/mcp/tests/test_mcp_tenancy_directory.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit cross-tenant-copy`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/mcp/tests/test_mcp_tenancy_directory.py`: add `"tenant_copy": "copy",` after `"tenant_list": "directory",` in `expected`; add `"copy"` to the literal on line 114 so it reads `assert set(declared.values()) == {"read", "create", "modify", "dream", "directory", "copy"}`; and change line 257 to `assert tenant_properties == {"tenant_create": {"tenant_id"}, "tenant_copy": {"source_tenant", "dest_tenant"}}`.

### Clarifier suggestion
Edit `packages/mcp/tests/test_mcp_tenancy_directory.py`: add `"tenant_copy": "copy",` after `"tenant_list": "directory",` in `expected`; add `"copy"` to the literal on line 114 so it reads `assert set(declared.values()) == {"read", "create", "modify", "dream", "directory", "copy"}`; and change line 257 to `assert tenant_properties == {"tenant_create": {"tenant_id"}, "tenant_copy": {"source_tenant", "dest_tenant"}}`.

### Answer
<!-- write below this line -->
---

## Q-002: packages/mcp/tests/test_tools.py:51-72 omits tenant_copy from the frozen registered-tool names

- **Status:** accepted
- **Blocking tasks:** 4
- **Kind:** technical
- **Asked:** 2026-10-21T06:08Z by deepseek, run r-20261021T0355Z-3d98, task 4

### Context
R8.1 says test_all_tools_registered gains tenant_copy, and the red suite requires the tool to be registered. The frozen file's expected set still ends at tenant_list, so test_all_tools_registered fails with "Extra items in the left set: 'tenant_copy'" as soon as green registers the tool.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/mcp/tests/test_tools.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit cross-tenant-copy`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/mcp/tests/test_tools.py`: add `"tenant_copy",` after `"tenant_list",` in the expected names set of test_all_tools_registered.

### Clarifier suggestion
Edit `packages/mcp/tests/test_tools.py`: add `"tenant_copy",` after `"tenant_list",` in the expected names set of test_all_tools_registered.

### Answer
<!-- write below this line -->

---

## Q-003: packages/cli/tests/test_cli_tenant_copy.py:272 asserts an empty id_map after a successful copy

- **Status:** open
- **Blocking tasks:** 5
- **Kind:** technical
- **Asked:** 2026-10-21T06:37Z by deepseek, run r-20261021T0612Z-645f, task 5

### Context
The test copies one memory (`w1`, `memories_copied == 1`) via `--entity Widget` and then asserts `entity_report["id_map"] == {}`. Requirement 1 defines `id_map` as source id -> new id, Requirement 5.1 assigns the new id while planning before any write, and R9.2/R9.10/MCP tests assert the copied ids appear in `id_map`. An empty `id_map` with `memories_copied == 1` is impossible under the spec and design, so the test is wrong.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/cli/tests/test_cli_tenant_copy.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit cross-tenant-copy`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/cli/tests/test_cli_tenant_copy.py`: replace `assert entity_report["id_map"] == {}` with `assert list(entity_report["id_map"]) == ["w1"]`

### Clarifier suggestion
Edit `packages/cli/tests/test_cli_tenant_copy.py`: replace `assert entity_report["id_map"] == {}` with `assert list(entity_report["id_map"]) == ["w1"]`

### Answer
<!-- write below this line -->
