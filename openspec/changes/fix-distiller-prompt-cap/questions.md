# Questions — fix-distiller-prompt-cap

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
| Q-001 | open | none | verdict | Finding F-b381f707: task 1.2 is ticked as already satisfied, but its text is not done |
<!-- l4:index:end -->

---

## Q-001: Finding F-b381f707: task 1.2 is ticked as already satisfied, but its text is not done

- **Status:** open
- **Blocking tasks:** none
- **Kind:** verdict
- **Asked:** round 1, verifier

### Context
The judge raised a major finding in round 1, and no deterministic check confirms it.

Title: task 1.2 is ticked as already satisfied, but its text is not done
Detail: Diff does not modify the 12000 + 4000 assertion in test_prompt_bounded_when_user_turns_alone_exceed_budget; only a new test was added.

Answer `accept` to waive the finding, or `reject` and say why: a rejected finding is fixed by a fix unit.

### Options
1. accept
2. reject: <reason>

### Answer
<!-- write below this line -->
