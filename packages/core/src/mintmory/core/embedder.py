"""
Pluggable embedding providers (ADR-0004 — protocol design).

MintMory performs vector similarity search over memory content. Every embedder
exposes the same narrow surface (``EmbedderProtocol``) so callers depend only on
the protocol, never a concrete provider. The concrete implementations that ship
here:

  * ``HashingEmbedder`` — the production DEFAULT (R2). Pure-Python, in-process,
    numpy-only feature-hashing TF-IDF over word + character n-grams. No model,
    no network, no torch. Deterministic across processes/platforms because it
    hashes with ``blake2b`` (not Python's salted ``hash()``).
  * ``LocalEmbedder``  — sentence-transformers/all-MiniLM-L6-v2 (384 dims).
    Heavy (PyTorch ~2 GB); the ``sentence_transformers`` import is lazy and only
    happens inside ``__init__`` so importing this module never drags in PyTorch.
  * ``OllamaEmbedder`` — Ollama's OpenAI-compatible ``/v1/embeddings`` (default
    ``nomic-embed-text``, 768 dims). Stdlib ``urllib`` + numpy; network access is
    deferred until ``embed``/``embed_batch`` is called.
  * ``OpenAIEmbedder`` — text-embedding-3-small (1536 dims). The ``openai``
    import is lazy for the same reason.
  * ``FakeEmbedder``   — deterministic, dependency-free hashing embedder. This is
    THE embedder used across the test suite: identical text always yields an
    identical vector, no model and no network required.

All embed outputs are ``np.ndarray`` of dtype ``float32``, shape
``(dimensions,)``, L2-normalised (the zero-vector case is guarded to avoid a
divide-by-zero, returning an all-zero vector unchanged).

Note (vs ADR-0004): the ADR's ``schema_meta``/``memory_vectors`` SQL and its
config-object factory signature are STALE per PLAN.md §0. Only the *protocol*
design from ADR-0004 is authoritative; the factory here is
``create_embedder(provider: str, **kwargs)`` as specified by the build contract,
plus ``embedder_from_settings`` for config-driven construction.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from mintmory.core.config import EmbeddingSettings


class EmbeddingError(Exception):
    """Raised when an embedder fails to produce a vector (model/API error)."""


def _l2_normalise(vec: NDArray[np.float32]) -> NDArray[np.float32]:
    """L2-normalise a 1-D float32 vector, guarding the zero-vector case.

    Returns the vector divided by its L2 norm. If the norm is zero (or
    non-finite), the input is returned unchanged as float32 to avoid a
    divide-by-zero.
    """
    arr = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0 or not np.isfinite(norm):
        return arr
    return (arr / norm).astype(np.float32)


@runtime_checkable
class EmbedderProtocol(Protocol):
    """Abstract embedding provider. All implementations must be thread-safe."""

    @property
    def dimensions(self) -> int:
        """Number of float32 dimensions in output vectors."""
        ...

    @property
    def model_name(self) -> str:
        """Human-readable model identifier."""
        ...

    def embed(self, text: str) -> NDArray[np.float32]:
        """Embed a single text string.

        Returns a 1-D float32 ndarray of shape ``(self.dimensions,)``,
        L2-normalised. Raises ``EmbeddingError`` on model/API failure.
        """
        ...

    def embed_batch(self, texts: list[str]) -> list[NDArray[np.float32]]:
        """Embed a list of texts, returning vectors in the same order/length."""
        ...


# Tokeniser shared by HashingEmbedder: lowercase, split on non-alphanumerics.
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


class HashingEmbedder:
    """Pure-Python feature-hashing TF-IDF embedder — the production default.

    Pipeline (deterministic, numpy-only; see docs/EXPERIMENTS.md §1.3):

      1. Tokenise — lowercase, split on ``[^a-z0-9]+``; drop tokens of length < 2.
      2. Word n-grams — emit ``word_ngram`` (default unigrams + bigrams).
      3. Char n-grams — for each token emit char ``char_ngram`` (default 3..5)
         grams of ``"^" + token + "$"`` (boundary markers). This is what makes
         the embedder robust to typos / inflection (``endpoint`` ≈ ``endpoints``).
         Disabled when ``char_ngram`` max is 0.
      4. Feature hashing — ``h = blake2b(feature, digest_size=8)``;
         ``bucket = h % dim``; ``sign = +1 if (h >> 63) & 1 else -1`` (signed
         hashing cancels collisions in expectation). Accumulate ``sign * weight``
         into ``vec[bucket]``.
      5. TF weight — raw term frequency, optionally ``× IDF`` (``use_idf``). IDF
         is supplied per-feature by ``embed_batch``'s ``idf`` argument; absent
         entries (and the whole no-IDF path) degrade to 1.0.
      6. L2-normalise (zero-vector guarded).

    Determinism: ``blake2b`` is stable across processes/platforms (unlike
    Python's salted ``hash()``), so identical text → identical vector forever.
    No RNG, no seed.
    """

    MODEL_ID = "hashing-tfidf-v1"

    def __init__(
        self,
        dim: int = 512,
        word_ngram: tuple[int, int] = (1, 2),
        char_ngram: tuple[int, int] = (3, 5),
        use_idf: bool = False,
        idf_floor: float = 1.0,
    ) -> None:
        if dim <= 0:
            raise ValueError(f"dim must be positive, got {dim}")
        self._dim = dim
        self._word_min, self._word_max = word_ngram
        self._char_min, self._char_max = char_ngram
        self._use_idf = use_idf
        self._idf_floor = idf_floor

    @property
    def dimensions(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self.MODEL_ID

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _tokenise(text: str) -> list[str]:
        """Lowercase, split on ``[^a-z0-9]+``, drop tokens of length < 2."""
        return [tok for tok in _TOKEN_SPLIT_RE.split(text.lower()) if len(tok) >= 2]

    def _features(self, text: str) -> list[str]:
        """Expand text into the full list of hashed-feature strings (with TF dups).

        Word n-grams (``self._word_min``..``self._word_max``) over the token list,
        plus character n-grams (``self._char_min``..``self._char_max``) over each
        ``"^" + tok + "$"``. Term frequency is encoded by repetition in this list.
        """
        tokens = self._tokenise(text)
        features: list[str] = []

        # Word n-grams (prefixed so they never collide with char n-grams).
        for n in range(self._word_min, self._word_max + 1):
            if n <= 0 or n > len(tokens):
                continue
            for i in range(len(tokens) - n + 1):
                features.append("w:" + " ".join(tokens[i : i + n]))

        # Character n-grams over boundary-marked tokens.
        if self._char_max > 0:
            lo = max(self._char_min, 1)
            for tok in tokens:
                padded = "^" + tok + "$"
                for n in range(lo, self._char_max + 1):
                    if n > len(padded):
                        continue
                    for i in range(len(padded) - n + 1):
                        features.append("c:" + padded[i : i + n])

        return features

    @staticmethod
    def _hash(feature: str) -> tuple[int, float]:
        """Return ``(bucket_base_int, sign)`` for a feature via blake2b digest."""
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        h = int.from_bytes(digest, "big")
        sign = 1.0 if (h >> 63) & 1 else -1.0
        return h, sign

    def _idf_for(self, feature: str, idf: dict[str, float]) -> float:
        if not self._use_idf:
            return 1.0
        return idf.get(feature, self._idf_floor)

    # -- public API ---------------------------------------------------------
    def embed(self, text: str) -> NDArray[np.float32]:
        return self.embed_batch([text])[0]

    def embed_batch(
        self, texts: list[str], idf: dict[str, float] | None = None
    ) -> list[NDArray[np.float32]]:
        idf_map: dict[str, float] = idf or {}
        out: list[NDArray[np.float32]] = []
        for text in texts:
            vec = np.zeros(self._dim, dtype=np.float32)
            for feature in self._features(text):
                h, sign = self._hash(feature)
                bucket = h % self._dim
                vec[bucket] += np.float32(sign * self._idf_for(feature, idf_map))
            out.append(_l2_normalise(vec))
        return out


class LocalEmbedder:
    """sentence-transformers/all-MiniLM-L6-v2, 384 dims, CPU by default.

    The ``sentence_transformers`` import is lazy (inside ``__init__``) so that
    importing this module never pulls in PyTorch. If the dependency is missing,
    a clear ``ImportError`` tells the user to install the ``[local]`` extra.
    """

    MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
    _DIMENSIONS = 384

    def __init__(self, device: str = "cpu", cache_dir: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - exercised only without extra
            raise ImportError(
                "LocalEmbedder requires 'sentence-transformers'. Install the "
                "local extra: pip install 'mintmory-core[local]'"
            ) from exc

        self._model = SentenceTransformer(self.MODEL_ID, device=device, cache_folder=cache_dir)

    @property
    def dimensions(self) -> int:
        return self._DIMENSIONS

    @property
    def model_name(self) -> str:
        return self.MODEL_ID

    def embed(self, text: str) -> NDArray[np.float32]:
        try:
            vec = self._model.encode(text, normalize_embeddings=True, convert_to_numpy=True)
        except Exception as exc:  # pragma: no cover - requires real model
            raise EmbeddingError(f"LocalEmbedder.embed failed: {exc}") from exc
        return _l2_normalise(np.asarray(vec, dtype=np.float32))

    def embed_batch(self, texts: list[str]) -> list[NDArray[np.float32]]:
        try:
            vecs = self._model.encode(
                texts,
                batch_size=32,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        except Exception as exc:  # pragma: no cover - requires real model
            raise EmbeddingError(f"LocalEmbedder.embed_batch failed: {exc}") from exc
        return [_l2_normalise(np.asarray(v, dtype=np.float32)) for v in vecs]


class OllamaEmbedder:
    """Embeddings via Ollama's OpenAI-compatible ``/v1/embeddings`` (L2-normalised).

    Stdlib ``urllib`` + numpy only — no extra dependencies. Lazy/defensive: no
    network call happens at construction time; the endpoint is contacted only
    when ``embed``/``embed_batch`` is invoked. Moved into core from
    ``scripts/local_llm.py`` so transports/scripts can select it via config.
    """

    MODEL_ID = "nomic-embed-text"
    _DEFAULT_BASE_URL = "http://localhost:11434/v1"
    _DEFAULT_DIM = 768

    def __init__(
        self,
        model: str = MODEL_ID,
        dim: int = _DEFAULT_DIM,
        base_url: str | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        if dim <= 0:
            raise ValueError(f"dim must be positive, got {dim}")
        self._model = model
        self._dim = dim
        self._base_url = (base_url or self._DEFAULT_BASE_URL).rstrip("/")
        self._timeout_s = timeout_s

    @property
    def dimensions(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            self._base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - local OpenAI-compatible endpoint
                req, timeout=self._timeout_s
            ) as resp:
                result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - requires network
            raise EmbeddingError(f"OllamaEmbedder request failed: {exc}") from exc
        return result

    def embed(self, text: str) -> NDArray[np.float32]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[NDArray[np.float32]]:
        if not texts:
            return []
        data = self._post("/embeddings", {"model": self._model, "input": texts})
        try:
            rows = sorted(data["data"], key=lambda d: d.get("index", 0))
        except (KeyError, TypeError) as exc:  # pragma: no cover - requires network
            raise EmbeddingError(f"OllamaEmbedder bad response: {data!r}") from exc
        return [_l2_normalise(np.asarray(r["embedding"], dtype=np.float32)) for r in rows]


class OpenAIEmbedder:
    """openai text-embedding-3-small, 1536 dims.

    The ``openai`` import is lazy (inside ``__init__``). If the dependency is
    missing, a clear ``ImportError`` tells the user to install the ``[openai]``
    extra. Outputs are L2-normalised.
    """

    MODEL_ID = "text-embedding-3-small"
    _DIMENSIONS = 1536

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - exercised only without extra
            raise ImportError(
                "OpenAIEmbedder requires 'openai'. Install the openai extra: "
                "pip install 'mintmory-core[openai]'"
            ) from exc

        self._client = OpenAI(api_key=api_key, base_url=base_url)

    @property
    def dimensions(self) -> int:
        return self._DIMENSIONS

    @property
    def model_name(self) -> str:
        return self.MODEL_ID

    def embed(self, text: str) -> NDArray[np.float32]:
        try:
            resp = self._client.embeddings.create(input=[text], model=self.MODEL_ID)
        except Exception as exc:  # pragma: no cover - requires network
            raise EmbeddingError(f"OpenAIEmbedder.embed failed: {exc}") from exc
        vec = np.asarray(resp.data[0].embedding, dtype=np.float32)
        return _l2_normalise(vec)

    def embed_batch(self, texts: list[str]) -> list[NDArray[np.float32]]:
        try:
            resp = self._client.embeddings.create(input=texts, model=self.MODEL_ID)
        except Exception as exc:  # pragma: no cover - requires network
            raise EmbeddingError(f"OpenAIEmbedder.embed_batch failed: {exc}") from exc
        ordered = sorted(resp.data, key=lambda d: d.index)
        return [_l2_normalise(np.asarray(d.embedding, dtype=np.float32)) for d in ordered]


class FakeEmbedder:
    """Deterministic, dependency-free embedder for tests.

    Vectors are derived by hashing tokens into a fixed-dimension float32 buffer,
    then L2-normalising. Properties:

      * No external dependencies (no model, no network).
      * Deterministic: identical text always yields an identical vector.
      * Configurable ``dim`` (default 384, matching all-MiniLM-L6-v2).
      * Empty / whitespace-only text yields an all-zero vector (the zero-vector
        guard in ``_l2_normalise`` keeps it finite, never NaN).

    This is THE embedder injected throughout the MintMory test suite.
    """

    MODEL_ID = "fake-hash-embedder"

    def __init__(self, dim: int = 384) -> None:
        if dim <= 0:
            raise ValueError(f"dim must be positive, got {dim}")
        self._dim = dim

    @property
    def dimensions(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self.MODEL_ID

    def embed(self, text: str) -> NDArray[np.float32]:
        vec = np.zeros(self._dim, dtype=np.float32)
        tokens = text.lower().split()
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            # Bucket: which dimension this token contributes to.
            bucket = int.from_bytes(digest[:4], "big") % self._dim
            # Weight: stable, signed contribution in roughly [-1, 1].
            raw = int.from_bytes(digest[4:8], "big")
            weight = (raw / 0xFFFFFFFF) * 2.0 - 1.0
            vec[bucket] += np.float32(weight)
        return _l2_normalise(vec)

    def embed_batch(self, texts: list[str]) -> list[NDArray[np.float32]]:
        return [self.embed(text) for text in texts]


def create_embedder(provider: str = "hashing", **kwargs: Any) -> EmbedderProtocol:
    """Factory mapping a provider name to a concrete embedder.

    Args:
        provider: One of ``"hashing"`` (default), ``"local"``, ``"openai"``,
            ``"ollama"``, or ``"fake"``.
        **kwargs: Forwarded to the chosen embedder's constructor.

    Returns:
        An object satisfying ``EmbedderProtocol``.

    Raises:
        ValueError: if ``provider`` is not a known provider.
    """
    if provider == "hashing":
        return HashingEmbedder(**kwargs)
    if provider == "local":
        return LocalEmbedder(**kwargs)
    if provider == "openai":
        return OpenAIEmbedder(**kwargs)
    if provider == "ollama":
        return OllamaEmbedder(**kwargs)
    if provider == "fake":
        return FakeEmbedder(**kwargs)
    raise ValueError(f"Unknown embedding provider: {provider!r}")


def embedder_from_settings(settings: EmbeddingSettings | None = None) -> EmbedderProtocol:
    """Build an embedder from :class:`EmbeddingSettings` (config-driven construction).

    This is what scripts/transports call. With default settings it returns a
    ``HashingEmbedder(dim=512, word_ngram=(1, 2), char_ngram=(3, 5),
    use_idf=False)``. Other providers are selected by ``settings.provider`` and
    receive only the kwargs that apply to them.

    Args:
        settings: An ``EmbeddingSettings`` group; ``None`` loads the group's
            defaults from the environment.

    Returns:
        An object satisfying ``EmbedderProtocol``.
    """
    if settings is None:
        from mintmory.core.config import EmbeddingSettings as RuntimeEmbeddingSettings

        settings = RuntimeEmbeddingSettings()

    provider = settings.provider.value

    if provider == "hashing":
        return HashingEmbedder(
            dim=settings.dim,
            word_ngram=(settings.word_ngram_min, settings.word_ngram_max),
            char_ngram=(settings.char_ngram_min, settings.char_ngram_max),
            use_idf=settings.use_idf,
        )
    if provider == "fake":
        return FakeEmbedder(dim=settings.dim)
    if provider == "local":
        return LocalEmbedder()
    if provider == "ollama":
        kwargs: dict[str, Any] = {"dim": settings.dim}
        if settings.model is not None:
            kwargs["model"] = settings.model
        if settings.base_url is not None:
            kwargs["base_url"] = settings.base_url
        return OllamaEmbedder(**kwargs)
    if provider == "openai":
        return OpenAIEmbedder(api_key=settings.api_key, base_url=settings.base_url)
    raise ValueError(f"Unknown embedding provider: {provider!r}")
