# Capability: agent-history (delta)

## ADDED Requirements

### Requirement: Distiller transcript elision stays within the cap, markers included
`_elide_transcript(redacted_lines, max_prompt_chars)` in
`mintmory.core.history.distill` SHALL return at most `max_prompt_chars` characters
for every input, counting each `… [N turns elided] …` marker line and every newline,
on every path. Text that fits SHALL be returned unchanged; assistant/tool turns SHALL
be dropped before user turns; the first and last turns SHALL appear, shortened only
when they alone do not fit.

#### Scenario: User turns alone exceed the cap (the review fixture)
- **GIVEN** 80 turns: 40 pairs of a user turn `"u" * 400` followed by an assistant turn `"a" * 2000`, and `max_prompt_chars=12000` (today: 12,309 chars, 24 markers)
- **WHEN** `_elide_transcript` runs
- **THEN** the result has at most 12,000 characters, its first line is `"[USER] " + "u" * 400`, its last line is `"[ASSISTANT] " + "a" * 2000`, and it contains `turns elided`.

#### Scenario: The drop path counts its markers
- **GIVEN** 60 turns: 30 pairs of a user turn `"u" * 300` and an assistant turn `"a" * 300`, and `max_prompt_chars=12000` (today: 12,205 chars)
- **WHEN** `_elide_transcript` runs
- **THEN** the result has at most 12,000 characters and contains all 30 lines `"[USER] " + "u" * 300` (the user turns fit once the assistant turns are dropped, markers included).

#### Scenario: Many single-turn gaps
- **GIVEN** 400 turns: 200 pairs of a user turn `"u" * 50` and a tool turn `"t" * 10`, and `max_prompt_chars=12000` (today: 15,733 chars, 178 markers)
- **WHEN** `_elide_transcript` runs
- **THEN** the result has at most 12,000 characters, its first line is `"[USER] " + "u" * 50` and its last line is `"[TOOL] " + "t" * 10`.

#### Scenario: The first and last turns alone exceed the cap
- **GIVEN** `[("user", "u" * 2000), ("assistant", "a" * 2000)]` with `max_prompt_chars=500` (today: 4,020 chars), and separately `[("user", "u" * 2000)]` with `max_prompt_chars=500`
- **WHEN** `_elide_transcript` runs on each
- **THEN** each result has at most 500 characters and starts with `[USER] u`; the two-turn result also contains `[ASSISTANT] a`.

#### Scenario: Text within the cap is unchanged
- **GIVEN** `[("user", "hi"), ("assistant", "ok")]` with `max_prompt_chars=12000`
- **WHEN** `_elide_transcript` runs
- **THEN** it returns exactly `"[USER] hi\n[ASSISTANT] ok"`.

#### Scenario: The whole prompt is bounded by the cap plus the template
- **GIVEN** the existing test `test_prompt_bounded_when_user_turns_alone_exceed_budget` (60 user turns of 5,000 chars, `max_turn_chars=2000`, `max_prompt_chars=12000`, empty `prev_context`)
- **WHEN** `distill_llm` builds the prompt
- **THEN** `len(prompt) <= 12000 + len(HISTORY_SEGMENT_PROMPT.format(prev_context="", transcript="", repo=s.repo))` (`HISTORY_SEGMENT_PROMPT` from `mintmory.core.prompts`), replacing the old `<= 12000 + 4000` tolerance, and `ASK-0 `, `ASK-59 ` and `elided` still appear.
