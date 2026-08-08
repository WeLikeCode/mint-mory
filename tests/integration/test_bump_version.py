"""Lockstep version bump: rewrites version = lines and mintmory-* ~= bounds."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "bump_version", Path(__file__).parents[2] / "scripts" / "bump_version.py"
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
bump_text = _mod.bump_text

SAMPLE = """\
[project]
name = "mintmory-cli"
version = "0.1.0"
dependencies = [
    "mintmory-core~=0.1.0",
    "typer[all]>=0.12",
]

[project.optional-dependencies]
docs = ["mintmory-core[docs]~=0.1.0"]
"""


def test_bump_rewrites_version_and_bounds() -> None:
    out = bump_text(SAMPLE, "0.2.0")
    assert 'version = "0.2.0"' in out
    assert '"mintmory-core~=0.2.0"' in out
    assert '"mintmory-core[docs]~=0.2.0"' in out
    # third-party pins untouched
    assert '"typer[all]>=0.12"' in out
    assert "0.1.0" not in out


def test_bump_only_touches_first_version_line() -> None:
    sample = SAMPLE + '\ncomment = "version = \\"9.9.9\\" in a string"\n'
    out = bump_text(sample, "0.3.0")
    assert out.count('version = "0.3.0"') == 1
