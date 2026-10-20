# Questions — multi-tenancy-reads

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
| Q-001 | accepted | 3 | technical | packages/core/tests/test_tenancy_search_reads.py:175 — trace callback expands bound parameters |
| Q-002 | open | 3 | technical | packages/core/tests/test_tenancy_search_reads.py:256-261 — internal FTS statements false-positive |
| Q-003 | open | 3 | technical | packages/core/tests/test_tenancy_search_reads.py:396-400 — observed callables are never passed to fuse_and_search |
<!-- l4:index:end -->

---

## Q-001: packages/core/tests/test_tenancy_search_reads.py:175 — trace callback expands bound parameters

- **Status:** accepted
- **Blocking tasks:** 3
- **Kind:** technical
- **Asked:** 2026-10-20T02:12Z by deepseek, run r-20261020T0204Z-bf5f, task 3

### Context
The test asserts the traced SQL contains the literal `tenant_id = ?`, but sqlite3's trace callback receives the statement with bound values substituted (`tenant_id = 't1'`), so no parameterized implementation can satisfy it. The unscoped assertion at line 182 is consequently vacuous. This contradicts requirement 2.1's intent that the predicate is a bound parameter.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_tenancy_search_reads.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy-reads`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_tenancy_search_reads.py`: line 175 to `assert "tenant_id = 't1'" in scoped[0]` and line 182 to `assert "tenant_id =" not in unscoped[0]`.

### Clarifier suggestion
Edit `packages/core/tests/test_tenancy_search_reads.py`: line 175 to `assert "tenant_id = 't1'" in scoped[0]` and line 182 to `assert "tenant_id =" not in unscoped[0]`.

### Answer
<!-- write below this line -->
---

## Q-002: packages/core/tests/test_tenancy_search_reads.py:256-261 — internal FTS statements false-positive

- **Status:** open
- **Blocking tasks:** 3
- **Kind:** technical
- **Asked:** 2026-10-20T02:12Z by deepseek, run r-20261020T0204Z-bf5f, task 3

### Context
`lacks_predicate` flags every traced statement whose text contains `memories` and lacks `tenant_id`. SQLite's own FTS5 index reads (for example `-- SELECT pgno FROM 'main'.'memories_fts_idx' ...`) contain `memories` in the index name, so they can never carry a tenant predicate and the assertion fails for any correct FTS implementation. The check should only inspect statements that read the base `memories`/`concept_links` tables.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_tenancy_search_reads.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy-reads`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_tenancy_search_reads.py`: replace the `lacks_predicate` comprehension with `[sql for sql in scoped_stmts if sql.lstrip().startswith("SELECT") and ("memories" in sql or "concept_links" in sql) and "tenant_id" not in sql]`.

### Clarifier suggestion
Edit `packages/core/tests/test_tenancy_search_reads.py`: replace the `lacks_predicate` comprehension with `[sql for sql in scoped_stmts if sql.lstrip().startswith("SELECT") and ("memories" in sql or "concept_links" in sql) and "tenant_id" not in sql]`.

### Answer
<!-- write below this line -->
---

## Q-003: packages/core/tests/test_tenancy_search_reads.py:396-400 — observed callables are never passed to fuse_and_search

- **Status:** open
- **Blocking tasks:** 3
- **Kind:** technical
- **Asked:** 2026-10-20T02:12Z by deepseek, run r-20261020T0204Z-bf5f, task 3

### Context
`_fuse_kwargs(alice)` itself calls `_fuse_callables(alice)` and returns a *different* set of fakes than the `calls` dict obtained by the preceding `_fuse_callables(alice)`, so `calls['created']`, `calls['recorded']` and `calls['bumped']` stay empty regardless of what `fuse_and_search` does. The same latent issue exists in the R3.3 test at lines 415-420, which only passes because it expects empty lists.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/core/tests/test_tenancy_search_reads.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit multi-tenancy-reads`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/core/tests/test_tenancy_search_reads.py`: change `_fuse_kwargs` to `def _fuse_kwargs(alice: Seed, callables: dict[str, Any]) -> dict[str, Any]:` and remove its internal `_fuse_callables(alice)` line; in both fuse tests do `callables, calls = _fuse_callables(alice)` and pass `**_fuse_kwargs(alice, callables)`.

### Clarifier suggestion
Edit `packages/core/tests/test_tenancy_search_reads.py`: change `_fuse_kwargs` to `def _fuse_kwargs(alice: Seed, callables: dict[str, Any]) -> dict[str, Any]:` and remove its internal `_fuse_callables(alice)` line; in both fuse tests do `callables, calls = _fuse_callables(alice)` and pass `**_fuse_kwargs(alice, callables)`.

### Answer
<!-- write below this line -->
