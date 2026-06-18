"""
Embedder unit tests — FakeEmbedder ONLY.

FakeEmbedder is the dependency-free, deterministic embedder used across the
MintMory test suite. These tests exercise determinism, shape, dtype, dimension,
L2 normalisation, batch length/order, and empty-string handling. We deliberately
do NOT instantiate LocalEmbedder/OpenAIEmbedder (no model, no network); we only
assert FakeEmbedder satisfies the runtime-checkable EmbedderProtocol.
"""

import math

import numpy as np
from mintmory.core.config import EmbeddingProvider, EmbeddingSettings
from mintmory.core.embedder import (
    EmbedderProtocol,
    FakeEmbedder,
    HashingEmbedder,
    embedder_from_settings,
)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


class TestProtocolConformance:
    def test_fake_embedder_satisfies_protocol(self) -> None:
        assert isinstance(FakeEmbedder(), EmbedderProtocol)

    def test_model_name_is_stable_string(self) -> None:
        embedder = FakeEmbedder()
        assert isinstance(embedder.model_name, str)
        assert embedder.model_name


class TestDimensions:
    def test_default_dimension_is_384(self) -> None:
        assert FakeEmbedder().dimensions == 384

    def test_configurable_dimension(self) -> None:
        assert FakeEmbedder(dim=128).dimensions == 128
        assert FakeEmbedder(dim=1536).dimensions == 1536

    def test_embed_respects_configured_dimension(self) -> None:
        embedder = FakeEmbedder(dim=64)
        vec = embedder.embed("hello world")
        assert vec.shape == (64,)


class TestShapeAndDtype:
    def test_embed_shape(self) -> None:
        vec = FakeEmbedder().embed("the quick brown fox")
        assert vec.shape == (384,)

    def test_embed_dtype_is_float32(self) -> None:
        vec = FakeEmbedder().embed("the quick brown fox")
        assert vec.dtype == np.float32

    def test_embed_returns_ndarray(self) -> None:
        vec = FakeEmbedder().embed("anything")
        assert isinstance(vec, np.ndarray)
        assert vec.ndim == 1


class TestDeterminism:
    def test_identical_text_yields_identical_vector(self) -> None:
        embedder = FakeEmbedder()
        a = embedder.embed("MintMory typed memory")
        b = embedder.embed("MintMory typed memory")
        assert np.array_equal(a, b)

    def test_separate_instances_agree(self) -> None:
        a = FakeEmbedder().embed("deterministic across instances")
        b = FakeEmbedder().embed("deterministic across instances")
        assert np.array_equal(a, b)

    def test_different_text_yields_different_vector(self) -> None:
        embedder = FakeEmbedder()
        a = embedder.embed("alpha beta gamma")
        b = embedder.embed("delta epsilon zeta")
        assert not np.array_equal(a, b)

    def test_case_insensitive(self) -> None:
        embedder = FakeEmbedder()
        assert np.array_equal(embedder.embed("Hello World"), embedder.embed("hello world"))


class TestNormalisation:
    def test_nonempty_vector_is_unit_norm(self) -> None:
        vec = FakeEmbedder().embed("some non trivial content here")
        assert math.isclose(float(np.linalg.norm(vec)), 1.0, rel_tol=1e-5)

    def test_normalisation_holds_for_many_inputs(self) -> None:
        embedder = FakeEmbedder()
        for text in ["a", "two words", "a much longer sentence with several tokens"]:
            norm = float(np.linalg.norm(embedder.embed(text)))
            assert math.isclose(norm, 1.0, rel_tol=1e-5)


class TestEmptyStringHandling:
    def test_empty_string_returns_zero_vector(self) -> None:
        vec = FakeEmbedder().embed("")
        assert vec.shape == (384,)
        assert vec.dtype == np.float32
        assert float(np.linalg.norm(vec)) == 0.0
        assert not np.isnan(vec).any()

    def test_whitespace_only_returns_zero_vector(self) -> None:
        vec = FakeEmbedder().embed("   \t \n ")
        assert float(np.linalg.norm(vec)) == 0.0
        assert not np.isnan(vec).any()


class TestBatch:
    def test_batch_length_matches_input(self) -> None:
        texts = ["one", "two", "three", "four"]
        vecs = FakeEmbedder().embed_batch(texts)
        assert len(vecs) == len(texts)

    def test_batch_order_matches_single_embed(self) -> None:
        embedder = FakeEmbedder()
        texts = ["alpha", "beta", "gamma"]
        batch = embedder.embed_batch(texts)
        for text, batched in zip(texts, batch, strict=True):
            assert np.array_equal(batched, embedder.embed(text))

    def test_batch_each_vector_correct_shape_and_dtype(self) -> None:
        vecs = FakeEmbedder(dim=128).embed_batch(["x", "y"])
        for vec in vecs:
            assert vec.shape == (128,)
            assert vec.dtype == np.float32

    def test_empty_batch_returns_empty_list(self) -> None:
        assert FakeEmbedder().embed_batch([]) == []


# ---------------------------------------------------------------------------
# HashingEmbedder — the production default (R2). Pure-Python, numpy-only.
# ---------------------------------------------------------------------------
class TestHashingProtocolConformance:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(HashingEmbedder(), EmbedderProtocol)

    def test_model_name_is_model_id(self) -> None:
        embedder = HashingEmbedder()
        assert embedder.model_name == "hashing-tfidf-v1"
        assert embedder.model_name == HashingEmbedder.MODEL_ID


class TestHashingDimensions:
    def test_default_dimension_is_512(self) -> None:
        assert HashingEmbedder().dimensions == 512

    def test_configurable_dimension(self) -> None:
        assert HashingEmbedder(dim=256).dimensions == 256
        assert HashingEmbedder(dim=768).dimensions == 768

    def test_embed_respects_configured_dimension(self) -> None:
        vec = HashingEmbedder(dim=128).embed("hello world endpoint")
        assert vec.shape == (128,)


class TestHashingShapeAndDtype:
    def test_embed_shape(self) -> None:
        vec = HashingEmbedder().embed("the quick brown fox")
        assert vec.shape == (512,)

    def test_embed_dtype_is_float32(self) -> None:
        vec = HashingEmbedder().embed("the quick brown fox")
        assert vec.dtype == np.float32

    def test_embed_returns_1d_ndarray(self) -> None:
        vec = HashingEmbedder().embed("anything here")
        assert isinstance(vec, np.ndarray)
        assert vec.ndim == 1


class TestHashingDeterminism:
    def test_identical_text_yields_identical_vector(self) -> None:
        embedder = HashingEmbedder()
        a = embedder.embed("MintMory typed memory graph")
        b = embedder.embed("MintMory typed memory graph")
        assert np.array_equal(a, b)

    def test_separate_instances_agree(self) -> None:
        a = HashingEmbedder().embed("deterministic across instances")
        b = HashingEmbedder().embed("deterministic across instances")
        assert np.array_equal(a, b)

    def test_different_text_yields_different_vector(self) -> None:
        embedder = HashingEmbedder()
        a = embedder.embed("alpha beta gamma")
        b = embedder.embed("delta epsilon zeta")
        assert not np.array_equal(a, b)

    def test_case_insensitive(self) -> None:
        embedder = HashingEmbedder()
        assert np.array_equal(embedder.embed("Hello World"), embedder.embed("hello world"))


class TestHashingNormalisation:
    def test_nonempty_vector_is_unit_norm(self) -> None:
        vec = HashingEmbedder().embed("some non trivial content here")
        assert math.isclose(float(np.linalg.norm(vec)), 1.0, rel_tol=1e-5)

    def test_normalisation_holds_for_many_inputs(self) -> None:
        embedder = HashingEmbedder()
        for text in ["ab", "two words", "a much longer sentence with several tokens"]:
            norm = float(np.linalg.norm(embedder.embed(text)))
            assert math.isclose(norm, 1.0, rel_tol=1e-5)


class TestHashingCharNgramRobustness:
    def test_inflection_more_similar_than_unrelated(self) -> None:
        embedder = HashingEmbedder()
        endpoint = embedder.embed("endpoint")
        endpoints = embedder.embed("endpoints")
        unrelated_a = embedder.embed("banana")
        unrelated_b = embedder.embed("telescope")
        related = _cosine(endpoint, endpoints)
        unrelated = _cosine(unrelated_a, unrelated_b)
        assert related > unrelated
        assert related > 0.0

    def test_char_ngrams_can_be_disabled(self) -> None:
        # With char n-grams off, single distinct tokens share no features.
        embedder = HashingEmbedder(char_ngram=(0, 0))
        endpoint = embedder.embed("endpoint")
        endpoints = embedder.embed("endpoints")
        assert math.isclose(_cosine(endpoint, endpoints), 0.0, abs_tol=1e-6)


class TestHashingEmptyString:
    def test_empty_string_returns_zero_vector(self) -> None:
        vec = HashingEmbedder().embed("")
        assert vec.shape == (512,)
        assert vec.dtype == np.float32
        assert float(np.linalg.norm(vec)) == 0.0
        assert not np.isnan(vec).any()

    def test_whitespace_only_returns_zero_vector(self) -> None:
        vec = HashingEmbedder().embed("   \t \n ")
        assert float(np.linalg.norm(vec)) == 0.0
        assert not np.isnan(vec).any()

    def test_single_char_token_dropped(self) -> None:
        # Tokens of length < 2 are dropped -> zero vector for a lone char.
        vec = HashingEmbedder().embed("a")
        assert float(np.linalg.norm(vec)) == 0.0


class TestHashingBatch:
    def test_batch_length_matches_input(self) -> None:
        texts = ["one note", "two note", "three note", "four note"]
        vecs = HashingEmbedder().embed_batch(texts)
        assert len(vecs) == len(texts)

    def test_batch_order_matches_single_embed(self) -> None:
        embedder = HashingEmbedder()
        texts = ["alpha token", "beta token", "gamma token"]
        batch = embedder.embed_batch(texts)
        for text, batched in zip(texts, batch, strict=True):
            assert np.array_equal(batched, embedder.embed(text))

    def test_empty_batch_returns_empty_list(self) -> None:
        assert HashingEmbedder().embed_batch([]) == []


# ---------------------------------------------------------------------------
# embedder_from_settings — config-driven construction.
# ---------------------------------------------------------------------------
class TestEmbedderFromSettings:
    def test_default_returns_hashing_embedder(self) -> None:
        embedder = embedder_from_settings(EmbeddingSettings())
        assert isinstance(embedder, HashingEmbedder)
        assert embedder.dimensions == 512
        assert embedder.model_name == "hashing-tfidf-v1"

    def test_none_settings_returns_hashing_embedder(self) -> None:
        embedder = embedder_from_settings(None)
        assert isinstance(embedder, HashingEmbedder)

    def test_fake_provider_returns_fake_embedder(self) -> None:
        settings = EmbeddingSettings(provider=EmbeddingProvider.FAKE, dim=128)
        embedder = embedder_from_settings(settings)
        assert isinstance(embedder, FakeEmbedder)
        assert embedder.dimensions == 128

    def test_hashing_dim_override_is_honoured(self) -> None:
        settings = EmbeddingSettings(provider=EmbeddingProvider.HASHING, dim=256)
        embedder = embedder_from_settings(settings)
        assert isinstance(embedder, HashingEmbedder)
        assert embedder.dimensions == 256

    def test_default_satisfies_protocol(self) -> None:
        assert isinstance(embedder_from_settings(EmbeddingSettings()), EmbedderProtocol)
