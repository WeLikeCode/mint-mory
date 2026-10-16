# Tasks — fix-markdown-cleanup-fences

Paths: `conversion.py` = `packages/core/src/mintmory/core/conversion.py`, tests in
`packages/core/tests/test_conversion.py`. Line numbers are as of `staging` a08aee3.

## 1. Failing tests first
- [x] 1.1 In `test_conversion.py`, after `test_clean_markdown_is_idempotent` (:97-107),
  add one test per scenario of `specs/ingestion/spec.md` (10 scenarios, 10 tests, listed
  below by scenario name), with the exact inputs and expected strings written there
  (Python string literals; the ``` fences are plain characters inside the strings):
  - Scenario "Fenced content is kept, the prose around it is cleaned" ->
    `test_clean_markdown_keeps_fenced_blocks_byte_identical` (fails today)
  - Scenario "Line endings are still normalised inside a fence" ->
    `test_clean_markdown_normalises_crlf_inside_fence` (fails today: the trailing
    spaces are stripped)
  - Scenario "Fence grammar" -> `test_clean_markdown_fence_grammar` (one assert per
    input; fails today on the first, second and third inputs)
  - Scenario "An unterminated fence runs to the end of the text" ->
    `test_clean_markdown_unterminated_fence_runs_to_end` (fails today)
  - Scenario "A comment is removed only within one run of non-fenced lines" ->
    `test_clean_markdown_comment_split_by_fence_is_kept` (fails today: the regex
    removes from `<!--` to `-->` across the fence)
  - Scenario "An unterminated fence keeps its trailing blank lines" ->
    `test_clean_markdown_unterminated_fence_keeps_trailing_blank_lines` (input
    `"a\n```\nx\n\n\n"`, asserts it is returned unchanged; fails today)
  - Scenario "Blank runs before a fence still collapse" ->
    `test_clean_markdown_collapses_blank_run_before_fence` (passes today, guard)
  - Scenario "A removed comment that exposes an opener needs only one pass" ->
    `test_clean_markdown_comment_exposes_opener` (asserts the output
    `"```\n\ny"` for the input of the scenario)
  - Scenario "A second pass changes the first pass's output" ->
    `test_clean_markdown_needs_second_pass` (asserts the output
    `"```\n```\n\n```"` for `"<!-- c -->```\n```\n<!-- k -->  \n```"`; this test
    fails if `clean_markdown` runs a single `_clean_pass`, which returns
    `"```\n```\n<!-- k -->  \n```"`)
  - Scenario "Idempotent with fences, unchanged without" ->
    `test_clean_markdown_is_idempotent_with_fences` (loop over the inputs of all the
    scenarios above, the CRLF one included; assert
    `clean_markdown(clean_markdown(s)) == clean_markdown(s)`); the "unchanged
    without fences" half is the existing tests, run unedited in 3.1.
  Run `.venv/bin/pytest -q --no-cov packages/core/tests/test_conversion.py -k clean_markdown`.

## 2. Fix
- [x] 2.1 In `conversion.py` add a module-level regex
  `_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")` and a private helper
  `_fenced_line_mask(lines: list[str]) -> list[bool]` that marks, for each line,
  whether it is part of a fenced block: a line matching `_FENCE_OPEN_RE` opens a
  block unless the run is backticks and group 2 contains a backtick; the block
  closes at the first later line matching
  `^ {0,3}` + the same character repeated at least `len(run)` times + `[ \t]*$`
  (build it with `re.escape`); the opening line, the closing line and every line
  between are marked; an unclosed block runs to the last line. Scanning continues
  after the closing line.
- [x] 2.2 Rewrite `clean_markdown(text: str) -> str` (:102-114):
  1. `text = text.replace("\r\n", "\n").replace("\r", "\n")`;
  2. `lines = text.split("\n")`; `mask = _fenced_line_mask(lines)`;
  3. walk the lines: a marked line is appended to the output unchanged; each
     maximal run of unmarked lines is joined with `"\n"`, passed through
     `_HTML_COMMENT_RE.sub("", ...)`, split again, each line `rstrip()`ed, and
     consecutive empty lines in that run reduced to one before being appended;
  4. strip leading and trailing empty lines of `output` only while they are unmarked (outside a fence; a fenced
     line is never removed), then `return "\n".join(output)`.
  Put steps 2 to 4 in a helper `_clean_pass(text: str) -> str`; `clean_markdown`
  normalises line endings (step 1), then calls `_clean_pass` until the result stops
  changing (`while (new := _clean_pass(text)) != text: text = new`, then return it).
  Every pass that changes the text only removes characters, so the text gets shorter and the loop ends. Fences are identified from scratch on
  each pass's input (design.md, Decisions D1): this keeps the function idempotent when
  removing a comment exposes a fence line, at the price of the one exception in the
  requirement; the scenarios "A removed comment that exposes an opener needs only one
  pass" and "A second pass changes the first pass's output" pin both behaviours.
  Keep `_BLANK_RUN_RE` only if still used (ruff F841/F401 otherwise; it is a module
  constant, so remove it if unused). Update the docstring and the module docstring
  sentence (:10-12) to say fenced code blocks are copied unchanged.
- [ ] 2.3 Do not change `extract_markdown`, the suffix tables or the call sites.

## 3. Gates
- [ ] 3.1 The existing `test_conversion.py` tests and the ingest/index-tree CLI tests
  in `packages/cli/tests/test_cli.py` pass unedited.
- [ ] 3.2 `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`,
  `.venv/bin/mypy packages`, `.venv/bin/pytest -q` (coverage gate), and
  `npx --yes @fission-ai/openspec@1.14.1 validate fix-markdown-cleanup-fences --strict`.
