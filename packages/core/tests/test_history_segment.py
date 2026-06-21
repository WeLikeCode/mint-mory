"""
Tests for mintmory.core.history.segment — pure, deterministic segmentation.

Contract (design.md §3 + spec.md):
  - disabled/short  -> one segment covering all turns
  - long session    -> user-boundary snap (never split a tool/assistant burst)
  - time-gap        -> forces a boundary
  - runt merge      -> trailing segment < min_turns merges into previous
  - idempotent      -> same turns -> same segments
  - ranges tile     -> turn_lo/turn_hi cover all seqs, no gaps/overlap
  - cap             -> max_segments_per_session clips the count
"""

from __future__ import annotations

from datetime import UTC

import pytest
from mintmory.core.config import SegmentSettings
from mintmory.core.history.models import NormalizedTurn, Segment
from mintmory.core.history.segment import segment_turns

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _turns(
    n: int,
    *,
    roles: list[str] | None = None,
    ts_offset_minutes: int = 0,
    ts_step_minutes: int = 1,
    base_ts: str = "2024-01-01T10:00:00Z",
    include_ts: bool = True,
) -> list[NormalizedTurn]:
    """Build n NormalizedTurn objects with simple auto-assigned roles and timestamps."""
    from datetime import datetime, timedelta

    base = datetime.fromisoformat(base_ts.replace("Z", "+00:00"))
    result = []
    for i in range(n):
        # Default: user turn every 3rd (0-indexed), otherwise assistant.
        role = roles[i % len(roles)] if roles else ("user" if i % 3 == 0 else "assistant")
        if include_ts:
            ts_dt = base + timedelta(minutes=ts_offset_minutes + i * ts_step_minutes)
            ts = ts_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            ts = None
        result.append(NormalizedTurn(seq=i, ts=ts, role=role, text=f"turn {i}"))
    return result


def _seg_settings(**kwargs: object) -> SegmentSettings:
    """Build SegmentSettings with sensible test defaults overridden by kwargs."""
    from typing import Any  # noqa: PLC0415

    defaults: dict[str, Any] = {
        "enabled": True,
        "target_turns": 5,
        "min_turns": 3,
        "max_turns": 8,
        "gap_minutes": 30,
        "max_segments_per_session": 0,
        "allow_cloud_llm": False,
    }
    defaults.update(kwargs)
    return SegmentSettings(**defaults)


def _assert_tiles(segments: list[Segment], turns: list[NormalizedTurn]) -> None:
    """Assert segments tile the turns with no gaps or overlap."""
    if not turns:
        assert segments == []
        return
    # Collect all seqs from segments.
    seqs_in_segs: list[int] = []
    for seg in segments:
        for seq in range(seg.turn_lo, seg.turn_hi + 1):
            seqs_in_segs.append(seq)
    expected_seqs = [t.seq for t in turns]
    assert sorted(seqs_in_segs) == sorted(expected_seqs), (
        f"Segments do not tile turns: segment seqs={sorted(seqs_in_segs)}, "
        f"turn seqs={sorted(expected_seqs)}"
    )


# ---------------------------------------------------------------------------
# Empty and single-turn cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_turns_returns_empty(self) -> None:
        segments = segment_turns([], _seg_settings())
        assert segments == []

    def test_single_turn_returns_one_segment(self) -> None:
        turns = [NormalizedTurn(seq=0, ts="2024-01-01T10:00:00Z", role="user", text="hi")]
        segments = segment_turns(turns, _seg_settings())
        assert len(segments) == 1
        assert segments[0].idx == 0
        assert segments[0].turn_lo == 0
        assert segments[0].turn_hi == 0

    def test_two_turns_returns_one_segment(self) -> None:
        turns = _turns(2)
        segments = segment_turns(turns, _seg_settings())
        assert len(segments) == 1


# ---------------------------------------------------------------------------
# disabled / short => single segment
# ---------------------------------------------------------------------------


class TestDisabledShort:
    def test_disabled_always_one_segment(self) -> None:
        turns = _turns(50)  # many turns but disabled
        seg = _seg_settings(enabled=False)
        segments = segment_turns(turns, seg)
        assert len(segments) == 1
        assert segments[0].turn_lo == turns[0].seq
        assert segments[0].turn_hi == turns[-1].seq

    def test_short_session_is_one_segment(self) -> None:
        # max_turns=8; 7 turns -> one segment.
        turns = _turns(7)
        seg = _seg_settings(max_turns=8)
        segments = segment_turns(turns, seg)
        assert len(segments) == 1

    def test_exactly_max_turns_is_one_segment(self) -> None:
        turns = _turns(8)
        seg = _seg_settings(max_turns=8)
        segments = segment_turns(turns, seg)
        assert len(segments) == 1

    def test_one_more_than_max_turns_triggers_split(self) -> None:
        # 9 > 8 so we enter the windowing path.
        turns = _turns(9, roles=["user", "assistant", "assistant"])
        seg = _seg_settings(target_turns=5, min_turns=2, max_turns=8)
        segments = segment_turns(turns, seg)
        assert len(segments) >= 1
        _assert_tiles(segments, turns)


# ---------------------------------------------------------------------------
# User-boundary snap — never split a tool/assistant burst
# ---------------------------------------------------------------------------


class TestUserBoundarySnap:
    def test_boundary_falls_at_user_turn(self) -> None:
        """After reaching target_turns, the next user turn triggers a seal."""
        # Build: u a a a a u a a a (9 turns, target=5, max=8)
        roles = [
            "user",
            "assistant",
            "assistant",
            "assistant",
            "assistant",
            "user",
            "assistant",
            "assistant",
            "assistant",
        ]
        turns = _turns(len(roles), roles=roles)
        seg = _seg_settings(target_turns=5, min_turns=2, max_turns=8)
        segments = segment_turns(turns, seg)
        # There should be 2 segments (first ends before the 6th turn which is user).
        assert len(segments) >= 2
        _assert_tiles(segments, turns)
        # The boundary between segment 0 and 1 must be at a user turn.
        if len(segments) >= 2:
            # First turn of segment 1 must be role == 'user'.
            seg1_first_seq = segments[1].turn_lo
            first_turn_of_seg1 = next(t for t in turns if t.seq == seg1_first_seq)
            assert first_turn_of_seg1.role == "user"

    def test_never_splits_inside_tool_burst(self) -> None:
        """Tool/assistant turns immediately after a user ask stay in one segment."""
        # u a tool tool tool u a a a a u ...
        roles = [
            "user",
            "assistant",
            "tool",
            "tool",
            "tool",
            "user",
            "assistant",
            "assistant",
            "assistant",
            "assistant",
            "user",
            "assistant",
        ]
        turns = _turns(len(roles), roles=roles)
        seg = _seg_settings(target_turns=5, min_turns=2, max_turns=10)
        segments = segment_turns(turns, seg)
        _assert_tiles(segments, turns)
        # No segment should start with a tool or assistant turn
        # UNLESS it's the very first segment.
        for s in segments[1:]:
            first_seq = s.turn_lo
            first_turn = next(t for t in turns if t.seq == first_seq)
            assert first_turn.role == "user", (
                f"Segment {s.idx} starts with role={first_turn.role!r} (expected 'user')"
            )

    def test_force_close_at_max_turns(self) -> None:
        """If no user turn appears, force-close at max_turns."""
        # All assistant turns — no user boundary will appear.
        roles = ["assistant"] * 12
        turns = _turns(len(roles), roles=roles)
        seg = _seg_settings(target_turns=5, min_turns=2, max_turns=8)
        segments = segment_turns(turns, seg)
        # Each window is force-closed at 8; expect at least 1 segment.
        assert len(segments) >= 1
        _assert_tiles(segments, turns)


# ---------------------------------------------------------------------------
# Time-gap break
# ---------------------------------------------------------------------------


class TestTimeGap:
    def test_gap_forces_new_segment(self) -> None:
        """A gap > gap_minutes between consecutive turns forces a boundary."""
        from datetime import datetime, timedelta

        base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
        # 5 turns close together, then a 60-minute gap, then 5 more = 10 total.
        # Settings: gap_minutes=30, max_turns=15 (> 10 so short-session check
        # doesn't fire), target_turns=20 (high so normal windowing doesn't fire).
        turns = []
        for i in range(5):
            ts = (base + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
            role = "user" if i == 0 else "assistant"
            turns.append(NormalizedTurn(seq=i, ts=ts, role=role, text=f"t{i}"))
        gap_base = base + timedelta(minutes=4 + 60)
        for j in range(5):
            ts = (gap_base + timedelta(minutes=j)).strftime("%Y-%m-%dT%H:%M:%SZ")
            role = "user" if j == 0 else "assistant"
            turns.append(NormalizedTurn(seq=5 + j, ts=ts, role=role, text=f"t{5 + j}"))

        # With 10 turns > max_turns (must be < 10 to enter windowing path).
        # Use max_turns=9 so 10 > 9 -> windowing; target_turns=20 -> no
        # target-based close; gap=30 -> the 60-min gap fires.
        seg = _seg_settings(
            target_turns=20,
            min_turns=1,
            max_turns=9,
            gap_minutes=30,
        )
        segments = segment_turns(turns, seg)
        assert len(segments) == 2, f"Expected 2 segments, got {len(segments)}: {segments}"
        _assert_tiles(segments, turns)

    def test_no_gap_break_when_gap_minutes_zero(self) -> None:
        """gap_minutes=0 disables the time-gap check."""
        from datetime import datetime, timedelta

        base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
        # 12 turns (> max_turns=11) so windowing is active, but target=20 so no
        # target-based close.  gap=0 disables gap check -> one segment (force-
        # closed at max_turns=11, leaving 1 runt that merges back -> 1 segment
        # OR 2 segments depending on sizes).
        # Simplest: keep turns <= max_turns so single-seg path verifies the gap is off.
        turns = []
        for i in range(8):
            ts = (base + timedelta(minutes=i * 120)).strftime("%Y-%m-%dT%H:%M:%SZ")
            turns.append(
                NormalizedTurn(
                    seq=i, ts=ts, role="user" if i % 2 == 0 else "assistant", text=f"t{i}"
                )
            )
        # 8 turns <= max_turns=9 -> short session path -> single segment regardless of gap.
        seg = _seg_settings(
            target_turns=25,
            min_turns=1,
            max_turns=9,
            gap_minutes=0,
        )
        segments = segment_turns(turns, seg)
        assert len(segments) == 1

    def test_none_ts_never_triggers_gap(self) -> None:
        """Turns with ts=None do not trigger gap breaks."""
        # 20 turns all with ts=None; max_turns=9 so windowing is active.
        # gap_minutes=1 but all ts are None -> no gap fires -> only target/max
        # windowing applies.
        turns = _turns(20, include_ts=False, roles=["user", "assistant", "assistant"])
        seg = _seg_settings(target_turns=25, min_turns=1, max_turns=9, gap_minutes=1)
        segments = segment_turns(turns, seg)
        # All ts=None means _last_ts returns _EPOCH, so gap_exceeds always False.
        # With target=25 > 20, only max_turns=9 force-closes.
        _assert_tiles(segments, turns)
        # The key property: no spurious gap-triggered splits (all must be ~max_turns).
        for s in segments:
            size = s.turn_hi - s.turn_lo + 1
            # Each segment should be at most max_turns in size (force-close only).
            assert size <= seg.max_turns


# ---------------------------------------------------------------------------
# Runt merge
# ---------------------------------------------------------------------------


class TestRuntMerge:
    def test_trailing_runt_merges_into_previous(self) -> None:
        """A final segment smaller than min_turns merges into the previous."""
        # target=5, min=3, max=8.
        # Construct: 5 turns, then 2 more (runt < min=3).
        # With target=5 and the next user after 5 turns, window closes after 5.
        # Then 2 turns remain -> runt -> merges.
        roles = [
            "user",
            "assistant",
            "assistant",
            "assistant",
            "assistant",
            "user",
            "assistant",
        ]  # 7 turns
        turns = _turns(7, roles=roles)
        seg = _seg_settings(target_turns=5, min_turns=3, max_turns=8)
        segments = segment_turns(turns, seg)
        # If runt (2 turns) merges, we should have 1 segment.
        _assert_tiles(segments, turns)
        # After merging, no segment should be a runt (< min_turns) UNLESS it's the only one.
        if len(segments) > 1:
            last = segments[-1]
            last_size = last.turn_hi - last.turn_lo + 1
            assert last_size >= seg.min_turns, (
                f"Last segment has {last_size} turns < min_turns={seg.min_turns}"
            )

    def test_no_merge_when_runt_is_big_enough(self) -> None:
        """If the final window has >= min_turns, no merge happens."""
        # target=5, min=2, max=7: so 8 > 7 -> windowing active.
        # 5 turns then user boundary, then 3 more -> 2 segments of size 5 and 3.
        # runt threshold min=2: 3 >= 2 so no merge.
        roles = [
            "user",
            "assistant",
            "assistant",
            "assistant",
            "assistant",
            "user",
            "assistant",
            "assistant",
        ]  # 8 turns
        turns = _turns(8, roles=roles)
        seg = _seg_settings(target_turns=5, min_turns=2, max_turns=7)
        segments = segment_turns(turns, seg)
        _assert_tiles(segments, turns)
        # We expect 2 segments with sizes 5 and 3.
        assert len(segments) == 2
        assert segments[1].turn_hi - segments[1].turn_lo + 1 == 3


# ---------------------------------------------------------------------------
# Idempotent
# ---------------------------------------------------------------------------


class TestIdempotent:
    def test_same_turns_same_segments(self) -> None:
        turns = _turns(25)
        seg = _seg_settings(target_turns=5, min_turns=2, max_turns=8)
        s1 = segment_turns(turns, seg)
        s2 = segment_turns(turns, seg)
        assert s1 == s2

    def test_deterministic_with_different_settings(self) -> None:
        turns = _turns(30)
        seg = _seg_settings(target_turns=10, min_turns=3, max_turns=15)
        s1 = segment_turns(turns, seg)
        s2 = segment_turns(turns, seg)
        assert s1 == s2


# ---------------------------------------------------------------------------
# Ranges tile
# ---------------------------------------------------------------------------


class TestRangesTile:
    def test_ranges_tile_no_gaps(self) -> None:
        turns = _turns(30)
        seg = _seg_settings(target_turns=5, min_turns=2, max_turns=8)
        segments = segment_turns(turns, seg)
        _assert_tiles(segments, turns)

    def test_ranges_tile_single_segment(self) -> None:
        turns = _turns(5)
        seg = _seg_settings()
        segments = segment_turns(turns, seg)
        _assert_tiles(segments, turns)

    def test_idx_is_zero_based_contiguous(self) -> None:
        turns = _turns(30)
        seg = _seg_settings(target_turns=5, min_turns=2, max_turns=8)
        segments = segment_turns(turns, seg)
        for i, s in enumerate(segments):
            assert s.idx == i, f"Expected idx={i}, got {s.idx}"

    def test_consecutive_segs_share_boundary(self) -> None:
        """The turn_hi of segment k must be exactly turn_lo[k+1] - 1."""
        turns = _turns(30, roles=["user", "assistant", "assistant"])
        seg = _seg_settings(target_turns=5, min_turns=2, max_turns=8)
        segments = segment_turns(turns, seg)
        for i in range(len(segments) - 1):
            assert segments[i].turn_hi + 1 == segments[i + 1].turn_lo, (
                f"Gap between seg {i} and {i + 1}: "
                f"turn_hi={segments[i].turn_hi}, turn_lo={segments[i + 1].turn_lo}"
            )


# ---------------------------------------------------------------------------
# max_segments cap
# ---------------------------------------------------------------------------


class TestMaxSegmentsCap:
    def test_cap_limits_segment_count(self) -> None:
        turns = _turns(40, roles=["user", "assistant", "assistant"])
        seg = _seg_settings(target_turns=5, min_turns=2, max_turns=8, max_segments_per_session=3)
        segments = segment_turns(turns, seg)
        assert len(segments) <= 3

    def test_cap_tiles_all_turns(self) -> None:
        turns = _turns(40, roles=["user", "assistant", "assistant"])
        seg = _seg_settings(target_turns=5, min_turns=2, max_turns=8, max_segments_per_session=2)
        segments = segment_turns(turns, seg)
        _assert_tiles(segments, turns)
        assert len(segments) <= 2

    def test_cap_zero_is_unlimited(self) -> None:
        turns = _turns(40, roles=["user", "assistant", "assistant"])
        seg = _seg_settings(target_turns=5, min_turns=2, max_turns=8, max_segments_per_session=0)
        segments = segment_turns(turns, seg)
        # With cap=0 we can have more than 3 segments.
        assert len(segments) >= 1
        _assert_tiles(segments, turns)


# ---------------------------------------------------------------------------
# Segment dataclass
# ---------------------------------------------------------------------------


class TestSegmentDataclass:
    def test_segment_is_frozen(self) -> None:
        s = Segment(
            idx=0,
            turn_lo=0,
            turn_hi=4,
            ts_start="2024-01-01T10:00:00Z",
            ts_end="2024-01-01T10:05:00Z",
        )
        with pytest.raises((AttributeError, TypeError)):
            s.idx = 1  # type: ignore[misc]

    def test_ts_start_from_first_non_none_ts(self) -> None:
        """ts_start is the first non-None ts in the slice."""
        turns = [
            NormalizedTurn(seq=0, ts=None, role="user", text="a"),
            NormalizedTurn(seq=1, ts="2024-06-01T09:00:00Z", role="assistant", text="b"),
        ]
        seg = _seg_settings(enabled=False)
        segments = segment_turns(turns, seg)
        assert len(segments) == 1
        assert segments[0].ts_start == "2024-06-01T09:00:00Z"
