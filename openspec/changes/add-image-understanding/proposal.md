# Change: Image understanding (agent-supplied vision, provider seam)

**ID:** `add-image-understanding`
**Status:** proposed
**Capabilities:** `image-understanding` (new), `ingestion` (modified)
**Owner:** orchestrator (Opus)

## Why — gap G5

`mintmory index-tree` (add-recurrent-tree-indexing) records every file in a
cloud-backed tree as a *file-record*: name, type, size, mtime, online-only
status, and folder-sibling context. For an image or diagram that is **all** it
records — the image's own visual content (the text drawn inside it, and what it
depicts) is invisible to search. On the Hermes corpus that means roughly
**~12,900 images/diagrams** are indexed as metadata-and-neighbours only. A search
for the words on a whiteboard photo, the labels in an architecture diagram, or
"the screenshot of the parking settings screen" cannot match them, because that
text was never extracted.

This is the LEANN/tree-indexing **gap G5**, called out as future work in
`add-recurrent-tree-indexing` (`openspec/README.md`: "G5 image OCR + launchd
recurrence are future").

The fix mirrors the two patterns the codebase already proved:

- **MM-17 (agent-supplied summaries)** — `DreamingEngine.collect_summary_jobs`
  hands the agent a prepare-step work-list and `apply_summary` persists what the
  agent wrote, with a **no-drift** incremental property and **no LLM backend
  required** (the agent IS the LLM). Vision is the same shape: the active agent is
  already vision-capable, so it can read an image far better than any small local
  model — at no extra infrastructure cost. The only missing piece is **transport**:
  you cannot inject a vision callable across an MCP tool call. So we do the same
  prepare/apply split for images.
- **MM-16 (personal notes)** — a separate `MemoryRecord` is `ANNOTATES`-linked to
  the thing it is about, and reverse traversal surfaces it on search. An image
  *description* is exactly that: a record that annotates the image file-record.

Defaults reproduce today's behaviour exactly: without `--vision` and without
calling `image_jobs`, nothing changes.

## What changes

1. **A provider seam (`Captioner`).** A `Captioner` protocol
   `describe(image: ImageInput) -> ImageDescription`, selected by a new
   `MINTMORY_VISION_PROVIDER` config in a `VisionSettings` group (env
   `MINTMORY_VISION_*`), mirroring `NoteSettings`/`ConversionSettings`. Three
   providers, dispatched by a single factory:
   - `agent` (**DEFAULT, and the ONLY one implemented in v1**) — no backend; the
     active vision-capable agent supplies the text via a prepare/apply loop. There
     is no server-side captioner object for `agent`; the factory returns `None`
     and the prepare/apply core methods are used instead.
   - `llm` (**SEAM/STUB only**) — would call a vision model over an
     OpenAI-compatible vision tier (`MINTMORY_VISION_BASE_URL` / `_MODEL` /
     `_API_KEY`). The v1 factory raises a clear `NotImplementedError`
     ("vision provider 'llm' is not implemented; configure
     MINTMORY_VISION_PROVIDER=agent").
   - `ocr` (**SEAM/STUB only**) — local tesseract behind an optional `[ocr]`
     extra. The v1 factory raises the same kind of clear error.
   The seam (protocol + config + factory dispatch) MUST exist so `llm`/`ocr` drop
   in later **without touching callers**.

2. **Agent-supplied flow (v1 core), mirroring MM-17 EXACTLY in shape.** Two new
   functions in a new `core/vision.py` module (no LLM, no `Captioner` required):
   - `image_jobs(adapter, *, include_all=False, include_bytes=False, limit=0,
     settings=None) -> list[ImageJob]` — DISCOVERY over the already-indexed image
     **file-records** (the `category=context, source=document` memories
     `index-tree` writes, whose `metadata.ext` is a raster image suffix). By
     default returns only image file-records that NEED a (re)description: those
     with **no active** `image_description` memory `ANNOTATES`-linking them.
     `include_all=True` returns all image file-records regardless.
   - `image_caption_put(adapter, file_id_or_path, description, *, settings=None)
     -> ImageDescription` — persists the agent's combined text as a new
     `MemoryRecord` (`category=context, source=document, is_note=False, metadata
     {kind:"image_description", source_image: path}`) and `ANNOTATES`-links it to
     the image file-record. Idempotent: re-putting **archives the prior**
     `image_description` for that image before adding the new one, so a re-poll of
     `image_jobs` (default) does NOT re-surface it (the MM-17 no-drift property).

3. **SVG is self-describing (free, no model, no agent).** SVG `<text>` is just
   XML; a small pure-Python extractor (`extract_svg_text`) pulls it out. SVG
   images therefore get an `image_description` record **directly** from the
   extracted text — handled automatically during `index-tree --vision` and treated
   as already-described by `image_jobs` (an SVG with extractable text never
   surfaces as a raster job). Raster images
   (`.jpg/.jpeg/.png/.gif/.webp/.bmp`) need the agent/provider. Proprietary design
   formats (Adobe XD `.xd`, Visio `.vsdx`, AutoCAD `.dwg`, Photoshop `.psd`,
   `.eps`) stay metadata-only (render-then-vision is DEFERRED).

4. **`index-tree --vision`** — a new flag adding a **third content mode** beside
   `text_eligible` / `want_binary` for image suffixes, under the SAME download
   budget and incremental manifest, recording `index_mode="vision"`. In `agent`
   mode `--vision` surfaces/queues the raster jobs (reported as a count) and runs
   the free SVG extraction inline; for `llm`/`ocr` (future) it would run the
   provider inline. Without `--vision` the command is byte-for-byte unchanged.

5. **Transports (one core, three thin wrappers).** Built like
   `summary_jobs`/`summary_put` (MM-17) and the notes tools (MM-16):
   - MCP: `image_jobs(include_all=False, include_bytes=False, limit=0)` and
     `image_caption_put(file_id_or_path, description)`; FastMCP `instructions`
     note added.
   - CLI: `mintmory image-jobs` (rich/JSON) and `mintmory image-caption-put`
     (`--file`/stdin fallback for the description text).
   - HTTP: `GET /images/jobs` and `PUT /images/{file_id}`; `docs/openapi/
     mintmory.yaml` updated (paths + `ImageJob` / `ImageCaptionPut` schemas).

6. **Types** — `ImageJob` and `ImageDescription` in `core/types.py`.

7. **The ONE schema change** — widen the `index_manifest.index_mode` CHECK
   constraint from `('metadata','content')` to `('metadata','content','vision')`,
   using the same idempotent best-effort migration pattern as the existing
   `_ensure_is_note_column` / `_ensure_trigram` helpers. No other schema change;
   the `ANNOTATES` link type already exists in the `concept_links.link_type` CHECK.

8. **Optional extras** — `[image]` (Pillow, lazy-imported, for downscaling large
   image payloads) and `[ocr]` (pytesseract, for the future `ocr` provider). Both
   are **optional**; absent, vision still works (Pillow absent → just size-cap and
   skip oversized; `ocr` provider absent → the stub error already covers it).

## What this explicitly does NOT do

- **No automatic captioning of raster images.** v1 implements **only the `agent`
  provider**: the `llm` and `ocr` providers are a seam (protocol + config + factory
  dispatch) whose factory raises a clear "not implemented / configure" error. No
  vision model is called by MintMory in v1.
- **No structured OCR/caption split.** A description is ONE combined blob = what
  the image depicts + any legible text (OCR and caption together). A structured
  `{ocr, caption}` split is DEFERRED.
- **No proprietary-format support.** Adobe XD, Visio, DWG, Photoshop, EPS stay
  metadata-only; render-then-vision is DEFERRED.
- **No behaviour change to any existing path.** `index-tree` without `--vision`,
  `ingest`, `search`, `dream`, summaries, notes, and the metadata file-record
  shape are all unchanged. `get_annotating_notes` (which filters `is_note=1`) is
  untouched — image descriptions are `is_note=False` and use a SEPARATE reverse
  traversal so they never leak into the notes channel on search.
- **No new REQUIRED dependency.** Pillow is only behind `[image]` (lazy-imported);
  tesseract only behind `[ocr]` (and only reached by the stubbed `ocr` provider).
  The single SQLite file is unchanged apart from the `index_mode` CHECK widening
  (no new table, no new column).
- **No new search ranking.** Image descriptions are ordinary
  `category=context` memories: they enter FTS/vector search like any other content
  and are auto-included on the file-record via the existing `ANNOTATES` reverse
  traversal mechanism (a parallel, `is_note`-agnostic helper). No bespoke scoring.

## Impact

- **Core:** `core/types.py` (`ImageJob`, `ImageDescription`); new
  `core/vision.py` (`Captioner` protocol, `ImageInput`, `extract_svg_text`,
  `captioner_from_settings`, `image_jobs`, `image_caption_put`, the raster-suffix
  / image-byte helpers); `core/config.py` (`VisionSettings` +
  `Settings.vision`); `core/storage.py` (the `index_mode` CHECK migration helper;
  an additive reverse-`ANNOTATES` read helper for non-note description records —
  e.g. `get_annotating_descriptions` — and an image-file-record finder); `core/
  schema.sql` (widen the `index_mode` CHECK + comment).
- **CLI:** `packages/cli` — `index-tree --vision` integration (third content mode,
  SVG inline, manifest `index_mode="vision"`); `image-jobs` and
  `image-caption-put` commands.
- **Transports:** `packages/mcp` (`image_jobs`, `image_caption_put` +
  `instructions`); `packages/api` (`GET /images/jobs`, `PUT /images/{file_id}` +
  `ImageJob` response / `ImageCaptionPut` request schemas);
  `docs/openapi/mintmory.yaml`.
- **Packaging:** `packages/core/pyproject.toml` — `[image]` and `[ocr]` optional
  extras (mirroring `[docs]`/`[otel]`).
- **Tests:** core (types; SVG extractor; `image_jobs` needs-redescribe rule +
  hybrid-bytes + size cap; `image_caption_put` ANNOTATES + idempotent archive +
  no-drift round-trip; provider factory: `agent`→None, `llm`/`ocr`→raise; schema
  CHECK migration) + each transport + `index-tree --vision`.
- **Docs:** `README` + agent/onboarding doc (the `image_jobs → agent describes →
  image_caption_put` loop; SVG free; providers); `openspec/README.md` bullet.
- **Back-compat:** purely additive. Every default reproduces today's behaviour;
  `image_jobs`/`image_caption_put` require no configured backend; `index-tree`
  without `--vision` is unchanged. The only schema delta is a CHECK-constraint
  widening applied idempotently on startup (old DBs keep working; the new value is
  only ever written by `--vision`).
