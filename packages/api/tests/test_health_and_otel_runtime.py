"""Telemetry-runtime behaviour ``packages/api/tests/test_health_and_otel.py`` depends on (7.1).

Spec: observability › Telemetry enablement modes; observability › Invalid MintMory telemetry
settings fall back; observability › Exporter selection and endpoint resolution.

Task 7.1 updates the API health/OTel tests for the runtime this unit introduces:

* the default enablement mode is the string ``"auto"`` (which probes the collector), so the
  default-off test must pass ``OTelSettings(enabled="false")`` explicitly, and that explicit off
  must stay off without probing;
* ``OTelSettings(enabled=True, ...)`` keeps working (normalised to ``"true"``) and case is
  normalised too;
* the runtime wraps every configured span exporter (``_Scrubbing`` / ``_GuardedSpanExporter``),
  so the exporter-type check must follow ``_inner`` down to the innermost exporter before
  asserting its type.

Accepted finding F-0ad188: ``_Scrubbing`` keeps the exporter it wraps in ``_inner``, as
``_GuardedSpanExporter`` does; the exporter-type check follows ``_inner`` until an object has
none and asserts the innermost exporter's type (the OTLP HTTP span exporter).

``_reset_telemetry`` shadows the root ``conftest.py`` fixture of the same name for this module
only: these tests own the telemetry state they install and stay runnable (and fail by assertion)
against a unit base where ``telemetry.reset_telemetry`` is absent.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.config import OTelSettings

_ENDPOINT_VARIABLES = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
)
_OTLP_HTTP = "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"


@pytest.fixture(autouse=True)
def _reset_telemetry() -> Iterator[None]:
    """Own this module's telemetry state; tolerate the helper being absent (unit base)."""
    reset = getattr(telemetry, "reset_telemetry", None)
    if reset is not None:
        reset()
    yield
    if reset is not None:
        reset()


def _innermost(exporter: Any) -> tuple[Any, int]:
    """Follow ``_inner`` wrappers down to the real exporter and count the hops."""
    hops = 0
    while hasattr(exporter, "_inner"):
        exporter = exporter._inner
        hops += 1
    return exporter, hops


@pytest.mark.l4("C-9d8f8f9c")
def test_explicit_false_enabled_returns_false_without_probing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OTelSettings(enabled="false")`` is honoured and never probes for a collector.

    The runtime's default is ``"auto"`` (which probes); explicit off short-circuits before the
    reachability check. The auto branch is the positive control: it too ends off here, but the
    probe is what decided that, so the test asserts a real answer and not only the zero ``False``.
    """
    monkeypatch.delenv("MINTMORY_OTEL_ENABLED", raising=False)
    for variable in _ENDPOINT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)

    assert OTelSettings(enabled="false").enabled == "false"
    assert hasattr(telemetry, "_endpoint_reachable"), (
        "the runtime must expose the reachability probe seam"
    )

    probes: list[str] = []

    def _unreachable(url: str, timeout: float = 0.1) -> bool:
        probes.append(url)
        return False

    monkeypatch.setattr(telemetry, "_endpoint_reachable", _unreachable)

    assert telemetry.init_telemetry(OTelSettings(enabled="false")) is False
    assert probes == [], "explicit off must not probe for a collector"

    assert telemetry.init_telemetry(OTelSettings()) is False
    assert probes != [], "auto with no endpoint variable must probe the default endpoint"


@pytest.mark.l4("C-e1c42220")
def test_enabled_setting_normalises_booleans_and_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OTelSettings`` normalises booleans and case into the enablement Literal."""
    monkeypatch.delenv("MINTMORY_OTEL_ENABLED", raising=False)

    assert OTelSettings().enabled == "auto"
    assert OTelSettings(enabled=True).enabled == "true"
    assert OTelSettings(enabled=False).enabled == "false"

    for raw, expected in (("TRUE", "true"), ("False", "false"), ("AUTO", "auto")):
        monkeypatch.setenv("MINTMORY_OTEL_ENABLED", raw)
        assert OTelSettings().enabled == expected, raw


@pytest.mark.l4("C-6fc7f4c6")
def test_configured_otlp_span_exporter_chain_ends_at_the_otlp_http_exporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The span processor receives the scrubber, and the OTLP HTTP exporter is the innermost one.

    The runtime wraps the configured exporter (``_Scrubbing`` on the outside, then
    ``_GuardedSpanExporter``), so the exporter-type check must walk ``_inner`` rather than look
    at the first object it finds.
    """
    pytest.importorskip("opentelemetry.sdk.trace")
    te_mod = pytest.importorskip("opentelemetry.exporter.otlp.proto.http.trace_exporter")

    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "otlp")
    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "none")

    assert telemetry.init_telemetry() is True

    provider = getattr(telemetry, "_tracer_provider", None)
    assert provider is not None, "init did not install a tracer provider"
    processor = provider._active_span_processor._span_processors[0]
    exporter = processor.span_exporter

    innermost, hops = _innermost(exporter)
    assert hops >= 1, "the configured span exporter must be wrapped before the processor sees it"
    assert isinstance(innermost, te_mod.OTLPSpanExporter)
    assert type(innermost).__module__ + "." + type(innermost).__qualname__ == _OTLP_HTTP
