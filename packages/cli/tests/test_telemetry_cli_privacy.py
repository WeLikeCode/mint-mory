"""Telemetry carries no content: notes, LLM prompts, concept names, headers and indexed files.

Spec: observability › Telemetry carries no content › Notes, LLM calls, concept names, headers
and indexed files leak nothing.

With telemetry on, a note is created, a full dream runs against a local OpenAI-compatible chat
server (the summary prompt holds the concept name and a memory sentinel, the ``Authorization``
header holds the key), and ``mintmory index-tree`` indexes a text file holding another sentinel.
No exported span name, span or event attribute, status description or metric attribute may carry
any sentinel. The test asserts the server really received the chat request carrying the key, and
that this unit's ``mintmory.cli.index-tree`` root span exists, so a no-op telemetry shim cannot
make the privacy check pass vacuously.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from mintmory.cli.main import app
from mintmory.core import telemetry
from mintmory.core.config import LLMProvider, LLMSettings
from mintmory.core.llm import build_dreaming_engine
from mintmory.core.notes import create_note
from mintmory.core.storage import StorageAdapter
from typer.testing import CliRunner

pytest.importorskip("opentelemetry.sdk")

_KEY = "SENTINEL-" + "KEY-" + "6e"
_NOTE = "SENTINEL-NOTE-5d"
_CONCEPT = "zq-concept-41"
_DREAM = "SENTINEL-DREAM-8e"
_OUT = "SENTINEL-OUT-2b"
_FILE = "SENTINEL-FILE-3c"


class _ChatServer:
    """A local OpenAI-compatible ``/v1/chat/completions`` endpoint recording each request."""

    def __init__(self) -> None:
        self._bodies: list[bytes] = []
        self._authorizations: list[str | None] = []
        self._lock = threading.Lock()
        receiver = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                with receiver._lock:
                    receiver._bodies.append(body)
                    receiver._authorizations.append(self.headers.get("Authorization"))
                payload = json.dumps({"choices": [{"message": {"content": _OUT}}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        """``http://127.0.0.1:<port>/v1`` — the client appends ``/chat/completions``."""
        host = str(self._server.server_address[0])
        port = self._server.server_address[1]
        return f"http://{host}:{port}/v1"

    @property
    def requests(self) -> list[bytes]:
        """The JSON bodies of every chat request received."""
        with self._lock:
            return list(self._bodies)

    @property
    def authorizations(self) -> list[str | None]:
        """The ``Authorization`` header of every chat request received."""
        with self._lock:
            return list(self._authorizations)

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)


@pytest.fixture()
def chat_server() -> Iterator[_ChatServer]:
    """A local ``ThreadingHTTPServer`` answering chat requests in a daemon thread."""
    server = _ChatServer()
    try:
        yield server
    finally:
        server.shutdown()


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default providers, so repeated inits stay meaningful."""
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


def _in_memory_span_exporter() -> Any:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    return InMemorySpanExporter()


def _in_memory_metric_reader() -> Any:
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    return InMemoryMetricReader()


def _all_text(exporter: Any, reader: Any) -> str:
    """Every span name, span/event attribute, status description and metric attribute value."""
    lines: list[str] = []
    for span in exporter.get_finished_spans():
        lines.append(span.name)
        for key, value in dict(span.attributes or {}).items():
            lines.append(f"{key}={value}")
        for event in span.events:
            lines.append(event.name)
            for key, value in dict(event.attributes or {}).items():
                lines.append(f"{key}={value}")
        status = span.status
        if status is not None:
            lines.append(str(status.description or ""))
    data = reader.get_metrics_data()
    if data is not None:
        for resource_metrics in data.resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    for point in metric.data.data_points:
                        for key, value in dict(point.attributes).items():
                            lines.append(f"{key}={value}")
    return "\n".join(lines)


def _assert_no_sentinel(exporter: Any, reader: Any, sentinels: Sequence[str]) -> None:
    """Telemetry really recorded something, and no field anywhere carries a sentinel."""
    assert exporter.get_finished_spans(), "no spans were exported"
    blob = _all_text(exporter, reader)
    for sentinel in sentinels:
        assert sentinel not in blob, f"telemetry leaked {sentinel!r}"


@pytest.mark.l4("C-395d5e72")
def test_notes_llm_concepts_headers_and_files_leak_nothing(
    chat_server: _ChatServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Note, dream prompt, concept name, auth key and indexed file all stay out of telemetry."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True

    store = StorageAdapter(":memory:")
    store.initialise()
    try:
        for suffix in ("one", "two", "three"):
            store.add_memory(
                content=f'the "{_CONCEPT}" memory {suffix} carrying {_DREAM}',
                category="fact",
            )

        create_note(store, _NOTE)

        engine = build_dreaming_engine(
            store,
            LLMSettings(
                provider=LLMProvider.OLLAMA,
                base_url=chat_server.base_url,
                model="m",
                api_key=_KEY,
            ),
        )
        engine.run_full()
    finally:
        store.close()

    assert chat_server.requests, "the dreaming engine must call the local chat server"
    assert f"Bearer {_KEY}" in chat_server.authorizations, chat_server.authorizations

    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "privacy_cli.db"))
    monkeypatch.setenv("COLUMNS", "200")
    folder = tmp_path / "indexed"
    folder.mkdir()
    (folder / "data.txt").write_text(f"a file holding {_FILE}\n")

    result = CliRunner().invoke(app, ["index-tree", str(folder)])
    assert result.exit_code == 0, result.output

    names = {span.name for span in exporter.get_finished_spans()}
    assert "mintmory.cli.index-tree" in names, sorted(names)

    _assert_no_sentinel(
        exporter,
        reader,
        (_CONCEPT, _NOTE, _DREAM, _OUT, _KEY, _FILE),
    )
