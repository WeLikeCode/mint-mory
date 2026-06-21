# Capability: agent-history (delta)

## ADDED Requirements

### Requirement: Bounded LLM distiller prompt

The LLM distiller SHALL bound the transcript it sends to the model so an oversized
segment cannot produce an unbounded prompt. Each turn's text SHALL be truncated to
`SegmentSettings.max_turn_chars`, and the assembled transcript SHALL be elided to
`SegmentSettings.max_prompt_chars` by head+tail elision. Boundedness is the hard
guarantee. Elision SHALL drop/shorten assistant and tool turns first and SHALL NOT
drop any `user`-role turn **unless the user turns alone exceed `max_prompt_chars`**,
in which case it SHALL keep the first user turn (the ask), the last turn (the
outcome), and as many remaining user turns as fit. The first ask and last turn
SHALL always survive. Redaction SHALL be applied BEFORE truncation, so no secret is
exposed by truncating.

#### Scenario: A huge segment yields a bounded, ask-preserving prompt
- **GIVEN** a segment containing a 200k-character turn and several long turns
- **WHEN** `distill_llm` builds the prompt
- **THEN** the prompt's transcript length is ≤ `max_prompt_chars` (plus a small elision marker), every `user` turn's (truncated) text is present, the first ask and last turn are present, and no secret appears.

### Requirement: Bounded LLM generation

The distiller's chat completion SHALL be length-bounded via `max_tokens` so a model
cannot generate indefinitely. `LLMSettings.max_tokens` (default 0 = unset) and an
optional `max_tokens` argument to the chat call SHALL cause `max_tokens` to be sent
in the `/chat/completions` payload only when greater than 0; the history distiller
SHALL bound generation using `SegmentSettings.distill_max_tokens`. Existing callers
that pass no `max_tokens` and leave `LLMSettings.max_tokens=0` SHALL behave exactly
as before (no field sent).

#### Scenario: Distiller caps completion length
- **WHEN** the history distiller calls the model
- **THEN** the request payload includes a `max_tokens` equal to `distill_max_tokens`
- **AND** a plain `chat()` with `LLMSettings.max_tokens=0` sends no `max_tokens` field.

### Requirement: Incremental, crash-safe ingest commits

Backfill and sync SHALL commit each session's distilled segments as that session's
distillation completes, so progress persists and is visible during a long run. All
database writes SHALL occur only on the main thread (distillation MAY run in worker
threads); a failure distilling one session SHALL be counted in `report.errors` and
SHALL NOT discard already-committed sessions.

#### Scenario: A mid-run failure does not lose earlier work
- **GIVEN** a backfill over several sessions where distilling session #3 raises
- **WHEN** the run completes
- **THEN** sessions #1 and #2 are persisted, `report.errors == 1`, and no partial/duplicate rows exist.
