# ADR-0001: Python + uv Workspaces as the Monorepo Stack

**Status:** Accepted  
**Date:** 2026-06-15  
**Deciders:** MintMory core team  
**Supersedes:** (none — first architectural decision)

---

## Context

MintMory must expose three distinct transports from a single codebase:

1. **stdio** — used by CLI tooling and by Claude Code's sub-process integration
2. **MCP (Model Context Protocol)** — used by LLM agent hosts (Claude Code, Cursor, Open WebUI) that speak the MCP spec over stdio or SSE
3. **HTTP REST** — used by external services, dashboards, and non-MCP integrations via FastAPI

The primary consumers are LLM agents running inside Python toolchains (Serena, Claude Code hooks written in Python, uv-based scripts). The research corpus (Memori, Mem0, widemem, MemGPT, MEMTIER) is uniformly Python. The vector/embedding ecosystem — `sentence-transformers`, `sqlite-vec`, `spaCy` — is Python-first and has no production-grade TypeScript equivalents at equivalent maturity.

### Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **TypeScript + pnpm workspaces** | Excellent tooling for web frontends, strong type inference | No `sentence-transformers`, no `sqlite-vec` bindings, MCP SDK is younger and missing async batch semantics; Serena integration would require a language bridge |
| **Python + Poetry workspaces** | Mature, widely understood | Workspace linking is cumbersome; lock file strategy diverges from uv's `uv.lock`; slower resolver than uv |
| **Python + uv workspaces (chosen)** | Fastest resolver in the Python ecosystem, first-class workspace support since uv 0.4, identical `pyproject.toml` semantics, direct integration with `fastmcp` | Relatively new tool; uv workspace support may lag bleeding-edge PEP adoption |
| **Rust core + Python FFI** | Maximum performance for embedding math | Enormous complexity; overkill for a target of 100k memories |

---

## Decision

**Use Python 3.12 with uv workspaces** as the single monorepo toolchain, structured as four packages:

```
MintMory/
├── pyproject.toml          # workspace root
├── packages/
│   ├── core/               # mintmory-core — domain types, SQLite engine, embedding, dreaming
│   ├── mcp/                # mintmory-mcp  — MCP server via fastmcp
│   ├── api/                # mintmory-api  — FastAPI HTTP REST server
│   └── cli/                # mintmory-cli  — Typer CLI (stdio transport)
├── tests/                  # cross-package integration tests
└── scripts/                # dev tooling (seed DB, run dreamd, benchmark)
```

The workspace root `pyproject.toml` declares:

```toml
[tool.uv.workspace]
members = ["packages/*"]

[tool.uv]
dev-dependencies = ["pytest>=8", "pytest-asyncio", "ruff", "mypy"]
```

Each sub-package lists `mintmory-core` as a path dependency so that a single `uv sync` installs the full graph in editable mode.

---

## Rationale

### Transport coverage via fastmcp

`fastmcp` (v2+) supports all three transports from a single `FastMCP` application object:

```python
from fastmcp import FastMCP

mcp = FastMCP("MintMory")

@mcp.tool()
async def store_memory(content: str, category: str) -> dict: ...

# stdio: mcp.run()
# SSE/HTTP MCP: mcp.run(transport="sse", port=8001)
# Mounted inside FastAPI: app.mount("/mcp", mcp.get_asgi_app())
```

This eliminates the need for a separate server implementation per transport — one MCP tool definition covers the LLM-agent and CLI use cases; the FastAPI layer wraps the same core domain functions directly.

### Local embedding ecosystem

`sentence-transformers` ships `all-MiniLM-L6-v2` as a ~90 MB download with no runtime dependencies beyond PyTorch CPU. Running `model.encode(texts, batch_size=32)` produces 384-dim float32 vectors synchronously. The `sqlite-vec` extension consumes these directly as `BLOB` columns. There is no equivalent TypeScript pipeline that avoids a network call.

### Developer experience

`uv run pytest` from the workspace root resolves the full dependency graph in seconds. `uv add --package mintmory-core numpy` adds a dependency to the correct package. Hot-reload during development uses `uv run uvicorn mintmory_api.main:app --reload`.

---

## Consequences

### Positive

- All three transports share the same domain model and database session; no serialization round-trips between processes.
- `fastmcp` generates an OpenAPI schema from MCP tool decorators, making the MCP and REST surfaces consistent by construction.
- `sentence-transformers` and `sqlite-vec` are pip-installable with no system libraries beyond a C compiler for the SQLite extension (pre-built wheels available).
- `uv lock` produces a fully reproducible environment; CI pins the uv version in `.github/workflows`.

### Negative / Risks

- **uv workspace maturity:** uv workspaces became stable in v0.4 (late 2024). Edge cases around editable installs with C extensions may surface; mitigation is to pin `uv>=0.5` and test on CI.
- **No frontend package:** If a web UI is added later, a separate `pnpm` workspace alongside the Python monorepo is the cleanest option — not mixing toolchains inside uv.
- **PyTorch size:** The default `sentence-transformers` install pulls ~2 GB of PyTorch CPU wheels. Production deployments should use the `torch` slim variant or switch to the OpenAI embedder override. The `EmbedderProtocol` abstraction (see ADR-0004) makes this substitution at config time.

### Neutral

- Python 3.12 is the minimum; 3.13 is not yet required. The `asyncio` task group API (`asyncio.TaskGroup`) used in the dreaming daemon requires 3.11+.
- Type checking is enforced via `mypy --strict` on all packages; `ruff` handles formatting and linting. Both are declared as workspace dev-dependencies.

---

## References

- [uv workspace documentation](https://docs.astral.sh/uv/concepts/workspaces/)
- [fastmcp transport docs](https://github.com/jlowin/fastmcp)
- Serena MCP server (Python, used as integration model)
- Memori source: SQLite WAL + background loop pattern (Python)
