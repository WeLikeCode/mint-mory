# Change: Segmented LLM distiller for agent history (Phase 2)

## Why

The v1 agent-history distiller (`core/history/distill.py`) is deterministic and
shallow: it collapses an entire session — however long — into ONE 600-char row
built from the first user turn + last assistant turn. A multi-hour session reads
as a single blob, losing the *progression* of what actually happened, and the
summary text is crude (it even surfaced `<local-command-caveat>` wrappers).

Phase 2 fixes both, along two composable axes:
- **Segment long sessions** into multiple timeline entries (~25 turns each) so a
  long session reads as an ordered "what happened, then what happened next".
- **Optionally LLM-distill** each segment (via `MINTMORY_LLM_*`) into a crisp
  changelog entry with cross-segment continuity — while the **default stays fully
  offline** (deterministic per-segment summaries, zero LLM calls).

Informed by an Opus max-thinking brainstorm + analysis of how **mempalace**
(exchange-pair atomicity, verbatim-first, reconstruction metadata) and **LEANN**
(role-tagged concatenation, chunk sizing) handle long content.

## What changes

- **Segmentation (pure, deterministic):** `core/history/segment.py` splits a
  session's normalized turns into segments by turn count, snapping cuts to a
  `user`-turn boundary (never mid-exchange / mid-tool-burst), with a time-gap
  override and runt-merge. Short sessions stay one segment. Boundaries are a pure
  function of turns (stable ids, idempotent). Knobs: `SegmentSettings`
  (`MINTMORY_HISTORY_SEG_*`), **enabled by default**.
- **One record per segment:** `record_type` stays `session_summary` (existing
  queries unchanged); envelope gains `segment_id` (`<session_id>#<i>`),
  `segment_index`, `segment_count`, `turn_lo`, `turn_hi`, and the **`title`**
  (fixes a latent bug — title was never stored). `valid_from` = segment start, so
  segments interleave chronologically.
- **LLM distiller (opt-in, local-first):** `distill_llm` summarizes each segment
  into strict JSON `{title, kind, summary, outcome, next_context}`, passing a
  short running context from the prior segment. **Every turn is redacted before it
  enters the prompt** (MM-27 boundary), output redacted again before persist. The
  distiller is built only when `MINTMORY_LLM_*` is configured AND the base_url is
  local — a non-localhost (cloud) endpoint requires an explicit opt-in
  (`--allow-cloud-llm` / `MINTMORY_HISTORY_ALLOW_CLOUD_LLM=true`); otherwise it
  falls back to deterministic (nothing leaves the box).
- **Idempotency & cost:** upsert by `segment_id`; archive orphaned tail segments
  on shrink (no hard delete); content-hash cache; `--max-llm-calls` budget and
  `--llm-only-since DATE` for recent-first rollout; `distiller_version=2`.
- **Timeline UX:** segments interleave by `valid_from` with a
  `(valid_from, session_id, segment_index)` tiebreak; CLI shows a `[k/N]` marker
  and the title; `--group-by-session` view; back-link carries `turn_lo/turn_hi`.
  MCP tools return the segment fields; `history_stats` reports sessions vs segments.

## Impact

- Affected specs: **agent-history** (segmentation + LLM distillation).
- Affected code: `core/history/{models,segment,distill,ingest,query,redact}.py`,
  `core/config.py` (`SegmentSettings`), `core/prompts.py`, `core/llm.py`
  (`build_history_distiller`); CLI `history` commands; `mintmory-history-mcp` tools.
- Default behaviour change: segmentation ON → long sessions now produce multiple
  timeline rows even with no LLM (a backfill-time change; deterministic + offline).
- No `schema.sql` change. New tests. All gates green.
