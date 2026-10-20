# Verification: kiro:multi-tenancy-cli: FAIL (round 6)

traceability: not checked (an earlier step failed)

- Base: `7ae2320de153d99a3aef4d11ef87be3d8b8e4aac`
- Head: `695f4afbe2c79f073acda897093d05c259410f98`
- Implementer profiles: deepseek, glm
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | failed | 0.2 | base staging@7ae2320de1 contained; Feedback FB-001 (tests): CLI help tests must not depend on terminal colour (repository CI fails) |
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

- [major, feedback] Feedback FB-001 (tests): CLI help tests must not depend on terminal colour (repository CI fails): test_help_documents_the_tenant_option passes in the L4 gates but fails in the repository CI (GitHub Actions run 39482344837, job 'lint · types · tests', step 'Pytest (coverage gate ≥ 80%)': 1 failed, 2277 passed). In GitHub Actions the variable GITHUB_ACTIONS is set, and Typer then forces a colour terminal: typer/rich_utils.py sets FORCE_TERMINAL = True when GITHUB_ACTIONS, FORCE_COLOR or PY_COLORS is set, and _get_rich_console() reads FORCE_TERMINAL on every call. The --help output then carries ANSI escape codes, so the plain sentence 'Tenant id. Absent or 'global': reads span every tenant an...

## Fix unit

Fix unit 3 is created for these tasks:
- F-250a0697 Feedback FB-001 (tests): CLI help tests must not depend on terminal colour (repository CI fails)

## New tests (red then green, `task.red_ok` in the ledger)

- `packages.cli.tests.test_cli_tenancy::test_add_search_and_stats_use_the_selected_tenant` (task 2): not in the report
- `packages.cli.tests.test_cli_tenancy::test_docs_commands_are_read_tenant_scoped` (task 2): not in the report
- `packages.cli.tests.test_cli_tenancy::test_dream_is_confined_to_the_selected_tenant` (task 2): not in the report
- `packages.cli.tests.test_cli_tenancy::test_image_commands_use_the_selected_tenant` (task 2): not in the report
- `packages.cli.tests.test_cli_tenancy::test_ingest_dedups_within_the_write_tenant` (task 2): not in the report
- `packages.cli.tests.test_cli_tenancy::test_missing_and_inactive_tenants_are_handled` (task 2): not in the report
- `packages.cli.tests.test_cli_tenancy::test_note_and_notes_are_tenant_scoped` (task 2): not in the report
- `packages.cli.tests.test_cli_tenancy::test_summary_commands_use_the_selected_tenant` (task 2): not in the report
- `packages.cli.tests.test_cli_tenancy::test_tenant_create_reports_created_again_and_invalid_ids` (task 3): not in the report
- `packages.cli.tests.test_cli_tenancy::test_tenant_list_reports_fresh_global_and_created_tenants` (task 3): not in the report
- `packages.cli.tests.test_cli_tenancy::test_valid_tenant_option_does_not_change_the_tenant_directory` (task 3): not in the report
- `packages.cli.tests.test_cli_tenancy::test_vision_run_and_caption_put_use_the_write_tenant` (task 2): not in the report
- `packages.cli.tests.test_cli_tenancy_gate::test_gate_full_cli_tenancy_flow_and_coverage_floor` (task 5): not in the report
- `packages.cli.tests.test_cli_tenancy_image_caption_put_fix::test_image_caption_put_refuses_a_global_image_with_exit_one` (task 1.1): not in the report
- `packages.cli.tests.test_cli_tenancy_image_caption_put_fix::test_image_caption_put_without_an_active_record_exits_one[/tmp/no-such-image.png]` (task 1.1): not in the report
- `packages.cli.tests.test_cli_tenancy_image_caption_put_fix::test_image_caption_put_without_an_active_record_exits_one[no-such-image-id]` (task 1.1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_doctor_refuses_a_named_tenant` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_help_documents_the_tenant_option` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_history_refuses_a_named_tenant` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_index_tree_refuses_a_named_tenant` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_invalid_tenant_is_rejected_before_any_command` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_mcp_serve_refuses_a_named_tenant` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_migrate_storage_refuses_a_named_tenant` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_refusals_and_validation_happen_before_the_command` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_serve_refuses_a_named_tenant_but_runs_unscoped` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_tenant_migration_error_is_reported` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_tenant_not_found_from_a_write_is_reported` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_tenant_option_goes_before_the_command` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_tenant_scope_maps_absent_empty_global_and_named` (task 1): not in the report
- `packages.cli.tests.test_cli_tenancy_root::test_valid_tenant_does_not_change_the_tenant_directory` (task 1): not in the report
- `tests.integration.test_tenancy_cli::test_cli_tenancy_sequence_on_one_sqlite_file` (task 4): not in the report
