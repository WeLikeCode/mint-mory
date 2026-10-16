"""Repo-root pytest configuration.

Test-only tuning: the file-backed SQLite databases used by the CLI/MCP/API test
suites are opened by several short-lived connections per test. The production
``busy_timeout`` default (5s) is correct for multi-agent deployments but turns
those transient WAL lock waits into multi-second stalls under pytest. Cap it low
for the test session — production behaviour is unchanged (the constant default in
``storage._busy_timeout_ms`` stays 5000ms; the two unit tests that assert the
default/override manage this env var themselves).

Telemetry (task 1.1): every package's tests run with ``MINTMORY_OTEL_ENABLED=false``
by default, and an autouse fixture returns the telemetry module to its no-op shim
before and after each test, so no test builds a network exporter by accident.

Telemetry test seam (task 1.2): ``closed_port`` and ``otlp_receiver`` let any package's
tests point an exporter at a local OTLP/HTTP endpoint and inspect what it delivered.
"""

import os
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

os.environ.setdefault("MINTMORY_SQLITE_BUSY_TIMEOUT_MS", "100")
os.environ.setdefault("MINTMORY_OTEL_ENABLED", "false")


@pytest.fixture(autouse=True)
def _reset_telemetry() -> Iterator[None]:
    """Keep each test on the no-op telemetry shim (spec: shared test fixtures)."""
    from mintmory.core import telemetry

    telemetry.reset_telemetry()
    yield
    telemetry.reset_telemetry()


def _attribute_value(value: Any) -> Any:
    """Unwrap a protobuf ``AnyValue`` into the plain Python value it carries."""
    which = value.WhichOneof("value")
    if which is None:
        return None
    return getattr(value, which)


class _OtlpReceiver:
    """A local OTLP/HTTP collector that records every POST it receives."""

    def __init__(self) -> None:
        self._requests: list[tuple[str, bytes]] = []
        self._lock = threading.Lock()
        receiver = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                with receiver._lock:
                    receiver._requests.append((self.path, body))
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def endpoint(self) -> str:
        """``http://127.0.0.1:<port>`` for the receiver's socket."""
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def requests(self) -> list[tuple[str, bytes]]:
        """``(path, body bytes)`` for every POST the receiver answered with 200."""
        with self._lock:
            return list(self._requests)

    def spans(self) -> list[tuple[str, dict[str, Any]]]:
        """``(name, resource-attributes dict)`` per span posted to ``/v1/traces``."""
        from opentelemetry.proto.collector.trace.v1 import trace_service_pb2

        spans: list[tuple[str, dict[str, Any]]] = []
        for path, body in self.requests:
            if path != "/v1/traces":
                continue
            request = trace_service_pb2.ExportTraceServiceRequest()
            request.ParseFromString(body)
            for resource_spans in request.resource_spans:
                attributes = {
                    item.key: _attribute_value(item.value)
                    for item in resource_spans.resource.attributes
                }
                for scope_spans in resource_spans.scope_spans:
                    for span in scope_spans.spans:
                        spans.append((span.name, attributes))
        return spans

    def shutdown(self) -> None:
        """Stop answering and release the port; safe to call once at teardown."""
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)


@pytest.fixture
def closed_port() -> int:
    """A ``127.0.0.1`` port nobody listens on, so an export there fails fast."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def otlp_receiver() -> Iterator[_OtlpReceiver]:
    """A local ``ThreadingHTTPServer`` collector running in a daemon thread."""
    receiver = _OtlpReceiver()
    try:
        yield receiver
    finally:
        receiver.shutdown()
