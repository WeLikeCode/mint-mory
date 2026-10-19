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
from collections.abc import Callable
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


def _safe(step: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run one telemetry step; drop its failure at DEBUG so the request is unaffected.

    The step's result comes back unchanged. A raising step is dropped with one DEBUG record on
    ``mintmory.telemetry`` naming only the exception class, and ``None`` comes back.
    """
    try:
        return step(*args, **kwargs)
    except Exception as error:  # noqa: BLE001 - a telemetry step must never alter the request
        _LOGGER.debug("telemetry: http middleware step failed (%s)", type(error).__name__)
        return None


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
    value = os.environ.get(_EXCLUDED_URLS_VARIABLE, "")
    patterns: tuple[re.Pattern[str], ...] = _safe(_compile_excluded, value) or ()
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

        headers = _safe(_decode_headers, scope.get("headers") or []) or {}
        context = _safe(telemetry.extract_context, headers)

        stack = contextlib.ExitStack()
        span_cm = _safe(
            telemetry.span,
            method,
            kind="server",
            context=context,
            record_exception=False,
            set_status_on_exception=False,
        )
        span = None if span_cm is None else _safe(stack.enter_context, span_cm)
        if span is None:
            _safe(stack.close)
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        sent: list[int] = []

        async def wrapped_send(message: Any) -> None:
            if message.get("type") == "http.response.start" and not sent:
                sent.append(message.get("status"))
            await send(message)

        error: Exception | None = None
        try:
            await self.app(scope, receive, wrapped_send)
        except Exception as exc:
            error = exc
        finally:
            route = scope.get("route")
            route_path = _safe(getattr, route, "path", None) if route is not None else None
            if not isinstance(route_path, str):
                route_path = None
            if route_path is not None:
                _safe(span.update_name, f"{method} {route_path}")

            status = sent[0] if sent else None
            if not isinstance(status, int):
                status = None
            if status is None and error is not None:
                status = _INTERNAL_ERROR_STATUS

            attributes: dict[str, Any] = {_REQUEST_METHOD: method}
            if route_path is not None:
                attributes[_ROUTE] = route_path
            if status is not None:
                attributes[_RESPONSE_STATUS] = status
            _safe(span.set_attributes, attributes)

            if error is not None:
                _safe(telemetry.mark_error, span, type(error).__name__)
            elif status is not None and status >= _INTERNAL_ERROR_STATUS:
                _safe(telemetry.mark_error, span, str(status))

            metric_attributes: dict[str, Any] = {_REQUEST_METHOD: method}
            if route_path is not None:
                metric_attributes[_ROUTE] = route_path
            if status is not None:
                metric_attributes[_RESPONSE_STATUS] = status
            _safe(
                telemetry.record_histogram,
                _DURATION_HISTOGRAM,
                time.perf_counter() - started,
                unit="s",
                boundaries=_DURATION_BUCKETS,
                **metric_attributes,
            )

            _safe(stack.close)

        if error is not None:
            raise error
