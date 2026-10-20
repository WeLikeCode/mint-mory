"""Regression tests for FB-001: the CLI help is rendered without forced colour."""

from __future__ import annotations

import pytest
import typer.rich_utils
from mintmory.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

TENANT_HELP = (
    "Tenant id. Absent or 'global': reads span every tenant and writes go to the global tenant."
)


@pytest.mark.l4("C-bfe27132")
def test_root_help_is_plain_and_documents_the_tenant_option() -> None:
    assert typer.rich_utils.FORCE_TERMINAL is None, (
        "the CLI conftest autouse fixture must clear Typer's forced colour terminal"
    )

    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "\x1b[" not in result.output, result.output

    normalized = " ".join(result.output.split())
    assert TENANT_HELP in normalized, normalized


@pytest.mark.l4("C-c35d15c6")
def test_tenant_help_is_plain_and_lists_the_directory_commands() -> None:
    assert typer.rich_utils.FORCE_TERMINAL is None, (
        "the CLI conftest autouse fixture must clear Typer's forced colour terminal"
    )

    result = runner.invoke(app, ["tenant", "--help"])
    assert result.exit_code == 0, result.output
    assert "\x1b[" not in result.output, result.output

    normalized = " ".join(result.output.split())
    assert "create" in normalized, normalized
    assert "list" in normalized, normalized
