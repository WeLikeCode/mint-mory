# Capability: ingestion (delta)

This change introduces the `ingestion` capability spec. All requirements below
are **ADDED**.

## ADDED Requirements

### Requirement: Automatic document conversion on ingest
The system SHALL convert binary document formats to Markdown automatically
during `mintmory ingest`, routing each file by its suffix, so that office
documents become first-class indexable memories without a manual pre-step.

#### Scenario: Word/PDF/Excel are converted, not corrupted
- **WHEN** a user runs `mintmory ingest report.docx` (or `.pdf`/`.xlsx`/`.pptx`)
  with the `docs` extra installed
- **THEN** the file is converted via markitdown to Markdown, cleaned, chunked,
  and stored, and each stored memory's metadata records `converter: "markitdown"`.

#### Scenario: Plain text and Markdown bypass conversion
- **WHEN** a user ingests a `.md` or `.txt` file
- **THEN** it is read directly (no markitdown), cleaned with the conservative
  formatter, and stored with metadata `converter: "text"`.

### Requirement: Conservative formatting normalisation
The system SHALL apply a conservative, idempotent `clean_markdown` pass to all
ingested content that normalises line endings, strips trailing whitespace,
collapses 3+ blank lines to one, trims leading/trailing blank lines, and removes
HTML comments — without reflowing prose, altering fenced code, or changing table
structure.

#### Scenario: Cleanup is idempotent
- **WHEN** `clean_markdown` is applied twice to any input
- **THEN** the second application returns a value identical to the first.

### Requirement: Optional dependency, graceful degradation
The system SHALL keep `markitdown` an optional extra (`docs`) and SHALL NOT make
`mintmory.core` import-time depend on it. When a convertible binary is ingested
without the extra installed, the system SHALL skip that file with an actionable
message and continue ingesting the remaining files.

#### Scenario: Missing extra skips one file, not the run
- **WHEN** a user ingests a directory containing `a.md` and `b.pdf` without the
  `docs` extra installed
- **THEN** `a.md` is ingested, `b.pdf` is skipped with a message naming
  `uv sync --extra docs`, and the command exits 0.

### Requirement: Ingest safety limits and control
The system SHALL enforce configurable limits that bound conversion of untrusted
input — on-disk size, **decompressed output size**, and **per-file wall-clock
time** — and SHALL provide a `--convert/--no-convert` flag plus `MINTMORY_CONVERT_*`
settings (including `MINTMORY_CONVERT_ENABLED` as a global off-switch) to control
conversion behaviour. No single file may hang the run.

#### Scenario: Oversized file is rejected
- **WHEN** a file exceeds `MINTMORY_CONVERT_MAX_FILE_MB` on disk
- **THEN** that file is skipped with a clear "too large" message and the run
  continues.

#### Scenario: Decompression bomb is bounded by output size
- **WHEN** a small compressed file (zip-based docx/xlsx, or a PDF) decompresses
  to markdown larger than `MINTMORY_CONVERT_MAX_OUTPUT_MB`
- **THEN** the conversion is rejected (the on-disk cap alone does not bound the
  decompressed output) and the run continues.

#### Scenario: A wedged conversion does not hang the run
- **WHEN** converting a file takes longer than `MINTMORY_CONVERT_TIMEOUT_S`
- **THEN** that file is skipped with a "timed out" message, the bulk run
  continues, and the process can still exit (the conversion runs in a daemon
  thread).

#### Scenario: Global off-switch disables conversion
- **WHEN** `MINTMORY_CONVERT_ENABLED=false`
- **THEN** convertible binaries are skipped (not converted) even with the `docs`
  extra installed, while text/markdown still ingest.

### Requirement: Empty conversion is surfaced, not silently dropped
When a conversion succeeds but produces no extractable text, the system SHALL
report that explicitly and SHALL NOT count the file as successfully converted.

#### Scenario: Image-only PDF yields a clear note
- **WHEN** a convertible file produces empty text (e.g. an image-only scan)
- **THEN** the file is reported as "produced no extractable text", stored as
  zero memories, and excluded from the converted tally.

### Requirement: Conversion readiness is observable
`mintmory doctor` SHALL report whether markitdown is installed and how many
formats are convertible, as a non-fatal readiness row.

#### Scenario: Doctor reports conversion readiness
- **WHEN** a user runs `mintmory doctor`
- **THEN** the output includes a `conversion` row stating markitdown
  availability, and the row never changes the command's healthy/unhealthy exit.
