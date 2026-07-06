"""
Backend conformance test package for MintMory — Phase 1.

Exports the ``BackendHandle`` fixture wrapper so that both ``conftest.py`` and
test modules can import it without depending on conftest's special-import status.

Import path (resolved when pytest adds ``packages/core/tests/`` to sys.path for
this package): ``from conformance import BackendHandle``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from mintmory.core.ports import StorageBackend

__all__ = ["BackendHandle"]


@dataclass
class BackendHandle:
    """
    Test wrapper around an initialised ``StorageBackend``.

    Provides the live backend and a *factory* that opens a fresh, initialised
    handle pointing to the **same** underlying database.  Tests that need to
    verify cross-connection visibility (e.g. write on handle A, read on handle B)
    call ``new_connection()`` to obtain the second handle.

    No ``sqlite3.Connection``, no private members, no ``:memory:`` — 100%
    backend-agnostic surface.
    """

    backend: StorageBackend
    _factory: Callable[[], StorageBackend] = field(repr=False)

    def new_connection(self) -> StorageBackend:
        """Open and return a second initialised ``StorageBackend`` at the same DB."""
        b = self._factory()
        b.initialise()
        return b
