# Delivery plan multitenancy

- Status: stopped
- Repository: https://github.com/WeLikeCode/mint-mory
- Target: staging at db0436bc5abf44f807c3129b90040fb5de13b97b
- Merge: auto
- No promotion target is set. Promotion was not performed.
- Written: 2026-10-21T03:51:35Z
- Stopped: unit_halted (kiro:cross-tenant-copy): task 2: max_task_attempts (3) reached in red on glm (3), deepseek (2); last failure: vacuous: C-02945d2c (none of its tests fails by assertion: packages.core.tests.test_transfer_selection::test_duplicate_contents_inside_one_selection_copy_once, packages.core.tests.test_transfer_selection::test_inact

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
- Result: integrated at 14bde5a778bc68a9a0d08404c16e119a3215417d
- Pull request: 44
- Merge commit: 14bde5a778bc68a9a0d08404c16e119a3215417d
- Post-merge check: pass with profile all (5 gate(s) passed; skipped (not configured): build, e2e)
- Usage: $8.92, 10 run(s), 1 attempt(s)

### kiro:tenant-scoped-mcp
- Result: integrated at db0436bc5abf44f807c3129b90040fb5de13b97b
- Pull request: 45
- Merge commit: db0436bc5abf44f807c3129b90040fb5de13b97b
- Post-merge check: pass with profile all (5 gate(s) passed; skipped (not configured): build, e2e)
- Usage: $1.80, 2 run(s), 1 attempt(s)

### kiro:cross-tenant-copy
- Result: not integrated
- Pull request: <forge>/WeLikeCode/mint-mory/pull/46
- Merge commit: none
- Post-merge check: not run
- Usage: $0.11, 1 run(s), 1 attempt(s)

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

- Cost: $21.81
- Of which the readiness review: $3.64
- Runs that dispatched a unit: 28
