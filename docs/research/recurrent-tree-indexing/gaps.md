# Gap analysis — recurrent tree indexing

What MintMory does **not** do today that this task needs. Each gap notes the
current behaviour, why it blocks the task, and the proposed resolution. Severity:
🔴 blocks the default (metadata) mode · 🟠 blocks the opt-in content mode · 🟡 quality/ops.

---

## G1 🔴 No online-only / no-download awareness
- **Now:** `mintmory ingest` → `extract_markdown` → `read_text`/markitdown reads
  bytes unconditionally. On macOS OneDrive Files-On-Demand, reading a placeholder
  triggers a full download. 15,249/15,266 files here are placeholders (35 GB).
- **Blocks:** any whole-tree pass would download ~35 GB.
- **Resolution:** a **stat-only walk** (size/mtime/flags via `os.stat`, no `open`)
  as the default. Detect placeholders (`st_blocks == 0 && st_size > 0`) and record
  an `online_only` flag; never read content unless the content pass is explicitly
  enabled for that file.

## G2 🔴 No metadata + context indexing
- **Now:** a memory is always built from file *content*. There is no path that
  turns "a file exists here, next to these files" into a memory.
- **Blocks:** the user's core requirement ("if not indexable as text, index the
  metadata and contextual information, e.g. being in the same folder as x,y,z").
- **Resolution:** a deterministic *file-record* renderer → one memory per file:
  filename, relative path, parent folder, type label, size, mtime (absolute),
  online-only flag, and **folder context**: parent-area, depth, and a bounded
  sample of sibling files in the same directory. `category=context` (or
  `reference`), `source=document`, metadata carries the structured fields.

## G3 🔴 No incremental change-detection or upsert-by-path
- **Now:** dedup is **exact-content match only** (`SELECT 1 ... WHERE content=?`).
  Re-runs re-read/re-convert every file; a *changed* file is stored as a second
  memory (old one orphaned); there is no per-source state.
- **Blocks:** "recurrent" indexing — every run would be full-cost and would
  accumulate stale duplicates as files change.
- **Resolution:** an **index manifest** keyed by absolute path →
  `(size, mtime, content_hash, index_mode, memory_ids, last_seen)`. Each run:
  skip unchanged (same size+mtime), re-index changed (and **update/replace** the
  prior memories for that path), and mark missing paths as removed/archived.
  Needs a small schema addition + an upsert/replace-by-path storage method.

## G4 🔴 No recurrence / scheduling
- **Now:** the CLI is one-shot; nothing re-runs it.
- **Blocks:** "recurrent".
- **Resolution:** a launchd **LaunchAgent** (`StartCalendarInterval` daily, or
  `StartInterval`) running `mintmory index-tree --once`; logs to a file; `--once`
  is the idempotent unit of work. (Install is outward-facing → user-gated.)

## G5 🟠 No image / diagram understanding
- **Now:** markitdown on a `.jpg`/`.png` yields ~EXIF only (often empty for these);
  diagram formats here — `.xd` (Adobe XD), `.vsdx` (Visio), `.dwg` (CAD), `.psd`,
  `.eps`, `.svg` — are **not** markitdown-convertible. No OCR, no vision captioning.
- **Blocks:** turning the ~12,900 images/diagrams into *searchable text* (beyond
  metadata+context, which G2 covers).
- **Resolution (future):** optional OCR (tesseract) and/or a vision-LLM captioning
  pass behind a new extra + budget; out of scope for the first cut. Until then,
  images/diagrams get **metadata + context only** (which satisfies the stated
  requirement).

## G6 🟡 No per-source namespace / collection; shared-DB blast radius
- **Now:** all memories share one flat store. Writing 15k file-records (incl.
  2,246 personal photos) into `hermes.db` (currently 420 memories, also written
  by Ares) 36×'s it and dilutes recall with low-signal/private rows.
- **Resolution:** index into a **dedicated DB** (e.g. `~/.mintmory/onedrive.db`)
  *or* tag every row with a `collection`/`source_root` in metadata so it can be
  filtered/swept as a unit. Decision needed (see questions).

## G7 🟠 No download budget / selective content controls
- **Now:** no way to say "download at most N MB" or "full-text only `.docx`/`.pdf`
  under folder X". The content pass would be all-or-nothing.
- **Resolution:** `--content-types`, `--content-globs`, and `--max-download-mb`
  controls on the content pass; stop (and report) when the budget is hit.

## G8 🟡 No index-run report / observability
- **Now:** ingest prints a one-line summary; no persisted run record.
- **Resolution:** emit (and optionally persist) a per-run report:
  scanned / new / changed / unchanged / removed / downloaded-bytes / failures,
  reusing the OTel seam (MM-6) for spans.

---

## Decisions required before implementation
These are genuinely the user's call (cost / privacy / cadence) and scope the build:

1. **Scope** — which files become memories? (docs only · docs + non-photo file
   metadata · everything incl. all image metadata) and do we exclude `Personal`?
2. **Content depth** — metadata-only (no downloads) vs also full-text the
   documents (bounded download). Start metadata-only is the safe default.
3. **Cadence** — daily · hourly · manual-only for now.
4. **Target DB** — dedicated `onedrive.db` vs the shared `hermes.db` (tagged).

## Build order once decided
1. Storage: manifest table + `upsert_by_source(path, ...)` / replace-by-path (G3, G6).
2. Core: stat-only walk + file-record/context renderer (G1, G2).
3. CLI: `mintmory index-tree` (scope/exclude/content/budget flags) (G7).
4. Content pass: reuse MM-11 conversion for opted-in files (G7).
5. Recurrence: launchd plist + `--once` + logging (G4).
6. Report + tests + docs (G8).
7. (Future) image/diagram OCR/vision (G5).
