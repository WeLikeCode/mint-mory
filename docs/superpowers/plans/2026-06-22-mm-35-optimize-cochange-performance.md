# MM-35: Optimize Document Co-Change Performance

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add folder+time-bucket blocking and vectorized distance matrix to co-change clustering so it scales to large corpora (O(N·k) vs O(N²)).

**Architecture:** Three changes to cochange.py: `_build_blocks` partitions docs by (folder, time-bucket), `_block_distance_matrix` computes per-block vectorized distances, and `cluster_changesets` runs the existing MM-34 fallback-or-HDBSCAN decision per block. CoChangeResult gains a `truncated` field. Config gets three new knobs.

**Tech Stack:** Python 3.12, numpy (vectorized), scikit-learn HDBSCAN (optional), pydantic-settings

---

## File Map

- **Modify:** `packages/core/src/mintmory/core/config.py` — add 3 new `DocumentSettings` knobs
- **Modify:** `packages/core/src/mintmory/core/cochange.py` — add `_build_blocks`, `_block_distance_matrix`, `_cluster_one_block`, refactor `cluster_changesets`, add `truncated` to `CoChangeResult`
- **Modify:** `packages/cli/src/mintmory/cli/main.py` — surface `result.truncated` in the co-change summary rows
- **Modify:** `packages/core/tests/test_cochange.py` — MM-35 tests (parity, blocking, truncation, determinism, config)
- **Modify:** `packages/core/tests/test_config.py` — MM-35 config knob tests

---

### Task 1: Add new config knobs to DocumentSettings

**Files:**
- Modify: `packages/core/src/mintmory/core/config.py` (after `cochange_distance_eps` at line 319)
- Test: `packages/core/tests/test_config.py`

- [ ] **Step 1: Write the failing config tests**

Add a new class `TestDocumentSettingsMM35` at the end of `packages/core/tests/test_config.py`:

```python
class TestDocumentSettingsMM35:
    """MM-35: new DocumentSettings knobs for blocking."""

    def test_new_knob_defaults(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings()
        assert s.cochange_block_by_folder is True
        assert s.cochange_time_bucket_seconds == 86_400
        assert s.max_cochange_partition_size == 2000

    def test_cochange_block_by_folder_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mintmory.core.config import DocumentSettings

        monkeypatch.setenv("MINTMORY_DOC_COCHANGE_BLOCK_BY_FOLDER", "false")
        s = DocumentSettings()
        assert s.cochange_block_by_folder is False

    def test_cochange_time_bucket_seconds_lower_bound(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(cochange_time_bucket_seconds=1)
        assert s.cochange_time_bucket_seconds == 1

    def test_cochange_time_bucket_seconds_below_lower_bound_raises(self) -> None:
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(cochange_time_bucket_seconds=0)

    def test_max_cochange_partition_size_lower_bound(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(max_cochange_partition_size=2)
        assert s.max_cochange_partition_size == 2

    def test_max_cochange_partition_size_below_lower_bound_raises(self) -> None:
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(max_cochange_partition_size=1)

    def test_max_cochange_partition_size_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mintmory.core.config import DocumentSettings

        monkeypatch.setenv("MINTMORY_DOC_MAX_COCHANGE_PARTITION_SIZE", "500")
        s = DocumentSettings()
        assert s.max_cochange_partition_size == 500
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/core/tests/test_config.py::TestDocumentSettingsMM35 -q 2>&1 | tail -10
```
Expected: FAIL — `TestDocumentSettingsMM35` references fields that don't exist yet.

- [ ] **Step 3: Add 3 new knobs to DocumentSettings in config.py**

In `packages/core/src/mintmory/core/config.py`, after line 319 (`cochange_distance_eps`), add:

```python
    # MM-35 — blocking + partition-size ceiling
    cochange_block_by_folder: bool = True
    cochange_time_bucket_seconds: int = Field(default=86_400, ge=1)
    max_cochange_partition_size: int = Field(default=2000, ge=2)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run --no-sync pytest packages/core/tests/test_config.py::TestDocumentSettingsMM35 -q 2>&1 | tail -10
```
Expected: 7 passed.

- [ ] **Step 5: Run all config tests**

```bash
uv run --no-sync pytest packages/core/tests/test_config.py -q 2>&1 | tail -10
```
Expected: All pass.

---

### Task 2: Add `truncated` field to CoChangeResult

**Files:**
- Modify: `packages/core/src/mintmory/core/cochange.py`
- Modify: `packages/core/tests/test_cochange.py` (fix positional constructors if any)

- [ ] **Step 1: Add `truncated: int = 0` to CoChangeResult dataclass**

In `packages/core/src/mintmory/core/cochange.py`, the current `CoChangeResult`:
```python
@dataclass
class CoChangeResult:
    """Return value of cluster_changesets (MM-34 B)."""

    changesets: list[ChangeSet]
    dropped_oversized: int  # change-sets dropped because len > max_cochange_cluster_size
    dropped_singletons: int  # gap-split fragments dropped because len < min_cluster_size
```

Change to:
```python
@dataclass
class CoChangeResult:
    """Return value of cluster_changesets (MM-34 B)."""

    changesets: list[ChangeSet]
    dropped_oversized: int  # change-sets dropped because len > max_cochange_cluster_size
    dropped_singletons: int  # gap-split fragments dropped because len < min_cluster_size
    truncated: int = 0  # MM-35: docs dropped from oversized blocks before clustering
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
uv run --no-sync pytest packages/core/tests/test_cochange.py -q 2>&1 | tail -10
```
Expected: All 46 pass (new `truncated` field has default 0, no existing test passes it positionally).

---

### Task 3: Implement `_build_blocks`

**Files:**
- Modify: `packages/core/src/mintmory/core/cochange.py` — add helper before `cluster_changesets`
- Test: `packages/core/tests/test_cochange.py`

- [ ] **Step 1: Write failing tests for `_build_blocks`**

Add class `TestBuildBlocks` to `packages/core/tests/test_cochange.py`:

```python
class TestBuildBlocks:
    """MM-35: _build_blocks partitions by (folder, time-bucket)."""

    def test_two_folders_two_blocks(self) -> None:
        from mintmory.core.cochange import _build_blocks

        # Same time-bucket, two folders
        docs = [
            _make_doc("ma1", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("ma2", "/root/a/f2.txt", "a/f2.txt", 60.0),
            _make_doc("mb1", "/root/b/f3.txt", "b/f3.txt", 120.0),
            _make_doc("mb2", "/root/b/f4.txt", "b/f4.txt", 180.0),
        ]
        # bucket large enough to keep all in same time-bucket
        blocks, truncated = _build_blocks(docs, bucket_seconds=86_400, max_block=2000)  # type: ignore[arg-type]
        assert len(blocks) == 2
        assert truncated == 0
        # Each block is from one folder
        folders = {frozenset(d.rel.split("/")[0] for d in block) for block in blocks}  # type: ignore[attr-defined]
        assert frozenset({"a"}) in folders
        assert frozenset({"b"}) in folders

    def test_cross_folder_never_share_block(self) -> None:
        from mintmory.core.cochange import _build_blocks

        docs = [
            _make_doc("a1", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("b1", "/root/b/f2.txt", "b/f2.txt", 10.0),
        ]
        blocks, truncated = _build_blocks(docs, bucket_seconds=86_400, max_block=2000)  # type: ignore[arg-type]
        assert len(blocks) == 2
        assert truncated == 0
        for block in blocks:
            folders = {d.rel.split("/")[0] for d in block}  # type: ignore[attr-defined]
            assert len(folders) == 1

    def test_root_files_share_empty_key(self) -> None:
        from mintmory.core.cochange import _build_blocks

        docs = [
            _make_doc("r1", "/f1.txt", "f1.txt", 0.0),
            _make_doc("r2", "/f2.txt", "f2.txt", 60.0),
        ]
        blocks, truncated = _build_blocks(docs, bucket_seconds=86_400, max_block=2000)  # type: ignore[arg-type]
        # Both root files share "" folder key → one block
        assert len(blocks) == 1
        assert len(blocks[0]) == 2
        assert truncated == 0

    def test_different_time_buckets_two_blocks(self) -> None:
        from mintmory.core.cochange import _build_blocks

        # Same folder, but 2 days apart with 1-day buckets
        docs = [
            _make_doc("e1", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("e2", "/root/a/f2.txt", "a/f2.txt", 60.0),
            _make_doc("e3", "/root/a/f3.txt", "a/f3.txt", 2 * 86_400.0),
            _make_doc("e4", "/root/a/f4.txt", "a/f4.txt", 2 * 86_400.0 + 60),
        ]
        blocks, truncated = _build_blocks(docs, bucket_seconds=86_400, max_block=2000)  # type: ignore[arg-type]
        assert len(blocks) == 2
        assert truncated == 0

    def test_truncation_keeps_first_by_mtime_docid(self) -> None:
        from mintmory.core.cochange import _build_blocks

        # 5 docs in same (folder, bucket); max_block=3 → 2 truncated
        docs = [
            _make_doc(f"m{i}", f"/root/a/f{i}.txt", f"a/f{i}.txt", float(i * 10))
            for i in range(5)
        ]
        import random
        shuffled = docs.copy()
        random.shuffle(shuffled)
        blocks, truncated = _build_blocks(shuffled, bucket_seconds=86_400, max_block=3)  # type: ignore[arg-type]
        assert len(blocks) == 1
        assert len(blocks[0]) == 3
        assert truncated == 2
        # The kept docs should be the first 3 by (mtime, doc_id)
        kept_ids = [d.doc_id for d in blocks[0]]  # type: ignore[attr-defined]
        expected = [f"/root/a/f{i}.txt" for i in range(3)]
        assert kept_ids == expected

    def test_block_order_deterministic(self) -> None:
        from mintmory.core.cochange import _build_blocks
        import random

        docs = [
            _make_doc("a1", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("a2", "/root/a/f2.txt", "a/f2.txt", 60.0),
            _make_doc("b1", "/root/b/f3.txt", "b/f3.txt", 120.0),
            _make_doc("b2", "/root/b/f4.txt", "b/f4.txt", 180.0),
            _make_doc("c1", "/root/c/f5.txt", "c/f5.txt", 240.0),
        ]
        blocks_a, _ = _build_blocks(docs, bucket_seconds=86_400, max_block=2000)  # type: ignore[arg-type]
        shuffled = docs.copy()
        random.shuffle(shuffled)
        blocks_b, _ = _build_blocks(shuffled, bucket_seconds=86_400, max_block=2000)  # type: ignore[arg-type]
        keys_a = [[d.doc_id for d in b] for b in blocks_a]  # type: ignore[attr-defined]
        keys_b = [[d.doc_id for d in b] for b in blocks_b]  # type: ignore[attr-defined]
        assert keys_a == keys_b
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run --no-sync pytest packages/core/tests/test_cochange.py::TestBuildBlocks -q 2>&1 | tail -5
```
Expected: ImportError or AttributeError — `_build_blocks` doesn't exist yet.

- [ ] **Step 3: Implement `_build_blocks` in cochange.py**

Add this function before `cluster_changesets` in `packages/core/src/mintmory/core/cochange.py`:

```python
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
    1. Sort docs by (mtime, doc_id) — global determinism rule.
    2. Key each doc: folder = rel.rsplit("/", 1)[0] if "/" in rel else "".
       bucket = floor(mtime / bucket_seconds).
    3. Group by (folder, bucket); iterate keys in sorted order.
    4. Truncate blocks longer than max_block (keep first max_block docs, already
       in (mtime, doc_id) order); count truncated docs.

    Returns:
        (blocks, total_truncated_count)
    """
    import math
    from collections import defaultdict

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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run --no-sync pytest packages/core/tests/test_cochange.py::TestBuildBlocks -q 2>&1 | tail -10
```
Expected: All tests pass.

---

### Task 4: Implement `_block_distance_matrix`

**Files:**
- Modify: `packages/core/src/mintmory/core/cochange.py`
- Test: `packages/core/tests/test_cochange.py`

- [ ] **Step 1: Write failing parity tests for `_block_distance_matrix`**

Add class `TestBlockDistanceMatrix` to `packages/core/tests/test_cochange.py`:

```python
class TestBlockDistanceMatrix:
    """MM-35: _block_distance_matrix parity with scalar oracle within 1e-9."""

    def _scalar_dist(
        self,
        a: object,
        b: object,
        s: object,
    ) -> float:
        """Replicate the MM-34 scalar pair computation."""
        from mintmory.core.cochange import _cosine_distance, _path_distance, _time_distance
        from mintmory.core.config import DocumentSettings

        assert isinstance(s, DocumentSettings)
        tau = float(s.tau_seconds)
        w_t = s.weight_time
        w_p = s.weight_path
        w_c = s.weight_content
        t_dist = _time_distance(a, b, tau)  # type: ignore[arg-type]
        p_dist = _path_distance(a, b)  # type: ignore[arg-type]
        has_content = (
            s.use_embeddings
            and a.embedding is not None  # type: ignore[attr-defined]
            and b.embedding is not None  # type: ignore[attr-defined]
        )
        if has_content:
            c_dist = _cosine_distance(
                a.embedding,  # type: ignore[attr-defined]
                b.embedding,  # type: ignore[attr-defined]
            )
            w_c_eff = w_c
        else:
            c_dist = 0.0
            w_c_eff = 0.0
        denom = w_t + w_p + w_c_eff
        return float(
            (w_t * t_dist + w_p * p_dist + w_c_eff * c_dist) / denom
            if denom != 0.0
            else 0.0
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
            weight_time=1.0, weight_path=0.5, weight_content=0.5,
            tau_seconds=3600, use_embeddings=True,
        )
        D = _block_distance_matrix(docs, s)  # type: ignore[arg-type]
        n = len(docs)
        for i in range(n):
            for j in range(n):
                expected = 0.0 if i == j else self._scalar_dist(docs[i], docs[j], s)
                assert abs(float(D[i, j]) - expected) < 1e-9, (
                    f"D[{i},{j}]={D[i,j]:.10f} vs scalar={expected:.10f}"
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
            weight_time=1.0, weight_path=0.5, weight_content=0.5,
            tau_seconds=3600, use_embeddings=False,
        )
        D = _block_distance_matrix(docs, s)  # type: ignore[arg-type]
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
            weight_time=1.0, weight_path=0.5, weight_content=0.5,
            tau_seconds=3600, use_embeddings=True,
        )
        D = _block_distance_matrix(docs, s)  # type: ignore[arg-type]
        n = len(docs)
        for i in range(n):
            for j in range(n):
                expected = 0.0 if i == j else self._scalar_dist(docs[i], docs[j], s)
                assert abs(float(D[i, j]) - expected) < 1e-9, (
                    f"D[{i},{j}]={D[i,j]:.10f} vs scalar={expected:.10f}"
                )

    def test_parity_zero_norm_embedding(self) -> None:
        """Zero-norm embedding → cosine returns 0.5 (neutral); content kept."""
        from mintmory.core.cochange import _block_distance_matrix
        from mintmory.core.config import DocumentSettings

        zero_emb = np.zeros(8, dtype=np.float32)
        docs = [
            _make_doc("m1", "/root/a/f1.txt", "a/f1.txt", 0.0, zero_emb),
            _make_doc("m2", "/root/a/f2.txt", "a/f2.txt", 60.0, _fake_emb(5)),
        ]
        s = DocumentSettings(
            weight_time=1.0, weight_path=0.5, weight_content=0.5,
            tau_seconds=3600, use_embeddings=True,
        )
        D = _block_distance_matrix(docs, s)  # type: ignore[arg-type]
        expected = self._scalar_dist(docs[0], docs[1], s)
        assert abs(float(D[0, 1]) - expected) < 1e-9

    def test_parity_root_files(self) -> None:
        """Root files (no '/' in rel) have depth=0 → path_distance=0 between them."""
        from mintmory.core.cochange import _block_distance_matrix
        from mintmory.core.config import DocumentSettings

        docs = [
            _make_doc("r1", "/f1.txt", "f1.txt", 0.0, None),
            _make_doc("r2", "/f2.txt", "f2.txt", 60.0, None),
        ]
        s = DocumentSettings(
            weight_time=1.0, weight_path=0.5, weight_content=0.0,
            tau_seconds=3600, use_embeddings=False,
        )
        D = _block_distance_matrix(docs, s)  # type: ignore[arg-type]
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
        D = _block_distance_matrix(docs, s)  # type: ignore[arg-type]
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
        D = _block_distance_matrix(docs, s)  # type: ignore[arg-type]
        np.testing.assert_allclose(D, D.T, atol=1e-12)

    def test_parity_random_inputs(self) -> None:
        """Property-style test: 50 random doc pairs, all within 1e-9."""
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
            weight_time=1.0, weight_path=0.5, weight_content=0.5,
            tau_seconds=3600, use_embeddings=True,
        )
        D = _block_distance_matrix(docs, s)  # type: ignore[arg-type]
        for i in range(len(docs)):
            for j in range(len(docs)):
                expected = 0.0 if i == j else self._scalar_dist(docs[i], docs[j], s)
                assert abs(float(D[i, j]) - expected) < 1e-9, (
                    f"pair ({i},{j}): vectorized={D[i,j]:.12f} scalar={expected:.12f}"
                )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --no-sync pytest packages/core/tests/test_cochange.py::TestBlockDistanceMatrix -q 2>&1 | tail -5
```
Expected: ImportError — `_block_distance_matrix` not yet defined.

- [ ] **Step 3: Implement `_block_distance_matrix` in cochange.py**

Add after `_build_blocks` and before `cluster_changesets`:

```python
def _block_distance_matrix(
    block: list[ChangedDoc],
    s: "DocumentSettings",
) -> NDArray[np.float64]:
    """Vectorized per-block composite distance matrix (MM-35).

    Numerically identical (within 1e-9) to the scalar _time_distance /
    _path_distance / _cosine_distance composition for every pair.

    Rules replicated from MM-34 cluster_changesets inner loop:
    - Time: np.minimum(1.0, |m_i - m_j| / tau)
    - Content: (1 - clip(sim, -1, 1)) / 2 via L2-normalised E @ E.T
      - embedding None → content DROPPED (w_c_eff=0 for that pair)
      - embedding zero-norm → content=0.5 KEPT (same as _cosine_distance)
    - Path: (depth_i + depth_j - 2*common) / max(1, depth_i + depth_j)
    - Combine with per-pair effective weights; diagonal 0.0; symmetric.
    """
    k = len(block)
    w_t = s.weight_time
    w_p = s.weight_path
    w_c = s.weight_content
    tau = float(s.tau_seconds)

    # --- Time term (k x k broadcast) ---
    m = np.array([d.mtime for d in block], dtype=np.float64)
    time_mat: NDArray[np.float64] = np.minimum(
        1.0, np.abs(m[:, None] - m[None, :]) / tau
    )

    # --- Path term ---
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
    # has_embedding[i] = True iff use_embeddings AND block[i].embedding is not None
    has_emb = np.array(
        [s.use_embeddings and d.embedding is not None for d in block],
        dtype=bool,
    )
    # content_mat: (k x k), neutral default 0.0 (overridden per pair below)
    content_mat: NDArray[np.float64] = np.zeros((k, k), dtype=np.float64)
    # w_c_mask[i, j] = True iff pair (i,j) has content (BOTH embeddings present + use_embeddings)
    w_c_mask: NDArray[np.bool_] = has_emb[:, None] & has_emb[None, :]

    if s.use_embeddings and np.any(has_emb):
        dim = 0
        for d in block:
            if d.embedding is not None:
                dim = len(d.embedding)
                break
        # Build E (k x dim) — zero rows for missing embeddings
        E: NDArray[np.float64] = np.zeros((k, dim), dtype=np.float64)
        for i, d in enumerate(block):
            if d.embedding is not None:
                E[i] = d.embedding.astype(np.float64)

        # L2-normalise rows; zero-norm rows stay zero (→ cosine=0.5 handled below)
        norms: NDArray[np.float64] = np.linalg.norm(E, axis=1, keepdims=True)
        # Identify zero-norm rows (will produce 0.5 cosine distance, not dropped)
        zero_norm_mask: NDArray[np.bool_] = (norms[:, 0] == 0.0) & has_emb
        safe_norms = np.where(norms == 0.0, 1.0, norms)
        E_norm: NDArray[np.float64] = E / safe_norms

        sim: NDArray[np.float64] = E_norm @ E_norm.T
        raw_content: NDArray[np.float64] = (1.0 - np.clip(sim, -1.0, 1.0)) / 2.0

        # For zero-norm rows, cosine is 0 @ anything = 0 → raw_content = 0.5
        # which is exactly what _cosine_distance returns when either norm==0.
        # The above formula already yields 0.5 when either row is zero (dot=0 → sim=0 → (1-0)/2=0.5)
        # BUT only when BOTH rows are zero or mixed zero/nonzero — check:
        # If row i is zero and row j is nonzero unit: dot(0, v)=0 → sim=0 → content=0.5 ✓
        # If both zero: dot(0,0)=0 → sim=0 → content=0.5 ✓
        # So raw_content already gives 0.5 for zero-norm pairs. Good.
        _ = zero_norm_mask  # used conceptually above

        # Apply content only where w_c_mask is True (both embeddings present)
        content_mat = np.where(w_c_mask, raw_content, 0.0)

    # --- Combine ---
    # w_c_eff[i,j] = w_c if w_c_mask[i,j] else 0.0
    w_c_eff_mat: NDArray[np.float64] = np.where(w_c_mask, w_c, 0.0)
    denom: NDArray[np.float64] = w_t + w_p + w_c_eff_mat
    numer: NDArray[np.float64] = (
        w_t * time_mat + w_p * path_mat + w_c_eff_mat * content_mat
    )
    # Avoid divide-by-zero (all weights could be 0.0 in degenerate config)
    D: NDArray[np.float64] = np.where(denom != 0.0, numer / denom, 0.0)

    # Force diagonal to 0.0 and ensure symmetry
    np.fill_diagonal(D, 0.0)
    D = (D + D.T) / 2.0
    np.fill_diagonal(D, 0.0)

    return D
```

- [ ] **Step 4: Run parity tests to verify they pass**

```bash
uv run --no-sync pytest packages/core/tests/test_cochange.py::TestBlockDistanceMatrix -q 2>&1 | tail -10
```
Expected: All parity tests pass within 1e-9.

---

### Task 5: Extract `_cluster_one_block` and refactor `cluster_changesets`

**Files:**
- Modify: `packages/core/src/mintmory/core/cochange.py`
- Test: `packages/core/tests/test_cochange.py`

- [ ] **Step 1: Write failing MM-35 integration tests**

Add class `TestMM35ClusterChangesets` to `packages/core/tests/test_cochange.py`:

```python
class TestMM35ClusterChangesets:
    """MM-35: blocking-on/off parity, truncation, determinism across shuffles."""

    def _make_two_folder_burst_docs(self) -> list[object]:
        """4 docs: 2 tight in folder 'a', 2 tight in folder 'b', far apart in time."""
        return [
            _make_doc("ma1", "/root/a/f1.txt", "a/f1.txt", 0.0, _fake_emb(0)),
            _make_doc("ma2", "/root/a/f2.txt", "a/f2.txt", 60.0, _fake_emb(1)),
            _make_doc("mb1", "/root/b/f3.txt", "b/f3.txt", 10_000.0, _fake_emb(10)),
            _make_doc("mb2", "/root/b/f4.txt", "b/f4.txt", 10_060.0, _fake_emb(11)),
        ]

    def _settings_mm35(
        self,
        block_by_folder: bool = True,
        bucket_seconds: int = 86_400,
        max_partition: int = 2000,
        fallback_enabled: bool = True,
        fallback_max_n: int = 8,
        **kw: object,
    ) -> object:
        from mintmory.core.config import DocumentSettings

        return DocumentSettings(
            cochange_enabled=True,
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.5,
            tau_seconds=3600,
            min_cluster_size=2,
            use_embeddings=True,
            max_cochange_gap_seconds=86_400,
            max_cochange_cluster_size=50,
            cochange_fallback_enabled=fallback_enabled,
            cochange_fallback_max_n=fallback_max_n,
            cochange_distance_eps=0.35,
            cochange_label_kind=True,
            cochange_block_by_folder=block_by_folder,
            cochange_time_bucket_seconds=bucket_seconds,
            max_cochange_partition_size=max_partition,
            **kw,  # type: ignore[arg-type]
        )

    def test_blocking_off_parity_with_mm34(self) -> None:
        """blocking-off + sub-cap corpus → same change-sets as MM-34 global path."""
        from mintmory.core.cochange import cluster_changesets

        docs = self._make_two_folder_burst_docs()
        s_blocking = self._settings_mm35(block_by_folder=False, max_partition=2000)
        s_global = self._settings_mm35(block_by_folder=True, max_partition=2000)
        r_blocking = cluster_changesets(docs, s_blocking, run_kind="incremental")  # type: ignore[arg-type]
        r_global = cluster_changesets(docs, s_global, run_kind="incremental")  # type: ignore[arg-type]
        # Both should produce 2 change-sets (well-separated bursts)
        assert len(r_blocking.changesets) == len(r_global.changesets)

    def test_blocking_on_isolates_folders(self) -> None:
        """With blocking-on, each folder forms its own block and its own change-set."""
        from mintmory.core.cochange import cluster_changesets

        docs = self._make_two_folder_burst_docs()
        s = self._settings_mm35(block_by_folder=True, bucket_seconds=86_400)
        result = cluster_changesets(docs, s, run_kind="incremental")  # type: ignore[arg-type]
        # 2 change-sets, one per folder
        assert len(result.changesets) == 2
        for cs in result.changesets:
            # All members must come from the same folder
            folders = set()
            for mid in cs.member_ids:
                if mid.startswith("ma"):
                    folders.add("a")
                elif mid.startswith("mb"):
                    folders.add("b")
            assert len(folders) == 1

    def test_determinism_across_shuffles(self) -> None:
        """Same change-set ids regardless of input order."""
        import random
        from mintmory.core.cochange import cluster_changesets

        docs = self._make_two_folder_burst_docs()
        s = self._settings_mm35()
        r1 = cluster_changesets(docs, s, run_kind="incremental")  # type: ignore[arg-type]
        shuffled = docs.copy()
        random.shuffle(shuffled)  # type: ignore[arg-type]
        r2 = cluster_changesets(shuffled, s, run_kind="incremental")  # type: ignore[arg-type]
        ids1 = sorted(cs.changeset_id for cs in r1.changesets)
        ids2 = sorted(cs.changeset_id for cs in r2.changesets)
        assert ids1 == ids2

    def test_truncation_reported_in_result(self) -> None:
        """A single-folder block > max_partition → truncated > 0."""
        from mintmory.core.cochange import cluster_changesets

        # 5 docs, same folder, same bucket; max_partition=3 → 2 truncated
        docs = [
            _make_doc(f"m{i}", f"/root/a/f{i}.txt", f"a/f{i}.txt", float(i * 10))
            for i in range(5)
        ]
        s = self._settings_mm35(block_by_folder=True, max_partition=3)
        result = cluster_changesets(docs, s, run_kind="incremental")  # type: ignore[arg-type]
        assert result.truncated == 2

    def test_truncation_blocking_off(self) -> None:
        """blocking-off path: single block capped at max_partition → truncated count."""
        from mintmory.core.cochange import cluster_changesets

        docs = [
            _make_doc(f"m{i}", f"/root/a/f{i}.txt", f"a/f{i}.txt", float(i * 10))
            for i in range(5)
        ]
        s = self._settings_mm35(block_by_folder=False, max_partition=3)
        result = cluster_changesets(docs, s, run_kind="incremental")  # type: ignore[arg-type]
        assert result.truncated == 2

    def test_no_truncation_when_within_cap(self) -> None:
        from mintmory.core.cochange import cluster_changesets

        docs = self._make_two_folder_burst_docs()
        s = self._settings_mm35(max_partition=2000)
        result = cluster_changesets(docs, s, run_kind="incremental")  # type: ignore[arg-type]
        assert result.truncated == 0

    def test_small_block_hits_components_fallback(self) -> None:
        """With n<=fallback_max_n per block, components fallback is used (no sklearn needed)."""
        from mintmory.core.cochange import cluster_changesets

        docs = [
            _make_doc("m1", "/root/a/f1.txt", "a/f1.txt", 0.0, None),
            _make_doc("m2", "/root/a/f2.txt", "a/f2.txt", 60.0, None),
            _make_doc("m3", "/root/a/f3.txt", "a/f3.txt", 120.0, None),
        ]
        s = self._settings_mm35(
            fallback_enabled=True, fallback_max_n=8,
            weight_content=0.0, use_embeddings=False,  # type: ignore[arg-type]
        )
        result = cluster_changesets(docs, s, run_kind="incremental")  # type: ignore[arg-type]
        assert len(result.changesets) == 1
        assert len(result.changesets[0].member_ids) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --no-sync pytest packages/core/tests/test_cochange.py::TestMM35ClusterChangesets -q 2>&1 | tail -8
```
Expected: Various failures because `cluster_changesets` doesn't yet support `truncated` or blocking.

- [ ] **Step 3: Implement `_cluster_one_block` helper and refactor `cluster_changesets`**

First add `_cluster_one_block` before `cluster_changesets` in cochange.py:

```python
def _cluster_one_block(
    block: list[ChangedDoc],
    D: NDArray[np.float64],
    s: "DocumentSettings",
    kind_value: str,
) -> tuple[list[ChangeSet], int, int]:
    """Run the MM-34 fallback-or-HDBSCAN decision on a single block.

    This is the same decision logic extracted from MM-34's cluster_changesets:
    1. If n <= fallback_max_n (and fallback enabled): connected-components.
    2. Else: HDBSCAN. If all-noise and fallback enabled: connected-components.
    3. Else: _changesets_from_labels.

    Returns:
        (changesets, dropped_oversized, dropped_singletons)
    """
    n = len(block)
    gap = float(s.max_cochange_gap_seconds)
    min_size = s.min_cluster_size
    max_size = s.max_cochange_cluster_size
    eps = float(s.cochange_distance_eps)

    use_fallback_directly = s.cochange_fallback_enabled and n <= s.cochange_fallback_max_n
    if use_fallback_directly:
        components = _connected_components(D, eps, min_size)
        return _changesets_from_components(block, components, kind_value, gap, min_size, max_size)

    # HDBSCAN path
    try:
        from sklearn.cluster import HDBSCAN
    except ImportError as exc:
        raise CoChangeUnavailable(
            "scikit-learn is not installed; run: pip install 'mintmory[cochange]'"
        ) from exc

    hdb = HDBSCAN(metric="precomputed", min_cluster_size=min_size)
    hdb.fit(D)
    labels: NDArray[np.int32] = np.asarray(hdb.labels_, dtype=np.int32)
    probs: NDArray[np.float64] = np.asarray(hdb.probabilities_, dtype=np.float64)

    if bool(np.all(labels == -1)) and s.cochange_fallback_enabled:
        components = _connected_components(D, eps, min_size)
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
```

Then replace `cluster_changesets` with the new blocked version. The new function replaces the old one entirely. Replace the existing function body starting at the `if len(docs) < 2` guard:

```python
def cluster_changesets(
    docs: list[ChangedDoc],
    s: "DocumentSettings",
    *,
    run_kind: str = "incremental",
) -> CoChangeResult:
    """Cluster changed documents into change-sets using per-block HDBSCAN or components.

    MM-35: partitions docs into (folder, time-bucket) blocks before clustering so
    the distance matrix is bounded by the block size, not N. Each block runs the
    MM-34 fallback-or-HDBSCAN decision independently. Results are accumulated.

    Returns CoChangeResult with empty changesets when:
    - fewer than 2 docs, or
    - s.cochange_enabled is False.

    Raises CoChangeUnavailable if scikit-learn is not installed AND the HDBSCAN
    path is taken (the connected-components fallback never requires sklearn).
    """
    if len(docs) < 2 or not s.cochange_enabled:
        return CoChangeResult(
            changesets=[], dropped_oversized=0, dropped_singletons=0, truncated=0
        )

    # 1. Sort for determinism (global, feeds _build_blocks order)
    sorted_docs = sorted(docs, key=lambda d: (d.mtime, d.doc_id))

    # E: cochange_label_kind gates whether change-sets carry a kind tag.
    kind_value = run_kind if s.cochange_label_kind else ""

    # 2. Build blocks (MM-35)
    bucket = min(s.cochange_time_bucket_seconds, s.max_cochange_gap_seconds)
    if s.cochange_block_by_folder:
        blocks, total_truncated = _build_blocks(
            sorted_docs, bucket_seconds=bucket, max_block=s.max_cochange_partition_size
        )
    else:
        # Single global block, still capped
        capped = sorted_docs[: s.max_cochange_partition_size]
        total_truncated = max(0, len(sorted_docs) - len(capped))
        blocks = [capped]

    # 3. Cluster each block, accumulate results
    all_changesets: list[ChangeSet] = []
    total_oversized = 0
    total_singletons = 0

    for block in blocks:
        if len(block) < s.min_cluster_size:
            continue
        D = _block_distance_matrix(block, s)
        sets, dropped_over, dropped_sing = _cluster_one_block(block, D, s, kind_value)
        all_changesets.extend(sets)
        total_oversized += dropped_over
        total_singletons += dropped_sing

    return CoChangeResult(
        changesets=all_changesets,
        dropped_oversized=total_oversized,
        dropped_singletons=total_singletons,
        truncated=total_truncated,
    )
```

- [ ] **Step 4: Run all cochange tests**

```bash
uv run --no-sync pytest packages/core/tests/test_cochange.py -q 2>&1 | tail -15
```
Expected: All tests pass (46 old + new MM-35 tests).

---

### Task 6: Update CLI to surface `result.truncated`

**Files:**
- Modify: `packages/cli/src/mintmory/cli/main.py`

- [ ] **Step 1: Add `cochange_result_truncated` tracking and surface in table**

In `packages/cli/src/mintmory/cli/main.py`, update the co-change post-walk section (around line 890):

Change the variable initialization block to add a truncated counter:
```python
    n_changesets = 0
    n_co_changed_files = 0
    cochange_result_dropped_oversized = 0
    cochange_result_dropped_singletons = 0
    cochange_result_truncated = 0  # MM-35: docs dropped from oversized blocks
```

After `cochange_result_dropped_singletons = cochange_result.dropped_singletons`, add:
```python
            cochange_result_truncated = cochange_result.truncated
```

In the table rendering section (after `if cochange_result_dropped_singletons > 0:`), add:
```python
        if cochange_result_truncated > 0:
            table.add_row("truncated_from_blocks", str(cochange_result_truncated))
```

Also add a one-line console notice before the table (immediately after the try block in the co-change section, around line 908), to print when truncated > 0:
```python
            if cochange_result.truncated > 0:
                console.print(
                    f"[yellow]co-change: {cochange_result.truncated} file(s) dropped "
                    f"from oversized blocks (max_cochange_partition_size="
                    f"{doc_s.max_cochange_partition_size})[/yellow]"
                )
```

- [ ] **Step 2: Run CLI tests to ensure nothing broke**

```bash
uv run --no-sync pytest packages/cli/tests/ -q 2>&1 | tail -10
```
Expected: All pass.

---

### Task 7: Run all gates

**Files:** no new files

- [ ] **Step 1: ruff check**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory && uv run --no-sync ruff check packages 2>&1 | tail -20
```
Expected: No errors. Fix any that appear.

- [ ] **Step 2: ruff format**

```bash
uv run --no-sync ruff format packages 2>&1 | tail -5
```
Expected: "N files reformatted" or "All done!" with no errors.

- [ ] **Step 3: mypy --strict**

```bash
uv run --no-sync mypy packages/core/src packages/cli/src 2>&1 | tail -20
```
Expected: "Success: no issues found". Fix any type errors.

- [ ] **Step 4: pytest full suite**

```bash
uv run --no-sync pytest packages/core packages/cli -q 2>&1 | tail -20
```
Expected: >= 80% coverage, all tests pass.

- [ ] **Step 5: openspec validate**

```bash
openspec validate optimize-document-cochange-performance --strict 2>&1
```
Expected: "Change '...' is valid"
