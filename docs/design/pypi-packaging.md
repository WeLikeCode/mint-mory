# PyPI packaging — design

**Date:** 2026-08-08
**Status:** approved
**Goal:** `pip install mintmory` works from PyPI, with extras for the MCP server, REST API, and heavy optional dependencies.

## Decisions (locked)

- **Publish shape:** the four existing workspace distros (`mintmory-core`, `mintmory-mcp`, `mintmory-api`, `mintmory-cli`) plus a new metadata-only **umbrella distro `mintmory`**.
- **Release mechanism:** GitHub Actions with PyPI **Trusted Publishing** (OIDC, no API tokens), triggered by `v*` git tags. TestPyPI publish runs before the real PyPI publish.
- **Versioning:** lockstep — all five distros share one version, bumped together.

## Verified facts (2026-08-08)

- All five names (`mintmory`, `mintmory-core`, `mintmory-mcp`, `mintmory-api`, `mintmory-cli`) return 404 on `pypi.org/pypi/<name>/json` — unclaimed.
- The `mintmory.*` namespace is a clean PEP 420 namespace package: no `__init__.py` at the `mintmory/` level in any package, so multiple distros can co-install into one namespace.
- `schema.sql` / `schema_postgres.sql` are located at runtime via `Path(__file__).parent` (`packages/core/src/mintmory/core/storage.py:271`), which works from an installed wheel; hatchling includes non-Python files under the packaged directory by default.
- Each package's `src/mintmory/` contains empty leftover scaffolding dirs (e.g. `packages/api/src/mintmory/{cli,core,mcp}`) — untracked/empty, to be deleted.
- License is MIT (root `LICENSE`, copyright WeLikeCode). Repo: `github.com/WeLikeCode/mint-mory`.

## Components

### 1. Umbrella package `packages/meta` → distro `mintmory`

Metadata-only: it must ship **no files under `mintmory/`** so it can never clobber or shadow the namespace owned by the real distros (hatchling wheel target with `bypass-selection = true`).

- `dependencies = ["mintmory-cli~=<version>"]` (pulls `mintmory-core` transitively).
- Extras:
  - `mcp` → `mintmory-mcp~=<version>`
  - `api` → `mintmory-api~=<version>`
  - `all` → both
  - Pass-throughs to core's heavy extras: `local`, `openai`, `anthropic`, `docs`, `otel`, `image`, `ocr`, `cochange`, `postgres` → `mintmory-core[<extra>]~=<version>`
- Uses the root `README.md` as its long description.
- Added to `[tool.uv.workspace] members` and given `tool.uv.sources` workspace entries so dev resolution is unchanged.

### 2. Inter-package dependency bounds

`tool.uv.sources = { workspace = true }` does not travel into published metadata; today the published requirement would be an unbounded `mintmory-core`. Every intra-workspace dependency becomes `mintmory-core~=0.1.0` (compatible-release bound), with the workspace source kept for local dev. Lockstep version bumps are done by `scripts/bump_version.py`, which rewrites the `version =` line and every `mintmory-*~=` bound across the five pyprojects.

### 3. Metadata completion (all five pyprojects)

Each `[project]` table gains: `license = "MIT"` + `license-files`, `readme`, `authors` (WeLikeCode), `keywords`, `classifiers` (Development Status, Python 3.12/3.13, Typing :: Typed), and `[project.urls]` (Homepage/Repository/Issues → the GitHub repo). The code is mypy-strict but ships no `py.typed` markers today; each portion of the namespace package gains one (`src/mintmory/<portion>/py.typed`) so the Typing classifier is honest — the umbrella gets neither. The four sub-packages get short per-package `README.md` files (a paragraph + pointer to the main repo); the umbrella reuses the root README. Empty scaffolding dirs under each `src/mintmory/` are deleted.

### 4. Build + install verification

A repeatable script `scripts/check_dist.sh` that CI and humans run identically:

1. `uv build --all-packages` → `dist/` with 5 sdists + 5 wheels.
2. `twine check dist/*`.
3. Wheel content assertions: `mintmory-core` wheel contains `schema.sql`, `schema_postgres.sql`; **no wheel except core** contains `mintmory/core/…`; umbrella wheel contains no `mintmory/` files at all.
4. Fresh-venv smoke test installing **only from `dist/`** (`--no-index --find-links dist` plus PyPI for third-party deps): `pip install "mintmory[all]"`, then `mintmory --help`, `mintmory-mcp --help` (or import-check), `mintmory-api` import-check, `python -c "import mintmory.core, mintmory.cli, mintmory.mcp, mintmory.api"`.

### 5. Release workflow `.github/workflows/release.yml`

Trigger: push of tags matching `v*`.

Jobs: `build` (uv build + twine check + wheel assertions, uploads `dist/` artifact) → `smoke-test` (fresh-venv install from artifact) → `publish-testpypi` (gh-action-pypi-publish, OIDC, environment `testpypi`) → `publish-pypi` (same, environment `pypi`). The `pypi` GitHub environment can carry a manual-approval protection rule. A sanity step asserts the tag version matches the package version.

### 6. Docs

README gains an Install section (`pip install mintmory`, extras table). CONTRIBUTING gains a Releasing section (bump script → tag → push → approve).

## Manual steps (owner-only, documented in the plan)

Register the five names as **pending Trusted Publishers** on both pypi.org and test.pypi.org: owner `WeLikeCode`, repo `mint-mory`, workflow `release.yml`, environments `pypi` / `testpypi`. Create the two GitHub environments.

## Error handling / risks

- **Umbrella build shape** (no-code wheel) is unusual — mitigated by the wheel-content assertion and fresh-venv smoke test before anything is published.
- **A publish half-completes** (some of the 5 distros uploaded, then a failure): PyPI rejects re-uploads of the same version. Mitigation: TestPyPI rehearsal first, and `skip-existing: true` on the publish steps so a re-run of the job uploads only the missing distros.
- **Name-squatting window:** names verified free today; registering pending publishers claims them — do the manual step early.

## Testing

- Existing test suite must stay green (no runtime code changes expected beyond deleting empty dirs).
- The verification script (component 4) is the acceptance test; it runs in CI on every release tag and can be run locally anytime.

## Out of scope

Package restructuring, docs site, changing `requires-python`, Alembic/migration work, publishing Docker images.
