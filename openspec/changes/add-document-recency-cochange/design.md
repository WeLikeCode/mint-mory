# Design: Document recency + co-change index (MM-33)

Builds on the existing `index-tree` command (`cli/main.py`), `tree_index.py`
(stat-only OneDrive-safe walk → `FileEntry{path,rel,size,mtime,online_only}`), the
`index_manifest` change-detection, and `concept_links`. No new walk/diff code.

## 1. `core/config.py` — `DocumentSettings`

New `BaseSettings` group `doc` (env prefix `MINTMORY_DOC_`), added to `Settings`:

```python
class DocumentSettings(BaseSettings):
    cochange_enabled: bool = True                       # run the co-change pass when possible
    weight_time: float = Field(default=1.0, ge=0.0)     # composite-distance weights
    weight_path: float = Field(default=0.5, ge=0.0)
    weight_content: float = Field(default=0.5, ge=0.0)
    tau_seconds: int = Field(default=3600, ge=1)        # time-delta normalisation scale
    min_cluster_size: int = Field(default=2, ge=2)      # HDBSCAN; <2 is meaningless
    use_embeddings: bool = True                          # include content dimension
```

## 2. `core/cochange.py` (new) — pure clustering + planning + queries

**Pure clustering (no store, no network — the testable core).**

```python
@dataclass(frozen=True)
class ChangedDoc:
    memory_id: str        # the file-record memory id (the co-change node)
    doc_id: str           # stable id = absolute path
    rel: str              # root-relative POSIX path (for path distance)
    mtime: float          # epoch seconds
    embedding: NDArray[np.float32] | None   # file-record / content embedding

@dataclass(frozen=True)
class ChangeSet:
    changeset_id: str           # deterministic: sha1(sorted doc_ids + max mtime)[:16]
    member_ids: list[str]       # memory ids, sorted
    observed_at: str            # ISO-8601 naive-UTC (max mtime in cluster)
    edges: list[tuple[str, str, float]]   # (src_id, dst_id, strength) pairwise within cluster
    order: list[str]            # member ids sorted by mtime (for 'before' edges)

def cluster_changesets(docs: list[ChangedDoc], s: DocumentSettings) -> list[ChangeSet]: ...
```

Algorithm:
1. If `len(docs) < 2` or `not s.cochange_enabled` → return `[]`.
2. **Sort `docs` by (mtime, doc_id)** first — makes HDBSCAN border-point assignment
   and the `changeset_id` deterministic across re-runs (idempotency).
3. Build a precomputed N×N distance matrix `D`, each term normalised to `[0,1]`:
   - `time(a,b) = min(1.0, |mtime_a − mtime_b| / s.tau_seconds)`
   - `path(a,b) = (depth_a + depth_b − 2·common_prefix_len) / max(1, depth_a + depth_b)`
     where depth/prefix are over `rel` split on `/` (parent dirs only).
   - `content(a,b) = (1 − cosine(emb_a, emb_b)) / 2`; if either embedding is `None`
     or `not s.use_embeddings`, the content term is dropped and its weight removed
     from the denominator.
   - `D[a,b] = (w_t·time + w_p·path + w_c·content) / (w_t + w_p + w_c_effective)`.
4. `HDBSCAN(metric="precomputed", min_cluster_size=s.min_cluster_size).fit(D)`.
   `labels_` (−1 = noise → excluded), `probabilities_` → edge `strength`
   (`min(prob_a, prob_b)`, clamped to `[0,1]`).
5. Per cluster label ≥ 0: build a `ChangeSet` (deterministic id, members, pairwise
   `relates_to` edges, `before` order by mtime). Noise points yield no change-set.

`scikit-learn`'s `HDBSCAN` is imported **lazily inside** `cluster_changesets`; if the
import fails the caller (CLI) reports the `cochange` extra install hint and skips —
recency is unaffected.

**Store application + read queries (thin I/O wrappers, scoped to documents).**

```python
def apply_changesets(store, sets: list[ChangeSet], method: str = "hdbscan") -> int:
    # For each member: merge metadata.changeset_id/observed_at/method via update_memory.
    # For each edge: store link relates_to (entity=f"changeset:{id}", strength, source="inference")
    #   and 'before' edges along `order`. Idempotent: delete prior changeset:<id> edges first.

def changed_with(store, path: str) -> list[dict]:   # cluster peers of a doc, with strength + observed_at
def documents_timeline(store, *, since=None, from_iso=None, to_iso=None,
                       collection=None, limit=50) -> list[dict]:  # newer→older docs by valid_from
```

`changed_with`/`documents_timeline` filter `source = 'document'` (and optional
`collection`) so they never surface non-document memories.

## 3. `cli/main.py` — `index-tree` co-change pass + recency

- **Recency (in the existing per-file write):** set
  `valid_from = datetime.fromtimestamp(entry.mtime, tz=UTC).replace(tzinfo=None)`
  and `metadata["modified_source"] = "fs_mtime"` on the file-record `add_memory`
  (and on the `update_memory` for changed files). Additive only.
- **Collect changed docs:** during the walk, append a `ChangedDoc` for every file
  counted as `added` or `updated` (content actually changed), capturing the
  file-record `memory_id`, path, `rel`, `mtime`, and an embedding
  (`store`'s embedder over the file-record/content text; `None` if unavailable).
- **Post-walk pass:** new `--cochange/--no-cochange` flag (default
  `settings.doc.cochange_enabled`). If enabled and ≥2 changed docs:
  `sets = cluster_changesets(changed, settings.doc)` then
  `apply_changesets(store, sets)`. Report `changesets` + `co_changed_files` counts.
  If the `cochange` extra is missing, print the one-line install hint and continue.
- **New `docs` Typer sub-app:**
  - `docs timeline [--since/--from/--to] [--collection] [--limit] [--db]` →
    `documents_timeline(...)`, newest-first, columns date/collection/path/title.
  - `docs changed-with <path> [--db]` → `changed_with(...)`; each row shows the peer
    path, edge strength, observed time, and the honesty label
    `"observed co-change (time+folder+content); not a version-controlled commit"`.

## 4. Storage target & safety

`index-tree` already targets the working store by default and honours `--db`
(separate DB optional) — this satisfies the storage decision with no change. The
co-change pass operates **only** on the run's changed `source="document"` records;
`apply_changesets` updates only those memory ids and writes edges only among them.
No working-store memory outside the document set is ever read or modified. (A
manual `hermes.db` backup is taken operationally before first run.)

## 5. Dependency — optional `cochange` extra

`packages/core/pyproject.toml`:
```toml
[project.optional-dependencies]
cochange = ["scikit-learn>=1.3"]   # HDBSCAN; ADR-0004: heavy deps stay opt-in
```
`numpy` is already a core dep. Co-change is enabled-by-default in config but a
no-op-with-hint when `scikit-learn` is absent, so the base install stays light.

## 6. Honest limits

- Co-change precision is bounded by run cadence and by the weights; it is "observed
  co-change," never an atomic commit. Singletons are noise, not change-sets.
- `modified_source = "fs_mtime"` marks recency as heuristic (mtime can be reset by
  copies/sync/restore); a future Graph tier would be authoritative.

## 7. Testing

- **`test_cochange.py` (pure):** two temporally+topically distinct bursts → two
  change-sets; a lone edit → noise (no change-set); deterministic `changeset_id`
  across re-runs; distance-term normalisation bounds `[0,1]`; weight effects;
  no-embedding fallback (content term dropped); `<2` docs → `[]`.
- **`test_index_tree_cochange.py` (integration, temp dir):** `valid_from` = mtime
  set; two edit bursts → two change-sets + `relates_to`/`before` edges; unchanged
  re-run → no new change-sets (idempotent); a pre-existing non-document memory in
  the store is untouched (scope safety); `changed-with`/`docs timeline` return the
  expected rows. (sklearn-gated tests `skip` if the extra is absent in CI.)
