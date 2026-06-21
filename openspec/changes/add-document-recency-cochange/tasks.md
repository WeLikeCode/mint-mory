# Tasks: Document recency + co-change index (MM-33)

## 1. Config
- [ ] Add `DocumentSettings` to `core/config.py` (fields per design §1) and wire
  `doc: DocumentSettings` into `Settings` (env prefix `MINTMORY_DOC_`).
- [ ] Tests: defaults + bounds (`test_config.py`).

## 2. Pure clustering core — `core/cochange.py`
- [ ] `ChangedDoc`, `ChangeSet` dataclasses (design §2).
- [ ] `cluster_changesets(docs, settings)`: sort-first determinism; precomputed
  composite distance (time/path/content, normalised `[0,1]`, content dropped when
  no embedding); lazy `sklearn.cluster.HDBSCAN(metric="precomputed")`; noise
  excluded; `probabilities_` → edge strength; deterministic `changeset_id`.
- [ ] Tests `test_cochange.py`: clustering, noise singleton, determinism,
  normalisation bounds, weight effects, no-embedding fallback, `<2` docs → `[]`.

## 3. Store application + read queries — `core/cochange.py`
- [ ] `apply_changesets(store, sets)`: merge `changeset_id`/`observed_at`/`method`
  via `update_memory`; write `relates_to` (entity=`changeset:<id>`, strength,
  source=`inference`) + `before` edges; idempotent (delete prior `changeset:<id>`
  edges first); scoped to the given member ids only.
- [ ] `changed_with(store, path)` and `documents_timeline(store, ...)`, both
  filtered to `source='document'` (+ optional collection).
- [ ] Tests: apply is idempotent and scoped; queries return expected rows/order.

## 4. CLI — recency + co-change pass + `docs` commands (`cli/main.py`)
- [ ] In `index-tree`: set `valid_from` = mtime (naive-UTC) + `modified_source`
  on file-record writes/updates (additive).
- [ ] Collect `ChangedDoc` for each added/updated file (memory_id, path, rel,
  mtime, embedding via store embedder or None).
- [ ] `--cochange/--no-cochange` flag (default `settings.doc.cochange_enabled`):
  post-walk `cluster_changesets` + `apply_changesets`; report `changesets` +
  `co_changed_files`; missing-extra → one-line install hint, continue.
- [ ] New `docs` Typer sub-app: `docs timeline` (newer→older) and
  `docs changed-with <path>` (peers + strength + observed time + honesty label).
- [ ] Tests `test_index_tree_cochange.py`: valid_from set; two bursts → two
  change-sets + edges; idempotent re-run; non-document memory untouched;
  `changed-with`/`docs timeline` rows. sklearn-gated tests `skip` if extra absent.

## 5. Dependency + docs
- [ ] Add `cochange = ["scikit-learn>=1.3"]` optional extra to
  `packages/core/pyproject.toml`.
- [ ] README/onboarding note: `pip install mintmory[cochange]` for co-change;
  recency works without it; document the honest-limit wording.

## 6. Gates
- [ ] `ruff` + `ruff format` clean; `mypy --strict` clean.
- [ ] `pytest` ≥ 80% coverage; full suite green.
- [ ] `openspec validate add-document-recency-cochange --strict`.
