# Capability: agent-history (delta)

## MODIFIED Requirements

### Requirement: Bounded LLM distiller prompt

The LLM distiller SHALL bound the transcript it sends to the model so an oversized
segment cannot produce an unbounded prompt. Each turn's text SHALL be truncated to
`SegmentSettings.max_turn_chars`, and the assembled transcript SHALL be elided to
`SegmentSettings.max_prompt_chars` by head+tail elision. Boundedness is the hard
guarantee: `_elide_transcript(redacted_lines, max_prompt_chars)` in
`mintmory.core.history.distill` SHALL return at most `max_prompt_chars` characters
for every input, counting every `… [N turns elided] …` marker line and every newline,
on every path (for `max_prompt_chars >= 100`; a smaller cap is not a supported
configuration, the result is then still cut to the cap). Its input is a list of
`(role, text)` tuples; it renders each as `"[" + role.upper() + "] " + text` (for
example `[USER] hi`, `[ASSISTANT] ok`, `[TOOL] out`), joins the lines with `"\n"`, and
inserts one marker line per gap of dropped turns. Text that fits SHALL be returned
unchanged. Elision SHALL drop assistant and tool turns first and SHALL NOT drop any
`user`-role turn **unless the user turns alone, markers included, exceed
`max_prompt_chars`**, in which case it SHALL keep the first turn, the last turn, and
as many remaining user turns as fit (taken in index order). The first and last turns
SHALL always appear, shortened (cut at the end, with a single marker line between them
when other turns were dropped) only when they alone do not fit. Redaction SHALL be
applied BEFORE truncation, so no secret is exposed by truncating.

#### Scenario: A huge segment yields a bounded, ask-preserving prompt
- **GIVEN** a segment containing a 200k-character turn and several long turns
- **WHEN** `distill_llm` builds the prompt
- **THEN** the prompt's transcript length is at most `max_prompt_chars`, markers included, every `user` turn's (truncated) text is present, the first ask and last turn are present, and no secret appears.

#### Scenario: User turns alone exceed the cap (the review fixture)
- **GIVEN** 80 turns: 40 pairs of a user turn `"u" * 400` followed by an assistant turn `"a" * 2000`, and `max_prompt_chars=12000` (today: 12,309 chars, 24 markers)
- **WHEN** `_elide_transcript` runs
- **THEN** the result has exactly 11,880 characters: 23 lines `"[USER] " + "u" * 400` (the turns at indices 0, 2, ..., 44), the last line `"[ASSISTANT] " + "a" * 2000`, 22 markers `… [1 turns elided] …` and one marker `… [34 turns elided] …` (47 lines in all); it starts with `"[USER] " + "u" * 400`.

#### Scenario: The drop path counts its markers
- **GIVEN** 60 turns: 30 pairs of a user turn `"u" * 300` and an assistant turn `"a" * 300`, and `max_prompt_chars=12000` (today: 12,205 chars, 22 markers)
- **WHEN** `_elide_transcript` runs
- **THEN** the result has exactly 11,913 characters: all 30 lines `"[USER] " + "u" * 300`, 7 assistant lines `"[ASSISTANT] " + "a" * 300` (the last turn and 6 others) and 23 markers `… [1 turns elided] …` (60 lines in all).

#### Scenario: Many single-turn gaps
- **GIVEN** 400 turns: 200 pairs of a user turn `"u" * 50` and a tool turn `"t" * 10`, and `max_prompt_chars=12000` (today: 15,733 chars, 178 markers)
- **WHEN** `_elide_transcript` runs
- **THEN** the result has exactly 11,947 characters: 151 lines `"[USER] " + "u" * 50` (the turns at indices 0, 2, ..., 300), 150 markers `… [1 turns elided] …`, one marker `… [98 turns elided] …`, and the last line `"[TOOL] " + "t" * 10` (303 lines in all); the first line is `"[USER] " + "u" * 50`.

#### Scenario: The first and last turns alone exceed the cap
- **GIVEN** `[("user", "u" * 2000), ("assistant", "a" * 2000)]` with `max_prompt_chars=500` (today: 4,020 chars), and separately `[("user", "u" * 2000)]` with `max_prompt_chars=500`
- **WHEN** `_elide_transcript` runs on each
- **THEN** the two-turn result has exactly 500 characters: `("[USER] " + "u" * 2000)[:249]`, a newline, then `("[ASSISTANT] " + "a" * 2000)[:250]`; the one-turn result is `("[USER] " + "u" * 2000)[:500]`.

#### Scenario: Turns between an oversized first and last turn become one marker
- **GIVEN** `[("user", "u" * 2000), ("assistant", "a" * 500), ("user", "u" * 500), ("assistant", "a" * 2000)]` with `max_prompt_chars=500`
- **WHEN** `_elide_transcript` runs
- **THEN** the result has exactly 500 characters in three lines: the first 239 characters of `"[USER] " + "u" * 2000`, the line `… [2 turns elided] …` (20 characters), and the first 239 characters of `"[ASSISTANT] " + "a" * 2000`.

#### Scenario: Text within the cap is unchanged
- **GIVEN** `[("user", "hi"), ("assistant", "ok")]` with `max_prompt_chars=12000`
- **WHEN** `_elide_transcript` runs
- **THEN** it returns exactly `"[USER] hi\n[ASSISTANT] ok"`.

#### Scenario: The whole prompt is bounded by the cap plus the template
- **GIVEN** the existing test `test_prompt_bounded_when_user_turns_alone_exceed_budget` (60 user turns of 5,000 chars, `max_turn_chars=2000`, `max_prompt_chars=12000`, empty `prev_context`, which `distill_llm` passes through `redact` unchanged as `""`)
- **WHEN** `distill_llm` builds the prompt
- **THEN** `len(prompt) <= 12000 + len(HISTORY_SEGMENT_PROMPT.format(prev_context="", transcript="", repo="myproject"))` (`HISTORY_SEGMENT_PROMPT` from `mintmory.core.prompts`; `repo` is `summary.repo`, `"myproject"` for `_make_summary()`), replacing the old `<= 12000 + 4000` tolerance, and `ASK-0 `, `ASK-59 ` and `elided` still appear.
