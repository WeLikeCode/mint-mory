# Verification: kiro:multi-tenancy-cli: FAIL (round 4)

traceability: not checked (an earlier step failed)

- Base: `7ae2320de153d99a3aef4d11ef87be3d8b8e4aac`
- Head: `c994c20bc90f376cec59af7fef8680e934f2b61b`
- Implementer profiles: deepseek
- Judge: claude-judge, 0 call(s), prompt sha256 `-`

## Ladder

| Step | Name | Status | Seconds | Note |
|---|---|---|---|---|
| 0 | preconditions | failed | 0.1 | base staging@7ae2320de1 contained; repository CI failed: ci.yml / lint · types · tests |
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

- [blocker, deterministic] repository CI failed: ci.yml / lint · types · tests: job `ci.yml / lint · types · tests` failed on the hand-off commit c994c20bc9 (<forge>/WeLikeCode/mint-mory/actions/runs/39482344837/job/118834065447). Log ends: ...0T19:21:18.7389830Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, astral-sh/setup-uv@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/. 33336 1929 94% 2026-10-20T19:21:17.5276081Z Required test coverage of 80% reached. Total coverage: 94.21% 2026-10-20T19:21:17.5276812Z...

## Fix unit

Fix unit 2 is created for these tasks:
- F-fda7e586 repository CI failed: ci.yml / lint · types · tests

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
