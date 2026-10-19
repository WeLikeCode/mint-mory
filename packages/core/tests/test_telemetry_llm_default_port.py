"""The ``gen_ai.chat`` span's default port comes from the URL scheme (FB-005 item 3).

Spec: observability › Outbound calls carry the trace context.

``post_chat_completion`` records ``server.address``/``server.port`` from ``urlsplit(base_url)``.
A ``base_url`` without an explicit port has ``parsed.port is None``; the span must then carry
80 for ``http`` and 443 for ``https``. These tests replace ``urlopen`` with a failure so the
assertion is about the span attributes only and never depends on the network.
"""

from __future__ import annotations

import urllib.error
from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.llm import post_chat_completion

pytest.importorskip("opentelemetry.sdk")


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


def _chat_spans(exporter: Any) -> list[Any]:
    return [span for span in exporter.get_finished_spans() if span.name == "gen_ai.chat"]


@pytest.mark.parametrize(("scheme", "expected_port"), [("http", 80), ("https", 443)])
def test_chat_span_defaults_the_port_from_the_url_scheme(
    scheme: str,
    expected_port: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A URL without a port records 80 for http and 443 for https on the chat span."""
    exporter = _in_memory_span_exporter()
    assert telemetry.init_telemetry(span_exporter=exporter) is True

    def _unreachable(*args: Any, **kwargs: Any) -> Any:
        raise urllib.error.URLError("SENTINEL-NETWORK")

    monkeypatch.setattr("urllib.request.urlopen", _unreachable)

    with pytest.raises(urllib.error.URLError):
        post_chat_completion(
            base_url=f"{scheme}://127.0.0.1",
            api_key=None,
            payload={"model": "m", "messages": []},
            timeout_s=0.5,
            system="test",
            model="m",
        )

    spans = _chat_spans(exporter)
    assert len(spans) == 1, [span.name for span in exporter.get_finished_spans()]
    attributes = dict(spans[0].attributes or {})
    assert attributes.get("server.address") == "127.0.0.1", attributes
    assert attributes.get("server.port") == expected_port, attributes
