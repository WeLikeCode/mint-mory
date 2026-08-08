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
