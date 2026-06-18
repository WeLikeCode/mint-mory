# Change: Recurrent, online-only-aware tree indexing for Hermes

**ID:** `add-recurrent-tree-indexing`
**Status:** IMPLEMENTED (manual cadence) — `mintmory index-tree`. See `results.md`.
**Capability:** `ingestion`
**Owner:** team-lead (Claude)

> Decisions taken: scope=**everything** (incl. Personal); depth=metadata for all +
> **opt-in full-text** for docs (bounded download); cadence=**manual** (no launchd
> installed); target=**shared `hermes.db`**, collection-tagged
> `onedrive:ExampleOrg`. Re-index modes: **(a) incremental** (default — new/
> changed only) and **(b) `--force`** (re-index everything). Gap G5 (image/diagram
> OCR/vision) remains future work; G4 launchd shipped as design only (cadence=manual).

## Why

Hermes should continuously index a shared knowledge folder so its memory tracks
the team's living document set. The concrete target:

```
/Users/you/Library/CloudStorage/OneDrive-SharedLibraries-ExampleOrg
```

### Discovery (measured 2026-06-17, stat-only — no downloads)

| Metric | Value |
|---|---|
| Files | **15,266** (594 dirs) |
| Apparent size | **35.15 GB** |
| **Actually local** | **1.4 MB** → **15,249 / 15,266 files are online-only placeholders** |
| Dominant content | **~12,900 images/diagrams** (12,510 jpg, 198 png, 100 jpeg, 36 svg, 39 Adobe XD, 14 DWG, 11 Visio, 33 psd, 30 eps, 21 gif) |
| Real documents | **~1,200** (332 pdf, 101 xlsx, 86 docx, 43 pptx, 9 doc, 26 txt, 342 html, 92 xml, 13 json) |
| Build artifacts (noise) | 531 dll, 66 pdb, 64 exe, 58 zip, 56 jar, 12 rar, 37 crc, 35 config, 17 ttf, 17 aax |
| Layout | All under `Acme - Documents`; jpgs concentrated in `002_Team Drive` (10,149) and `Personal` (2,246 personal photos); docs spread across `Acme - Documents` |
| Hermes DB today | `~/.mintmory/hermes.db` = 420 memories, 4.2 MB |
| markitdown | **not installed** (`docs` extra not synced) |

### What this means

1. **Content reads = downloads.** `mintmory ingest` reads every file
   (`extract_markdown` → `read_text`/markitdown). Pointed at this tree it would
   pull **~35 GB** out of OneDrive. So **metadata + context indexing must be the
   default**, and full-text extraction a deliberate, bounded opt-in — the
   opposite of MM-11's "convert everything you can".
2. **The user's "index metadata + contextual info when a file isn't indexable as
   text" is the *primary* mode here**, not a fallback — it applies to ~95% of the
   tree (all images/diagrams + every online-only file we choose not to download).
3. **Recurrence + incrementality are mandatory.** Re-converting 1,200 docs and
   re-walking 15k files on every run is wasteful and (for content) expensive;
   runs must detect change (path + size + mtime) and update in place.
4. **Privacy / signal.** 2,246 `Personal` photos and a pile of build artifacts
   are noise (and possibly private) for a shared agent memory; scope + exclusions
   matter, as does whether this lands in the shared `hermes.db` or a dedicated DB.

## What changes (proposed)

A new **tree indexer** capability:

1. **`mintmory index-tree`** — walk configured roots, **stat-only by default**
   (no content reads ⇒ no downloads), emitting one *file-record* memory per file
   capturing name, path, folder, type, size, mtime, online-only flag, and
   **folder context** (sibling files, parent area).
2. **Incremental manifest** — per-path state (size, mtime, content hash, index
   mode) so each run only (re)indexes new/changed files and **updates in place**
   instead of duplicating.
3. **Opt-in content depth** — for selected types/folders, download + markitdown
   (MM-11) + chunk the full text, under an explicit **download budget**.
4. **Recurrence** — a launchd LaunchAgent (daily by default) invoking the
   indexer; plus `--once` for manual runs.
5. **Scoping & exclusions** — include/exclude globs and folder filters (default:
   drop build artifacts; `Personal` photos configurable).

The detailed interface contract is in `design.md`; the **gaps that block a clean
implementation** (and the decisions needed) are in `gaps.md`.

## Impact

- **Affected specs:** `ingestion` (deltas in `specs/`).
- **New code (planned):** a tree-indexer module + `mintmory index-tree` CLI +
  manifest table/migration; reuses MM-11 `conversion` for the opt-in content pass.
- **Ops:** a `~/Library/LaunchAgents` plist for recurrence (install gated on
  user go-ahead — outward-facing).
- **Data:** writes into `hermes.db` (or a dedicated DB — see `gaps.md` G6).
