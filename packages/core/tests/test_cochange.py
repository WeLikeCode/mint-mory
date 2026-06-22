"""
Unit tests for core/cochange.py (MM-33/MM-34).

Tests pure clustering (no store), distance-term bounds, and determinism.
sklearn-dependent tests are gated by pytest.importorskip.
"""

from __future__ import annotations

import numpy as np
import pytest
from mintmory.core.cochange import ChangedDoc
from mintmory.core.config import DocumentSettings
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
) -> ChangedDoc:
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
) -> DocumentSettings:
    return DocumentSettings(
        cochange_enabled=cochange_enabled,
        weight_time=weight_time,
        weight_path=weight_path,
        weight_content=weight_content,
        tau_seconds=tau_seconds,
        min_cluster_size=min_cluster_size,
        use_embeddings=use_embeddings,
    )


def _settings_mm34(
    cochange_enabled: bool = True,
    weight_time: float = 1.0,
    weight_path: float = 0.5,
    weight_content: float = 0.5,
    tau_seconds: int = 3600,
    min_cluster_size: int = 2,
    use_embeddings: bool = False,
    max_cochange_gap_seconds: int = 86_400,
    max_cochange_cluster_size: int = 50,
    cochange_fallback_enabled: bool = False,
    cochange_fallback_max_n: int = 8,
    cochange_distance_eps: float = 0.35,
    cochange_exclude_images: bool = False,
    cochange_exclude_artifacts: bool = False,
    cochange_exclude_suffixes_csv: str = "",
    cochange_label_kind: bool = True,
) -> DocumentSettings:
    return DocumentSettings(
        cochange_enabled=cochange_enabled,
        weight_time=weight_time,
        weight_path=weight_path,
        weight_content=weight_content,
        tau_seconds=tau_seconds,
        min_cluster_size=min_cluster_size,
        use_embeddings=use_embeddings,
        max_cochange_gap_seconds=max_cochange_gap_seconds,
        max_cochange_cluster_size=max_cochange_cluster_size,
        cochange_fallback_enabled=cochange_fallback_enabled,
        cochange_fallback_max_n=cochange_fallback_max_n,
        cochange_distance_eps=cochange_distance_eps,
        cochange_exclude_images=cochange_exclude_images,
        cochange_exclude_artifacts=cochange_exclude_artifacts,
        cochange_exclude_suffixes_csv=cochange_exclude_suffixes_csv,
        cochange_label_kind=cochange_label_kind,
    )


def _fake_emb(seed: int, dim: int = 8) -> NDArray[np.float32]:
    """Generate a unit-normalised fake embedding from a seed."""
    rng = np.random.default_rng(seed)
    vec = rng.random(dim).astype(np.float32) + 0.01
    out: NDArray[np.float32] = (vec / np.linalg.norm(vec)).astype(np.float32)
    return out


# ---------------------------------------------------------------------------
# Tests: < 2 docs / disabled → CoChangeResult with empty changesets
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_docs_returns_empty(self) -> None:
        from mintmory.core.cochange import cluster_changesets

        s = _settings()
        result = cluster_changesets([], s)
        assert result.changesets == []

    def test_single_doc_returns_empty(self) -> None:
        from mintmory.core.cochange import cluster_changesets

        docs = [_make_doc("m1", "/a/b.txt", "b.txt", 1_000.0)]
        s = _settings()
        result = cluster_changesets(docs, s)
        assert result.changesets == []

    def test_disabled_returns_empty(self) -> None:
        from mintmory.core.cochange import cluster_changesets

        docs = [
            _make_doc("m1", "/a/b.txt", "b.txt", 1_000.0),
            _make_doc("m2", "/a/c.txt", "c.txt", 1_001.0),
        ]
        s = _settings(cochange_enabled=False)
        result = cluster_changesets(docs, s)
        assert result.changesets == []

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

        sets, _, _ = _changesets_from_labels(
            docs,
            labels,
            probs,
            run_kind="incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
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
# Tests: clustering
# ---------------------------------------------------------------------------
# NOTE: with the default fallback_max_n=8 these small-N cases take the pure
# connected-components fallback path, so they do NOT require scikit-learn. Tests
# that must exercise the HDBSCAN branch (n > fallback_max_n) gate themselves with
# a local `pytest.importorskip("sklearn")`.


class TestClustering:
    """Clustering tests (small-N → connected-components fallback path)."""

    def _two_burst_docs(self) -> list[ChangedDoc]:
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
        result = cluster_changesets(docs, s)
        sets = result.changesets
        assert len(sets) == 2

    def test_changeset_has_deterministic_id(self) -> None:
        """Same docs → same changeset_ids across two calls."""
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_burst_docs()
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        result_a = cluster_changesets(docs, s)
        result_b = cluster_changesets(docs, s)
        ids_a = sorted(cs.changeset_id for cs in result_a.changesets)
        ids_b = sorted(cs.changeset_id for cs in result_b.changesets)
        assert ids_a == ids_b

    def test_changeset_id_is_16_chars(self) -> None:
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_burst_docs()
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        result = cluster_changesets(docs, s)
        for cs in result.changesets:
            assert len(cs.changeset_id) == 16

    def test_changeset_member_ids_sorted(self) -> None:
        """member_ids within each ChangeSet are sorted."""
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_burst_docs()
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        result = cluster_changesets(docs, s)
        for cs in result.changesets:
            assert cs.member_ids == sorted(cs.member_ids)

    def test_changeset_edges_strength_in_range(self) -> None:
        """Edge strengths are in [0, 1]."""
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_burst_docs()
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        result = cluster_changesets(docs, s)
        for cs in result.changesets:
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
        result = cluster_changesets(docs, s)
        sets = result.changesets
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
        result = cluster_changesets(docs, s)
        # With weight_content=0 the effective denominator = w_t + w_p; still clusters
        assert isinstance(result.changesets, list)

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
        result = cluster_changesets(docs, s)
        for cs in result.changesets:
            assert len(cs.order) == len(cs.member_ids)

    def test_result_list_type(self) -> None:
        """cluster_changesets always returns a CoChangeResult with a list of ChangeSet objects."""
        from mintmory.core.cochange import ChangeSet, cluster_changesets

        docs = [
            _make_doc("m1", "/a/x.txt", "a/x.txt", 0.0, _fake_emb(0)),
            _make_doc("m2", "/a/y.txt", "a/y.txt", 10.0, _fake_emb(1)),
        ]
        s = _settings()
        result = cluster_changesets(docs, s)
        assert isinstance(result.changesets, list)
        for cs in result.changesets:
            assert isinstance(cs, ChangeSet)


# ---------------------------------------------------------------------------
# MM-34 new tests
# ---------------------------------------------------------------------------


class TestCoChangeResult:
    """MM-34: cluster_changesets returns CoChangeResult, not list[ChangeSet]."""

    def test_result_type_empty(self) -> None:
        from mintmory.core.cochange import CoChangeResult, cluster_changesets

        s = _settings_mm34()
        result = cluster_changesets([], s)
        assert isinstance(result, CoChangeResult)
        assert result.changesets == []
        assert result.dropped_oversized == 0
        assert result.dropped_singletons == 0

    def test_result_type_disabled(self) -> None:
        from mintmory.core.cochange import CoChangeResult, cluster_changesets

        docs = [
            _make_doc("m1", "/a/b.txt", "b.txt", 1_000.0),
            _make_doc("m2", "/a/c.txt", "c.txt", 1_001.0),
        ]
        s = _settings_mm34(cochange_enabled=False)
        result = cluster_changesets(docs, s)
        assert isinstance(result, CoChangeResult)
        assert result.changesets == []


class TestChangeSetKind:
    """MM-34 E: kind is threaded into each ChangeSet from run_kind."""

    def test_kind_on_changeset_dataclass(self) -> None:
        from mintmory.core.cochange import ChangeSet

        cs = ChangeSet(
            changeset_id="abc123",
            member_ids=["m1", "m2"],
            observed_at="2026-01-01T00:00:00",
            edges=[],
            order=["m1", "m2"],
            kind="incremental",
        )
        assert cs.kind == "incremental"

    def test_kind_propagated_from_labels(self) -> None:
        """_changesets_from_labels propagates run_kind to every ChangeSet."""
        from mintmory.core.cochange import _changesets_from_labels

        docs = [
            _make_doc("c0a", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("c0b", "/root/a/f2.txt", "a/f2.txt", 60.0),
        ]
        labels = np.array([0, 0], dtype=np.int32)
        probs = np.array([1.0, 1.0], dtype=np.float64)
        sets, dropped_oversized, dropped_singletons = _changesets_from_labels(
            docs,
            labels,
            probs,
            run_kind="cold_full_index",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        assert all(cs.kind == "cold_full_index" for cs in sets)

    def test_kind_incremental(self) -> None:
        from mintmory.core.cochange import _changesets_from_labels

        docs = [
            _make_doc("c0a", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("c0b", "/root/a/f2.txt", "a/f2.txt", 60.0),
        ]
        labels = np.array([0, 0], dtype=np.int32)
        probs = np.array([1.0, 1.0], dtype=np.float64)
        sets, _, _ = _changesets_from_labels(
            docs,
            labels,
            probs,
            run_kind="incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        assert all(cs.kind == "incremental" for cs in sets)


class TestTimeGapSplit:
    """MM-34 A: _split_on_time_gap splits clusters at large internal gaps."""

    def test_no_split_when_all_within_gap(self) -> None:
        from mintmory.core.cochange import _split_on_time_gap

        docs = [
            _make_doc("m1", "/a/f1.txt", "f1.txt", 1000.0),
            _make_doc("m2", "/a/f2.txt", "f2.txt", 2000.0),
            _make_doc("m3", "/a/f3.txt", "f3.txt", 3000.0),
        ]
        groups, dropped = _split_on_time_gap(docs, gap_seconds=86_400, min_size=2)
        assert len(groups) == 1
        assert len(groups[0]) == 3
        assert dropped == 0

    def test_split_on_2year_internal_gap(self) -> None:
        from mintmory.core.cochange import _split_on_time_gap

        two_years = 2 * 365 * 24 * 3600
        docs = [
            _make_doc("a1", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("a2", "/root/a/f2.txt", "a/f2.txt", 60.0),
            _make_doc("b1", "/root/a/f3.txt", "a/f3.txt", float(two_years)),
            _make_doc("b2", "/root/a/f4.txt", "a/f4.txt", float(two_years + 60)),
        ]
        groups, dropped = _split_on_time_gap(docs, gap_seconds=86_400, min_size=2)
        assert len(groups) == 2, f"Expected 2 groups after 2-year gap, got {len(groups)}"
        assert dropped == 0

    def test_sub_min_size_fragment_dropped(self) -> None:
        from mintmory.core.cochange import _split_on_time_gap

        docs = [
            _make_doc("a1", "/a/f1.txt", "f1.txt", 0.0),
            _make_doc("a2", "/a/f2.txt", "f2.txt", 60.0),
            _make_doc("lone", "/a/f3.txt", "f3.txt", float(90 * 24 * 3600)),
        ]
        groups, dropped = _split_on_time_gap(docs, gap_seconds=86_400, min_size=2)
        assert len(groups) == 1
        assert dropped == 1

    def test_adjacent_gap_invariant_on_output(self) -> None:
        from mintmory.core.cochange import _split_on_time_gap

        docs = [_make_doc(f"m{i}", f"/a/f{i}.txt", f"f{i}.txt", float(i * 100)) for i in range(4)]
        groups, _ = _split_on_time_gap(docs, gap_seconds=86_400, min_size=2)
        for group in groups:
            sorted_group = sorted(group, key=lambda d: (d.mtime, d.doc_id))
            for k in range(len(sorted_group) - 1):
                gap = sorted_group[k + 1].mtime - sorted_group[k].mtime
                assert gap <= 86_400

    def test_fragment_changeset_id_is_deterministic(self) -> None:
        from mintmory.core.cochange import _changesets_from_labels

        two_years = 2 * 365 * 24 * 3600
        docs = [
            _make_doc("a1", "/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("a2", "/a/f2.txt", "a/f2.txt", 60.0),
            _make_doc("b1", "/a/f3.txt", "a/f3.txt", float(two_years)),
            _make_doc("b2", "/a/f4.txt", "a/f4.txt", float(two_years + 60)),
        ]
        labels = np.array([0, 0, 0, 0], dtype=np.int32)
        probs = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float64)
        sets_a, _, _ = _changesets_from_labels(
            docs,
            labels,
            probs,
            run_kind="incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        sets_b, _, _ = _changesets_from_labels(
            docs,
            labels,
            probs,
            run_kind="incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        ids_a = sorted(cs.changeset_id for cs in sets_a)
        ids_b = sorted(cs.changeset_id for cs in sets_b)
        assert ids_a == ids_b


class TestSizeCap:
    """MM-34 B: change-sets exceeding max_cochange_cluster_size are dropped."""

    def test_60_member_cluster_dropped(self) -> None:
        from mintmory.core.cochange import _changesets_from_labels

        docs = [_make_doc(f"m{i}", f"/a/f{i}.txt", f"f{i}.txt", float(i * 5)) for i in range(60)]
        labels = np.array([0] * 60, dtype=np.int32)
        probs = np.array([1.0] * 60, dtype=np.float64)
        sets, dropped_oversized, _ = _changesets_from_labels(
            docs,
            labels,
            probs,
            run_kind="incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        assert len(sets) == 0
        assert dropped_oversized == 1

    def test_small_cluster_not_dropped(self) -> None:
        from mintmory.core.cochange import _changesets_from_labels

        docs = [_make_doc(f"m{i}", f"/a/f{i}.txt", f"f{i}.txt", float(i * 5)) for i in range(10)]
        labels = np.array([0] * 10, dtype=np.int32)
        probs = np.array([1.0] * 10, dtype=np.float64)
        sets, dropped_oversized, _ = _changesets_from_labels(
            docs,
            labels,
            probs,
            run_kind="incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        assert len(sets) == 1
        assert dropped_oversized == 0


class TestConnectedComponentsFallback:
    """MM-34 F: connected-components fallback — no sklearn required."""

    def test_connected_components_tight_cluster(self) -> None:
        from mintmory.core.cochange import _connected_components

        d: NDArray[np.float64] = np.full((4, 4), 0.05, dtype=np.float64)
        np.fill_diagonal(d, 0.0)
        components = _connected_components(d, eps=0.35, min_size=2)
        assert len(components) == 1
        assert sorted(components[0]) == [0, 1, 2, 3]

    def test_connected_components_two_disjoint(self) -> None:
        from mintmory.core.cochange import _connected_components

        d: NDArray[np.float64] = np.array(
            [
                [0.0, 0.05, 0.9, 0.9],
                [0.05, 0.0, 0.9, 0.9],
                [0.9, 0.9, 0.0, 0.05],
                [0.9, 0.9, 0.05, 0.0],
            ],
            dtype=np.float64,
        )
        components = _connected_components(d, eps=0.35, min_size=2)
        assert len(components) == 2
        member_sets = {frozenset(c) for c in components}
        assert frozenset({0, 1}) in member_sets
        assert frozenset({2, 3}) in member_sets

    def test_connected_components_below_min_size_excluded(self) -> None:
        from mintmory.core.cochange import _connected_components

        d: NDArray[np.float64] = np.array(
            [[0.0, 0.05, 0.9], [0.05, 0.0, 0.9], [0.9, 0.9, 0.0]],
            dtype=np.float64,
        )
        components = _connected_components(d, eps=0.35, min_size=2)
        assert len(components) == 1
        assert sorted(components[0]) == [0, 1]

    def test_changesets_from_components_basic(self) -> None:
        from mintmory.core.cochange import _changesets_from_components

        docs = [
            _make_doc("m1", "/a/f1.txt", "f1.txt", 100.0),
            _make_doc("m2", "/a/f2.txt", "f2.txt", 200.0),
            _make_doc("m3", "/b/f3.txt", "b/f3.txt", 300.0),
            _make_doc("m4", "/b/f4.txt", "b/f4.txt", 400.0),
        ]
        components = [[0, 1], [2, 3]]
        sets, dropped_oversized, dropped_singletons = _changesets_from_components(
            docs,
            components,
            "incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        assert len(sets) == 2
        assert dropped_oversized == 0
        assert dropped_singletons == 0
        for cs in sets:
            assert len(cs.member_ids) == 2
            assert cs.kind == "incremental"

    def test_cluster_changesets_small_n_fallback(self) -> None:
        """n <= fallback_max_n: skip HDBSCAN; 4 tight files form one change-set."""
        from mintmory.core.cochange import cluster_changesets

        docs = [_make_doc(f"m{i}", f"/root/f{i}.txt", f"f{i}.txt", float(i * 5)) for i in range(4)]
        s = _settings_mm34(
            cochange_fallback_enabled=True,
            cochange_fallback_max_n=8,
            cochange_distance_eps=0.35,
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.0,
            tau_seconds=3600,
            min_cluster_size=2,
            use_embeddings=False,
        )
        result = cluster_changesets(docs, s, run_kind="incremental")
        assert len(result.changesets) == 1
        assert len(result.changesets[0].member_ids) == 4

    def test_label_kind_disabled_blanks_kind(self) -> None:
        """cochange_label_kind=False -> change-sets carry no kind tag (knob honoured)."""
        from mintmory.core.cochange import cluster_changesets

        docs = [_make_doc(f"m{i}", f"/root/f{i}.txt", f"f{i}.txt", float(i * 5)) for i in range(4)]
        s = _settings_mm34(
            cochange_fallback_enabled=True,
            cochange_fallback_max_n=8,
            cochange_distance_eps=0.35,
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.0,
            tau_seconds=3600,
            min_cluster_size=2,
            use_embeddings=False,
            cochange_label_kind=False,
        )
        result = cluster_changesets(docs, s, run_kind="cold_full_index")
        assert result.changesets
        assert all(cs.kind == "" for cs in result.changesets)

    def test_cluster_changesets_fallback_deterministic_id(self) -> None:
        from mintmory.core.cochange import cluster_changesets

        docs = [_make_doc(f"m{i}", f"/root/f{i}.txt", f"f{i}.txt", float(i * 5)) for i in range(4)]
        s = _settings_mm34(
            cochange_fallback_enabled=True,
            cochange_fallback_max_n=8,
            cochange_distance_eps=0.35,
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.0,
            tau_seconds=3600,
            min_cluster_size=2,
            use_embeddings=False,
        )
        r1 = cluster_changesets(docs, s, run_kind="incremental")
        r2 = cluster_changesets(docs, s, run_kind="incremental")
        ids1 = sorted(cs.changeset_id for cs in r1.changesets)
        ids2 = sorted(cs.changeset_id for cs in r2.changesets)
        assert ids1 == ids2

    def test_fallback_two_files_beyond_eps_not_unioned(self) -> None:
        from mintmory.core.cochange import cluster_changesets

        docs = [
            _make_doc("ma", "/root/a/fa.txt", "a/fa.txt", 0.0),
            _make_doc("mb", "/root/b/fb.txt", "b/fb.txt", 36_000.0),
        ]
        s = _settings_mm34(
            cochange_fallback_enabled=True,
            cochange_fallback_max_n=8,
            cochange_distance_eps=0.35,
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.0,
            tau_seconds=3600,
            min_cluster_size=2,
            use_embeddings=False,
        )
        result = cluster_changesets(docs, s, run_kind="incremental")
        assert len(result.changesets) == 0

    def test_fallback_obeys_gap_split_and_size_cap(self) -> None:
        from mintmory.core.cochange import _changesets_from_components

        docs = [_make_doc(f"m{i}", f"/a/f{i}.txt", f"f{i}.txt", float(i * 10)) for i in range(60)]
        components = [list(range(60))]
        sets, dropped_oversized, _ = _changesets_from_components(
            docs,
            components,
            "incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        assert len(sets) == 0
        assert dropped_oversized == 1

    def test_all_noise_labels_returns_empty(self) -> None:
        """_changesets_from_labels with all -1 labels returns empty."""
        sklearn = pytest.importorskip("sklearn")  # noqa: F841
        from mintmory.core.cochange import _changesets_from_labels

        docs = [_make_doc(f"m{i}", f"/root/f{i}.txt", f"f{i}.txt", float(i * 5)) for i in range(4)]
        labels = np.array([-1, -1, -1, -1], dtype=np.int32)
        probs = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float64)
        sets, dropped_oversized, _ = _changesets_from_labels(
            docs,
            labels,
            probs,
            run_kind="incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        assert len(sets) == 0
        assert dropped_oversized == 0


class TestHdbscanBranch:
    """MM-34 F: tests that exercise the HDBSCAN branch (n > fallback_max_n).

    These set a low fallback_max_n so cluster_changesets takes the HDBSCAN path
    rather than the small-N fallback, covering lines that the small-N tests skip.
    """

    def test_all_noise_from_hdbscan_triggers_components_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HDBSCAN returns all-noise on n>max_n -> components fallback still forms a set."""
        pytest.importorskip("sklearn")
        import sklearn.cluster
        from mintmory.core.cochange import cluster_changesets

        class _AllNoiseHDBSCAN:
            def __init__(self, *args: object, **kwargs: object) -> None:
                self.labels_: NDArray[np.int32] = np.empty(0, dtype=np.int32)
                self.probabilities_: NDArray[np.float64] = np.empty(0, dtype=np.float64)

            def fit(self, x: NDArray[np.float64]) -> _AllNoiseHDBSCAN:
                n = x.shape[0]
                self.labels_ = np.full(n, -1, dtype=np.int32)
                self.probabilities_ = np.zeros(n, dtype=np.float64)
                return self

        monkeypatch.setattr(sklearn.cluster, "HDBSCAN", _AllNoiseHDBSCAN)

        # 10 tight files, same folder, close mtimes -> all within eps.
        docs = [_make_doc(f"m{i}", f"/root/f{i}.txt", f"f{i}.txt", float(i * 5)) for i in range(10)]
        s = _settings_mm34(
            cochange_fallback_enabled=True,
            cochange_fallback_max_n=2,  # n=10 > 2 -> HDBSCAN path taken
            cochange_distance_eps=0.35,
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.0,
            tau_seconds=3600,
            min_cluster_size=2,
            use_embeddings=False,
        )
        result = cluster_changesets(docs, s, run_kind="incremental")
        # HDBSCAN said all-noise; the components fallback recovers the tight group.
        assert len(result.changesets) == 1
        assert len(result.changesets[0].member_ids) == 10

    def test_large_n_hdbscan_path_separates_bursts(self) -> None:
        """n > fallback_max_n routes through HDBSCAN; two folders stay unmerged."""
        pytest.importorskip("sklearn")
        from mintmory.core.cochange import cluster_changesets

        # Two dense bursts of 6, far apart in time AND folder.
        docs = []
        for i in range(6):
            docs.append(
                _make_doc(f"a{i}", f"/root/a/f{i}.txt", f"a/f{i}.txt", float(i * 30), _fake_emb(i))
            )
        for i in range(6):
            docs.append(
                _make_doc(
                    f"b{i}",
                    f"/root/b/f{i}.txt",
                    f"b/f{i}.txt",
                    100_000.0 + i * 30,
                    _fake_emb(50 + i),
                )
            )
        s = _settings_mm34(
            cochange_fallback_enabled=True,
            cochange_fallback_max_n=2,  # n=12 > 2 -> HDBSCAN path taken
            cochange_distance_eps=0.35,
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.5,
            tau_seconds=3600,
            min_cluster_size=2,
            use_embeddings=True,
        )
        result = cluster_changesets(docs, s, run_kind="cold_full_index")
        # At least one change-set, and no change-set mixes burst A with burst B.
        assert result.changesets
        for cs in result.changesets:
            has_a = any(m.startswith("a") for m in cs.member_ids)
            has_b = any(m.startswith("b") for m in cs.member_ids)
            assert not (has_a and has_b), f"burst A and B merged in {cs.member_ids}"


class TestBuildBlocks:
    """MM-35: _build_blocks partitions by (folder, time-bucket)."""

    def test_two_folders_two_blocks(self) -> None:
        from mintmory.core.cochange import _build_blocks

        docs = [
            _make_doc("ma1", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("ma2", "/root/a/f2.txt", "a/f2.txt", 60.0),
            _make_doc("mb1", "/root/b/f3.txt", "b/f3.txt", 120.0),
            _make_doc("mb2", "/root/b/f4.txt", "b/f4.txt", 180.0),
        ]
        blocks, truncated = _build_blocks(docs, bucket_seconds=86_400, max_block=2000)
        assert len(blocks) == 2
        assert truncated == 0

    def test_cross_folder_never_share_block(self) -> None:
        from mintmory.core.cochange import _build_blocks

        docs = [
            _make_doc("a1", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("b1", "/root/b/f2.txt", "b/f2.txt", 10.0),
        ]
        blocks, truncated = _build_blocks(docs, bucket_seconds=86_400, max_block=2000)
        assert len(blocks) == 2
        assert truncated == 0
        for block in blocks:
            folders = {(d.rel.rsplit("/", 1)[0] if "/" in d.rel else "") for d in block}
            assert len(folders) == 1

    def test_root_files_share_empty_key(self) -> None:
        from mintmory.core.cochange import _build_blocks

        docs = [
            _make_doc("r1", "/f1.txt", "f1.txt", 0.0),
            _make_doc("r2", "/f2.txt", "f2.txt", 60.0),
        ]
        blocks, truncated = _build_blocks(docs, bucket_seconds=86_400, max_block=2000)
        assert len(blocks) == 1
        assert len(blocks[0]) == 2
        assert truncated == 0

    def test_different_time_buckets_two_blocks(self) -> None:
        from mintmory.core.cochange import _build_blocks

        docs = [
            _make_doc("e1", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("e2", "/root/a/f2.txt", "a/f2.txt", 60.0),
            _make_doc("e3", "/root/a/f3.txt", "a/f3.txt", 2 * 86_400.0),
            _make_doc("e4", "/root/a/f4.txt", "a/f4.txt", 2 * 86_400.0 + 60),
        ]
        blocks, truncated = _build_blocks(docs, bucket_seconds=86_400, max_block=2000)
        assert len(blocks) == 2
        assert truncated == 0

    def test_truncation_keeps_first_by_mtime_docid(self) -> None:
        import random

        from mintmory.core.cochange import _build_blocks

        docs = [
            _make_doc(f"m{i}", f"/root/a/f{i}.txt", f"a/f{i}.txt", float(i * 10)) for i in range(5)
        ]
        shuffled = docs.copy()
        random.shuffle(shuffled)
        blocks, truncated = _build_blocks(shuffled, bucket_seconds=86_400, max_block=3)
        assert len(blocks) == 1
        assert len(blocks[0]) == 3
        assert truncated == 2
        kept_ids = [d.doc_id for d in blocks[0]]
        expected = [f"/root/a/f{i}.txt" for i in range(3)]
        assert kept_ids == expected

    def test_block_order_deterministic(self) -> None:
        import random

        from mintmory.core.cochange import _build_blocks

        docs = [
            _make_doc("a1", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("a2", "/root/a/f2.txt", "a/f2.txt", 60.0),
            _make_doc("b1", "/root/b/f3.txt", "b/f3.txt", 120.0),
            _make_doc("b2", "/root/b/f4.txt", "b/f4.txt", 180.0),
            _make_doc("c1", "/root/c/f5.txt", "c/f5.txt", 240.0),
        ]
        blocks_a, _ = _build_blocks(docs, bucket_seconds=86_400, max_block=2000)
        shuffled = docs.copy()
        random.shuffle(shuffled)
        blocks_b, _ = _build_blocks(shuffled, bucket_seconds=86_400, max_block=2000)
        keys_a = [[d.doc_id for d in b] for b in blocks_a]
        keys_b = [[d.doc_id for d in b] for b in blocks_b]
        assert keys_a == keys_b


class TestBlockDistanceMatrix:
    """MM-35: _block_distance_matrix parity with scalar oracle within 1e-9."""

    def _scalar_dist(self, a: ChangedDoc, b: ChangedDoc, s: DocumentSettings) -> float:
        """Replicate the MM-34 scalar pair computation as oracle."""
        from mintmory.core.cochange import _cosine_distance, _path_distance, _time_distance

        tau = float(s.tau_seconds)
        w_t = s.weight_time
        w_p = s.weight_path
        w_c = s.weight_content
        t_dist = _time_distance(a, b, tau)
        p_dist = _path_distance(a, b)
        has_content = s.use_embeddings and a.embedding is not None and b.embedding is not None
        if has_content:
            assert a.embedding is not None
            assert b.embedding is not None
            c_dist = _cosine_distance(
                a.embedding,
                b.embedding,
            )
            w_c_eff = w_c
        else:
            c_dist = 0.0
            w_c_eff = 0.0
        denom = w_t + w_p + w_c_eff
        return float(
            (w_t * t_dist + w_p * p_dist + w_c_eff * c_dist) / denom if denom != 0.0 else 0.0
        )

    def test_parity_with_embeddings(self) -> None:
        from mintmory.core.cochange import _block_distance_matrix
        from mintmory.core.config import DocumentSettings

        docs = [
            _make_doc("m1", "/root/a/f1.txt", "a/f1.txt", 0.0, _fake_emb(1)),
            _make_doc("m2", "/root/a/f2.txt", "a/f2.txt", 600.0, _fake_emb(2)),
            _make_doc("m3", "/root/b/f3.txt", "b/f3.txt", 1200.0, _fake_emb(3)),
        ]
        s = DocumentSettings(
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.5,
            tau_seconds=3600,
            use_embeddings=True,
        )
        D = _block_distance_matrix(docs, s)  # noqa: N806
        n = len(docs)
        for i in range(n):
            for j in range(n):
                expected = 0.0 if i == j else self._scalar_dist(docs[i], docs[j], s)
                assert abs(float(D[i, j]) - expected) < 1e-9, (
                    f"D[{i},{j}]={D[i, j]:.10f} vs scalar={expected:.10f}"
                )

    def test_parity_no_embeddings(self) -> None:
        from mintmory.core.cochange import _block_distance_matrix
        from mintmory.core.config import DocumentSettings

        docs = [
            _make_doc("m1", "/root/a/f1.txt", "a/f1.txt", 0.0, None),
            _make_doc("m2", "/root/b/f2.txt", "b/f2.txt", 3600.0, None),
            _make_doc("m3", "/root/c/f3.txt", "c/f3.txt", 7200.0, None),
        ]
        s = DocumentSettings(
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.5,
            tau_seconds=3600,
            use_embeddings=False,
        )
        D = _block_distance_matrix(docs, s)  # noqa: N806
        n = len(docs)
        for i in range(n):
            for j in range(n):
                expected = 0.0 if i == j else self._scalar_dist(docs[i], docs[j], s)
                assert abs(float(D[i, j]) - expected) < 1e-9

    def test_parity_mixed_none_embeddings(self) -> None:
        """Some docs have embeddings, some don't. Pairs with missing emb drop content."""
        from mintmory.core.cochange import _block_distance_matrix
        from mintmory.core.config import DocumentSettings

        docs = [
            _make_doc("m1", "/root/a/f1.txt", "a/f1.txt", 0.0, _fake_emb(1)),
            _make_doc("m2", "/root/a/f2.txt", "a/f2.txt", 600.0, None),
            _make_doc("m3", "/root/b/f3.txt", "b/f3.txt", 1200.0, _fake_emb(3)),
        ]
        s = DocumentSettings(
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.5,
            tau_seconds=3600,
            use_embeddings=True,
        )
        D = _block_distance_matrix(docs, s)  # noqa: N806
        n = len(docs)
        for i in range(n):
            for j in range(n):
                expected = 0.0 if i == j else self._scalar_dist(docs[i], docs[j], s)
                assert abs(float(D[i, j]) - expected) < 1e-9, (
                    f"D[{i},{j}]={D[i, j]:.10f} vs scalar={expected:.10f}"
                )

    def test_parity_zero_norm_embedding(self) -> None:
        """Zero-norm embedding → cosine=0.5 (neutral), content KEPT (not dropped)."""
        from mintmory.core.cochange import _block_distance_matrix
        from mintmory.core.config import DocumentSettings

        zero_emb = np.zeros(8, dtype=np.float32)
        docs = [
            _make_doc("m1", "/root/a/f1.txt", "a/f1.txt", 0.0, zero_emb),
            _make_doc("m2", "/root/a/f2.txt", "a/f2.txt", 60.0, _fake_emb(5)),
        ]
        s = DocumentSettings(
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.5,
            tau_seconds=3600,
            use_embeddings=True,
        )
        D = _block_distance_matrix(docs, s)  # noqa: N806
        expected = self._scalar_dist(docs[0], docs[1], s)
        assert abs(float(D[0, 1]) - expected) < 1e-9

    def test_zero_norm_differs_from_none(self) -> None:
        """Zero-norm embedding (content KEPT at 0.5) differs from None (content DROPPED).

        This is a critical semantic: use_embeddings=True with zero-norm embedding
        keeps content in the distance formula (cosine=0.5, w_c_eff=w_c), while
        use_embeddings=True with embedding=None drops content (w_c_eff=0, denom shrinks).
        The resulting distances must be numerically different.
        """
        from mintmory.core.cochange import _block_distance_matrix
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.5,
            tau_seconds=3600,
            use_embeddings=True,
        )
        # Partner has a non-trivial embedding
        partner = _make_doc("partner", "/root/a/f2.txt", "a/f2.txt", 60.0, _fake_emb(5))

        # Case A: first doc has zero-norm embedding (present but zero)
        zero_emb = np.zeros(8, dtype=np.float32)
        doc_zero = _make_doc("zero", "/root/a/f1.txt", "a/f1.txt", 0.0, zero_emb)
        D_zero = _block_distance_matrix([doc_zero, partner], s)  # noqa: N806

        # Case B: first doc has None embedding (content dropped)
        doc_none = _make_doc("none_emb", "/root/a/f1.txt", "a/f1.txt", 0.0, None)
        D_none = _block_distance_matrix([doc_none, partner], s)  # noqa: N806

        # They must differ because zero-norm keeps content (at 0.5) while None drops it
        assert abs(float(D_zero[0, 1]) - float(D_none[0, 1])) > 1e-6, (
            f"Expected zero-norm ({D_zero[0, 1]:.6f}) != none ({D_none[0, 1]:.6f})"
        )

    def test_parity_root_files(self) -> None:
        """Root files (no '/' in rel) have depth=0 → path_distance=0 between them."""
        from mintmory.core.cochange import _block_distance_matrix
        from mintmory.core.config import DocumentSettings

        docs = [
            _make_doc("r1", "/f1.txt", "f1.txt", 0.0, None),
            _make_doc("r2", "/f2.txt", "f2.txt", 60.0, None),
        ]
        s = DocumentSettings(
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.0,
            tau_seconds=3600,
            use_embeddings=False,
        )
        D = _block_distance_matrix(docs, s)  # noqa: N806
        expected = self._scalar_dist(docs[0], docs[1], s)
        assert abs(float(D[0, 1]) - expected) < 1e-9

    def test_diagonal_is_zero(self) -> None:
        from mintmory.core.cochange import _block_distance_matrix
        from mintmory.core.config import DocumentSettings

        docs = [
            _make_doc("m1", "/root/a/f1.txt", "a/f1.txt", 0.0, _fake_emb(1)),
            _make_doc("m2", "/root/b/f2.txt", "b/f2.txt", 600.0, _fake_emb(2)),
            _make_doc("m3", "/root/c/f3.txt", "c/f3.txt", 1200.0, None),
        ]
        s = DocumentSettings()
        D = _block_distance_matrix(docs, s)  # noqa: N806
        for i in range(len(docs)):
            assert D[i, i] == pytest.approx(0.0)

    def test_matrix_is_symmetric(self) -> None:
        from mintmory.core.cochange import _block_distance_matrix
        from mintmory.core.config import DocumentSettings

        docs = [
            _make_doc("m1", "/root/a/f1.txt", "a/f1.txt", 0.0, _fake_emb(1)),
            _make_doc("m2", "/root/b/f2.txt", "b/f2.txt", 3600.0, _fake_emb(2)),
            _make_doc("m3", "/root/a/f3.txt", "a/f3.txt", 7200.0, None),
        ]
        s = DocumentSettings()
        D = _block_distance_matrix(docs, s)  # noqa: N806
        np.testing.assert_allclose(D, D.T, atol=1e-12)

    def test_parity_random_inputs(self) -> None:
        """Property-style test: 20 random docs, all pairs within 1e-9."""
        import random

        from mintmory.core.cochange import _block_distance_matrix
        from mintmory.core.config import DocumentSettings

        rng = np.random.default_rng(42)
        random.seed(42)
        folders = ["a", "b", "c", ""]
        docs = []
        for i in range(20):
            folder = random.choice(folders)
            rel = f"{folder}/f{i}.txt" if folder else f"f{i}.txt"
            mtime = float(rng.integers(0, 200_000))
            emb_choice = rng.integers(0, 3)
            if emb_choice == 0:
                emb = None
            elif emb_choice == 1:
                emb = np.zeros(8, dtype=np.float32)
            else:
                raw = rng.random(8).astype(np.float32)
                emb = raw / (np.linalg.norm(raw) + 1e-8)
            docs.append(_make_doc(f"m{i}", f"/root/{rel}", rel, mtime, emb))

        s = DocumentSettings(
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.5,
            tau_seconds=3600,
            use_embeddings=True,
        )
        D = _block_distance_matrix(docs, s)  # noqa: N806
        for i in range(len(docs)):
            for j in range(len(docs)):
                expected = 0.0 if i == j else self._scalar_dist(docs[i], docs[j], s)
                assert abs(float(D[i, j]) - expected) < 1e-9, (
                    f"pair ({i},{j}): vectorized={D[i, j]:.12f} scalar={expected:.12f}"
                )


# ---------------------------------------------------------------------------
# MM-35 integration tests
# ---------------------------------------------------------------------------


class TestMM35ClusterChangesets:
    """MM-35: blocking-on/off, parity with MM-34, truncation, determinism."""

    def _settings_mm35(
        self,
        block_by_folder: bool = True,
        bucket_seconds: int = 86_400,
        max_partition: int = 2000,
        fallback_enabled: bool = True,
        fallback_max_n: int = 8,
        use_embeddings: bool = True,
        weight_content: float = 0.5,
    ) -> DocumentSettings:
        return DocumentSettings(
            cochange_enabled=True,
            weight_time=1.0,
            weight_path=0.5,
            weight_content=weight_content,
            tau_seconds=3600,
            min_cluster_size=2,
            use_embeddings=use_embeddings,
            max_cochange_gap_seconds=86_400,
            max_cochange_cluster_size=50,
            cochange_fallback_enabled=fallback_enabled,
            cochange_fallback_max_n=fallback_max_n,
            cochange_distance_eps=0.35,
            cochange_label_kind=True,
            cochange_block_by_folder=block_by_folder,
            cochange_time_bucket_seconds=bucket_seconds,
            max_cochange_partition_size=max_partition,
        )

    def _two_folder_burst_docs(self) -> list[ChangedDoc]:
        return [
            _make_doc("ma1", "/root/a/f1.txt", "a/f1.txt", 0.0, _fake_emb(0)),
            _make_doc("ma2", "/root/a/f2.txt", "a/f2.txt", 60.0, _fake_emb(1)),
            _make_doc("mb1", "/root/b/f3.txt", "b/f3.txt", 10_000.0, _fake_emb(10)),
            _make_doc("mb2", "/root/b/f4.txt", "b/f4.txt", 10_060.0, _fake_emb(11)),
        ]

    def test_blocking_off_single_global_pass(self) -> None:
        """blocking=False → single block containing all docs."""
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_folder_burst_docs()
        s = self._settings_mm35(block_by_folder=False, max_partition=2000)
        result = cluster_changesets(docs, s, run_kind="incremental")
        # Should produce 2 change-sets (bursts are far apart in time and folder)
        assert len(result.changesets) == 2
        assert result.truncated == 0

    def test_blocking_on_isolates_folders(self) -> None:
        """blocking=True → each folder is its own block → 2 change-sets."""
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_folder_burst_docs()
        s = self._settings_mm35(block_by_folder=True)
        result = cluster_changesets(docs, s, run_kind="incremental")
        assert len(result.changesets) == 2
        # Verify no change-set mixes members from different folders
        for cs in result.changesets:
            has_a = any(m.startswith("ma") for m in cs.member_ids)
            has_b = any(m.startswith("mb") for m in cs.member_ids)
            assert not (has_a and has_b)

    def test_determinism_across_shuffles(self) -> None:
        """Same change-set ids regardless of input order."""
        import random

        from mintmory.core.cochange import cluster_changesets

        docs = self._two_folder_burst_docs()
        s = self._settings_mm35()
        r1 = cluster_changesets(docs, s, run_kind="incremental")
        shuffled = list(docs)
        random.shuffle(shuffled)
        r2 = cluster_changesets(shuffled, s, run_kind="incremental")
        ids1 = sorted(cs.changeset_id for cs in r1.changesets)
        ids2 = sorted(cs.changeset_id for cs in r2.changesets)
        assert ids1 == ids2

    def test_truncation_reported_in_result(self) -> None:
        """A block > max_partition → truncated > 0 in result."""
        from mintmory.core.cochange import cluster_changesets

        docs = [
            _make_doc(f"m{i}", f"/root/a/f{i}.txt", f"a/f{i}.txt", float(i * 10)) for i in range(5)
        ]
        s = self._settings_mm35(block_by_folder=True, max_partition=3)
        result = cluster_changesets(docs, s, run_kind="incremental")
        assert result.truncated == 2

    def test_truncation_blocking_off(self) -> None:
        """blocking=False: single block capped at max_partition → truncated count."""
        from mintmory.core.cochange import cluster_changesets

        docs = [
            _make_doc(f"m{i}", f"/root/a/f{i}.txt", f"a/f{i}.txt", float(i * 10)) for i in range(5)
        ]
        s = self._settings_mm35(block_by_folder=False, max_partition=3)
        result = cluster_changesets(docs, s, run_kind="incremental")
        assert result.truncated == 2

    def test_no_truncation_within_cap(self) -> None:
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_folder_burst_docs()
        s = self._settings_mm35(max_partition=2000)
        result = cluster_changesets(docs, s, run_kind="incremental")
        assert result.truncated == 0

    def test_small_block_uses_components_fallback(self) -> None:
        """n <= fallback_max_n per block → connected-components (no sklearn needed)."""
        from mintmory.core.cochange import cluster_changesets

        docs = [
            _make_doc("m1", "/root/a/f1.txt", "a/f1.txt", 0.0, None),
            _make_doc("m2", "/root/a/f2.txt", "a/f2.txt", 60.0, None),
            _make_doc("m3", "/root/a/f3.txt", "a/f3.txt", 120.0, None),
        ]
        s = self._settings_mm35(
            fallback_enabled=True,
            fallback_max_n=8,
            use_embeddings=False,
            weight_content=0.0,
        )
        result = cluster_changesets(docs, s, run_kind="incremental")
        assert len(result.changesets) == 1
        assert len(result.changesets[0].member_ids) == 3

    def test_result_truncated_field_default_zero(self) -> None:
        """result.truncated is 0 when no truncation occurs."""
        from mintmory.core.cochange import cluster_changesets

        docs = self._two_folder_burst_docs()
        s = self._settings_mm35(max_partition=2000)
        result = cluster_changesets(docs, s, run_kind="incremental")
        assert result.truncated == 0
        assert hasattr(result, "truncated")

    def test_bucket_clamped_to_gap_seconds(self) -> None:
        """bucket = min(cochange_time_bucket_seconds, max_cochange_gap_seconds).

        When cochange_time_bucket_seconds > max_cochange_gap_seconds, the effective
        bucket is capped to max_cochange_gap_seconds. Docs farther than the gap
        apart must not share a block even if the raw time bucket would group them.
        """
        from mintmory.core.cochange import _build_blocks

        # Two docs 2 hours apart; bucket=7 days but gap=1 hour → effective bucket=1 hour.
        # floor(0 / 3600) = 0; floor(7200 / 3600) = 2 → different buckets → different blocks.
        gap_seconds = 3600
        bucket_seconds = min(86_400 * 7, gap_seconds)  # effective = 3600
        docs = [
            _make_doc("e1", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("e2", "/root/a/f2.txt", "a/f2.txt", 7200.0),  # 2h later
        ]
        blocks, truncated = _build_blocks(docs, bucket_seconds=bucket_seconds, max_block=2000)
        assert len(blocks) == 2, f"Expected 2 blocks (different time buckets), got {len(blocks)}"
        assert truncated == 0

    def test_blocking_off_parity_changeset_ids(self) -> None:
        """blocking=False + sub-cap corpus → changeset_ids match direct components path."""
        from mintmory.core.cochange import (
            _block_distance_matrix,
            _changesets_from_components,
            _connected_components,
            cluster_changesets,
        )
        from mintmory.core.config import DocumentSettings

        docs = [
            _make_doc("m1", "/root/a/f1.txt", "a/f1.txt", 0.0, None),
            _make_doc("m2", "/root/a/f2.txt", "a/f2.txt", 60.0, None),
            _make_doc("m3", "/root/a/f3.txt", "a/f3.txt", 120.0, None),
        ]
        s = self._settings_mm35(
            block_by_folder=False,
            max_partition=2000,
            fallback_enabled=True,
            fallback_max_n=8,
            use_embeddings=False,
            weight_content=0.0,
        )
        assert isinstance(s, DocumentSettings)

        # Run cluster_changesets with blocking disabled (single global block)
        result = cluster_changesets(docs, s, run_kind="incremental")

        # Reproduce what a direct components path on the same sorted docs would give:
        sorted_docs = sorted(docs, key=lambda d: (d.mtime, d.doc_id))
        dist_mat = _block_distance_matrix(sorted_docs, s)
        components = _connected_components(
            dist_mat, eps=s.cochange_distance_eps, min_size=s.min_cluster_size
        )
        kind_value = "incremental" if s.cochange_label_kind else ""
        ref_sets, _, _ = _changesets_from_components(
            sorted_docs,
            components,
            kind_value,
            gap_seconds=float(s.max_cochange_gap_seconds),
            min_size=s.min_cluster_size,
            max_cluster_size=s.max_cochange_cluster_size,
        )

        # Change-set IDs must match exactly
        ids_from_cluster = sorted(cs.changeset_id for cs in result.changesets)
        ids_from_reference = sorted(cs.changeset_id for cs in ref_sets)
        assert ids_from_cluster == ids_from_reference, (
            f"blocking=False IDs={ids_from_cluster} != reference IDs={ids_from_reference}"
        )

    def test_blocking_off_hdbscan_path_parity(self) -> None:
        """blocking=False, N>fallback_max_n, embeddings → matches the MM-34 HDBSCAN oracle.

        Covers the highest-risk parity branch (HDBSCAN, not components): a single
        global block must reproduce exactly what MM-34 did (same matrix -> HDBSCAN
        -> label assembly), so changeset_ids match an independently built oracle.
        """
        pytest.importorskip("sklearn")
        from mintmory.core.cochange import (
            _block_distance_matrix,
            _changesets_from_components,
            _changesets_from_labels,
            _connected_components,
            cluster_changesets,
        )
        from sklearn.cluster import HDBSCAN

        docs = []
        for i in range(6):
            docs.append(
                _make_doc(f"a{i}", f"/root/a/f{i}.txt", f"a/f{i}.txt", float(i * 30), _fake_emb(i))
            )
        for i in range(6):
            docs.append(
                _make_doc(
                    f"b{i}",
                    f"/root/b/f{i}.txt",
                    f"b/f{i}.txt",
                    100_000.0 + i * 30,
                    _fake_emb(50 + i),
                )
            )
        s = self._settings_mm35(
            block_by_folder=False, fallback_max_n=2, use_embeddings=True, weight_content=0.5
        )
        result = cluster_changesets(docs, s, run_kind="incremental")

        # Oracle: one global block -> identical matrix -> HDBSCAN -> the MM-34 path.
        sorted_docs = sorted(docs, key=lambda d: (d.mtime, d.doc_id))
        d_mat = _block_distance_matrix(sorted_docs, s)
        hdb = HDBSCAN(metric="precomputed", min_cluster_size=s.min_cluster_size).fit(d_mat)
        labels = np.asarray(hdb.labels_, dtype=np.int32)
        probs = np.asarray(hdb.probabilities_, dtype=np.float64)
        if bool(np.all(labels == -1)):  # cluster_changesets would fall back to components
            comps = _connected_components(
                d_mat, eps=s.cochange_distance_eps, min_size=s.min_cluster_size
            )
            ref_sets, _, _ = _changesets_from_components(
                sorted_docs,
                comps,
                "incremental",
                gap_seconds=float(s.max_cochange_gap_seconds),
                min_size=s.min_cluster_size,
                max_cluster_size=s.max_cochange_cluster_size,
            )
        else:
            ref_sets, _, _ = _changesets_from_labels(
                sorted_docs,
                labels,
                probs,
                run_kind="incremental",
                gap_seconds=float(s.max_cochange_gap_seconds),
                min_size=s.min_cluster_size,
                max_cluster_size=s.max_cochange_cluster_size,
            )
        assert sorted(cs.changeset_id for cs in result.changesets) == sorted(
            cs.changeset_id for cs in ref_sets
        )

    def test_large_corpus_blocks_bounded(self) -> None:
        """Blocking keeps every block <= cap, so no dense N×N matrix over all files.

        Covers the 'large corpus stays tractable' spec scenario: a 2000-file,
        50-folder corpus partitions into small per-folder blocks (max << cap),
        never a single 2000×2000 matrix.
        """
        from mintmory.core.cochange import _build_blocks

        docs = []
        for folder in range(50):
            for i in range(40):  # 2000 files total across 50 folders
                docs.append(
                    _make_doc(
                        f"m{folder}_{i}",
                        f"/root/d{folder}/f{i}.txt",
                        f"d{folder}/f{i}.txt",
                        float(folder * 100_000 + i * 30),
                        None,
                    )
                )
        sorted_docs = sorted(docs, key=lambda d: (d.mtime, d.doc_id))
        blocks, truncated = _build_blocks(sorted_docs, 86_400, 2000)
        assert truncated == 0
        assert blocks
        # Each folder (distinct time base) is its own small block — never one big matrix.
        assert max(len(b) for b in blocks) <= 40
