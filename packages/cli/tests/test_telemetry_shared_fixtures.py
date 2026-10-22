"""The root conftest.py OTLP receiver fixtures (observability › Shared telemetry test fixtures).

Task 1.2 puts MintMory's shared telemetry fixtures in the root ``conftest.py``: ``closed_port``
(a 127.0.0.1 port nobody listens on) and ``otlp_receiver`` (a ``ThreadingHTTPServer`` answering on
a daemon thread, torn down at test teardown, that records the POSTs and decodes the spans' names
and resource attributes). Any package's tests reach them by fixture name; this test lives in
``packages/cli/tests`` as the requirement's scenario does. The receiver is exercised with the real
OTLP/HTTP exporter over loopback, so the fixture's behaviour — not just its name — is pinned.
"""

from __future__ import annotations

import socket
import time
from typing import Any

import pytest


def _fixture_available(request: pytest.FixtureRequest, name: str) -> bool:
    """Whether ``name`` resolves here, so an absent fixture fails by assertion, not error."""
    try:
        request.getfixturevalue(name)
    except pytest.FixtureLookupError:
        return False
    return True


@pytest.mark.l4("C-29c6c2b6")
def test_cli_tests_can_request_the_shared_telemetry_fixtures(
    request: pytest.FixtureRequest,
) -> None:
    """A test in packages/cli/tests reaches both shared fixtures by name."""
    assert _fixture_available(request, "otlp_receiver") is True, (
        "root conftest.py must provide an otlp_receiver fixture to every package's tests"
    )
    assert _fixture_available(request, "closed_port") is True, (
        "root conftest.py must provide a closed_port fixture to every package's tests"
    )


@pytest.mark.l4("C-29c6c2b6")
def test_otlp_receiver_records_a_post_and_decodes_the_exported_spans(
    request: pytest.FixtureRequest,
) -> None:
    """otlp_receiver answers the OTLP/HTTP POST with 200 and reports the span it carried."""
    assert _fixture_available(request, "otlp_receiver") is True, (
        "root conftest.py must provide an otlp_receiver fixture to every package's tests"
    )
    receiver = request.getfixturevalue("otlp_receiver")
    assert receiver.endpoint.startswith("http://127.0.0.1:"), receiver.endpoint

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    provider = TracerProvider()
    provider.add_span_processor(
        SimpleSpanProcessor(OTLPSpanExporter(endpoint=f"{receiver.endpoint}/v1/traces"))
    )
    tracer = provider.get_tracer("fixture-probe")
    with tracer.start_as_current_span("fixture-probe"):
        pass
    provider.shutdown()

    deadline = time.monotonic() + 2.0
    while not receiver.requests and time.monotonic() < deadline:
        time.sleep(0.01)
    assert receiver.requests, "the receiver must record the exporter's POST"
    assert receiver.requests[0][0] == "/v1/traces"
    assert "fixture-probe" in [name for name, _attrs in receiver.spans()]


@pytest.mark.l4("C-29c6c2b6")
def test_closed_port_is_a_loopback_port_nobody_listens_on(request: pytest.FixtureRequest) -> None:
    """closed_port gives an int 127.0.0.1 port with no listener, so an export there fails fast."""
    assert _fixture_available(request, "closed_port") is True, (
        "root conftest.py must provide a closed_port fixture to every package's tests"
    )
    port: Any = request.getfixturevalue("closed_port")
    assert isinstance(port, int)
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=0.2)
