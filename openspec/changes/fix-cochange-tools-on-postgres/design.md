# Design: fix-cochange-tools-on-postgres

The proposal and tasks carry the content.

## Decisions
- **OpenSpec validation is not a task gate.** Same decision as `deployment-hardening` (its
  design.md `## Decisions`): the L4 gates in `.l4/config.yaml` are `uv sync --frozen ...`,
  ruff, mypy and pytest only, and `npx @fission-ai/openspec` needs Node and network. The
  author runs `openspec validate fix-cochange-tools-on-postgres --strict` before merging; no task requires it.
