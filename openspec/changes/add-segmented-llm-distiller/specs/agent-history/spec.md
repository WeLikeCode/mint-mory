# Capability: agent-history (delta)

## ADDED Requirements

### Requirement: Deterministic session segmentation

The system SHALL split a session's normalized turns into one or more segments by a
**pure, deterministic** function of the turns (no LLM, no I/O), so segment ids and
counts are stable across re-ingest. Segmentation SHALL be **enabled by default**
(`SegmentSettings.enabled`). A session whose turn count is ≤ `max_turns`, or when
disabled, SHALL yield exactly one segment spanning all turns. Otherwise segments
SHALL accumulate to ~`target_turns` and close at the **next `user`-role turn** (a
segment boundary SHALL NOT fall between a user turn and the assistant/tool turns
answering it), force-closing at `max_turns`; a gap greater than `gap_minutes`
between consecutive turns SHALL force a boundary; a trailing segment smaller than
`min_turns` SHALL merge into the previous one. Each segment SHALL carry a turn
range (`turn_lo`..`turn_hi`, inclusive `seq`) covering the turns with no gaps or
overlap.

#### Scenario: Short session stays one segment; long session splits at user turns
- **GIVEN** a session with fewer turns than `max_turns`
- **THEN** segmentation yields exactly one segment covering all turns.
- **GIVEN** a long session
- **WHEN** it is segmented
- **THEN** each boundary falls at a `user` turn (never inside a tool/assistant burst), and the segments' turn ranges tile the session with no gaps or overlap.

### Requirement: One timeline record per segment

Each segment SHALL be stored as one `MemoryRecord` (`category=EPISODIC`,
`source=AGENT`, `record_type="session_summary"`) with `valid_from` = the segment's
first-turn time, so segments interleave chronologically. The metadata envelope
SHALL include `segment_id` (`<session_id>#<index>`), `segment_index`,
`segment_count`, `turn_lo`, `turn_hi`, and `title`. Writes SHALL be idempotent on
`segment_id`. When a re-distill produces FEWER segments than before, the orphaned
higher-index segments SHALL be archived (`is_archived=1`), not duplicated or left
stale; they SHALL disappear from timeline/search/stats.

#### Scenario: Re-segmenting to fewer parts archives the orphans
- **GIVEN** a session previously stored as 5 segments
- **WHEN** it is re-ingested and now yields 3 segments
- **THEN** segments 0–2 are updated in place and segments 3–4 are archived (absent from timeline), with no duplicate rows.

### Requirement: Optional, local-first LLM segment distiller

When `MINTMORY_LLM_*` is configured, the system SHALL distill each segment via an
LLM into a title, kind, summary, outcome, and a `next_context` handed to the
following segment's prompt. The distiller SHALL be built ONLY when the provider is
set AND the LLM `base_url` is local — a non-local (cloud) endpoint SHALL require an
explicit opt-in (`--allow-cloud-llm` / `MINTMORY_HISTORY_ALLOW_CLOUD_LLM`);
otherwise the system SHALL fall back to deterministic per-segment summaries.
With `provider=none` the system SHALL produce deterministic per-segment summaries
with **zero LLM calls** (offline). Any LLM error, empty, or malformed-JSON result
SHALL fall back to the deterministic summary for that segment and never abort the
run.

#### Scenario: Cloud endpoint is not used without opt-in
- **GIVEN** `MINTMORY_LLM_*` points at a non-localhost base_url and `allow_cloud_llm` is false
- **WHEN** the history distiller is built
- **THEN** it is `None` (deterministic path used) and no transcript leaves the machine.

### Requirement: Secrets redacted before reaching the LLM

The system SHALL redact every segment turn's text (and the carried `prev_context`)
before it is placed into an LLM prompt, so no live secret is sent to the LLM
endpoint. The distilled output SHALL also be redacted before persistence.

#### Scenario: A planted secret never reaches the model
- **GIVEN** a segment turn containing an `mk_agent_…` key or a JWT
- **WHEN** the LLM distiller builds its prompt
- **THEN** the prompt text contains only `[REDACTED:…]` placeholders, not the secret.

### Requirement: Cost-bounded, recent-first re-distillation

LLM distillation SHALL be cost-bounded: a content-hash cache SHALL skip unchanged
segments; `--max-llm-calls` SHALL cap calls per run (excess segments fall back to
deterministic); `--llm-only-since DATE` SHALL restrict LLM spend to recent
sessions. `distiller_version` SHALL gate re-runs. The ingest report SHALL surface
`segments_written`, `llm_calls`, `llm_cache_hits`, and `llm_fallbacks`.

#### Scenario: A call budget caps LLM spend and falls back
- **GIVEN** a backfill with `--max-llm-calls 10` over sessions needing more than 10 segment distillations
- **WHEN** the run reaches 10 LLM calls
- **THEN** the remaining segments use deterministic summaries, the run completes, and the report shows `llm_calls = 10` with the rest counted as fallbacks/deferred.

### Requirement: Segment-aware timeline ordering and rendering

`timeline` SHALL order by `valid_from` descending with a
`(session_id, segment_index)` tiebreak so a session's segments stay in author
order within the same timestamp second. The CLI SHALL render the segment `title`
and a `[k/N]` marker when `segment_count > 1`, and offer a `--group-by-session`
view. MCP `history_timeline`/`history_search` rows SHALL include `segment_index`,
`segment_count`, `turn_lo`, `turn_hi`, and `title`; `history_stats` SHALL report
both total sessions and total segments.

#### Scenario: Same-second segments keep author order
- **GIVEN** two segments of one session whose `valid_from` falls in the same second
- **WHEN** the timeline is rendered newest-first
- **THEN** they appear adjacent in ascending `segment_index` order, not interleaved with each other arbitrarily.
