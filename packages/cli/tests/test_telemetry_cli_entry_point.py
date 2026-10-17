"""CLI entry-point telemetry tests (observability › Every entry point initialises telemetry once).

Task 1.2 adds the Typer group callback in ``mintmory.cli.main`` that calls
``telemetry.init_telemetry(default_service_name="mintmory-cli")`` for every command except
``serve`` and ``mcp-serve``. The callback is already present at HEAD (it was added while
making task 1.1's red tests green), so these new functions pin the same four CLI scenarios
against the existing code.
"""

from __future__ import annotations

import logging
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mintmory.cli.main import app
from mintmory.core import telemetry
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the CLI at an isolated DB file under tmp_path (mirrors test_cli.py)."""
    db_path = tmp_path / "cli_telemetry_entry_point.db"
    monkeypatch.setenv("MINTMORY_DB", str(db_path))
    yield db_path


def _record_init_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    """Replace ``telemetry.init_telemetry`` with a recorder; return its ``(args, kwargs)`` list."""

    def _record(*args: Any, **kwargs: Any) -> bool:
        calls.append((args, kwargs))
        return False

    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(telemetry, "init_telemetry", _record)
    return calls


@pytest.mark.l4("C-ce57c578")
def test_add_span_reaches_the_collector_under_the_cli_service_name(
    cli_db: Path, monkeypatch: pytest.MonkeyPatch, otlp_receiver: Any
) -> None:
    """A traced CLI command exports its span with the ``mintmory-cli`` service name."""
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
def test_bad_otlp_timeout_still_lets_add_succeed(
    cli_db: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing telemetry init logs one WARNING and the command still adds the memory."""
    monkeypatch.setenv("MINTMORY_OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TIMEOUT", "abc")

    with caplog.at_level(logging.WARNING, logger="mintmory.telemetry"):
        result = runner.invoke(app, ["add", "hello"])

    assert result.exit_code == 0, result.output
    assert "Added memory" in result.output
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name == "mintmory.telemetry" and record.levelno == logging.WARNING
    ]
    assert any("telemetry disabled: init failed (ValueError)" in message for message in warnings), (
        f"expected a ValueError init warning, got: {warnings}"
    )


@pytest.mark.l4("C-28b6e3fb")
def test_unrelated_invalid_setting_does_not_break_command_help(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The callback must not read unrelated settings, so a bad one cannot break ``--help``."""
    calls = _record_init_calls(monkeypatch)
    monkeypatch.setenv("MINTMORY_SUMMARY_CONCURRENCY", "0")

    result = runner.invoke(app, ["add", "--help"])

    assert result.exit_code == 0, result.output
    assert "Usage" in result.output
    assert len(calls) == 1, "the group callback must still run for '<cmd> --help'"
    _args, kwargs = calls[0]
    assert kwargs.get("default_service_name") == "mintmory-cli"


@pytest.mark.l4("C-f0a8c0a2")
def test_serve_commands_defer_telemetry_to_their_servers(
    cli_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``serve`` and ``mcp-serve`` skip the CLI init; their servers initialise themselves."""
    calls = _record_init_calls(monkeypatch)

    control = runner.invoke(app, ["add", "hello"])
    assert control.exit_code == 0, control.output
    assert len(calls) == 1, "control: a normal command must initialise telemetry once"
    calls.clear()

    fake_uvicorn = types.ModuleType("uvicorn")

    def _uvicorn_run(*args: Any, **kwargs: Any) -> None:
        return None

    setattr(fake_uvicorn, "run", _uvicorn_run)  # noqa: B010 — builds the fake module
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    fake_server = types.ModuleType("mintmory.mcp.server")

    def _server_main() -> None:
        return None

    setattr(fake_server, "main", _server_main)  # noqa: B010 — builds the fake module
    monkeypatch.setitem(sys.modules, "mintmory.mcp.server", fake_server)

    serve = runner.invoke(app, ["serve"])
    mcp_serve = runner.invoke(app, ["mcp-serve"])
    assert serve.exit_code == 0, serve.output
    assert mcp_serve.exit_code == 0, mcp_serve.output
    assert calls == []
