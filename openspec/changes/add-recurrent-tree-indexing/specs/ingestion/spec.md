# Capability: ingestion (delta) — tree indexing (manual cadence)

## ADDED Requirements

### Requirement: Online-only-safe tree indexing
`mintmory index-tree` SHALL walk a directory tree with `os.stat` only, and SHALL NOT
open or read an online-only file (a cloud placeholder: `st_blocks == 0` and
`st_size > 0`) unless the user opts in to a budgeted pass (`--content`, `--vision`).
Indexing a cloud-backed library with default options therefore triggers no
download. Local small plain-text files MAY be read by default (see "Default
text-content pass skips online-only files").

#### Scenario: Placeholder files are indexed without download
- **WHEN** `mintmory index-tree` runs with default options over a tree of online-only placeholders
- **THEN** every file is recorded from its metadata (stat only), no file is opened, and no download is triggered.

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
Downloading and converting binary documents (`--content`) SHALL be opt-in and
bounded by a download budget (`--max-download-mb`) and a type filter
(`--content-types`). The inline text-content pass for small plain-text files is the
one content read that is on by default, and it never reads online-only files.

#### Scenario: Content pass respects the budget
- **WHEN** `--content` is set with `--max-download-mb`
- **THEN** files are downloaded+converted until the budget is reached, after
  which remaining files fall back to metadata-only and the run reports the cutoff.

### Requirement: Scoping, exclusions, and collection tagging
The system SHALL support include/exclude globs (`--include`, `--exclude`) and a
collection tag stamped on every produced memory and manifest row, so a source can
be filtered or swept as a unit (and optionally targeted to a dedicated DB with
`--db`). Build artifacts are excluded only when the caller lists them in
`--exclude`; there is no default denylist.

#### Scenario: Excluded files and folders are skipped
- **WHEN** a tree contains build artifacts (`.dll`/`.exe`/`.jar`) and a `Personal/` folder, and `index-tree` runs with `--exclude "*.dll,*.exe,*.jar,Personal/**"`
- **THEN** those files produce no memories, and every produced memory carries the collection tag.

#### Scenario: Without --exclude, artifacts are indexed as metadata
- **WHEN** the same tree is indexed without `--exclude`
- **THEN** each artifact gets a metadata + folder-context record like any other non-text file (no default denylist is applied).

### Requirement: Default text-content pass skips online-only files
The inline text-content pass (on by default via `--text-content`; suffixes in
`mintmory.core.conversion.TEXT_SUFFIXES`, size up to `--text-max-kb`) SHALL NOT read
a file whose walk entry has `online_only` set. That file SHALL be indexed as
metadata only (manifest `index_mode` `metadata`), and the run report SHALL count it
in a `text-skipped-online-only` row.

#### Scenario: An online-only text file is not read by default
- **GIVEN** a tree with a local `local.txt` and a `cloud.txt` that the walk reports as online-only
- **WHEN** `mintmory index-tree <tree> --collection lib` runs with default options
- **THEN** the command exits 0, `extract_markdown` is never called with `cloud.txt`, no `category='fact'` memory holds `cloud.txt`'s body, the manifest row of `cloud.txt` has `index_mode='metadata'` and `online_only=1`, `local.txt` is still full-texted (`index_mode='content'`), and the report table has a row `text-skipped-online-only` whose value is `1`.

#### Scenario: The count is per run and the row is shown only when non-zero
- **WHEN** the same command runs a second time on the unchanged tree
- **THEN** the row `text-skipped-online-only` again shows `1` (every scanned online-only text file within the size cap is counted, unchanged or not); and a run in which no text file is online-only, or a run with `--no-text-content`, prints no `text-skipped-online-only` row.

#### Scenario: The budgeted content pass can still fetch it on request (fresh DB)
- **GIVEN** an empty DB and the same tree
- **WHEN** the run is `mintmory index-tree <tree> --collection lib --content --content-types txt`
- **THEN** `cloud.txt` is read by the content pass, its size counts toward the `downloaded` row and the download budget, its manifest `index_mode` is `content`, and it is NOT counted in `text-skipped-online-only` (no such row).

### Requirement: A metadata row is upgraded by a later content run without --force
The unchanged check in `index_tree` (`packages/cli/src/mintmory/cli/main.py`, the `existing = store.manifest_get(path_str)` block) SHALL skip a file only when its `size` and `mtime` match the manifest row AND the row is "covered": `index_mode` is `content` or `vision`, or the mode this run wants (`desired_mode`) is `metadata`. Therefore a row with `index_mode='metadata'` whose file is unchanged is re-indexed, with no `--force`, when this run wants `content` (it is not counted as `unchanged`); a row with `index_mode='content'` is never downgraded to `metadata` by a later run (it is counted as `unchanged`), even when that later run skips the file as online-only. This is existing behaviour; this change adds scenarios for it and does not modify the check.

#### Scenario: Default run, then a content run, upgrades the file without --force
- **GIVEN** the tree of the first scenario, indexed once with default options (so `cloud.txt` has `index_mode='metadata'`, `online_only=1`; `local.txt` has `index_mode='content'`), no file touched since
- **WHEN** `mintmory index-tree <tree> --collection lib --content --content-types txt` runs (no `--force`)
- **THEN** `cloud.txt` is read exactly once and its row becomes `index_mode='content'`; its previous metadata memory is replaced, not duplicated (one memory per path for the file record); `local.txt` is counted in `unchanged`; the `unchanged` row shows `1`; no `text-skipped-online-only` row is printed.

#### Scenario: A content row is not downgraded by a later default run
- **GIVEN** the DB left by the previous scenario
- **WHEN** `mintmory index-tree <tree> --collection lib` runs with default options
- **THEN** `cloud.txt` stays `index_mode='content'` and is counted in `unchanged` (the row `unchanged` shows `2`); `cloud.txt` is not opened; the `text-skipped-online-only` row shows `1`, because the counter is per scanned file and runs before the unchanged check.

#### Scenario: Budget exhausted, online-only text falls back to metadata
- **GIVEN** a fresh DB and two online-only files `a.txt` and `b.txt` (scanned in that order), run with `--content --content-types txt --max-download-mb 0.000001`
- **WHEN** the run finishes
- **THEN** `a.txt` is read (it crosses the budget, so `budget_hit` becomes true) and gets `index_mode='content'`; `b.txt` is not read, keeps `index_mode='metadata'`, and IS counted in `text-skipped-online-only` (row shows `1`), because it is an online-only text file that was not read.

#### Scenario: Empty tree
- **WHEN** `index-tree` runs on an empty directory with default options
- **THEN** it exits 0, `scanned` is `0`, and no `text-skipped-online-only` row is printed.

### Requirement: Code is located by name
Units that edit `index_tree` SHALL locate code by function and variable name (`text_eligible`, `want_binary`, `desired_mode`, `store.manifest_get`), not by line number; line numbers in `tasks.md` are as of staging a08aee3 and shift when `fix-cochange-tools-on-postgres` merges first.

#### Scenario: Names resolve on the merged base
- **WHEN** the dependency `fix-cochange-tools-on-postgres` has merged
- **THEN** `grep -n "text_eligible\|want_binary\|desired_mode" packages/cli/src/mintmory/cli/main.py` still finds the lines the task edits.
