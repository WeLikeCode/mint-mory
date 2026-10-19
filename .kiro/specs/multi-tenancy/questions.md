# Questions — multi-tenancy

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
| Q-001 | open | 5 | technical | packages/core/tests/test_tenant_directory.py:191 |
<!-- l4:index:end -->

---

## Q-001: packages/core/tests/test_tenant_directory.py:191

- **Status:** open
- **Blocking tasks:** 5
- **Kind:** technical
- **Asked:** 2026-10-19T16:22Z by deepseek, run r-20261019T1437Z-76f9, task 5

### Context
test_set_tenant_active_updates_flag_and_timestamp calls `_insert_tenant(store, "acme", name="Acme", updated_at="2020-01-01T00:00:00")`. The helper defaults `created_at` to "2026-01-01T00:00:00", but line 199 asserts `row["created_at"] == "2020-01-01T00:00:00"`. set_tenant_active must not modify created_at, so the assertion is unsatisfiable as written; the spec (R5.4) only says to update is_active and updated_at.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_tenant_directory.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_tenant_directory.py`: at line 191 change `_insert_tenant(store, "acme", name="Acme", updated_at="2020-01-01T00:00:00")` to `_insert_tenant(store, "acme", name="Acme", created_at="2020-01-01T00:00:00", updated_at="2020-01-01T00:00:00")`
2. Edit `packages/core/tests/test_tenant_directory.py`: at line 199 change `assert row["created_at"] == "2020-01-01T00:00:00"` to `assert row["created_at"] == "2026-01-01T00:00:00"`

### Clarifier suggestion
Edit `packages/core/tests/test_tenant_directory.py`: at line 191 change `_insert_tenant(store, "acme", name="Acme", updated_at="2020-01-01T00:00:00")` to `_insert_tenant(store, "acme", name="Acme", created_at="2020-01-01T00:00:00", updated_at="2020-01-01T00:00:00")`

### Answer
<!-- write below this line -->
