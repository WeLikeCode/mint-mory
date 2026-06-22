"""
core/cochange.py — document co-change clustering and store I/O (MM-33/MM-34).

Pure clustering (no store, no network) + thin store wrappers for applying
change-sets and querying co-changed documents.

The clustering uses HDBSCAN from scikit-learn (optional ``cochange`` extra).
When scikit-learn is not installed, ``cluster_changesets`` raises
``CoChangeUnavailable`` — the CLI catches this and prints an install hint.
The connected-components fallback (MM-34 F) never requires scikit-learn.

MM-34 additions:
- CoChangeResult dataclass (cluster_changesets now returns this, not list[ChangeSet])
- kind: str field on ChangeSet (propagated from run_kind parameter)
- _split_on_time_gap: post-cluster split on adjacent mtime gap > gap_seconds
- _connected_components: pure union-find fallback (no sklearn)
- _changesets_from_components: builds ChangeSet clusters from components
- _build_changeset: shared single-changeset builder
- Hybrid fallback in cluster_changesets: when n <= fallback_max_n OR all-noise
- documents_timeline: NULL-safe record_role != 'chunk' predicate
- changed_with: includes kind from metadata.changeset_kind
- apply_changesets: writes changeset_kind to member metadata

Distance matrix (precomputed, N×N, all terms in [0, 1]):
    time(a,b) = min(1.0, |mtime_a - mtime_b| / tau_seconds)
    path(a,b) = (depth_a + depth_b - 2·common_prefix_len)
                / max(1, depth_a + depth_b)      # parent-dir parts of rel
    content(a,b) = (1 - cosine(emb_a, emb_b)) / 2
                   (dropped when either embedding is None or use_embeddings=False)
    D[a,b] = (w_t·time + w_p·path + w_c·content) / (w_t + w_p + w_c_effective)

changeset_id = sha1("|".join(sorted doc_ids) + "@{max_mtime:.0f}")[:16]
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from mintmory.core.config import DocumentSettings
    from mintmory.core.storage import StorageAdapter


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class CoChangeUnavailable(Exception):  # noqa: N818
    """Raised when scikit-learn is not installed (lazy import failed).

    Spec-mandated name (design.md §2); N818 suppressed intentionally.
    """


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChangedDoc:
    """A document that changed in the current index-tree run."""

    memory_id: str  # the file-record memory id (the co-change node)
    doc_id: str  # stable id = absolute path
    rel: str  # root-relative POSIX path (for path distance)
    mtime: float  # epoch seconds
    embedding: NDArray[np.float32] | None  # file-record / content embedding


@dataclass(frozen=True)
class ChangeSet:
    """A cluster of documents that co-changed in the same run."""

    changeset_id: str  # deterministic: sha1(sorted doc_ids + max mtime)[:16]
    member_ids: list[str]  # memory ids, sorted
    observed_at: str  # ISO-8601 naive-UTC (max mtime in cluster)
    edges: list[tuple[str, str, float]]  # (src_id, dst_id, strength) pairwise within cluster
    order: list[str]  # member ids sorted by mtime (for 'before' edges)
    kind: str = "incremental"  # MM-34 E: 'cold_full_index' | 'incremental'


@dataclass
class CoChangeResult:
    """Return value of cluster_changesets (MM-34 B)."""

    changesets: list[ChangeSet]
    dropped_oversized: int  # change-sets dropped because len > max_cochange_cluster_size
    dropped_singletons: int  # gap-split fragments dropped because len < min_cluster_size
    truncated: int = 0  # MM-35: docs dropped from oversized blocks before clustering


# ---------------------------------------------------------------------------
# Distance helpers
# ---------------------------------------------------------------------------


def _time_distance(a: ChangedDoc, b: ChangedDoc, tau: float) -> float:
    """Normalised time distance in [0, 1]."""
    return min(1.0, abs(a.mtime - b.mtime) / tau)


def _path_distance(a: ChangedDoc, b: ChangedDoc) -> float:
    """Normalised path distance based on parent-directory parts of rel, in [0, 1]."""
    parts_a = a.rel.split("/")[:-1]  # parent dirs only (drop filename)
    parts_b = b.rel.split("/")[:-1]
    depth_a = len(parts_a)
    depth_b = len(parts_b)
    # Count common prefix length
    common = 0
    for pa, pb in zip(parts_a, parts_b, strict=False):
        if pa == pb:
            common += 1
        else:
            break
    total = depth_a + depth_b
    return (total - 2 * common) / max(1, total)


def _cosine_distance(a: NDArray[np.float32], b: NDArray[np.float32]) -> float:
    """Cosine distance in [0, 1]: (1 - cosine_similarity) / 2."""
    dot = float(np.dot(a, b))
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.5  # undefined → neutral
    cosine_sim = dot / (na * nb)
    # Clamp to [-1, 1] for numerical safety, then map to [0, 1]
    cosine_sim = max(-1.0, min(1.0, cosine_sim))
    return (1.0 - cosine_sim) / 2.0


# ---------------------------------------------------------------------------
# MM-34 A: post-cluster time-gap split
# ---------------------------------------------------------------------------


def _split_on_time_gap(
    cluster_docs: list[ChangedDoc],
    gap_seconds: float,
    min_size: int,
) -> tuple[list[list[ChangedDoc]], int]:
    """Split a cluster into sub-groups wherever an adjacent mtime gap exceeds gap_seconds.

    Sorts by (mtime, doc_id) for determinism, then walks adjacent pairs.
    Sub-groups with len < min_size are dropped and counted.

    Returns:
        (valid_sub_groups, dropped_singleton_count)
    """
    if not cluster_docs:
        return [], 0

    sorted_docs = sorted(cluster_docs, key=lambda d: (d.mtime, d.doc_id))

    groups: list[list[ChangedDoc]] = []
    current: list[ChangedDoc] = [sorted_docs[0]]
    for doc in sorted_docs[1:]:
        if doc.mtime - current[-1].mtime > gap_seconds:
            groups.append(current)
            current = [doc]
        else:
            current.append(doc)
    groups.append(current)

    valid: list[list[ChangedDoc]] = []
    dropped = 0
    for g in groups:
        if len(g) >= min_size:
            valid.append(g)
        else:
            dropped += 1
    return valid, dropped


# ---------------------------------------------------------------------------
# MM-34 F: connected-components fallback (pure numpy / union-find, no sklearn)
# ---------------------------------------------------------------------------


def _connected_components(
    dist_matrix: NDArray[np.float64],
    eps: float,
    min_size: int,
) -> list[list[int]]:
    """Union-find connected components over a symmetric distance matrix.

    Two nodes i, j are in the same component when dist_matrix[i, j] <= eps.
    Components with len < min_size are excluded.

    Deterministic: node order follows the caller's matrix row order
    (cluster_changesets uses (mtime, doc_id) sort, so this is stable).
    Does NOT require scikit-learn.
    """
    n = dist_matrix.shape[0]
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression (halving)
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i in range(n):
        for j in range(i + 1, n):
            if dist_matrix[i, j] <= eps:
                union(i, j)

    comp: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        comp[find(i)].append(i)

    return [sorted(members) for members in comp.values() if len(members) >= min_size]


# ---------------------------------------------------------------------------
# Internal: build one ChangeSet from a list of ChangedDoc
# ---------------------------------------------------------------------------


def _build_changeset(
    docs: list[ChangedDoc],
    *,
    strength_fn: Callable[[int, int], float],
    run_kind: str,
) -> ChangeSet:
    """Build a single ChangeSet from a group of ChangedDoc (already gap-split and capped).

    Args:
        docs: The members of this change-set (any order; sorted internally).
        strength_fn: Callable(i, j) → float; edge strength for docs[i] <-> docs[j].
        run_kind: Kind tag propagated to ChangeSet.kind.

    The changeset_id is deterministic: sha1(sorted doc_ids + "@{max_mtime:.0f}")[:16].
    """
    doc_ids_sorted = sorted(d.doc_id for d in docs)
    max_mtime = max(d.mtime for d in docs)

    payload = "|".join(doc_ids_sorted) + f"@{max_mtime:.0f}"
    changeset_id = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]  # noqa: S324

    observed_at = datetime.fromtimestamp(max_mtime, tz=UTC).replace(tzinfo=None).isoformat()
    member_ids = sorted(d.memory_id for d in docs)

    edges: list[tuple[str, str, float]] = []
    for ci in range(len(docs)):
        for cj in range(ci + 1, len(docs)):
            strength = float(max(0.0, min(1.0, strength_fn(ci, cj))))
            edges.append((docs[ci].memory_id, docs[cj].memory_id, strength))

    order_docs = sorted(docs, key=lambda d: (d.mtime, d.doc_id))
    order = [d.memory_id for d in order_docs]

    return ChangeSet(
        changeset_id=changeset_id,
        member_ids=member_ids,
        observed_at=observed_at,
        edges=edges,
        order=order,
        kind=run_kind,
    )


def _changesets_from_components(
    sorted_docs: list[ChangedDoc],
    components: list[list[int]],
    run_kind: str,
    gap_seconds: float,
    min_size: int,
    max_cluster_size: int,
) -> tuple[list[ChangeSet], int, int]:
    """Build ChangeSets from connected-components clusters (MM-34 F fallback).

    Each component is a list of indices into sorted_docs. Edge strength is 1.0
    (no HDBSCAN membership probability available for this path). Passes through
    the same _split_on_time_gap (A) and size cap (B) as the HDBSCAN path.

    Returns:
        (changesets, dropped_oversized, dropped_singletons)
    """
    all_sets: list[ChangeSet] = []
    total_oversized = 0
    total_singletons = 0

    for component in components:
        cluster_docs = [sorted_docs[i] for i in component]
        sub_groups, singletons = _split_on_time_gap(cluster_docs, gap_seconds, min_size)
        total_singletons += singletons
        for group in sub_groups:
            if len(group) > max_cluster_size:
                total_oversized += 1
                continue
            cs = _build_changeset(group, strength_fn=lambda _ci, _cj: 1.0, run_kind=run_kind)
            all_sets.append(cs)

    return all_sets, total_oversized, total_singletons


# ---------------------------------------------------------------------------
# MM-35: blocking by (folder, time-bucket)
# ---------------------------------------------------------------------------


def _build_blocks(
    docs: list[ChangedDoc],
    bucket_seconds: int,
    max_block: int,
) -> tuple[list[list[ChangedDoc]], int]:
    """Partition changed docs into clustering blocks by (parent_folder, time_bucket).

    Algorithm (design.md §2):
    1. Sort docs by (mtime, doc_id) for global determinism.
    2. Key each doc: folder = rel.rsplit("/", 1)[0] if "/" in rel else "".
       bucket = floor(mtime / bucket_seconds).
    3. Group by (folder, bucket); iterate keys in sorted order (determinism).
    4. Truncate blocks longer than max_block to first max_block docs
       (already in (mtime, doc_id) order); count total truncated docs.

    Returns:
        (blocks, total_truncated_count)
    """
    # Sort by (mtime, doc_id) for global determinism
    sorted_docs = sorted(docs, key=lambda d: (d.mtime, d.doc_id))

    groups: dict[tuple[str, int], list[ChangedDoc]] = defaultdict(list)
    for d in sorted_docs:
        folder = d.rel.rsplit("/", 1)[0] if "/" in d.rel else ""
        bucket = int(math.floor(d.mtime / bucket_seconds))
        groups[(folder, bucket)].append(d)

    total_truncated = 0
    blocks: list[list[ChangedDoc]] = []
    for key in sorted(groups.keys()):
        group = groups[key]
        if len(group) > max_block:
            total_truncated += len(group) - max_block
            group = group[:max_block]
        blocks.append(group)

    return blocks, total_truncated


def _block_distance_matrix(
    block: list[ChangedDoc],
    s: DocumentSettings,
) -> NDArray[np.float64]:
    """Vectorized per-block composite distance matrix (MM-35).

    Numerically identical (within 1e-9) to the scalar _time_distance /
    _path_distance / _cosine_distance composition for every pair.

    Content term rules (replicated from MM-34 cluster_changesets loop):
    - use_embeddings=False OR embedding is None for either doc → content DROPPED
      (w_c_eff=0, NOT neutral 0.5; denominator shrinks)
    - embedding present but zero-norm → cosine returns 0.5 (neutral), content KEPT
      (w_c_eff = w_c; this is the _cosine_distance zero-norm behaviour)
    """
    k = len(block)
    w_t = s.weight_time
    w_p = s.weight_path
    w_c = s.weight_content
    tau = float(s.tau_seconds)

    # --- Time term (k x k broadcast) ---
    m = np.array([d.mtime for d in block], dtype=np.float64)
    time_mat: NDArray[np.float64] = np.minimum(1.0, np.abs(m[:, None] - m[None, :]) / tau)

    # --- Path term (bounded loop over k rows) ---
    parts: list[list[str]] = [d.rel.split("/")[:-1] for d in block]
    depths = np.array([len(p) for p in parts], dtype=np.float64)
    path_mat: NDArray[np.float64] = np.zeros((k, k), dtype=np.float64)
    for i in range(k):
        for j in range(i + 1, k):
            common = 0
            for pi, pj in zip(parts[i], parts[j], strict=False):
                if pi == pj:
                    common += 1
                else:
                    break
            da = depths[i]
            db = depths[j]
            total = da + db
            val = (total - 2.0 * common) / max(1.0, total)
            path_mat[i, j] = val
            path_mat[j, i] = val

    # --- Content term ---
    # has_emb[i]: use_embeddings AND embedding is not None (not zero-norm — zero-norm is kept)
    has_emb = np.array(
        [s.use_embeddings and d.embedding is not None for d in block],
        dtype=bool,
    )
    # w_c_mask[i,j]: True iff BOTH embeddings present (and use_embeddings)
    w_c_mask: NDArray[np.bool_] = has_emb[:, None] & has_emb[None, :]

    content_mat: NDArray[np.float64] = np.zeros((k, k), dtype=np.float64)

    if s.use_embeddings and np.any(has_emb):
        # Cosine distance: replicate _cosine_distance scalar logic exactly per pair.
        # The scalar operates on float32 arrays: dot and norm are float32 operations
        # converted to Python float. We must match this precisely to stay within 1e-9.
        # Key: np.linalg.norm(arr_f32) on an individual array differs from
        # np.linalg.norm(matrix_f32, axis=1) for the same row — LAPACK SNRM2 vs
        # a different reduction path. So we cache per-doc norms from the original
        # embedding arrays, not from a stacked matrix.
        emb_list: list[NDArray[np.float32] | None] = [d.embedding for d in block]
        norms_f32: list[float] = [
            float(np.linalg.norm(e)) if e is not None else 0.0 for e in emb_list
        ]

        raw_content: NDArray[np.float64] = np.zeros((k, k), dtype=np.float64)
        for i in range(k):
            if not has_emb[i]:
                continue
            ei = emb_list[i]
            assert ei is not None  # noqa: S101
            na = norms_f32[i]
            for j in range(i + 1, k):
                if not has_emb[j]:
                    continue
                ej = emb_list[j]
                assert ej is not None  # noqa: S101
                dot_val = float(np.dot(ei, ej))
                nb = norms_f32[j]
                if na == 0.0 or nb == 0.0:
                    c = 0.5  # zero-norm → neutral (matching _cosine_distance)
                else:
                    sim_ij = max(-1.0, min(1.0, dot_val / (na * nb)))
                    c = (1.0 - sim_ij) / 2.0
                raw_content[i, j] = c
                raw_content[j, i] = c

        # Apply content only where BOTH embeddings are present (w_c_mask)
        content_mat = np.where(w_c_mask, raw_content, 0.0)

    # --- Combine with per-pair effective weights ---
    w_c_eff_mat: NDArray[np.float64] = np.where(w_c_mask, w_c, 0.0)
    denom: NDArray[np.float64] = w_t + w_p + w_c_eff_mat
    numer: NDArray[np.float64] = w_t * time_mat + w_p * path_mat + w_c_eff_mat * content_mat
    # Guard the divide so an all-zero-weight config (ge=0.0 permits it) yields 0.0
    # without a RuntimeWarning; denom==0 only when every effective weight is 0.
    dist: NDArray[np.float64] = np.zeros((k, k), dtype=np.float64)
    np.divide(numer, denom, out=dist, where=denom != 0.0)

    # Force diagonal to 0.0; matrix is symmetric by construction but enforce it
    np.fill_diagonal(dist, 0.0)

    return dist


# ---------------------------------------------------------------------------
# Core clustering
# ---------------------------------------------------------------------------


def _cluster_one_block(
    block: list[ChangedDoc],
    dist_matrix: NDArray[np.float64],
    s: DocumentSettings,
    kind_value: str,
) -> tuple[list[ChangeSet], int, int]:
    """Run the MM-34 fallback-or-HDBSCAN decision on a single pre-built block.

    Args:
        block: The documents in this block (already sorted by (mtime, doc_id)).
        dist_matrix: The precomputed N×N distance matrix for this block.
        s: DocumentSettings.
        kind_value: The kind tag string (already resolved from run_kind + cochange_label_kind).

    Returns:
        (changesets, dropped_oversized, dropped_singletons)

    Decision logic (MM-34):
    1. If cochange_fallback_enabled AND len(block) <= cochange_fallback_max_n:
       → connected-components at cochange_distance_eps
    2. Else: HDBSCAN(metric='precomputed', min_cluster_size).
       If all labels == -1 AND fallback enabled → connected-components.
       Else → _changesets_from_labels.
    """
    n = len(block)
    gap = float(s.max_cochange_gap_seconds)
    min_size = s.min_cluster_size
    max_size = s.max_cochange_cluster_size
    eps = float(s.cochange_distance_eps)

    use_fallback_directly = s.cochange_fallback_enabled and n <= s.cochange_fallback_max_n
    if use_fallback_directly:
        components = _connected_components(dist_matrix, eps, min_size)
        return _changesets_from_components(block, components, kind_value, gap, min_size, max_size)

    # HDBSCAN path — lazy import so the connected-components fallback never requires sklearn
    try:
        from sklearn.cluster import HDBSCAN
    except ImportError as exc:
        raise CoChangeUnavailable(
            "scikit-learn is not installed; run: pip install 'mintmory[cochange]'"
        ) from exc

    hdb = HDBSCAN(metric="precomputed", min_cluster_size=min_size)
    hdb.fit(dist_matrix)
    labels: NDArray[np.int32] = np.asarray(hdb.labels_, dtype=np.int32)
    probs: NDArray[np.float64] = np.asarray(hdb.probabilities_, dtype=np.float64)

    if bool(np.all(labels == -1)) and s.cochange_fallback_enabled:
        components = _connected_components(dist_matrix, eps, min_size)
        return _changesets_from_components(block, components, kind_value, gap, min_size, max_size)

    return _changesets_from_labels(
        block,
        labels,
        probs,
        run_kind=kind_value,
        gap_seconds=gap,
        min_size=min_size,
        max_cluster_size=max_size,
    )


def cluster_changesets(
    docs: list[ChangedDoc],
    s: DocumentSettings,
    *,
    run_kind: str = "incremental",
) -> CoChangeResult:
    """Cluster changed documents into change-sets using HDBSCAN or connected-components.

    MM-35: Partitions docs into blocks by (parent_folder, time_bucket) before clustering,
    then runs the MM-34 fallback-or-HDBSCAN decision per block using a vectorized
    distance matrix (_block_distance_matrix). Returns CoChangeResult with a truncated
    field counting docs dropped from oversized blocks before clustering.

    Algorithm:
    1. Return early if fewer than 2 docs or cochange_enabled is False.
    2. Sort docs by (mtime, doc_id) for determinism.
    3. If cochange_block_by_folder: partition into (folder, time_bucket) blocks via
       _build_blocks, capping each block at max_cochange_partition_size.
       Else: use a single global block, also capped at max_cochange_partition_size.
    4. For each block with len >= min_cluster_size:
       a. Build per-block N×N distance matrix with _block_distance_matrix.
       b. Run _cluster_one_block (MM-34 decision: fallback or HDBSCAN).
    5. Accumulate changesets, dropped_oversized, dropped_singletons, truncated.
    6. Return CoChangeResult.

    Returns CoChangeResult with empty changesets when:
    - fewer than 2 docs, or
    - s.cochange_enabled is False.

    Raises CoChangeUnavailable if scikit-learn is not installed AND the HDBSCAN
    path is taken for any block (the connected-components fallback never requires sklearn).
    """
    if len(docs) < 2 or not s.cochange_enabled:
        return CoChangeResult(changesets=[], dropped_oversized=0, dropped_singletons=0, truncated=0)

    # Sort for determinism. _build_blocks also sorts internally;
    # the duplicate sort is cheap and keeps the blocking=False path consistent.
    sorted_docs = sorted(docs, key=lambda d: (d.mtime, d.doc_id))

    # E: cochange_label_kind gates whether change-sets carry a kind tag. When off,
    # kind is blanked so apply_changesets writes no metadata.changeset_kind.
    kind_value = run_kind if s.cochange_label_kind else ""

    # 2. Build blocks
    bucket = min(s.cochange_time_bucket_seconds, s.max_cochange_gap_seconds)
    if s.cochange_block_by_folder:
        blocks, total_truncated = _build_blocks(
            sorted_docs, bucket_seconds=bucket, max_block=s.max_cochange_partition_size
        )
    else:
        # Single global block, still capped at max_cochange_partition_size
        capped = sorted_docs[: s.max_cochange_partition_size]
        total_truncated = max(0, len(sorted_docs) - len(capped))
        blocks = [capped]

    # 3. Cluster each block and accumulate
    all_changesets: list[ChangeSet] = []
    total_oversized = 0
    total_singletons = 0

    for block in blocks:
        if len(block) < s.min_cluster_size:
            continue
        block_dist = _block_distance_matrix(block, s)
        sets, dropped_over, dropped_sing = _cluster_one_block(block, block_dist, s, kind_value)
        all_changesets.extend(sets)
        total_oversized += dropped_over
        total_singletons += dropped_sing

    return CoChangeResult(
        changesets=all_changesets,
        dropped_oversized=total_oversized,
        dropped_singletons=total_singletons,
        truncated=total_truncated,
    )


def _changesets_from_labels(
    sorted_docs: list[ChangedDoc],
    labels: NDArray[np.int32],
    probs: NDArray[np.float64],
    *,
    run_kind: str = "incremental",
    gap_seconds: float = 86_400.0,
    min_size: int = 2,
    max_cluster_size: int = 50,
) -> tuple[list[ChangeSet], int, int]:
    """Build ChangeSets from HDBSCAN cluster labels.

    Label -1 (noise) is excluded. Each raw cluster passes through
    _split_on_time_gap (A) then the size cap (B).

    Returns:
        (changesets, dropped_oversized, dropped_singletons)
    """
    clusters: dict[int, list[int]] = defaultdict(list)
    for idx, label in enumerate(labels):
        if int(label) >= 0:  # -1 == noise → skip
            clusters[int(label)].append(idx)

    all_sets: list[ChangeSet] = []
    total_oversized = 0
    total_singletons = 0

    for _label, indices in sorted(clusters.items()):
        cluster_docs = [sorted_docs[i] for i in indices]

        # A: gap split
        sub_groups, singletons = _split_on_time_gap(cluster_docs, gap_seconds, min_size)
        total_singletons += singletons

        # B + assemble: size cap + ChangeSet per surviving fragment
        for group in sub_groups:
            if len(group) > max_cluster_size:
                total_oversized += 1
                continue

            # Probability lookup by doc_id (from original sorted_docs indices)
            prob_by_docid: dict[str, float] = {
                sorted_docs[i].doc_id: float(probs[i]) for i in indices
            }

            def _make_strength(
                g: list[ChangedDoc], pbd: dict[str, float]
            ) -> Callable[[int, int], float]:
                def _s(ci: int, cj: int) -> float:
                    pa = pbd.get(g[ci].doc_id, 0.0)
                    pb = pbd.get(g[cj].doc_id, 0.0)
                    return float(max(0.0, min(1.0, min(pa, pb))))

                return _s

            cs = _build_changeset(
                group,
                strength_fn=_make_strength(group, prob_by_docid),
                run_kind=run_kind,
            )
            all_sets.append(cs)

    return all_sets, total_oversized, total_singletons


# ---------------------------------------------------------------------------
# Store application
# ---------------------------------------------------------------------------


def apply_changesets(
    store: StorageAdapter,
    sets: list[ChangeSet],
    method: str = "hdbscan",
) -> int:
    """Apply change-sets to the store.

    For each member memory: merge changeset_id / changeset_observed_at /
    changeset_method / changeset_kind (MM-34 E) into the memory's metadata via
    update_memory.

    For each cluster: delete existing concept_links with entity=f"changeset:{id}"
    (idempotency), then insert pairwise relates_to edges and consecutive before
    edges along order.

    Returns the count of change-sets applied.

    Idempotency: edges are deleted by entity=f"changeset:{id}" before
    re-insertion. Re-running on the same inputs produces identical ids and
    re-applies safely.
    """
    from mintmory.core.types import ConceptLink, ConceptLinkType, LinkSource

    for cs in sets:
        entity_tag = f"changeset:{cs.changeset_id}"

        # Idempotency: delete prior edges for this changeset entity
        conn = store.connect()
        conn.execute(
            "DELETE FROM concept_links WHERE entity = ?",
            (entity_tag,),
        )
        conn.commit()

        # Merge metadata on each member
        for mid in cs.member_ids:
            mem = store.get_memory(mid)
            if mem is None:
                continue
            merged_meta: dict[str, Any] = dict(mem.metadata)
            merged_meta["changeset_id"] = cs.changeset_id
            merged_meta["changeset_observed_at"] = cs.observed_at
            merged_meta["changeset_method"] = method
            if cs.kind:  # MM-34 E: blank when cochange_label_kind is off
                merged_meta["changeset_kind"] = cs.kind
            store.update_memory(mid, metadata=merged_meta)

        # Pairwise relates_to edges within cluster
        for src_id, dst_id, strength in cs.edges:
            link = ConceptLink(
                source_memory_id=src_id,
                target_memory_id=dst_id,
                link_type=ConceptLinkType.RELATES_TO,
                entity=entity_tag,
                strength=strength,
                confidence=strength,
                source=LinkSource.INFERENCE,
            )
            store.add_link(link)

        # Consecutive before edges along order
        for i in range(len(cs.order) - 1):
            before_link = ConceptLink(
                source_memory_id=cs.order[i],
                target_memory_id=cs.order[i + 1],
                link_type=ConceptLinkType.BEFORE,
                entity=entity_tag,
                strength=1.0,
                confidence=1.0,
                source=LinkSource.INFERENCE,
            )
            store.add_link(before_link)

    return len(sets)


# ---------------------------------------------------------------------------
# Read queries
# ---------------------------------------------------------------------------


def changed_with(store: StorageAdapter, path: str) -> list[dict[str, Any]]:
    """Return peer documents that co-changed with the document at ``path``.

    Each result has: {path, strength, observed_at, kind}.
    MM-34: kind is taken from peer metadata.changeset_kind.
    """
    conn = store.connect()

    rows = conn.execute(
        "SELECT id, metadata FROM memories "
        "WHERE source = 'document' AND is_archived = 0 "
        "AND json_extract(metadata, '$.path') = ? "
        "ORDER BY rowid DESC",
        (path,),
    ).fetchall()

    if not rows:
        return []

    target_row = rows[0]
    target_id: str = target_row["id"]
    target_meta: dict[str, Any] = json.loads(target_row["metadata"] or "{}")
    changeset_id: str | None = target_meta.get("changeset_id")

    if not changeset_id:
        return []

    entity_tag = f"changeset:{changeset_id}"

    peer_rows = conn.execute(
        "SELECT id, metadata FROM memories "
        "WHERE source = 'document' AND is_archived = 0 "
        "AND json_extract(metadata, '$.changeset_id') = ? "
        "AND id != ?",
        (changeset_id, target_id),
    ).fetchall()

    results: list[dict[str, Any]] = []
    for peer in peer_rows:
        peer_id: str = peer["id"]
        peer_meta: dict[str, Any] = json.loads(peer["metadata"] or "{}")
        peer_path: str = peer_meta.get("path", "")
        observed_at: str = peer_meta.get("changeset_observed_at", "")
        kind: str = peer_meta.get("changeset_kind", "")  # MM-34 E

        link_row = conn.execute(
            "SELECT strength FROM concept_links "
            "WHERE link_type = 'relates_to' AND entity = ? "
            "AND ((source_memory_id = ? AND target_memory_id = ?) "
            "     OR (source_memory_id = ? AND target_memory_id = ?))",
            (entity_tag, target_id, peer_id, peer_id, target_id),
        ).fetchone()
        strength = float(link_row["strength"]) if link_row else 0.0

        results.append(
            {
                "path": peer_path,
                "strength": strength,
                "observed_at": observed_at,
                "kind": kind,  # MM-34 E
            }
        )

    return results


def documents_timeline(
    store: StorageAdapter,
    *,
    since: str | None = None,
    from_iso: str | None = None,
    to_iso: str | None = None,
    collection: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return document memories newest-first (by valid_from) in the given window.

    Each element has: {date, collection, path, title, valid_from}.
    Only source='document' records appear.
    MM-34 D: Body chunks (record_role='chunk') are excluded via a NULL-safe predicate
    so legacy file-records without record_role still appear.

    When no window is specified (since/from_iso/to_iso all None), all documents
    are returned (no time restriction).
    """
    now = datetime.now(UTC).replace(tzinfo=None)

    if since is not None or from_iso is not None or to_iso is not None:
        from mintmory.core.history.query import resolve_window

        start, end = resolve_window(since=since, from_iso=from_iso, to_iso=to_iso, now=now)
    else:
        start = datetime(1970, 1, 1)
        end = datetime(9999, 12, 31, 23, 59, 59)

    conn = store.connect()
    where = [
        "source = 'document'",
        "is_archived = 0",
        "valid_from IS NOT NULL",
        "valid_from >= ?",
        "valid_from <= ?",
        # MM-34 D: exclude body chunks; NULL-safe so legacy records without record_role still appear
        "(json_extract(metadata, '$.record_role') IS NULL "
        "OR json_extract(metadata, '$.record_role') != 'chunk')",
    ]
    params: list[Any] = [start.isoformat(), end.isoformat()]

    if collection is not None:
        where.append("json_extract(metadata, '$.collection') = ?")
        params.append(collection)

    params.append(limit)

    rows = conn.execute(
        "SELECT content, metadata, valid_from FROM memories "
        "WHERE " + " AND ".join(where) + " "
        "ORDER BY valid_from DESC "
        "LIMIT ?",
        params,
    ).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        meta: dict[str, Any] = json.loads(row["metadata"] or "{}")
        valid_from: str = row["valid_from"] or ""
        date_str = valid_from[:10]
        title = meta.get("rel") or (row["content"] or "")[:80]
        results.append(
            {
                "date": date_str,
                "collection": meta.get("collection", ""),
                "path": meta.get("path", ""),
                "title": title,
                "valid_from": valid_from,
            }
        )

    return results
