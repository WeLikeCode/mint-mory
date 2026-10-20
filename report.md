# Delivery plan multitenancy

- Status: stopped
- Repository: https://github.com/WeLikeCode/mint-mory
- Target: staging at 7ae2320de153d99a3aef4d11ef87be3d8b8e4aac
- Merge: auto
- No promotion target is set. Promotion was not performed.
- Written: 2026-10-20T20:38:37Z
- Stopped: unit_halted (kiro:multi-tenancy-cli): task 1.1: max_task_attempts (3) reached in single; last failure: new failing tests added in green: packages.cli.tests.test_cli_help_no_colour::test_help_resets_forced_colour_and_documents_tenant_option

## Units

### kiro:multi-tenancy
- Result: integrated at 5d73c5c56746a639ee128bd0e3975a20243fbe65
- Pull request: 40
- Merge commit: 5d73c5c56746a639ee128bd0e3975a20243fbe65
- Post-merge check: pass with profile all (5 gate(s) passed; skipped (not configured): build, e2e)
- Usage: $1.27, 5 run(s), 1 attempt(s)

### kiro:multi-tenancy-writes
- Result: integrated at fa4a2494d2e4aae40e044e8badaf6841bde6af82
- Pull request: 41
- Merge commit: fa4a2494d2e4aae40e044e8badaf6841bde6af82
- Post-merge check: pass with profile all (5 gate(s) passed; skipped (not configured): build, e2e)
- Usage: $1.60, 2 run(s), 1 attempt(s)

### kiro:multi-tenancy-reads
- Result: integrated at 47bb91111d99442cc9d5ab63a9396eae5c569a5d
- Pull request: 42
- Merge commit: 47bb91111d99442cc9d5ab63a9396eae5c569a5d
- Post-merge check: pass with profile all (5 gate(s) passed; skipped (not configured): build, e2e)
- Usage: $2.46, 3 run(s), 1 attempt(s)

### kiro:tenant-scoped-core
- Result: integrated at 50be8282b07d9be15bd7d36f911627f716caf6e6
- Pull request: 43
- Merge commit: 50be8282b07d9be15bd7d36f911627f716caf6e6
- Post-merge check: pass with profile all (5 gate(s) passed; skipped (not configured): build, e2e)
- Usage: $2.01, 5 run(s), 1 attempt(s)

### kiro:multi-tenancy-cli
- Result: not integrated
- Pull request: <forge>/WeLikeCode/mint-mory/pull/44
- Merge commit: none
- Post-merge check: not run
- Usage: $5.78, 8 run(s), 1 attempt(s)

### kiro:tenant-scoped-mcp
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### kiro:cross-tenant-copy
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### kiro:multi-tenancy-postgres
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### kiro:multi-tenancy-postgres-writes
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

### kiro:multi-tenancy-postgres-reads
- Result: not integrated
- Pull request: none
- Merge commit: none
- Post-merge check: not run
- Usage: $0.00, 0 run(s), 1 attempt(s)

## Batches

- tenancy-sqlite (profile none): accepted at 47bb91111d99442cc9d5ab63a9396eae5c569a5d
- tenancy-surfaces (profile none): not checked
- tenancy-postgres (profile none): not checked

## Usage

- Cost: $16.76
- Of which the readiness review: $3.64
- Runs that dispatched a unit: 23
