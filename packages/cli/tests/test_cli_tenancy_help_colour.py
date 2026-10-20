"""Regression tests for FB-001: CLI help must not depend on terminal colour."""

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
def test_help_is_colourless_and_documents_the_tenant_option() -> None:
    assert typer.rich_utils.FORCE_TERMINAL is None

    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "\x1b[" not in result.output, result.output

    normalized = " ".join(result.output.split())
    assert TENANT_HELP in normalized, normalized
