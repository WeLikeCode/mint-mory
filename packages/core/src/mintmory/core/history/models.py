"""
history/models.py — normalized schema for agentic session summaries.

Dataclasses are frozen so instances are hashable and safe to cache.
Adapters yield (SessionSummary, list[NormalizedTurn]) per session;
kind/title/summary_text fields are left at defaults — distill() fills them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

AGENTS: tuple[str, ...] = ("claude_code", "codex", "kiro")
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


@dataclass
class SessionSummary:
    """Normalised metadata + distilled summary for one agentic session."""

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
