# Change: Markdown cleanup leaves fenced code blocks untouched

## Why

add-markitdown-ingestion requires `clean_markdown` to be conservative: it SHALL NOT
alter fenced code (requirement "Conservative formatting normalisation"; the module
docstring of `packages/core/src/mintmory/core/conversion.py` says the same).
`clean_markdown` (`conversion.py:102-114`) is not fence-aware: it removes HTML
comments (:108), strips trailing whitespace (:110) and collapses blank-line runs
(:112) across the whole text, fenced blocks included. Measured on `staging`
(a08aee3):

```
clean_markdown("```html\n<!-- keep me -->\nline   \n\n\n\nend\n```")
== "```html\n\nline\n\nend\n```"      # comment gone, trailing spaces gone, blank lines collapsed
```

That corrupts code samples in ingested documents (HTML/XML comments in code,
significant trailing whitespace, intentional blank lines). It runs on every
`ingest`/`index-tree` text read and every markitdown conversion
(`conversion.py:173,200,204`).

## What changes

`clean_markdown` splits the text (after line-ending normalisation) into fenced and
non-fenced lines. Fenced lines — from an opening ``` or ~~~ fence through its
closing fence, identified on the text each pass reads — are copied byte-identical
within that pass. Comment removal, trailing-whitespace
stripping and blank-run collapsing apply only to the runs of lines outside fences,
exactly as today. Leading and trailing blank lines of the whole result are still
removed. The function stays pure, total and idempotent: it repeats the pass (`_clean_pass`)
until the text stops changing, re-identifying fences each time. Idempotence wins over
byte-identity in one case only: a removed comment that exposes a new fence marker
(spec scenario "A second pass changes the first pass's output"; design.md D1).

Out of scope: indented (4-space) code blocks, inline code spans, HTML `<pre>` blocks.

## Impact

- Affected specs: **ingestion** (ADDED).
- Code: `packages/core/src/mintmory/core/conversion.py` (`clean_markdown` + a private
  fence helper). Tests: `packages/core/tests/test_conversion.py`.
- Text without fences is cleaned exactly as before (the existing tests pass unedited).
