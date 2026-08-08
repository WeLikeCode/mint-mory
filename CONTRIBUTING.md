# Contributing to MintMory

Thanks for your interest! MintMory is a small, opinionated codebase with a
spec-first workflow and strict quality gates. This guide gets you productive.

## Development setup

```bash
uv sync                 # core + CLI + MCP + API + dev tools
uv sync --extra docs    # if you touch document ingestion (markitdown)
```

Python 3.12+. Everything runs locally; no cloud or model downloads are required
for the default configuration.

## Quality gates (all must pass)

```bash
uv run pytest          # tests, coverage gate ≥ 80%
uv run ruff check .    # lint (line length 100)
uv run ruff format .   # formatting
uv run mypy packages   # strict type-checking
```

A change is not done until all four are green.

## Project layout

```
packages/core   # the domain logic — types, storage, search, dreaming, scoring, notes
packages/cli    # Typer CLI            (mintmory)
packages/mcp    # MCP server           (mintmory-mcp)
packages/api    # FastAPI HTTP API     (mintmory-api)
openspec/       # spec-first change proposals
docs/           # ADRs, OpenAPI spec, experiment records
```

All domain logic lives in `packages/core`; the three transports are thin wrappers
that serialise the same Pydantic models. **Do not** duplicate logic in a transport.

## The spec-first workflow

Non-trivial changes are designed before they are written, under `openspec/changes/<id>/`:

- `proposal.md` — why + what changes + impact
- `design.md` — the frozen interface contract implementers build against
- `tasks.md` — disjoint, ownable work items
- `specs/<capability>/spec.md` — requirement deltas (`ADDED`/`MODIFIED`/`REMOVED`)

Read [`AGENTS.md`](AGENTS.md) first — it documents the invariants (idempotent
dreaming, the source-of-truth hierarchy, the single-file rule, the
"defaults reproduce today's behaviour" config discipline).

## Conventions

- New config defaults must reproduce existing behaviour, so each knob is a tracked
  experiment (see `docs/EXPERIMENTS.md`).
- Keep the core dependency-light and the database a single file.
- Add tests that assert real behaviour, not just exit codes.
- Conventional, focused commits; one logical change per PR.

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

## Reporting bugs / proposing features

Open an issue with a minimal reproduction (for bugs) or a short problem statement
and proposed approach (for features). Large features are best started as an
`openspec/` proposal so the design can be reviewed before implementation.
