"""
Tests for the StorageBackend port, StorageSettings, build_storage() factory,
and the new methods absorbed into SqliteBackend.

These are ADDITIVE tests — they do not modify existing tests.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from mintmory.core.embedder import FakeEmbedder
from mintmory.core.ports import StorageBackend
from mintmory.core.storage import SqliteBackend, StorageAdapter
from mintmory.core.storage_factory import build_storage

# ---------------------------------------------------------------------------
# Alias back-compat
# ---------------------------------------------------------------------------


def test_storage_adapter_alias_is_sqlite_backend() -> None:
    """StorageAdapter must remain a valid alias for SqliteBackend."""
    assert StorageAdapter is SqliteBackend


# ---------------------------------------------------------------------------
# build_storage() factory
# ---------------------------------------------------------------------------


def test_build_storage_returns_sqlite_backend_by_default(tmp_path: Path) -> None:
    """build_storage() with no args returns a SqliteBackend instance."""
    db = tmp_path / "test.db"
    env = {"MINTMORY_DB": str(db)}
    old = {k: os.environ.pop(k, None) for k in env}
    os.environ.update(env)
    try:
        store = build_storage()
        assert isinstance(store, SqliteBackend)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_build_storage_honors_backend_env(tmp_path: Path) -> None:
    """build_storage() with MINTMORY_STORAGE_BACKEND=sqlite still gives SqliteBackend."""
    db = tmp_path / "test2.db"
    env = {"MINTMORY_DB": str(db), "MINTMORY_STORAGE_BACKEND": "sqlite"}
    old = {k: os.environ.pop(k, None) for k in env}
    os.environ.update(env)
    try:
        store = build_storage()
        assert isinstance(store, SqliteBackend)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_build_storage_postgres_raises_value_error_without_dsn() -> None:
    """Postgres backend without a DSN raises ValueError (Phase 2: backend implemented)."""
    from mintmory.core.config import StorageBackendEnum, StorageSettings

    s = StorageSettings(backend=StorageBackendEnum.POSTGRES)  # no dsn
    with pytest.raises(ValueError, match="DSN"):
        build_storage(s)


def test_build_storage_with_embedder(tmp_path: Path) -> None:
    """build_storage() passes the embedder through to SqliteBackend."""
    db = tmp_path / "emb.db"
    env = {"MINTMORY_DB": str(db)}
    old = {k: os.environ.pop(k, None) for k in env}
    os.environ.update(env)
    try:
        emb = FakeEmbedder()
        store = build_storage(embedder=emb)
        assert store.embedder is emb
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_build_storage_creates_parent_dir(tmp_path: Path) -> None:
    """build_storage() must create the parent directory if it doesn't exist."""
    nested = tmp_path / "a" / "b" / "c" / "memories.db"
    assert not nested.parent.exists()
    env = {"MINTMORY_DB": str(nested)}
    old = {k: os.environ.pop(k, None) for k in env}
    os.environ.update(env)
    try:
        build_storage()
        assert nested.parent.exists()
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------------------
# StorageBackend Protocol conformance
# ---------------------------------------------------------------------------


def test_sqlite_backend_satisfies_protocol() -> None:
    """isinstance check against the runtime_checkable Protocol must pass."""
    store = SqliteBackend(":memory:")
    assert isinstance(store, StorageBackend)


# ---------------------------------------------------------------------------
# ping()
# ---------------------------------------------------------------------------


def test_ping_true_on_live_db(tmp_path: Path) -> None:
    """ping() returns True when the DB is accessible."""
    store = SqliteBackend(str(tmp_path / "ping.db"))
    store.initialise()
    assert store.ping() is True


# ---------------------------------------------------------------------------
# manifest_get returns ManifestEntry (TypedDict)
# ---------------------------------------------------------------------------


def test_manifest_get_returns_manifest_entry(tmp_path: Path) -> None:
    """manifest_get must return a ManifestEntry TypedDict (dict with known keys)."""
    import json

    store = SqliteBackend(str(tmp_path / "manifest.db"))
    store.initialise()

    # Insert a manifest row via upsert. index_mode must be one of the schema-allowed
    # values: 'metadata', 'content', or 'vision'.
    store.manifest_upsert(
        path="/tmp/foo.txt",
        collection="default",
        size=100,
        mtime=1234567890.0,
        content_hash="abc123",
        index_mode="content",
        memory_ids=["m1", "m2"],
        online_only=False,
    )

    entry = store.manifest_get("/tmp/foo.txt")
    assert entry is not None
    # Must be a dict (TypedDict is a plain dict at runtime)
    assert isinstance(entry, dict)
    # Check key fields exist and are correct
    assert entry["path"] == "/tmp/foo.txt"
    assert entry["collection"] == "default"
    assert entry["content_hash"] == "abc123"
    # memory_ids is stored and returned as a JSON-encoded string (not decoded)
    assert isinstance(entry["memory_ids"], str)
    decoded = json.loads(entry["memory_ids"])
    assert "m1" in decoded


def test_manifest_get_returns_none_for_missing(tmp_path: Path) -> None:
    """manifest_get returns None for an unknown path."""
    store = SqliteBackend(str(tmp_path / "manifest2.db"))
    store.initialise()
    assert store.manifest_get("/nonexistent/path.txt") is None


# ---------------------------------------------------------------------------
# memory_exists_with_content()
# ---------------------------------------------------------------------------


def test_memory_exists_with_content_true(tmp_path: Path) -> None:
    """memory_exists_with_content returns True when content exists."""
    store = SqliteBackend(str(tmp_path / "exist.db"))
    store.initialise()
    store.add_memory(content="hello world", category="fact", source="agent")
    assert store.memory_exists_with_content("hello world") is True


def test_memory_exists_with_content_false(tmp_path: Path) -> None:
    """memory_exists_with_content returns False for absent content."""
    store = SqliteBackend(str(tmp_path / "exist2.db"))
    store.initialise()
    assert store.memory_exists_with_content("this does not exist") is False


def test_memory_exists_matches_direct_query(tmp_path: Path) -> None:
    """memory_exists_with_content result must match a direct SQL SELECT 1 query."""
    store = SqliteBackend(str(tmp_path / "exist3.db"))
    store.initialise()
    content = "unique content for direct comparison"
    store.add_memory(content=content, category="fact", source="agent")

    # Direct query result
    conn = store.connect()
    row = conn.execute("SELECT 1 FROM memories WHERE content = ? LIMIT 1", (content,)).fetchone()
    direct = row is not None

    assert store.memory_exists_with_content(content) == direct


# ---------------------------------------------------------------------------
# vector_search_available() — public method
# ---------------------------------------------------------------------------


def test_vector_search_available_is_public(tmp_path: Path) -> None:
    """vector_search_available must be callable as a public method."""
    store = SqliteBackend(str(tmp_path / "vec.db"))
    store.initialise()
    # Return value is bool; just ensure it doesn't raise and is bool
    result = store.vector_search_available()
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# StorageSettings env aliases
# ---------------------------------------------------------------------------


def test_storage_settings_legacy_timeout_alias() -> None:
    """MINTMORY_SQLITE_BUSY_TIMEOUT_MS must be honoured as legacy alias."""
    from mintmory.core.config import StorageSettings

    old = os.environ.pop("MINTMORY_SQLITE_BUSY_TIMEOUT_MS", None)
    os.environ["MINTMORY_SQLITE_BUSY_TIMEOUT_MS"] = "9999"
    try:
        s = StorageSettings()
        assert s.busy_timeout_ms == 9999
    finally:
        os.environ.pop("MINTMORY_SQLITE_BUSY_TIMEOUT_MS", None)
        if old is not None:
            os.environ["MINTMORY_SQLITE_BUSY_TIMEOUT_MS"] = old


def test_storage_settings_primary_timeout_wins_over_legacy() -> None:
    """Primary env var MINTMORY_STORAGE_BUSY_TIMEOUT_MS takes precedence."""
    from mintmory.core.config import StorageSettings

    old_primary = os.environ.pop("MINTMORY_STORAGE_BUSY_TIMEOUT_MS", None)
    old_legacy = os.environ.pop("MINTMORY_SQLITE_BUSY_TIMEOUT_MS", None)
    os.environ["MINTMORY_STORAGE_BUSY_TIMEOUT_MS"] = "7777"
    os.environ["MINTMORY_SQLITE_BUSY_TIMEOUT_MS"] = "3333"
    try:
        s = StorageSettings()
        assert s.busy_timeout_ms == 7777
    finally:
        os.environ.pop("MINTMORY_STORAGE_BUSY_TIMEOUT_MS", None)
        os.environ.pop("MINTMORY_SQLITE_BUSY_TIMEOUT_MS", None)
        if old_primary is not None:
            os.environ["MINTMORY_STORAGE_BUSY_TIMEOUT_MS"] = old_primary
        if old_legacy is not None:
            os.environ["MINTMORY_SQLITE_BUSY_TIMEOUT_MS"] = old_legacy


# ---------------------------------------------------------------------------
# anchor_candidates — public (was _anchor_candidates)
# ---------------------------------------------------------------------------


def test_anchor_candidates_is_public(tmp_path: Path) -> None:
    """anchor_candidates must be callable as a public method (no leading underscore)."""
    store = SqliteBackend(str(tmp_path / "anchor.db"), embedder=FakeEmbedder())
    store.initialise()
    store.add_memory(content="Python is a programming language", category="fact", source="agent")
    # Should not raise; returns list of (score, MemoryRecord)
    results = store.anchor_candidates("Python", limit=3)
    assert isinstance(results, list)
