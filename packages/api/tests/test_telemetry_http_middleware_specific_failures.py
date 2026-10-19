"""The middleware logs each failing telemetry step by name (FB-005 item 1).

Spec: observability › Middleware telemetry never alters a request.

The committed ``test_safe_steps_keep_the_response_when_span_updates_fail`` only asserts that
``RuntimeError`` appears in the log, which the precondition helper ``_safe_drops_a_failure``
already guarantees before any span update fails. These tests give each failing step its own
exception class and assert that the middleware logs every one of them, so a step that stops
failing (or a guard that stops naming the failure) is visible.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.api.telemetry_middleware import TelemetryMiddleware
from mintmory.core import telemetry

pytest.importorskip("opentelemetry.sdk")

_DEBUG_PREFIX = "telemetry: http middleware step failed"


class _ExtractError(Exception):
    pass


class _NameError(Exception):
    pass


class _AttributesError(Exception):
    pass


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


class _Route:
    path = "/x"


def _failure_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "mintmory.telemetry" and record.levelno == logging.DEBUG
    ]


def test_each_failing_span_step_is_named_in_the_debug_log(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """extract_context, update_name and set_attributes each log their own exception class."""
    exporter = _in_memory_span_exporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True

    from opentelemetry.sdk.trace import Span

    def _raise_extract(carrier: Any) -> Any:
        raise _ExtractError("SENTINEL-EXTRACT")

    def _raise_name(self: Any, *args: Any, **kwargs: Any) -> None:
        raise _NameError("SENTINEL-NAME")

    def _raise_attributes(self: Any, *args: Any, **kwargs: Any) -> None:
        raise _AttributesError("SENTINEL-ATTRIBUTES")

    monkeypatch.setattr(telemetry, "extract_context", _raise_extract)
    monkeypatch.setattr(Span, "update_name", _raise_name)
    monkeypatch.setattr(Span, "set_attributes", _raise_attributes)

    start = {"type": "http.response.start", "status": 200, "headers": []}
    body = {"type": "http.response.body", "body": b"ok"}
    sent: list[dict[str, Any]] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send(start)
        await send(body)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": [],
        "route": _Route(),
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    with caplog.at_level(logging.DEBUG, logger="mintmory.telemetry"):
        assert asyncio.run(TelemetryMiddleware(inner)(scope, receive, send)) is None

    assert sent == [start, body]
    assert len(exporter.get_finished_spans()) == 1, exporter.get_finished_spans()

    messages = _failure_messages(caplog)
    for failure in (_ExtractError, _NameError, _AttributesError):
        assert any(
            _DEBUG_PREFIX in message and failure.__name__ in message for message in messages
        ), (failure.__name__, messages)
