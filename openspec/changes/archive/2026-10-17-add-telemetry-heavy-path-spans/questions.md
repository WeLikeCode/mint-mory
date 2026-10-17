# Questions — add-telemetry-heavy-path-spans

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
| Q-001 | answered | 4.1 | technical | packages/cli/tests/test_telemetry_cli_heavy_paths.py:135 sorts by added ascending then asserts the first run has added=2 |
| Q-002 | answered | none | verdict | Hold H-8b8cc0d1: scope: `packages/core/src/mintmory/core/history/ingest.py` changes module `core`, which the spec does not name |
| Q-003 | answered | none | verdict | Hold H-e0757174: the diff is longer than 120000 characters: the judge saw only the start |
| Q-004 | answered | none | verdict | Hold H-e0757174: the diff is longer than 120000 characters: the judge saw only the start |
<!-- l4:index:end -->

---

## Q-001: packages/cli/tests/test_telemetry_cli_heavy_paths.py:135 sorts by added ascending then asserts the first run has added=2

- **Status:** answered
- **Blocking tasks:** 4.1
- **Kind:** technical
- **Asked:** 2026-10-17T15:11Z by deepseek, run r-20261017T1320Z-5212, task 4.1

### Context
The test collects the two `mintmory.cli.index-tree` attribute dicts and sorts them ascending by `mintmory.files.added`, naming element 0 `first_run`; it then asserts `first_run` has added=2, updated=0, unchanged=0 (the physical first run). The spec requirement and finding F-b98cfc require `.added`, `.updated`, `.unchanged`, `.failed` to mirror `index_tree`'s existing counters (`added`, `updated`, `unchanged`, `failed`): the first run adds 2 files (added=2, updated=0, unchanged=0) and the second run modifies one file and leaves one unchanged (added=0, updated=1, unchanged=1). Ascending-by-added therefore always puts the second run at index 0, so no spec-compliant implementation can make this frozen test pass.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `packages/cli/tests/test_telemetry_cli_heavy_paths.py`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit add-telemetry-heavy-path-spans`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `packages/cli/tests/test_telemetry_cli_heavy_paths.py`: change the sort key on line 135 from `a.get("mintmory.files.added", 0)` to `a.get("mintmory.files.updated", 0)` so the first run (updated=0) sorts first and every assertion holds.
2. Edit `packages/cli/tests/test_telemetry_cli_heavy_paths.py`: add `reverse=True` to the `sorted(...)` call on lines 134-136 so the run with added=2 sorts first.

### Clarifier suggestion
Edit `packages/cli/tests/test_telemetry_cli_heavy_paths.py`: change the sort key on line 135 from `a.get("mintmory.files.added", 0)` to `a.get("mintmory.files.updated", 0)` so the first run (updated=0) sorts first and every assertion holds.

### Answer
<!-- write below this line -->
Edit packages/cli/tests/test_telemetry_cli_heavy_paths.py: the test bug is the ordering, not the assertions. Sorting ascending by mintmory.files.added always puts the second run (added=0) first. Order the two index-tree spans by when they started, which is the real order of the two runs: by_start = sorted(spans, key=lambda s: s.start_time), then first_run, second_run = _attributes(by_start[0]), _attributes(by_start[1]). Keep every assertion unchanged (first run 2 added, 0 updated, 0 unchanged, 0 failed; second run 1 updated, 1 unchanged, 0 failed). Do not sort by another counter.

---

## Q-002: Hold H-8b8cc0d1: scope: `packages/core/src/mintmory/core/history/ingest.py` changes module `core`, which the spec does not name

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 2, verifier

### Context
After round 2 the verifier cannot decide on its own: scope: `packages/core/src/mintmory/core/history/ingest.py` changes module `core`, which the spec does not name

Answer `accept` if the unit can go on as it stands, or `reject` and say why: a rejected hold is fixed by a fix unit.

### Options
1. accept
2. reject: <reason>

### Answer
<!-- write below this line -->
accept: in scope. The proposal names history/ingest.py among the files this change edits, and the spec requires that work handed to thread pools in history backfill and sync runs in a fresh copy of the caller's context per task. The diff of packages/core/src/mintmory/core/history/ingest.py is exactly that: _prepare_session is wrapped in telemetry.run_in_context before it is submitted to the executor, in backfill and in sync, and nothing else changes.
---

## Q-003: Hold H-e0757174: the diff is longer than 120000 characters: the judge saw only the start

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 2, verifier

### Context
After round 2 the verifier cannot decide on its own: the diff is longer than 120000 characters: the judge saw only the start

Answer `accept` if the unit can go on as it stands, or `reject` and say why; end the reason with a sentence WHEN ... THEN ... so that a fix unit can be made.

### Options
1. accept
2. reject: <reason>

### Answer
<!-- write below this line -->
reject: an independent full-diff review (51/51 unit tests and the full gate pass; with telemetry off every command matches the base) found two breaks of this spec's rule that recording a metric point or attribute SHALL never raise into the caller (spec.md line 35; tasks.md asks for try/except). (1) telemetry.counts_added (telemetry.py:1006) calls add_count outside its try, and add_count does not guard counter.add or the instrument creation: with a failing meter, storage add_memory (storage.py:468, storage_postgres.py:418) raises RuntimeError after the row is stored, so mintmory add exits non-zero and a retry stores a duplicate. (2) span() sets attributes without a guard (telemetry.py:630), so embed_span and file_span make embed() raise when set_attribute raises. WHEN the meter, a counter's add, a histogram's record or a span's set_attribute raises inside a telemetry helper (counts_added, add_count, record_value, the span attributes of embed_span and file_span) THEN the error stays inside telemetry: add_memory returns the stored record, embed() and the wrapped call run and return normally, and the attribute or point is dropped.

---

## Q-004: Hold H-e0757174: the diff is longer than 120000 characters: the judge saw only the start

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 4, verifier

### Context
After round 4 the verifier cannot decide on its own: the diff is longer than 120000 characters: the judge saw only the start

Answer `accept` if the unit can go on as it stands, or `reject` and say why; end the reason with a sentence WHEN ... THEN ... so that a fix unit can be made.

### Options
1. accept
2. reject: <reason>

### Answer
<!-- write below this line -->
accept: the hold is only about the diff's length (2.2 MB, of which about 202 kB is code and tests; the rest is the harness's own ledger and verification files). Since the full-diff review that rejected round 3 (Q-003), the unit changed only by fix-2: a new test file (test_telemetry_helper_guards.py, no pre-existing test touched) and telemetry.py, where add_count and record_value now wrap instrument creation and add/record in try/except, counts_added guards its add_count call, and span() sets attributes through _set_attribute_safe; the one other set_attribute call (_set_result_count) was already guarded, and no other module sets span attributes. Both defects named in Q-003 are closed, and round 4 passes every gate (setup, ruff, format, mypy, pytest) with 22/22 criteria covered.
