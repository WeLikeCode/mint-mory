"""
core/cochange.py — document co-change clustering and store I/O (MM-33).

Pure clustering (no store, no network) + thin store wrappers for applying
change-sets and querying co-changed documents.

The clustering uses HDBSCAN from scikit-learn (optional ``cochange`` extra).
When scikit-learn is not installed, ``cluster_changesets`` raises
``CoChangeUnavailable`` — the CLI catches this and prints an install hint.

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
# Core clustering
# ---------------------------------------------------------------------------


def cluster_changesets(
    docs: list[ChangedDoc],
    s: DocumentSettings,
) -> list[ChangeSet]:
    """Cluster changed documents into change-sets using HDBSCAN.

    Returns an empty list when:
    - fewer than 2 docs, or
    - s.cochange_enabled is False.

    Raises CoChangeUnavailable if scikit-learn is not installed.

    Algorithm:
    1. Sort docs by (mtime, doc_id) for determinism.
    2. Build a precomputed N×N float64 distance matrix.
    3. Fit HDBSCAN(metric='precomputed', min_cluster_size=s.min_cluster_size).
    4. Labels_ -1 = noise (excluded). probabilities_ → edge strength.
    5. Build ChangeSet per label ≥ 0.
    """
    if len(docs) < 2 or not s.cochange_enabled:
        return []

    # Lazy import — raises CoChangeUnavailable when not installed
    try:
        from sklearn.cluster import HDBSCAN
    except ImportError as exc:
        raise CoChangeUnavailable(
            "scikit-learn is not installed; run: pip install 'mintmory[cochange]'"
        ) from exc

    # 1. Sort for determinism
    sorted_docs = sorted(docs, key=lambda d: (d.mtime, d.doc_id))
    n = len(sorted_docs)

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

            # Content term — dropped when either embedding is None or use_embeddings=False
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
            if denominator == 0.0:
                d_val = 0.0
            else:
                d_val = (w_t * t_dist + w_p * p_dist + w_c_eff * c_dist) / denominator

            dist_matrix[i, j] = d_val
            dist_matrix[j, i] = d_val

    # 3. Fit HDBSCAN
    hdb = HDBSCAN(metric="precomputed", min_cluster_size=s.min_cluster_size)
    hdb.fit(dist_matrix)
    labels: NDArray[np.int32] = np.asarray(hdb.labels_, dtype=np.int32)
    probs: NDArray[np.float64] = np.asarray(hdb.probabilities_, dtype=np.float64)

    # 4-5. Group by label (noise = -1 excluded) and build ChangeSets.
    return _changesets_from_labels(sorted_docs, labels, probs)


def _changesets_from_labels(
    sorted_docs: list[ChangedDoc],
    labels: NDArray[np.int32],
    probs: NDArray[np.float64],
) -> list[ChangeSet]:
    """Build ChangeSets from cluster labels. Label -1 (HDBSCAN noise) is excluded.

    Pure and deterministic — extracted from ``cluster_changesets`` so the noise
    exclusion + change-set assembly can be tested without HDBSCAN (whose behaviour
    on tiny inputs is unstable). ``sorted_docs`` MUST be in the same order the
    labels/probs index (i.e. the matrix row order).
    """
    from collections import defaultdict

    clusters: dict[int, list[int]] = defaultdict(list)
    for idx, label in enumerate(labels):
        if int(label) >= 0:  # -1 == noise → not co-change
            clusters[int(label)].append(idx)

    changesets: list[ChangeSet] = []
    for _label, indices in sorted(clusters.items()):
        cluster_docs = [sorted_docs[i] for i in indices]
        doc_ids_sorted = sorted(d.doc_id for d in cluster_docs)
        max_mtime = max(d.mtime for d in cluster_docs)

        # Deterministic id
        payload = "|".join(doc_ids_sorted) + f"@{max_mtime:.0f}"
        changeset_id = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]  # noqa: S324

        # observed_at = naive-UTC ISO from max_mtime
        observed_at = datetime.fromtimestamp(max_mtime, tz=UTC).replace(tzinfo=None).isoformat()

        # member_ids sorted
        member_ids = sorted(d.memory_id for d in cluster_docs)

        # pairwise edges: (src_id, dst_id, strength)
        edges: list[tuple[str, str, float]] = []
        for ci in range(len(indices)):
            for cj in range(ci + 1, len(indices)):
                gi = indices[ci]
                gj = indices[cj]
                strength = float(max(0.0, min(1.0, min(probs[gi], probs[gj]))))
                edges.append((sorted_docs[gi].memory_id, sorted_docs[gj].memory_id, strength))

        # order: memory ids sorted by mtime (then doc_id for tie-break)
        order_docs = sorted(cluster_docs, key=lambda d: (d.mtime, d.doc_id))
        order = [d.memory_id for d in order_docs]

        changesets.append(
            ChangeSet(
                changeset_id=changeset_id,
                member_ids=member_ids,
                observed_at=observed_at,
                edges=edges,
                order=order,
            )
        )

    return changesets


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
    changeset_method into the memory's metadata via update_memory.

    For each cluster: delete existing concept_links with entity=f"changeset:{id}"
    (idempotency), then insert pairwise relates_to edges and consecutive before
    edges along order.

    Returns the count of change-sets applied.

    Idempotency / edge identity: each cluster's edges are deleted by their
    ``entity="changeset:<id>"`` tag before re-insertion, so re-applying the SAME
    change-set never duplicates edges. This is safe because ``index-tree`` writes a
    FRESH memory id for every changed file each run (old ids are archived), so a
    given (source,target) member pair never recurs under a different changeset id —
    avoiding the ``concept_links`` UNIQUE(source,target,link_type) INSERT-OR-IGNORE
    from silently dropping a new edge while a stale-tagged one survives.

    Not atomic across a whole change-set (the DELETE commits, then each member
    update / link insert commits in its own transaction); a crash mid-apply leaves
    a change-set partially written, but a re-run is idempotent and self-heals.
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

    Finds the document memory for ``path`` (metadata.path == path,
    source='document'), collects its changeset_id(s) from metadata, and
    returns peer docs sharing a changeset_id (excluding self) with fields:
    {path, strength, observed_at}.

    Strength is taken from the relates_to concept_link between the two if one
    exists; otherwise 0.0.
    """
    conn = store.connect()

    # Find the memory for this path. ORDER BY rowid DESC makes "most recent wins"
    # deterministic (SQLite gives no row order without ORDER BY); in practice only
    # one active row exists per path, but don't rely on insertion order.
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

    # Find all document memories with the same changeset_id
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

        # Look up strength from the relates_to link between the two
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

    When no window is specified (since/from_iso/to_iso all None), all documents
    are returned (no time restriction) — unlike the history timeline which defaults
    to the last 90 days.
    """
    now = datetime.now(UTC).replace(tzinfo=None)

    if since is not None or from_iso is not None or to_iso is not None:
        from mintmory.core.history.query import resolve_window

        start, end = resolve_window(since=since, from_iso=from_iso, to_iso=to_iso, now=now)
    else:
        # No window: return all documents (no time restriction)
        start = datetime(1970, 1, 1)
        end = datetime(9999, 12, 31, 23, 59, 59)

    conn = store.connect()
    where = [
        "source = 'document'",
        "is_archived = 0",
        "valid_from IS NOT NULL",
        "valid_from >= ?",
        "valid_from <= ?",
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
        # Title: rel or first 80 chars of content
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
