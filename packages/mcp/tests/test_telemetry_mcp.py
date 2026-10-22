"""MCP boundary tracing: FastMCP's native SERVER span per tool call (task 3.1).

Spec: observability › MCP tool calls are traced once.

The behaviour is FastMCP 3.4.2's own (``server_span`` in ``fastmcp/server/telemetry.py``):
no MintMory code adds a span or middleware, so the tests only pin what the installed
FastMCP does against the runtime's global provider. Every test initialises telemetry
through the seam with an injected in-memory span exporter before the ``fastmcp.Client``
is opened and asserts inside the ``with`` block, before the next teardown resets the
shim. Clients follow the ``mcp_client`` fixture of ``test_tools.py`` and the
``history_client`` fixture of ``test_history_mcp.py``, copied.

TDD exemption: already satisfied — FastMCP 3.4.2 traces each tool call natively and the
runtime unit made the provider global, so these scenarios are true of the base code by
design (task 3.2: no MCP code, no span per tool call).
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastmcp import Client
from mintmory.core import telemetry
from mintmory.core.storage import StorageAdapter
from mintmory.mcp import server
from mintmory.mcp.history_server import mcp as history_mcp
from mintmory.mcp.server import mcp

pytest.importorskip("opentelemetry.sdk")

_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
_PARENT_SPAN_ID = "00f067aa0ba902b7"
_TRACEPARENT = f"00-{_TRACE_ID}-{_PARENT_SPAN_ID}-01"
_TOOL_ERROR_TYPE = "fastmcp.exceptions.ToolError"


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


@pytest.fixture
async def history_client(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, telemetry_env: Any
) -> AsyncIterator[tuple[Client[Any], Any]]:
    """Yield an in-memory history client (fixture of ``test_history_mcp.py``) with its exporter."""
    monkeypatch.delenv("MINTMORY_DB", raising=False)
    db_file = str(tmp_path / "agent-history.db")
    store = StorageAdapter(db_file)
    store.initialise()
    store.close()
    monkeypatch.setenv("MINTMORY_HISTORY_DB", db_file)
    async with Client(history_mcp) as client:
        yield client, telemetry_env


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _names(exporter: Any) -> list[str]:
    return [span.name for span in exporter.get_finished_spans()]


def _server_spans(exporter: Any) -> list[Any]:
    from opentelemetry.trace import SpanKind

    return [span for span in exporter.get_finished_spans() if span.kind is SpanKind.SERVER]


def _attributes(span: Any) -> dict[str, Any]:
    return dict(span.attributes or {})


def _ancestor_span_ids(span: Any, by_id: dict[int, Any]) -> set[int]:
    """The span ids of ``span``'s ancestors, walking the parent chain."""
    ids: set[int] = set()
    parent = span.parent
    while parent is not None:
        ids.add(parent.span_id)
        parent_span = by_id.get(parent.span_id)
        parent = parent_span.parent if parent_span is not None else None
    return ids


def _telemetry_text(exporter: Any) -> str:
    """Every span name, span/event attribute and status description, as one text."""
    lines: list[str] = []
    for span in exporter.get_finished_spans():
        lines.append(span.name)
        for key, value in _attributes(span).items():
            lines.append(f"{key}={value}")
        for event in span.events:
            lines.append(event.name)
            for key, value in dict(event.attributes or {}).items():
                lines.append(f"{key}={value}")
        if span.status is not None:
            lines.append(str(span.status.description or ""))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The verified FastMCP version is installed
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-7d4fc8c6")
def test_fastmcp_version_is_the_verified_one() -> None:
    """The traced-behaviour facts were verified by running fastmcp 3.4.2 only."""
    assert importlib.metadata.version("fastmcp") == "3.4.2", (
        "the FastMCP telemetry facts in this module were verified on 3.4.2 only; "
        "check them again against the new version before trusting these tests"
    )


# ---------------------------------------------------------------------------
# Tool call is one span with core spans below it
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-811d0420")
async def test_tool_call_is_one_server_span_with_core_spans_below_it(
    mcp_client: tuple[Client[Any], Any],
) -> None:
    """One SERVER span per tool call; the search span of the call is its descendant."""
    client, exporter = mcp_client

    added = await client.call_tool(
        "memory_add", {"content": "Acme parking uses OAuth.", "category": "fact"}
    )
    assert added.is_error is False
    res = await client.call_tool("memory_search", {"query": "parking"})
    assert res.is_error is False
    assert res.data["total_found"] >= 1, "the memory added first must be found"

    server_calls = [span.name for span in _server_spans(exporter)]
    assert server_calls.count("tools/call memory_search") == 1, server_calls
    assert server_calls.count("tools/call memory_add") == 1, server_calls

    call_span = next(
        span for span in _server_spans(exporter) if span.name == "tools/call memory_search"
    )
    by_id = {span.context.span_id: span for span in exporter.get_finished_spans()}
    search_spans = [span for span in by_id.values() if span.name == "mintmory.search"]
    assert search_spans, _names(exporter)
    ancestor_ids = _ancestor_span_ids(search_spans[-1], by_id)
    assert call_span.context.span_id in ancestor_ids, (
        "mintmory.search must descend from the SERVER span of its tool call"
    )


@pytest.mark.l4("C-811d0420")
async def test_history_tool_call_is_one_server_span(
    history_client: tuple[Client[Any], Any],
) -> None:
    """The history server's tool call is also exactly one native SERVER span."""
    client, exporter = history_client
    res = await client.call_tool("history_stats", {})
    assert res.is_error is False

    server_calls = [span.name for span in _server_spans(exporter)]
    assert server_calls.count("tools/call history_stats") == 1, server_calls


# ---------------------------------------------------------------------------
# A failing tool is marked
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-313b2e72")
async def test_failing_tool_is_marked(
    mcp_client: tuple[Client[Any], Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raising tool re-surfaces as ToolError; the span carries tool_error, no message."""
    from opentelemetry.trace import StatusCode

    client, exporter = mcp_client

    def _raise() -> Any:
        raise RuntimeError("SENTINEL-77")

    monkeypatch.setattr(server, "_get_store", _raise)

    result = await client.call_tool("memory_stats", {}, raise_on_error=False)
    assert result.is_error is True

    spans = [span for span in _server_spans(exporter) if span.name == "tools/call memory_stats"]
    assert len(spans) == 1, _names(exporter)
    span = spans[0]
    assert span.status.status_code == StatusCode.ERROR
    assert not span.status.description, span.status.description
    assert _attributes(span)["error.type"] == "tool_error"

    exception_events = [event for event in span.events if event.name == "exception"]
    assert exception_events, "the tool's exception must be recorded as an event"
    for event in exception_events:
        assert dict(event.attributes or {}) == {"exception.type": _TOOL_ERROR_TYPE}

    assert "SENTINEL-77" not in _telemetry_text(exporter)


# ---------------------------------------------------------------------------
# Tool arguments never reach telemetry
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-b03582ac")
async def test_tool_arguments_never_reach_telemetry(
    mcp_client: tuple[Client[Any], Any],
) -> None:
    """Neither the search query nor the note text appears anywhere in the exported spans."""
    client, exporter = mcp_client

    res = await client.call_tool("memory_search", {"query": "SENTINEL-ARG-4f"})
    assert res.is_error is False
    assert res.data["session_id"], "the search must have produced a session"
    note = await client.call_tool("memory_note", {"content": "SENTINEL-ARG-9a"})
    assert note.is_error is False
    assert note.data["note"]["is_note"] is True

    exported = _telemetry_text(exporter)
    assert "SENTINEL-ARG-4f" not in exported
    assert "SENTINEL-ARG-9a" not in exported


# ---------------------------------------------------------------------------
# Context in _meta is continued
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-da502b68")
async def test_meta_traceparent_is_continued(mcp_client: tuple[Client[Any], Any]) -> None:
    """``_meta`` context starts the SERVER span; the fastmcp CLIENT span adds none."""
    from opentelemetry.trace import SpanKind

    client, exporter = mcp_client
    raw = await client.session.call_tool("memory_stats", {}, meta={"traceparent": _TRACEPARENT})
    assert raw.isError is False, "the raw session call must reach the tool"

    spans = [span for span in _server_spans(exporter) if span.name == "tools/call memory_stats"]
    assert len(spans) == 1, _names(exporter)
    span = spans[0]
    assert span.context.trace_id == int(_TRACE_ID, 16)
    assert span.parent is not None, "the SERVER span must continue the _meta context"
    assert span.parent.span_id == int(_PARENT_SPAN_ID, 16)

    client_spans = [
        s
        for s in exporter.get_finished_spans()
        if s.kind is SpanKind.CLIENT and s.name == "tools/call memory_stats"
    ]
    assert client_spans == [], _names(exporter)


# ---------------------------------------------------------------------------
# Tool spans follow a new init
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-fa4bc29e")
async def test_tool_spans_follow_a_new_init(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    telemetry_env: Any,
) -> None:
    """After ``reset_telemetry`` and a new init, spans land in the new exporter only."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter_a = telemetry_env
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "memories.db"))
    server._store = None
    try:
        async with Client(mcp) as client:
            first = await client.call_tool("memory_stats", {})
            assert first.is_error is False

        spans_a = [
            span for span in _server_spans(exporter_a) if span.name == "tools/call memory_stats"
        ]
        assert len(spans_a) == 1, _names(exporter_a)

        telemetry.reset_telemetry()
        exporter_b = InMemorySpanExporter()
        assert telemetry.init_telemetry(span_exporter=exporter_b) is True

        async with Client(mcp) as client_b:
            second = await client_b.call_tool("memory_stats", {})
            assert second.is_error is False

        spans_b = [
            span for span in _server_spans(exporter_b) if span.name == "tools/call memory_stats"
        ]
        assert len(spans_b) == 1, _names(exporter_b)
    finally:
        if server._store is not None:
            server._store.close()
        server._store = None
