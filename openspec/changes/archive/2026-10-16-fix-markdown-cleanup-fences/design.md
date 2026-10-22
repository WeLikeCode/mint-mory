# Design — fix-markdown-cleanup-fences

Code: `clean_markdown` in `packages/core/src/mintmory/core/conversion.py`, split into
`_fenced_line_mask`, `_clean_pass` and the `clean_markdown` loop (tasks.md 2.1, 2.2).

## Decisions

### D1 Fences are identified per pass; idempotence wins in one case
The spec had two statements that disagreed: "every fenced block is copied unchanged"
and "repeat until the text stops changing". Input `"<!-- c -->```\n```\n<!-- k -->  \n```"`
shows it: pass 1 keeps lines 2 to 4 as a fence and removes the comment on line 1,
leaving a "```" on line 1; pass 2 then pairs lines 1 and 2 as a fence, so the old
block's `<!-- k -->  ` becomes prose and is cleaned. Decision: `_clean_pass` identifies
fences on its own input and copies them unchanged; `clean_markdown` repeats it
until a fixed point, so the output satisfies `clean_markdown(out) == out`.
Idempotence (a requirement of add-markitdown-ingestion) takes precedence over
byte-identity, and the only exception is a comment removal that creates a fence
marker line not present in the input. The requirement text, the scenario "A second
pass changes the first pass's output" and tasks.md 2.2 state this the same way.
Rejected: identify fences once on the original input and never again. A fixed
point would then not hold (the output re-read would show a new fence), breaking
idempotence.

### D2 Why a loop and not one pass
A single `_clean_pass` on the input of that scenario returns
`"```\n```\n<!-- k -->  \n```"`, which `clean_markdown` would clean further on a
second call. Only the loop returns `"```\n```\n\n```"`; test
`test_clean_markdown_needs_second_pass` fails without it.

### D3 Unterminated fence
An opener with no closer runs to the last line and its trailing blank lines are kept;
the strip of leading and trailing blank lines applies only to unmarked lines.
