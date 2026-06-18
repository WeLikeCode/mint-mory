# Capability: ingestion (delta) — recurrent tree indexing

## ADDED Requirements

### Requirement: Online-only-safe tree indexing
The system SHALL index a directory tree without reading file contents by default,
so that indexing a cloud-backed (online-only) library does not trigger downloads.

#### Scenario: Placeholder files are indexed without download
- **WHEN** `mintmory index-tree` runs over a tree of online-only placeholders
- **THEN** every file is recorded from its metadata (stat only), no file is
  opened, and no download is triggered.

### Requirement: Metadata + folder-context records
For any file not indexed as text, the system SHALL create a memory from its
metadata and folder context, including a bounded sample of sibling files.

#### Scenario: An image is indexed by metadata and neighbours
- **WHEN** a `.jpg` (or any non-text file) is indexed
- **THEN** a memory is stored with its name, path, type, size, mtime, online-only
  status, and the names of other files in the same folder.

### Requirement: Incremental, idempotent runs
The system SHALL maintain per-path index state and SHALL, on each run, skip
unchanged files, re-index changed files in place (replacing prior memories for
that path), and optionally archive memories for files that have disappeared.

#### Scenario: Re-run skips unchanged and updates changed
- **WHEN** `index-tree` runs twice and one file's size/mtime changed between runs
- **THEN** unchanged files produce no new memories, the changed file's memories
  are replaced (not duplicated), and the manifest reflects the new state.

### Requirement: Bounded, opt-in content extraction
Full-text extraction (download + convert) SHALL be opt-in and bounded by a
download budget and type/glob filters.

#### Scenario: Content pass respects the budget
- **WHEN** `--content` is set with `--max-download-mb`
- **THEN** files are downloaded+converted until the budget is reached, after
  which remaining files fall back to metadata-only and the run reports the cutoff.

### Requirement: Recurrent execution
The system SHALL provide a recurring scheduler integration (launchd) whose unit
of work is a single idempotent `--once` pass, with run logging.

#### Scenario: Scheduled run is idempotent
- **WHEN** the scheduled `index-tree --once` runs on an unchanged tree
- **THEN** it makes no new memories and exits 0.

### Requirement: Scoping, exclusions, and collection tagging
The system SHALL support include/exclude globs, a default build-artifact
denylist, and a collection tag stamped on every produced memory so a source can
be filtered or swept as a unit (and optionally targeted to a dedicated DB).

#### Scenario: Artifacts and excluded folders are skipped
- **WHEN** a tree contains build artifacts (.dll/.exe/.jar/…) and an excluded
  folder
- **THEN** those files produce no memories, and every produced memory carries the
  collection tag.
