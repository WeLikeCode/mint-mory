# Change: Bound the LLM segment distiller (MM-30)

## Why

The Phase-2 LLM distiller (MM-29) hangs on real data. Measured on the live index:
segment transcripts are huge — median 15k chars, p90 45k, **max 163k chars** (138
segments > 50k). A backfill with `gemma4:e4b` via local Ollama got **stuck on its
first segment for 3.5 hours** with zero progress. Root causes:

1. **No prompt-size cap.** `distill_llm` only elides oversized `tool_result`
   turns (to 400 chars); the *total* transcript and long user/assistant turns are
   uncapped, so a single big segment produces a 100k+ char prompt.
2. **No generation bound.** The chat call sets no `max_tokens`, so the model can
   generate indefinitely; combined with urllib's per-read (not total) timeout, a
   slow token trickle never trips `MINTMORY_LLM_TIMEOUT_S` → effective hang.
3. **No incremental persistence.** Backfill uses collect-then-write (distill ALL,
   then commit), so a 3.5h hang produced nothing and risked losing everything.

## What changes

- **Prompt cap in `distill_llm`:** truncate each turn to `max_turn_chars` and the
  whole transcript to `max_prompt_chars` via head+tail elision, **always keeping
  every user turn's (truncated) text** so the ask is never dropped. New
  `SegmentSettings` knobs.
- **Generation bound:** add `max_tokens` to `LLMSettings` and the
  `post_chat_completion`/`LLMClient.chat` path; the history distiller defaults it
  (e.g. 512) so completions are bounded — the real runaway guard.
- **Commit-as-completed:** backfill/sync commit each session as its distill future
  completes (serial commits on the main thread, interleaved with the parallel
  distill) — incremental persistence + live progress, without reintroducing the
  shared-connection bug (MM-29 blocker).

Default behaviour is unchanged for `provider=none` (deterministic, offline). The
bounds only shape what the LLM path sends/returns; the existing redaction,
local-only gate, idempotency, and ordering invariants are untouched.

## Impact

- Affected specs: **agent-history**.
- Affected code: `core/config.py` (`SegmentSettings` + `LLMSettings.max_tokens`),
  `core/llm.py` (`post_chat_completion`/`LLMClient.chat` max_tokens;
  `build_history_distiller` default), `core/history/distill.py` (`distill_llm`
  prompt cap), `core/history/ingest.py` (commit-as-completed).
- New/updated tests; all gates green. No schema change.
