"""HTTP boundary tracing: the API's SERVER span and its duration metric (task 2.1).

Spec: observability › HTTP server spans continue the caller's trace; observability › How the
middleware ends the server span; observability › Middleware telemetry never alters a request;
observability › Excluded HTTP paths; observability › HTTP server duration metric.

Each test initialises telemetry through the runtime's seam with an in-memory span exporter and
metric reader, then drives the module-level ``app`` through a ``TestClient`` (as the ``client``
fixture of ``test_routes.py`` does) or, for the middleware's own outcomes, the ASGI harness the
spec describes. Assertions run inside the ``with`` block, before ``shutdown_telemetry``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mintmory.api import app as app_module
from mintmory.api import telemetry_middleware
from mintmory.api.telemetry_middleware import TelemetryMiddleware
from mintmory.core import telemetry

pytest.importorskip("opentelemetry.sdk")

_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
_PARENT_SPAN_ID = "00f067aa0ba902b7"
_TRACEPARENT = f"00-{_TRACE_ID}-{_PARENT_SPAN_ID}-01"
_DURATION = "http.server.request.duration"
_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


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


@pytest.fixture
def telemetry_env() -> Iterator[tuple[Any, Any]]:
    """Telemetry on with an in-memory span exporter and metric reader."""
    exporter = _in_memory_span_exporter()
    reader = _in_memory_metric_reader()
    assert telemetry.init_telemetry(span_exporter=exporter, metric_reader=reader) is True
    yield exporter, reader


@pytest.fixture
def client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    telemetry_env: tuple[Any, Any],
) -> Iterator[TestClient]:
    """A TestClient backed by a throwaway DB, with telemetry already initialised."""
    db_file = tmp_path / "api_test.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_file))
    monkeypatch.setattr(app_module, "_store", None)
    with TestClient(app_module.app) as test_client:
        yield test_client
    monkeypatch.setattr(app_module, "_store", None)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _names(exporter: Any) -> list[str]:
    return [span.name for span in exporter.get_finished_spans()]


def _spans(exporter: Any, name: str) -> list[Any]:
    return [span for span in exporter.get_finished_spans() if span.name == name]


def _one(exporter: Any, name: str) -> Any:
    spans = _spans(exporter, name)
    assert len(spans) == 1, f"expected one {name!r} span, got {_names(exporter)}"
    return spans[0]


def _attributes(span: Any) -> dict[str, Any]:
    return dict(span.attributes or {})


def _metric(reader: Any, name: str) -> Any:
    data = reader.get_metrics_data()
    assert data is not None, "no metrics were exported"
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == name:
                    return metric
    return None


def _points(reader: Any, name: str) -> list[Any]:
    metric = _metric(reader, name)
    if metric is None:
        return []
    return list(metric.data.data_points)


def _ancestor_span_ids(span: Any, by_id: dict[int, Any]) -> set[int]:
    """The span ids of ``span``'s ancestors, walking the parent chain."""
    ids: set[int] = set()
    parent = span.parent
    while parent is not None:
        ids.add(parent.span_id)
        parent_span = by_id.get(parent.span_id)
        parent = parent_span.parent if parent_span is not None else None
    return ids


def _telemetry_text(exporter: Any, reader: Any) -> str:
    """Every span name, span/event attribute, status description and duration attribute value."""
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
    for point in _points(reader, _DURATION):
        for key, value in dict(point.attributes).items():
            lines.append(f"{key}={value}")
    return "\n".join(lines)


def _create_memory(client: TestClient) -> dict[str, Any]:
    resp = client.post(
        "/memories",
        json={"content": "Acme parking uses OAuth.", "category": "fact"},
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()
    return data


def _scope() -> dict[str, Any]:
    return {"type": "http", "method": "GET", "path": "/x", "headers": []}


async def _run_middleware(
    inner: Any, sent: list[dict[str, Any]], scope: dict[str, Any] | None = None
) -> Any:
    """Run ``TelemetryMiddleware(inner)`` over the spec's ASGI harness, appending to ``sent``."""

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    middleware = TelemetryMiddleware(inner)
    return await middleware(scope if scope is not None else _scope(), receive, send)


# ---------------------------------------------------------------------------
# HTTP server spans continue the caller's trace
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-dc87542c")
def test_incoming_traceparent_is_continued(
    client: TestClient, telemetry_env: tuple[Any, Any]
) -> None:
    exporter, _reader = telemetry_env
    _create_memory(client)

    resp = client.post(
        "/memories/search",
        json={"query": "parking"},
        headers={"traceparent": _TRACEPARENT},
    )
    assert resp.status_code == 200, resp.text

    server = _one(exporter, "POST /memories/search")
    assert server.context.trace_id == int(_TRACE_ID, 16)
    assert server.parent is not None, "the server span must continue the caller's trace"
    assert server.parent.span_id == int(_PARENT_SPAN_ID, 16)

    by_id = {span.context.span_id: span for span in exporter.get_finished_spans()}
    search = _one(exporter, "mintmory.search")
    assert server.context.span_id in _ancestor_span_ids(search, by_id)


@pytest.mark.l4("C-30744114")
def test_route_template_names_the_span_not_the_raw_path(
    client: TestClient, telemetry_env: tuple[Any, Any]
) -> None:
    exporter, _reader = telemetry_env
    created = _create_memory(client)
    memory_id = created["id"]

    resp = client.get(f"/memories/{memory_id}", params={"verbose": "1"})
    assert resp.status_code == 200, resp.text

    span = _one(exporter, "GET /memories/{memory_id}")
    attributes = _attributes(span)
    assert attributes["http.route"] == "/memories/{memory_id}"
    assert "url.path" not in attributes
    assert "url.query" not in attributes
    for value in attributes.values():
        assert memory_id not in str(value)


# ---------------------------------------------------------------------------
# How the middleware ends the server span
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-7507adff")
def test_no_route_and_method_mismatch(client: TestClient, telemetry_env: tuple[Any, Any]) -> None:
    from opentelemetry.trace import StatusCode

    exporter, _reader = telemetry_env
    assert client.get("/no-such-path").status_code == 404
    assert client.delete("/stats").status_code == 405
    preflight = client.options(
        "/stats",
        headers={"Origin": "http://x", "Access-Control-Request-Method": "GET"},
    )
    assert preflight.status_code == 200

    not_found = _one(exporter, "GET")
    assert _attributes(not_found)["http.response.status_code"] == 404
    assert "http.route" not in _attributes(not_found)
    assert not_found.status.status_code == StatusCode.UNSET

    method_mismatch = _one(exporter, "DELETE /stats")
    assert _attributes(method_mismatch)["http.route"] == "/stats"
    assert _attributes(method_mismatch)["http.response.status_code"] == 405
    assert method_mismatch.status.status_code == StatusCode.UNSET

    preflight_span = _one(exporter, "OPTIONS")
    assert _attributes(preflight_span)["http.response.status_code"] == 200
    assert "http.route" not in _attributes(preflight_span)
    assert preflight_span.status.status_code == StatusCode.UNSET


@pytest.mark.l4("C-d6238220")
def test_route_raising_before_the_response_starts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    telemetry_env: tuple[Any, Any],
) -> None:
    from opentelemetry.trace import StatusCode

    exporter, reader = telemetry_env
    monkeypatch.setenv("MINTMORY_DB", str(tmp_path / "api_test.db"))
    monkeypatch.setattr(app_module, "_store", None)

    def _raise() -> None:
        raise RuntimeError("SENTINEL-55")

    routes = app_module.app.router.routes
    added = len(routes)
    app_module.app.add_api_route("/test-raise", _raise, methods=["GET"])
    try:
        with TestClient(app_module.app, raise_server_exceptions=False) as test_client:
            resp = test_client.get("/test-raise")
            assert resp.status_code == 500

            span = _one(exporter, "GET /test-raise")
            assert span.status.status_code == StatusCode.ERROR
            assert not span.status.description
            attributes = _attributes(span)
            assert attributes["error.type"] == "RuntimeError"
            assert attributes["http.response.status_code"] == 500
            assert not span.events

            points = _points(reader, _DURATION)
            assert len(points) == 1, points
            assert dict(points[0].attributes)["http.response.status_code"] == 500

            assert "SENTINEL-55" not in _telemetry_text(exporter, reader)
    finally:
        del routes[added:]
        monkeypatch.setattr(app_module, "_store", None)


@pytest.mark.l4("C-85b39250")
def test_exception_after_the_response_started(telemetry_env: tuple[Any, Any]) -> None:
    from opentelemetry.trace import StatusCode

    exporter, reader = telemetry_env
    sent: list[dict[str, Any]] = []
    start = {"type": "http.response.start", "status": 200, "headers": []}
    error = RuntimeError("SENTINEL-56")

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send(start)
        raise error

    with pytest.raises(RuntimeError) as excinfo:
        asyncio.run(_run_middleware(inner, sent))
    assert excinfo.value is error
    assert sent == [start]

    span = _one(exporter, "GET")
    assert span.status.status_code == StatusCode.ERROR
    assert not span.status.description
    assert _attributes(span)["error.type"] == "RuntimeError"
    assert _attributes(span)["http.response.status_code"] == 200
    assert not span.events

    points = _points(reader, _DURATION)
    assert len(points) == 1, points
    assert dict(points[0].attributes)["http.response.status_code"] == 200
    assert "SENTINEL-56" not in _telemetry_text(exporter, reader)


@pytest.mark.l4("C-be1a4b66")
def test_5xx_answer_without_an_exception(telemetry_env: tuple[Any, Any]) -> None:
    from opentelemetry.trace import StatusCode

    exporter, _reader = telemetry_env
    sent: list[dict[str, Any]] = []
    start = {"type": "http.response.start", "status": 503, "headers": []}
    body = {"type": "http.response.body", "body": b"x"}

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send(start)
        await send(body)

    assert asyncio.run(_run_middleware(inner, sent)) is None
    assert sent == [start, body]

    span = _one(exporter, "GET")
    assert span.status.status_code == StatusCode.ERROR
    assert _attributes(span)["error.type"] == "503"
    assert isinstance(_attributes(span)["error.type"], str)
    assert _attributes(span)["http.response.status_code"] == 503


@pytest.mark.l4("C-7ec77600")
def test_cancelled_request_and_no_response_at_all(telemetry_env: tuple[Any, Any]) -> None:
    from opentelemetry.trace import StatusCode

    exporter, reader = telemetry_env

    sent: list[dict[str, Any]] = []

    async def cancelling(scope: Any, receive: Any, send: Any) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_run_middleware(cancelling, sent))
    assert sent == []

    silent: list[dict[str, Any]] = []

    async def returning(scope: Any, receive: Any, send: Any) -> None:
        return None

    assert asyncio.run(_run_middleware(returning, silent)) is None
    assert silent == []

    spans = _spans(exporter, "GET")
    assert len(spans) == 2, _names(exporter)
    for span in spans:
        assert span.status.status_code == StatusCode.UNSET
        attributes = _attributes(span)
        assert "error.type" not in attributes
        assert "http.response.status_code" not in attributes
        assert not span.events

    points = _points(reader, _DURATION)
    assert len(points) == 1, points
    assert points[0].count == 2
    for point in points:
        assert dict(point.attributes) == {"http.request.method": "GET"}


# ---------------------------------------------------------------------------
# Middleware telemetry never alters a request
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-1420ab97")
def test_malformed_traceparent_starts_a_new_trace(
    client: TestClient, telemetry_env: tuple[Any, Any]
) -> None:
    from opentelemetry import trace as otel_trace
    from opentelemetry.context import Context

    exporter, _reader = telemetry_env
    first = client.get("/stats", headers={"traceparent": "garbage"})
    second = client.get(
        "/stats",
        headers={"traceparent": "00-" + "0" * 32 + "-" + "0" * 16 + "-01"},
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    spans = _spans(exporter, "GET /stats")
    assert len(spans) == 2, _names(exporter)
    for span in spans:
        assert span.parent is None
        assert span.context.trace_id != int(_TRACE_ID, 16)

    context = telemetry.extract_context({"traceparent": "garbage"})
    assert isinstance(context, Context)
    assert otel_trace.get_current_span(context).get_span_context().is_valid is False


@pytest.mark.l4("C-a2f61e7e")
def test_failing_histogram_record_leaves_the_response_unchanged(
    client: TestClient,
    telemetry_env: tuple[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter, _reader = telemetry_env
    first = client.get("/stats")
    assert first.status_code == 200, first.text
    b0 = first.content

    from opentelemetry.sdk.metrics._internal.instrument import Histogram

    def _raising(self: Any, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("histogram record failed")

    monkeypatch.setattr(Histogram, "record", _raising)

    second = client.get("/stats")
    assert second.status_code == 200, second.text
    assert second.content == b0
    assert len(_spans(exporter, "GET /stats")) == 2, _names(exporter)


@pytest.mark.l4("C-5fd2f50f")
def test_failing_span_updates_leave_the_response_unchanged(
    telemetry_env: tuple[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    exporter, _reader = telemetry_env

    from opentelemetry.sdk.trace import Span

    def _raising(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("span update failed")

    monkeypatch.setattr(Span, "set_attribute", _raising)
    monkeypatch.setattr(Span, "set_attributes", _raising)
    monkeypatch.setattr(Span, "update_name", _raising)
    monkeypatch.setattr(telemetry, "extract_context", _raising)

    start = {"type": "http.response.start", "status": 201, "headers": [(b"x-a", b"1")]}
    body = {"type": "http.response.body", "body": b"ok"}

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        await send(start)
        await send(body)

    with caplog.at_level(logging.DEBUG, logger="mintmory.telemetry"):
        sent: list[dict[str, Any]] = []
        assert asyncio.run(_run_middleware(inner, sent)) is None
        assert sent == [start, body]

        error = ValueError("v")

        async def raising_inner(scope: Any, receive: Any, send: Any) -> None:
            await send(start)
            await send(body)
            raise error

        sent_error: list[dict[str, Any]] = []
        with pytest.raises(ValueError) as excinfo:
            asyncio.run(_run_middleware(raising_inner, sent_error))
        assert excinfo.value is error
        assert sent_error == [start, body]

        before = len(exporter.get_finished_spans())
        monkeypatch.setattr(telemetry, "span", _raising)
        sent_no_span: list[dict[str, Any]] = []
        assert asyncio.run(_run_middleware(inner, sent_no_span)) is None
        assert sent_no_span == [start, body]
        assert len(exporter.get_finished_spans()) == before

    assert "RuntimeError" in caplog.text


# ---------------------------------------------------------------------------
# Excluded HTTP paths
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-d3c89585")
def test_health_probes_are_not_traced(client: TestClient, telemetry_env: tuple[Any, Any]) -> None:
    exporter, _reader = telemetry_env
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    assert client.get("/healthz/x").status_code == 404

    names = _names(exporter)
    assert "GET /healthz" not in names
    assert "GET /readyz" not in names
    assert names == ["GET"], names


@pytest.mark.l4("C-6b05011d")
def test_excluded_by_the_environment(
    client: TestClient, telemetry_env: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter, _reader = telemetry_env
    created = _create_memory(client)
    memory_id = created["id"]
    memory_span = "GET /memories/{memory_id}"

    monkeypatch.setenv("OTEL_PYTHON_EXCLUDED_URLS", "^/stats$,/summaries")
    assert client.get("/stats").status_code == 200
    assert client.get("/summaries").status_code == 200
    assert client.get(f"/memories/{memory_id}").status_code == 200

    names = _names(exporter)
    assert "GET /stats" not in names, names
    assert "GET /summaries" not in names, names
    assert memory_span in names, names

    exporter.clear()
    monkeypatch.setenv("OTEL_PYTHON_EXCLUDED_URLS", " , ^/stats$ ,")
    assert client.get("/stats").status_code == 200
    assert client.get("/summaries").status_code == 200
    assert client.get(f"/memories/{memory_id}").status_code == 200

    names = _names(exporter)
    assert "GET /stats" not in names, names
    assert "GET /summaries" in names, names
    assert memory_span in names, names


@pytest.mark.l4("C-512ddc0c")
def test_a_bad_exclusion_pattern_is_skipped(
    client: TestClient,
    telemetry_env: tuple[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    exporter, _reader = telemetry_env
    monkeypatch.delenv("OTEL_PYTHON_EXCLUDED_URLS", raising=False)
    created = _create_memory(client)
    memory_id = created["id"]
    memory_span = "GET /memories/{memory_id}"

    clear = getattr(telemetry_middleware._compile_excluded, "cache_clear", None)
    if callable(clear):
        clear()
    monkeypatch.setenv("OTEL_PYTHON_EXCLUDED_URLS", "([,^/stats$")

    with caplog.at_level(logging.WARNING, logger="mintmory.telemetry"):
        for _ in range(2):
            assert client.get("/stats").status_code == 200
            assert client.get(f"/memories/{memory_id}").status_code == 200

    names = _names(exporter)
    assert "GET /stats" not in names, names
    assert memory_span in names, names

    warnings = [
        record
        for record in caplog.records
        if record.name == "mintmory.telemetry"
        and record.levelno == logging.WARNING
        and "([" in record.getMessage()
    ]
    assert len(warnings) == 1, [record.getMessage() for record in warnings]


# ---------------------------------------------------------------------------
# HTTP server duration metric
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-7409b7a7")
def test_request_duration_recorded(client: TestClient, telemetry_env: tuple[Any, Any]) -> None:
    _exporter, reader = telemetry_env
    assert client.get("/stats").status_code == 200
    assert client.get("/stats").status_code == 200

    metric = _metric(reader, _DURATION)
    assert metric is not None, "the duration histogram was not recorded"
    assert metric.unit == "s"

    points = _points(reader, _DURATION)
    assert len(points) == 1, points
    point = points[0]
    assert dict(point.attributes) == {
        "http.route": "/stats",
        "http.request.method": "GET",
        "http.response.status_code": 200,
    }
    assert point.count == 2
    assert tuple(point.explicit_bounds) == _BUCKETS
