# PyPI Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `pip install mintmory` works from PyPI — four existing distros plus a metadata-only `mintmory` umbrella, released by tag-triggered GitHub Actions with Trusted Publishing.

**Architecture:** The uv workspace keeps its four packages (`mintmory-core/-mcp/-api/-cli`, PEP 420 namespace `mintmory.*`). A new `packages/meta` distro named `mintmory` ships zero code and maps extras onto the other distros. Inter-package deps gain `~=` version bounds (lockstep versioning via a bump script). A verification script builds all wheels, asserts their contents, and smoke-tests a fresh-venv install; the release workflow runs that script, then publishes to TestPyPI, then PyPI via OIDC.

**Tech Stack:** uv (workspace, build), hatchling ≥1.27 (PEP 639 license metadata), twine (check only), `pypa/gh-action-pypi-publish`, GitHub environments `testpypi`/`pypi`.

**Spec:** `docs/design/pypi-packaging.md` (approved 2026-08-08).

**Conventions:** Commit prefix `MM-51:`. NO `Co-Authored-By` trailers (user rule). Repo root: `/Users/alexandruiacobescu/gooseProjects/MintMory`; all paths below are repo-relative, all commands run from repo root.

---

### Task 1: Delete scaffolding dirs, add `py.typed` markers

Each `packages/*/src/mintmory/` contains empty leftover dirs for the other portions (untracked — git doesn't track empty dirs). The code is mypy-strict but ships no `py.typed`, so installed wheels would be untyped to consumers.

**Files:**
- Create: `packages/core/src/mintmory/core/py.typed`, `packages/mcp/src/mintmory/mcp/py.typed`, `packages/api/src/mintmory/api/py.typed`, `packages/cli/src/mintmory/cli/py.typed` (all empty)
- Delete: every empty dir under `packages/*/src/mintmory/`

- [ ] **Step 1: Delete empty dirs**

Run: `find packages/*/src/mintmory -type d -empty -delete`
Then verify: `ls packages/api/src/mintmory/` → shows only `api`.

- [ ] **Step 2: Create the four empty marker files**

Run: `touch packages/core/src/mintmory/core/py.typed packages/mcp/src/mintmory/mcp/py.typed packages/api/src/mintmory/api/py.typed packages/cli/src/mintmory/cli/py.typed`

- [ ] **Step 3: Verify gates still pass**

Run: `uv run pytest -x -q` and `uv run mypy packages`
Expected: same green as before (no behavior change).

- [ ] **Step 4: Commit**

```bash
git add packages/*/src/mintmory/*/py.typed
git commit -m "MM-51: ship py.typed markers; drop empty namespace scaffolding dirs"
```

---

### Task 2: Complete publish metadata in the four package pyprojects

`tool.uv.sources` does not travel into published metadata, so intra-workspace deps must carry version bounds. Each package also needs license/readme/classifiers/urls, its own `README.md`, and a copy of the root `LICENSE` (PEP 639 `license-files` paths are relative to the package dir; root `LICENSE` stays canonical).

**Files:**
- Modify: `packages/core/pyproject.toml`, `packages/mcp/pyproject.toml`, `packages/api/pyproject.toml`, `packages/cli/pyproject.toml`
- Create: `packages/{core,mcp,api,cli}/README.md`, `packages/{core,mcp,api,cli}/LICENSE` (copies)

- [ ] **Step 1: Copy LICENSE into each package**

Run: `for p in core mcp api cli; do cp LICENSE packages/$p/LICENSE; done`

- [ ] **Step 2: Write the four short READMEs**

`packages/core/README.md`:
```markdown
# mintmory-core

Core library of [MintMory](https://github.com/WeLikeCode/mint-mory) — a typed
memory system for LLM agents (8 memory categories, typed concept links, hybrid
FTS5 + vector search) on SQLite or Postgres.

Most users want the umbrella package instead: `pip install mintmory`.

Optional extras: `local` (sentence-transformers embeddings), `openai`,
`anthropic`, `docs` (markitdown ingestion), `otel`, `image`, `ocr`,
`cochange`, `postgres`. MIT licensed.
```

`packages/mcp/README.md`:
```markdown
# mintmory-mcp

MCP server for [MintMory](https://github.com/WeLikeCode/mint-mory) — exposes
the typed agent-memory system over the Model Context Protocol (stdio/SSE via
fastmcp). Entry points: `mintmory-mcp`, `mintmory-history-mcp`.

Most users want the umbrella package instead: `pip install "mintmory[mcp]"`.
MIT licensed.
```

`packages/api/README.md`:
```markdown
# mintmory-api

FastAPI REST API for [MintMory](https://github.com/WeLikeCode/mint-mory) — the
typed agent-memory system. Entry point: `mintmory-api`.

Most users want the umbrella package instead: `pip install "mintmory[api]"`.
MIT licensed.
```

`packages/cli/README.md`:
```markdown
# mintmory-cli

Typer CLI for [MintMory](https://github.com/WeLikeCode/mint-mory) — the typed
agent-memory system. Entry point: `mintmory`.

Most users want the umbrella package instead: `pip install mintmory`.
MIT licensed.
```

- [ ] **Step 3: Edit `packages/core/pyproject.toml`**

Replace the top of `[project]` (everything from `name` through `requires-python`, leaving `dependencies` and later sections untouched) with:

```toml
[project]
name = "mintmory-core"
version = "0.1.0"
description = "MintMory core: Palantir-inspired typed memory ontology with SQLite storage"
requires-python = ">=3.12"
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
authors = [{ name = "WeLikeCode" }]
keywords = ["memory", "llm", "agents", "mcp", "sqlite", "vector-search"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Typing :: Typed",
]

[project.urls]
Homepage = "https://github.com/WeLikeCode/mint-mory"
Repository = "https://github.com/WeLikeCode/mint-mory"
Issues = "https://github.com/WeLikeCode/mint-mory/issues"
```

(Do NOT add a `License ::` classifier — PEP 639 SPDX `license = "MIT"` replaces it.)

And bump the build backend floor (PEP 639 needs hatchling ≥1.27):

```toml
[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"
```

- [ ] **Step 4: Edit `packages/mcp/pyproject.toml`**

Same `[project]` metadata block pattern (name `mintmory-mcp`, description unchanged, same classifiers/urls/license/readme/keywords, hatchling floor). Additionally change the dependency line:

```toml
dependencies = [
    "mintmory-core~=0.1.0",
    "fastmcp>=2.3",
    "mcp>=1.6",
    "anthropic>=0.35",   # LLM passive self-assessment
    "structlog>=24.4",
]
```

Keep `[tool.uv.sources]`, `[project.scripts]`, and the wheel target as-is.

- [ ] **Step 5: Edit `packages/api/pyproject.toml`**

Same metadata pattern (name `mintmory-api`); dependency line becomes `"mintmory-core~=0.1.0",` (rest of the list unchanged). Keep sources/scripts/wheel target.

- [ ] **Step 6: Edit `packages/cli/pyproject.toml`**

Same metadata pattern (name `mintmory-cli`); dependency line becomes `"mintmory-core~=0.1.0",` and the extra becomes:

```toml
[project.optional-dependencies]
docs = ["mintmory-core[docs]~=0.1.0"]            # pulls markitdown via core's docs extra
```

- [ ] **Step 7: Re-lock and verify**

Run: `uv lock && uv sync && uv run pytest -x -q`
Expected: lock succeeds (workspace sources still satisfy the `~=` bounds), tests green.

- [ ] **Step 8: Commit**

```bash
git add packages/*/pyproject.toml packages/*/README.md packages/*/LICENSE uv.lock
git commit -m "MM-51: publishable metadata + version-bounded intra-workspace deps"
```

---

### Task 3: Umbrella package `packages/meta` → distro `mintmory`

Metadata-only distro: MUST ship no files under `mintmory/` (it would shadow the namespace portions). Hatchling's `bypass-selection = true` produces an empty (metadata-only) wheel.

**Files:**
- Create: `packages/meta/pyproject.toml`, `packages/meta/README.md`, `packages/meta/LICENSE` (copy)
- Modify: `pyproject.toml` (root — workspace members)

- [ ] **Step 1: Create `packages/meta/pyproject.toml`**

```toml
[project]
name = "mintmory"
version = "0.1.0"
description = "MintMory — typed memory for LLM agents. Umbrella package: CLI + core, extras for the MCP server and REST API."
requires-python = ">=3.12"
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
authors = [{ name = "WeLikeCode" }]
keywords = ["memory", "llm", "agents", "mcp", "sqlite", "vector-search"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries :: Python Modules",
]
dependencies = [
    "mintmory-cli~=0.1.0",
]

[project.optional-dependencies]
# Sibling distros
mcp = ["mintmory-mcp~=0.1.0"]
api = ["mintmory-api~=0.1.0"]
all = ["mintmory-mcp~=0.1.0", "mintmory-api~=0.1.0"]
# Pass-throughs to core's heavy/optional extras
local = ["mintmory-core[local]~=0.1.0"]
openai = ["mintmory-core[openai]~=0.1.0"]
anthropic = ["mintmory-core[anthropic]~=0.1.0"]
docs = ["mintmory-core[docs]~=0.1.0"]
otel = ["mintmory-core[otel]~=0.1.0"]
image = ["mintmory-core[image]~=0.1.0"]
ocr = ["mintmory-core[ocr]~=0.1.0"]
cochange = ["mintmory-core[cochange]~=0.1.0"]
postgres = ["mintmory-core[postgres]~=0.1.0"]

[project.urls]
Homepage = "https://github.com/WeLikeCode/mint-mory"
Repository = "https://github.com/WeLikeCode/mint-mory"
Issues = "https://github.com/WeLikeCode/mint-mory/issues"

[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

# Metadata-only distro: ship no code so it can never shadow the mintmory.*
# namespace owned by the real packages.
[tool.hatch.build.targets.wheel]
bypass-selection = true

[tool.uv.sources]
mintmory-cli = { workspace = true }
mintmory-mcp = { workspace = true }
mintmory-api = { workspace = true }
mintmory-core = { workspace = true }
```

- [ ] **Step 2: Create `packages/meta/README.md`**

````markdown
# MintMory

Typed memory for LLM agents: 8 memory categories, typed concept links, hybrid
FTS5 + vector search, dream-state consolidation — on SQLite (default) or
Postgres. Ships a CLI, an MCP server, and a REST API.

```bash
pip install mintmory          # CLI + core
pip install "mintmory[mcp]"   # + MCP server (mintmory-mcp)
pip install "mintmory[api]"   # + REST API (mintmory-api)
pip install "mintmory[all]"   # everything above
```

Optional capability extras (forwarded to `mintmory-core`): `local`
(sentence-transformers embeddings, pulls PyTorch), `openai`, `anthropic`,
`docs` (PDF/DOCX/… ingestion), `otel`, `image`, `ocr`, `cochange`,
`postgres`.

Docs, source, and issue tracker: <https://github.com/WeLikeCode/mint-mory>.
MIT licensed.
````

- [ ] **Step 3: Copy license**

Run: `cp LICENSE packages/meta/LICENSE`

- [ ] **Step 4: Add to workspace in root `pyproject.toml`**

```toml
[tool.uv.workspace]
members = [
    "packages/core",
    "packages/mcp",
    "packages/api",
    "packages/cli",
    "packages/meta",
]
```

- [ ] **Step 5: Re-lock, sync, verify the empty-wheel build**

Run: `uv lock && uv sync`
Run: `uv build --package mintmory && python3 -c "import zipfile,glob; ns=zipfile.ZipFile(glob.glob('dist/mintmory-0.1.0-py3-none-any.whl')[0]).namelist(); assert not [n for n in ns if n.startswith('mintmory/')], ns; print('empty wheel OK:', ns)"`
Expected: prints `empty wheel OK:` followed by only `mintmory-0.1.0.dist-info/...` entries.

- [ ] **Step 6: Run tests**

Run: `uv run pytest -x -q`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add packages/meta pyproject.toml uv.lock
git commit -m "MM-51: mintmory umbrella distro (metadata-only, extras map to sibling distros)"
```

---

### Task 4: `scripts/bump_version.py` — lockstep version bump

**Files:**
- Create: `scripts/bump_version.py`
- Test: `tests/integration/test_bump_version.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_bump_version.py`:
```python
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

SAMPLE = '''\
[project]
name = "mintmory-cli"
version = "0.1.0"
dependencies = [
    "mintmory-core~=0.1.0",
    "typer[all]>=0.12",
]

[project.optional-dependencies]
docs = ["mintmory-core[docs]~=0.1.0"]
'''


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_bump_version.py -v --no-cov`
Expected: FAIL (file `scripts/bump_version.py` does not exist → spec loader error).

- [ ] **Step 3: Write `scripts/bump_version.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_bump_version.py -v --no-cov`
Expected: 2 PASSED.

- [ ] **Step 5: Sanity round-trip on the real tree**

Run: `python3 scripts/bump_version.py 0.1.1 && git diff --stat && git checkout -- packages`
Expected: exactly the five pyprojects changed; then reverted.

- [ ] **Step 6: Commit**

```bash
git add scripts/bump_version.py tests/integration/test_bump_version.py
git commit -m "MM-51: lockstep bump_version script + test"
```

---

### Task 5: `scripts/check_dist.sh` — build, assert, smoke-test

One script CI and humans run identically. Uses uv for the venv/installer (handles Metadata-Version 2.4; stock venv pip may be too old).

**Files:**
- Create: `scripts/check_dist.sh` (mode 755)

- [ ] **Step 1: Write the script**

```bash
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
```

Run: `chmod +x scripts/check_dist.sh`

- [ ] **Step 2: Run it**

Run: `bash scripts/check_dist.sh`
Expected: ends with `check_dist: ALL OK`, printing all five `dist==0.1.0` lines. If the smoke-test install resolves `mintmory-*` from PyPI instead of `dist/` it would fail (names unpublished) — failure here means the local wheels weren't picked up.

- [ ] **Step 3: Commit**

```bash
git add scripts/check_dist.sh
git commit -m "MM-51: check_dist.sh — build all distros, assert wheel contents, smoke-test install"
```

---

### Task 6: `.github/workflows/release.yml` — tag-triggered Trusted Publishing

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: release

on:
  push:
    tags: ["v*"]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Tag must match package version
        run: |
          python3 -c "
          import os, sys, tomllib
          tag = os.environ['GITHUB_REF_NAME'].removeprefix('v')
          with open('packages/meta/pyproject.toml', 'rb') as f:
              version = tomllib.load(f)['project']['version']
          if tag != version:
              sys.exit(f'tag {tag} != package version {version}')
          "
      - name: Build, assert, smoke-test
        run: bash scripts/check_dist.sh
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  publish-testpypi:
    needs: build
    runs-on: ubuntu-latest
    environment: testpypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/
          skip-existing: true

  publish-pypi:
    needs: publish-testpypi
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          skip-existing: true
```

(`skip-existing: true` makes a re-run after a half-completed publish upload only the missing distros — PyPI rejects same-version re-uploads otherwise.)

- [ ] **Step 2: Lint the YAML**

Run: `uvx --from yamllint yamllint -d relaxed .github/workflows/release.yml` (or `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/release.yml'))"`)
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "MM-51: tag-triggered release workflow (TestPyPI then PyPI, trusted publishing)"
```

---

### Task 7: Docs — README install section, CONTRIBUTING release runbook

**Files:**
- Modify: `README.md:73-85` (the `## Install` section)
- Modify: `CONTRIBUTING.md` (append a `## Releasing` section before `## Reporting bugs / proposing features`)

- [ ] **Step 1: Rewrite README `## Install`**

Replace lines 73–85 (the current uv-clone-only instructions) with:

````markdown
## Install

From PyPI (Python 3.12+):

```bash
pip install mintmory          # CLI + core
pip install "mintmory[mcp]"   # + MCP server (mintmory-mcp entry point)
pip install "mintmory[api]"   # + REST API (mintmory-api entry point)
pip install "mintmory[all]"   # everything above
```

Capability extras (combine freely, e.g. `"mintmory[all,local,docs]"`):
`local` (sentence-transformers embeddings — pulls PyTorch), `openai`,
`anthropic`, `docs` (PDF/DOCX/XLSX/… ingestion), `otel`, `image`, `ocr`,
`cochange`, `postgres`.

For development, use [uv](https://docs.astral.sh/uv/). Clone and sync:

```bash
git clone https://github.com/WeLikeCode/mint-mory.git
cd mint-mory
uv sync                 # core + CLI + MCP + API
uv sync --extra docs    # optional: PDF/DOCX/XLSX/… ingestion (markitdown)
uv sync --extra local   # optional: local sentence-transformers embeddings
```
````

(Keep the trailing `---` separator and `## Quickstart` untouched. Note: until the first release is published, add nothing else — the section is forward-looking and lands in the same PR as the release tooling.)

- [ ] **Step 2: Add `## Releasing` to CONTRIBUTING.md**

Insert before `## Reporting bugs / proposing features`:

```markdown
## Releasing

All five distros (`mintmory`, `mintmory-core`, `mintmory-mcp`, `mintmory-api`,
`mintmory-cli`) version in lockstep and publish from one git tag.

1. `python scripts/bump_version.py X.Y.Z` — rewrites versions + `~=` bounds
2. `uv lock` — refresh the lockfile
3. `bash scripts/check_dist.sh` — local build + smoke test (CI reruns this)
4. Commit, then `git tag vX.Y.Z && git push origin main vX.Y.Z`
5. The `release` workflow builds, publishes to TestPyPI, then (after the
   `pypi` environment gate, if configured) to PyPI via Trusted Publishing.

### One-time PyPI setup (repo owner)

On **both** pypi.org and test.pypi.org, while logged in: *Your account →
Publishing → Add a new pending publisher*, once per distro name
(`mintmory`, `mintmory-core`, `mintmory-mcp`, `mintmory-api`, `mintmory-cli`):

- Owner: `WeLikeCode` — Repository: `mint-mory`
- Workflow name: `release.yml`
- Environment: `pypi` (on pypi.org) / `testpypi` (on test.pypi.org)

Then in GitHub → Settings → Environments, create `testpypi` and `pypi`;
optionally add a required-reviewer rule on `pypi` for a manual approval gate.
Do this soon — registering pending publishers is also what claims the names.
```

- [ ] **Step 3: Commit**

```bash
git add README.md CONTRIBUTING.md
git commit -m "MM-51: install matrix in README, release runbook + trusted-publisher setup in CONTRIBUTING"
```

---

### Task 8: Final verification

- [ ] **Step 1: Full gate run**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy packages && bash scripts/check_dist.sh`
Expected: everything green, `check_dist: ALL OK`.

- [ ] **Step 2: Confirm clean tree and review the branch diff**

Run: `git status --short` (empty) and `git log --oneline main@{u}..HEAD 2>/dev/null || git log --oneline -8`
Expected: the MM-51 commit series from Tasks 1–7.

- [ ] **Step 3: Hand back to the user**

Remaining owner-only steps (cannot be automated):
1. Register the 5 pending Trusted Publishers on pypi.org + test.pypi.org (per CONTRIBUTING §Releasing).
2. Create GitHub environments `testpypi` and `pypi`.
3. First release: `git tag v0.1.0 && git push origin v0.1.0`.
