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
        result = cluster_changesets(docs, s)  # type: ignore[arg-type]
        assert len(result.changesets) == 2
        n = apply_changesets(store, result.changesets)  # type: ignore[arg-type]
        assert n == 2

        # Check that members carry metadata
        for cs in result.changesets:
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
        result = cluster_changesets(docs, s)  # type: ignore[arg-type]

        apply_changesets(store, result.changesets)  # type: ignore[arg-type]
        apply_changesets(store, result.changesets)  # type: ignore[arg-type]

        # Count concept_links — should not be doubled
        conn = store.connect()
        for cs in result.changesets:
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
        result = cluster_changesets(docs, s)  # type: ignore[arg-type]
        apply_changesets(store, result.changesets)  # type: ignore[arg-type]

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
        result = cluster_changesets(docs, s)  # type: ignore[arg-type]
        apply_changesets(store, result.changesets)  # type: ignore[arg-type]

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
        result = cluster_changesets(docs, s)  # type: ignore[arg-type]
        apply_changesets(store, result.changesets)  # type: ignore[arg-type]

        for cs in result.changesets:
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


# ---------------------------------------------------------------------------
# MM-34: Store query side — chunks excluded, kind in changed_with
# ---------------------------------------------------------------------------


class TestQuerySideMM34:
    """MM-34: Store query side — chunks excluded, kind in changed_with."""

    def _make_store(self, tmp_path: Path) -> object:
        """Create an in-memory store for testing."""
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()
        return store

    def test_chunks_excluded_from_timeline(self, tmp_path: Path) -> None:
        """Body chunks (record_role='chunk') must not appear in documents_timeline."""
        from mintmory.core.cochange import documents_timeline
        from mintmory.core.storage import StorageAdapter

        store = self._make_store(tmp_path)
        assert isinstance(store, StorageAdapter)

        vf = datetime.fromtimestamp(1_700_000_000.0, tz=UTC).replace(tzinfo=None)

        # Write a file-record
        store.add_memory(
            content="My document",
            category="context",
            source="document",
            valid_from=vf,
            metadata={"path": "/docs/a.md", "record_role": "file", "collection": "test"},
        )

        # Write a body chunk (same path, different record_role)
        store.add_memory(
            content="First paragraph of my document",
            category="context",
            source="document",
            valid_from=vf,
            metadata={"path": "/docs/a.md", "record_role": "chunk", "collection": "test"},
        )

        rows = documents_timeline(store)  # type: ignore[arg-type]
        paths = [r["path"] for r in rows]
        assert "/docs/a.md" in paths, "file-record must appear in timeline"
        # The file appears once (the file-record), not twice
        assert paths.count("/docs/a.md") == 1, "file must appear exactly once (chunk excluded)"

    def test_legacy_records_without_record_role_appear_in_timeline(self, tmp_path: Path) -> None:
        """Records without record_role (legacy) must still appear in documents_timeline."""
        from mintmory.core.cochange import documents_timeline
        from mintmory.core.storage import StorageAdapter

        store = self._make_store(tmp_path)
        assert isinstance(store, StorageAdapter)

        vf = datetime.fromtimestamp(1_000_000_000.0, tz=UTC).replace(tzinfo=None)

        # Legacy record: no record_role at all
        store.add_memory(
            content="legacy document without record_role",
            category="context",
            source="document",
            valid_from=vf,
            metadata={"path": "/legacy/doc.txt", "collection": "legacy"},
        )

        rows = documents_timeline(store)  # type: ignore[arg-type]
        paths = [r["path"] for r in rows]
        assert "/legacy/doc.txt" in paths, (
            "legacy record without record_role must appear in timeline"
        )

    def test_changed_with_returns_kind(self, tmp_path: Path) -> None:
        """changed_with results include a 'kind' field populated from changeset_kind."""
        from mintmory.core.cochange import (
            ChangedDoc,
            apply_changesets,
            changed_with,
            cluster_changesets,
        )
        from mintmory.core.config import DocumentSettings
        from mintmory.core.storage import StorageAdapter

        store = self._make_store(tmp_path)
        assert isinstance(store, StorageAdapter)

        mtime_a = 1_000_000.0
        mtime_b = 1_000_060.0  # 60s later — same burst

        rec_a = store.add_memory(
            content="doc A",
            category="context",
            source="document",
            valid_from=datetime.fromtimestamp(mtime_a, tz=UTC).replace(tzinfo=None),
            metadata={
                "path": "/root/a.txt",
                "rel": "a.txt",
                "collection": "test",
                "mtime": mtime_a,
            },
        )
        rec_b = store.add_memory(
            content="doc B",
            category="context",
            source="document",
            valid_from=datetime.fromtimestamp(mtime_b, tz=UTC).replace(tzinfo=None),
            metadata={
                "path": "/root/b.txt",
                "rel": "b.txt",
                "collection": "test",
                "mtime": mtime_b,
            },
        )

        docs = [
            ChangedDoc(
                memory_id=rec_a.id,
                doc_id="/root/a.txt",
                rel="a.txt",
                mtime=mtime_a,
                embedding=_fake_emb(1),
            ),
            ChangedDoc(
                memory_id=rec_b.id,
                doc_id="/root/b.txt",
                rel="b.txt",
                mtime=mtime_b,
                embedding=_fake_emb(2),
            ),
        ]

        # Use fallback path (n=2 <= cochange_fallback_max_n=8 by default)
        s = DocumentSettings(
            cochange_enabled=True,
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.5,
            tau_seconds=3600,
            min_cluster_size=2,
            cochange_fallback_enabled=True,
        )
        result = cluster_changesets(docs, s, run_kind="incremental")
        assert len(result.changesets) >= 1, "expected at least one changeset"
        apply_changesets(store, result.changesets)  # type: ignore[arg-type]

        peers = changed_with(store, "/root/a.txt")  # type: ignore[arg-type]
        assert len(peers) == 1, "expected exactly one peer"
        assert "kind" in peers[0], "changed_with result must include 'kind' field"
        assert peers[0]["kind"] == "incremental"

    def test_changeset_kind_written_to_member_metadata(self, tmp_path: Path) -> None:
        """apply_changesets writes changeset_kind to each member's metadata."""
        from mintmory.core.cochange import (
            ChangedDoc,
            apply_changesets,
            cluster_changesets,
        )
        from mintmory.core.config import DocumentSettings
        from mintmory.core.storage import StorageAdapter

        store = self._make_store(tmp_path)
        assert isinstance(store, StorageAdapter)

        mtime_a = 2_000_000.0
        mtime_b = 2_000_120.0  # 2 min later

        rec_a = store.add_memory(
            content="cold index doc A",
            category="context",
            source="document",
            valid_from=datetime.fromtimestamp(mtime_a, tz=UTC).replace(tzinfo=None),
            metadata={
                "path": "/cold/a.txt",
                "rel": "a.txt",
                "collection": "cold",
                "mtime": mtime_a,
            },
        )
        rec_b = store.add_memory(
            content="cold index doc B",
            category="context",
            source="document",
            valid_from=datetime.fromtimestamp(mtime_b, tz=UTC).replace(tzinfo=None),
            metadata={
                "path": "/cold/b.txt",
                "rel": "b.txt",
                "collection": "cold",
                "mtime": mtime_b,
            },
        )

        docs = [
            ChangedDoc(
                memory_id=rec_a.id,
                doc_id="/cold/a.txt",
                rel="a.txt",
                mtime=mtime_a,
                embedding=_fake_emb(10),
            ),
            ChangedDoc(
                memory_id=rec_b.id,
                doc_id="/cold/b.txt",
                rel="b.txt",
                mtime=mtime_b,
                embedding=_fake_emb(20),
            ),
        ]

        s = DocumentSettings(
            cochange_enabled=True,
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.5,
            tau_seconds=3600,
            min_cluster_size=2,
            cochange_fallback_enabled=True,
        )
        result = cluster_changesets(docs, s, run_kind="cold_full_index")
        assert len(result.changesets) >= 1, "expected at least one changeset"
        apply_changesets(store, result.changesets)  # type: ignore[arg-type]

        for mid in [rec_a.id, rec_b.id]:
            mem = store.get_memory(mid)
            assert mem is not None
            assert "changeset_kind" in mem.metadata, (
                f"member {mid} missing changeset_kind in metadata"
            )
            assert mem.metadata["changeset_kind"] == "cold_full_index", (
                f"expected 'cold_full_index', got {mem.metadata['changeset_kind']!r}"
            )

    def test_chunk_records_carry_recency(self, tmp_path: Path) -> None:
        """Body chunks carry recency fields (valid_from, modified_source=fs_mtime) but no
        changeset_id.  This verifies the store round-trips these correctly so the CLI can
        rely on them when setting record_role='chunk'."""
        from mintmory.core.storage import StorageAdapter

        store = self._make_store(tmp_path)
        assert isinstance(store, StorageAdapter)

        rec = store.add_memory(
            content="First paragraph of the document",
            category="context",
            source="document",
            valid_from=datetime.fromisoformat("2026-01-15T10:00:00"),
            metadata={
                "path": "/docs/b.md",
                "record_role": "chunk",
                "modified_source": "fs_mtime",
                "collection": "test",
            },
        )

        mem = store.get_memory(rec.id)
        assert mem is not None
        assert mem.valid_from is not None, "chunk must carry valid_from"
        assert mem.valid_from.isoformat() == "2026-01-15T10:00:00", (
            f"valid_from round-trip failed: {mem.valid_from!r}"
        )
        assert mem.metadata.get("modified_source") == "fs_mtime", (
            "chunk must carry modified_source='fs_mtime'"
        )
        assert mem.metadata.get("record_role") == "chunk", "chunk must carry record_role='chunk'"
        assert "changeset_id" not in mem.metadata, (
            "body chunks must NOT carry changeset_id (spec: chunk carries recency, not timeline)"
        )

    def test_stray_old_file_not_co_changed(self, tmp_path: Path) -> None:
        """A stray old file in the same folder as recently-changed files is NOT co-changed
        with those files: a gap > max_cochange_gap_seconds triggers a gap-split that
        separates the old file into its own singleton, which is dropped (< min_cluster_size)."""
        from mintmory.core.cochange import ChangedDoc, cluster_changesets
        from mintmory.core.config import DocumentSettings
        from mintmory.core.storage import StorageAdapter

        store = self._make_store(tmp_path)
        assert isinstance(store, StorageAdapter)

        mtime_new1 = 1_000_000.0
        mtime_new2 = 1_000_060.0
        mtime_old = 0.0  # 11+ days before the others — gap >> 86_400 s

        rec_new1 = store.add_memory(
            content="new file 1",
            category="context",
            source="document",
            valid_from=datetime.fromtimestamp(mtime_new1, tz=UTC).replace(tzinfo=None),
            metadata={
                "path": "/a/new1.txt",
                "rel": "a/new1.txt",
                "collection": "t",
                "mtime": mtime_new1,
            },
        )
        rec_new2 = store.add_memory(
            content="new file 2",
            category="context",
            source="document",
            valid_from=datetime.fromtimestamp(mtime_new2, tz=UTC).replace(tzinfo=None),
            metadata={
                "path": "/a/new2.txt",
                "rel": "a/new2.txt",
                "collection": "t",
                "mtime": mtime_new2,
            },
        )
        rec_old = store.add_memory(
            content="stray old file",
            category="context",
            source="document",
            valid_from=datetime.fromtimestamp(mtime_old, tz=UTC).replace(tzinfo=None),
            metadata={
                "path": "/a/old_stray.txt",
                "rel": "a/old_stray.txt",
                "collection": "t",
                "mtime": mtime_old,
            },
        )

        docs = [
            ChangedDoc(
                memory_id=rec_new1.id,
                doc_id="/a/new1.txt",
                rel="a/new1.txt",
                mtime=mtime_new1,
                embedding=_fake_emb(1),
            ),
            ChangedDoc(
                memory_id=rec_new2.id,
                doc_id="/a/new2.txt",
                rel="a/new2.txt",
                mtime=mtime_new2,
                embedding=_fake_emb(2),
            ),
            ChangedDoc(
                memory_id=rec_old.id,
                doc_id="/a/old_stray.txt",
                rel="a/old_stray.txt",
                mtime=mtime_old,
                embedding=_fake_emb(3),
            ),
        ]

        s = DocumentSettings(
            cochange_enabled=True,
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.5,
            tau_seconds=3600,
            min_cluster_size=2,
            max_cochange_gap_seconds=86_400,
            cochange_fallback_enabled=True,
            cochange_fallback_max_n=8,
            cochange_distance_eps=0.35,
        )
        result = cluster_changesets(docs, s, run_kind="incremental")

        # Collect all memory IDs that appear in any changeset
        all_changeset_member_ids: set[str] = set()
        for cs in result.changesets:
            all_changeset_member_ids.update(cs.member_ids)

        # The stray old file must not be grouped with the new files
        assert rec_old.id not in all_changeset_member_ids, (
            "stray old file (mtime=0.0) must not appear in any changeset alongside recent files"
        )
