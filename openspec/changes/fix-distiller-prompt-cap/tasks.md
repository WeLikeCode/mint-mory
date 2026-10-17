# Tasks — fix-distiller-prompt-cap

Paths: `distill.py` = `packages/core/src/mintmory/core/history/distill.py`, tests in
`packages/core/tests/test_history_distill_phase2.py`. Line numbers are as of
`staging` a08aee3. `mypy packages` (strict) also checks the tests.

## 1. Failing tests first
- [x] 1.1 In the test module, import `_elide_transcript` (add it to the existing
  `from mintmory.core.history.distill import (...)` block) and
  `from mintmory.core.prompts import HISTORY_SEGMENT_PROMPT`. `_elide_transcript(redacted_lines: list[tuple[str, str]], max_prompt_chars: int) -> str` renders each tuple as `f"[{role.upper()}] {text}"` itself. Add one test per
  scenario of `specs/agent-history/spec.md`, calling `_elide_transcript` directly
  with lists of `(role, text)` tuples built exactly as the scenarios say:
  Assert the exact numbers of the scenarios (`len(result)`, the counts of `[USER]`
  lines and of `turns elided` lines; section 4 shows how they are derived):
  - `test_elide_user_turns_alone_over_cap_stays_within_cap` (11,880; fails today: 12,309)
  - `test_elide_drop_path_counts_markers` (11,913; fails today: 12,205)
  - `test_elide_many_gaps_stays_within_cap` (11,947; fails today: 15,733)
  - `test_elide_first_and_last_over_cap_are_shortened` (500 and 500; fails today: 4,020 and 2,007)
  - `test_elide_first_and_last_over_cap_with_middle_turns` (the four-turn scenario: exercises the `n > 2` marker
    branch of 2.5)
  - `test_elide_within_cap_is_unchanged` (passes today, guard)
  Run `.venv/bin/pytest -q --no-cov packages/core/tests/test_history_distill_phase2.py -k elide`;
  the first five must fail today (the four-turn one too: its output is far over 500); the within-cap guard passes.
- [x] 1.2 Tighten `test_prompt_bounded_when_user_turns_alone_exceed_budget` (:645-664):
  replace `assert len(prompt) <= 12000 + 4000, ...` (:659) with
  `overhead = len(HISTORY_SEGMENT_PROMPT.format(prev_context="", transcript="", repo=s.repo))`
  (`s = _make_summary()` is already defined in that test, `s.repo == "myproject"`; the
  empty `prev_context` reaches the template as `""`: `distill_llm` only redacts and caps it)
  and `assert len(prompt) <= 12000 + overhead, f"prompt not bounded: {len(prompt)}"`.
  Keep its other assertions.

## 2. Fix `_elide_transcript` (`distill.py:194-278`)
- [x] 2.1 Add a private helper `_render(lines: list[str], kept_sorted: list[int]) -> str`
  that returns `_insert_elision_markers(lines, kept_sorted, 0)` (the marker text
  `… [N turns elided] …` does not change; the third argument `dropped_count` is not
  used by that function's body, so `0` is correct). Every budget check below compares
  `len(_render(...))` with `max_prompt_chars`, never the marker-free join.
- [x] 2.2 Keep the early return when `"\n".join(lines)` fits. Drop path: iterate
  the droppable (non-protected) indices middle-first exactly as today; after
  removing each one, return
  `_render(lines, sorted(kept))` as soon as its length fits. (`protected` = indices 0,
  `n - 1` and every `role == "user"` turn, as today; the droppable ones are assistant
  and tool turns. A render per candidate is O(n) so the path is O(n^2); with the
  fixtures here, at most 400 turns, that is fine.)
- [x] 2.3 When all droppable turns are gone, return `_render(lines, sorted(protected))`
  if it fits.
- [x] 2.4 Last-resort path: start from `kept = sorted({0, n - 1})`; for each middle
  user index in ascending order (`sorted(...)`, not set order), keep it only if
  `len(_render(lines, sorted(set(kept) | {idx}))) <= max_prompt_chars`. Remove
  `marker_budget` and the `remaining` arithmetic. Return the render if it fits.
- [x] 2.5 Final guard (first and last turn alone do not fit): if `n == 1` return
  `lines[0][:max_prompt_chars]`; otherwise build `marker = [f"… [{n - 2} turns elided] …"]` (an f-string: the
  marker shows the real count)
  when `n > 2` (else `[]`), let
  `avail = max_prompt_chars - sum(len(m) for m in marker) - (len(marker) + 1)`,
  `h = min(len(lines[0]), max(avail // 2, avail - len(lines[n - 1])))`,
  `t = min(len(lines[n - 1]), avail - h)`, and return
  `"\n".join([lines[0][:h], *marker, lines[n - 1][:t]])[:max_prompt_chars]`
  (the trailing slice is the last safety net). Caps below 100 are not supported (the
  spec states it); the slice still keeps the length bound. Update the docstring: the bound
  counts markers and newlines, and the first/last lines may be shortened when they
  alone exceed the cap.
- [x] 2.6 Do not change `distill_llm`, the per-turn `max_turn_chars` truncation, the
  redaction order, or `SegmentSettings`.

## 3. Gates
- [x] 3.1 The existing tests in `test_history_distill_phase2.py`,
  `test_llm_distiller.py` and `test_history_ingest.py` pass unedited (except 1.2).
- [ ] 3.2 `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`,
  `.venv/bin/mypy packages`, `.venv/bin/pytest -q` (coverage gate). These are the real gates of `.l4/config.yaml` (uv sync, ruff, mypy,
  pytest); OpenSpec validation is not a task gate (design.md `## Decisions`).

## 4. Arithmetic behind the scenarios (checked against `distill.py` on staging a08aee3)
A rendered line is `"[USER] "` (7) + text, `"[ASSISTANT] "` (12) + text, `"[TOOL] "` (7)
+ text. A marker `… [N turns elided] …` is 20 characters for N of 1 digit, 21 for 2
digits, 22 for 3. A render of L lines has L - 1 newlines. Drop path: removing one line
that sits between two kept lines removes `len(line) + 1` and adds a marker `+ 1`.
The "today" numbers are what the unfixed function returns (measured by running it).

- **Review fixture** (40 pairs, user 407, assistant 2,012): full text is
  `40 * (407 + 2012) + 79` = 96,839 > 12,000. All 39 droppable assistant turns gone,
  the render is `40 * 407` = 16,280 + markers > 12,000, so the last-resort path runs.
  Kept users are added in index order while the render fits. With `u` users at indices
  0, 2, ..., 2(u-1) plus the last turn (index 79): lines `2u + 1`, markers `u - 1` of
  20 plus one gap marker over the turns between the last kept user and the last turn; for u = 23 the gap is turns 45..78 =
  34, 21 characters. Length `23 * 407 + 22 * 20 + 21 + 2012 + 46` = 9,361 + 440 + 21 +
  2,012 + 46 = **11,880** <= 12,000. For u = 24: `9,768 + 460 + 21 + 2,012 + 48` =
  12,309 > 12,000, so the 24th user is refused.
- **Drop path** (30 pairs, user 307, assistant 312): full text is
  `30 * (307 + 312) + 59` = 18,629. Each dropped assistant (indices 29, 31, 27, 33, ...
  middle-first, never adjacent) changes the length by `-(312 + 1) + (20 + 1)` = -292.
  After k drops: `18,629 - 292k`. k = 22 gives 12,205 > 12,000 (this is today's number: the
  old check ignored the markers, stopped at k = 22 and then added them); k = 23 gives
  18,629 - 6,716 = **11,913** <= 12,000. Result: 30 user lines, 29 - 23 = 6 assistant
  lines + the last turn = 7, 23 markers, 60 lines.
- **Many single-turn gaps** (200 pairs, user 57, tool 17): full text is
  `200 * 74 + 399` = 15,199. Dropping the 199 tool turns before the last one leaves
  200 users + 199 markers + the last tool line: `11,400 + 3,980 + 17 + 399` = 15,796 >
  12,000, so the last-resort path runs. With `u` users at 0, 2, ..., 2(u-1) and the
  last turn (index 399): `57u + 20(u - 1) + M + 17 + 2u` where M is the gap marker.
  u = 151: gap = turns 301..398 = 98, M = 21: `8,607 + 3,000 + 21 + 17 + 302` =
  **11,947**. u = 152 gives `8,664 + 3,020 + 21 + 17 + 304` = 12,026 > 12,000, and
  every later user (index 302, 304, ...) adds 57 + 20 + 2 = 79 to the 11,947 (or 78
  when the gap shrinks to 1 digit), so all are refused.
- **Two turns, cap 500**: `avail = 500 - 0 - 1` = 499; `h = min(2007, max(249, 499 - 2012))`
  = 249; `t = min(2012, 499 - 249)` = 250; length `249 + 1 + 250` = 500.
- **Four turns, cap 500**: marker `… [2 turns elided] …` = 20; `avail = 500 - 20 - 2` = 478;
  `h = min(2007, max(239, 478 - 2012))` = 239; `t = min(2012, 478 - 239)` = 239;
  length `239 + 1 + 20 + 1 + 239` = 500.
- **One turn**: `lines[0][:500]`, 500 characters.
