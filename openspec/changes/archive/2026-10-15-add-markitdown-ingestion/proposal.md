# Change: Automatic document conversion for ingestion (markitdown)

**ID:** `add-markitdown-ingestion`
**Status:** proposed → in-progress
**Capability:** `ingestion`
**Owner:** team-lead (Claude)

## Why

`mintmory ingest` currently reads every file with
`Path.read_text(encoding="utf-8", errors="replace")`
(`packages/cli/src/mintmory/cli/main.py`). That is correct for `.md`/`.txt`
but **silently corrupts every binary office format**: a `.docx`, `.pdf`,
`.xlsx`, or `.pptx` ingests as mojibake (the decoded bytes of a zip/PDF
container), which then pollutes FTS, embeddings, entity extraction, and the
concept graph. In practice agents (e.g. Ares) have architecture docs in Word
/ PDF / Excel and cannot feed them to MintMory at all.

The data-ingestion quality ceiling is therefore set by *format coverage*, not
by the memory model. Microsoft's [`markitdown`](https://github.com/microsoft/markitdown)
converts PDF, Word, PowerPoint, Excel, HTML, CSV, EPUB, RTF and more into
clean Markdown with one API (`MarkItDown().convert(path).text_content`). Wiring
it into the ingest path — **automatically, by file type** — turns those formats
into first-class, indexable memories.

## What changes

1. **New core module `mintmory.core.conversion`** — a pure dispatcher:
   text files are read directly; convertible binaries are routed through
   markitdown; *all* output passes a conservative `clean_markdown()`
   formatting pass before it is returned. markitdown is imported lazily.
2. **New optional extra `docs`** (`markitdown[all]`) on `mintmory-core` and
   `mintmory-cli`. Core stays pure-Python by default — consistent with the
   embedder and the `[otel]`/`[local]` precedent. No new hard dependency.
3. **New `ConversionSettings` group** (`MINTMORY_CONVERT_*`): `enabled`,
   `max_file_mb`, `extra_text_suffixes_csv`, `enable_plugins`. Defaults
   preserve "just works" behaviour with a safety size cap.
4. **`mintmory ingest` auto-converts**: the default `--glob` gains the office
   suffixes, a `--convert/--no-convert` flag is added, each file is routed
   through the dispatcher, the chosen method is recorded in memory metadata
   (`converter: "text"|"markitdown"`), and conversion failures **skip the one
   file with a clear message** instead of aborting the run.
5. **`mintmory doctor`** reports whether the `docs` extra (markitdown) is
   installed and how many suffixes are convertible — a non-fatal readiness row.

Out of scope: MCP/HTTP ingest endpoints (no ingest tool exists there today),
OCR/image description, Azure Document Intelligence, and YouTube/URL inputs.
These are reachable later via markitdown options but are not wired now.

## Impact

- **Affected specs:** `ingestion` (new capability spec, see `specs/`).
- **Affected code:** `packages/core/src/mintmory/core/conversion.py` (new),
  `packages/core/src/mintmory/core/config.py`,
  `packages/core/pyproject.toml`, `packages/cli/pyproject.toml`,
  `packages/cli/src/mintmory/cli/main.py`.
- **Tests:** `packages/core/tests/test_conversion.py` (new),
  `packages/cli/tests/test_cli.py` (extended).
- **Docs:** `docs/hermes-onboarding.md`, this change folder.
- **Back-compat:** `.md`/`.txt` ingestion is byte-identical except for the
  conservative cleanup (CRLF→LF, trailing-whitespace strip, 3+ blank lines
  collapsed). No schema change, no migration. markitdown absent ⇒ text/markdown
  ingestion is unaffected; only binaries error with an install hint.
