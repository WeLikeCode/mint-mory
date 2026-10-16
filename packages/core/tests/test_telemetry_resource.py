"""Resource computation: ``OTEL_RESOURCE_ATTRIBUTES`` and MintMory's identity (task 6.2).

Spec: observability › Resource identifies the process.

MintMory computes the SDK ``Resource`` itself so the parsed ``OTEL_RESOURCE_ATTRIBUTES`` win
over MintMory's defaults and ``service.name`` is resolved in the documented order
(``OTEL_SERVICE_NAME``, ``service.name`` in the attributes, ``MINTMORY_OTEL_SERVICE_NAME``, the
caller's default). MintMory always adds ``service.namespace=mintmory``, ``service.version`` (the
installed ``mintmory-core`` version, else ``unknown``) and a random ``service.instance.id``.

``_reset_telemetry`` here shadows the root ``conftest.py`` fixture of the same name for this
module only: these tests own the telemetry state they install and stay runnable (and fail by
assertion) against a unit base where ``telemetry.reset_telemetry`` is absent.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterator
from typing import Any

import pytest
from mintmory.core import telemetry
from mintmory.core.config import OTelSettings

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
def _clear_service_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No service-name variable: each test states exactly what it needs."""
    for variable in _SERVICE_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
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


def _require(name: str) -> Any:
    """A private helper this task owns; missing on a unit base is a failure, not an error."""
    helper = getattr(telemetry, name, None)
    assert helper is not None, f"telemetry.{name} is missing"
    return helper


@pytest.mark.l4("C-a556a3c6")
def test_resource_attributes_from_env_parses_pairs_and_decodes_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``OTEL_RESOURCE_ATTRIBUTES`` is ``k=v`` pairs whose values are percent-decoded."""
    parser = _require("_resource_attributes_from_env")
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES",
        "deployment.environment.name=staging%2Fblue,service.namespace=team",
    )

    attributes = parser()
    assert attributes == {
        "deployment.environment.name": "staging/blue",
        "service.namespace": "team",
    }, attributes


@pytest.mark.l4("C-a556a3c6", "C-a58004cf")
def test_service_name_resolution_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Standard variables beat MintMory's setting, which beats the caller's default."""
    resolver = _require("_service_name")
    settings = OTelSettings(service_name="from-settings")

    assert resolver(settings, "mintmory-cli") == "from-settings"
    assert resolver(OTelSettings(service_name=None), "mintmory-cli") == "mintmory-cli"

    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "service.name=attrs")
    assert resolver(settings, "mintmory-cli") == "attrs"

    monkeypatch.setenv("OTEL_SERVICE_NAME", "memo")
    assert resolver(settings, "mintmory-cli") == "memo"


@pytest.mark.l4("C-a556a3c6")
def test_parsed_attributes_overlay_mintmory_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The parsed keys win over MintMory's ``service.namespace`` default and are kept."""
    builder = _require("_build_resource")
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES", "service.namespace=team,deployment.environment.name=dev"
    )

    resource = builder(OTelSettings(service_name=None), "mintmory-cli")
    attributes = dict(getattr(resource, "attributes", {}) or {})
    assert attributes.get("service.namespace") == "team", attributes
    assert attributes.get("deployment.environment.name") == "dev", attributes
    assert attributes.get("service.name") == "mintmory-cli", attributes


@pytest.mark.l4("C-a58004cf")
def test_span_resource_has_default_name_namespace_version_and_instance_id() -> None:
    """A span created by the caller's default name carries MintMory's generated identity."""
    exporter = _in_memory()

    assert _init(default_service_name="mintmory-cli", span_exporter=exporter) is True
    with telemetry.span("x"):
        pass

    spans = list(exporter.get_finished_spans())
    assert [span.name for span in spans] == ["x"], [span.name for span in spans]
    attributes = dict(spans[0].resource.attributes)
    assert attributes.get("service.name") == "mintmory-cli", attributes
    assert attributes.get("service.namespace") == "mintmory", attributes
    assert attributes.get("service.version"), attributes
    assert attributes.get("service.instance.id"), attributes


@pytest.mark.l4("C-a58004cf")
def test_service_version_is_the_installed_version_else_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``service.version`` is ``mintmory-core``'s version, else ``unknown`` when unreadable."""
    version = _require("_service_version")
    installed = importlib.metadata.version("mintmory-core")
    assert installed
    assert version() == installed

    def _missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr("mintmory.core.telemetry.importlib.metadata.version", _missing)
    assert version() == "unknown"
