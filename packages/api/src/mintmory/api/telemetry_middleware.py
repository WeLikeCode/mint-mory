"""ASGI middleware that traces each HTTP request as a SERVER span.

Spec: observability › HTTP server spans continue the caller's trace; observability › How the
middleware ends the server span; observability › Middleware telemetry never alters a request;
observability › Excluded HTTP paths; observability › HTTP server duration metric.
"""

from __future__ import annotations

import contextlib
import functools
import logging
import os
import re
import time
from collections.abc import Iterator
from typing import Any

from mintmory.core import telemetry

_LOGGER = logging.getLogger("mintmory.telemetry")

_EXCLUDED_URLS_VARIABLE = "OTEL_PYTHON_EXCLUDED_URLS"
_HEALTH_PATHS = ("/healthz", "/readyz")
_DURATION_HISTOGRAM = "http.server.request.duration"
_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
_REQUEST_METHOD = "http.request.method"
_ROUTE = "http.route"
_RESPONSE_STATUS = "http.response.status_code"
_INTERNAL_ERROR_STATUS = 500


def _debug(error: BaseException) -> None:
    """One DEBUG record naming only the exception class; telemetry never changes a response."""
    _LOGGER.debug("telemetry middleware: %s", type(error).__name__)


@contextlib.contextmanager
def _guard() -> Iterator[None]:
    """Run one telemetry step; drop its failure at DEBUG so the request is unaffected."""
    try:
        yield
    except Exception as error:  # noqa: BLE001 - a telemetry step must never alter the request
        _debug(error)


@functools.cache
def _compile_excluded(value: str) -> tuple[re.Pattern[str], ...]:
    """Compile the comma-separated regexes of ``value``, skipping invalid items.

    Items are stripped and empties ignored; an invalid regex is skipped with one WARNING
    naming it. Cached on the whole value, so the warning is logged at the value's first compile.
    """
    patterns: list[re.Pattern[str]] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            patterns.append(re.compile(item))
        except re.error:
            _LOGGER.warning("invalid %s pattern %r skipped", _EXCLUDED_URLS_VARIABLE, item)
    return tuple(patterns)


def _is_excluded(path: str) -> bool:
    """Whether ``path`` is a health probe or matches an ``OTEL_PYTHON_EXCLUDED_URLS`` regex."""
    if path in _HEALTH_PATHS:
        return True
    patterns: tuple[re.Pattern[str], ...] = ()
    with _guard():
        patterns = _compile_excluded(os.environ.get(_EXCLUDED_URLS_VARIABLE, ""))
    return any(pattern.search(path) is not None for pattern in patterns)


def _decode_headers(headers: Any) -> dict[str, str]:
    """ASGI header bytes as a lower-cased mapping, decoded as latin-1."""
    decoded: dict[str, str] = {}
    for name, value in headers:
        decoded[name.decode("latin-1").lower()] = value.decode("latin-1")
    return decoded


class TelemetryMiddleware:
    """Outermost user middleware: one SERVER span and one duration point per traced request."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or _is_excluded(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")

        headers: dict[str, str] = {}
        with _guard():
            headers = _decode_headers(scope.get("headers") or [])

        context = None
        with _guard():
            context = telemetry.extract_context(headers)

        span_cm = None
        with _guard():
            span_cm = telemetry.span(
                method,
                kind="server",
                context=context,
                record_exception=False,
                set_status_on_exception=False,
            )

        span = None
        if span_cm is not None:
            with _guard():
                span = span_cm.__enter__()

        if span is None:
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        sent: list[int] = []

        async def wrapped_send(message: Any) -> None:
            if message.get("type") == "http.response.start" and not sent:
                sent.append(message.get("status"))
            await send(message)

        error_raised: BaseException | None = None
        try:
            await self.app(scope, receive, wrapped_send)
        except BaseException as error:  # noqa: BLE001 - every way a request ends is handled
            error_raised = error

        route_path: str | None = None
        with _guard():
            route = scope.get("route")
            route_path = None if route is None else route.path

        if route_path is not None:
            with _guard():
                span.update_name(f"{method} {route_path}")

        status: int | None = sent[0] if sent else None
        if status is None and isinstance(error_raised, Exception):
            status = _INTERNAL_ERROR_STATUS

        attributes: dict[str, Any] = {_REQUEST_METHOD: method}
        if route_path is not None:
            attributes[_ROUTE] = route_path
        if status is not None:
            attributes[_RESPONSE_STATUS] = status
        with _guard():
            span.set_attributes(attributes)

        if isinstance(error_raised, Exception):
            with _guard():
                telemetry.mark_error(span, type(error_raised).__name__)
        elif error_raised is None and status is not None and status >= _INTERNAL_ERROR_STATUS:
            with _guard():
                telemetry.mark_error(span, str(status))

        metric_attributes: dict[str, Any] = {_REQUEST_METHOD: method}
        if route_path is not None:
            metric_attributes[_ROUTE] = route_path
        if status is not None:
            metric_attributes[_RESPONSE_STATUS] = status
        with _guard():
            telemetry.record_histogram(
                _DURATION_HISTOGRAM,
                time.perf_counter() - started,
                unit="s",
                boundaries=_DURATION_BUCKETS,
                **metric_attributes,
            )

        with _guard():
            span_cm.__exit__(None, None, None)

        if error_raised is not None:
            raise error_raised
