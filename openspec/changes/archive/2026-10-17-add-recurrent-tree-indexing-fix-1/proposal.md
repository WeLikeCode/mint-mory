# Proposal: fix 1 for add-recurrent-tree-indexing

## Why
The verifier found problems in `add-recurrent-tree-indexing` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-b34b9dc3 (major): task 2.3 is ticked as already satisfied, but its text is not done: Decided by human in Q-007: the finding is right. Task 2.3 also asks to update the --text-content help text and the index_tree docstring to say that online-only files are skipped by this pass; the unit diff changes neither (only the counter and the report row). WHEN mintmory index-tree --help is shown THEN the --text-content help says that online-only files are skipped by the inline text pass, and the index_tree docstring says the same.. Counter and row present, but --text-content help text and index_tree docstring not updated in the diff.

## Impact
The code and the tests of `add-recurrent-tree-indexing`.
