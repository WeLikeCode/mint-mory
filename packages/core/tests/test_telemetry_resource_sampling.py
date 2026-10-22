"""Resource identity and sampling / propagation (task 6.1).

Spec: observability › Resource identifies the process, and observability › Sampling and
propagation follow the OpenTelemetry environment.

* ``service.name`` is, in order, ``OTEL_SERVICE_NAME``, ``service.name`` in
  ``OTEL_RESOURCE_ATTRIBUTES``, ``MINTMORY_OTEL_SERVICE_NAME``, and the entry point's default the
  caller passes; MintMory adds ``service.namespace`` and a non-empty ``service.version``.
* The tracer provider takes its sampler from ``OTEL_TRACES_SAMPLER`` (``always_off`` drops every
  span), so with the default sampler a span reaches the exporter and the API's W3C propagator
  carries its context to injected carriers.

``_reset_telemetry`` here shadows the root ``conftest.py`` fixture of the same name for this
module only: these tests own the telemetry state they install and stay runnable (and fail by
assertion) against a unit base where ``telemetry.reset_telemetry`` is absent.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry

_SERVICE_VARIABLES = (
    "OTEL_SERVICE_NAME",
    "OTEL_RESOURCE_ATTRIBUTES",
    "MINTMORY_OTEL_SERVICE_NAME",
)


@pytest.fixture(autouse=True)
def _reset_telemetry() -> Iterator[None]:
    """Own this module's telemetry state; tolerate the helper being absent (unit base)."""
    reset = getattr(telemetry, "reset_telemetry", None)
    if reset is not None:
        reset()
    yield
    if reset is not None:
        reset()


@pytest.fixture(autouse=True)
def _fresh_global_providers() -> Iterator[None]:
    """Start each test on the API's default global providers.

    A successful init makes its providers global, and the OTel API allows that only once per
    process; resetting the once-guards keeps repeated inits in one test meaningful.
    """
    from opentelemetry import metrics, trace
    from opentelemetry.util._once import Once

    trace._TRACER_PROVIDER_SET_ONCE = Once()
    trace._TRACER_PROVIDER = None
    metrics._internal._METER_PROVIDER_SET_ONCE = Once()
    metrics._internal._METER_PROVIDER = None
    yield


def _init(**kwargs: Any) -> Any:
    """The test seam; a unit base without it is a failure, not an error."""
    try:
        return telemetry.init_telemetry(**kwargs)
    except TypeError:
        return "init_telemetry is missing the test seam"


def _in_memory() -> Any:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    return InMemorySpanExporter()


def _finished(exporter: Any) -> list[Any]:
    return list(exporter.get_finished_spans())


def _names(exporter: Any) -> list[str]:
    return [span.name for span in _finished(exporter)]


def _resource_attributes(span: Any) -> dict[str, Any]:
    return dict(span.resource.attributes)


@pytest.mark.l4("C-a58004cf")
def test_resource_uses_the_callers_default_service_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no service-name variable, the entry point's default names the process."""
    for variable in _SERVICE_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    exporter = _in_memory()

    assert _init(default_service_name="mintmory-cli", span_exporter=exporter) is True
    with telemetry.span("cli"):
        pass

    assert _names(exporter) == ["cli"], _names(exporter)
    attributes = _resource_attributes(_finished(exporter)[0])
    assert attributes.get("service.name") == "mintmory-cli", attributes
    assert attributes.get("service.version"), attributes


@pytest.mark.l4("C-a556a3c6")
def test_otel_service_name_wins_and_resource_attributes_override_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OTEL_SERVICE_NAME`` beats MintMory's; ``OTEL_RESOURCE_ATTRIBUTES`` overrides the rest."""
    monkeypatch.setenv("OTEL_SERVICE_NAME", "memo")
    monkeypatch.setenv("MINTMORY_OTEL_SERVICE_NAME", "other")
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES", "deployment.environment.name=dev,service.namespace=team"
    )
    exporter = _in_memory()

    assert _init(default_service_name="mintmory-cli", span_exporter=exporter) is True
    with telemetry.span("a"):
        pass

    assert _names(exporter) == ["a"], _names(exporter)
    attributes = _resource_attributes(_finished(exporter)[0])
    assert attributes.get("service.name") == "memo", attributes
    assert attributes.get("deployment.environment.name") == "dev", attributes
    assert attributes.get("service.namespace") == "team", attributes


@pytest.mark.l4("C-a556a3c6")
def test_resource_attribute_service_name_wins_without_otel_service_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without ``OTEL_SERVICE_NAME``, ``service.name`` in the attributes wins over MintMory's."""
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "service.name=attrs")
    monkeypatch.setenv("MINTMORY_OTEL_SERVICE_NAME", "other")
    exporter = _in_memory()

    assert _init(default_service_name="mintmory-cli", span_exporter=exporter) is True
    with telemetry.span("b"):
        pass

    assert _names(exporter) == ["b"], _names(exporter)
    attributes = _resource_attributes(_finished(exporter)[0])
    assert attributes.get("service.name") == "attrs", attributes


@pytest.mark.l4("C-19d78666")
def test_context_propagates_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API's W3C propagator injects the current span's trace and span ids."""
    from opentelemetry import propagate

    exporter = _in_memory()
    assert _init(span_exporter=exporter) is True

    carrier: dict[str, str] = {}
    with telemetry.span("parent") as span:
        propagate.inject(carrier)
        context = getattr(span, "get_span_context", lambda: None)()

    assert context is not None, "telemetry.span did not yield an SDK span"
    assert context.is_valid is True
    assert "traceparent" in carrier, carrier
    assert format(context.trace_id, "032x") in carrier["traceparent"], carrier
    assert format(context.span_id, "016x") in carrier["traceparent"], carrier


@pytest.mark.l4("C-50f410cd")
def test_sampler_always_off_exports_nothing_while_the_default_exports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OTEL_TRACES_SAMPLER=always_off`` drops every span; the default sampler keeps them."""
    exporter = _in_memory()

    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "always_off")
    assert _init(span_exporter=exporter) is True
    with telemetry.span("dropped"):
        pass
    assert _names(exporter) == [], _names(exporter)

    reset = getattr(telemetry, "reset_telemetry", None)
    assert reset is not None, "reset_telemetry is missing"
    reset()
    monkeypatch.delenv("OTEL_TRACES_SAMPLER", raising=False)

    default_exporter = _in_memory()
    assert _init(span_exporter=default_exporter) is True
    with telemetry.span("kept"):
        pass
    assert _names(default_exporter) == ["kept"], _names(default_exporter)
