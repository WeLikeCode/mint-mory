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

    from collections import defaultdict

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
# Core clustering
# ---------------------------------------------------------------------------


def cluster_changesets(
    docs: list[ChangedDoc],
    s: DocumentSettings,
    *,
    run_kind: str = "incremental",
) -> CoChangeResult:
    """Cluster changed documents into change-sets using HDBSCAN or connected-components.

    MM-34: Returns CoChangeResult (was list[ChangeSet]).

    Algorithm:
    1. Sort docs by (mtime, doc_id) for determinism.
    2. Build a precomputed N×N float64 distance matrix.
    3a. If cochange_fallback_enabled AND n <= cochange_fallback_max_n:
        skip HDBSCAN, use connected-components at cochange_distance_eps.
    3b. Else: fit HDBSCAN(metric='precomputed', min_cluster_size).
        If it returns all-noise (every label == -1) AND fallback enabled:
        use connected-components on the same matrix.
    4. Feed raw clusters through _split_on_time_gap (A) and size cap (B).
    5. Return CoChangeResult.

    Returns CoChangeResult with empty changesets when:
    - fewer than 2 docs, or
    - s.cochange_enabled is False.

    Raises CoChangeUnavailable if scikit-learn is not installed AND the HDBSCAN
    path is taken (the connected-components fallback never requires sklearn).
    """
    if len(docs) < 2 or not s.cochange_enabled:
        return CoChangeResult(changesets=[], dropped_oversized=0, dropped_singletons=0)

    # 1. Sort for determinism
    sorted_docs = sorted(docs, key=lambda d: (d.mtime, d.doc_id))
    n = len(sorted_docs)

    # E: cochange_label_kind gates whether change-sets carry a kind tag. When off,
    # kind is blanked so apply_changesets writes no metadata.changeset_kind.
    kind_value = run_kind if s.cochange_label_kind else ""

    # 2. Build N×N distance matrix
    w_t = s.weight_time
    w_p = s.weight_path
    w_c = s.weight_content
    tau = float(s.tau_seconds)

    dist_matrix: NDArray[np.float64] = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n):
            a = sorted_docs[i]
            b = sorted_docs[j]
            t_dist = _time_distance(a, b, tau)
            p_dist = _path_distance(a, b)

            has_content = s.use_embeddings and a.embedding is not None and b.embedding is not None
            if has_content:
                assert a.embedding is not None  # noqa: S101 — mypy assist
                assert b.embedding is not None  # noqa: S101 — mypy assist
                c_dist = _cosine_distance(a.embedding, b.embedding)
                w_c_eff = w_c
            else:
                c_dist = 0.0
                w_c_eff = 0.0

            denominator = w_t + w_p + w_c_eff
            d_val = (
                (w_t * t_dist + w_p * p_dist + w_c_eff * c_dist) / denominator
                if denominator != 0.0
                else 0.0
            )
            dist_matrix[i, j] = d_val
            dist_matrix[j, i] = d_val

    gap = float(s.max_cochange_gap_seconds)
    min_size = s.min_cluster_size
    max_size = s.max_cochange_cluster_size
    eps = float(s.cochange_distance_eps)

    # 3. Choose clustering path
    use_fallback_directly = s.cochange_fallback_enabled and n <= s.cochange_fallback_max_n

    if use_fallback_directly:
        components = _connected_components(dist_matrix, eps, min_size)
        changesets, dropped_oversized, dropped_singletons = _changesets_from_components(
            sorted_docs, components, kind_value, gap, min_size, max_size
        )
        return CoChangeResult(
            changesets=changesets,
            dropped_oversized=dropped_oversized,
            dropped_singletons=dropped_singletons,
        )

    # HDBSCAN path — lazy import so the fallback never requires sklearn
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

    # If HDBSCAN returns all-noise and fallback is enabled, use components
    if bool(np.all(labels == -1)) and s.cochange_fallback_enabled:
        components = _connected_components(dist_matrix, eps, min_size)
        changesets, dropped_oversized, dropped_singletons = _changesets_from_components(
            sorted_docs, components, kind_value, gap, min_size, max_size
        )
        return CoChangeResult(
            changesets=changesets,
            dropped_oversized=dropped_oversized,
            dropped_singletons=dropped_singletons,
        )

    sets, dropped_oversized, dropped_singletons = _changesets_from_labels(
        sorted_docs,
        labels,
        probs,
        run_kind=kind_value,
        gap_seconds=gap,
        min_size=min_size,
        max_cluster_size=max_size,
    )
    return CoChangeResult(
        changesets=sets,
        dropped_oversized=dropped_oversized,
        dropped_singletons=dropped_singletons,
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
    from collections import defaultdict

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
