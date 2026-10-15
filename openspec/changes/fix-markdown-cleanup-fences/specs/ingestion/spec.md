# Capability: ingestion (delta)

## ADDED Requirements

### Requirement: Fenced code blocks survive markdown cleanup byte-identical
`clean_markdown` SHALL copy every fenced code block (opening ``` or ~~~ fence through
its closing fence, both fence lines included) unchanged, after the document-wide
`\r\n`/`\r` → `\n` normalisation: no HTML-comment removal, trailing-whitespace strip
or blank-line collapse inside it. Outside fences the cleanup SHALL be exactly as
today, and the function SHALL stay idempotent.

#### Scenario: Fenced content is kept, the prose around it is cleaned
- **GIVEN** the input `"Intro <!-- drop -->text\n\n\n\nmore\n\n```html\n<!-- keep me -->\nline   \n\n\n\nend\n```\n\n~~~\na\n\n\n\nb  \n~~~\n"`
- **WHEN** `clean_markdown` runs
- **THEN** it returns `"Intro text\n\nmore\n\n```html\n<!-- keep me -->\nline   \n\n\n\nend\n```\n\n~~~\na\n\n\n\nb  \n~~~"` (today it returns `"Intro text\n\nmore\n\n```html\n\nline\n\nend\n```\n\n~~~\na\n\nb\n~~~"`).

#### Scenario: Line endings are still normalised inside a fence
- **WHEN** `clean_markdown("```\r\nx  \r\n```")` runs
- **THEN** it returns `"```\nx  \n```"` (CRLF becomes LF; the trailing spaces stay).

#### Scenario: Fence grammar
- **GIVEN** a fence opens on a line of at most 3 leading spaces followed by 3 or more backticks or 3 or more tildes (a backtick fence's info string has no backtick), and closes on a later line of at most 3 leading spaces, the same character repeated at least as many times as the opening run, and only spaces/tabs after it
- **WHEN** `clean_markdown` runs on each input below
- **THEN** `"~~~\n```\n<!-- k -->\n~~~\n<!-- gone -->"` → `"~~~\n```\n<!-- k -->\n~~~"` (a backtick line does not close a tilde fence); `"````\n```\n<!-- k -->\n````\n<!-- gone -->"` → `"````\n```\n<!-- k -->\n````"` (a shorter run does not close); `"   ```\n<!-- k -->\n   ```"` is returned unchanged (3-space indent opens); `"    ```\n<!-- x -->"` → `"    ```"` (4-space indent is not a fence).

#### Scenario: An unterminated fence runs to the end of the text
- **WHEN** `clean_markdown("a\n```\n<!-- c -->\n\n\n\nb")` runs
- **THEN** it returns the input unchanged.

#### Scenario: A comment is removed only within one run of non-fenced lines
- **WHEN** `clean_markdown("a <!-- open\n```\nx\n```\nclose --> b")` runs
- **THEN** it returns the input unchanged (the comment's start and end are separated by a fence).

#### Scenario: Blank runs before a fence still collapse
- **WHEN** `clean_markdown("text\n\n\n\n```\ny\n```")` runs
- **THEN** it returns `"text\n\n```\ny\n```"`.

#### Scenario: Idempotent with fences, unchanged without
- **WHEN** `clean_markdown` is applied twice to each input of the scenarios above
- **THEN** the second application returns its input unchanged; and every existing test in `packages/core/tests/test_conversion.py` (no fences) passes unedited.
