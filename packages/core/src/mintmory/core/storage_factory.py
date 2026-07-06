"""
``build_storage()`` factory — resolves ``StorageSettings`` into a concrete
``StorageBackend`` instance.

Only the SQLite backend is implemented in Phase 0.  The Postgres branch raises
``NotImplementedError`` with a clear message so callers see it immediately.

Call sites:
  - ``api/app.py`` lifespan:          ``build_storage()``          (no embedder)
  - ``mcp/server.py`` lazy init:      ``build_storage()``          (no embedder)
  - ``cli/main.py`` ``_get_store``:   ``build_storage(embedder=…)``(with embedder)

History construction sites (``history/ingest.py``, ``history/query.py``,
``cli/main.py:_get_history_store``) construct ``SqliteBackend`` explicitly — they
are SQLite-by-design (Hermes guard, ``0o600``, rowid semantics).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mintmory.core.config import StorageSettings
    from mintmory.core.embedder import EmbedderProtocol
    from mintmory.core.ports import StorageBackend

_DEFAULT_DB = str(Path.home() / ".mintmory" / "memories.db")


def build_storage(
    settings: StorageSettings | None = None,
    *,
    embedder: EmbedderProtocol | None = None,
) -> StorageBackend:
    """Construct and return a ``StorageBackend`` for the given settings.

    Args:
        settings: a ``StorageSettings`` instance (or ``None`` to read from env).
        embedder: optional embedder (CLI passes one; API/MCP pass ``None``).

    Returns:
        An uninitialised ``StorageBackend``.  The caller is responsible for
        calling ``.initialise()`` and (for the API) creating the parent directory.

    Raises:
        NotImplementedError: when ``settings.backend == "postgres"`` (Phase 2).
    """
    from mintmory.core.config import StorageBackendEnum, StorageSettings  # noqa: PLC0415
    from mintmory.core.storage import SqliteBackend  # noqa: PLC0415

    s: StorageSettings = settings if settings is not None else StorageSettings()

    if s.backend is StorageBackendEnum.SQLITE:
        # Resolve db_path: StorageSettings.db_path (MINTMORY_STORAGE_DB_PATH) >
        # MINTMORY_DB env var > ~/.mintmory/memories.db
        db_path = s.db_path or os.environ.get("MINTMORY_DB", _DEFAULT_DB)
        # Mirror the mkdir the callers used to do inline.
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return SqliteBackend(
            db_path,
            embedder=embedder,
            busy_timeout_ms=s.busy_timeout_ms,
        )

    if s.backend is StorageBackendEnum.POSTGRES:
        from mintmory.core.storage_postgres import PostgresBackend  # noqa: PLC0415

        dsn = s.dsn or os.environ.get("MINTMORY_STORAGE_DSN", "")
        if not dsn:
            raise ValueError(
                "PostgresBackend requires a DSN.  Set MINTMORY_STORAGE_DSN or "
                "StorageSettings(dsn=...) / MINTMORY_STORAGE_DSN env var."
            )
        return PostgresBackend(
            dsn=dsn,
            embedder=embedder,
            pool_min=s.pool_min,
            pool_max=s.pool_max,
        )

    raise ValueError(f"unknown storage backend {s.backend!r}")
