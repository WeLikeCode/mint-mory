# Design: Improve document co-change quality (MM-34)

Builds on MM-33 (`core/cochange.py`, `core/config.py` `DocumentSettings`,
`cli/main.py` `index-tree` co-change pass + `docs` sub-app, `core/tree_index.py`
suffix sets). No new walk/diff machinery; the existing precomputed-distance +
HDBSCAN core is reused. Every change here operates on the run's changed
`source="document"` records only.

## 0. Live-run evidence (motivating numbers)

| Symptom | Observed | Root cause |
|---|---|---|
| 6.5-yr change-set | 1 set spans 2391 days, 10 files | path_dist=0 + weak content term; time term cannot split |
| 890-file change-set | timelapse `.jpg` dump at one instant | binary/image types + bulk write |
| co-location not co-change | 93% single-folder, median span 0 days | cold index: all files "new", OneDrive sync-stamps |
| chunks lack recency | body chunks have no `valid_from` | MM-33 only stamps the file-record |

## 1. `core/config.py` — new `DocumentSettings` knobs

Added to the existing group (env prefix `MINTMORY_DOC_`):

```python
# A — hard time-gap guard (post-cluster split)
max_cochange_gap_seconds: int = Field(default=86_400, ge=1)   # 24h; adjacent gap > this splits a cluster
# B — cluster-size cap + non-knowledge exclusion
max_cochange_cluster_size: int = Field(default=50, ge=2)      # drop change-sets larger than this
cochange_exclude_images: bool = True                          # drop image suffixes from co-change
cochange_exclude_artifacts: bool = True                       # drop ARTIFACT_SUFFIXES from co-change
cochange_exclude_suffixes_csv: str = ""                       # extra suffixes to exclude (".log,.tmp")
# E — cold/incremental honesty
cochange_label_kind: bool = True                              # tag change-sets cold_full_index vs incremental
# F — hybrid small-N / all-noise fallback (live-run finding: HDBSCAN returns 0
#     change-sets for a normal incremental edit of a few files — density model needs
#     contrast a small batch lacks)
cochange_fallback_enabled: bool = True                        # use connected-components fallback
cochange_fallback_max_n: int = Field(default=8, ge=2)         # <=N OR all-noise -> fallback
cochange_distance_eps: float = Field(default=0.35, ge=0.0, le=1.0)  # single-linkage cutoff
```

`cochange_exclude_suffixes` is a parsed property mirroring `ConversionSettings.extra_text_suffixes`
(lowercase, single leading dot, blanks dropped). Bounds chosen so each default
either *tightens* (gap/cap/exclude — intentional behaviour change to fix the bugs)
or is purely additive (label). Defaults are opinionated, not no-ops: MM-33's output
was wrong, so the safe default is the corrected behaviour, documented in the
proposal.

**Why 86_400 / 50.** 24h spans a realistic multi-session edit day while excluding
the 6.5-yr and most cold-sync blobs; 50 is well above any plausible single logical
edit (a refactor touching dozens of files) yet two orders of magnitude below the
890-file dump. Both are env-overridable.

## 2. `core/tree_index.py` — image suffix set

Add a shared frozenset next to `ARTIFACT_SUFFIXES`:

```python
IMAGE_SUFFIXES: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp",
     ".heic", ".heif", ".raw", ".cr2", ".nef", ".psd", ".ico"}
)
```

(`.svg` is intentionally NOT excluded — it carries extractable text and is a
vision/knowledge candidate.) This set is used by the CLI to filter the co-change
collection; it does not affect indexing/recency/vision.

## 3. `core/cochange.py` — A (time-gap split) + B (size cap) + E (kind tag)

### A. Post-cluster time-gap split — the mechanism, and why not pre-cluster

**Rejected: pre-cluster distance clamp.** Forcing `D[a,b] = 1.0` (or `inf`) when
`|Δt| > gap` does NOT forbid co-change. HDBSCAN is density-based: it builds a
mutual-reachability minimum spanning tree, so two files a decade apart can still
land in one cluster if a *chain* of intermediate-dated files connects them (each
adjacent hop under the gap). `inf`/`nan` are additionally illegal in a
`metric="precomputed"` matrix. A clamp therefore changes densities unpredictably
and is non-deterministic w.r.t. the invariant we actually want.

**Chosen: deterministic post-cluster split.** After `_changesets_from_labels`
produces raw clusters, run `_split_on_time_gap(cluster_docs, gap)`:

1. Sort the cluster's docs by `(mtime, doc_id)` (already the global sort order).
2. Walk adjacent pairs; start a new sub-group whenever
   `docs[i].mtime - docs[i-1].mtime > gap`.
3. Each sub-group with `len >= min_cluster_size` becomes its own `ChangeSet`
   (fresh deterministic `changeset_id` over its own member doc_ids + its own max
   mtime). Sub-groups below `min_cluster_size` are discarded (treated as noise).

**Invariant guaranteed:** every emitted change-set has all adjacent internal mtime
gaps `<= max_cochange_gap_seconds`, hence total span `<=`
`(members-1) * gap` and — more importantly — no two *adjacent-in-time* members are
farther apart than the gap. This is a hard guard independent of path/content
weights, which is exactly what finding A needs. It is fully deterministic (pure
function of sorted mtimes + the threshold).

Applied to the live data: the 10-file 6.5-yr set fragments at each multi-month gap;
each fragment is almost always a singleton or a sub-`min_cluster_size` group, so it
is dropped — the bogus change-set disappears.

### B. Cluster-size cap

After the time-gap split (so we cap on *real* candidate change-sets, not the raw
HDBSCAN blob), drop any `ChangeSet` whose `len(member_ids) > max_cochange_cluster_size`.
Return a structured result so the CLI can warn:

```python
@dataclass(frozen=True)
class CoChangeResult:
    changesets: list[ChangeSet]
    dropped_oversized: int      # count of clusters dropped for size
    dropped_singletons: int     # sub-groups dropped after the gap split
```

`cluster_changesets` returns `CoChangeResult` (was `list[ChangeSet]`). **This is a
signature change** — `apply_changesets` and the CLI are updated to read
`result.changesets`. Drop (not split, not keep) is correct: an oversized group has
no internal signal to split meaningfully (the gap split already ran), and keeping it
pollutes every member's `changed-with`. Type exclusion happens upstream (CLI, §5) so
oversized drops here are the residual large *same-type same-window* blobs.

### E. Cold/incremental kind tag

`cluster_changesets` gains a `run_kind: str` parameter (`"cold_full_index"` |
`"incremental"`), threaded into each `ChangeSet` as a new field `kind: str`.
`apply_changesets` writes `metadata.changeset_kind = cs.kind` on each member and
tags the `concept_links.entity` unchanged. Default `run_kind="incremental"` keeps
callers that omit it on the honest-but-conservative side. The CLI decides the kind
(see §5).

### Idempotency & determinism

The split produces a *different* `changeset_id` per fragment, but since each id is a
pure function of `(sorted member doc_ids, max mtime)`, re-running on the same inputs
yields identical ids — `apply_changesets`' delete-by-entity idempotency still holds.
Determinism of the split itself is guaranteed by the existing `(mtime, doc_id)`
global sort.

### F. Hybrid small-N / all-noise fallback — the live-run fix

**Live-run finding.** HDBSCAN returns ZERO change-sets for the feature's primary use
case: editing 4 tightly-related files in one folder at one moment gave pairwise
distances ~0.03 (an obvious single group) yet HDBSCAN labelled all four noise
(`[-1,-1,-1,-1]`). HDBSCAN's density/min-samples machinery refuses to declare a
cluster without density *contrast*, which a small uniform edit batch lacks. The
post-cluster guards (A/B) cannot help because HDBSCAN produces nothing to guard.

**Decision (user): keep HDBSCAN, add a fallback** (do not replace HDBSCAN — it still
works on large corpora with density variation).

**Mechanism.** In `cluster_changesets`, after building the distance matrix:
1. If `cochange_fallback_enabled` and `n <= cochange_fallback_max_n` (default 8):
   skip HDBSCAN, go straight to connected-components (HDBSCAN is unreliable here).
2. Else run HDBSCAN as today. If it yields **zero** clusters (every label == −1) and
   the fallback is enabled, run connected-components on the same matrix.
3. **Connected-components (single-linkage at `eps`):** union-find over all pairs with
   `D[i,j] <= cochange_distance_eps`; each component with `>= min_cluster_size`
   members is a candidate cluster. Membership probability is unavailable, so edge
   `strength` for fallback clusters is `1.0` (clamped). Deterministic: the global
   `(mtime, doc_id)` sort fixes union order and component membership.
4. Candidate clusters from EITHER path are then fed through the SAME
   `_split_on_time_gap` (A) and size cap (B), so all invariants (no over-gap span, no
   oversized blob) still hold.

`_changesets_from_labels` is reused for the HDBSCAN path; a sibling
`_changesets_from_components(sorted_docs, components)` builds the fallback clusters
into the same raw-cluster form before A/B. `CoChangeResult` gains nothing new; the
CLI may optionally report whether the fallback fired.

**Why eps=0.35.** Tight same-folder/same-window edits measure ~0.03–0.13; cross-folder
or cross-day pairs exceed ~0.3 (live data). 0.35 unions real edit batches while
keeping unrelated files apart, and the time-gap split (A) still guards any chain that
slips through. Env-overridable.

**Determinism & idempotency.** Connected components over a fixed-threshold symmetric
matrix with a fixed node order are deterministic; `changeset_id` remains a pure
function of member doc_ids + max mtime, so `apply_changesets` idempotency holds.

## 4. `core/cochange.py` — D is CLI-side, but the query honours roles

Body-chunk recency is stamped in the CLI (§5). To keep `documents_timeline` showing
one row per file (not one per chunk), the file-record is marked
`metadata.record_role = "file"` and body chunks `record_role = "chunk"`;
`documents_timeline` adds `AND json_extract(metadata,'$.record_role') != 'chunk'`
(NULL-safe: legacy file-records without the key still match, since `!= 'chunk'`
returns NULL→excluded — so we use
`(json_extract(...) IS NULL OR json_extract(...) != 'chunk')`). `changed_with` is
unaffected (it keys on `changeset_id`, which chunks never carry).

## 5. `cli/main.py` — collection filter (B), chunk recency (D), run kind (E)

- **B (collection filter).** When appending a `ChangedDoc`, skip the file when its
  suffix is in the effective exclude set:
  `IMAGE_SUFFIXES` (if `cochange_exclude_images`) ∪ `ARTIFACT_SUFFIXES` (if
  `cochange_exclude_artifacts`) ∪ `doc.cochange_exclude_suffixes`. The file-record
  and any body chunks are still written with full recency — only co-change skips it.
- **D (chunk recency).** In the body-chunk `add_memory` (currently no `valid_from`),
  pass `valid_from=file_mtime_dt` and add `metadata.modified_source = "fs_mtime"`,
  `metadata.record_role = "chunk"`. Add `metadata.record_role = "file"` to the
  file-record write. Additive.
- **E (run kind).** Before the walk, capture
  `was_cold = len(store.manifest_paths(collection)) == 0`; pass
  `run_kind="cold_full_index" if was_cold else "incremental"` to
  `cluster_changesets`. Print it in the index-tree summary table
  (`cochange_kind` row) and in `docs changed-with` (a line:
  `kind: cold_full_index (co-location-dominated)` vs `kind: incremental`).
- **Result plumbing.** `cluster_changesets` now returns `CoChangeResult`; the CLI
  reads `.changesets`, sums `co_changed_files` from those, and prints
  `dropped_oversized`/`dropped_singletons` as extra summary rows when non-zero.
- **changed-with output (E).** Surface the kind from any peer's
  `metadata.changeset_kind` so the user sees whether the grouping came from a cold
  bulk index (co-location-dominated) or an incremental edit.

## 6. Edge cases

- **Gap split yields zero valid sub-groups** (every fragment below
  `min_cluster_size`): the original cluster contributes no change-set;
  `dropped_singletons` counts the discarded fragments.
- **All changed files excluded by type** (e.g. a pure image dump): `changed_docs` is
  empty/`<2` → `cluster_changesets` returns an empty `CoChangeResult`; no error.
- **Oversized cluster that the gap split could not break** (e.g. 200 files written
  within one 24h window, same type): dropped by the size cap with a warning; this is
  the residual cold-sync blob and is correctly excluded.
- **Mixed legacy store** (MM-33 file-records without `record_role`): timeline query
  uses the NULL-safe predicate so they still appear.
- **`max_cochange_cluster_size` set below a real cluster** by an aggressive operator:
  documented that legitimate large edits can be dropped; the warning names the count.

## 7. Testing

- **`test_cochange.py` (pure):**
  - gap split: a single HDBSCAN cluster with an internal 2-year gap splits into the
    two dense sub-groups; a sub-group below `min_cluster_size` is dropped
    (`dropped_singletons` incremented); resulting change-sets have all adjacent
    gaps `<= gap`.
  - deterministic `changeset_id` for each fragment across re-runs.
  - size cap: a 60-member cluster (all within the gap) is dropped, `dropped_oversized == 1`.
  - kind tag: `run_kind` is propagated to every `ChangeSet.kind` and to member metadata.
  - **fallback (F):** 4 tight files for which the HDBSCAN path is forced to all-noise
    still form one change-set via connected-components; `n <= fallback_max_n` skips
    HDBSCAN; two files beyond `eps` are not unioned (unless chained); fallback
    `changeset_id` is deterministic across re-runs; `_changesets_from_components`
    output passes the gap-split + size-cap.
- **`test_index_tree_cochange.py` (integration, temp dir, sklearn-gated):**
  - image/binary files are written with `valid_from` but never appear in a change-set
    or in `changed_with`.
  - body chunks carry `valid_from`/`modified_source`/`record_role="chunk"` and do
    NOT appear as separate rows in `docs timeline`.
  - a cold first index tags change-sets `cold_full_index`; a second incremental edit
    run tags new change-sets `incremental`.
  - the 6.5-yr-style scenario (two dense bursts + a stray old file in the same folder)
    yields only the dense change-set(s); the stray is not co-changed.
- **`test_config.py`:** new knob defaults + bounds; `cochange_exclude_suffixes`
  parsing.

## 8. Gates

`ruff` + `ruff format` clean; `mypy --strict` clean; `pytest >= 80%`; full suite
green; `openspec validate improve-document-cochange-quality --strict`.
