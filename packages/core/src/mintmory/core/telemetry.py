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
  * Enable with ``init_telemetry(OTelSettings(...))`` once at startup
    (CLI/API/MCP/scripts). Exporter: ``console`` (stderr) or ``otlp`` (uses the
    standard ``OTEL_EXPORTER_OTLP_*`` env vars).
  * Export never runs on the calling thread and never raises: a guard around each
    configured exporter turns a failure into ``FAILURE`` and logs it once per
    signal per failure streak. ``init_telemetry`` never raises: a bad exporter is
    swallowed, the runtime reverts to the no-op shim and one WARNING names only
    the exception class.

Use the OTel GenAI semantic conventions for LLM spans (gen_ai.* attributes) so
traces render in any OTel-aware backend.
"""

from __future__ import annotations

import atexit
import contextlib
import importlib.metadata
import importlib.util
import logging
import os
import socket
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar
from urllib.parse import unquote, urlparse

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
_SUPPORTED_PROTOCOL = "http/protobuf"
_EXPORTER_LOGGER_NAME = "opentelemetry.exporter.otlp.proto.http"
_SERVICE_NAMESPACE = "mintmory"

# Lazily-populated handles; all None == no-op shim.
_enabled: bool = False
_tracer: Any = None
_meter: Any = None
_instruments: dict[str, Any] = {}
_tracer_provider: Any = None
_meter_provider: Any = None
_saved_exporter_level: int | None = None
_atexit_registered: bool = False
_shutdown_lock = threading.Lock()


class _NoopSpan:
    """Stand-in span when telemetry is disabled (attribute sets are dropped)."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: D401
        return None

    def set_attributes(self, attrs: Mapping[str, Any]) -> None:
        return None

    def record_exception(self, exc: BaseException) -> None:
        return None

    def update_name(self, name: str) -> None:
        return None


def is_enabled() -> bool:
    return _enabled


def _sdk_disabled() -> bool:
    """``OTEL_SDK_DISABLED`` (any case) is the standard kill switch."""
    return os.environ.get("OTEL_SDK_DISABLED", "").strip().lower() == "true"


def _has_endpoint_variable() -> bool:
    """Whether any standard endpoint variable is set."""
    return any(os.environ.get(name) for name in _ENDPOINT_VARIABLES)


def _resolve_exporter(settings: OTelSettings, signal: str) -> str:
    """One signal's exporter: ``OTEL_<SIGNAL>_EXPORTER`` wins over ``MINTMORY_OTEL_EXPORTER``.

    The standard variable may be a comma list; the first known item wins, else the
    MintMory default. Anything but a single known token logs one WARNING naming the
    variable.
    """
    variable = f"OTEL_{signal}_EXPORTER"
    raw = os.environ.get(variable, "").strip()
    if not raw:
        return settings.exporter
    normalised = raw.lower()
    if normalised in _KNOWN_EXPORTERS:
        return normalised
    known = [item.strip().lower() for item in raw.split(",")]
    known = [item for item in known if item in _KNOWN_EXPORTERS]
    _LOGGER.warning("%s=%r is not a known exporter; falling back", variable, raw)
    if known:
        return known[0]
    return settings.exporter


def _check_protocol(signal: str, warned: set[str]) -> None:
    """Only ``http/protobuf`` is supported; a per-signal variable wins, the shared one warns."""
    specific_var = f"OTEL_EXPORTER_OTLP_{signal}_PROTOCOL"
    specific = os.environ.get(specific_var, "").strip()
    if specific:
        if specific != _SUPPORTED_PROTOCOL:
            _LOGGER.warning(
                "%s=%r is not supported; using %s", specific_var, specific, _SUPPORTED_PROTOCOL
            )
        return
    shared = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "").strip()
    if shared and shared != _SUPPORTED_PROTOCOL and "OTEL_EXPORTER_OTLP_PROTOCOL" not in warned:
        warned.add("OTEL_EXPORTER_OTLP_PROTOCOL")
        _LOGGER.warning(
            "OTEL_EXPORTER_OTLP_PROTOCOL=%r is not supported; using %s",
            shared,
            _SUPPORTED_PROTOCOL,
        )


def _resource_attributes_from_env() -> dict[str, str]:
    """Parse ``OTEL_RESOURCE_ATTRIBUTES`` (``k=v`` pairs, values percent-decoded)."""
    raw = os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "").strip()
    attributes: dict[str, str] = {}
    for pair in raw.split(","):
        key, separator, value = pair.partition("=")
        key = key.strip()
        if separator and key:
            attributes[key] = unquote(value.strip())
    return attributes


def _service_version() -> str:
    """The installed ``mintmory-core`` version, or ``unknown`` when it cannot be read."""
    try:
        return importlib.metadata.version("mintmory-core")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _service_name(settings: OTelSettings, default_service_name: str | None) -> str:
    """The resource's ``service.name``: standard variables before MintMory's, else the default."""
    explicit = os.environ.get("OTEL_SERVICE_NAME", "").strip()
    if explicit:
        return explicit
    from_env = _resource_attributes_from_env().get("service.name")
    if from_env:
        return from_env
    if settings.service_name:
        return settings.service_name
    return default_service_name or "mintmory"


def _build_resource(settings: OTelSettings, default_service_name: str | None) -> Any:
    """The SDK ``Resource``: MintMory defaults, overridden by ``OTEL_RESOURCE_ATTRIBUTES``."""
    from opentelemetry.sdk.resources import Resource

    attributes: dict[str, Any] = {
        "service.namespace": _SERVICE_NAMESPACE,
        "service.version": _service_version(),
        "service.instance.id": uuid.uuid4().hex,
    }
    attributes.update(_resource_attributes_from_env())
    attributes["service.name"] = _service_name(settings, default_service_name)
    return Resource.create(attributes)


def _mute_exporter_logger() -> None:
    """Silence the OTLP/HTTP exporter's own retry spam while telemetry runs."""
    global _saved_exporter_level
    if _saved_exporter_level is None:
        logger = logging.getLogger(_EXPORTER_LOGGER_NAME)
        _saved_exporter_level = logger.level
        logger.setLevel(logging.CRITICAL)


def _restore_exporter_logger() -> None:
    """Put the OTLP/HTTP exporter logger back to the level saved by the first mute."""
    global _saved_exporter_level
    if _saved_exporter_level is not None:
        logging.getLogger(_EXPORTER_LOGGER_NAME).setLevel(_saved_exporter_level)
        _saved_exporter_level = None


def _log_export_failure(signal: str) -> None:
    """WARNING when an endpoint was configured, else DEBUG: one line per failure streak."""
    message = f"telemetry: {signal} export failed"
    if _has_endpoint_variable():
        _LOGGER.warning(message)
    else:
        _LOGGER.debug(message)


def _release_globals() -> None:
    """Drop the API's global providers the way OpenTelemetry's own test utilities do."""
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None


def _set_tracer_provider(provider: Any) -> None:
    global _tracer, _tracer_provider
    from opentelemetry import trace

    _tracer_provider = provider
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("mintmory")


def _set_meter_provider(provider: Any) -> None:
    global _meter, _meter_provider
    from opentelemetry import metrics

    _meter_provider = provider
    metrics.set_meter_provider(provider)
    _meter = metrics.get_meter("mintmory")


def _otlp_exporter_kwargs(settings: OTelSettings, signal: str) -> dict[str, Any]:
    """OTLP/HTTP exporter keyword arguments for one signal.

    When a standard endpoint variable applies, no ``endpoint`` is passed: the SDK reads the
    variable itself and appends the signal path. Without one, MintMory passes the local
    default plus ``/v1/traces`` or ``/v1/metrics``. A standard timeout variable also defers to
    the SDK, so an invalid one surfaces as the exporter's own ``ValueError``.
    """
    kwargs: dict[str, Any] = {}
    shared = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    specific = os.environ.get(f"OTEL_EXPORTER_OTLP_{signal}_ENDPOINT", "").strip()
    if not (shared or specific):
        kwargs["endpoint"] = f"{_DEFAULT_ENDPOINT}/v1/{signal.lower()}"
    if not (
        os.environ.get(f"OTEL_EXPORTER_OTLP_{signal}_TIMEOUT")
        or os.environ.get("OTEL_EXPORTER_OTLP_TIMEOUT")
    ):
        kwargs["timeout"] = settings.export_timeout_s
    return kwargs


def _scrub_span(span: Any) -> Any:
    """Rebuild a finished span with exception messages and ERROR descriptions dropped.

    Exception events keep only ``exception.type``; an ERROR status loses its description. Every
    other field is carried over untouched, for MintMory's spans and library spans alike.
    """
    from opentelemetry.sdk.trace import Event, ReadableSpan
    from opentelemetry.trace import Status, StatusCode

    events: list[Any] = []
    for event in span.events:
        if event.name == "exception":
            attributes = {
                key: value
                for key, value in dict(event.attributes or {}).items()
                if key == "exception.type"
            }
            events.append(Event(name=event.name, attributes=attributes, timestamp=event.timestamp))
        else:
            events.append(event)

    status = span.status
    if status is not None and status.status_code == StatusCode.ERROR:
        status = Status(StatusCode.ERROR)

    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=span.attributes,
        events=events,
        links=span.links,
        kind=span.kind,
        instrumentation_info=span._instrumentation_info,
        status=status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class _Scrubbing:
    """Outermost span-exporter wrapper: scrubs every span before the real exporter sees it."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def export(self, spans: Any) -> Any:
        return self._inner.export([_scrub_span(span) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return bool(self._inner.force_flush(timeout_millis))


class _GuardedSpanExporter:
    """Wraps a span exporter so a failing export never raises and never floods the log."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._failing = False

    def export(self, spans: Any) -> Any:
        from opentelemetry.sdk.trace.export import SpanExportResult

        try:
            result = self._inner.export(spans)
        except Exception:  # noqa: BLE001 - the guard's whole point is to swallow it
            result = SpanExportResult.FAILURE
        if result == SpanExportResult.FAILURE:
            if not self._failing:
                self._failing = True
                _log_export_failure("trace")
            return SpanExportResult.FAILURE
        if self._failing:
            self._failing = False
            _LOGGER.info("telemetry: trace export recovered")
        return result

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return bool(self._inner.force_flush(timeout_millis))


def _build_guarded_metric_exporter() -> type:
    """The metric guard class, built on first use so importing the SDK base stays lazy.

    ``_GuardedMetricExporter`` must be a ``MetricExporter`` for a
    ``PeriodicExportingMetricReader`` to read its ``_preferred_temporality`` /
    ``_preferred_aggregation``, but importing ``opentelemetry.sdk`` at module load would defeat
    the no-op shim's zero import cost. Module-level ``__getattr__`` builds it once instead.
    """
    from opentelemetry.sdk.metrics.export import MetricExporter

    class _GuardedMetricExporter(MetricExporter):
        """Wraps a metric exporter so a failing export never raises and never floods the log."""

        def __init__(self, inner: Any) -> None:
            super().__init__(
                preferred_temporality=getattr(inner, "_preferred_temporality", None),
                preferred_aggregation=getattr(inner, "_preferred_aggregation", None),
            )
            self._inner = inner
            self._failing = False

        def export(self, metrics_data: Any, timeout_millis: float = 10_000, **kwargs: Any) -> Any:
            from opentelemetry.sdk.metrics.export import MetricExportResult

            try:
                result = self._inner.export(metrics_data, timeout_millis, **kwargs)
            except Exception:  # noqa: BLE001 - the guard's whole point is to swallow it
                result = MetricExportResult.FAILURE
            if result == MetricExportResult.FAILURE:
                if not self._failing:
                    self._failing = True
                    _log_export_failure("metric")
                return MetricExportResult.FAILURE
            if self._failing:
                self._failing = False
                _LOGGER.info("telemetry: metric export recovered")
            return result

        def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
            self._inner.shutdown(timeout_millis, **kwargs)

        def force_flush(self, timeout_millis: float = 10_000) -> bool:
            return bool(self._inner.force_flush(timeout_millis))

    return _GuardedMetricExporter


def __getattr__(name: str) -> Any:
    """Build ``_GuardedMetricExporter`` on first access, so the SDK import stays lazy."""
    if name == "_GuardedMetricExporter":
        exporter_class = _guarded_metric_exporter_class()
        globals()[name] = exporter_class
        return exporter_class
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_cached_metric_guard: type | None = None


def _guarded_metric_exporter_class() -> type:
    """The single cached ``_GuardedMetricExporter`` class, built on first use."""
    global _cached_metric_guard
    if _cached_metric_guard is None:
        _cached_metric_guard = _build_guarded_metric_exporter()
    return _cached_metric_guard


def _build_tracer_provider(
    resource: Any,
    exporter_kind: str,
    settings: OTelSettings,
    injected_exporter: Any,
) -> Any:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

    if injected_exporter is not None:
        scrubbed: Any = _Scrubbing(injected_exporter)
        provider = TracerProvider(resource=resource, shutdown_on_exit=False)
        provider.add_span_processor(SimpleSpanProcessor(scrubbed))
        return provider
    if exporter_kind == "otlp":
        _mute_exporter_logger()
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter: Any = OTLPSpanExporter(**_otlp_exporter_kwargs(settings, "TRACES"))
    else:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        exporter = ConsoleSpanExporter(out=sys.stderr)
    guarded: Any = _Scrubbing(_GuardedSpanExporter(exporter))
    provider = TracerProvider(resource=resource, shutdown_on_exit=False)
    provider.add_span_processor(BatchSpanProcessor(guarded))
    return provider


def _build_meter_provider(
    resource: Any,
    exporter_kind: str,
    settings: OTelSettings,
    injected_reader: Any,
) -> Any:
    from opentelemetry.sdk.metrics import MeterProvider

    if injected_reader is not None:
        return MeterProvider(
            resource=resource, metric_readers=[injected_reader], shutdown_on_exit=False
        )
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    if exporter_kind == "otlp":
        _mute_exporter_logger()
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

        exporter: Any = OTLPMetricExporter(**_otlp_exporter_kwargs(settings, "METRICS"))
    else:
        from opentelemetry.sdk.metrics.export import ConsoleMetricExporter

        exporter = ConsoleMetricExporter(out=sys.stderr)
    guarded: Any = _guarded_metric_exporter_class()(exporter)
    reader = PeriodicExportingMetricReader(
        guarded, export_timeout_millis=settings.export_timeout_s * 1000
    )
    return MeterProvider(resource=resource, metric_readers=[reader], shutdown_on_exit=False)


def _register_atexit() -> None:
    """Register the single process-wide shutdown hook, re-armed only by ``reset_telemetry``."""
    global _atexit_registered
    if not _atexit_registered:
        atexit.register(shutdown_telemetry)
        _atexit_registered = True


def _activate(
    settings: OTelSettings,
    *,
    default_service_name: str,
    traces_exporter: str,
    metrics_exporter: str,
    span_exporter: Any,
    metric_reader: Any,
) -> bool:
    """Build and install the providers; the caller holds ``_shutdown_lock``."""
    global _enabled

    resource = _build_resource(settings, default_service_name)

    warned: set[str] = set()
    if traces_exporter == "otlp":
        _check_protocol("TRACES", warned)
    if metrics_exporter == "otlp":
        _check_protocol("METRICS", warned)

    if traces_exporter != "none":
        _set_tracer_provider(
            _build_tracer_provider(resource, traces_exporter, settings, span_exporter)
        )
    if metrics_exporter != "none":
        _set_meter_provider(
            _build_meter_provider(resource, metrics_exporter, settings, metric_reader)
        )

    _enabled = True
    _register_atexit()
    return True


def init_telemetry(
    settings: OTelSettings | None = None,
    *,
    default_service_name: str = "mintmory",
    span_exporter: Any = None,
    metric_reader: Any = None,
) -> bool:
    """Idempotent. Returns True if real OTel export is active afterwards.

    No-op (returns False) when telemetry is switched off, no collector answers
    ``auto``, or the optional ``opentelemetry`` SDK is not installed. An injected
    exporter or reader enables telemetry regardless of the environment and never
    builds a configured exporter.
    """
    global _enabled
    if settings is None:
        from mintmory.core.config import OTelSettings

        settings = OTelSettings()
    if _enabled:
        return True

    injected = span_exporter is not None or metric_reader is not None
    if injected:
        if not _sdk_available():
            _LOGGER.warning(
                "OpenTelemetry export requested but the SDK is missing; "
                "install 'mintmory-core[otel]'"
            )
            return False
        traces_exporter = "injected" if span_exporter is not None else "none"
        metrics_exporter = "injected" if metric_reader is not None else "none"
    else:
        traces_exporter = _resolve_exporter(settings, "TRACES")
        metrics_exporter = _resolve_exporter(settings, "METRICS")
        if traces_exporter == "none" and metrics_exporter == "none":
            return False
        state = _resolve_state(settings)
        if state == "off" or state == "no collector":
            return False
        if state == "sdk missing":
            if settings.enabled == "true" or _has_endpoint_variable():
                _LOGGER.warning(
                    "OpenTelemetry export requested but the SDK is missing; "
                    "install 'mintmory-core[otel]'"
                )
            return False

    with _shutdown_lock:
        if _enabled:
            return True
        try:
            return _activate(
                settings,
                default_service_name=default_service_name,
                traces_exporter=traces_exporter,
                metrics_exporter=metrics_exporter,
                span_exporter=span_exporter,
                metric_reader=metric_reader,
            )
        except Exception as error:  # noqa: BLE001 - init must never raise
            _teardown(2.0)
            _LOGGER.warning("telemetry disabled: init failed (%s)", type(error).__name__)
            return False


@contextmanager
def span(
    name: str,
    *,
    kind: str = "internal",
    context: Any = None,
    record_exception: bool = True,
    set_status_on_exception: bool = True,
    **attrs: Any,
) -> Iterator[Any]:
    """Context manager: a real span when enabled, else a cheap no-op.

    ``kind`` maps ``"internal"``/``"server"``/``"client"`` to ``SpanKind``; any other value
    maps to INTERNAL. ``context`` makes the span an explicit child of that context.
    ``record_exception`` and ``set_status_on_exception`` reach the tracer unchanged, so callers
    can suppress the SDK's automatic exception event and ERROR status.
    """
    tracer = _tracer
    if not _enabled or tracer is None:
        yield _NoopSpan()
        return
    from opentelemetry.trace import SpanKind

    kinds = {
        "internal": SpanKind.INTERNAL,
        "server": SpanKind.SERVER,
        "client": SpanKind.CLIENT,
    }
    with tracer.start_as_current_span(
        name,
        context=context,
        kind=kinds.get(kind, SpanKind.INTERNAL),
        record_exception=record_exception,
        set_status_on_exception=set_status_on_exception,
    ) as sp:
        for key, value in attrs.items():
            if value is not None:
                _set_attribute_safe(sp, key, value)
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


def _instrument(kind: str, factory_name: str, name: str, meter: Any, **options: Any) -> Any:
    inst = _instruments.get(name)
    if inst is None and meter is not None:
        inst = getattr(meter, factory_name)(name, **options)
        _instruments[name] = inst
    return inst


def add_count(name: str, value: int = 1, **attrs: Any) -> None:
    meter = _meter
    if not _enabled or meter is None:
        return
    try:
        counter = _instrument("counter", "create_counter", name, meter)
        if counter is not None:
            counter.add(value, {k: v for k, v in attrs.items() if v is not None})
    except Exception:  # noqa: BLE001 - a metric must never break the caller
        return


def record_value(name: str, value: float, *, unit: str | None = None, **attrs: Any) -> None:
    meter = _meter
    if not _enabled or meter is None:
        return
    try:
        options: dict[str, Any] = {} if unit is None else {"unit": unit}
        hist = _instrument("histogram", "create_histogram", name, meter, **options)
        if hist is not None:
            hist.record(value, {k: v for k, v in attrs.items() if v is not None})
    except Exception:  # noqa: BLE001 - a metric must never break the caller
        return


def _teardown(timeout_s: float) -> None:
    """Shutdown what was built, drop the module state and restore the logger level.

    The caller holds ``_shutdown_lock``.
    """
    global _enabled, _tracer, _meter, _tracer_provider, _meter_provider

    providers = [
        provider for provider in (_tracer_provider, _meter_provider) if provider is not None
    ]
    if providers:

        def _shutdown() -> None:
            for provider in providers:
                with contextlib.suppress(Exception):
                    provider.shutdown()

        thread = threading.Thread(target=_shutdown, name="mintmory-telemetry-shutdown", daemon=True)
        thread.start()
        thread.join(timeout_s)
        _release_globals()

    _enabled = False
    _tracer = None
    _meter = None
    _tracer_provider = None
    _meter_provider = None
    _instruments.clear()
    _restore_exporter_logger()


def shutdown_telemetry(timeout_s: float = 2.0) -> None:
    """The one teardown: safe to repeat and without a prior init."""
    with _shutdown_lock:
        _teardown(timeout_s)


def reset_telemetry() -> None:
    """Test-only: drop the module state so each test starts from the no-op shim."""
    global _atexit_registered
    shutdown_telemetry(0.5)
    atexit.unregister(shutdown_telemetry)
    _atexit_registered = False


def _sdk_available() -> bool:
    """Whether the optional ``opentelemetry.sdk`` is installed, without importing it.

    ``find_spec`` raises ``ModuleNotFoundError`` (an ``ImportError``) when the package is absent
    and can raise ``ValueError`` for a namespace/``__spec__`` quirk; both mean "not available"
    rather than a crash.
    """
    try:
        return importlib.util.find_spec("opentelemetry.sdk") is not None
    except (ImportError, ValueError):
        return False


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


def _resolve_state(settings: OTelSettings) -> str:
    """The single on/off decision: ``off`` | ``sdk missing`` | ``export`` | ``no collector``."""
    if settings.enabled == "false" or _sdk_disabled():
        return "off"
    if not _sdk_available():
        return "sdk missing"
    if (
        settings.enabled != "true"
        and not _has_endpoint_variable()
        and not _endpoint_reachable(_DEFAULT_ENDPOINT)
    ):
        return "no collector"
    return "export"


def _traces_endpoint() -> str:
    """The OTLP/HTTP traces URL: the traces variable, else the shared endpoint plus a path."""
    traces_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
    if traces_endpoint:
        return traces_endpoint
    shared_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip() or _DEFAULT_ENDPOINT
    return f"{shared_endpoint}/v1/traces"


def mark_error(span: Any, error_type: str) -> None:
    """The one way MintMory marks a span failed: ERROR status, no description, ``error.type``.

    A no-op for ``_NoopSpan`` (telemetry off, or traces ``none``) and any span without a
    status method. Never raises, so hot paths call it without a guard.
    """
    try:
        from opentelemetry.trace import Status, StatusCode
    except Exception:  # noqa: BLE001 - the SDK may be absent; marking must never raise
        return
    try:
        set_status = getattr(span, "set_status", None)
        if set_status is not None:
            set_status(Status(StatusCode.ERROR))
        set_attribute = getattr(span, "set_attribute", None)
        if set_attribute is not None:
            set_attribute("error.type", error_type)
    except Exception:  # noqa: BLE001 - marking must never raise
        return


def run_in_context(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``fn`` so each call runs in a fresh copy of the caller's context.

    A thread-pool worker starts with an empty context, which drops the trace: spans opened
    there begin a new trace. Capturing the caller's context here and attaching it inside the
    wrapper keeps the worker's spans in the caller's trace. With telemetry off ``fn`` is
    returned unchanged, so the no-op shim keeps its zero import cost.
    """
    if not _enabled:
        return fn
    from opentelemetry import context as otel_context

    captured = otel_context.get_current()

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = otel_context.attach(captured)
        try:
            return fn(*args, **kwargs)
        finally:
            otel_context.detach(token)

    return wrapper


class _PhaseHandle:
    """Reports a timed search stage's result count back to :func:`search_phase`."""

    def __init__(self) -> None:
        self.count = 0

    def set_count(self, count: int) -> None:
        self.count = count


def _set_result_count(phase_span: Any, count: int) -> None:
    """Set ``mintmory.result_count`` on the stage span; never raise into the caller."""
    try:
        phase_span.set_attribute("mintmory.result_count", count)
    except Exception:  # noqa: BLE001 - an attribute must never break a search
        return


def _record_search_latency(name: str, started: float) -> None:
    """Record the ``mintmory.search.latency_ms`` point; never raise into the caller."""
    try:
        record_value(
            "mintmory.search.latency_ms",
            (time.perf_counter() - started) * 1000.0,
            unit="ms",
            phase=name,
        )
    except Exception:  # noqa: BLE001 - a metric must never break a search
        return


_span_context = span


@contextmanager
def search_phase(name: str, *, span: bool = True) -> Iterator[_PhaseHandle]:
    """Time one search stage: its ``mintmory.search.<name>`` span, count and latency point.

    The block reports the stage's result count through ``set_count(n)`` (0 by default). The
    latency point is recorded even when the block raises; a failing stage is marked with
    ``mark_error`` before the exception is re-raised. With ``span`` false only the point is
    recorded, and with telemetry off every call is a no-op.
    """
    handle = _PhaseHandle()
    started = time.perf_counter()
    if not span:
        try:
            yield handle
        finally:
            _record_search_latency(name, started)
        return
    with _span_context(f"mintmory.search.{name}") as phase_span:
        try:
            yield handle
        except Exception as error:
            mark_error(phase_span, type(error).__name__)
            raise
        finally:
            _set_result_count(phase_span, handle.count)
            _record_search_latency(name, started)


def timed_phase(name: str) -> Callable[[_F], _F]:
    """Wrap a search stage so it records only its ``mintmory.search.latency_ms`` point."""

    def deco(func: _F) -> _F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with search_phase(name, span=False):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return deco


_embedding_active: ContextVar[bool] = ContextVar("mintmory_embedding_active", default=False)


def _embedding_batch_size(args: tuple[Any, ...], kwargs: dict[str, Any]) -> int:
    """The number of texts in an ``embed``/``embed_batch`` call (``embed`` is always one)."""
    if args:
        first = args[0]
    elif kwargs:
        first = next(iter(kwargs.values()))
    else:
        return 0
    if isinstance(first, str):
        return 1
    try:
        return len(first)
    except TypeError:
        return 1


def _record_embed_latency(provider: str, model: str, started: float) -> None:
    """Record the ``mintmory.embed.latency_ms`` point; never raise into the caller."""
    try:
        record_value(
            "mintmory.embed.latency_ms",
            (time.perf_counter() - started) * 1000.0,
            unit="ms",
            provider=provider,
            model=model or None,
        )
    except Exception:  # noqa: BLE001 - a metric must never break an embedding
        return


def embed_span[F: Callable[..., Any]](fn: F) -> F:
    """Decorate a public ``embed``/``embed_batch`` with one span and latency point per call.

    The embedder supplies its ``provider`` class attribute, ``model_name`` and ``dimensions``.
    A public method calling another (``embed`` delegating to ``embed_batch`` or the reverse)
    still records once: a module ``ContextVar`` re-entrancy guard keeps only the outermost call.
    A failing call marks its span with ``mark_error`` and still records its latency point.
    """

    @wraps(fn)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        if _embedding_active.get():
            return fn(self, *args, **kwargs)
        if not _enabled:
            return fn(self, *args, **kwargs)
        token = _embedding_active.set(True)
        started = time.perf_counter()
        provider = getattr(self, "provider", "")
        model = getattr(self, "model_name", "") or ""
        attrs: dict[str, Any] = {
            "mintmory.embed.provider": provider,
            "gen_ai.request.model": model or None,
            "mintmory.embed.batch_size": _embedding_batch_size(args, kwargs),
            "mintmory.embed.dim": getattr(self, "dimensions", None),
        }
        try:
            with _span_context("mintmory.embed", **attrs) as embed_span_obj:
                try:
                    return fn(self, *args, **kwargs)
                except Exception as error:
                    mark_error(embed_span_obj, type(error).__name__)
                    raise
                finally:
                    _record_embed_latency(provider, model, started)
        finally:
            _embedding_active.reset(token)

    return wrapper  # type: ignore[return-value]


def set_attributes(**attrs: Any) -> None:
    """Set attributes on the span that is current when called; never raises.

    A no-op when telemetry is off. None values are dropped, matching :func:`span`. Used to
    report the ``index-tree`` counters on the command span that is active around the walk.
    """
    if not _enabled:
        return
    try:
        from opentelemetry import trace

        current = trace.get_current_span()
        if current is None or not current.is_recording():
            return
        current.set_attributes({key: value for key, value in attrs.items() if value is not None})
    except Exception:  # noqa: BLE001 - an attribute must never break the caller
        return


def counts_added[F: Callable[..., Any]](fn: F) -> F:
    """Count ``mintmory.memories.added`` for each record ``fn`` returns, by category.

    ``fn`` is an ``add_memory`` call returning a memory record; the wrapper records the
    counter with ``category=record.category.value`` and marks itself with
    ``__mintmory_counter__`` so both storage backends can be checked for the shared
    decorator. With telemetry off ``add_count`` is already a no-op.
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        record = fn(*args, **kwargs)
        try:
            category = record.category.value
        except Exception:  # noqa: BLE001 - the counter must never break a write
            return record
        try:
            add_count("mintmory.memories.added", category=category)
        except Exception:  # noqa: BLE001 - the counter must never break a write
            return record
        return record

    wrapper.__mintmory_counter__ = "mintmory.memories.added"  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


def _set_attribute_safe(span: Any, key: str, value: Any) -> None:
    """Set one span attribute; never raise into the caller."""
    try:
        span.set_attribute(key, value)
    except Exception:  # noqa: BLE001 - an attribute must never break the wrapped work
        return


@contextmanager
def file_span(name: str, *, suffix: str, size_bytes: int) -> Iterator[Any]:
    """Wrap one per-file conversion/caption with ``mintmory.outcome`` and ERROR on failure.

    The span carries ``mintmory.file.suffix`` and ``mintmory.file.size_bytes`` from the start
    and ``mintmory.outcome=ok`` when the block returns. A failing block is set to
    ``mintmory.outcome=failed``, marked with ``mark_error`` (the exception class name) and its
    exception re-raised unchanged, so the command's own ``ConversionError``/``VisionError``
    handlers still count it. With telemetry off every call is a no-op.
    """
    attrs: dict[str, Any] = {
        "mintmory.file.suffix": suffix,
        "mintmory.file.size_bytes": size_bytes,
    }
    with span(name, **attrs) as file_span_obj:
        try:
            yield file_span_obj
        except Exception as error:
            _set_attribute_safe(file_span_obj, "mintmory.outcome", "failed")
            mark_error(file_span_obj, type(error).__name__)
            raise
        _set_attribute_safe(file_span_obj, "mintmory.outcome", "ok")


def command_span(name: str) -> Callable[[_F], _F]:
    """Decorate a CLI command so it runs inside a root span ``mintmory.cli.<name>``.

    Spaces in ``name`` become dots. ``typer.Exit`` is a ``RuntimeError`` subclass, so the span
    is opened with ``record_exception=False`` and ``set_status_on_exception=False`` and marked
    only through ``mark_error``: an exit with code 0 (``--help``, a clean ``typer.Exit()``) stays
    UNSET, while a non-zero exit or any other exception becomes ERROR with ``error.type``. With
    telemetry off every call is a no-op.
    """

    span_name = "mintmory.cli." + name.replace(" ", ".")

    def deco(fn: _F) -> _F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(
                span_name,
                record_exception=False,
                set_status_on_exception=False,
            ) as command_span_obj:
                try:
                    return fn(*args, **kwargs)
                except BaseException as error:
                    if _command_exit_code(error) != 0:
                        mark_error(command_span_obj, type(error).__name__)
                    raise

        return wrapper  # type: ignore[return-value]

    return deco


def _command_exit_code(error: BaseException) -> int:
    """The exit code of a ``typer.Exit``/``SystemExit``; any other exception counts non-zero."""
    code = getattr(error, "exit_code", None)
    if code is None and isinstance(error, SystemExit):
        code = error.code
    if code is None:
        return 1
    if isinstance(code, int):
        return code
    return 1


_trace_context_propagator: Any = None


def _fixed_trace_context_propagator() -> Any:
    """The fixed W3C trace-context propagator used for outbound headers (never ``baggage``)."""
    global _trace_context_propagator
    if _trace_context_propagator is None:
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

        _trace_context_propagator = TraceContextTextMapPropagator()
    return _trace_context_propagator


def inject_trace_headers(headers: dict[str, str]) -> dict[str, str]:
    """Write the current span's ``traceparent``/``tracestate`` into ``headers``; never raises.

    A fixed W3C trace-context propagator is used, so an inbound ``baggage`` (which may carry user
    data) is never forwarded to a possibly third-party endpoint. With telemetry off the carrier is
    returned untouched.
    """
    if not _enabled:
        return headers
    try:
        _fixed_trace_context_propagator().inject(headers)
    except Exception:  # noqa: BLE001 - a header helper must never break a request
        return headers
    return headers


def extract_context(carrier: Mapping[str, str]) -> Any:
    """Extract the W3C context from an inbound ``carrier``; ``None`` when telemetry is off.

    The global propagator is used (trace context and baggage). A missing or malformed
    ``traceparent`` extracts to a context with no valid span, so the request starts a new trace.
    Never raises.
    """
    if not _enabled:
        return None
    try:
        from opentelemetry.propagate import extract

        return extract(carrier)
    except Exception:  # noqa: BLE001 - extraction must never break a request
        return None


def record_histogram(
    name: str,
    value: float,
    *,
    unit: str,
    boundaries: Sequence[float] | None = None,
    **attrs: Any,
) -> None:
    """Record one point on the histogram ``name``, with an optional explicit bucket set.

    The histogram is built once through :func:`_instrument`, so the meter's factory receives
    ``unit`` and ``explicit_bucket_boundaries_advisory=boundaries`` on first creation. ``None``
    attributes are dropped; with metrics off the meter is never touched; the body never raises.
    """
    meter = _meter
    if not _enabled or meter is None:
        return
    try:
        options: dict[str, Any] = {"unit": unit}
        if boundaries is not None:
            options["explicit_bucket_boundaries_advisory"] = boundaries
        hist = _instrument("histogram", "create_histogram", name, meter, **options)
        if hist is not None:
            hist.record(value, {k: v for k, v in attrs.items() if v is not None})
    except Exception:  # noqa: BLE001 - a metric must never break the caller
        return


def status(settings: OTelSettings, default_service_name: str = "mintmory-cli") -> dict[str, str]:
    raise NotImplementedError
