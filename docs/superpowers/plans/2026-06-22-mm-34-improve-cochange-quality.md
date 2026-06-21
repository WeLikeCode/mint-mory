# MM-34 Improve Document Co-Change Quality — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix five correctness defects in the MM-33 co-change clustering: time-gap split to prevent multi-year clusters, size cap to drop bulk-binary blobs, body-chunk recency stamps, cold-vs-incremental kind labelling, and a connected-components fallback so small incremental edits actually register as co-change.

**Architecture:** All changes are additive to existing modules — no new files, no schema migrations. `cochange.py` gains `CoChangeResult`, `_split_on_time_gap`, `_connected_components`, `_changesets_from_components`, and a `kind` field on `ChangeSet`. `config.py` gains 9 new knobs. `tree_index.py` gains `IMAGE_SUFFIXES`. `cli/main.py` is updated to filter excluded suffixes, stamp chunk recency, compute `was_cold`, and surface kind in output. The split/cap/assemble tail is shared between HDBSCAN and fallback paths.

**Tech Stack:** Python 3.12, pydantic-settings, numpy, scikit-learn 1.9.x (HDBSCAN path only; fallback is pure numpy/union-find), SQLite, Typer/Rich CLI, pytest, ruff (line-length 100), mypy --strict.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `packages/core/src/mintmory/core/config.py` | MODIFY | Add 9 new `DocumentSettings` knobs + `cochange_exclude_suffixes` property |
| `packages/core/src/mintmory/core/tree_index.py` | MODIFY | Add `IMAGE_SUFFIXES` frozenset |
| `packages/core/src/mintmory/core/cochange.py` | MODIFY | `CoChangeResult`, `kind` on `ChangeSet`, `_split_on_time_gap`, `_connected_components`, `_changesets_from_components`, refactored `cluster_changesets`, updated `apply_changesets`, updated `documents_timeline`, updated `changed_with` |
| `packages/cli/src/mintmory/cli/main.py` | MODIFY | Exclude-suffix filter, chunk recency, `was_cold`, `run_kind`, result plumbing, summary rows, kind in `changed-with` output |
| `packages/core/tests/test_config.py` | MODIFY | Extend `TestDocumentSettings` with new knob tests |
| `packages/core/tests/test_cochange.py` | MODIFY | Add gap-split, size-cap, kind, fallback, components tests |
| `packages/core/tests/test_index_tree_cochange.py` | MODIFY | Add image-exclusion, chunk-recency, cold/incremental kind, stray-file tests |
| `packages/cli/tests/test_index_tree_cochange_cli.py` | MODIFY | Add image-exclusion CLI, chunk-timeline, cold/incremental kind, end-to-end incremental tests |

---

## Task 1: Config — New `DocumentSettings` Knobs

**Files:**
- Modify: `packages/core/src/mintmory/core/config.py` (lines 289-306)
- Test: `packages/core/tests/test_config.py`

- [ ] **Step 1.1: Write failing tests for new knobs**

Add a new `TestDocumentSettingsMM34` class to `packages/core/tests/test_config.py`:

```python
class TestDocumentSettingsMM34:
    """MM-34: new DocumentSettings knobs."""

    def test_new_knob_defaults(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings()
        assert s.max_cochange_gap_seconds == 86_400
        assert s.max_cochange_cluster_size == 50
        assert s.cochange_exclude_images is True
        assert s.cochange_exclude_artifacts is True
        assert s.cochange_exclude_suffixes_csv == ""
        assert s.cochange_label_kind is True
        assert s.cochange_fallback_enabled is True
        assert s.cochange_fallback_max_n == 8
        assert s.cochange_distance_eps == pytest.approx(0.35)

    def test_max_cochange_gap_seconds_lower_bound(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(max_cochange_gap_seconds=1)
        assert s.max_cochange_gap_seconds == 1

    def test_max_cochange_gap_seconds_below_lower_bound_raises(self) -> None:
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(max_cochange_gap_seconds=0)

    def test_max_cochange_cluster_size_lower_bound(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(max_cochange_cluster_size=2)
        assert s.max_cochange_cluster_size == 2

    def test_max_cochange_cluster_size_below_lower_bound_raises(self) -> None:
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(max_cochange_cluster_size=1)

    def test_cochange_fallback_max_n_lower_bound(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(cochange_fallback_max_n=2)
        assert s.cochange_fallback_max_n == 2

    def test_cochange_fallback_max_n_below_lower_bound_raises(self) -> None:
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(cochange_fallback_max_n=1)

    def test_cochange_distance_eps_bounds(self) -> None:
        from mintmory.core.config import DocumentSettings

        s_low = DocumentSettings(cochange_distance_eps=0.0)
        assert s_low.cochange_distance_eps == pytest.approx(0.0)
        s_high = DocumentSettings(cochange_distance_eps=1.0)
        assert s_high.cochange_distance_eps == pytest.approx(1.0)

    def test_cochange_distance_eps_below_zero_raises(self) -> None:
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(cochange_distance_eps=-0.01)

    def test_cochange_distance_eps_above_one_raises(self) -> None:
        from mintmory.core.config import DocumentSettings

        with pytest.raises(ValidationError):
            DocumentSettings(cochange_distance_eps=1.01)

    def test_cochange_exclude_suffixes_empty(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(cochange_exclude_suffixes_csv="")
        assert s.cochange_exclude_suffixes == frozenset()

    def test_cochange_exclude_suffixes_parsed(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(cochange_exclude_suffixes_csv=".log,.TMP, .bak ")
        assert s.cochange_exclude_suffixes == frozenset({".log", ".tmp", ".bak"})

    def test_cochange_exclude_suffixes_no_leading_dot_gets_one(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(cochange_exclude_suffixes_csv="log,tmp")
        # Should have leading dot added
        assert ".log" in s.cochange_exclude_suffixes
        assert ".tmp" in s.cochange_exclude_suffixes

    def test_cochange_exclude_suffixes_blanks_dropped(self) -> None:
        from mintmory.core.config import DocumentSettings

        s = DocumentSettings(cochange_exclude_suffixes_csv=",.log,,")
        assert s.cochange_exclude_suffixes == frozenset({".log"})

    def test_env_prefix_doc_reads_new_knobs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mintmory.core.config import DocumentSettings

        monkeypatch.setenv("MINTMORY_DOC_MAX_COCHANGE_GAP_SECONDS", "3600")
        monkeypatch.setenv("MINTMORY_DOC_COCHANGE_FALLBACK_ENABLED", "false")
        s = DocumentSettings()
        assert s.max_cochange_gap_seconds == 3600
        assert s.cochange_fallback_enabled is False
```

- [ ] **Step 1.2: Run to confirm failures**

```bash
cd /Users/alexandruiacobescu/gooseProjects/MintMory
uv run --no-sync pytest packages/core/tests/test_config.py::TestDocumentSettingsMM34 -v 2>&1 | tail -20
```

Expected: All tests FAIL with `AttributeError` (fields don't exist yet).

- [ ] **Step 1.3: Implement the new knobs in `DocumentSettings`**

Open `packages/core/src/mintmory/core/config.py`. In `DocumentSettings` (after the `use_embeddings` line), add:

```python
    # MM-34 — A: hard time-gap guard (post-cluster split)
    max_cochange_gap_seconds: int = Field(default=86_400, ge=1)
    # MM-34 — B: cluster-size cap + non-knowledge type exclusion
    max_cochange_cluster_size: int = Field(default=50, ge=2)
    cochange_exclude_images: bool = True
    cochange_exclude_artifacts: bool = True
    cochange_exclude_suffixes_csv: str = ""
    # MM-34 — E: cold/incremental honesty label
    cochange_label_kind: bool = True
    # MM-34 — F: hybrid small-N / all-noise fallback
    cochange_fallback_enabled: bool = True
    cochange_fallback_max_n: int = Field(default=8, ge=2)
    cochange_distance_eps: float = Field(default=0.35, ge=0.0, le=1.0)

    @property
    def cochange_exclude_suffixes(self) -> frozenset[str]:
        """Extra co-change-excluded suffixes: lowercase, single leading dot, blanks dropped."""
        return frozenset(
            f".{tok.lstrip('.')}"
            for tok in _csv_set(self.cochange_exclude_suffixes_csv)
        )
```

- [ ] **Step 1.4: Run tests to confirm passing**

```bash
uv run --no-sync pytest packages/core/tests/test_config.py -v 2>&1 | tail -20
```

Expected: All `TestDocumentSettingsMM34` tests pass. Existing `TestDocumentSettings` tests still pass.

---

## Task 2: `IMAGE_SUFFIXES` in `tree_index.py`

**Files:**
- Modify: `packages/core/src/mintmory/core/tree_index.py` (after line 28, `ARTIFACT_SUFFIXES`)

- [ ] **Step 2.1: Write a failing test**

Add to `packages/core/tests/test_tree_index.py` (or create the `TestImageSuffixes` class if the file exists):

```python
class TestImageSuffixes:
    """MM-34: IMAGE_SUFFIXES frozenset."""

    def test_image_suffixes_exported(self) -> None:
        from mintmory.core.tree_index import IMAGE_SUFFIXES

        assert isinstance(IMAGE_SUFFIXES, frozenset)

    def test_contains_expected_raster_types(self) -> None:
        from mintmory.core.tree_index import IMAGE_SUFFIXES

        for suffix in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
                       ".webp", ".heic", ".heif", ".raw", ".cr2", ".nef", ".psd", ".ico"):
            assert suffix in IMAGE_SUFFIXES, f"{suffix} should be in IMAGE_SUFFIXES"

    def test_svg_not_in_image_suffixes(self) -> None:
        from mintmory.core.tree_index import IMAGE_SUFFIXES

        assert ".svg" not in IMAGE_SUFFIXES  # SVG carries text, not excluded
```

Run:
```bash
uv run --no-sync pytest packages/core/tests/test_tree_index.py::TestImageSuffixes -v 2>&1 | tail -10
```

Expected: FAIL (`ImportError: cannot import name 'IMAGE_SUFFIXES'`).

- [ ] **Step 2.2: Implement `IMAGE_SUFFIXES`**

In `packages/core/src/mintmory/core/tree_index.py`, after the `ARTIFACT_SUFFIXES` definition (line 28), add:

```python
# Raster/binary image suffixes excluded from co-change clustering by default (MM-34).
# SVG is intentionally NOT here — it carries extractable text and is a knowledge candidate.
IMAGE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp",
        ".heic", ".heif", ".raw", ".cr2", ".nef", ".psd", ".ico",
    }
)
```

- [ ] **Step 2.3: Run tests**

```bash
uv run --no-sync pytest packages/core/tests/test_tree_index.py -v 2>&1 | tail -10
```

Expected: All pass.

---

## Task 3: `CoChangeResult`, `kind` on `ChangeSet`, Time-Gap Split, Size Cap

**Files:**
- Modify: `packages/core/src/mintmory/core/cochange.py`
- Test: `packages/core/tests/test_cochange.py`

This is the biggest core change. We'll do it in one step to keep consistency.

- [ ] **Step 3.1: Write failing tests for gap split, size cap, kind, and `CoChangeResult`**

Add new test classes to `packages/core/tests/test_cochange.py`:

```python
# ---------------------------------------------------------------------------
# Helper: update _settings() to accept new MM-34 knobs
# ---------------------------------------------------------------------------


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


class TestCoChangeResult:
    """MM-34: cluster_changesets returns CoChangeResult, not list[ChangeSet]."""

    def test_result_type_empty(self) -> None:
        from mintmory.core.cochange import CoChangeResult, cluster_changesets

        s = _settings_mm34()
        result = cluster_changesets([], s)  # type: ignore[arg-type]
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
        result = cluster_changesets(docs, s)  # type: ignore[arg-type]
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

    def test_kind_default_changeset_from_labels(self) -> None:
        """_changesets_from_labels accepts run_kind and sets it on every ChangeSet."""
        from mintmory.core.cochange import _changesets_from_labels

        docs = [
            _make_doc("c0a", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("c0b", "/root/a/f2.txt", "a/f2.txt", 60.0),
        ]
        labels = np.array([0, 0], dtype=np.int32)
        probs = np.array([1.0, 1.0], dtype=np.float64)
        # Note: _changesets_from_labels needs the gap/min_size args after refactor.
        # It now returns (list[ChangeSet], dropped_singletons_count).
        sets, dropped = _changesets_from_labels(
            docs,  # type: ignore[arg-type]
            labels,
            probs,
            run_kind="cold_full_index",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        assert all(cs.kind == "cold_full_index" for cs in sets)

    def test_kind_incremental_is_default(self) -> None:
        """run_kind defaults to 'incremental' when not supplied."""
        from mintmory.core.cochange import _changesets_from_labels

        docs = [
            _make_doc("c0a", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("c0b", "/root/a/f2.txt", "a/f2.txt", 60.0),
        ]
        labels = np.array([0, 0], dtype=np.int32)
        probs = np.array([1.0, 1.0], dtype=np.float64)
        sets, _ = _changesets_from_labels(
            docs,  # type: ignore[arg-type]
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
        # gap = 86400 >> 2000s between adjacent -> no split
        groups, dropped = _split_on_time_gap(docs, gap_seconds=86_400, min_size=2)  # type: ignore[arg-type]
        assert len(groups) == 1
        assert len(groups[0]) == 3
        assert dropped == 0

    def test_split_on_2year_internal_gap(self) -> None:
        from mintmory.core.cochange import _split_on_time_gap

        TWO_YEARS = 2 * 365 * 24 * 3600  # ~63M seconds
        # Burst A: t=0, t=60. Burst B: t=TWO_YEARS, t=TWO_YEARS+60
        docs = [
            _make_doc("a1", "/root/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("a2", "/root/a/f2.txt", "a/f2.txt", 60.0),
            _make_doc("b1", "/root/a/f3.txt", "a/f3.txt", float(TWO_YEARS)),
            _make_doc("b2", "/root/a/f4.txt", "a/f4.txt", float(TWO_YEARS + 60)),
        ]
        groups, dropped = _split_on_time_gap(docs, gap_seconds=86_400, min_size=2)  # type: ignore[arg-type]
        assert len(groups) == 2, f"Expected 2 groups after 2-year gap, got {len(groups)}"
        assert dropped == 0

    def test_sub_min_size_fragment_dropped(self) -> None:
        from mintmory.core.cochange import _split_on_time_gap

        # Cluster: two close, then big gap, then one lone file (below min_size=2)
        docs = [
            _make_doc("a1", "/a/f1.txt", "f1.txt", 0.0),
            _make_doc("a2", "/a/f2.txt", "f2.txt", 60.0),
            _make_doc("lone", "/a/f3.txt", "f3.txt", float(90 * 24 * 3600)),  # 90 days later
        ]
        groups, dropped = _split_on_time_gap(docs, gap_seconds=86_400, min_size=2)  # type: ignore[arg-type]
        assert len(groups) == 1  # only the pair survives
        assert dropped == 1  # the lone singleton is dropped

    def test_adjacent_gap_invariant_on_output(self) -> None:
        """Every pair of adjacent (by mtime) members in every output group
        must have a gap <= gap_seconds."""
        from mintmory.core.cochange import _split_on_time_gap

        # Irregular spacing: 0, 100, 200, 300 (no gap > 86400)
        docs = [
            _make_doc(f"m{i}", f"/a/f{i}.txt", f"f{i}.txt", float(i * 100))
            for i in range(4)
        ]
        groups, _ = _split_on_time_gap(docs, gap_seconds=86_400, min_size=2)  # type: ignore[arg-type]
        for group in groups:
            sorted_group = sorted(group, key=lambda d: (d.mtime, d.doc_id))  # type: ignore[attr-defined]
            for k in range(len(sorted_group) - 1):
                gap = sorted_group[k + 1].mtime - sorted_group[k].mtime  # type: ignore[attr-defined]
                assert gap <= 86_400

    def test_fragment_changeset_id_is_deterministic(self) -> None:
        """Each fragment from _split_on_time_gap gets a deterministic sha1 id."""
        from mintmory.core.cochange import _changesets_from_labels, _split_on_time_gap

        TWO_YEARS = 2 * 365 * 24 * 3600
        docs = [
            _make_doc("a1", "/a/f1.txt", "a/f1.txt", 0.0),
            _make_doc("a2", "/a/f2.txt", "a/f2.txt", 60.0),
            _make_doc("b1", "/a/f3.txt", "a/f3.txt", float(TWO_YEARS)),
            _make_doc("b2", "/a/f4.txt", "a/f4.txt", float(TWO_YEARS + 60)),
        ]
        # Run twice and confirm same ids
        labels = np.array([0, 0, 0, 0], dtype=np.int32)
        probs = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float64)
        sets_a, _ = _changesets_from_labels(
            docs, labels, probs,  # type: ignore[arg-type]
            run_kind="incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        sets_b, _ = _changesets_from_labels(
            docs, labels, probs,  # type: ignore[arg-type]
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

    def test_60_member_cluster_dropped_with_count(self) -> None:
        from mintmory.core.cochange import _changesets_from_labels

        # 60 docs all within 5s of each other (one large cluster)
        docs = [
            _make_doc(f"m{i}", f"/a/f{i}.txt", f"f{i}.txt", float(i * 5))
            for i in range(60)
        ]
        labels = np.array([0] * 60, dtype=np.int32)
        probs = np.array([1.0] * 60, dtype=np.float64)
        sets, dropped = _changesets_from_labels(
            docs, labels, probs,  # type: ignore[arg-type]
            run_kind="incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        # The 60-member cluster was not split by gap (all within 86400s) but exceeds cap
        # Actually 60 * 5s = 295s << 86400s, so no gap split -> 1 cluster of 60 -> dropped
        assert len(sets) == 0
        assert dropped == 1

    def test_small_cluster_not_dropped(self) -> None:
        from mintmory.core.cochange import _changesets_from_labels

        docs = [
            _make_doc(f"m{i}", f"/a/f{i}.txt", f"f{i}.txt", float(i * 5))
            for i in range(10)
        ]
        labels = np.array([0] * 10, dtype=np.int32)
        probs = np.array([1.0] * 10, dtype=np.float64)
        sets, dropped = _changesets_from_labels(
            docs, labels, probs,  # type: ignore[arg-type]
            run_kind="incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        assert len(sets) == 1
        assert dropped == 0
```

- [ ] **Step 3.2: Run to confirm failures**

```bash
uv run --no-sync pytest packages/core/tests/test_cochange.py::TestCoChangeResult packages/core/tests/test_cochange.py::TestChangeSetKind packages/core/tests/test_cochange.py::TestTimeGapSplit packages/core/tests/test_cochange.py::TestSizeCap -v 2>&1 | tail -30
```

Expected: All FAIL.

- [ ] **Step 3.3: Implement the changes in `cochange.py`**

Replace the entire `packages/core/src/mintmory/core/cochange.py` with the updated version. The key changes are:

1. Add `CoChangeResult` dataclass after `ChangeSet`
2. Add `kind: str` field to `ChangeSet`
3. Add `_split_on_time_gap`
4. Refactor `_changesets_from_labels` to accept `run_kind`, `gap_seconds`, `min_size`, `max_cluster_size` and return `tuple[list[ChangeSet], int]` (sets + dropped_oversized_count; plus track dropped singletons separately)
5. Update `cluster_changesets` signature: add `run_kind: str = "incremental"` param; return `CoChangeResult`

Here is the full updated `cochange.py`:

```python
"""
core/cochange.py — document co-change clustering and store I/O (MM-33/MM-34).

Pure clustering (no store, no network) + thin store wrappers for applying
change-sets and querying co-changed documents.

The clustering uses HDBSCAN from scikit-learn (optional ``cochange`` extra).
When scikit-learn is not installed, ``cluster_changesets`` raises
``CoChangeUnavailable`` — the CLI catches this and prints an install hint.

MM-34 additions:
- CoChangeResult dataclass (cluster_changesets now returns this, not list[ChangeSet])
- kind: str field on ChangeSet (propagated from run_kind parameter)
- _split_on_time_gap: post-cluster split on adjacent mtime gap > gap_seconds
- _connected_components: pure union-find fallback (no sklearn)
- _changesets_from_components: builds ChangeSet clusters from components
- Hybrid fallback: when n <= fallback_max_n OR HDBSCAN returns all-noise
- documents_timeline: NULL-safe record_role != 'chunk' predicate
- changed_with: includes kind from metadata.changeset_kind

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
    kind: str = "incremental"  # MM-34 E: 'cold_full_index' | 'incremental'


@dataclass
class CoChangeResult:
    """Return value of cluster_changesets (MM-34)."""

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

    Args:
        cluster_docs: The documents in one raw cluster (any order).
        gap_seconds: Adjacent-pair mtime gap threshold in seconds.
        min_size: Sub-groups smaller than this are dropped (counted as singletons).

    Returns:
        (sub_groups, dropped_singleton_count) where sub_groups contains only
        groups with len >= min_size. The order within each group is (mtime, doc_id).
    """
    sorted_docs = sorted(cluster_docs, key=lambda d: (d.mtime, d.doc_id))
    if not sorted_docs:
        return [], 0

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
# MM-34 F: connected-components fallback (pure numpy, no sklearn)
# ---------------------------------------------------------------------------


def _connected_components(
    dist_matrix: NDArray[np.float64],
    eps: float,
    min_size: int,
) -> list[list[int]]:
    """Union-find connected components over a symmetric distance matrix.

    Two nodes i,j are connected when dist_matrix[i,j] <= eps.
    Returns a list of component index-lists, each with len >= min_size.
    The component membership is stable (deterministic) given a fixed node
    ordering (the (mtime, doc_id) sort order used by cluster_changesets).

    Does NOT require scikit-learn.
    """
    n = dist_matrix.shape[0]
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
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

    components: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        components[find(i)].append(i)

    return [sorted(members) for members in components.values() if len(members) >= min_size]


def _changesets_from_components(
    sorted_docs: list[ChangedDoc],
    components: list[list[int]],
    run_kind: str,
    gap_seconds: float,
    min_size: int,
    max_cluster_size: int,
) -> tuple[list[ChangeSet], int, int]:
    """Build ChangeSets from connected-components clusters (MM-34 F fallback).

    Each component is a list of indices into sorted_docs. The edge strength
    for fallback clusters is 1.0 (no HDBSCAN membership probability available).
    Passes through the same gap-split (A) and size-cap (B) as the HDBSCAN path.

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
            cs = _build_changeset(group, strength_fn=lambda _i, _j: 1.0, run_kind=run_kind)
            all_sets.append(cs)

    return all_sets, total_oversized, total_singletons


# ---------------------------------------------------------------------------
# Internal: build one ChangeSet from a list of docs
# ---------------------------------------------------------------------------


def _build_changeset(
    docs: list[ChangedDoc],
    *,
    strength_fn: Any,  # callable(i, j) -> float where i,j are indices into docs
    run_kind: str,
) -> ChangeSet:
    """Build a single ChangeSet from a list of ChangedDoc (already gap-split/capped).

    strength_fn(i, j) returns the edge strength for docs[i] <-> docs[j].
    """
    doc_ids_sorted = sorted(d.doc_id for d in docs)
    max_mtime = max(d.mtime for d in docs)

    # Deterministic id: sha1 over sorted doc_ids + max_mtime
    payload = "|".join(doc_ids_sorted) + f"@{max_mtime:.0f}"
    changeset_id = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]  # noqa: S324

    observed_at = datetime.fromtimestamp(max_mtime, tz=UTC).replace(tzinfo=None).isoformat()
    member_ids = sorted(d.memory_id for d in docs)

    # Pairwise edges
    edges: list[tuple[str, str, float]] = []
    for ci in range(len(docs)):
        for cj in range(ci + 1, len(docs)):
            strength = float(max(0.0, min(1.0, strength_fn(ci, cj))))
            edges.append((docs[ci].memory_id, docs[cj].memory_id, strength))

    # Order by mtime
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


# ---------------------------------------------------------------------------
# Core clustering
# ---------------------------------------------------------------------------


def cluster_changesets(
    docs: list[ChangedDoc],
    s: DocumentSettings,
    *,
    run_kind: str = "incremental",
) -> CoChangeResult:
    """Cluster changed documents into change-sets.

    MM-34: Returns CoChangeResult (was list[ChangeSet]).

    Algorithm:
    1. Sort docs by (mtime, doc_id) for determinism.
    2. Build a precomputed N×N float64 distance matrix.
    3a. If fallback_enabled and n <= fallback_max_n: skip HDBSCAN, use
        connected-components at eps=cochange_distance_eps.
    3b. Else: fit HDBSCAN. If it returns all-noise and fallback_enabled:
        use connected-components on the same matrix.
    4. Feed raw clusters through _split_on_time_gap (A) and size cap (B).
    5. Return CoChangeResult.

    Returns CoChangeResult with empty changesets when:
    - fewer than 2 docs, or
    - s.cochange_enabled is False.

    Raises CoChangeUnavailable if scikit-learn is not installed AND HDBSCAN
    path is needed (fallback path never requires sklearn).
    """
    if len(docs) < 2 or not s.cochange_enabled:
        return CoChangeResult(changesets=[], dropped_oversized=0, dropped_singletons=0)

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

    # 3. Choose path: fallback (components) or HDBSCAN
    use_fallback_directly = s.cochange_fallback_enabled and n <= s.cochange_fallback_max_n

    if use_fallback_directly:
        components = _connected_components(dist_matrix, eps, min_size)
        changesets, dropped_oversized, dropped_singletons = _changesets_from_components(
            sorted_docs, components, run_kind, gap, min_size, max_size
        )
        return CoChangeResult(
            changesets=changesets,
            dropped_oversized=dropped_oversized,
            dropped_singletons=dropped_singletons,
        )

    # HDBSCAN path — lazy import
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

    # Check if HDBSCAN returned all noise
    all_noise = bool(np.all(labels == -1))
    if all_noise and s.cochange_fallback_enabled:
        components = _connected_components(dist_matrix, eps, min_size)
        changesets, dropped_oversized, dropped_singletons = _changesets_from_components(
            sorted_docs, components, run_kind, gap, min_size, max_size
        )
        return CoChangeResult(
            changesets=changesets,
            dropped_oversized=dropped_oversized,
            dropped_singletons=dropped_singletons,
        )

    sets, dropped_oversized, dropped_singletons = _changesets_from_labels(
        sorted_docs, labels, probs,
        run_kind=run_kind,
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

    Label -1 (noise) is excluded. Each raw cluster is passed through
    _split_on_time_gap (A) and the size cap (B).

    Returns:
        (changesets, dropped_oversized, dropped_singletons)
    """
    from collections import defaultdict

    clusters: dict[int, list[int]] = defaultdict(list)
    for idx, label in enumerate(labels):
        if int(label) >= 0:
            clusters[int(label)].append(idx)

    all_sets: list[ChangeSet] = []
    total_oversized = 0
    total_singletons = 0

    for _label, indices in sorted(clusters.items()):
        cluster_docs = [sorted_docs[i] for i in indices]
        # A: gap split
        sub_groups, singletons = _split_on_time_gap(cluster_docs, gap_seconds, min_size)
        total_singletons += singletons
        # B + assemble: size cap + build ChangeSet per surviving fragment
        for group in sub_groups:
            if len(group) > max_cluster_size:
                total_oversized += 1
                continue
            # Build index mapping within the ORIGINAL sorted_docs for probs lookup
            # We need the probability for each doc in the group (by original index)
            orig_indices = {sorted_docs[i].doc_id: i for i in indices}

            def _strength(ci: int, cj: int, _g: list[ChangedDoc] = group) -> float:
                gi = orig_indices.get(_g[ci].doc_id, 0)
                gj = orig_indices.get(_g[cj].doc_id, 0)
                return float(max(0.0, min(1.0, min(probs[gi], probs[gj]))))

            cs = _build_changeset(group, strength_fn=_strength, run_kind=run_kind)
            all_sets.append(cs)

    return all_sets, total_oversized, total_singletons
```

- [ ] **Step 3.4: Run tests**

```bash
uv run --no-sync pytest packages/core/tests/test_cochange.py -v 2>&1 | tail -40
```

Expected: All new tests pass. Existing `TestEdgeCases`, `TestDistanceBounds` pass (they call `cluster_changesets` and check `== []` — update them to check `result.changesets == []`).

**IMPORTANT:** The existing edge-case tests call `cluster_changesets` and compare to `[]`. After the signature change, `cluster_changesets` returns `CoChangeResult`, not a list. You MUST update those old tests:

```python
# In TestEdgeCases:
def test_empty_docs_returns_empty(self) -> None:
    from mintmory.core.cochange import cluster_changesets

    s = _settings()
    result = cluster_changesets([], s)  # type: ignore[arg-type]
    assert result.changesets == []  # was: assert result == []

def test_single_doc_returns_empty(self) -> None:
    from mintmory.core.cochange import cluster_changesets

    docs = [_make_doc("m1", "/a/b.txt", "b.txt", 1_000.0)]
    s = _settings()
    result = cluster_changesets(docs, s)  # type: ignore[arg-type]
    assert result.changesets == []  # was: assert result == []

def test_disabled_returns_empty(self) -> None:
    from mintmory.core.cochange import cluster_changesets

    docs = [
        _make_doc("m1", "/a/b.txt", "b.txt", 1_000.0),
        _make_doc("m2", "/a/c.txt", "c.txt", 1_001.0),
    ]
    s = _settings(cochange_enabled=False)
    result = cluster_changesets(docs, s)  # type: ignore[arg-type]
    assert result.changesets == []  # was: assert result == []
```

Also update `TestClustering` tests similarly (they use `sets = cluster_changesets(...)` and then check `len(sets) == 2` etc.) — change to `result = cluster_changesets(...); sets = result.changesets`.

---

## Task 4: Fallback (Connected-Components) Tests

**Files:**
- Test: `packages/core/tests/test_cochange.py`

- [ ] **Step 4.1: Add fallback tests (no sklearn gate required)**

Add class `TestConnectedComponentsFallback` to `test_cochange.py`:

```python
class TestConnectedComponentsFallback:
    """MM-34 F: connected-components fallback — no sklearn required."""

    def test_connected_components_tight_cluster(self) -> None:
        """4 nodes all within eps of each other → one component."""
        from mintmory.core.cochange import _connected_components

        # 4×4 matrix where all pairwise distances = 0.05
        d: NDArray[np.float64] = np.full((4, 4), 0.05, dtype=np.float64)
        np.fill_diagonal(d, 0.0)
        components = _connected_components(d, eps=0.35, min_size=2)
        assert len(components) == 1
        assert sorted(components[0]) == [0, 1, 2, 3]

    def test_connected_components_two_disjoint_clusters(self) -> None:
        """Nodes 0,1 close to each other; nodes 2,3 close to each other; cross >> eps."""
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
        """A component with fewer than min_size members is not returned."""
        from mintmory.core.cochange import _connected_components

        # 3 nodes: 0-1 close, node 2 isolated (all distances > eps)
        d: NDArray[np.float64] = np.array(
            [[0.0, 0.05, 0.9], [0.05, 0.0, 0.9], [0.9, 0.9, 0.0]],
            dtype=np.float64,
        )
        components = _connected_components(d, eps=0.35, min_size=2)
        # {0,1} passes min_size=2; {2} (size 1) is excluded
        assert len(components) == 1
        assert sorted(components[0]) == [0, 1]

    def test_changesets_from_components_basic(self) -> None:
        """_changesets_from_components builds valid ChangeSets from components."""
        from mintmory.core.cochange import _changesets_from_components

        docs = [
            _make_doc("m1", "/a/f1.txt", "f1.txt", 100.0),
            _make_doc("m2", "/a/f2.txt", "f2.txt", 200.0),
            _make_doc("m3", "/b/f3.txt", "b/f3.txt", 300.0),
            _make_doc("m4", "/b/f4.txt", "b/f4.txt", 400.0),
        ]
        # Component 1: [0,1]; Component 2: [2,3]
        components = [[0, 1], [2, 3]]
        sets, dropped_oversized, dropped_singletons = _changesets_from_components(
            docs, components, "incremental", gap_seconds=86_400, min_size=2, max_cluster_size=50  # type: ignore[arg-type]
        )
        assert len(sets) == 2
        assert dropped_oversized == 0
        assert dropped_singletons == 0
        for cs in sets:
            assert len(cs.member_ids) == 2
            assert cs.kind == "incremental"

    def test_cluster_changesets_small_n_takes_fallback_path(self) -> None:
        """n <= fallback_max_n: HDBSCAN is skipped; 4 tight files form one change-set."""
        from mintmory.core.cochange import cluster_changesets

        # 4 tight docs: same folder, same-ish mtime, no embeddings
        docs = [
            _make_doc(f"m{i}", f"/root/f{i}.txt", f"f{i}.txt", float(i * 5))
            for i in range(4)
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
        result = cluster_changesets(docs, s, run_kind="incremental")  # type: ignore[arg-type]
        # All 4 docs have time_dist ~ 0 and path_dist=0 (same root) → D ≈ 0 << eps=0.35
        assert len(result.changesets) == 1
        assert len(result.changesets[0].member_ids) == 4

    def test_cluster_changesets_fallback_deterministic_id(self) -> None:
        """Fallback changeset_id is stable across two calls with identical input."""
        from mintmory.core.cochange import cluster_changesets

        docs = [
            _make_doc(f"m{i}", f"/root/f{i}.txt", f"f{i}.txt", float(i * 5))
            for i in range(4)
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
        r1 = cluster_changesets(docs, s, run_kind="incremental")  # type: ignore[arg-type]
        r2 = cluster_changesets(docs, s, run_kind="incremental")  # type: ignore[arg-type]
        ids1 = sorted(cs.changeset_id for cs in r1.changesets)
        ids2 = sorted(cs.changeset_id for cs in r2.changesets)
        assert ids1 == ids2

    def test_fallback_two_files_beyond_eps_not_unioned(self) -> None:
        """Two files with pairwise distance > eps are NOT placed in the same change-set."""
        from mintmory.core.cochange import cluster_changesets

        # Two docs with high time distance (tau=3600; 10h apart = 0.8*tau) + different folder
        docs = [
            _make_doc("ma", "/root/a/fa.txt", "a/fa.txt", 0.0),
            _make_doc("mb", "/root/b/fb.txt", "b/fb.txt", 36_000.0),  # 10h later
        ]
        s = _settings_mm34(
            cochange_fallback_enabled=True,
            cochange_fallback_max_n=8,
            cochange_distance_eps=0.35,  # distance(ma,mb) > 0.35
            weight_time=1.0,
            weight_path=0.5,
            weight_content=0.0,
            tau_seconds=3600,
            min_cluster_size=2,
            use_embeddings=False,
        )
        result = cluster_changesets(docs, s, run_kind="incremental")  # type: ignore[arg-type]
        # These two files should NOT form a change-set (distance > eps)
        assert len(result.changesets) == 0

    def test_fallback_obeys_gap_split_and_size_cap(self) -> None:
        """Fallback component clusters still pass through gap-split and size cap."""
        from mintmory.core.cochange import _changesets_from_components

        # 60 docs, all pairwise distance 0 (same file, different ids), in one component
        docs = [
            _make_doc(f"m{i}", f"/a/f{i}.txt", f"f{i}.txt", float(i * 10))
            for i in range(60)
        ]
        # One component with all 60 indices
        components = [list(range(60))]
        sets, dropped_oversized, dropped_singletons = _changesets_from_components(
            docs, components, "incremental", gap_seconds=86_400, min_size=2, max_cluster_size=50  # type: ignore[arg-type]
        )
        # 60 * 10s = 590s total span, no gap split, but 60 > 50 → dropped
        assert len(sets) == 0
        assert dropped_oversized == 1

    def test_all_noise_hdbscan_triggers_fallback(self) -> None:
        """When HDBSCAN labels all docs as noise, fallback fires if enabled."""
        sklearn = pytest.importorskip("sklearn")  # noqa: F841
        from mintmory.core.cochange import _changesets_from_labels

        docs = [
            _make_doc(f"m{i}", f"/root/f{i}.txt", f"f{i}.txt", float(i * 5))
            for i in range(4)
        ]
        # Force all-noise labels
        labels = np.array([-1, -1, -1, -1], dtype=np.int32)
        probs = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float64)
        # _changesets_from_labels should yield 0 changesets (all noise, no fallback here)
        sets, dropped_oversized, dropped_singletons = _changesets_from_labels(
            docs, labels, probs,  # type: ignore[arg-type]
            run_kind="incremental",
            gap_seconds=86_400,
            min_size=2,
            max_cluster_size=50,
        )
        assert len(sets) == 0
        assert dropped_oversized == 0
        # But cluster_changesets with n<=max_n will use fallback instead of HDBSCAN
```

- [ ] **Step 4.2: Run fallback tests**

```bash
uv run --no-sync pytest packages/core/tests/test_cochange.py::TestConnectedComponentsFallback -v 2>&1 | tail -30
```

Expected: All pass (pure numpy tests run without sklearn).

---

## Task 5: Update `apply_changesets` + `documents_timeline` + `changed_with`

**Files:**
- Modify: `packages/core/src/mintmory/core/cochange.py`

These are smaller surgical changes to the existing store methods.

- [ ] **Step 5.1: Write failing tests for the query side**

Add to `packages/core/tests/test_index_tree_cochange.py`:

```python
class TestQuerySideMM34:
    """MM-34 D/E: documents_timeline excludes chunks; changed_with returns kind."""

    def test_timeline_excludes_chunks(self, tmp_path: Path) -> None:
        """Body chunks with record_role='chunk' are NOT shown in documents_timeline."""
        from mintmory.core.cochange import documents_timeline
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        mtime = 1_700_000_000.0
        vf = datetime.fromtimestamp(mtime, tz=UTC).replace(tzinfo=None)

        # File record
        store.add_memory(
            content="File: report.pdf",
            category="context",
            source="document",
            valid_from=vf,
            metadata={
                "path": "/a/report.pdf",
                "collection": "c",
                "modified_source": "fs_mtime",
                "record_role": "file",
            },
        )
        # Body chunk — should NOT appear in timeline
        store.add_memory(
            content="This is the body content chunk 0",
            category="fact",
            source="document",
            valid_from=vf,
            metadata={
                "path": "/a/report.pdf",
                "collection": "c",
                "modified_source": "fs_mtime",
                "record_role": "chunk",
            },
        )

        rows = documents_timeline(store, limit=50)  # type: ignore[arg-type]
        assert len(rows) == 1
        assert rows[0]["path"] == "/a/report.pdf"

    def test_timeline_includes_legacy_records_without_record_role(self, tmp_path: Path) -> None:
        """Legacy file-records without record_role still appear (NULL-safe predicate)."""
        from mintmory.core.cochange import documents_timeline
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        vf = datetime.fromtimestamp(1_000_000.0, tz=UTC).replace(tzinfo=None)
        store.add_memory(
            content="legacy record",
            category="context",
            source="document",
            valid_from=vf,
            metadata={"path": "/old.txt", "collection": "c"},  # no record_role
        )

        rows = documents_timeline(store, limit=50)  # type: ignore[arg-type]
        assert len(rows) == 1
        assert rows[0]["path"] == "/old.txt"

    def test_changed_with_returns_kind(self, tmp_path: Path) -> None:
        """changed_with includes kind from metadata.changeset_kind."""
        from mintmory.core.cochange import changed_with
        from mintmory.core.storage import StorageAdapter

        store = StorageAdapter(str(tmp_path / "test.db"))
        store.initialise()

        mtime = 1_000_000.0
        vf = datetime.fromtimestamp(mtime, tz=UTC).replace(tzinfo=None)

        mem_a = store.add_memory(
            content="doc a",
            category="context",
            source="document",
            valid_from=vf,
            metadata={
                "path": "/a/fa.txt",
                "collection": "c",
                "changeset_id": "cs001",
                "changeset_observed_at": "2026-01-01T00:00:00",
                "changeset_kind": "incremental",
            },
        )
        store.add_memory(
            content="doc b",
            category="context",
            source="document",
            valid_from=vf,
            metadata={
                "path": "/a/fb.txt",
                "collection": "c",
                "changeset_id": "cs001",
                "changeset_observed_at": "2026-01-01T00:00:00",
                "changeset_kind": "incremental",
            },
        )

        _ = mem_a
        peers = changed_with(store, "/a/fa.txt")  # type: ignore[arg-type]
        assert len(peers) == 1
        assert "kind" in peers[0]
        assert peers[0]["kind"] == "incremental"
```

- [ ] **Step 5.2: Run to see failures**

```bash
uv run --no-sync pytest packages/core/tests/test_index_tree_cochange.py::TestQuerySideMM34 -v 2>&1 | tail -20
```

Expected: `test_timeline_excludes_chunks` FAILS (chunks appear), `test_changed_with_returns_kind` FAILS (no `kind` key).

- [ ] **Step 5.3: Update `apply_changesets`**

In `cochange.py`, the `apply_changesets` function currently takes `sets: list[ChangeSet]`. Update the metadata merge to also write `changeset_kind`:

```python
            merged_meta["changeset_id"] = cs.changeset_id
            merged_meta["changeset_observed_at"] = cs.observed_at
            merged_meta["changeset_method"] = method
            merged_meta["changeset_kind"] = cs.kind  # MM-34 E
```

- [ ] **Step 5.4: Update `documents_timeline` SQL predicate**

In `documents_timeline`, add to the `where` list:

```python
        "(json_extract(metadata, '$.record_role') IS NULL "
        "OR json_extract(metadata, '$.record_role') != 'chunk')",
```

- [ ] **Step 5.5: Update `changed_with` to include `kind`**

In `changed_with`, in the results.append block, add:

```python
            "kind": peer_meta.get("changeset_kind", ""),
```

- [ ] **Step 5.6: Run query-side tests**

```bash
uv run --no-sync pytest packages/core/tests/test_index_tree_cochange.py -v 2>&1 | tail -30
```

Expected: All pass (including existing tests). **Note:** The existing integration tests call `apply_changesets(store, sets)` where `sets` used to be `list[ChangeSet]` from `cluster_changesets` — now they need to pass `result.changesets`. Update those call sites in `test_index_tree_cochange.py`.

---

## Task 6: CLI Updates

**Files:**
- Modify: `packages/cli/src/mintmory/cli/main.py`
- Test: `packages/cli/tests/test_index_tree_cochange_cli.py`

- [ ] **Step 6.1: Write failing CLI tests**

Add these test functions/classes to `packages/cli/tests/test_index_tree_cochange_cli.py`:

```python
import time

_T0_CLI = 1_700_000_000.0


def _make_mixed_tree(root: Path) -> None:
    """Create a tree with both .md files and .jpg image files at similar mtimes."""
    files = {
        "folder_a/doc1.md": _T0_CLI,
        "folder_a/doc2.md": _T0_CLI + 60.0,
        "folder_a/photo.jpg": _T0_CLI + 30.0,  # image file — excluded from co-change
    }
    for rel, mtime in files.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(f"content of {rel}")
        os.utime(fp, (mtime, mtime))


def _make_text_with_content(root: Path) -> None:
    """Create a text file with substantial content for chunk testing."""
    fp = root / "doc_with_body.md"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("Section 1\n" + "text " * 200 + "\n\nSection 2\n" + "more " * 200)
    os.utime(fp, (_T0_CLI, _T0_CLI))


# --- Image exclusion from co-change ---


@pytest.mark.skipif(
    pytest.importorskip("sklearn", reason="scikit-learn required") is None,
    reason="requires sklearn",
)
def test_image_files_excluded_from_cochange_but_indexed(
    cli_db: Path, tmp_path: Path
) -> None:
    """Image files (.jpg) get recency but no changeset_id even when alongside .md files."""
    sklearn = pytest.importorskip("sklearn")  # noqa: F841
    root = tmp_path / "corpus"
    _make_mixed_tree(root)

    result = runner.invoke(app, ["index-tree", str(root), "--cochange"])
    assert result.exit_code == 0, result.output

    store = _store(cli_db)
    # .jpg should be indexed (has a document memory) but no changeset_id
    jpg_meta = _doc_meta(store, str(root / "folder_a/photo.jpg"))
    assert "changeset_id" not in jpg_meta
    # .md files CAN have a changeset_id (two .md files in same folder at close mtimes)
    md1_meta = _doc_meta(store, str(root / "folder_a/doc1.md"))
    assert md1_meta.get("modified_source") == "fs_mtime"  # indexed with recency


# --- Body chunk recency and record_role ---


def test_body_chunk_recency_and_record_role(cli_db: Path, tmp_path: Path) -> None:
    """Body chunks get valid_from + record_role='chunk'; timeline shows 1 row not 2."""
    root = tmp_path / "corpus"
    _make_text_with_content(root)

    result = runner.invoke(
        app,
        ["index-tree", str(root), "--no-cochange", "--text-content"],
    )
    assert result.exit_code == 0, result.output

    store = _store(cli_db)
    conn = store.connect()

    # Expect: 1 file record (record_role='file') + at least 1 chunk (record_role='chunk')
    all_doc_rows = conn.execute(
        "SELECT metadata FROM memories WHERE source='document' AND is_archived=0"
    ).fetchall()
    roles = [json.loads(r["metadata"] or "{}").get("record_role") for r in all_doc_rows]
    assert "file" in roles
    assert "chunk" in roles

    # documents_timeline should show only 1 row (the file record, not the chunks)
    from mintmory.core.cochange import documents_timeline

    rows = documents_timeline(store, limit=50)
    assert len(rows) == 1

    # Chunks should carry valid_from
    chunk_rows = conn.execute(
        "SELECT valid_from, metadata FROM memories WHERE source='document' "
        "AND is_archived=0 AND json_extract(metadata, '$.record_role') = 'chunk'"
    ).fetchall()
    assert len(chunk_rows) >= 1
    for r in chunk_rows:
        assert r["valid_from"] is not None
        meta = json.loads(r["metadata"] or "{}")
        assert meta.get("modified_source") == "fs_mtime"
        assert meta.get("record_role") == "chunk"


# --- Cold vs incremental kind ---


def test_cold_run_tags_cold_full_index(cli_db: Path, tmp_path: Path) -> None:
    """First (cold) index-tree run tags change-sets as cold_full_index."""
    sklearn = pytest.importorskip("sklearn")  # noqa: F841
    root = tmp_path / "corpus"
    _make_tree(root)

    result = runner.invoke(app, ["index-tree", str(root), "--cochange"])
    assert result.exit_code == 0, result.output

    store = _store(cli_db)
    conn = store.connect()
    kinds = conn.execute(
        "SELECT DISTINCT json_extract(metadata, '$.changeset_kind') AS k "
        "FROM memories WHERE source='document' AND is_archived=0"
    ).fetchall()
    kind_values = {r["k"] for r in kinds if r["k"] is not None}
    assert "cold_full_index" in kind_values, f"expected cold_full_index in {kind_values}"


def test_incremental_run_tags_incremental(cli_db: Path, tmp_path: Path) -> None:
    """Second run (after cold first) editing a subset tags those change-sets incremental."""
    sklearn = pytest.importorskip("sklearn")  # noqa: F841
    root = tmp_path / "corpus"
    _make_tree(root)

    # Cold first run
    assert runner.invoke(app, ["index-tree", str(root), "--cochange"]).exit_code == 0

    # Edit two files in the same folder within a short window
    for rel in ["folder_a/f1.txt", "folder_a/f2.txt"]:
        fp = root / rel
        fp.write_text(f"Updated content for {rel} with extra text.")
        new_mtime = _T0 + 200_000.0  # well after the cold run
        os.utime(fp, (new_mtime, new_mtime))

    result = runner.invoke(app, ["index-tree", str(root), "--cochange"])
    assert result.exit_code == 0, result.output

    store = _store(cli_db)
    conn = store.connect()
    # Check that at least one active memory now has changeset_kind=incremental
    row = conn.execute(
        "SELECT id FROM memories WHERE source='document' AND is_archived=0 "
        "AND json_extract(metadata, '$.changeset_kind') = 'incremental'"
    ).fetchone()
    assert row is not None, "Expected at least one 'incremental' changeset_kind after edit run"


def test_docs_changed_with_shows_kind(cli_db: Path, tmp_path: Path) -> None:
    """docs changed-with output includes the kind line."""
    sklearn = pytest.importorskip("sklearn")  # noqa: F841
    root = tmp_path / "corpus"
    _make_tree(root)

    assert runner.invoke(app, ["index-tree", str(root), "--cochange"]).exit_code == 0

    f1 = str(root / "folder_a/f1.txt")
    result = runner.invoke(app, ["docs", "changed-with", f1])
    assert result.exit_code == 0, result.output
    # kind should appear in output
    assert "kind:" in result.output or "cold_full_index" in result.output or "incremental" in result.output


def test_summary_table_shows_cochange_kind(cli_db: Path, tmp_path: Path) -> None:
    """index-tree summary table has a cochange_kind row."""
    sklearn = pytest.importorskip("sklearn")  # noqa: F841
    root = tmp_path / "corpus"
    _make_tree(root)

    result = runner.invoke(app, ["index-tree", str(root), "--cochange"])
    assert result.exit_code == 0, result.output
    assert "cochange_kind" in result.output
```

- [ ] **Step 6.2: Run to see failures**

```bash
uv run --no-sync pytest packages/cli/tests/test_index_tree_cochange_cli.py -v 2>&1 | tail -30
```

Expected: Several tests fail.

- [ ] **Step 6.3: Update `index_tree` in `cli/main.py`**

**6.3a: Import `IMAGE_SUFFIXES` and `ARTIFACT_SUFFIXES` at the right place.**

Inside the `index_tree` function body (where the existing `from mintmory.core.cochange import ...` line is, around line 535), add to the imports:

```python
    from mintmory.core.tree_index import ARTIFACT_SUFFIXES, IMAGE_SUFFIXES
```

**6.3b: Compute `was_cold` BEFORE the walk.**

Find where `store = _get_store()` and `run_cochange` are set (around line 550). After that block, add (before the `for root in roots:` loop):

```python
    # MM-34 E: determine run kind BEFORE the walk (cold = collection has no prior entries)
    was_cold = run_cochange and len(store.manifest_paths(collection)) == 0
    run_kind = "cold_full_index" if was_cold else "incremental"
```

**6.3c: Build the effective exclude set.**

After `run_kind = ...`, add:

```python
    # MM-34 B: build the effective co-change exclude set
    _cochange_exclude: frozenset[str] = frozenset()
    if run_cochange:
        if settings.doc.cochange_exclude_images:
            _cochange_exclude |= IMAGE_SUFFIXES
        if settings.doc.cochange_exclude_artifacts:
            _cochange_exclude |= ARTIFACT_SUFFIXES
        _cochange_exclude |= settings.doc.cochange_exclude_suffixes
```

**6.3d: Skip image/artifact suffixes when collecting `ChangedDoc`.**

Find the co-change collection block (around line 822):

```python
                # Co-change: collect this doc for cluster_changesets
                if run_cochange:
```

Change it to:

```python
                # Co-change: collect this doc for cluster_changesets
                # MM-34 B: skip excluded suffixes (images/artifacts/custom)
                if run_cochange and entry.suffix not in _cochange_exclude:
```

**6.3e: Add `record_role="file"` to file-record write.**

Find the `file_record = store.add_memory(...)` call (around line 652). Add `"record_role": "file"` to its metadata dict:

```python
                    metadata={
                        "collection": collection,
                        "path": path_str,
                        "rel": entry.rel,
                        "ext": entry.suffix,
                        "size": entry.size,
                        "mtime": entry.mtime,
                        "online_only": entry.online_only,
                        "folder": str(Path(entry.rel).parent),
                        "index_mode": "metadata",
                        "modified_source": "fs_mtime",
                        "record_role": "file",  # MM-34 D
                    },
```

**6.3f: Add recency + `record_role="chunk"` to body chunks.**

Find the chunk `crec = store.add_memory(...)` call inside `do_content` (around line 687). Add `valid_from=file_mtime_dt` and update metadata:

```python
                            crec = store.add_memory(
                                content=chunk,
                                category="fact",
                                source="document",
                                valid_from=file_mtime_dt,  # MM-34 D
                                metadata={
                                    "collection": collection,
                                    "source_file": path_str,
                                    "rel": entry.rel,
                                    "chunk": i,
                                    "converter": result.method,
                                    "modified_source": "fs_mtime",  # MM-34 D
                                    "record_role": "chunk",  # MM-34 D
                                },
                            )
```

**6.3g: Update the co-change post-walk pass.**

Find the block at around line 867:

```python
    if run_cochange and len(changed_docs) >= 2:
        from mintmory.core.cochange import apply_changesets

        try:
            sets = cluster_changesets(changed_docs, settings.doc)
            n_changesets = apply_changesets(store, sets)
            n_co_changed_files = sum(len(cs.member_ids) for cs in sets)
        except CoChangeUnavailable:
            ...
```

Replace with:

```python
    # Co-change post-walk pass — MM-34: result is CoChangeResult, not list[ChangeSet]
    n_changesets = 0
    n_co_changed_files = 0
    dropped_oversized = 0
    dropped_singletons = 0
    if run_cochange and len(changed_docs) >= 2:
        from mintmory.core.cochange import apply_changesets

        try:
            co_result = cluster_changesets(changed_docs, settings.doc, run_kind=run_kind)
            n_changesets = apply_changesets(store, co_result.changesets)
            n_co_changed_files = sum(len(cs.member_ids) for cs in co_result.changesets)
            dropped_oversized = co_result.dropped_oversized
            dropped_singletons = co_result.dropped_singletons
        except CoChangeUnavailable:
            console.print(
                "[dim]co-change skipped: install the 'cochange' extra "
                "(pip install mintmory[cochange])[/dim]"
            )
```

**6.3h: Update the summary table.**

Find the summary table block (around line 880):

```python
    if run_cochange:
        table.add_row("changesets", str(n_changesets))
        table.add_row("co_changed_files", str(n_co_changed_files))
```

Replace with:

```python
    if run_cochange:
        table.add_row("changesets", str(n_changesets))
        table.add_row("co_changed_files", str(n_co_changed_files))
        table.add_row("cochange_kind", run_kind)  # MM-34 E
        if dropped_oversized:
            table.add_row("dropped_oversized", str(dropped_oversized))
        if dropped_singletons:
            table.add_row("dropped_singletons", str(dropped_singletons))
```

**6.3i: Update `docs changed-with` to print kind.**

In `docs_changed_with`, update the peer printing loop. Add a `kind` column to the table and print it:

```python
    table = Table(title=f"Co-changed with: {path}")
    table.add_column("peer path", style="white")
    table.add_column("strength", justify="right", style="green")
    table.add_column("observed at", style="cyan")
    table.add_column("kind", style="magenta")  # MM-34 E
    for peer in peers:
        kind_str = peer.get("kind", "")
        if kind_str == "cold_full_index":
            kind_str = "cold_full_index (co-location-dominated)"
        table.add_row(
            peer["path"],
            f"{peer['strength']:.3f}",
            peer["observed_at"],
            kind_str,
        )
    console.print(table)
    # MM-34 E: surface kind summary after table
    if peers:
        first_kind = peers[0].get("kind", "")
        console.print(f"[dim]kind: {first_kind}[/dim]")
```

- [ ] **Step 6.4: Run CLI tests**

```bash
uv run --no-sync pytest packages/cli/tests/test_index_tree_cochange_cli.py -v 2>&1 | tail -40
```

Expected: All pass (including existing tests — they need updating to use `co_result.changesets` pattern, but they call the CLI not the Python API directly, so they should mostly still work once the CLI reads `result.changesets`).

---

## Task 7: Run All Gates

- [ ] **Step 7.1: ruff check**

```bash
uv run --no-sync ruff check packages 2>&1 | tail -20
```

Expected: No errors. Fix any flagged issues (common: lambda in closure needs `default=` capture for closure variable, long lines).

- [ ] **Step 7.2: ruff format**

```bash
uv run --no-sync ruff format packages 2>&1
```

Expected: "All files reformatted" or "N files left unchanged."

- [ ] **Step 7.3: mypy**

```bash
uv run --no-sync mypy packages/core/src packages/cli/src 2>&1 | tail -30
```

Expected: 0 errors. Common issues to pre-empt:
- `strength_fn: Any` — the callable in `_build_changeset` should be typed as `Callable[[int, int], float]`; import from `collections.abc`.
- `CoChangeResult` is a non-frozen dataclass; mypy --strict will accept it but verify fields are annotated.
- `_settings_mm34` helper in tests uses `object` return type — this is fine for tests with `# type: ignore`.

To use `Callable`, add to cochange.py imports:
```python
from collections.abc import Callable
```
And change the `strength_fn` parameter type:
```python
    strength_fn: Callable[[int, int], float],
```

- [ ] **Step 7.4: pytest**

```bash
uv run --no-sync pytest packages/core packages/cli -q 2>&1 | tail -30
```

Expected: All pass, >= 80% coverage.

- [ ] **Step 7.5: openspec validate**

```bash
uv run --no-sync openspec validate improve-document-cochange-quality --strict 2>&1
```

Expected: validation passes.

---

## Task 8: Fix Any Issues Found

- [ ] **Step 8.1: Fix closure capture in `_changesets_from_labels`**

The lambda `_strength` inside the for-loop captures `orig_indices`, `group`, and `probs` by reference, which is safe here because each lambda is used immediately (not stored). However, mypy may complain about the `_g` default trick in the test. Use a proper function:

In `_changesets_from_labels`, replace the inline `_strength` lambda approach with:

```python
            # Build probability lookup by doc_id
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

            cs = _build_changeset(group, strength_fn=_make_strength(group, prob_by_docid), run_kind=run_kind)
```

- [ ] **Step 8.2: Re-run all gates and confirm green**

```bash
uv run --no-sync ruff check packages && \
uv run --no-sync ruff format --check packages && \
uv run --no-sync mypy packages/core/src packages/cli/src && \
uv run --no-sync pytest packages/core packages/cli -q 2>&1 | tail -20
```

---

## Self-Review: Spec Coverage Check

| Spec requirement | Task covering it |
|---|---|
| A. Time-gap split — `_split_on_time_gap`, post-cluster | Task 3 (cochange.py), Task 4 (tests) |
| B. Cluster-size cap (>50 dropped) | Task 3 (cochange.py `_changesets_from_labels`) |
| B. Type exclusion — IMAGE_SUFFIXES, ARTIFACT_SUFFIXES in CLI filter | Task 2 (tree_index.py), Task 6 (CLI) |
| D. Body-chunk recency (`valid_from`, `modified_source`, `record_role`) | Task 6 (CLI) |
| D. `documents_timeline` NULL-safe chunk filter | Task 5 (cochange.py), Task 5 (tests) |
| E. `kind` on ChangeSet, `changeset_kind` in metadata | Task 3 (ChangeSet field), Task 5 (`apply_changesets`) |
| E. `was_cold` logic in CLI | Task 6 (CLI) |
| E. `cochange_kind` row in summary table | Task 6 (CLI) |
| E. `changed_with` returns `kind` | Task 5 (cochange.py), Task 5 (tests) |
| E. `docs changed-with` prints kind | Task 6 (CLI) |
| F. `_connected_components` union-find (no sklearn) | Task 3 (cochange.py) |
| F. `_changesets_from_components` | Task 3 (cochange.py) |
| F. Fallback when n<=max_n (skip HDBSCAN) | Task 3 (cluster_changesets) |
| F. Fallback when all-noise (HDBSCAN then components) | Task 3 (cluster_changesets) |
| F. Fallback passes through gap-split + size-cap | Task 4 (tests) |
| Config: all 9 new knobs | Task 1 (config.py) |
| `CoChangeResult` return type | Task 3 |
| Tests: gap-split, size-cap, kind, fallback | Tasks 3/4 |
| Tests: config knob bounds + suffix parsing | Task 1 |
| Tests: chunk exclusion from timeline | Task 5 |
| Tests: cold/incremental CLI end-to-end | Task 6 |
| Tests: image exclusion CLI | Task 6 |
| Existing tests updated (result.changesets, ChangeSet.kind) | Task 3/5/6 |

All requirements covered. No deviations from spec.

---

Plan complete and saved to `docs/superpowers/plans/2026-06-22-mm-34-improve-cochange-quality.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — dispatches a fresh subagent per task, review between tasks, fast iteration loop

**2. Inline Execution** — executes tasks in this session using executing-plans skill with checkpoints

Which approach?
