# Tasks: Improve document co-change quality (MM-34)

## 1. Config (`core/config.py`)
- [ ] Add to `DocumentSettings`: `max_cochange_gap_seconds` (default 86_400, ge=1),
  `max_cochange_cluster_size` (default 50, ge=2), `cochange_exclude_images`
  (default True), `cochange_exclude_artifacts` (default True),
  `cochange_exclude_suffixes_csv` (default ""), `cochange_label_kind` (default True).
- [ ] Add `cochange_exclude_suffixes` parsed property (lowercase, single leading
  dot, blanks dropped — mirror `ConversionSettings.extra_text_suffixes`).
- [ ] Add fallback knobs: `cochange_fallback_enabled` (default True),
  `cochange_fallback_max_n` (default 8, ge=2), `cochange_distance_eps`
  (default 0.35, ge=0.0, le=1.0).
- [ ] Tests (`test_config.py`): defaults, bounds, suffix parsing, fallback knobs.

## 2. Suffix set (`core/tree_index.py`)
- [ ] Add `IMAGE_SUFFIXES` frozenset (jpg/jpeg/png/gif/bmp/tiff/tif/webp/heic/heif/
  raw/cr2/nef/psd/ico; `.svg` deliberately excluded from the set).

## 3. Time-gap split + size cap + kind (`core/cochange.py`)
- [ ] Add `CoChangeResult` dataclass (`changesets`, `dropped_oversized`,
  `dropped_singletons`).
- [ ] Add `kind: str` field to `ChangeSet`.
- [ ] `_split_on_time_gap(cluster_docs, gap, min_size)`: sort by (mtime, doc_id),
  split on adjacent gap > `gap`, keep sub-groups with `len >= min_size`, drop the
  rest; return (sub-group lists, dropped count).
- [ ] Wire the split into `_changesets_from_labels` (or a wrapper) so each fragment
  gets its own deterministic `changeset_id` (sha1 over its own member doc_ids + its
  own max mtime).
- [ ] Apply the size cap AFTER the split: drop `ChangeSet`s with
  `len(member_ids) > max_cochange_cluster_size`, counting `dropped_oversized`.
- [ ] Thread `run_kind: str = "incremental"` through `cluster_changesets` into each
  `ChangeSet.kind`; change `cluster_changesets` return type to `CoChangeResult`.
- [ ] Tests (`test_cochange.py`): internal-gap split into two groups; sub-min-size
  fragment dropped; all emitted change-sets satisfy the adjacent-gap invariant;
  deterministic fragment ids across re-runs; 60-member cluster dropped
  (`dropped_oversized==1`); kind propagated.

## 3b. Hybrid small-N / all-noise fallback (`core/cochange.py`) — finding F
- [ ] `_connected_components(dist_matrix, eps, min_size)`: union-find over pairs with
  `D[i,j] <= eps`; return components with `>= min_size` members (deterministic node
  order = the global (mtime, doc_id) sort).
- [ ] `_changesets_from_components(sorted_docs, components, ...)`: build raw clusters
  into the same form `_changesets_from_labels` produces (fallback edge strength=1.0).
- [ ] In `cluster_changesets`: if `cochange_fallback_enabled` and
  `n <= cochange_fallback_max_n` → skip HDBSCAN, use components; else run HDBSCAN and
  if it returns ZERO clusters (all-noise) and fallback enabled → use components on the
  same matrix. Feed component clusters through the SAME gap-split (A) + size cap (B).
- [ ] Tests (`test_cochange.py`): 4 tight files where HDBSCAN is forced/known to
  produce all-noise still form one change-set via the fallback; `n <= fallback_max_n`
  takes the fallback path; two files beyond `eps` are not unioned (unless chained);
  fallback `changeset_id` deterministic across re-runs; component clusters still obey
  the gap-split + size cap.

## 4. Apply + query (`core/cochange.py`)
- [ ] `apply_changesets`: write `metadata.changeset_kind = cs.kind`; read
  `result.changesets`; remain idempotent (delete-by-entity unchanged).
- [ ] `documents_timeline`: add NULL-safe `record_role != 'chunk'` predicate so
  body chunks never appear as timeline rows; legacy file-records (no `record_role`)
  still appear.
- [ ] `changed_with`: include `kind` (from peer `metadata.changeset_kind`) in each
  returned row.
- [ ] Tests: chunks excluded from timeline, legacy rows still shown; `changed_with`
  returns `kind`.

## 5. CLI (`cli/main.py`)
- [ ] Co-change collection filter: skip appending a `ChangedDoc` when the suffix is
  in the effective exclude set (`IMAGE_SUFFIXES` if `cochange_exclude_images` ∪
  `ARTIFACT_SUFFIXES` if `cochange_exclude_artifacts` ∪
  `doc.cochange_exclude_suffixes`). File-record + chunks still written.
- [ ] Body-chunk recency: pass `valid_from=file_mtime_dt`,
  `metadata.modified_source="fs_mtime"`, `metadata.record_role="chunk"`; add
  `metadata.record_role="file"` to the file-record write.
- [ ] Run kind: compute `was_cold = len(store.manifest_paths(collection)) == 0`
  before the walk; pass `run_kind` to `cluster_changesets`; read `.changesets`.
- [ ] Summary table: add `cochange_kind`, and `dropped_oversized`/
  `dropped_singletons` rows when non-zero.
- [ ] `docs changed-with`: print the change-set kind line
  (`cold_full_index (co-location-dominated)` vs `incremental`).
- [ ] Tests (`test_index_tree_cochange.py`, sklearn-gated): excluded image/binary
  files get recency but no change-set/peers; chunks have recency and are absent from
  timeline; cold run tags `cold_full_index`, incremental run tags `incremental`;
  stray-old-file-in-folder is not co-changed.

## 6. Docs
- [ ] Update README/onboarding co-change note: gap guard, size cap, type exclusion,
  cold-vs-incremental labelling, and the new `MINTMORY_DOC_*` knobs.

## 7. Gates
- [ ] `ruff` + `ruff format` clean; `mypy --strict` clean.
- [ ] `pytest` >= 80% coverage; full suite green.
- [ ] `openspec validate improve-document-cochange-quality --strict`.
