#!/usr/bin/env bash
# Build all five distros, assert wheel contents, smoke-test a fresh-venv
# install from dist/ only. Run from anywhere inside the repo; CI runs this too.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

rm -rf dist
uv build --all-packages

echo "--- artifact count"
[ "$(ls dist/*.whl | wc -l)" -eq 5 ] || { echo "expected 5 wheels"; ls dist; exit 1; }
[ "$(ls dist/*.tar.gz | wc -l)" -eq 5 ] || { echo "expected 5 sdists"; ls dist; exit 1; }

echo "--- twine check"
uvx twine check dist/*

echo "--- wheel content assertions"
python3 - <<'EOF'
import glob
import zipfile


def names(pattern: str) -> tuple[list[str], str]:
    paths = glob.glob(pattern)
    assert len(paths) == 1, f"{pattern}: {paths}"
    return zipfile.ZipFile(paths[0]).namelist(), paths[0]


core, p = names("dist/mintmory_core-*.whl")
for expect in ("mintmory/core/schema.sql", "mintmory/core/schema_postgres.sql",
               "mintmory/core/py.typed"):
    assert any(n.endswith(expect) for n in core), f"{p} missing {expect}"

for pkg in ("mcp", "api", "cli"):
    ns, p = names(f"dist/mintmory_{pkg}-*.whl")
    assert any(n.startswith(f"mintmory/{pkg}/") for n in ns), f"{p} ships no code"
    assert any(n.endswith(f"mintmory/{pkg}/py.typed") for n in ns), f"{p} missing py.typed"
    for other in ("core", "mcp", "api", "cli"):
        if other != pkg:
            assert not any(n.startswith(f"mintmory/{other}/") for n in ns), \
                f"{p} leaks mintmory/{other}"

# Underscore normalisation means this glob matches ONLY the umbrella.
meta, p = names("dist/mintmory-*.whl")
assert not any(n.startswith("mintmory/") for n in meta), f"{p} must ship no code: {meta}"
print("wheel contents OK")
EOF

echo "--- fresh-venv smoke test (installs from dist/ + PyPI for 3rd-party)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
uv venv --quiet "$tmp/venv"
uv pip install --quiet --python "$tmp/venv/bin/python" --find-links dist "mintmory[all]"
"$tmp/venv/bin/mintmory" --help >/dev/null
"$tmp/venv/bin/python" - <<'EOF'
import importlib.metadata as md

import mintmory.api  # noqa: F401
import mintmory.cli  # noqa: F401
import mintmory.core  # noqa: F401
import mintmory.mcp  # noqa: F401

for dist in ("mintmory", "mintmory-core", "mintmory-mcp", "mintmory-api", "mintmory-cli"):
    print(f"{dist}=={md.version(dist)}")
EOF
echo "check_dist: ALL OK"
