# Capability: ingestion (delta) — image understanding in tree indexing

## ADDED Requirements

### Requirement: Vision content mode for tree indexing
`mintmory index-tree` SHALL provide a `--vision` flag adding a THIRD content mode
for image suffixes, beside the existing text-content and binary-content modes,
under the SAME download budget and the SAME incremental manifest. When `--vision`
is set, for each image file (raster or SVG, excluding proprietary design formats):

- SVG files SHALL be self-described inline (pure-Python text extraction → an
  `image_description` memory `ANNOTATES`-linked to the file-record), consuming the
  download budget only if the file is online-only and must be fetched.
- Raster files under the `agent` provider (the default) SHALL be QUEUED for the
  agent (counted and recorded in the manifest as vision-mode) rather than
  described inline — the agent describes them later via the image-job loop.
- Raster files under a future `llm`/`ocr` provider WOULD be described inline; in
  v1 selecting such a provider with `--vision` SHALL fail fast with a clear
  message (non-zero exit), not a stack trace.
- Proprietary design formats (`.xd`, `.vsdx`, `.dwg`, `.psd`, `.eps`) SHALL be
  skipped by the vision branch (counted as vision-skipped) and remain
  metadata-only.

Files handled by the vision branch SHALL record `index_mode="vision"` in the
manifest. The change-detection logic SHALL treat `index_mode in (content,
vision)` as already richer than metadata, so an unchanged tree is not
re-described on re-runs (incremental). Without `--vision`, NONE of this behaviour
SHALL run and `index-tree` SHALL be byte-for-byte unchanged.

#### Scenario: Vision flag describes SVGs and queues rasters
- **WHEN** `mintmory index-tree --vision` runs over a folder containing one `.svg`
  (with embedded text), one `.png`, and one `.xd`, with `provider=agent`
- **THEN** the `.svg` gets an `image_description` inline, the `.png` is queued for
  the agent (reported as images-queued), the `.xd` is reported as vision-skipped,
  and the `.svg` and `.png` manifest rows record `index_mode="vision"`.

#### Scenario: Vision runs are incremental
- **WHEN** `index-tree --vision` runs twice over an unchanged tree
- **THEN** the second run does not re-extract the SVG text or re-queue the raster
  (the manifest's `index_mode="vision"` marks them as already handled).

#### Scenario: Default behaviour is unchanged without the flag
- **WHEN** `mintmory index-tree` runs WITHOUT `--vision`
- **THEN** no image is described or queued, no `index_mode="vision"` row is
  written, and the produced file-records and report are identical to before this
  change.

#### Scenario: Unconfigured non-agent provider fails fast
- **WHEN** `index-tree --vision` runs with `MINTMORY_VISION_PROVIDER=llm` (or
  `ocr`) in v1
- **THEN** the command exits non-zero with a clear message directing the operator
  to use `MINTMORY_VISION_PROVIDER=agent` (no images are partially processed and
  no stack trace is shown).

## MODIFIED Requirements

### Requirement: Incremental, idempotent runs
The system SHALL maintain per-path index state and SHALL, on each run, skip
unchanged files, re-index changed files in place (replacing prior memories for
that path), and optionally archive memories for files that have disappeared. The
per-path index state SHALL record an `index_mode` of `metadata`, `content`, or
`vision`. A file already indexed at `content` or `vision` SHALL be treated as
covered (not downgraded to metadata) on a re-run when its size and mtime are
unchanged. Adding the `vision` index mode SHALL be backward-compatible: databases
created before this change (whose manifest permitted only `metadata`/`content`)
SHALL be migrated idempotently on startup to permit `vision`, preserving all
existing manifest rows, and SHALL continue to function if the migration cannot be
applied (falling back to writing only `metadata`/`content`).

#### Scenario: Re-run skips unchanged and updates changed
- **WHEN** `index-tree` runs twice and one file's size/mtime changed between runs
- **THEN** unchanged files produce no new memories, the changed file's memories
  are replaced (not duplicated), and the manifest reflects the new state.

#### Scenario: A vision-indexed file is not downgraded on a metadata re-run
- **WHEN** a file was indexed with `index_mode="vision"` and `index-tree` later
  runs WITHOUT `--vision` over the unchanged file
- **THEN** the file is treated as covered (unchanged), its description memory is
  retained, and the manifest still records `index_mode="vision"`.

#### Scenario: Old database is migrated to allow the vision index mode
- **WHEN** a database whose `index_manifest` was created before this change is
  opened and initialised
- **THEN** the manifest is migrated idempotently to permit `index_mode="vision"`
  with all existing rows preserved, and a subsequent `index-tree --vision` can
  write `vision` rows.
