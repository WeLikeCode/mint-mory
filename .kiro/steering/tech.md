# Tech

## Stack

- Python 3.12, typed with Pydantic. `mypy` runs in strict mode.
- uv workspace (`[tool.uv.workspace]` in root `pyproject.toml`) with five
  members: `core`, `mcp`, `api`, `cli`, `meta`.
- Storage: SQLite + `sqlite-vec` + FTS5 (single `.db` file, WAL mode). A
  Postgres backend also exists (`storage_postgres.py`, `schema_postgres.sql`);
  the backend is selected via `storage_factory.py`.
- Transports: Typer (CLI), fastmcp (MCP), FastAPI (API).
- Lint/format: `ruff` (line length 100, rule sets `E,F,I,N,W,UP,B,SIM,ANN`,
  ignoring `ANN401` and `UP042`).

## Commands

All commands run through uv from the repo root.

```bash
# Full test suite (coverage gate: --cov-fail-under=80 is in pyproject)
uv run pytest

# Single package / file
uv run pytest packages/core/tests/
uv run pytest packages/core/tests/test_schema.py -x

# Coverage report
uv run pytest --cov=packages --cov-report=term-missing

# Types (strict) and lint — both must pass before a PR
uv run mypy packages/
uv run ruff check packages/
uv run ruff format --check packages/
```

## Conventions

- Enums use the deliberate `(str, Enum)` pattern (not `StrEnum`) — `UP042` is
  ignored for this reason. Do not "modernise" them to `StrEnum`.
- `asyncio_mode = "auto"` — async tests need no explicit marker.
- The `l4` pytest marker tags acceptance-criteria tests.

## Definition of done for a task

1. The affected package's tests exit 0: `uv run pytest packages/<pkg>/tests/`.
2. `uv run mypy packages/<pkg>/` exits 0.
3. `uv run ruff check packages/<pkg>/` exits 0.

"The implementation is written" is not done — the gates must have been run.
