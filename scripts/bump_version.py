#!/usr/bin/env python3
"""Lockstep version bump across the five mintmory distros.

Usage: python scripts/bump_version.py X.Y.Z
Rewrites the `version = "..."` line and every `mintmory-*~=A.B.C` bound in the
five package pyprojects, and the double-quoted `appVersion` line of
deploy/helm/mintmory/Chart.yaml (the chart's default image tag). Follow with
`uv lock`, commit, then tag `vX.Y.Z`.
"""

import re
import sys
from pathlib import Path

PYPROJECTS = [
    Path("packages/core/pyproject.toml"),
    Path("packages/mcp/pyproject.toml"),
    Path("packages/api/pyproject.toml"),
    Path("packages/cli/pyproject.toml"),
    Path("packages/meta/pyproject.toml"),
]

CHART = Path("deploy/helm/mintmory/Chart.yaml")


def bump_text(text: str, new_version: str) -> str:
    text = re.sub(r'^version = "[^"]+"', f'version = "{new_version}"', text, count=1, flags=re.M)
    return re.sub(
        r"(mintmory-[a-z]+(?:\[[^\]]*\])?)~=\d+\.\d+\.\d+",
        rf"\g<1>~={new_version}",
        text,
    )


def bump_chart_text(text: str, new_version: str) -> str:
    """Rewrite the double-quoted appVersion line only (chart version untouched)."""
    updated, count = re.subn(
        r'^appVersion: "[^"]+"$',
        f'appVersion: "{new_version}"',
        text,
        count=1,
        flags=re.M,
    )
    if count == 0:
        raise ValueError("appVersion line not found")
    return updated


def main(argv: list[str] | None = None, root: Path | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    run_root = Path(__file__).parents[1] if root is None else root
    if len(args) != 1 or not re.fullmatch(r"\d+\.\d+\.\d+", args[0]):
        sys.exit("usage: bump_version.py X.Y.Z")
    new_version = args[0]
    # Bump the chart first: a missing/unparseable appVersion line aborts before
    # any file is written, so the chart never drifts from the release tag.
    chart_path = run_root / CHART
    try:
        chart_new = bump_chart_text(chart_path.read_text(encoding="utf-8"), new_version)
    except ValueError as exc:
        sys.exit(f"{CHART}: {exc}")
    chart_path.write_text(chart_new, encoding="utf-8")
    print(f"bumped {CHART}")
    for rel in PYPROJECTS:
        path = run_root / rel
        path.write_text(bump_text(path.read_text(encoding="utf-8"), new_version), encoding="utf-8")
        print(f"bumped {rel}")
    print(
        f"\nnow run: uv lock && git commit -am 'release: v{new_version}' && git tag v{new_version}"
    )


if __name__ == "__main__":
    main()
