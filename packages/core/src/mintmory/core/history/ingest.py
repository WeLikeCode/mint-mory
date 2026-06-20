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
import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from mintmory.core.history.distill import distill
from mintmory.core.history.models import SessionSummary
from mintmory.core.history.redact import redact
from mintmory.core.storage import StorageAdapter
from mintmory.core.types import MemoryCategory, MemorySource

if TYPE_CHECKING:
    pass

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
# Writer
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


def _manifest_update(adapter_db: StorageAdapter, path: str, collection: str) -> None:
    """Update the manifest entry for a processed file."""
    adapter_db.manifest_upsert(
        path=path,
        collection=collection,
        size=_file_size(path),
        mtime=_file_mtime(path),
        online_only=False,
        index_mode="content",
        memory_ids=[],
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
# backfill
# ---------------------------------------------------------------------------


def backfill(
    db_path: str = DEFAULT_HISTORY_DB,
    sources: list[str] | None = None,
    *,
    limit: int = 0,
) -> IngestReport:
    """
    Full ingest of all sessions from the specified adapter sources.

    _assert_not_working_db ensures we never write to the working store.
    Opens/initialises the dedicated StorageAdapter.
    For each source adapter: iter_sessions -> distill -> write_session.
    Records index_manifest rows to skip unchanged files on re-run.
    limit > 0 caps sessions per source (for smoke-testing).
    """
    _assert_not_working_db(db_path)
    store = _open_history_db(db_path)

    active_sources = sources if sources is not None else list(_ALL_SOURCES)
    report = IngestReport()

    for source_name in active_sources:
        try:
            iter_fn = _load_adapter(source_name)
        except (ImportError, ValueError):
            continue

        by_source_count = 0

        for session_idx, (summary, turns) in enumerate(iter_fn()):  # type: ignore[operator]
            report.scanned += 1

            # Track manifest for source files (dedup on re-run via path tracking)
            source_path = summary.source_path
            if source_path:
                _manifest_update(store, source_path, source_name)

            distilled = distill(summary, turns)
            mem_id = write_session(store, distilled)

            if mem_id is not None:
                report.written += 1
            by_source_count += 1

            if limit > 0 and session_idx + 1 >= limit:
                break

        report.by_source[source_name] = by_source_count

    return report


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


def sync(
    db_path: str = DEFAULT_HISTORY_DB,
    sources: list[str] | None = None,
) -> IngestReport:
    """
    Like backfill but skips sessions whose source file is unchanged per
    index_manifest (size+mtime+content_hash); only (re)distills changed/new files.
    """
    _assert_not_working_db(db_path)
    store = _open_history_db(db_path)

    active_sources = sources if sources is not None else list(_ALL_SOURCES)
    report = IngestReport()

    for source_name in active_sources:
        try:
            iter_fn = _load_adapter(source_name)
        except (ImportError, ValueError):
            continue

        by_source_count = 0
        seen_paths: set[str] = set()

        for summary, turns in iter_fn():  # type: ignore[operator]
            report.scanned += 1

            source_path = summary.source_path

            # Skip unchanged files (manifest dedup)
            if source_path and source_path not in seen_paths:
                if _manifest_unchanged(store, source_path, source_name):
                    report.skipped += 1
                    seen_paths.add(source_path)
                    continue
                seen_paths.add(source_path)

            distilled = distill(summary, turns)
            mem_id = write_session(store, distilled)

            if mem_id is not None:
                by_source_count += 1
                report.written += 1

            # Update manifest after processing
            if source_path:
                _manifest_update(store, source_path, source_name)

        report.by_source[source_name] = by_source_count

    return report
