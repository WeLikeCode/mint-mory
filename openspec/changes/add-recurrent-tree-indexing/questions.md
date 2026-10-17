# Questions — add-recurrent-tree-indexing

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
| Q-001 | answered | none | verdict | Criterion C-b54f84ac (ingestion › Online-only-safe tree indexing › Placeholder files are indexed without download): accept as satisfied? |
| Q-002 | open | none | verdict | Criterion C-1ccce576 (ingestion › Metadata + folder-context records › An image is indexed by metadata and neighbours): accept as satisfied? |
| Q-003 | open | none | verdict | Criterion C-99b1ee27 (ingestion › Incremental, idempotent runs › Re-run skips unchanged and updates changed): accept as satisfied? |
| Q-004 | open | none | verdict | Criterion C-4a833fcd (ingestion › Bounded, opt-in content extraction › Content pass respects the budget): accept as satisfied? |
| Q-005 | open | none | verdict | Criterion C-1474f431 (ingestion › Scoping, exclusions, and collection tagging › Excluded files and folders are skipped): accept as satisfied? |
| Q-006 | open | none | verdict | Criterion C-475f20f9 (ingestion › Scoping, exclusions, and collection tagging › Without --exclude, artifacts are indexed as metadata): accept as satisfied? |
| Q-007 | open | none | verdict | Finding F-b34b9dc3: task 2.3 is ticked as already satisfied, but its text is not done |
<!-- l4:index:end -->

---

## Q-001: Criterion C-b54f84ac (ingestion › Online-only-safe tree indexing › Placeholder files are indexed without download): accept as satisfied?

- **Status:** answered
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-b54f84ac (ingestion › Online-only-safe tree indexing › Placeholder files are indexed without download)

### Context
Criterion C-b54f84ac (ingestion › Online-only-safe tree indexing › Placeholder files are indexed without download) is needs human after round 1.

Scenario:
\- **WHEN** `mintmory index-tree` runs with default options over a tree of online-only placeholders
\- **THEN** every file is recorded from its metadata (stat only), no file is opened, and no download is triggered.

Why: uncovered: no adequate discriminating test traces it
Judge: insufficient_evidence
Tracing tests: none
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
accept: satisfied as it stands. test_is_online_only_detects_placeholder (packages/core/tests/test_tree_index.py) proves placeholder detection; the default text pass no longer reads an online-only file (task 2.2 guard, proven by the new test_index_tree_text_content_skips_online_only_file: the extract_markdown spy never sees cloud.txt and its manifest row stays metadata); binary content is read only with --content (want_binary needs the content flag), so a default run records every placeholder from stat only.
---

## Q-002: Criterion C-1ccce576 (ingestion › Metadata + folder-context records › An image is indexed by metadata and neighbours): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-1ccce576 (ingestion › Metadata + folder-context records › An image is indexed by metadata and neighbours)

### Context
Criterion C-1ccce576 (ingestion › Metadata + folder-context records › An image is indexed by metadata and neighbours) is needs human after round 1.

Scenario:
\- **WHEN** a `.jpg` (or any non-text file) is indexed
\- **THEN** a memory is stored with its name, path, type, size, mtime, online-only
  status, and the names of other files in the same folder.

Why: uncovered: no adequate discriminating test traces it
Judge: insufficient_evidence
Tracing tests: none
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-003: Criterion C-99b1ee27 (ingestion › Incremental, idempotent runs › Re-run skips unchanged and updates changed): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-99b1ee27 (ingestion › Incremental, idempotent runs › Re-run skips unchanged and updates changed)

### Context
Criterion C-99b1ee27 (ingestion › Incremental, idempotent runs › Re-run skips unchanged and updates changed) is needs human after round 1.

Scenario:
\- **WHEN** `index-tree` runs twice and one file's size/mtime changed between runs
\- **THEN** unchanged files produce no new memories, the changed file's memories
  are replaced (not duplicated), and the manifest reflects the new state.

Why: uncovered: no adequate discriminating test traces it
Judge: insufficient_evidence
Tracing tests: none
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-004: Criterion C-4a833fcd (ingestion › Bounded, opt-in content extraction › Content pass respects the budget): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-4a833fcd (ingestion › Bounded, opt-in content extraction › Content pass respects the budget)

### Context
Criterion C-4a833fcd (ingestion › Bounded, opt-in content extraction › Content pass respects the budget) is needs human after round 1.

Scenario:
\- **WHEN** `--content` is set with `--max-download-mb`
\- **THEN** files are downloaded+converted until the budget is reached, after
  which remaining files fall back to metadata-only and the run reports the cutoff.

Why: uncovered: no adequate discriminating test traces it
Judge: insufficient_evidence
Tracing tests: none
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-005: Criterion C-1474f431 (ingestion › Scoping, exclusions, and collection tagging › Excluded files and folders are skipped): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-1474f431 (ingestion › Scoping, exclusions, and collection tagging › Excluded files and folders are skipped)

### Context
Criterion C-1474f431 (ingestion › Scoping, exclusions, and collection tagging › Excluded files and folders are skipped) is needs human after round 1.

Scenario:
\- **WHEN** a tree contains build artifacts (`.dll`/`.exe`/`.jar`) and a `Personal/` folder, and `index-tree` runs with `--exclude "*.dll,*.exe,*.jar,Personal/**"`
\- **THEN** those files produce no memories, and every produced memory carries the collection tag.

Why: uncovered: no adequate discriminating test traces it
Judge: insufficient_evidence
Tracing tests: none
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-006: Criterion C-475f20f9 (ingestion › Scoping, exclusions, and collection tagging › Without --exclude, artifacts are indexed as metadata): accept as satisfied?

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier
- **Criteria:** C-475f20f9 (ingestion › Scoping, exclusions, and collection tagging › Without --exclude, artifacts are indexed as metadata)

### Context
Criterion C-475f20f9 (ingestion › Scoping, exclusions, and collection tagging › Without --exclude, artifacts are indexed as metadata) is needs human after round 1.

Scenario:
\- **WHEN** the same tree is indexed without `--exclude`
\- **THEN** each artifact gets a metadata + folder-context record like any other non-text file (no default denylist is applied).

Why: uncovered: no adequate discriminating test traces it
Judge: insufficient_evidence
Tracing tests: none
Ignored tests: none

Answer `accept` if the criterion is satisfied as it stands, or `reject` and say why.
If the code is right and the scenarios are incomplete, `reject` with a scenario: WHEN ... THEN ...

### Options
1. accept
2. reject: <reason>, or WHEN ... THEN ... for a spec gap

### Answer
<!-- write below this line -->
---

## Q-007: Finding F-b34b9dc3: task 2.3 is ticked as already satisfied, but its text is not done

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier

### Context
The judge raised a major finding in round 1, and no deterministic check confirms it.

Title: task 2.3 is ticked as already satisfied, but its text is not done
Detail: Counter, placement after want_binary and conditional report row are in the diff (main.py), but the task also requires updating the --text-content help text and index_tree docstring, and the diff does not change them (implementer admits this).

Answer `accept` to waive the finding, or `reject` and say why: a rejected finding is fixed by a fix unit.

### Options
1. accept
2. reject: <reason>

### Answer
<!-- write below this line -->
