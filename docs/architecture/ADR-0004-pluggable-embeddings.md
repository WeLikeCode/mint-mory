# ADR-0004: Pluggable Embedding Provider with Local Default

**Status:** Accepted  
**Date:** 2026-06-15  
**Deciders:** MintMory core team  
**Supersedes:** (none — embedding architecture decision)

---

## Context

MintMory performs vector similarity search as a core retrieval mechanism. Every stored memory requires an embedding vector; every search query requires an embedding of the query text. The choice of embedding model has significant implications for:

1. **Deployment portability:** requiring an API key at runtime breaks the zero-dependency self-contained goal.
2. **Embedding quality:** local models (384 dims) are weaker than hosted models (1536 dims, OpenAI `text-embedding-3-small`).
3. **Latency:** a network round-trip to OpenAI adds 100–300 ms per embed call; `sentence-transformers` adds ~5 ms on first call (model loaded), ~1 ms thereafter.
4. **Dimensionality consistency:** the `memory_vectors` virtual table is created with a fixed dimension. Changing embedding providers after initial data is written requires a full re-embed migration.
5. **Cost:** OpenAI `text-embedding-3-small` costs $0.02 per 1M tokens. For a developer with 100k memories × average 50 tokens = 5M tokens at ~$0.10 per full re-embed. Acceptable but not free.

### What Open Source Systems Do

| System | Embedding Approach |
|--------|--------------------|
| Memori | `sentence-transformers` hardcoded; no swap mechanism |
| Mem0 | OpenAI default; `LiteLLM` abstraction for provider swap |
| widemem | FAISS + OpenAI API; no local fallback |
| MemGPT / Letta | OpenAI default; `LiteLLM` wrapper |

None of the open source references implement a clean protocol-based abstraction that allows compile-time-safe provider switching. MintMory will introduce one.

---

## Decision

**Define an `EmbedderProtocol` in `core/embeddings.py` and ship two concrete implementations: `LocalEmbedder` (default) and `OpenAIEmbedder` (optional).** Additional providers can be added by implementing the protocol without modifying core.

### Protocol Definition

```python
# core/embeddings.py
from typing import Protocol, runtime_checkable
import numpy as np

@runtime_checkable
class EmbedderProtocol(Protocol):
    """Abstract embedding provider. All implementations must be thread-safe."""

    @property
    def dimensions(self) -> int:
        """Number of float32 dimensions in output vectors."""
        ...

    @property
    def model_name(self) -> str:
        """Human-readable model identifier for schema validation."""
        ...

    def embed(self, text: str) -> np.ndarray:
        """
        Embed a single text string.

        Args:
            text: Raw text to embed. Must be non-empty.

        Returns:
            1-D float32 ndarray of shape (self.dimensions,), L2-normalised.

        Raises:
            EmbeddingError: on model failure or API error.
        """
        ...

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """
        Embed a list of texts. Implementations MUST batch efficiently.

        Args:
            texts: Non-empty list of strings. Empty strings are silently
                   replaced with a zero vector.

        Returns:
            List of 1-D float32 ndarrays, same length and order as texts.
        """
        ...
```

### Local Embedder (Default)

```python
# core/embeddings.py

class LocalEmbedder:
    """sentence-transformers/all-MiniLM-L6-v2, 384 dims, CPU-only by default."""

    MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
    _DIMENSIONS = 384

    def __init__(self, device: str = "cpu", cache_dir: str | None = None) -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(self.MODEL_ID, device=device,
                                          cache_folder=cache_dir)

    @property
    def dimensions(self) -> int:
        return self._DIMENSIONS

    @property
    def model_name(self) -> str:
        return self.MODEL_ID

    def embed(self, text: str) -> np.ndarray:
        return self._model.encode(text, normalize_embeddings=True,
                                  convert_to_numpy=True)

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        return list(self._model.encode(texts, batch_size=32,
                                       normalize_embeddings=True,
                                       convert_to_numpy=True))
```

### OpenAI Embedder (Optional Override)

```python
class OpenAIEmbedder:
    """openai text-embedding-3-small, 1536 dims."""

    MODEL_ID = "text-embedding-3-small"
    _DIMENSIONS = 1536

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    @property
    def dimensions(self) -> int:
        return self._DIMENSIONS

    @property
    def model_name(self) -> str:
        return self.MODEL_ID

    def embed(self, text: str) -> np.ndarray:
        resp = self._client.embeddings.create(input=[text], model=self.MODEL_ID)
        vec = np.array(resp.data[0].embedding, dtype=np.float32)
        return vec / np.linalg.norm(vec)

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        resp = self._client.embeddings.create(input=texts, model=self.MODEL_ID)
        return [np.array(d.embedding, dtype=np.float32) /
                np.linalg.norm(np.array(d.embedding, dtype=np.float32))
                for d in sorted(resp.data, key=lambda x: x.index)]
```

### Configuration

Providers are resolved at startup time from the MintMory config file (`~/.mintmory/config.toml`):

```toml
[embedding]
provider = "local"        # "local" | "openai" | "custom"
device   = "cpu"          # "cpu" | "cuda" | "mps" (for local only)
cache_dir = "~/.mintmory/model_cache"

[embedding.openai]        # only read when provider = "openai"
api_key_env = "OPENAI_API_KEY"
model = "text-embedding-3-small"
```

The factory function:

```python
def create_embedder(config: EmbeddingConfig) -> EmbedderProtocol:
    if config.provider == "local":
        return LocalEmbedder(device=config.device, cache_dir=config.cache_dir)
    elif config.provider == "openai":
        import os
        api_key = os.environ[config.openai.api_key_env]
        return OpenAIEmbedder(api_key=api_key)
    else:
        raise ValueError(f"Unknown embedding provider: {config.provider!r}")
```

### Schema Validation at Startup

The `memory_vectors` virtual table is created with `FLOAT[N]` where N = `embedder.dimensions`. Before opening an existing database, MintMory reads the stored `embedding_model` and `embedding_dims` from the `schema_meta` table and asserts they match the configured embedder:

```sql
CREATE TABLE schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Populated at DB init:
-- ('embedding_model', 'sentence-transformers/all-MiniLM-L6-v2')
-- ('embedding_dims',  '384')
-- ('schema_version',  '1')
```

If they do not match, startup fails with a clear error:

```
DimensionMismatch: DB was created with 'text-embedding-3-small' (1536 dims)
but config specifies 'all-MiniLM-L6-v2' (384 dims).
Run `mintmory migrate re-embed` to rebuild the vector index, or update config.
```

---

## Rationale

### Why a Protocol and not ABC?

Python `Protocol` (PEP 544 structural subtyping) means that any object with the right method signatures satisfies the type constraint, without requiring explicit `class MyEmbedder(EmbedderProtocol)` inheritance. This allows:
- Third-party embedders to be used without modifying MintMory source
- `@runtime_checkable` enables `isinstance(obj, EmbedderProtocol)` assertions in tests

### Why L2-normalise?

`sqlite-vec` computes cosine similarity as `1 - (a·b)`. For L2-normalised vectors, cosine similarity equals the dot product, which `sqlite-vec` can compute with SIMD-accelerated code. Normalising at embed time (once) rather than at query time (every scan) is a ~5% speedup on 100k-vector searches.

### Why not LiteLLM?

LiteLLM is a full LLM routing layer that adds ~200 MB of transitive dependencies and pulls in multiple provider SDKs. MintMory's embedding needs are narrow (two methods, two providers). A thin protocol with two concrete classes is more auditable and has a smaller attack surface for an agent memory system that may store sensitive user data.

---

## Consequences

### Positive

- **Zero cloud dependency by default:** `pip install mintmory-core` and run; no API key required.
- **Provider swap is one config line:** changing `provider = "openai"` and setting `OPENAI_API_KEY` upgrades search quality without code changes.
- **Type safety:** `mypy` enforces that all callers use only `EmbedderProtocol` methods; adding a third provider never breaks existing call sites.
- **Testability:** tests inject a `FakeEmbedder` (deterministic vectors) without importing `sentence-transformers` or making network calls.
- **re-embed migration path:** `mintmory migrate re-embed` reads all `memories.content`, re-embeds in batches of 64, and bulk-updates `memory_vectors` in a single transaction. This is the only supported path to switch providers on an existing database.

### Negative / Risks

- **PyTorch footprint:** `sentence-transformers` installs PyTorch CPU (~2 GB wheels). Production Docker images should use `torch-cpu` slim variant. The `mintmory-core[local]` extra pins `torch` to the CPU wheel; `mintmory-core` without the extra omits PyTorch (suitable for OpenAI-only deployments).
- **Dimension lock-in:** the `memory_vectors` table dimension is fixed at DB creation time. Switching providers on an existing DB requires the migration tool. This is a one-time cost but must be documented clearly.
- **`all-MiniLM-L6-v2` quality ceiling:** 384-dim local embeddings are weak on long-form text (>256 tokens). Memory content should be chunked at store time if longer than 256 tokens. The `store_memory` tool truncates at 512 tokens and logs a warning.

### Neutral

- The `OpenAIEmbedder` works with any OpenAI-compatible API (Mistral, Together, local `llama.cpp` OpenAI server) by setting `base_url` in config. This is not advertised as a supported feature in v1 but is available by inspection.

---

## References

- sentence-transformers `all-MiniLM-L6-v2`: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
- sqlite-vec KNN query semantics: https://alexgarcia.xyz/sqlite-vec/
- Mem0 LiteLLM integration (examined, not adopted): https://github.com/mem0ai/mem0
- PEP 544 — Protocols for Structural Subtyping: https://peps.python.org/pep-0544/
- MEMTIER (arxiv): embedding quality impact on agent memory retrieval benchmarks
