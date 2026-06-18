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

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from mintmory.core.config import OTelSettings

_F = TypeVar("_F", bound=Callable[..., Any])

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


def init_telemetry(settings: OTelSettings | None = None) -> bool:
    """Idempotent. Returns True if real OTel export is active afterwards.

    No-op (returns False) when ``settings.enabled`` is false or the optional
    ``opentelemetry`` SDK is not installed.
    """
    global _enabled, _tracer, _meter
    if settings is None:
        from mintmory.core.config import OTelSettings

        settings = OTelSettings()
    if not settings.enabled:
        return False
    if _enabled:
        return True
    try:
        from opentelemetry import metrics, trace
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (
            ConsoleMetricExporter,
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except ImportError:
        import structlog

        structlog.get_logger(__name__).warning(
            "otel_enabled_but_sdk_missing", hint="pip install 'mintmory-core[otel]'"
        )
        return False

    resource = Resource.create({"service.name": settings.service_name})
    if settings.exporter == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        span_exporter: Any = OTLPSpanExporter()
    else:
        span_exporter = ConsoleSpanExporter()
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)
    reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    _tracer = trace.get_tracer("mintmory")
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
