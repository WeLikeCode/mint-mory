# Questions — tenant-scoped-core

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
| Q-001 | open | 1 | ambiguous | R1.7 assumes LinkSettings() default min_shared_entities=1, but the code default is 2 |
<!-- l4:index:end -->

---

## Q-001: R1.7 assumes LinkSettings() default min_shared_entities=1, but the code default is 2

- **Status:** open
- **Blocking tasks:** 1
- **Kind:** ambiguous
- **Asked:** 2026-10-20T05:19Z by deepseek, run r-20261020T0514Z-8813, task 1

### Context
C-1db051ad / requirements.md R1.7 says Scenario A uses the *default* LinkSettings(), where 'a pair links when it shares >= 1 entity', and expects three relates_to links among a1/a2/a3, which share only the single entity 'acme'. The actual default is min_shared_entities=2 (config.py:108; the docstring in dreaming.py:274 is stale), adopted deliberately as the production-tuned 'E-L-MID' profile, so the scenario yields 0 links. Existing tests work around this with an explicit _permissive() (min_shared_entities=1). The tenancy work does not otherwise need any config change. How should the Scenario A test be written?

### Options
1. Write Scenario A with an explicit LinkSettings(min_shared_entities=1) and leave the production default at 2.
2. Change the LinkSettings.min_shared_entities default to 1 as part of this unit (undoes the production tuning).
3. Keep the default at 2 and adjust the Scenario A fixture/expected links (requires re-specifying R1.7).

### Answer
<!-- write below this line -->
