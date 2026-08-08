#!/usr/bin/env python3
"""Lockstep version bump across the five mintmory distros.

Usage: python scripts/bump_version.py X.Y.Z
Rewrites the `version = "..."` line and every `mintmory-*~=A.B.C` bound in the
five package pyprojects. Follow with `uv lock`, commit, then tag `vX.Y.Z`.
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


def bump_text(text: str, new_version: str) -> str:
    text = re.sub(
        r'^version = "[^"]+"', f'version = "{new_version}"', text, count=1, flags=re.M
    )
    return re.sub(
        r"(mintmory-[a-z]+(?:\[[^\]]*\])?)~=\d+\.\d+\.\d+",
        rf"\g<1>~={new_version}",
        text,
    )


def main() -> None:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        sys.exit("usage: bump_version.py X.Y.Z")
    new_version = sys.argv[1]
    root = Path(__file__).parents[1]
    for rel in PYPROJECTS:
        path = root / rel
        path.write_text(bump_text(path.read_text(), new_version))
        print(f"bumped {rel}")
    print(f"\nnow run: uv lock && git commit -am 'release: v{new_version}' "
          f"&& git tag v{new_version}")


if __name__ == "__main__":
    main()
