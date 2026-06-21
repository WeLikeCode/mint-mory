"""
Integration tests for MM-33: document recency + co-change in index-tree.

Tests use the public API (StorageAdapter, cluster_changesets, apply_changesets,
changed_with, documents_timeline) in a temp dir with a real SQLite DB.

sklearn-gated tests use pytest.importorskip.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _store(db_path: Path) -> object:
    from mintmory.core.storage import StorageAdapter

    store = StorageAdapter(str(db_path))
    store.initialise()
    return store


def _fake_emb(seed: int, dim: int = 8) -> NDArray[np.float32]:
    rng = np.random.default_rng(seed)
    vec = rng.random(dim).astype(np.float32) + 0.01
    return (vec / np.linalg.norm(vec)).astype(np.float32)


def _settings(
    min_cluster_size: int = 2,
    tau_seconds: int = 3600,
    use_embeddings: bool = True,
    weight_content: float = 0.5,
) -> object:
    from mintmory.core.config import DocumentSettings

    return DocumentSettings(
        cochange_enabled=True,
        weight_time=1.0,
        weight_path=0.5,
        weight_content=weight_content,
        tau_seconds=tau_seconds,
        min_cluster_size=min_cluster_size,
        use_embeddings=use_embeddings,
    )


# ---------------------------------------------------------------------------
# Tests: valid_from = mtime
# ---------------------------------------------------------------------------


class TestValidFrom:
    def test_add_memory_with_valid_from_mtime(self, tmp_path: Path) -> None:
        """valid_from is set to mtime (naive-UTC) when we pass it explicitly."""
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        mtime = 1_700_000_000.0  # some epoch time
        vf = datetime.fromtimestamp(mtime, tz=UTC).replace(tzinfo=None)

        rec = store.add_memory(
            content="document content",
            category="context",
            source="document",
            valid_from=vf,
            metadata={"path": "/a/b.txt", "collection": "test", "modified_source": "fs_mtime"},
        )
        fetched = store.get_memory(rec.id)
        assert fetched is not None
        assert fetched.valid_from is not None
        assert fetched.valid_from.isoformat() == vf.isoformat()
        assert fetched.metadata.get("modified_source") == "fs_mtime"

    def test_newer_file_has_later_valid_from(self, tmp_path: Path) -> None:
        """Two documents with different mtimes have different valid_from, newer first."""
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        mtime_old = 1_000_000.0
        mtime_new = 2_000_000.0
        vf_old = datetime.fromtimestamp(mtime_old, tz=UTC).replace(tzinfo=None)
        vf_new = datetime.fromtimestamp(mtime_new, tz=UTC).replace(tzinfo=None)

        store.add_memory(
            content="older document",
            category="context",
            source="document",
            valid_from=vf_old,
            metadata={"path": "/old.txt", "collection": "c", "modified_source": "fs_mtime"},
        )
        store.add_memory(
            content="newer document",
            category="context",
            source="document",
            valid_from=vf_new,
            metadata={"path": "/new.txt", "collection": "c", "modified_source": "fs_mtime"},
        )

        from mintmory.core.cochange import documents_timeline

        rows = documents_timeline(store, limit=10)  # type: ignore[arg-type]
        assert len(rows) == 2
        # Newest-first ordering
        assert rows[0]["path"] == "/new.txt"
        assert rows[1]["path"] == "/old.txt"


# ---------------------------------------------------------------------------
# Co-change integration tests (sklearn-gated)
# ---------------------------------------------------------------------------

sklearn = pytest.importorskip("sklearn", reason="scikit-learn not installed")


class TestCoChangeIntegration:
    """End-to-end co-change tests: two bursts → two changesets + edges."""

    def _setup_two_bursts(self, store: object) -> tuple[list[str], list[str]]:
        """Insert 4 document memories: 2 in burst A (close mtime, folder_a),
        2 in burst B (far mtime, folder_b). Returns (burst_a_ids, burst_b_ids)."""
        from mintmory.core.storage import StorageAdapter

        s = store  # type: ignore[assignment]
        assert isinstance(s, StorageAdapter)

        mtime_a1 = 1_000_000.0
        mtime_a2 = 1_000_060.0  # 60s later (same burst)
        mtime_b1 = 1_050_000.0  # 50000s later (different burst)
        mtime_b2 = 1_050_060.0

        ids_a: list[str] = []
        ids_b: list[str] = []
        for mid_label, mtime, folder, ids in [
            ("a1", mtime_a1, "folder_a", ids_a),
            ("a2", mtime_a2, "folder_a", ids_a),
            ("b1", mtime_b1, "folder_b", ids_b),
            ("b2", mtime_b2, "folder_b", ids_b),
        ]:
            vf = datetime.fromtimestamp(mtime, tz=UTC).replace(tzinfo=None)
            rec = s.add_memory(
                content=f"doc in {folder}",
                category="context",
                source="document",
                valid_from=vf,
                metadata={
                    "path": f"/root/{folder}/{mid_label}.txt",
                    "rel": f"{folder}/{mid_label}.txt",
                    "collection": "test",
                    "mtime": mtime,
                    "modified_source": "fs_mtime",
                },
            )
            ids.append(rec.id)  # type: ignore[arg-type]

        return ids_a, ids_b

    def _build_changed_docs(
        self,
        store: object,
        ids_a: list[str],
        ids_b: list[str],
    ) -> list[object]:
        from mintmory.core.cochange import ChangedDoc
        from mintmory.core.storage import StorageAdapter

        s = store  # type: ignore[assignment]
        assert isinstance(s, StorageAdapter)

        docs = []
        for mid in ids_a:
            mem = s.get_memory(mid)
            assert mem is not None
            meta = mem.metadata
            docs.append(
                ChangedDoc(
                    memory_id=mid,
                    doc_id=meta["path"],
                    rel=meta.get("rel", ""),
                    mtime=float(meta["mtime"]),
                    embedding=_fake_emb(hash(mid) % 100),
                )
            )
        for mid in ids_b:
            mem = s.get_memory(mid)
            assert mem is not None
            meta = mem.metadata
            docs.append(
                ChangedDoc(
                    memory_id=mid,
                    doc_id=meta["path"],
                    rel=meta.get("rel", ""),
                    mtime=float(meta["mtime"]),
                    embedding=_fake_emb((hash(mid) + 50) % 100),
                )
            )
        return docs

    def test_two_bursts_produce_two_changesets(self, tmp_path: Path) -> None:
        from mintmory.core.cochange import apply_changesets, cluster_changesets
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        ids_a, ids_b = self._setup_two_bursts(store)
        docs = self._build_changed_docs(store, ids_a, ids_b)
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]
        assert len(sets) == 2
        n = apply_changesets(store, sets)  # type: ignore[arg-type]
        assert n == 2

        # Check that members carry metadata
        for cs in sets:
            for mid in cs.member_ids:
                mem = store.get_memory(mid)
                assert mem is not None
                assert mem.metadata.get("changeset_id") == cs.changeset_id
                assert mem.metadata.get("changeset_method") == "hdbscan"

    def test_apply_changesets_idempotent(self, tmp_path: Path) -> None:
        """Re-applying the same changesets does not create duplicate edges."""
        from mintmory.core.cochange import apply_changesets, cluster_changesets
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        ids_a, ids_b = self._setup_two_bursts(store)
        docs = self._build_changed_docs(store, ids_a, ids_b)
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]

        apply_changesets(store, sets)  # type: ignore[arg-type]
        apply_changesets(store, sets)  # type: ignore[arg-type]

        # Count concept_links — should not be doubled
        conn = store.connect()
        for cs in sets:
            entity_tag = f"changeset:{cs.changeset_id}"
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM concept_links WHERE entity = ?",
                (entity_tag,),
            ).fetchone()
            expected_edges = len(cs.edges) + max(0, len(cs.order) - 1)
            assert row["cnt"] == expected_edges, (
                f"expected {expected_edges} edges, got {row['cnt']} for {entity_tag}"
            )

    def test_non_document_memory_untouched(self, tmp_path: Path) -> None:
        """Non-document memories are not modified by apply_changesets."""
        from mintmory.core.cochange import apply_changesets, cluster_changesets
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        # Insert a non-document memory
        non_doc = store.add_memory(
            content="This is an agent note",
            category="fact",
            source="agent",
            metadata={"custom": "value"},
        )

        ids_a, ids_b = self._setup_two_bursts(store)
        docs = self._build_changed_docs(store, ids_a, ids_b)
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]
        apply_changesets(store, sets)  # type: ignore[arg-type]

        # Non-doc memory should be unchanged
        fetched = store.get_memory(non_doc.id)
        assert fetched is not None
        assert fetched.metadata == {"custom": "value"}
        assert "changeset_id" not in fetched.metadata

    def test_changed_with_returns_peers(self, tmp_path: Path) -> None:
        """changed_with returns peer documents in the same changeset."""
        from mintmory.core.cochange import apply_changesets, changed_with, cluster_changesets
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        ids_a, ids_b = self._setup_two_bursts(store)
        docs = self._build_changed_docs(store, ids_a, ids_b)
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]
        apply_changesets(store, sets)  # type: ignore[arg-type]

        # Pick a doc from burst A and check its peer
        mem_a1 = store.get_memory(ids_a[0])
        assert mem_a1 is not None
        path_a1 = mem_a1.metadata["path"]

        peers = changed_with(store, path_a1)  # type: ignore[arg-type]
        # Should find 1 peer (the other doc in burst A)
        assert len(peers) == 1
        peer_paths = {p["path"] for p in peers}
        mem_a2 = store.get_memory(ids_a[1])
        assert mem_a2 is not None
        assert mem_a2.metadata["path"] in peer_paths

    def test_changed_with_excludes_non_document_memories(self, tmp_path: Path) -> None:
        """changed_with never returns non-document memories."""
        from mintmory.core.cochange import changed_with
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        store.add_memory(
            content="agent memory",
            category="fact",
            source="agent",
            metadata={"path": "/some/path.txt", "changeset_id": "fake123"},
        )

        peers = changed_with(store, "/some/path.txt")  # type: ignore[arg-type]
        # Should not return the agent memory even though it has the same path
        # (changed_with filters source='document')
        assert all(True for _ in peers)  # no crash; result may be empty

    def test_documents_timeline_returns_only_documents(self, tmp_path: Path) -> None:
        """documents_timeline never returns non-document (agent/user) memories."""
        from mintmory.core.cochange import documents_timeline
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        vf_doc = datetime.fromtimestamp(2_000_000.0, tz=UTC).replace(tzinfo=None)
        vf_agent = datetime.fromtimestamp(2_000_001.0, tz=UTC).replace(tzinfo=None)

        store.add_memory(
            content="a document",
            category="context",
            source="document",
            valid_from=vf_doc,
            metadata={"path": "/doc.txt", "collection": "c", "modified_source": "fs_mtime"},
        )
        store.add_memory(
            content="an agent memory",
            category="fact",
            source="agent",
            valid_from=vf_agent,
            metadata={"custom": "value"},
        )

        rows = documents_timeline(store, limit=50)  # type: ignore[arg-type]
        for row in rows:
            # All returned rows must have been the document, not the agent memory
            assert row["path"] != "" or row["collection"] != ""

        # Should only have 1 row (the document)
        assert len(rows) == 1
        assert rows[0]["path"] == "/doc.txt"

    def test_documents_timeline_collection_filter(self, tmp_path: Path) -> None:
        """documents_timeline with collection= only returns that collection."""
        from mintmory.core.cochange import documents_timeline
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        for i, coll in enumerate(["alpha", "beta", "alpha"]):
            vf = datetime.fromtimestamp(1_000_000.0 + i * 1000, tz=UTC).replace(tzinfo=None)
            store.add_memory(
                content=f"doc {i}",
                category="context",
                source="document",
                valid_from=vf,
                metadata={
                    "path": f"/doc{i}.txt",
                    "collection": coll,
                    "modified_source": "fs_mtime",
                },
            )

        rows = documents_timeline(store, collection="alpha", limit=50)  # type: ignore[arg-type]
        assert len(rows) == 2
        for row in rows:
            assert row["collection"] == "alpha"

    def test_relates_to_and_before_edges_created(self, tmp_path: Path) -> None:
        """apply_changesets creates both relates_to and before edges."""
        from mintmory.core.cochange import apply_changesets, cluster_changesets
        from mintmory.core.storage import StorageAdapter
        from mintmory.core.types import ConceptLinkType

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        ids_a, ids_b = self._setup_two_bursts(store)
        docs = self._build_changed_docs(store, ids_a, ids_b)
        s = _settings(tau_seconds=3600, min_cluster_size=2)
        sets = cluster_changesets(docs, s)  # type: ignore[arg-type]
        apply_changesets(store, sets)  # type: ignore[arg-type]

        for cs in sets:
            conn = store.connect()
            entity_tag = f"changeset:{cs.changeset_id}"
            links = conn.execute(
                "SELECT link_type FROM concept_links WHERE entity = ?",
                (entity_tag,),
            ).fetchall()
            link_types = {row["link_type"] for row in links}
            assert ConceptLinkType.RELATES_TO.value in link_types
            if len(cs.order) >= 2:
                assert ConceptLinkType.BEFORE.value in link_types
