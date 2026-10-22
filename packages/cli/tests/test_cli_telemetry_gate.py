"""Task 2.1 gate: the CLI entry-point scenarios re-pinned under fresh names.

Spec: observability › Every entry point initialises telemetry once.

Task 2.1 is the unit's final check (the ruff/format/mypy/coverage gates). It adds no
behaviour of its own, so the four CLI scenarios of the delta are re-pinned here, once
more, against the callback that already satisfies them (TDD exemption: already satisfied
by task 1.2). Each test drives the real ``mintmory.cli.main.app`` through ``CliRunner``
and asserts a real, non-zero answer (an exported span, a printed id, a recorded init
call), so it fails on a base without the callback.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from mintmory.cli.main import app
from mintmory.core import telemetry
from mintmory.mcp import server as mcp_server
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def gate_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the CLI at an isolated DB file under tmp_path (mirrors test_cli.py)."""
    db_path = tmp_path / "cli_telemetry_gate.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    yield db_path


def _record_init(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace ``telemetry.init_telemetry`` with a recorder; return the kwargs it sees."""

    def _record(*args: Any, **kwargs: Any) -> bool:
        recorded.append(kwargs)
        return False

    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(telemetry, "init_telemetry", _record)
    return recorded


@pytest.mark.l4("C-ce57c578")
def test_gate_cli_add_command_exports_span_as_cli_service(
    gate_db: Path, monkeypatch: pytest.MonkeyPatch, otlp_receiver: Any
) -> None:
    """``mintmory add`` enables telemetry and exports the span as ``mintmory-cli``."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("MINTMORY_OTEL_EXPORTER", "otlp")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", otlp_receiver.endpoint)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
    monkeypatch.delenv("OTEL_METRICS_EXPORTER", raising=False)

    result = runner.invoke(app, ["add", "hello"])
    assert result.exit_code == 0, result.output
    # The atexit hook does not run inside CliRunner, so flush explicitly.
    telemetry.shutdown_telemetry()

    add_spans = [attrs for name, attrs in otlp_receiver.spans() if name == "mintmory.add_memory"]
    assert add_spans, "no mintmory.add_memory span reached the collector"
    assert all(attrs.get("service.name") == "mintmory-cli" for attrs in add_spans), add_spans


@pytest.mark.l4("C-5fc9c6f2")
def test_gate_cli_command_survives_telemetry_init_failure(
    gate_db: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A bad OTLP timeout fails init but the command still adds and exits 0."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "abc")

    with caplog.at_level(logging.WARNING, logger="mintmory.telemetry"):
        result = runner.invoke(app, ["add", "hello"])

    assert result.exit_code == 0, result.output
    assert "Added memory" in result.output
    assert "-" in result.output, "the command must print the new memory id"
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name == "mintmory.telemetry" and record.levelno == logging.WARNING
    ]
    assert any("telemetry disabled: init failed (ValueError)" in message for message in warnings), (
        f"expected a ValueError init warning, got: {warnings}"
    )


@pytest.mark.l4("C-28b6e3fb")
def test_gate_cli_help_survives_unrelated_invalid_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The callback must not read unrelated settings, so a bad one cannot break ``--help``."""
    recorded = _record_init(monkeypatch)
    monkeypatch.setenv("MINTMORY_SUMMARY_CONCURRENCY", "0")

    result = runner.invoke(app, ["add", "--help"])

    assert result.exit_code == 0, result.output
    assert "Usage" in result.output
    assert len(recorded) == 1, "the group callback must still run for '<cmd> --help'"
    assert recorded[0].get("default_service_name") == "mintmory-cli"


@pytest.mark.l4("C-f0a8c0a2")
def test_gate_cli_serve_commands_do_not_initialise_telemetry(
    gate_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``serve`` and ``mcp-serve`` skip the CLI init; their servers initialise themselves."""
    recorded = _record_init(monkeypatch)

    control = runner.invoke(app, ["add", "hello"])
    assert control.exit_code == 0, control.output
    assert len(recorded) == 1, "control: a normal command initialises telemetry"
    recorded.clear()

    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp_server, "main", lambda: None)

    serve = runner.invoke(app, ["serve"])
    mcp_serve = runner.invoke(app, ["mcp-serve"])
    assert serve.exit_code == 0, serve.output
    assert mcp_serve.exit_code == 0, mcp_serve.output
    assert recorded == []
