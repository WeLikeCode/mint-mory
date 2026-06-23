"""
history/models.py — normalized schema for agentic session summaries.

Dataclasses are frozen so instances are hashable and safe to cache.
Adapters yield (SessionSummary, list[NormalizedTurn]) per session;
kind/title/summary_text fields are left at defaults — distill() fills them.

Phase 2 additions:
  - Segment: frozen dataclass for a turn-range slice of a session.
  - SessionSummary: extended with segment_index, segment_count, turn_lo,
    turn_hi, session_ts_start, session_ts_end, outcome (defaults keep
    single-segment / backward compatibility).
"""

from __future__ import annotations

from dataclasses import dataclass, field

AGENTS: tuple[str, ...] = ("claude_code", "codex", "kiro", "hermes")
KINDS: tuple[str, ...] = (
    "fix",
    "feature",
    "refactor",
    "investigation",
    "chore",
    "docs",
    "incident",
)


@dataclass
class NormalizedTurn:
    """One turn in a normalised agentic session."""

    seq: int
    ts: str | None  # ISO-8601 UTC, or None
    role: str  # "user" | "assistant" | "tool"
    text: str
    tool_name: str | None = None


@dataclass(frozen=True)
class Segment:
    """A deterministic, contiguous slice of a session's turns (Phase 2).

    turn_lo / turn_hi are the inclusive seq values of the first and last turn
    in this segment. ts_start / ts_end are ISO-8601 UTC strings taken from
    the first/last non-None turn timestamp in the slice (fallback: session ts).
    idx is 0-based.
    """

    idx: int  # 0-based
    turn_lo: int  # inclusive seq of first turn in this segment
    turn_hi: int  # inclusive seq of last turn
    ts_start: str  # ISO-8601 UTC — first turn ts (fallback: session ts_start)
    ts_end: str  # ISO-8601 UTC — last turn ts


@dataclass
class SessionSummary:
    """Normalised metadata + distilled summary for one agentic session.

    Single-segment (Phase 1) callers leave the Phase-2 fields at their
    defaults: segment_index=0, segment_count=1, turn_lo=0, turn_hi=0.
    """

    session_id: str
    agent: str  # one of AGENTS
    repo: str  # git-root basename, else cwd basename, else "unknown"
    repo_path: str  # absolute cwd/workspace path ("" if unknown)
    branch: str  # "" if unknown
    ts_start: str  # ISO-8601 UTC (session's first turn / meta time)
    ts_end: str  # ISO-8601 UTC (last turn time; == ts_start if 1)
    turn_count: int
    tools_used: list[str] = field(default_factory=list)
    kind: str = "investigation"  # one of KINDS
    title: str = ""
    summary_text: str = ""  # changelog voice, <= 600 chars
    source_path: str = ""  # absolute path to the session file
    source_offset: int = 0  # byte offset of the session start (0 for whole-file)
    model: str = ""  # model id if known
    distiller_version: int = 1
    # Phase-2 segment fields (defaults keep single-segment compatibility)
    segment_index: int = 0  # 0-based index of this segment within the session
    segment_count: int = 1  # total segments in the session
    turn_lo: int = 0  # inclusive seq of first turn in this segment
    turn_hi: int = 0  # inclusive seq of last turn in this segment
    session_ts_start: str = ""  # whole-session start (grouping); "" -> fall back to ts_start
    session_ts_end: str = ""  # whole-session end
    outcome: str = ""  # short status line from the LLM ("" for deterministic)
