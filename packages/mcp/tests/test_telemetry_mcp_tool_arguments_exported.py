"""FB-004: the tool-argument privacy test must show the tool-call span was exported.

Spec: observability › MCP tool calls are traced once › Tool arguments never reach telemetry.

The committed ``test_tool_arguments_never_reach_telemetry`` (packages/mcp/tests/
test_telemetry_mcp.py) only asserts that the sentinel arguments are *absent* from the
exported spans. Absence is satisfied by an empty exporter too, so a silent stop of span
export would leave that test green. This test asserts the tool-call SERVER spans were
actually exported before it checks that no argument reached them, so no export fails it.

The fixtures of ``test_telemetry_mcp.py`` (the ``mcp_client`` fixture of ``test_tools.py``,
copied) are repeated here because the criterion's own test may not be edited; the missing
assertion lives in this new test instead.

TDD exemption: test-only follow-up found by the review of a merged change; no production
behaviour differs, so the base code already satisfies the outcome this test pins.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastmcp import Client
from mintmory.core import telemetry
from mintmory.mcp import server
from mintmory.mcp.server import mcp

pytest.importorskip("opentelemetry.sdk")

_SEARCH_SENTINEL = "SENTINEL-ARG-EXPORT-4f"
_NOTE_SENTINEL = "SENTINEL-ARG-EXPORT-9a"


@pytest.fixture
def telemetry_env() -> Iterator[Any]:
    """Telemetry on with an in-memory span exporter, through the runtime's seam."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True, (
        "the runtime seam must install the injected exporter as the global provider"
    )
    yield exporter
    telemetry.reset_telemetry()


@pytest.fixture
async def mcp_client(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, telemetry_env: Any
) -> AsyncIterator[tuple[Client[Any], Any]]:
    """Yield an in-memory client (fixture of ``test_tools.py``) with its exporter."""
    db_file = tmp_path / "memories.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_file))
    server._store = None
    try:
        async with Client(mcp) as client:
            yield client, telemetry_env
    finally:
        if server._store is not None:
            server._store.close()
        server._store = None


def _server_span_names(exporter: Any) -> list[str]:
    """The names of the finished SERVER spans the exporter holds."""
    from opentelemetry.trace import SpanKind

    return [span.name for span in exporter.get_finished_spans() if span.kind is SpanKind.SERVER]


def _telemetry_text(exporter: Any) -> str:
    """Every span name, span/event attribute and status description, as one text."""
    lines: list[str] = []
    for span in exporter.get_finished_spans():
        lines.append(span.name)
        for key, value in dict(span.attributes or {}).items():
            lines.append(f"{key}={value}")
        for event in span.events:
            lines.append(event.name)
            for key, value in dict(event.attributes or {}).items():
                lines.append(f"{key}={value}")
        if span.status is not None:
            lines.append(str(span.status.description or ""))
    return "\n".join(lines)


async def test_tool_call_spans_are_exported_and_carry_no_arguments(
    mcp_client: tuple[Client[Any], Any],
) -> None:
    """The SERVER span of each tool call is exported, and no sentinel argument reached it."""
    client, exporter = mcp_client

    res = await client.call_tool("memory_search", {"query": _SEARCH_SENTINEL})
    assert res.is_error is False
    assert res.data["session_id"], "the search must have produced a session"
    note = await client.call_tool("memory_note", {"content": _NOTE_SENTINEL})
    assert note.is_error is False
    assert note.data["note"]["is_note"] is True

    assert exporter.get_finished_spans(), (
        "the tool calls must have exported at least one span; otherwise the privacy "
        "assertions below hold for the wrong reason"
    )
    server_calls = _server_span_names(exporter)
    assert server_calls.count("tools/call memory_search") == 1, server_calls
    assert server_calls.count("tools/call memory_note") == 1, server_calls

    exported = _telemetry_text(exporter)
    assert _SEARCH_SENTINEL not in exported
    assert _NOTE_SENTINEL not in exported
