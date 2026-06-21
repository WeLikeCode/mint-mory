# Tasks — bound-llm-distiller (MM-30)

## 1. Config
- [x] 1.1 `SegmentSettings`: `max_turn_chars=2000`, `max_prompt_chars=12000`,
  `distill_max_tokens=512`. `LLMSettings`: `max_tokens=0`.

## 2. Generation bound
- [x] 2.1 `post_chat_completion`/`LLMClient.chat`: optional `max_tokens` (send only
  when >0; chat() falls back to settings.max_tokens). `build_history_distiller`
  closure passes `seg.distill_max_tokens`.

## 3. Prompt cap (core fix)
- [x] 3.1 `distill_llm`: per-turn truncate to `max_turn_chars`; total head+tail
  elision to `max_prompt_chars` that NEVER drops a user turn; first ask + last turn
  always survive; redact-before-truncate; cap prev_context.

## 4. Commit-as-completed
- [x] 4.1 backfill + sync: commit each session as its future completes (serial
  commits on main thread only); pass prompt caps through `distill_session`.

## 5. Tests + gates
- [x] 5.1 prompt-cap (huge segment -> bounded prompt, user turns kept, no leak,
  ask/outcome survive); max_tokens payload; incremental commit (failure mid-run
  keeps earlier sessions); concurrency no-data-loss still green; config bounds.
  `ruff && format && mypy && pytest` (cov ≥ 80).
