# Tasks — fix-distiller-prompt-cap

Paths: `distill.py` = `packages/core/src/mintmory/core/history/distill.py`, tests in
`packages/core/tests/test_history_distill_phase2.py`. Line numbers are as of
`staging` a08aee3. `mypy packages` (strict) also checks the tests.

## 1. Failing tests first
- [ ] 1.1 In the test module, import `_elide_transcript` (add it to the existing
  `from mintmory.core.history.distill import (...)` block) and
  `from mintmory.core.prompts import HISTORY_SEGMENT_PROMPT`. Add one test per
  scenario of `specs/agent-history/spec.md`, calling `_elide_transcript` directly
  with lists of `(role, text)` tuples built exactly as the scenarios say:
  - `test_elide_user_turns_alone_over_cap_stays_within_cap` (fails today: 12,309)
  - `test_elide_drop_path_counts_markers` (fails today: 12,205)
  - `test_elide_many_gaps_stays_within_cap` (fails today: 15,733)
  - `test_elide_first_and_last_over_cap_are_shortened` (fails today: 4,020 and 2,007)
  - `test_elide_first_and_last_over_cap_with_middle_turns` (the four-turn scenario: exercises the `n > 2` marker
    branch of 2.5)
  - `test_elide_within_cap_is_unchanged` (passes today, guard)
  Run `.venv/bin/pytest -q --no-cov packages/core/tests/test_history_distill_phase2.py -k elide`;
  the first four must fail.
- [ ] 1.2 Tighten `test_prompt_bounded_when_user_turns_alone_exceed_budget` (:645-664):
  replace `assert len(prompt) <= 12000 + 4000, ...` (:659) with
  `overhead = len(HISTORY_SEGMENT_PROMPT.format(prev_context="", transcript="", repo=s.repo))`
  and `assert len(prompt) <= 12000 + overhead, f"prompt not bounded: {len(prompt)}"`.
  Keep its other assertions.

## 2. Fix `_elide_transcript` (`distill.py:194-278`)
- [ ] 2.1 Add a private helper `_render(lines: list[str], kept_sorted: list[int]) -> str`
  that returns `_insert_elision_markers(lines, kept_sorted, 0)` (the marker text
  `… [N turns elided] …` does not change). Every budget check below compares
  `len(_render(...))` with `max_prompt_chars`, never the marker-free join.
- [ ] 2.2 Keep the early return when `"\n".join(lines)` fits. Drop path: iterate
  the droppable (non-protected) indices middle-first exactly as today; after
  removing each one, return
  `_render(lines, sorted(kept))` as soon as its length fits.
- [ ] 2.3 When all droppable turns are gone, return `_render(lines, sorted(protected))`
  if it fits.
- [ ] 2.4 Last-resort path: start from `kept = sorted({0, n - 1})`; for each middle
  user index in ascending order (`sorted(...)`, not set order), keep it only if
  `len(_render(lines, sorted(set(kept) | {idx}))) <= max_prompt_chars`. Remove
  `marker_budget` and the `remaining` arithmetic. Return the render if it fits.
- [ ] 2.5 Final guard (first and last turn alone do not fit): if `n == 1` return
  `lines[0][:max_prompt_chars]`; otherwise build `marker = [f"… [{n - 2} turns elided] …"]` (an f-string: the
  marker shows the real count)
  when `n > 2` (else `[]`), let
  `avail = max_prompt_chars - sum(len(m) for m in marker) - (len(marker) + 1)`,
  `h = min(len(lines[0]), max(avail // 2, avail - len(lines[n - 1])))`,
  `t = min(len(lines[n - 1]), avail - h)`, and return
  `"\n".join([lines[0][:h], *marker, lines[n - 1][:t]])[:max_prompt_chars]`
  (the trailing slice is the last safety net). Update the docstring: the bound
  counts markers and newlines, and the first/last lines may be shortened when they
  alone exceed the cap.
- [ ] 2.6 Do not change `distill_llm`, the per-turn `max_turn_chars` truncation, the
  redaction order, or `SegmentSettings`.

## 3. Gates
- [ ] 3.1 The existing tests in `test_history_distill_phase2.py`,
  `test_llm_distiller.py` and `test_history_ingest.py` pass unedited (except 1.2).
- [ ] 3.2 `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`,
  `.venv/bin/mypy packages`, `.venv/bin/pytest -q` (coverage gate), and
  `npx --yes @fission-ai/openspec@1.14.1 validate fix-distiller-prompt-cap --strict`.
