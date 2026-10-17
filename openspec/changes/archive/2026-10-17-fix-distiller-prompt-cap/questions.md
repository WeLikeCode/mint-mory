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
| Q-001 | answered | none | verdict | Finding F-b381f707: task 1.2 is ticked as already satisfied, but its text is not done |
<!-- l4:index:end -->

---

## Q-001: Finding F-b381f707: task 1.2 is ticked as already satisfied, but its text is not done

- **Status:** answered
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
accept: the behaviour task 1.2 asks for holds and is tested. The new test test_prompt_bounded_by_cap_plus_template (C-5bd97470) runs the same input as test_prompt_bounded_when_user_turns_alone_exceed_budget (60 user turns of 5,000 characters, max_turn_chars=2000, max_prompt_chars=12000) and asserts len(prompt) <= 12000 + len(HISTORY_SEGMENT_PROMPT.format(prev_context='', transcript='', repo=s.repo)) with ASK-0, ASK-59 and elided still present. The old test keeps its looser 12000 + 4000 bound: weaker, not wrong, and the red step cannot tighten an existing test in place, so a fix unit would only add another copy. Checked on the unit branch head (53d3b2b).
