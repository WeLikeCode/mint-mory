# Change: The distiller transcript never exceeds its cap

## Why

bound-llm-distiller (MM-30) made boundedness the hard guarantee of
`_elide_transcript` (`packages/core/src/mintmory/core/history/distill.py:194`): the
transcript sent to the LLM is at most `max_prompt_chars`. It is not: every budget
check measures the kept lines WITHOUT the `… [N turns elided] …` marker lines that
`_insert_elision_markers` (:281) adds afterwards, one per gap, and nothing shortens
the first and last turns when they alone exceed the cap. The existing test is too
loose to notice (see Evidence).

## What changes

- Every budget check in `_elide_transcript` measures the rendered text, markers and
  newlines included.
- The last-resort path adds middle user turns one at a time (in index order) and
  keeps each only if the rendered result still fits.
- A final guard shortens the first and last turn lines when they alone do not fit.
- The loose test is tightened to the exact cap; new direct tests cover the four
  overshoot inputs.

The priorities are unchanged: text within the cap is returned as is; assistant/tool
turns go before user turns; the first and last turns always appear; redaction still
happens before truncation. The marker text is unchanged.

## Evidence

Where the cap is exceeded:

- the drop path (assistant/tool turns removed middle-out) stops as soon as the
  marker-free text fits, then adds the markers;
- the "protected lines fit" path does the same;
- the last-resort path (user turns alone exceed the cap) reserves room for ONE marker
  (`marker_budget = 30`, :265) but inserts one per gap;
- when the first and last turns alone exceed the cap, nothing shortens them.

Measured on `staging` (a08aee3) with `max_prompt_chars=12000` unless noted:

| input | output chars | markers |
|---|---|---|
| 40 × (user 400 chars + assistant 2,000 chars) | 12,309 | 24 |
| 30 × (user 300 + assistant 300) | 12,205 | 22 |
| 200 × (user 50 + tool 10) | 15,733 | 178 |
| user 2,000 + assistant 2,000, cap 500 | 4,020 | 0 |

(40 user turns of 400 chars with no assistant turns fit: 11,853 chars, 1 marker.)
The existing test only checks `len(prompt) <= 12000 + 4000`
(`packages/core/tests/test_history_distill_phase2.py:659`), so none of this is caught.

## Impact

- Affected specs: **agent-history** (ADDED).
- Code: `packages/core/src/mintmory/core/history/distill.py` (`_elide_transcript`
  only). Tests: `packages/core/tests/test_history_distill_phase2.py`.
- No config, schema or prompt change.
