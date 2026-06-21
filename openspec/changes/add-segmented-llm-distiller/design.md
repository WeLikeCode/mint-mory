# Design & FROZEN contract — `add-segmented-llm-distiller` (Phase 2)

Match names/signatures/defaults/behaviour exactly. Additive except the intended
default change (segmentation ON). Invariant: **`provider=none` reproduces today's
behaviour generalized to N deterministic segments — fully offline, zero LLM**.
**Segment boundaries are a PURE function of turns** (no LLM) so ids/counts are
stable and idempotent. LLM affects only summary TEXT.

Locked decisions: segmentation **ON by default**; LLM distiller **local-only**
unless explicitly allowed; re-distill **recent-first + budget**.

---

## 1. `core/config.py` — `SegmentSettings`

```python
class SegmentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINTMORY_HISTORY_SEG_", extra="ignore")
    enabled: bool = True                 # default ON
    target_turns: int = Field(default=25, ge=4, le=500)
    min_turns: int = Field(default=12, ge=1, le=500)     # trailing-runt merge threshold
    max_turns: int = Field(default=40, ge=4, le=1000)    # hard cap if no user boundary
    gap_minutes: int = Field(default=45, ge=0, le=10000) # 0 disables the time-gap break
    max_segments_per_session: int = Field(default=0, ge=0)  # 0 = unlimited
    allow_cloud_llm: bool = False        # gate non-localhost LLM base_url for the distiller
```
Add `seg: SegmentSettings` to the aggregate `Settings`.

---

## 2. `core/history/models.py` — segment model

```python
@dataclass(frozen=True)
class Segment:
    idx: int          # 0-based
    turn_lo: int      # inclusive seq of first turn in this segment
    turn_hi: int      # inclusive seq of last turn
    ts_start: str     # ISO-8601 UTC — first turn ts (fallback: session ts_start)
    ts_end: str       # ISO-8601 UTC — last turn ts
```
Extend `SessionSummary` with (defaults keep single-segment compatibility):
```python
    segment_index: int = 0
    segment_count: int = 1
    turn_lo: int = 0
    turn_hi: int = 0
    session_ts_start: str = ""   # whole-session start (grouping); "" -> fall back to ts_start
    session_ts_end: str = ""
    outcome: str = ""            # short status line from the LLM ("" for deterministic)
```
For a SEGMENT, `ts_start`/`ts_end` are SEGMENT-local; `session_ts_start/end` hold
the whole-session range. `segment_id` is computed at write time as
`f"{session_id}#{segment_index}"` (not stored on the dataclass).

---

## 3. `core/history/segment.py` — pure segmentation (NEW)

```python
def segment_turns(turns: list[NormalizedTurn], settings: SegmentSettings) -> list[Segment]:
    """Pure, deterministic. No LLM, no I/O.
    - settings.enabled False OR len(turns) <= max_turns -> ONE segment [0..n-1].
    - else sweep: accumulate turns; once the window has >= target_turns, CLOSE at
      the NEXT turn whose role == 'user' (never split between a user ask and the
      assistant/tool turns answering it). Force-close at max_turns if no user
      boundary appears. A gap > gap_minutes between consecutive turn ts forces a
      boundary there (turns with ts=None never trigger a gap; they attach to the
      running window). Merge a final window of < min_turns back into the previous.
    - max_segments_per_session>0 caps the count (extra turns fold into the last seg).
    Each Segment.turn_lo/turn_hi index seq exactly; ts_start/end from the slice's
    first/last non-None ts (fallback to the session ts)."""
```
Empty `turns` -> `[]`. Single-turn -> one segment. Deterministic + idempotent
(same turns -> same segments).

---

## 4. `core/history/distill.py` — per-segment, deterministic + LLM

Refactor today's logic into a segment-scoped deterministic function, keep the same
output contract, and add the LLM variant:
```python
def distill_segment_deterministic(summary: SessionSummary, seg_turns: list[NormalizedTurn]) -> SessionSummary:
    """Today's heuristic, scoped to a segment's turn slice: title = first user turn
    in the slice (<=80); summary_text = 'Asked: <first user 200c> Outcome: <last
    assistant 300c> tools:…' (<=600c); kind = keyword heuristic; distiller_version=1."""

def distill_llm(
    summary: SessionSummary, seg_turns: list[NormalizedTurn], chat: ChatFn, *, prev_context: str = ""
) -> tuple[SessionSummary, str]:
    """LLM per-segment. Returns (filled SessionSummary, next_context).
    1. Build a redacted, role-tagged transcript of seg_turns: redact(turn.text) for
       EVERY turn BEFORE concatenation (hard security boundary). Head+tail elide
       oversized tool_results but NEVER drop a user turn.
    2. Prompt = prompts.HISTORY_SEGMENT_PROMPT.format(prev_context=redact(prev_context),
       repo=…, transcript=…) asking for STRICT JSON {title,kind,summary,outcome,next_context}.
    3. raw = chat(prompt); data = extract_json(raw) (tolerant; strips <think>).
    4. Validate/clamp: title<=80, summary<=600, kind in KINDS (else 'investigation'),
       outcome<=120, next_context<=300. On empty/garbage/missing -> raise (caller
       falls back to deterministic). distiller_version=2.
    Returns the new SessionSummary (dataclasses.replace) and next_context (redacted)
    for the next segment's prompt."""
```
`ChatFn = Callable[[str], str]` (so tests inject a fake; production passes
`LLMClient.chat`). `distill_llm` MUST NOT undo redaction; `write_session` still
redacts the OUTPUT title/summary before persist (defense in depth).

---

## 5. `core/prompts.py` — `HISTORY_SEGMENT_PROMPT`

A prompt instructing: summarize THIS segment of an agent coding session as a
changelog entry; output ONLY strict JSON with keys `title` (≤8 words, imperative),
`kind` (one of the 7 KINDS), `summary` (≤2 sentences, what was done/decided),
`outcome` (≤1 short clause: done/partial/blocked/…), `next_context` (≤1 sentence
to brief the next segment). Includes `{prev_context}` (what came before) and the
`{transcript}`.

---

## 6. `core/llm.py` — `build_history_distiller`

```python
def build_history_distiller(
    llm: LLMSettings, seg: SegmentSettings
) -> Callable[..., tuple[SessionSummary, str]] | None:
    """Return a per-segment LLM distiller, or None to use the deterministic path.
    None when: llm.provider is NONE; OR base_url is NON-LOCAL and not seg.allow_cloud_llm
    (local-only default — _is_local_base_url checks localhost/127.0.0.1/::1/[::1]).
    Otherwise build an LLMClient(llm) and return a closure
    (summary, seg_turns, prev_context) -> distill_llm(summary, seg_turns, client.chat,
    prev_context=prev_context)."""
```
`_is_local_base_url(url) -> bool` helper. This is the cloud-egress gate.

---

## 7. `core/history/ingest.py` — write segments, idempotent, budgeted

Replace per-session write with per-segment:
```python
def write_session_segments(
    store, session_summary, segments, distiller=None, *, budget=None, now=None
) -> SegWriteResult:
    """segments: list[Segment]. For each segment in ORDER:
      - seg_turns = full_turns[seg.turn_lo : seg.turn_hi+1] (caller passes turns);
      - compute content_hash = sha256(distiller_version|seg_signature|model|redacted seg transcript);
      - if an existing row with this segment_id has the same content_hash -> SKIP (cache hit);
      - else if distiller and budget allows: try distiller(seg_summary, seg_turns, prev_context)
        -> (summary, next_context); on ANY error/None -> deterministic + log fallback;
        else deterministic (next_context='');
      - redact title+summary_text; build envelope (below); UPSERT by segment_id
        (_find_by_segment_id -> update_memory else add_memory(id=segment_id,...));
        valid_from = seg.ts_start; carry prev_context = next_context.
    After writing 0..count-1: ORPHAN-SWEEP — archive_memory any existing row with
    metadata.session_id == session_id and segment_index >= count.
    Returns counts (written, updated, cache_hits, llm_calls, llm_fallbacks)."""
```
Envelope per segment (extends today's): add `segment_id, segment_index,
segment_count, turn_lo, turn_hi, title, outcome, session_ts_start, session_ts_end,
content_hash, seg_signature` (`seg_signature = sha of (target,min,max,gap,enabled)`).
Keep all existing keys (record_type, collection, agent, repo, repo_path, branch,
kind, session_id, ts_start, ts_end, turn_count, tools_used, source_path,
source_offset, model, distiller_version).

`backfill`/`sync` changes:
- build `distiller = build_history_distiller(load_settings().llm, seg_settings)` once;
  resolve `seg_settings` (with `allow_cloud_llm` overridable by the CLI flag).
- per session: `segs = segment_turns(turns, seg_settings)`; set
  `segment_count=len(segs)` and `session_ts_start/end`; call `write_session_segments`.
- **Re-distill triggers:** a file's segments are (re)written when the source file
  changed (manifest hash, existing) OR stored `distiller_version` < target OR stored
  `seg_signature` differs. Unchanged + same version/signature -> skip (sync).
- **Cost controls:** `LLMBudget(max_calls)` shared across sessions; `--max-llm-calls N`
  (0=unlimited); `--llm-only-since DATE` (sessions with `session_ts_start` older than
  DATE use deterministic even if a distiller exists); `--allow-cloud-llm`.
- **Concurrency:** fan ACROSS sessions with `ThreadPoolExecutor(max_workers=llm.max_concurrency)`
  (segments WITHIN a session stay sequential for the prev_context handoff), then
  write serially (mirror `dreaming.py` collect-then-write). Manifest update records
  all segment ids in `memory_ids`.
- `IngestReport` gains: `segments_written, llm_calls, llm_cache_hits, llm_fallbacks,
  llm_calls_deferred`.

---

## 8. `core/history/query.py` — segment-aware

- `_shape_row` adds `segment_index, segment_count, turn_lo, turn_hi, title, outcome`.
- `timeline` ORDER BY `valid_from DESC, session_id ASC, segment_index ASC` (the
  tiebreak is REQUIRED — second-resolution timestamps tie within a session).
- `timeline(..., group_by_session: bool = False)`: when True, group rows by
  `session_id` (each group ordered by segment_index), groups ordered by newest
  `valid_from`. Default False (flat chronological).
- `search` ranks segments individually; unchanged otherwise.

---

## 9. CLI + MCP

- CLI `history timeline`: render the `title` column; when `segment_count > 1`,
  annotate with `[k/N]` (k=segment_index+1). Add `--group-by-session`. `backfill`/
  `sync` gain `--max-llm-calls`, `--llm-only-since`, `--allow-cloud-llm`.
- MCP `history_timeline`/`history_search` return `segment_index, segment_count,
  turn_lo, turn_hi, title, outcome` in each row + a `group` param on timeline.
  `history_stats` returns `total_sessions` (distinct session_id) AND `total_segments`
  (row count).

---

## 10. Tests (contract)
- `test_history_segment.py`: disabled/short -> 1 segment; long session -> windows
  snapped to user turns (never split a tool burst); time-gap forces a break;
  trailing runt merges; deterministic (idempotent); turn_lo/turn_hi cover all seqs
  with no gaps/overlap; max_segments cap.
- `test_history_distill.py` (extend): `distill_segment_deterministic` scoped to a
  slice; `distill_llm` with a FAKE chat fn returns clamped fields + next_context;
  **a planted secret (`mk_agent_…`/JWT) in a turn never appears in the prompt the
  fake chat receives** (redaction-before-LLM); garbage/empty JSON -> raises (→fallback).
- `test_history_ingest.py` (extend): N segments -> N rows with segment_id/index/
  count/turn_lo/turn_hi/title; re-ingest with FEWER segments archives the orphans
  (is_archived=1, gone from timeline); content_hash cache skips unchanged; budget
  caps llm_calls then falls back; valid_from == segment ts_start.
- `test_history_query.py` (extend): same-second segments order by segment_index;
  group_by_session groups correctly; shape_row has the new keys.
- `test_llm.py`/config: `build_history_distiller` is None for provider=none and for
  non-local base_url without allow_cloud_llm; non-None for localhost or when allowed.
- MCP test: timeline/search rows carry segment fields; history_stats sessions≠segments.

All gates: `ruff check . && ruff format --check . && mypy packages && pytest -q` (cov ≥ 80).
Tests use temp DBs + fake chat fns only — never the real stores or a real LLM.
