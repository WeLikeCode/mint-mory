"""fix-cochange-tools-on-postgres, task 2.6: the MCP tool docs state SQLite-only.

``docs/agent-history-mcp.md`` documents the read-only working-store tools. The
behavioural half of the requirement (``docs_changed_with`` and ``docs_timeline``
return ``{"error": "not_implemented", "message": ...}`` on a non-``SqliteBackend``
store) is pinned in ``test_cochange_tools.py`` and implemented in
``mintmory.mcp.server``; this module pins the documentation half for the
``**Tools (MM-41 ...)**`` section, which was silent about the non-SQLite case.
"""

from __future__ import annotations

from pathlib import Path

import pytest

AGENT_HISTORY_DOC = Path(__file__).resolve().parents[3] / "docs" / "agent-history-mcp.md"

_TOOLS_MARKER = "**Tools (MM-41"


def _tools_section(text: str) -> str:
    """Return the MM-41 tools section of the doc, up to the next horizontal rule."""
    start = text.find(_TOOLS_MARKER)
    assert start != -1, f"no {_TOOLS_MARKER!r} heading in {AGENT_HISTORY_DOC}"
    rest = text[start:]
    end = rest.find("\n---")
    return rest if end == -1 else rest[:end]


def _documented_sqlite_only_section() -> str:
    return _tools_section(AGENT_HISTORY_DOC.read_text(encoding="utf-8"))


@pytest.mark.l4("C-51a21242")
def test_docs_changed_with_documents_sqlite_only() -> None:
    """The tools section names docs_changed_with and the SQLite-only not_implemented case."""
    section = _documented_sqlite_only_section()
    assert "docs_changed_with" in section
    assert "SQLite-only" in section
    assert "not_implemented" in section


@pytest.mark.l4("C-d2f427d6")
def test_docs_timeline_documents_sqlite_only() -> None:
    """The tools section names docs_timeline and the SQLite-only not_implemented case."""
    section = _documented_sqlite_only_section()
    assert "docs_timeline" in section
    assert "SQLite-only" in section
    assert "not_implemented" in section
