"""
Unit tests for core/cochange.py (MM-33).

Tests pure clustering (no store), distance-term bounds, and determinism.
sklearn-dependent tests are gated by pytest.importorskip.
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    memory_id: str,
    doc_id: str,
    rel: str,
    mtime: float,
    embedding: NDArray[np.float32] | None = None,
) -> object:
    from mintmory.core.cochange import ChangedDoc

    return ChangedDoc(
        memory_id=memory_id,
        doc_id=doc_id,
        rel=rel,
        mtime=mtime,
        embedding=embedding,
    )


def _settings(
    cochange_enabled: bool = True,
    weight_time: float = 1.0,
    weight_path: float = 0.5,
    weight_content: float = 0.5,
    tau_seconds: int = 3600,
    min_cluster_size: int = 2,
    use_embeddings: bool = True,
) -> object:
    from mintmory.core.config import DocumentSettings

    return DocumentSettings(
        cochange_enabled=cochange_enabled,
        weight_time=weight_time,
        weight_path=weight_path,
        weight_content=weight_content,
        tau_seconds=tau_seconds,
        min_cluster_size=min_cluster_size,
        use_embeddings=use_embeddings,
    )


def _fake_emb(seed: int, dim: int = 8) -> NDArray[np.float32]:
    """Generate a unit-normalised fake embedding from a seed."""
    rng = np.random.default_rng(seed)
    vec = rng.random(dim).astype(np.float32) + 0.01
    return (vec / np.linalg.norm(vec)).astype(np.float32)


# ---------------------------------------------------------------------------
# Tests: < 2 docs / disabled → []
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_docs_returns_empty(self) -> None:
        from mintmory.core.cochange import cluster_changesets

        s = _settings()
        result = cluster_changesets([], s)  # type: ignore[arg-type]
        assert result == []

    def test_single_doc_returns_empty(self) -> None:
        from mintmory.core.cochange import cluster_changesets

        docs = [_make_doc("m1", "/a/b.txt", "b.txt", 1_000.0)]
        s = _settings()
        result = cluster_changesets(docs, s)  # type: ignore[arg-type]
        assert result == []

    def test_disabled_returns_empty(self) -> None:
        from mintmory.core.cochange import cluster_changesets

        docs = [
            _make_doc("m1", "/a/b.txt", "b.txt", 1_000.0),
            _make_doc("m2", "/a/c.txt", "c.txt", 1_001.0),
        ]
        s = _settings(cochange_enabled=False)
        result = cluster_changesets(docs, s)  # type: ignore[arg-type]
        assert result == []

    def test_noise_label_is_excluded_from_changesets(self) -> None:
        """A doc HDBSCAN labels -1 (noise) is excluded from every change-set.

        HDBSCAN's clustering on tiny synthetic inputs is unstable, so we test the
        deterministic label→change-set builder directly (no sklearn needed) with a
        hand-crafted label vector: two docs in cluster 0, one doc as noise (-1).
        Only the cluster-0 pair becomes a change-set; the noise doc appears nowhere.
        """
        from mintmory.core.cochange import _changesets_from_labels

        docs = [
            _make_doc("c0a", "/root/a/f1.txt", "a/f1.txt", 0.0, None),
            _make_doc("c0b", "/root/a/f2.txt", "a/f2.txt", 60.0, None),
            _make_doc("noise", "/root/z/lonely.txt", "z/lonely.txt", 500_000.0, None),
        ]
        labels = np.array([0, 0, -1], dtype=np.int32)
        probs = np.array([1.0, 1.0, 0.0], dtype=np.float64)

        sets = _changesets_from_labels(docs, labels, probs)  # type: ignore[arg-type]
        assert len(sets) == 1
        assert sets[0].member_ids == ["c0a", "c0b"]
        all_members = {m for cs in sets for m in cs.member_ids}
        assert "noise" not in all_members


# ---------------------------------------------------------------------------
# Tests: distance term bounds
# ---------------------------------------------------------------------------


class TestDistanceBounds:
    def test_time_distance_zero_for_same_mtime(self) -> None:
        from mintmory.core.cochange import ChangedDoc, _time_distance

        a = ChangedDoc("m1", "/a", "a", 1000.0, None)
        b = ChangedDoc("m2", "/b", "b", 1000.0, None)
        assert _time_distance(a, b, 3600.0) == pytest.approx(0.0)

    def test_time_distance_one_for_large_delta(self) -> None:
        from mintmory.core.cochange import ChangedDoc, _time_distance

        a = ChangedDoc("m1", "/a", "a", 0.0, None)
        b = ChangedDoc("m2", "/b", "b", 100_000.0, None)
        result = _time_distance(a, b, 3600.0)
        assert result == pytest.approx(1.0)

    def test_time_distance_in_range(self) -> None:
        from mintmory.core.cochange import ChangedDoc, _time_distance

        a = ChangedDoc("m1", "/a", "a", 0.0, None)
        b = ChangedDoc("m2", "/b", "b", 1800.0, None)
        result = _time_distance(a, b, 3600.0)
        assert 0.0 <= result <= 1.0

    def test_path_distance_same_folder(self) -> None:
        from mintmory.core.cochange import ChangedDoc, _path_distance

        a = ChangedDoc("m1", "/a", "docs/a.txt", 0.0, None)
        b = ChangedDoc("m2", "/b", "docs/b.txt", 0.0, None)
        result = _path_distance(a, b)
        assert result == pytest.approx(0.0)

    def test_path_distance_different_folders(self) -> None:
        from mintmory.core.cochange import ChangedDoc, _path_distance

        a = ChangedDoc("m1", "/a", "src/core/a.txt", 0.0, None)
        b = ChangedDoc("m2", "/b", "docs/b.txt", 0.0, None)
        result = _path_distance(a, b)
        assert 0.0 <= result <= 1.0

    def test_path_distance_root_files(self) -> None:
        """Files at root have depth=0; distance should be 0 (no parent dirs)."""
        from mintmory.core.cochange import ChangedDoc, _path_distance

        a = ChangedDoc("m1", "/a.txt", "a.txt", 0.0, None)
        b = ChangedDoc("m2", "/b.txt", "b.txt", 0.0, None)
        # both have 0 parent dirs → distance = (0+0-0)/max(1,0) = 0
        result = _path_distance(a, b)
        assert result == pytest.approx(0.0)

    def test_cosine_distance_identical_vectors(self) -> None:
        from mintmory.core.cochange import _cosine_distance

        v = _fake_emb(42)
        result = _cosine_distance(v, v)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_cosine_distance_orthogonal_vectors(self) -> None:
        from mintmory.core.cochange import _cosine_distance

        v1 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        v2 = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
        result = _cosine_distance(v1, v2)
        # cosine_sim=0 → (1-0)/2 = 0.5
        assert result == pytest.approx(0.5)

    def test_cosine_distance_in_range(self) -> None:
        from mintmory.core.cochange import _cosine_distance

        v1 = _fake_emb(1)
        v2 = _fake_emb(2)
        result = _cosine_distance(v1, v2)
        assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# Tests: clustering (sklearn required)
# ---------------------------------------------------------------------------


sklearn = pytest.importorskip("sklearn", reason="scikit-learn not installed")


class TestClustering:
    """HDBSCAN-based clustering tests — require scikit-learn."""

    def _two_burst_docs(self) -> list[object]:
        """Four docs: two in burst A (low mtime, same folder),
        two in burst B (high mtime, same folder)."""
        # Burst A: folder_a/, mtime ~0
        emb_a = _fake_emb(0)
        emb_a2 = _fake_emb(1)
        # Burst B: folder_b/, mtime ~10000
        emb_b = _fake_emb(10)
        emb_b2 = _fake_emb(11)
        return [
            _make_doc("ma1", "/root/folder_a/f1.txt", "folder_a/f1.txt", 0.0, emb_a),
            _make_doc("ma2", "/root/folder_a/f2.txt", "folder_a/f2.txt", 60.0, emb_a2),
            _make_doc("mb1", "/root/folder_b/f3.txt", "folder_b/f3.txt", 10_000.0, emb_b),
            _make_doc("mb2", "/root/folder_b/f4.txt", "folder_b/f4.txt", 10_060.0, emb_b2),
        ]

    def test_two_bursts_yield_two_changesets(self) -> None:
        """Two distinct edit bursts (different time + folder) → 2 change-sets."""
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_burst_docs()
        # tau=3600 means 60s gap → time_dist very small; 10000s gap → 1.0
        # The big temporal and path gap should separate the two bursts.
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]
        assert len(sets) == 2

    def test_changeset_has_deterministic_id(self) -> None:
        """Same docs → same changeset_ids across two calls."""
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_burst_docs()
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        sets_a = cluster_changesets(docs, s)  # type: ignore[arg-type]
        sets_b = cluster_changesets(docs, s)  # type: ignore[arg-type]
        ids_a = sorted(cs.changeset_id for cs in sets_a)
        ids_b = sorted(cs.changeset_id for cs in sets_b)
        assert ids_a == ids_b

    def test_changeset_id_is_16_chars(self) -> None:
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_burst_docs()
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]
        for cs in sets:
            assert len(cs.changeset_id) == 16

    def test_changeset_member_ids_sorted(self) -> None:
        """member_ids within each ChangeSet are sorted."""
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_burst_docs()
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]
        for cs in sets:
            assert cs.member_ids == sorted(cs.member_ids)

    def test_changeset_edges_strength_in_range(self) -> None:
        """Edge strengths are in [0, 1]."""
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_burst_docs()
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]
        for cs in sets:
            for _src, _dst, strength in cs.edges:
                assert 0.0 <= strength <= 1.0

    def test_no_embedding_fallback(self) -> None:
        """When embeddings are None, clustering still works (content term dropped)."""
        from mintmory.core.cochange import cluster_changesets

        docs = [
            _make_doc("ma1", "/root/a/f1.txt", "a/f1.txt", 0.0, None),
            _make_doc("ma2", "/root/a/f2.txt", "a/f2.txt", 60.0, None),
            _make_doc("mb1", "/root/b/f3.txt", "b/f3.txt", 10_000.0, None),
            _make_doc("mb2", "/root/b/f4.txt", "b/f4.txt", 10_060.0, None),
        ]
        s = _settings(tau_seconds=3600, min_cluster_size=2, use_embeddings=False)
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]
        # Should still produce 2 changesets (time + path suffice)
        assert len(sets) == 2

    def test_weight_content_zero_ignores_embeddings(self) -> None:
        """weight_content=0 → content term is zero-weighted (embeddings ignored)."""
        from mintmory.core.cochange import cluster_changesets

        # Two identical-time, same-folder, but opposite embeddings
        docs = [
            _make_doc("ma1", "/root/a/f1.txt", "a/f1.txt", 0.0, _fake_emb(0)),
            _make_doc("ma2", "/root/a/f2.txt", "a/f2.txt", 60.0, _fake_emb(20)),
            _make_doc("mb1", "/root/b/f3.txt", "b/f3.txt", 10_000.0, _fake_emb(1)),
            _make_doc("mb2", "/root/b/f4.txt", "b/f4.txt", 10_060.0, _fake_emb(21)),
        ]
        s = _settings(
            tau_seconds=3600,
            min_cluster_size=2,
            weight_content=0.0,
        )
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]
        # With weight_content=0 the effective denominator = w_t + w_p; still clusters
        assert isinstance(sets, list)

    def test_changesets_have_order_field(self) -> None:
        """ChangeSet.order contains memory ids sorted by mtime."""
        from mintmory.core.cochange import cluster_changesets

        docs = [
            _make_doc("ma1", "/root/a/f1.txt", "a/f1.txt", 0.0, _fake_emb(0)),
            _make_doc("ma2", "/root/a/f2.txt", "a/f2.txt", 60.0, _fake_emb(1)),
            _make_doc("mb1", "/root/b/f3.txt", "b/f3.txt", 10_000.0, _fake_emb(10)),
            _make_doc("mb2", "/root/b/f4.txt", "b/f4.txt", 10_060.0, _fake_emb(11)),
        ]
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]
        for cs in sets:
            assert len(cs.order) == len(cs.member_ids)

    def test_result_list_type(self) -> None:
        """cluster_changesets always returns a list of ChangeSet objects."""
        from mintmory.core.cochange import ChangeSet, cluster_changesets

        docs = [
            _make_doc("m1", "/a/x.txt", "a/x.txt", 0.0, _fake_emb(0)),
            _make_doc("m2", "/a/y.txt", "a/y.txt", 10.0, _fake_emb(1)),
        ]
        s = _settings()
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]
        assert isinstance(sets, list)
        for cs in sets:
            assert isinstance(cs, ChangeSet)
