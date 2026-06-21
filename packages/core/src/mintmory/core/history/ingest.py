"""
history/ingest.py — writer, backfill/sync, hermes-guard, manifest dedup.

The dedicated history DB is ALWAYS separate from the working store:
  DEFAULT_HISTORY_DB = ~/.mintmory/agent-history.db
  HermesGuardError is raised if the target resolves to the working store.

_ADAPTERS lazily imports core.history.adapters.{claude_code,codex,kiro}.iter_sessions
inside backfill/sync so this module imports cleanly before the adapters exist.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import logging
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from mintmory.core.history.distill import distill_segment_deterministic
from mintmory.core.history.models import NormalizedTurn, Segment, SessionSummary
from mintmory.core.history.redact import redact
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import MemoryCategory, MemorySource

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_HISTORY_DB: str = "~/.mintmory/agent-history.db"

# Aliases for the enum members we use — verified to exist in types.py
_EPISODIC = MemoryCategory.EPISODIC
_AGENT = MemorySource.AGENT

# Per-source collection tag (spec differentiator #3) — agent -> collection slug.
_COLLECTION_FOR_AGENT: dict[str, str] = {
    "claude_code": "claude-code",
    "codex": "codex",
    "kiro": "kiro",
}


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class HermesGuardError(RuntimeError):
    """Raised when a history operation targets the working/hermes database."""


def _assert_not_working_db(db_path: str) -> None:
    """
    Raise HermesGuardError if db_path resolves to the working store:
    - the MINTMORY_DB env value
    - the CLI default (~/.mintmory/memories.db)
    - any '*/hermes.db'

    The history DB MUST be a distinct file.
    """
    resolved = os.path.abspath(os.path.expanduser(db_path))

    # Check MINTMORY_DB env
    env_db = os.environ.get("MINTMORY_DB", "")
    if env_db:
        env_resolved = os.path.abspath(os.path.expanduser(env_db))
        if resolved == env_resolved:
            raise HermesGuardError(
                f"History DB path {resolved!r} resolves to the working store "
                f"(MINTMORY_DB={env_db!r}). Use a separate file."
            )

    # Check CLI default memories.db
    memories_db = os.path.abspath(os.path.expanduser("~/.mintmory/memories.db"))
    if resolved == memories_db:
        raise HermesGuardError(
            f"History DB path {resolved!r} resolves to the working store "
            "(~/.mintmory/memories.db). Use a separate file."
        )

    # Check hermes.db pattern
    basename = os.path.basename(resolved)
    if basename == "hermes.db":
        raise HermesGuardError(
            f"History DB path {resolved!r} ends in 'hermes.db'. "
            "The history DB must be a distinct file from the working store."
        )


# ---------------------------------------------------------------------------
# Adapter registry — LAZY imports (adapters may not exist yet)
# ---------------------------------------------------------------------------

# Populated on first use in _load_adapter()
_ADAPTERS: dict[str, object] = {}


def _load_adapter(name: str) -> object:
    """Lazily import and return the iter_sessions callable for the named adapter."""
    if name not in _ADAPTERS:
        if name == "claude_code":
            from mintmory.core.history.adapters import claude_code  # noqa: PLC0415

            _ADAPTERS[name] = claude_code.iter_sessions
        elif name == "codex":
            from mintmory.core.history.adapters import codex  # noqa: PLC0415

            _ADAPTERS[name] = codex.iter_sessions
        elif name == "kiro":
            from mintmory.core.history.adapters import kiro  # noqa: PLC0415

            _ADAPTERS[name] = kiro.iter_sessions
        else:
            raise ValueError(f"Unknown adapter: {name!r}")
    return _ADAPTERS[name]


# ---------------------------------------------------------------------------
# LLM budget — shared counter for --max-llm-calls
# ---------------------------------------------------------------------------


class LLMBudget:
    """Thread-safe counter limiting how many LLM distiller calls to make.

    max_calls=0 means unlimited.
    """

    def __init__(self, max_calls: int = 0) -> None:
        self._max = max_calls
        self._used = 0
        self._lock = threading.Lock()

    def request(self) -> bool:
        """Reserve one call.  Returns True if allowed, False if budget exhausted."""
        if self._max == 0:
            with self._lock:
                self._used += 1
            return True
        with self._lock:
            if self._used < self._max:
                self._used += 1
                return True
        return False

    @property
    def used(self) -> int:
        with self._lock:
            return self._used


# ---------------------------------------------------------------------------
# Segment writer helpers
# ---------------------------------------------------------------------------


def _seg_signature(seg_settings: Any) -> str:
    """SHA-256 of the segmentation settings tuple (target,min,max,gap,enabled)."""
    sig = (
        f"{seg_settings.target_turns}|{seg_settings.min_turns}"
        f"|{seg_settings.max_turns}|{seg_settings.gap_minutes}|{seg_settings.enabled}"
    )
    return hashlib.sha256(sig.encode()).hexdigest()[:16]


def _segment_content_hash(
    distiller_version: int,
    seg_sig: str,
    model: str,
    seg_turns: list[NormalizedTurn],
) -> str:
    """SHA-256 of (distiller_version|seg_sig|model|redacted_transcript)."""
    lines = [redact(t.text) for t in seg_turns]
    transcript = "\n".join(lines)
    raw = f"{distiller_version}|{seg_sig}|{model}|{transcript}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _find_by_segment_id(adapter_db: StorageAdapter, segment_id: str) -> str | None:
    """Query the DB for a memory whose metadata.segment_id matches. Returns id or None."""
    conn = adapter_db.connect()
    row = conn.execute(
        "SELECT id FROM memories WHERE json_extract(metadata, '$.segment_id') = ?",
        (segment_id,),
    ).fetchone()
    if row is None:
        return None
    return str(row["id"])


def _get_stored_content_hash(adapter_db: StorageAdapter, mem_id: str) -> str | None:
    """Return the content_hash stored in a memory's metadata, or None."""
    conn = adapter_db.connect()
    row = conn.execute("SELECT metadata FROM memories WHERE id = ?", (mem_id,)).fetchone()
    if row is None:
        return None
    try:
        meta: dict[str, Any] = json.loads(row["metadata"] or "{}")
        val = meta.get("content_hash")
        return str(val) if val is not None else None
    except (json.JSONDecodeError, TypeError):
        return None


def _parse_valid_from(ts: str | None) -> datetime | None:
    """Parse ISO-8601 UTC string to a naive datetime, or None."""
    if not ts:
        return None
    try:
        s = ts
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# SegWriteResult
# ---------------------------------------------------------------------------


@dataclass
class SegWriteResult:
    """Return value of write_session_segments."""

    written: int = 0
    updated: int = 0
    cache_hits: int = 0
    llm_calls: int = 0
    llm_fallbacks: int = 0


# ---------------------------------------------------------------------------
# write_session_segments  (§7 — the per-segment writer)
# ---------------------------------------------------------------------------


@dataclass
class _PreparedSegment:
    """A distilled segment ready to commit — produced WITHOUT touching the store."""

    segment_id: str
    existing_id: str | None  # id to UPDATE (from preloaded cache), else None -> ADD
    cache_hit: bool  # True -> row is unchanged; do not write, just keep its id
    content: str
    envelope: dict[str, Any]
    valid_from: datetime | None


@dataclass
class _PreparedSession:
    sid: str
    seg_count: int
    prepared: list[_PreparedSegment]
    counts: SegWriteResult  # llm_calls / cache_hits / fallbacks pre-counted


def _preload_segment_cache(store: StorageAdapter) -> dict[str, tuple[str, str]]:
    """Map segment_id -> (memory_id, content_hash) for all session_summary rows.

    Read ONCE on the main thread so the parallel distill phase needs no DB access.
    """
    out: dict[str, tuple[str, str]] = {}
    try:
        conn = store.connect()
        rows = conn.execute(
            "SELECT id, json_extract(metadata, '$.segment_id') AS sid, "
            "json_extract(metadata, '$.content_hash') AS h FROM memories "
            "WHERE json_extract(metadata, '$.record_type') = 'session_summary'"
        ).fetchall()
        for r in rows:
            if r["sid"]:
                out[str(r["sid"])] = (str(r["id"]), str(r["h"] or ""))
    except sqlite3.OperationalError:
        pass
    return out


def distill_session(
    session_summary: SessionSummary,
    segments: list[Segment],
    full_turns: list[NormalizedTurn],
    distiller: Any = None,
    *,
    budget: LLMBudget | None = None,
    llm_only_since: datetime | None = None,
    seg_settings: Any = None,
    cache: dict[str, tuple[str, str]] | None = None,
) -> _PreparedSession:
    """PURE (no store access): distill each segment into a row ready to commit.

    Uses `cache` (segment_id -> (id, content_hash)) to skip unchanged segments and
    to know which id to UPDATE. Safe to call concurrently across sessions — it does
    NOT read or write the database. Segments are distilled in order (prev_context
    chain). The store writes happen later in commit_distilled() on the main thread.
    """
    from mintmory.core.config import SegmentSettings  # noqa: PLC0415

    counts = SegWriteResult()
    sid = session_summary.session_id
    seg_count = len(segments)
    if seg_count == 0:
        return _PreparedSession(sid=sid, seg_count=0, prepared=[], counts=counts)

    cache = cache or {}
    session_ts_start = segments[0].ts_start
    session_ts_end = segments[-1].ts_end
    if seg_settings is None:
        seg_settings = SegmentSettings()
    seg_sig = _seg_signature(seg_settings)

    distiller_allowed = distiller is not None
    if distiller_allowed and llm_only_since is not None:
        sdt = _parse_valid_from(session_ts_start)
        if sdt is not None and sdt < llm_only_since:
            distiller_allowed = False

    prev_context = ""
    out: list[_PreparedSegment] = []

    for i, seg in enumerate(segments):
        segment_id = f"{sid}#{i}"
        # Invariant: NormalizedTurn.seq == 0-based list index (all adapters); the
        # slice is safe because turn_lo/turn_hi are seq values.
        seg_turns = full_turns[seg.turn_lo : seg.turn_hi + 1]

        target_version = 2 if distiller_allowed else 1
        content_hash = _segment_content_hash(
            target_version, seg_sig, session_summary.model, seg_turns
        )
        cached = cache.get(segment_id)
        if cached is not None and cached[1] == content_hash:
            counts.cache_hits += 1
            out.append(_PreparedSegment(segment_id, cached[0], True, "", {}, None))
            continue

        seg_summary = dataclasses.replace(
            session_summary,
            segment_index=i,
            segment_count=seg_count,
            turn_lo=seg.turn_lo,
            turn_hi=seg.turn_hi,
            ts_start=seg.ts_start,
            ts_end=seg.ts_end,
            session_ts_start=session_ts_start,
            session_ts_end=session_ts_end,
        )

        next_context = ""
        used_llm = False
        if distiller_allowed:
            if budget.request() if budget is not None else True:
                try:
                    seg_summary, next_context = distiller(seg_summary, seg_turns, prev_context)
                    used_llm = True
                    counts.llm_calls += 1
                except Exception:
                    log.warning(
                        "LLM distiller failed for segment %s, using deterministic", segment_id
                    )
                    seg_summary = distill_segment_deterministic(seg_summary, seg_turns)
                    counts.llm_fallbacks += 1
            else:
                seg_summary = distill_segment_deterministic(seg_summary, seg_turns)
                counts.llm_fallbacks += 1
        else:
            seg_summary = distill_segment_deterministic(seg_summary, seg_turns)

        actual_version = seg_summary.distiller_version
        if actual_version != target_version:
            content_hash = _segment_content_hash(
                actual_version, seg_sig, session_summary.model, seg_turns
            )

        clean_title = redact(seg_summary.title)
        clean_summary = redact(seg_summary.summary_text)
        content = clean_summary or clean_title or "(no summary)"

        collection = _COLLECTION_FOR_AGENT.get(session_summary.agent, session_summary.agent)
        envelope: dict[str, Any] = {
            "record_type": "session_summary",
            "collection": collection,
            "agent": session_summary.agent,
            "repo": session_summary.repo,
            "repo_path": session_summary.repo_path,
            "branch": session_summary.branch,
            "kind": seg_summary.kind,
            "session_id": sid,
            "ts_start": seg.ts_start,
            "ts_end": seg.ts_end,
            "turn_count": seg.turn_hi - seg.turn_lo + 1,
            "tools_used": session_summary.tools_used,
            "source_path": session_summary.source_path,
            "source_offset": session_summary.source_offset,
            "model": session_summary.model,
            "distiller_version": actual_version,
            "segment_id": segment_id,
            "segment_index": i,
            "segment_count": seg_count,
            "turn_lo": seg.turn_lo,
            "turn_hi": seg.turn_hi,
            "title": clean_title,
            "outcome": redact(seg_summary.outcome) if used_llm else "",
            "session_ts_start": session_ts_start,
            "session_ts_end": session_ts_end,
            "content_hash": content_hash,
            "seg_signature": seg_sig,
        }
        out.append(
            _PreparedSegment(
                segment_id=segment_id,
                existing_id=cached[0] if cached is not None else None,
                cache_hit=False,
                content=content,
                envelope=envelope,
                valid_from=_parse_valid_from(seg.ts_start),
            )
        )
        prev_context = next_context

    return _PreparedSession(sid=sid, seg_count=seg_count, prepared=out, counts=counts)


def commit_distilled(
    store: StorageAdapter, ps: _PreparedSession
) -> tuple[SegWriteResult, list[str]]:
    """SERIAL store writes for one prepared session (run on the main thread only).

    Upserts each non-cache-hit segment by segment_id, then orphan-sweeps. Returns
    (result, written_ids) — written_ids includes cache-hit ids (for the manifest).
    """
    result = ps.counts
    written_ids: list[str] = []
    if ps.seg_count == 0:
        return result, written_ids
    for p in ps.prepared:
        if p.cache_hit:
            if p.existing_id:
                written_ids.append(p.existing_id)
            continue
        if p.existing_id is not None:
            store.update_memory(
                p.existing_id, content=p.content, metadata=p.envelope, valid_from=p.valid_from
            )
            result.updated += 1
            written_ids.append(p.existing_id)
        else:
            record = store.add_memory(
                content=p.content,
                category=_EPISODIC,
                source=_AGENT,
                valid_from=p.valid_from,
                metadata=p.envelope,
            )
            result.written += 1
            written_ids.append(record.id)
    _sweep_orphans(store, ps.sid, ps.seg_count)
    return result, written_ids


def write_session_segments(
    store: StorageAdapter,
    session_summary: SessionSummary,
    segments: list[Segment],
    full_turns: list[NormalizedTurn],
    distiller: Any = None,
    *,
    budget: LLMBudget | None = None,
    now: datetime | None = None,
    llm_only_since: datetime | None = None,
    seg_settings: Any = None,
) -> SegWriteResult:
    """Single-call writer (distill + commit) — backward-compatible serial path.

    Preloads the cache, distills (pure), then commits serially. Concurrent callers
    MUST instead use distill_session() in threads + commit_distilled() on the main
    thread (see backfill/sync) — never call this from multiple threads on one store.
    """
    if not segments:
        return SegWriteResult()
    cache = _preload_segment_cache(store)
    ps = distill_session(
        session_summary,
        segments,
        full_turns,
        distiller,
        budget=budget,
        llm_only_since=llm_only_since,
        seg_settings=seg_settings,
        cache=cache,
    )
    result, _ids = commit_distilled(store, ps)
    return result


def _sweep_orphans(store: StorageAdapter, session_id: str, current_count: int) -> None:
    """Archive memory rows for session_id where segment_index >= current_count."""
    conn = store.connect()
    orphan_rows = conn.execute(
        "SELECT id FROM memories "
        "WHERE json_extract(metadata, '$.session_id') = ? "
        "  AND json_extract(metadata, '$.segment_index') >= ? "
        "  AND json_extract(metadata, '$.segment_id') IS NOT NULL "
        "  AND is_archived = 0",
        (session_id, current_count),
    ).fetchall()
    for row in orphan_rows:
        store.archive_memory(str(row["id"]))


# ---------------------------------------------------------------------------
# Writer (legacy single-segment — kept for compatibility)
# ---------------------------------------------------------------------------


def write_session(adapter_db: StorageAdapter, summary: SessionSummary) -> str | None:
    """
    Redact title+summary_text; build a MemoryRecord and write it.

    The record has:
      content   = summary_text (or title if summary_text is empty)
      category  = EPISODIC
      source    = AGENT
      valid_from = ts_start
      metadata  = envelope (record_type, agent, repo, ..., session_id, ...)

    Idempotent on session_id: if a memory with metadata.session_id exists,
    update_memory; else add_memory. Returns memory id (or None if both
    summary_text and title are empty).
    """
    clean_title = redact(summary.title)
    clean_summary = redact(summary.summary_text)

    content = clean_summary or clean_title
    if not content:
        return None

    envelope: dict[str, object] = {
        "record_type": "session_summary",
        "collection": _COLLECTION_FOR_AGENT.get(summary.agent, summary.agent),
        "agent": summary.agent,
        "repo": summary.repo,
        "repo_path": summary.repo_path,
        "branch": summary.branch,
        "kind": summary.kind,
        "session_id": summary.session_id,
        "ts_start": summary.ts_start,
        "ts_end": summary.ts_end,
        "turn_count": summary.turn_count,
        "tools_used": summary.tools_used,
        "source_path": summary.source_path,
        "source_offset": summary.source_offset,
        "model": summary.model,
        "distiller_version": summary.distiller_version,
    }

    # Parse valid_from from ts_start
    valid_from: datetime | None = None
    try:
        ts = summary.ts_start
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        valid_from = datetime.fromisoformat(ts).replace(tzinfo=None)
    except (ValueError, AttributeError):
        valid_from = None

    # Check idempotency: look for existing memory with this session_id
    existing_id = _find_by_session_id(adapter_db, summary.session_id)

    if existing_id is not None:
        adapter_db.update_memory(
            existing_id,
            content=content,
            metadata=envelope,
            valid_from=valid_from,
        )
        return existing_id
    else:
        record = adapter_db.add_memory(
            content=content,
            category=_EPISODIC,
            source=_AGENT,
            valid_from=valid_from,
            metadata=envelope,
        )
        return record.id


def _find_by_session_id(adapter_db: StorageAdapter, session_id: str) -> str | None:
    """Query the DB for a memory whose metadata.session_id matches. Returns id or None."""
    conn = adapter_db.connect()
    row = conn.execute(
        "SELECT id FROM memories WHERE json_extract(metadata, '$.session_id') = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return str(row["id"])


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class IngestReport:
    """Summary of a backfill or sync run."""

    scanned: int = 0
    written: int = 0
    updated: int = 0
    skipped: int = 0
    redacted_hits: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    # Phase-2 segment fields
    segments_written: int = 0
    llm_calls: int = 0
    llm_cache_hits: int = 0
    llm_fallbacks: int = 0
    llm_calls_deferred: int = 0
    errors: int = 0  # sessions whose distill phase raised (never silently dropped)


# ---------------------------------------------------------------------------
# Manifest helpers (dedup by path+content_hash+mtime)
# ---------------------------------------------------------------------------


def _file_hash(path: str) -> str | None:
    """Return SHA-256 hex digest of a file's content, or None on error."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:  # noqa: PTH123
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _file_mtime(path: str) -> float:
    """Return mtime of a file, or 0.0 on error."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _file_size(path: str) -> int:
    """Return size of a file in bytes, or 0 on error."""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _manifest_unchanged(adapter_db: StorageAdapter, path: str, collection: str) -> bool:  # noqa: ARG001
    """
    Return True if the manifest entry for path indicates the file is unchanged
    (same size, mtime, and content_hash).
    """
    row = adapter_db.manifest_get(path)
    if row is None:
        return False
    current_mtime = _file_mtime(path)
    current_size = _file_size(path)
    if row["mtime"] != current_mtime or row["size"] != current_size:
        return False
    current_hash = _file_hash(path)
    stored_hash = row["content_hash"]
    return not (stored_hash and current_hash and stored_hash != current_hash)


def _manifest_update(
    adapter_db: StorageAdapter,
    path: str,
    collection: str,
    memory_ids: list[str] | None = None,
) -> None:
    """Update the manifest entry for a processed file."""
    adapter_db.manifest_upsert(
        path=path,
        collection=collection,
        size=_file_size(path),
        mtime=_file_mtime(path),
        online_only=False,
        index_mode="content",
        memory_ids=memory_ids or [],
        content_hash=_file_hash(path),
    )


# ---------------------------------------------------------------------------
# Open / initialise the dedicated history DB
# ---------------------------------------------------------------------------


def _open_history_db(db_path: str) -> StorageAdapter:
    """Expand, create parent dirs, initialise schema, set 0o600 permissions."""
    expanded = os.path.expanduser(db_path)
    abs_path = os.path.abspath(expanded)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    store = StorageAdapter(abs_path)
    store.initialise()
    # Secure permissions (best-effort; some filesystems don't support chmod)
    with contextlib.suppress(OSError):
        os.chmod(abs_path, 0o600)
    return store


# ---------------------------------------------------------------------------
# Source names
# ---------------------------------------------------------------------------

_ALL_SOURCES = ("claude_code", "codex", "kiro")


# ---------------------------------------------------------------------------
# _should_redistill: re-distill trigger check
# ---------------------------------------------------------------------------


def _should_redistill(
    store: StorageAdapter,
    session_id: str,
    target_distiller_version: int,
    seg_sig: str,
) -> bool:
    """Return True if any segment for this session needs re-distillation.

    Triggers:
    - No existing segments for this session
    - Any segment has distiller_version < target
    - Any segment has a different seg_signature
    """
    conn = store.connect()
    rows = conn.execute(
        "SELECT metadata FROM memories "
        "WHERE json_extract(metadata, '$.session_id') = ? "
        "  AND json_extract(metadata, '$.segment_id') IS NOT NULL "
        "  AND is_archived = 0",
        (session_id,),
    ).fetchall()

    if not rows:
        return True

    for row in rows:
        try:
            meta = json.loads(row["metadata"] or "{}")
        except (json.JSONDecodeError, TypeError):
            return True
        if meta.get("distiller_version", 0) < target_distiller_version:
            return True
        if meta.get("seg_signature", "") != seg_sig:
            return True
    return False


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------


def _prepare_session(
    args: tuple[SessionSummary, list[NormalizedTurn]],
    distiller: Any,
    budget: LLMBudget | None,
    llm_only_since: datetime | None,
    seg_settings: Any,
    cache: dict[str, tuple[str, str]],
) -> tuple[_PreparedSession, str]:
    """PURE (no store access): segment + distill one session for the parallel phase.

    Safe to run in a worker thread — all DB writes happen later in
    commit_distilled() on the main thread.
    """
    from mintmory.core.history.segment import segment_turns  # noqa: PLC0415

    summary, turns = args
    segs = segment_turns(turns, seg_settings)
    ps = distill_session(
        summary,
        segs,
        turns,
        distiller,
        budget=budget,
        llm_only_since=llm_only_since,
        seg_settings=seg_settings,
        cache=cache,
    )
    return ps, summary.source_path


def backfill(
    db_path: str = DEFAULT_HISTORY_DB,
    sources: list[str] | None = None,
    *,
    limit: int = 0,
    seg_settings: Any = None,
    distiller: Any = None,
    budget: LLMBudget | None = None,
    llm_only_since: datetime | None = None,
    max_concurrency: int = 1,
) -> IngestReport:
    """
    Full ingest of all sessions from the specified adapter sources.

    _assert_not_working_db ensures we never write to the working store.
    Opens/initialises the dedicated StorageAdapter.
    For each source adapter: iter_sessions -> segment -> distill -> write_session_segments.
    Records index_manifest rows to skip unchanged files on re-run.
    limit > 0 caps sessions per source (for smoke-testing).
    """
    from mintmory.core.config import SegmentSettings  # noqa: PLC0415

    _assert_not_working_db(db_path)
    store = _open_history_db(db_path)

    if seg_settings is None:
        seg_settings = SegmentSettings()

    active_sources = sources if sources is not None else list(_ALL_SOURCES)
    report = IngestReport()

    for source_name in active_sources:
        try:
            iter_fn = _load_adapter(source_name)
        except (ImportError, ValueError):
            continue

        by_source_count = 0
        # Collect all (summary, turns) for this source first (for fan-out)
        sessions_to_process: list[tuple[SessionSummary, list[NormalizedTurn]]] = []

        for session_idx, (summary, turns) in enumerate(iter_fn()):  # type: ignore[operator]
            report.scanned += 1
            sessions_to_process.append((summary, turns))
            if limit > 0 and session_idx + 1 >= limit:
                break

        # Preload the content-hash cache ONCE so the distill phase needs no DB access.
        cache = _preload_segment_cache(store)

        # Parallel + commit-as-completed (INVARIANT: all store writes on main thread only).
        prep_args = (distiller, budget, llm_only_since, seg_settings, cache)
        if max_concurrency > 1 and len(sessions_to_process) > 1:
            with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
                futures = {
                    executor.submit(_prepare_session, s, *prep_args): s for s in sessions_to_process
                }
                for future in as_completed(futures):
                    try:
                        ps, source_path = future.result()
                    except Exception as exc:  # never silently drop a session
                        report.errors += 1
                        log.warning("Session distill failed: %s", exc)
                        continue
                    # SERIAL commit on the main thread — never in a worker.
                    seg_result, written_ids = commit_distilled(store, ps)
                    _accumulate_seg_result(report, seg_result)
                    by_source_count += 1
                    if source_path:
                        _manifest_update(store, source_path, source_name, memory_ids=written_ids)
        else:
            for s in sessions_to_process:
                try:
                    ps, source_path = _prepare_session(s, *prep_args)
                except Exception as exc:
                    report.errors += 1
                    log.warning("Session distill failed: %s", exc)
                    continue
                seg_result, written_ids = commit_distilled(store, ps)
                _accumulate_seg_result(report, seg_result)
                by_source_count += 1
                if source_path:
                    _manifest_update(store, source_path, source_name, memory_ids=written_ids)

        report.by_source[source_name] = by_source_count

    return report


def _accumulate_seg_result(report: IngestReport, seg_result: SegWriteResult) -> None:
    """Merge a SegWriteResult into the IngestReport."""
    report.segments_written += seg_result.written + seg_result.updated
    report.written += seg_result.written
    report.updated += seg_result.updated
    report.llm_calls += seg_result.llm_calls
    report.llm_cache_hits += seg_result.cache_hits
    report.llm_fallbacks += seg_result.llm_fallbacks


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


def sync(
    db_path: str = DEFAULT_HISTORY_DB,
    sources: list[str] | None = None,
    *,
    seg_settings: Any = None,
    distiller: Any = None,
    budget: LLMBudget | None = None,
    llm_only_since: datetime | None = None,
    max_concurrency: int = 1,
) -> IngestReport:
    """
    Like backfill but skips sessions whose source file is unchanged per
    index_manifest (size+mtime+content_hash); only (re)distills changed/new files.

    Re-distill triggers: file changed (manifest) OR stored distiller_version < target
    OR stored seg_signature differs.
    """
    from mintmory.core.config import SegmentSettings  # noqa: PLC0415

    _assert_not_working_db(db_path)
    store = _open_history_db(db_path)

    if seg_settings is None:
        seg_settings = SegmentSettings()

    # Determine target distiller version for re-distill check
    target_distiller_version = 2 if distiller is not None else 1
    current_seg_sig = _seg_signature(seg_settings)

    active_sources = sources if sources is not None else list(_ALL_SOURCES)
    report = IngestReport()

    for source_name in active_sources:
        try:
            iter_fn = _load_adapter(source_name)
        except (ImportError, ValueError):
            continue

        by_source_count = 0
        seen_paths: set[str] = set()
        sessions_to_process: list[tuple[SessionSummary, list[NormalizedTurn]]] = []

        for summary, turns in iter_fn():  # type: ignore[operator]
            report.scanned += 1

            source_path = summary.source_path

            # Skip unchanged files (manifest dedup) — but still check distiller triggers
            if source_path and source_path not in seen_paths:
                seen_paths.add(source_path)
                if _manifest_unchanged(store, source_path, source_name) and not _should_redistill(
                    store, summary.session_id, target_distiller_version, current_seg_sig
                ):
                    report.skipped += 1
                    continue

            sessions_to_process.append((summary, turns))

        cache = _preload_segment_cache(store)

        # Parallel + commit-as-completed (INVARIANT: all store writes on main thread only).
        prep_args = (distiller, budget, llm_only_since, seg_settings, cache)
        if max_concurrency > 1 and len(sessions_to_process) > 1:
            with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
                futures = {
                    executor.submit(_prepare_session, s, *prep_args): s for s in sessions_to_process
                }
                for future in as_completed(futures):
                    try:
                        ps, source_path = future.result()
                    except Exception as exc:
                        report.errors += 1
                        log.warning("Session sync distill failed: %s", exc)
                        continue
                    # SERIAL commit on the main thread — never in a worker.
                    seg_result, written_ids = commit_distilled(store, ps)
                    _accumulate_seg_result(report, seg_result)
                    by_source_count += 1
                    if source_path:
                        _manifest_update(store, source_path, source_name, memory_ids=written_ids)
        else:
            for s in sessions_to_process:
                try:
                    ps, source_path = _prepare_session(s, *prep_args)
                except Exception as exc:
                    report.errors += 1
                    log.warning("Session sync distill failed: %s", exc)
                    continue
                seg_result, written_ids = commit_distilled(store, ps)
                _accumulate_seg_result(report, seg_result)
                by_source_count += 1
                if source_path:
                    _manifest_update(store, source_path, source_name, memory_ids=written_ids)

        report.by_source[source_name] = by_source_count

    return report
