# Tasks: Lower MCP token usage with opt-in concise results (MM-38)

## 1. Concise projection helpers (`packages/mcp/src/mintmory/mcp/concise.py`)
- [ ] `_snip(text, n=200)`, `concise_memory`, `concise_memory_get`,
  `concise_search_response` (notes_on_results → ids only), `concise_history_row`.
- [ ] Pure, no I/O; full type annotations.
- [ ] Tests `test_concise.py`: exact field sets, snippet truncation (long/short),
  notes→ids, envelope preserved.

## 2. Main server (`server.py`)
- [ ] Add `verbosity: Literal["full","concise"] = "full"` to `memory_search` and
  `memory_get`; when concise, project via the helpers. Full path unchanged.
- [ ] Append the one-line concise hint to both docstrings.
- [ ] Trim `memory_dream` docstring (relocate env-var prose to docs, keep pointer).
- [ ] Tighten the server `instructions` block; add concise-for-browse note.

## 3. History server (`history_server.py`)
- [ ] Add `verbosity: Literal["full","concise"] = "full"` to `history_timeline` and
  `history_search`; concise maps rows via `concise_history_row`. Full unchanged.
- [ ] Append concise hint to both docstrings; tighten `instructions` + add note.

## 4. Docs
- [ ] Add the relocated `memory_dream` LLM/config detail to an MCP/config doc;
  note the `verbosity="concise"` option for the read tools.

## 5. Tests (MCP)
- [ ] `verbosity="full"` returns today's shape for memory_search/memory_get/history
  tools (regression guard); `verbosity="concise"` returns the lean shape; default
  is full; concise serialization materially smaller than full.

## 6. Gates
- [ ] `ruff` + `ruff format` clean; `mypy packages` clean.
- [ ] `pytest -q` ≥ 80%; full suite green (`--extra cochange` env).
- [ ] `openspec validate optimize-mcp-token-usage --strict`.
