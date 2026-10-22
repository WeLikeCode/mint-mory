# Design & FROZEN contract — `bound-llm-distiller` (MM-30)

Match names/signatures/defaults exactly. Additive; `provider=none` path and the
MM-27/28/29 invariants (redaction-before-LLM, local-only gate, segment idempotency,
timeline ordering) are UNCHANGED. This change only BOUNDS the LLM path's input
(prompt size) and output (max_tokens), and makes commits incremental.

---

## 1. `core/config.py`

Add to `SegmentSettings`:
```python
    max_turn_chars: int = Field(default=2000, ge=100, le=100_000)     # cap per-turn text in the prompt
    max_prompt_chars: int = Field(default=12000, ge=500, le=500_000)  # cap total transcript in the prompt
    distill_max_tokens: int = Field(default=2048, ge=16, le=8192)     # cap LLM completion length
    # NOTE (MM-31): default raised 512->2048. Reasoning models (gemma4:e4b) spend the
    # token budget on hidden reasoning before emitting JSON; 512 yielded empty content
    # and silent deterministic fallback. 2048 leaves headroom for reasoning + content.
```
Add to `LLMSettings`:
```python
    max_tokens: int = Field(default=0, ge=0, le=32000)  # 0 = unset (no cap sent)
```

---

## 2. `core/llm.py` — generation bound

`post_chat_completion(...)` and `LLMClient.chat`: when the effective `max_tokens`
> 0, include `"max_tokens": n` in the `/chat/completions` payload. Add an optional
`max_tokens: int = 0` parameter to `LLMClient.chat` (default 0 → fall back to
`self.settings.max_tokens`); 0 means do not send the field (preserves today's
behaviour for all existing callers).

`build_history_distiller(llm, seg)`: when building the `LLMClient`, ensure the
distiller's completions are bounded — pass `seg.distill_max_tokens` so each chat
call caps generation. The returned closure calls `client.chat(prompt,
max_tokens=seg.distill_max_tokens)`. (No global default change to `LLMSettings`.)

---

## 3. `core/history/distill.py` — prompt cap (the core fix)

`distill_llm(summary, seg_turns, chat, *, prev_context="", max_turn_chars=2000,
max_prompt_chars=12000)`:
- Build the redacted, role-tagged transcript as today, BUT:
  1. **Per-turn truncate:** each turn's redacted text is truncated to
     `max_turn_chars` (append " … [truncated]" when cut). This already-existing
     tool_result elision is generalized to ALL turns.
  2. **Total cap with user-priority:** if the assembled transcript exceeds
     `max_prompt_chars`, elide to fit by **head+tail** (keep the first and last
     turns) while **never dropping any `user`-role turn's text** — drop/most-shorten
     assistant/tool turns in the middle first; if still over, keep all user turns
     (each ≤ a fair share) + a head/tail of context, and insert a
     "… [N turns elided] …" marker. The first user turn (the ask) and the last
     turn (the outcome) MUST always survive.
- Redaction still happens BEFORE truncation/assembly (truncating redacted text is
  safe; never truncate then redact). `prev_context` is still redacted and is also
  subject to a small cap (≤ max_turn_chars).
- Everything else (extract_json, clamps, ValueError on garbage, distiller_version=2,
  next_context) is unchanged.

The caller (`distill_session` in ingest) passes the `SegmentSettings` caps through.

---

## 4. `core/history/ingest.py` — commit-as-completed

Replace the two-phase "collect ALL prepared, then commit ALL" with **commit each
session as its future completes**, keeping writes serial on the main thread:
```python
with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
    futures = {executor.submit(_prepare_session, s, *prep_args): s for s in sessions_to_process}
    for future in as_completed(futures):
        try:
            ps, source_path = future.result()
        except Exception as exc:
            report.errors += 1; log.warning(...); continue
        seg_result, written_ids = commit_distilled(store, ps)   # SERIAL, main thread
        _accumulate_seg_result(report, seg_result)
        by_source_count += 1
        if source_path:
            _manifest_update(store, source_path, source_name, memory_ids=written_ids)
```
Apply to BOTH backfill and sync. INVARIANT preserved: all `store` writes
(`commit_distilled`, `_manifest_update`) happen ONLY on the main thread (never in a
worker) — the MM-29 blocker (concurrent shared-conn writes) stays fixed; this just
interleaves the serial commits with the parallel distill so progress persists and
is visible. The serial (max_concurrency<=1) path commits inline as before.
`distill_session` must pass the prompt caps into `distill_llm`.

---

## 5. Tests (contract)
- `test_history_distill_phase2.py` (extend): a segment with one 200k-char turn and
  several long turns -> the prompt passed to a capturing fake `chat` is ≤
  `max_prompt_chars` (+ small marker overhead) AND every user turn's (truncated)
  text is present AND no secret leaks (redaction before truncation). The first user
  ask + last turn survive elision.
- `test_llm.py`/distiller: `LLMClient.chat(max_tokens=n)` includes `max_tokens` in
  the payload; `chat()` (no arg) does NOT when `LLMSettings.max_tokens=0`;
  `build_history_distiller`'s closure caps generation via `distill_max_tokens`.
- `test_history_ingest.py` (extend): backfill commits incrementally — after a run
  with a FAKE distiller that raises on session #3, sessions #1–2 are persisted
  (not lost) and `report.errors == 1`; concurrent run (max_concurrency=4) still has
  zero data loss (existing regression test stays green); writes only on main thread.
- config: new `SegmentSettings`/`LLMSettings` fields parse + bounds.

All gates: `ruff check . && ruff format --check . && mypy packages && pytest -q` (cov ≥ 80).
Tests use fake chat fns + temp DBs only — never a real LLM or the real store.
