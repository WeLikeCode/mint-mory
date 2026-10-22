"""Shared fixtures of the CLI tests."""

from __future__ import annotations

import pytest
import typer.rich_utils


@pytest.fixture(autouse=True)
def _no_forced_colour(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render CLI output as on a plain pipe, in every environment.

    Typer forces a colour terminal when GITHUB_ACTIONS, FORCE_COLOR or PY_COLORS is set
    (``typer.rich_utils.FORCE_TERMINAL``), so in CI the help text carries ANSI escapes and
    text assertions fail there only. ``None`` lets rich see that CliRunner's output is no
    terminal, as it does locally.
    """
    monkeypatch.setattr(typer.rich_utils, "FORCE_TERMINAL", None)
