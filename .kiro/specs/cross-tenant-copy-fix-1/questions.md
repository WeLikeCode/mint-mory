# Questions — cross-tenant-copy-fix-1

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
| Q-001 | answered | 1.1 | ambiguous | Conflicting frozen test blocks the R3.2 fix |
<!-- l4:index:end -->

---

## Q-001: Conflicting frozen test blocks the R3.2 fix

- **Status:** answered
- **Blocking tasks:** 1.1
- **Kind:** ambiguous
- **Asked:** 2026-10-21T07:37Z by deepseek, run r-20261021T0729Z-ec22, task 1.1

### Context
Criterion C-18a7043f and design finding F-37e92031 require all_active over more than COPY_MAX non-superseded source rows to raise CopySelectionError even when some rows are destination duplicates. The existing test packages/core/tests/test_transfer_selection.py::test_skipped_duplicates_do_not_count_toward_copy_max seeds 3 active rows (one a destination duplicate) with COPY_MAX=2 and asserts all_active succeeds with 2 copies and 1 duplicate skip. The design explicitly says that test encodes the wrong rule and asks to keep R3.4's point with a selection that passes R3.2, i.e. change the test. The harness rejected my previous attempt for changing that existing test and says to leave existing tests as they are, and to report blocked with a question if one is wrong. Under the new rule the frozen test cannot pass, so the fix and the frozen test cannot both be satisfied. How should I proceed?

### Options
1. Allow modifying or replacing test_skipped_duplicates_do_not_count_toward_copy_max as the design requests.
2. Keep that test frozen and do not implement the R3.2 all_active cap, accepting that C-18a7043f stays unmet.
3. Provide a different mechanism (for example a renamed replacement test) that the harness will accept without changing the frozen test.

### Answer
<!-- write below this line -->
Option 1: unfreeze packages/core/tests/test_transfer_selection.py for task 1.1 and change only test_skipped_duplicates_do_not_count_toward_copy_max, which encodes the wrong rule for all_active. Keep its point (R3.4: skipped duplicates do not count toward COPY_MAX in the records to copy) with explicit ids, which R3.2 does not cover: COPY_MAX = 2, memory_ids=[dup, m2] where dup's content already exists in the destination and m2 has one active attached note; the copy succeeds with m2 and its note copied (2 records) and 1 duplicate skipped, while counting the duplicate would make 3 > 2. The new R3.2 behaviour (all_active or a filter over more than COPY_MAX remaining rows raises before any write) gets its own test. Change no other existing test.
