"""
Parametrised ``backend`` fixture for the MintMory storage-backend conformance suite.

Backends
--------
sqlite  — always available; backed by a real temp file (NOT ``:memory:``) so that
          ``BackendHandle.new_connection()`` can open a second connection to the same
          database and observe committed writes. A deterministic ``HashingEmbedder``
          (dim=64, fast for tests) is attached so the vector search phase runs
          reproducibly without any network or model dependency.

postgres — enabled ONLY when ``MINTMORY_TEST_PG_DSN`` is set in the environment AND
           a ``PostgresBackend`` is importable (Phase 2, not yet implemented). Today
           this parameter auto-skips cleanly via ``pytest.mark.skipif`` — the harness
           is "wired but empty" for Postgres until Phase 2 lands.

CI note (no empty PG job today)
--------------------------------
The Postgres conformance leg (``pgvector/pgvector:pg16`` service container +
``MINTMORY_TEST_PG_DSN``) is added to the CI matrix in Phase 2, alongside the
``PostgresBackend`` implementation.  Standing up an empty PG service container in
Phase 1 would cost real CI minutes for zero backend code — it is deliberate waste
deferred to Phase 2.

Markers
-------
``pytest.mark.vector``  — test requires ``backend.vector_search_available() == True``
                          (embedder attached + sqlite-vec/pgvector loaded). Tests
                          call ``pytest.skip()`` at runtime if the capability is
                          absent rather than failing.
``pytest.mark.trigram`` — test requires trigram substring-search capability (FTS5
                          trigram tokenizer for SQLite; pg_trgm for Postgres). Tests
                          probe at runtime and ``pytest.skip()`` if absent.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from mintmory.core.config import StorageSettings
from mintmory.core.embedder import HashingEmbedder
from mintmory.core.ports import StorageBackend
from mintmory.core.storage_factory import build_storage

# BackendHandle lives in this package's __init__.py so both conftest.py and test
# modules can import it without touching production code.
from conformance import BackendHandle

# ---------------------------------------------------------------------------
# Postgres availability probe (evaluated at import / collection time)
# ---------------------------------------------------------------------------


def _postgres_available() -> bool:
    """Return True iff a Postgres conformance run can proceed.

    Phase 1 invariant: always False (PostgresBackend not yet implemented).
    Phase 2 will flip this to True when MINTMORY_TEST_PG_DSN is set.
    """
    if not os.environ.get("MINTMORY_TEST_PG_DSN"):
        return False
    try:
        import mintmory.core.storage_postgres  # noqa: F401

        return True
    except ImportError:
        return False


_PG_SKIP_REASON = (
    "Postgres conformance leg requires MINTMORY_TEST_PG_DSN to be set in the "
    "environment AND PostgresBackend to be importable.  "
    "Both arrive in Phase 2 — the harness is wired but empty until then."
)

# ---------------------------------------------------------------------------
# Backend parameter list
# ---------------------------------------------------------------------------

_BACKEND_PARAMS = [
    pytest.param("sqlite", id="sqlite"),
    pytest.param(
        "postgres",
        id="postgres",
        marks=[
            pytest.mark.skipif(
                not _postgres_available(),
                reason=_PG_SKIP_REASON,
            )
        ],
    ),
]


# ---------------------------------------------------------------------------
# Marker registration
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "vector: test requires vector search capability "
        "(embedder attached + vec extension loaded). "
        "Tests call pytest.skip() at runtime when the capability is absent.",
    )
    config.addinivalue_line(
        "markers",
        "trigram: test requires trigram substring-search capability "
        "(FTS5 trigram tokenizer for SQLite; pg_trgm for Postgres). "
        "Tests probe at runtime and call pytest.skip() when absent.",
    )


# ---------------------------------------------------------------------------
# Backend fixture
# ---------------------------------------------------------------------------


@pytest.fixture(params=_BACKEND_PARAMS)
def backend(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Generator[BackendHandle, None, None]:
    """
    Yield a fresh, ``initialise()``d ``BackendHandle`` for each backend parameter.

    The SQLite leg uses a real on-disk file in ``tmp_path`` (not ``:memory:``) so
    that ``BackendHandle.new_connection()`` can open a second handle to the same
    database and observe committed writes.  Both handles share the same
    ``HashingEmbedder`` instance (dim=64) for reproducible vector similarity.

    Tests must NOT assume backend-specific internals (no ``.connect()``, no private
    members, no sqlite file paths).
    """
    param: str = request.param

    if param == "sqlite":
        db_path = str(tmp_path / "conformance.db")
        # dim=64 is intentionally small for test speed; large enough to exercise
        # the vector phase when sqlite-vec is available.
        emb = HashingEmbedder(dim=64)

        def _make_sqlite() -> StorageBackend:
            settings = StorageSettings(db_path=db_path)
            return build_storage(settings, embedder=emb)

        b = _make_sqlite()
        b.initialise()
        handle = BackendHandle(backend=b, _factory=_make_sqlite)
        yield handle
        b.close()
        return

    if param == "postgres":
        # Phase 2: PostgresBackend construction goes here.
        # This branch is unreachable in Phase 1 (the param is always skipped).
        # Use build_storage() — the real factory dispatch — so Phase 2 must wire
        # build_storage's postgres branch (not just add a class) to pass conformance.
        from mintmory.core.config import StorageBackendEnum  # noqa: PLC0415

        dsn = os.environ.get("MINTMORY_TEST_PG_DSN", "")
        emb_pg = HashingEmbedder(dim=64)

        def _make_postgres() -> StorageBackend:
            return build_storage(
                StorageSettings(backend=StorageBackendEnum.POSTGRES, dsn=dsn),
                embedder=emb_pg,
            )

        pg = _make_postgres()
        pg.initialise()
        handle_pg = BackendHandle(backend=pg, _factory=_make_postgres)
        yield handle_pg
        pg.close()
        return

    pytest.fail(f"Unknown backend param: {param!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Convenience factory fixture (parametrized same as ``backend``)
# ---------------------------------------------------------------------------


@pytest.fixture(params=_BACKEND_PARAMS)
def backend_factory(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Generator[Callable[[], BackendHandle], None, None]:
    """
    Yield a *factory* that creates fresh ``BackendHandle`` instances all pointing to
    the same database.  Useful for tests that spin up multiple handles explicitly.

    Note: calling the factory does NOT close the previously-opened handle.  Each
    test is responsible for closing handles it opens beyond the first.
    """
    param: str = request.param
    handles: list[StorageBackend] = []

    if param == "sqlite":
        db_path = str(tmp_path / "conformance_fac.db")
        emb = HashingEmbedder(dim=64)

        def _make_sqlite_fac() -> StorageBackend:
            settings = StorageSettings(db_path=db_path)
            return build_storage(settings, embedder=emb)

        # Initialise once (schema created); subsequent opens reuse the schema.
        first = _make_sqlite_fac()
        first.initialise()
        handles.append(first)

        def _factory() -> BackendHandle:
            b = _make_sqlite_fac()
            b.initialise()
            handles.append(b)
            return BackendHandle(backend=b, _factory=_make_sqlite_fac)

        yield _factory
        for h in handles:
            h.close()
        return

    if param == "postgres":
        # Unreachable in Phase 1 — skipped by the param mark.
        pytest.fail("postgres factory not yet implemented")  # pragma: no cover

    pytest.fail(f"Unknown backend param: {param!r}")  # pragma: no cover
