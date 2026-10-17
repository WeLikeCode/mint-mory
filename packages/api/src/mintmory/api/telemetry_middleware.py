"""ASGI middleware that traces each HTTP request as a SERVER span.

Stub for the red step of task 2.1: the tests import the seam; the behaviour lands in green.
"""

from __future__ import annotations

from typing import Any


def _compile_excluded(value: str) -> Any:
    raise NotImplementedError


class TelemetryMiddleware:
    def __init__(self, app: Any) -> None:
        raise NotImplementedError

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        raise NotImplementedError
