"""Lockstep version bump: rewrites version = lines and mintmory-* ~= bounds."""

import importlib.util
import tomllib
from pathlib import Path

import pytest
import yaml

_spec = importlib.util.spec_from_file_location(
    "bump_version", Path(__file__).parents[2] / "scripts" / "bump_version.py"
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
ROOT = Path(__file__).parents[2]
bump_text = _mod.bump_text
bump_chart_text = _mod.bump_chart_text
main = _mod.main

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


CHART_IN = 'apiVersion: v2\nname: mintmory\nversion: 0.1.0\nappVersion: "0.1.0"\n'
CHART_BUMPED = 'apiVersion: v2\nname: mintmory\nversion: 0.1.0\nappVersion: "0.2.0"\n'


def _write_bump_tree(root: Path, chart_text: str) -> tuple[Path, list[Path]]:
    """The five package pyprojects (copies of SAMPLE) plus Chart.yaml under root."""
    chart_path = root / "deploy" / "helm" / "mintmory" / "Chart.yaml"
    chart_path.parent.mkdir(parents=True)
    chart_path.write_text(chart_text, encoding="utf-8")
    pyprojects: list[Path] = []
    for name in ("core", "mcp", "api", "cli", "meta"):
        pyproject = root / "packages" / name / "pyproject.toml"
        pyproject.parent.mkdir(parents=True)
        pyproject.write_text(SAMPLE, encoding="utf-8")
        pyprojects.append(pyproject)
    return chart_path, pyprojects


@pytest.mark.l4("C-d321fc4b")
def test_chart_app_version_matches_package_version() -> None:
    chart_text = (ROOT / "deploy/helm/mintmory/Chart.yaml").read_text(encoding="utf-8")
    document = yaml.safe_load(chart_text)
    meta_text = (ROOT / "packages/meta/pyproject.toml").read_text(encoding="utf-8")
    meta = tomllib.loads(meta_text)
    assert document["appVersion"] == meta["project"]["version"]
    rewritten = bump_chart_text(chart_text, "9.9.9")
    assert rewritten == chart_text.replace(
        f'appVersion: "{document["appVersion"]}"', 'appVersion: "9.9.9"'
    )


@pytest.mark.l4("C-d321fc4b")
def test_bump_chart_rewrites_app_version_only() -> None:
    assert bump_chart_text(CHART_IN, "0.2.0") == CHART_BUMPED


@pytest.mark.l4("C-1997c052", "C-ce80d78d", "C-e656ed0f")
def test_bump_chart_fails_without_double_quoted_app_version() -> None:
    for text in ("appVersion: 0.1.0\n", "appVersion: '0.1.0'\n", "name: x\n"):
        with pytest.raises(ValueError) as excinfo:
            bump_chart_text(text, "0.2.0")
        assert str(excinfo.value) == "appVersion line not found"


@pytest.mark.l4("C-d321fc4b", "C-e656ed0f")
def test_bump_main_rewrites_chart_and_pyprojects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    chart_path, pyprojects = _write_bump_tree(tmp_path, CHART_IN)
    main(["0.2.0"], root=tmp_path)
    assert chart_path.read_text(encoding="utf-8") == CHART_BUMPED
    for pyproject in pyprojects:
        text = pyproject.read_text(encoding="utf-8")
        assert 'version = "0.2.0"' in text
        assert "0.1.0" not in text
    assert "bumped deploy/helm/mintmory/Chart.yaml" in capsys.readouterr().out


@pytest.mark.l4("C-1997c052")
def test_bump_main_writes_nothing_when_chart_unparseable(tmp_path: Path) -> None:
    chart_path, pyprojects = _write_bump_tree(tmp_path, "appVersion: 0.1.0\n")
    with pytest.raises(SystemExit) as excinfo:
        main(["0.2.0"], root=tmp_path)
    assert "appVersion" in str(excinfo.value)
    for pyproject in pyprojects:
        assert 'version = "0.1.0"' in pyproject.read_text(encoding="utf-8")
    assert chart_path.read_text(encoding="utf-8") == "appVersion: 0.1.0\n"


@pytest.mark.l4("C-ce80d78d")
def test_bump_main_rejects_bad_version(tmp_path: Path) -> None:
    chart_path, pyprojects = _write_bump_tree(tmp_path, CHART_IN)
    with pytest.raises(SystemExit) as excinfo:
        main(["1.2"], root=tmp_path)
    assert str(excinfo.value) == "usage: bump_version.py X.Y.Z"
    for pyproject in pyprojects:
        assert 'version = "0.1.0"' in pyproject.read_text(encoding="utf-8")
    assert chart_path.read_text(encoding="utf-8") == CHART_IN
    main(["0.2.0"], root=tmp_path)
    assert chart_path.read_text(encoding="utf-8") == CHART_BUMPED
    for pyproject in pyprojects:
        assert 'version = "0.2.0"' in pyproject.read_text(encoding="utf-8")
