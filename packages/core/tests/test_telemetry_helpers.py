"""Runtime helpers the later parts reuse (task 3.2).

Spec: observability › Telemetry enablement modes, and observability › Exporter selection and
endpoint resolution.

These pin the small helpers ``init_telemetry`` is built from:

* ``_DEFAULT_ENDPOINT`` is the OTLP/HTTP collector MintMory talks to when nothing is configured.
* ``_sdk_available`` reports whether the optional ``opentelemetry.sdk`` is installed, without
  importing it.
* ``_resolve_state(settings)`` is the single on/off decision behind the no-op shim: one of
  ``off``, ``sdk missing``, ``export`` or ``no collector``.
* ``_traces_endpoint()`` resolves the OTLP/HTTP traces URL — the traces-specific variable as
  written, else the shared endpoint plus ``/v1/traces``, else the local default plus the path.
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


@pytest.fixture(autouse=True)
def _clear_otel_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No endpoint variable, no kill switch: each test states exactly what it needs."""
    for variable in (*_ENDPOINT_VARIABLES, "OTEL_SDK_DISABLED"):
        monkeypatch.delenv(variable, raising=False)
    yield


def _settings(**overrides: Any) -> OTelSettings:
    """``OTelSettings`` with the test's explicit values overriding the environment."""
    return OTelSettings(**overrides)


@pytest.mark.l4("C-9d8f8f9c")
def test_resolve_state_off_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """``false``, and the standard kill switch over ``true``, both resolve to ``off``."""
    assert telemetry._resolve_state(_settings(enabled="false")) == "off"

    monkeypatch.setenv("OTEL_SDK_DISABLED", "TRUE")
    assert telemetry._resolve_state(_settings(enabled="true")) == "off"


@pytest.mark.l4("C-ead28cef")
def test_resolve_state_sdk_missing_when_the_sdk_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the SDK unavailable, an explicit request resolves to ``sdk missing``."""
    monkeypatch.setattr(telemetry, "_sdk_available", lambda: False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")

    assert telemetry._resolve_state(_settings(enabled="true")) == "sdk missing"


@pytest.mark.l4("C-aba1a372")
def test_resolve_state_export_when_an_endpoint_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``auto`` with an endpoint variable and the SDK present resolves to ``export``."""
    assert telemetry._sdk_available() is True
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")

    assert telemetry._resolve_state(_settings(enabled="auto")) == "export"


@pytest.mark.l4("C-2190b9f3")
def test_resolve_state_no_collector_when_auto_finds_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``auto`` with no endpoint variable and an unreachable default is ``no collector``."""
    monkeypatch.setattr(telemetry, "_endpoint_reachable", lambda url, timeout=0.1: False)

    assert telemetry._resolve_state(_settings(enabled="auto")) == "no collector"


@pytest.mark.l4("C-16b8c487")
def test_traces_endpoint_prefers_the_traces_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`` is used exactly as written."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://shared.invalid:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://traces.invalid:4318/custom")

    assert telemetry._traces_endpoint() == "http://traces.invalid:4318/custom"


@pytest.mark.l4("C-16b8c487")
def test_traces_endpoint_appends_the_traces_path_to_the_shared_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the traces-specific variable, the shared endpoint gets ``/v1/traces``."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.invalid:4318")

    assert telemetry._traces_endpoint() == "http://collector.invalid:4318/v1/traces"


@pytest.mark.l4("C-16b8c487")
def test_traces_endpoint_defaults_to_the_local_collector() -> None:
    """With nothing set, the traces URL is the local default plus ``/v1/traces``."""
    assert telemetry._DEFAULT_ENDPOINT == "http://localhost:4318"
    assert telemetry._traces_endpoint() == "http://localhost:4318/v1/traces"
