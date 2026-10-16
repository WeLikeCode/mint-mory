"""
OpenTelemetry instrumentation seam for MintMory — a no-op shim by default.

Design (docs/OBSERVABILITY.md §4):
  * OFF by default and ZERO import cost when off: ``opentelemetry`` is never
    imported at module load. The hot paths (`add_memory`, `search`, every dreaming
    step, every LLM/embedding call) wrap their bodies in ``span(...)`` / ``traced``
    / metric helpers that compile to nothing until telemetry is initialised.
  * ``opentelemetry-sdk`` is an OPTIONAL extra (``mintmory-core[otel]``). If
    ``MINTMORY_OTEL_ENABLED=true`` but the SDK is absent, we log one warning and
    stay in no-op mode (never crash).
  * Enable with ``init_telemetry(OTelSettings(enabled=True, ...))`` once at startup
    (CLI/API/MCP/scripts). Exporter: ``console`` (stderr) or ``otlp`` (uses the
    standard ``OTEL_EXPORTER_OTLP_*`` env vars).

Use the OTel GenAI semantic conventions for LLM spans (gen_ai.* attributes) so
traces render in any OTel-aware backend.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import socket
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar
from urllib.parse import urlparse

if TYPE_CHECKING:
    from mintmory.core.config import OTelSettings

_F = TypeVar("_F", bound=Callable[..., Any])

_LOGGER = logging.getLogger("mintmory.telemetry")

_DEFAULT_ENDPOINT = "http://localhost:4318"
_ENDPOINT_VARIABLES = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
)
_KNOWN_EXPORTERS = ("otlp", "console", "none")

# Lazily-populated handles; all None == no-op shim.
_enabled: bool = False
_tracer: Any = None
_meter: Any = None
_instruments: dict[str, Any] = {}


class _NoopSpan:
    """Stand-in span when telemetry is disabled (attribute sets are dropped)."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: D401
        return None

    def set_attributes(self, attrs: Mapping[str, Any]) -> None:
        return None

    def record_exception(self, exc: BaseException) -> None:
        return None


def is_enabled() -> bool:
    return _enabled


def _sdk_disabled() -> bool:
    """``OTEL_SDK_DISABLED`` (any case) is the standard kill switch."""
    return os.environ.get("OTEL_SDK_DISABLED", "").strip().lower() == "true"


def _signal_exporter(settings: OTelSettings, signal: str) -> str:
    """One signal's exporter: ``OTEL_<SIGNAL>_EXPORTER`` wins over ``MINTMORY_OTEL_EXPORTER``."""
    raw = os.environ.get(f"OTEL_{signal}_EXPORTER", "").strip()
    if raw:
        for item in raw.split(","):
            candidate = item.strip().lower()
            if candidate in _KNOWN_EXPORTERS:
                return candidate
    return settings.exporter


def init_telemetry(settings: OTelSettings | None = None) -> bool:
    """Idempotent. Returns True if real OTel export is active afterwards.

    No-op (returns False) when telemetry is switched off, no collector answers
    ``auto``, or the optional ``opentelemetry`` SDK is not installed.
    """
    global _enabled, _tracer, _meter
    if settings is None:
        from mintmory.core.config import OTelSettings

        settings = OTelSettings()
    if _enabled:
        return True
    if settings.enabled == "false" or _sdk_disabled():
        return False

    traces_exporter = _signal_exporter(settings, "TRACES")
    metrics_exporter = _signal_exporter(settings, "METRICS")
    if traces_exporter == "none" and metrics_exporter == "none":
        return False

    has_endpoint = any(os.environ.get(name) for name in _ENDPOINT_VARIABLES)
    if (
        not has_endpoint
        and settings.enabled != "true"
        and not _endpoint_reachable(_DEFAULT_ENDPOINT)
    ):
        return False

    if not _sdk_available():
        if settings.enabled == "true" or has_endpoint:
            _LOGGER.warning(
                "OpenTelemetry export requested but the SDK is missing; "
                "install 'mintmory-core[otel]'"
            )
        return False

    from opentelemetry import metrics, trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    resource = Resource.create({"service.name": settings.service_name or "mintmory"})
    if traces_exporter != "none":
        if traces_exporter == "otlp":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            span_exporter: Any = OTLPSpanExporter(**_otlp_exporter_kwargs("TRACES"))
        else:
            span_exporter = ConsoleSpanExporter(out=sys.stderr)
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("mintmory")

    if metrics_exporter != "none":
        if metrics_exporter == "otlp":
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

            metric_exporter: Any = OTLPMetricExporter(**_otlp_exporter_kwargs("METRICS"))
        else:
            metric_exporter = ConsoleMetricExporter(out=sys.stderr)
        reader = PeriodicExportingMetricReader(metric_exporter)
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
        _meter = metrics.get_meter("mintmory")

    _enabled = True
    return True


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[Any]:
    """Context manager: a real span when enabled, else a cheap no-op."""
    if not _enabled or _tracer is None:
        yield _NoopSpan()
        return
    with _tracer.start_as_current_span(name) as sp:
        for key, value in attrs.items():
            if value is not None:
                sp.set_attribute(key, value)
        yield sp


def traced(name: str | None = None) -> Callable[[_F], _F]:
    """Decorator wrapping a function body in ``span(name or qualname)``."""

    def deco(func: _F) -> _F:
        span_name = name or func.__qualname__

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(span_name):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return deco


def _instrument(kind: str, factory_name: str, name: str) -> Any:
    inst = _instruments.get(name)
    if inst is None and _meter is not None:
        inst = getattr(_meter, factory_name)(name)
        _instruments[name] = inst
    return inst


def add_count(name: str, value: int = 1, **attrs: Any) -> None:
    if not _enabled or _meter is None:
        return
    counter = _instrument("counter", "create_counter", name)
    if counter is not None:
        counter.add(value, {k: v for k, v in attrs.items() if v is not None})


def record_value(name: str, value: float, **attrs: Any) -> None:
    if not _enabled or _meter is None:
        return
    hist = _instrument("histogram", "create_histogram", name)
    if hist is not None:
        hist.record(value, {k: v for k, v in attrs.items() if v is not None})


def reset_telemetry() -> None:
    """Test-only: drop the module state so each test starts from the no-op shim."""
    global _enabled, _tracer, _meter
    _enabled = False
    _tracer = None
    _meter = None
    _instruments.clear()


def _sdk_available() -> bool:
    """Whether the optional ``opentelemetry.sdk`` is installed, without importing it."""
    return importlib.util.find_spec("opentelemetry.sdk") is not None


def _endpoint_reachable(url: str, timeout: float = 0.1) -> bool:
    """A quick TCP probe: True when something answers at ``url`` within ``timeout``."""
    parsed = urlparse(url)
    if not parsed.hostname:
        return False
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    try:
        with socket.create_connection((parsed.hostname, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def shutdown_telemetry(timeout_s: float = 2.0) -> None:
    raise NotImplementedError


def _resolve_state(settings: OTelSettings) -> str:
    """The single on/off decision: ``off`` | ``sdk missing`` | ``export`` | ``no collector``."""
    if settings.enabled == "false" or _sdk_disabled():
        return "off"
    if not _sdk_available():
        return "sdk missing"
    if settings.enabled != "true":
        has_endpoint = any(os.environ.get(name) for name in _ENDPOINT_VARIABLES)
        if not has_endpoint and not _endpoint_reachable(_DEFAULT_ENDPOINT):
            return "no collector"
    return "export"


def _traces_endpoint() -> str:
    """The OTLP/HTTP traces URL: the traces variable, else the shared endpoint plus a path."""
    traces_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
    if traces_endpoint:
        return traces_endpoint
    shared_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip() or _DEFAULT_ENDPOINT
    return f"{shared_endpoint}/v1/traces"


def _otlp_exporter_kwargs(signal: str) -> dict[str, Any]:
    """OTLP/HTTP exporter keyword arguments for one signal.

    When a standard endpoint variable applies, no ``endpoint`` is passed: the SDK reads the
    variable itself and appends the signal path. Without one, MintMory passes the local
    default plus ``/v1/traces`` or ``/v1/metrics``.
    """
    shared = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    specific = os.environ.get(f"OTEL_EXPORTER_OTLP_{signal}_ENDPOINT", "").strip()
    if shared or specific:
        return {}
    return {"endpoint": f"{_DEFAULT_ENDPOINT}/v1/{signal.lower()}"}
