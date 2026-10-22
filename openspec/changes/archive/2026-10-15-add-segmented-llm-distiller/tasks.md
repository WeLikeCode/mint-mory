# Tasks — add-segmented-llm-distiller (Phase 2)

## 1. Config + model
- [x] 1.1 `SegmentSettings` (`MINTMORY_HISTORY_SEG_`, enabled=True, target/min/max/gap,
  max_segments_per_session, allow_cloud_llm) + add to `Settings`.
- [x] 1.2 `models.py`: `Segment` dataclass; extend `SessionSummary`
  (segment_index/count, turn_lo/hi, session_ts_start/end, outcome).

## 2. Segmentation (pure)
- [x] 2.1 `core/history/segment.py` `segment_turns(turns, settings)` — deterministic
  window + user-boundary snap + gap override + runt-merge + cap; 1 segment when
  disabled/short.

## 3. Distiller
- [x] 3.1 `distill.py`: `distill_segment_deterministic` (refactor of today, per-slice);
  `distill_llm(summary, seg_turns, chat, prev_context)` → (summary, next_context),
  per-turn redact BEFORE prompt, strict-JSON extract+clamp, raise on garbage.
- [x] 3.2 `prompts.py` `HISTORY_SEGMENT_PROMPT`.
- [x] 3.3 `llm.py` `build_history_distiller(llm, seg)` → callable|None
  (None for provider=none or non-local base_url unless allow_cloud_llm); `_is_local_base_url`.

## 4. Ingest
- [x] 4.1 `write_session_segments` (upsert by segment_id, content_hash cache,
  deterministic/LLM per segment with prev_context, redact output, orphan-sweep archive).
- [x] 4.2 `backfill`/`sync`: segment each session, build distiller once, re-distill
  triggers (distiller_version/seg_signature), `--max-llm-calls`, `--llm-only-since`,
  `--allow-cloud-llm`, across-session concurrency; extend `IngestReport`.

## 5. Query + CLI + MCP
- [x] 5.1 `query.py`: `_shape_row` new fields; ORDER BY valid_from,session_id,segment_index;
  `group_by_session`.
- [x] 5.2 CLI `timeline` `[k/N]`+title + `--group-by-session`; new backfill/sync flags.
- [x] 5.3 MCP rows carry segment fields; `history_stats` total_sessions vs total_segments.

## 6. Tests + gates
- [x] 6.1 STAGE 1 CORE: test_history_segment.py (26 tests), test_history_distill_phase2.py
  (31 tests), test_llm_distiller.py (17 tests). `ruff check` clean. 759 total tests pass.
- [x] 6.2 STAGE 2: test_history_ingest.py extended (N segments, orphan-sweep, cache,
  budget, valid_from, prev_context chain); test_history_query.py extended (tiebreak,
  group_by_session, shape_row segment fields); test_history_mcp.py extended (segment
  fields, total_sessions/total_segments). 1077 total tests pass.
  `ruff check && ruff format --check && mypy packages && pytest -q` (cov 95%) — GATE PASSED.
