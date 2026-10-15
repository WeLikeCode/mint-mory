# Change: Document recency + co-change index (MM-33)

## Why

MintMory can ingest documents (`mintmory index-tree`, OneDrive-safe stat-only walk
into `index_manifest` + memories), but it cannot answer two questions users ask of
a non-git-versioned corpus (OneDrive, local folders, network shares):

1. **Recency** — "which document is newer / older?"
2. **Co-change** — "which documents were changed together?"

Git makes both trivial (a commit is an atomic, timestamped change-set). Without
version control we must derive them:

- Recency is a per-file scalar. `index-tree` already captures the file's `mtime`
  in metadata but does **not** set `valid_from`, so the time-ordered queries that
  already exist for agent-history don't work for documents.
- Co-change is fundamentally **unknowable** without VCS — there is no atomic
  change-set. The honest best is to **observe** it: each `index-tree` run already
  diffs content hashes against the manifest, so the set of files whose content
  changed in a run is a *manufactured change-set*. Raw "everything changed since
  last run" is too coarse, so we **cluster** the run's changed files by combined
  time + folder + content-similarity proximity.

## What changes

Extends the existing `index-tree` pipeline (no new walk/diff machinery):

- **Recency.** Stamp `valid_from` = the file's `mtime` (naive-UTC) and
  `metadata.modified_source = "fs_mtime"` (a trust tier; leaves room for a future
  authoritative `graph_*` tier) on every document memory. Unlocks newer/older
  ordering.
- **Co-change (observed).** After the walk, take the files whose content changed
  in this run and cluster them with **HDBSCAN** over a precomputed composite
  distance: `w_t·Δtime + w_p·path-distance + w_c·(1−cosine embedding)`. Each
  cluster (HDBSCAN `min_cluster_size = 2`; lone edits are *noise* = not co-change)
  becomes a change-set: members get `metadata.changeset_id` and pairwise
  `concept_links` edges (`relates_to` with `strength` = HDBSCAN membership
  probability, `entity = "changeset:<id>"`; `before` for recency order).
- **Storage.** Defaults to the **working store** (`hermes.db`) — documents become
  first-class members of the unified memory graph — with the existing `--db` flag
  as the **optional** separate-DB target. All co-change writes are strictly scoped
  to `source = "document"` records and to the current run's changed files, so they
  never touch the user's real memories.
- **Queries.** `mintmory docs timeline` (newer→older) and `mintmory docs
  changed-with <path>` (cluster peers, with strength + observed time + honesty
  label).
- **Dependency.** HDBSCAN ships in an **optional `cochange` extra**
  (`scikit-learn`), consistent with ADR-0004's light core. Recency always works;
  co-change runs when the extra is installed and ≥2 files changed, else a one-line
  install hint is logged.

Default `index-tree` behaviour (without co-change) is unchanged except that
document memories now carry `valid_from`/`modified_source` — additive metadata.

## Honest limit (carried into docs + query output)

Without version control, MintMory cannot know two files were changed in the same
*logical edit*. It observes that their content changed within the same run **and**
that they are temporally/structurally/topically close. "Changed together" therefore
means "co-changed in the same observed window," never an atomic commit; its
resolution is bounded by how often `index-tree` is run. Recency is heuristic when
sourced from filesystem `mtime` (the `modified_source` tier records this).

## Impact

- Affected specs: **ingestion** (ADDED requirements).
- Affected code: `core/cochange.py` (new — pure clustering + change-set planning +
  read queries), `core/config.py` (`DocumentSettings`), `cli/main.py`
  (`index-tree` co-change pass + `docs timeline`/`docs changed-with`),
  `packages/core/pyproject.toml` (`cochange` extra).
- Migrations: none (reuses `valid_from`, `metadata`, `concept_links`,
  `index_manifest`).
- Out of scope (future): Microsoft Graph (delta/`/versions`/activities),
  authoritative cloud recency + within-file version history, scheduled/webhook
  sync, MCP exposure, OOXML/PDF internal-date extraction.
