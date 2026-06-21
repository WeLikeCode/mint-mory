"""
history/segment.py — pure, deterministic session segmentation (Phase 2).

segment_turns() splits a list of NormalizedTurn objects into one or more
Segment slices using only the turn data and SegmentSettings.  No LLM, no I/O.

Algorithm (per design.md §3):
  1. disabled OR len(turns) <= max_turns  => one segment covering all turns.
  2. Sweep: accumulate turns.  Once window >= target_turns, mark as
     "ready to close".  The NEXT turn whose role == 'user' triggers a seal
     BEFORE that turn is added (user turn goes into the new window).
  3. A gap > gap_minutes between consecutive turn timestamps forces a seal
     before the current turn.  Turns with ts=None never trigger a gap.
  4. Force-close at max_turns if no user boundary appears.
  5. Merge a final segment of < min_turns back into the previous one.
  6. max_segments_per_session > 0 caps the count; extra turns fold into last.
  7. turn_lo / turn_hi cover turns with no gaps or overlap (seq-based).
  8. ts_start/ts_end: first/last non-None ts in the slice; fallback _EPOCH.

Invariants:
  - Empty turns   -> [].
  - Single turn   -> [one Segment].
  - Deterministic + idempotent: same turns -> same segments.
"""

from __future__ import annotations

from datetime import UTC, datetime

from mintmory.core.config import SegmentSettings
from mintmory.core.history.models import NormalizedTurn, Segment

# ISO-8601 sentinel used when a fallback timestamp cannot be determined.
_EPOCH = "1970-01-01T00:00:00Z"


def _parse_ts(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 UTC string to a timezone-aware datetime, or None."""
    if ts is None:
        return None
    try:
        t = ts
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        return datetime.fromisoformat(t).astimezone(UTC)
    except (ValueError, AttributeError):
        return None


def _gap_exceeds(prev_ts: str | None, curr_ts: str | None, gap_minutes: int) -> bool:
    """Return True if the gap between two timestamps exceeds gap_minutes."""
    if gap_minutes <= 0:
        return False
    prev = _parse_ts(prev_ts)
    curr = _parse_ts(curr_ts)
    if prev is None or curr is None:
        return False
    diff_minutes = (curr - prev).total_seconds() / 60.0
    return diff_minutes > gap_minutes


def _first_ts(turns: list[NormalizedTurn]) -> str:
    """Return the first non-None ts in the list, or _EPOCH."""
    for t in turns:
        if t.ts is not None:
            return t.ts
    return _EPOCH


def _last_ts(turns: list[NormalizedTurn]) -> str:
    """Return the last non-None ts in the list, or _EPOCH."""
    for t in reversed(turns):
        if t.ts is not None:
            return t.ts
    return _EPOCH


def _build_one_segment(turns: list[NormalizedTurn]) -> Segment:
    """Build a single Segment covering all turns."""
    return Segment(
        idx=0,
        turn_lo=turns[0].seq,
        turn_hi=turns[-1].seq,
        ts_start=_first_ts(turns),
        ts_end=_last_ts(turns),
    )


def _seal_window(window: list[NormalizedTurn], idx: int) -> Segment:
    """Convert an accumulated window of turns into a Segment."""
    return Segment(
        idx=idx,
        turn_lo=window[0].seq,
        turn_hi=window[-1].seq,
        ts_start=_first_ts(window),
        ts_end=_last_ts(window),
    )


def _reindex(segments: list[Segment]) -> list[Segment]:
    """Return a new list with idx reset to 0-based contiguous indices."""
    return [
        Segment(idx=i, turn_lo=s.turn_lo, turn_hi=s.turn_hi, ts_start=s.ts_start, ts_end=s.ts_end)
        for i, s in enumerate(segments)
    ]


def segment_turns(
    turns: list[NormalizedTurn],
    settings: SegmentSettings,
) -> list[Segment]:
    """Pure, deterministic segmentation of a session's turns.

    Returns [] for empty input.  Returns [one Segment] when:
      - settings.enabled is False, OR
      - len(turns) <= settings.max_turns.

    Otherwise applies the windowing algorithm described in design.md §3.
    """
    if not turns:
        return []

    # Short session or segmentation disabled -> single segment.
    if not settings.enabled or len(turns) <= settings.max_turns:
        return [_build_one_segment(turns)]

    segments: list[Segment] = []
    window: list[NormalizedTurn] = []
    seg_idx = 0
    ready_to_close = False  # True once window >= target_turns; wait for next user boundary

    for turn in turns:
        # Time-gap check: seal the window before adding this turn.
        if window and settings.gap_minutes > 0:
            prev_ts = _last_ts(window)
            if prev_ts != _EPOCH and _gap_exceeds(prev_ts, turn.ts, settings.gap_minutes):
                segments.append(_seal_window(window, seg_idx))
                seg_idx += 1
                window = []
                ready_to_close = False

        # User-boundary close: if ready and this is a user turn, seal before adding.
        if ready_to_close and turn.role == "user" and window:
            segments.append(_seal_window(window, seg_idx))
            seg_idx += 1
            window = []
            ready_to_close = False

        window.append(turn)

        # Force-close at max_turns (hard cap — must happen AFTER adding the turn).
        if len(window) >= settings.max_turns:
            segments.append(_seal_window(window, seg_idx))
            seg_idx += 1
            window = []
            ready_to_close = False
            continue

        # Mark ready to close once we've accumulated >= target_turns.
        if len(window) >= settings.target_turns:
            ready_to_close = True

    # Flush remaining turns.
    if window:
        segments.append(_seal_window(window, seg_idx))

    # Merge trailing runt (< min_turns) back into the previous segment.
    if len(segments) >= 2:
        last_seg = segments[-1]
        last_size = last_seg.turn_hi - last_seg.turn_lo + 1
        if last_size < settings.min_turns:
            prev_seg = segments[-2]
            merged = Segment(
                idx=prev_seg.idx,
                turn_lo=prev_seg.turn_lo,
                turn_hi=last_seg.turn_hi,
                ts_start=prev_seg.ts_start,
                ts_end=last_seg.ts_end,
            )
            segments[-2] = merged
            segments.pop()

    # Cap max_segments_per_session (0 = unlimited).
    if settings.max_segments_per_session > 0 and len(segments) > settings.max_segments_per_session:
        cap = settings.max_segments_per_session
        last_kept = segments[cap - 1]
        last_extra = segments[-1]
        folded = Segment(
            idx=last_kept.idx,
            turn_lo=last_kept.turn_lo,
            turn_hi=last_extra.turn_hi,
            ts_start=last_kept.ts_start,
            ts_end=last_extra.ts_end,
        )
        segments = segments[: cap - 1] + [folded]

    # Re-index contiguously (0-based) after merges and cap.
    return _reindex(segments)
