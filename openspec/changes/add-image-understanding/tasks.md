# Tasks — `add-image-understanding`

Disjoint file ownership so parallel Sonnet agents do not collide. Core work is
split by file: **Group 1 owns `core/types.py`** (the `ImageJob` /
`ImageDescription` models — pure additions every other group imports), **Group 2
owns `core/config.py`** (`VisionProvider` + `VisionSettings`), **Group 3 owns the
NEW `core/vision.py`** (the provider seam + SVG extractor + `image_jobs` /
`image_caption_put` — the critical path), **Group 4 owns `core/storage.py` +
`core/schema.sql`** (the `index_mode` CHECK widening + the two additive read
helpers). Transports are split by package (Groups 5/6/7), packaging (Group 8),
tests by package (Group 9), docs (Group 10).

**Order:** Groups 1, 2, 4 first (pure additions / storage helpers — independent).
Then Group 3 (the vision module — depends on the types/config/storage helpers and
freezes the §5/§7 signatures). Groups 5/6/7 (transports) run in parallel after
Group 3 lands `image_jobs` / `image_caption_put`; they treat design §11 as fixed.
Group 8 (extras) is independent and can run anytime. Group 9 (tests) runs
alongside/after its corresponding impl group. Group 10 (docs) last.

## 1. Core types — owns `core/types.py`
- [x] 1.1 Add an "Image understanding types" block (after the dreaming-types
      block, next to `SummaryJob`) with `ImageJob` (file_id, path, rel, mime,
      size, online_only, image_b64: str|None = None, current_description:
      str|None = None, oversized: bool = False) and `ImageDescription` (record:
      MemoryRecord, file_id, source_image, replaced_description_id: str|None =
      None), matching the existing Pydantic style (design §3). No validators.

## 2. Core config — owns `core/config.py`
- [x] 2.1 Add `VisionProvider(str, Enum)` (AGENT="agent", LLM="llm", OCR="ocr")
      next to `EmbeddingProvider`/`LLMProvider` (design §2).
- [x] 2.2 Add `VisionSettings(BaseSettings)` (env prefix `MINTMORY_VISION_`):
      provider (default AGENT), max_image_mb, downscale_max_px, max_download_mb,
      model/base_url/api_key/tesseract_cmd, + `max_image_bytes` /
      `max_download_bytes` properties (design §2). Defaults reproduce today.
- [x] 2.3 Register `vision: VisionSettings = Field(default_factory=VisionSettings)`
      on the aggregate `Settings` (design §2).

## 3. Core vision — owns the NEW `core/vision.py` (critical path)
- [x] 3.1 Module docstring (mirrors the house style: "no LLM, no network in the
      agent path; pure-Python SVG; lazy optional Pillow"). Suffix sets
      `RASTER_SUFFIXES`, `SVG_SUFFIXES`, `IMAGE_SUFFIXES`,
      `PROPRIETARY_IMAGE_SUFFIXES` + a `_mime_for(suffix)` map (design §1, §5b).
- [x] 3.2 `Captioner` Protocol (`runtime_checkable`) + `ImageInput`
      `@dataclass(frozen=True)` (design §4).
- [x] 3.3 `captioner_from_settings(settings=None) -> Captioner | None`: AGENT →
      None; LLM/OCR → raise `NotImplementedError` with the clear messages from
      design §4. ONLY place that branches on provider.
- [x] 3.4 `extract_svg_text(svg_bytes) -> str`: stdlib `xml.etree.ElementTree`,
      namespace-agnostic local-tag match (`text/tspan/title/desc/textPath`),
      trim/drop-empty/join `\n`/collapse adjacent dups, `""` on ParseError or no
      text, never raises (design §6).
- [x] 3.5 `image_jobs(adapter, *, include_all=False, include_bytes=False,
      limit=0, settings=None) -> list[ImageJob]`: discover raster image
      file-records (exclude descriptions via `metadata.kind`, exclude SVG +
      proprietary); needs-redescribe predicate via
      `adapter.get_annotating_descriptions(file_id, 1)`; deterministic order
      (rel, file_id); post-selection `limit`; hybrid-bytes per design §5b
      (online_only OR include_bytes; budget; size cap → oversized; lazy Pillow
      downscale; base64) (design §5).
- [x] 3.6 `image_caption_put(adapter, file_id_or_path, description, *,
      settings=None) -> ImageDescription`: resolve id-or-path (via
      `adapter.find_image_file_record` for the path case; `KeyError` if
      unresolved); ARCHIVE existing active `image_description`s ANNOTATES the
      file-record FIRST (capture `replaced_description_id`); add the new
      `context`/`document`/`is_note=False` memory (`metadata
      {kind:'image_description', source_image, collection?}`); ANNOTATES-link it
      (`LinkSource.INFERENCE`, strength/confidence 1.0); return `ImageDescription`
      (design §7). Idempotent / no-drift.
- [x] 3.7 Lazy, guarded Pillow downscale helper (used by 3.5): `try: from PIL
      import Image except ImportError: return raw`; never raise on a corrupt image
      (design §5b step 4).

## 4. Core storage + schema — owns `core/storage.py` + `core/schema.sql`
- [x] 4.1 `schema.sql`: widen `index_manifest.index_mode` CHECK to
      `('metadata','content','vision')` + update the inline comment (design §8a).
- [x] 4.2 `storage.py`: `_ensure_index_mode_vision(conn)` best-effort idempotent
      migration (rebuild table when the stored CREATE sql has the old 2-value
      CHECK and lacks 'vision'); call it in `initialise()` right after
      `_ensure_is_note_column` (design §8a). `manifest_upsert` is UNCHANGED.
- [x] 4.3 `storage.py`: `get_annotating_descriptions(memory_id, cap) ->
      list[MemoryRecord]` — reverse ANNOTATES, `is_note=0`, `is_archived=0`,
      `json_extract(metadata,'$.kind')='image_description'`, ORDER BY created_at
      DESC. MUST NOT modify `get_annotating_notes` (design §8b).
- [x] 4.4 `storage.py`: `find_image_file_record(path_or_rel) -> MemoryRecord |
      None` — most-recent active file-record matching metadata path/rel with an
      image suffix and NO `kind='image_description'` (design §8c).

## 5. Transport: MCP — owns `packages/mcp/src/mintmory/mcp/server.py`
- [x] 5.1 `image_jobs(include_all=False, include_bytes=False, limit=0)` tool:
      `_get_store()` + `load_settings().vision` + `vision.image_jobs(...)` +
      `model_dump(mode="json")` list (design §11a).
- [x] 5.2 `image_caption_put(file_id_or_path, description)` tool: reject empty
      (`bad_request`), `KeyError` → `not_found`, else
      `vision.image_caption_put(...).model_dump(mode="json")` (design §11a).
- [x] 5.3 Update FastMCP `instructions` (the image_jobs → describe →
      image_caption_put loop; no vision backend) + the tool-map comment block at
      the top of the file (design §11a).

## 6. Transport: CLI — owns `packages/cli/src/mintmory/cli/main.py`
- [x] 6.1 `index-tree --vision/--no-vision` flag: add `want_vision` beside
      `text_eligible`/`want_binary` (image suffix, not proprietary); extend
      `desired_mode`/`covered` for `index_mode='vision'`; SVG inline via
      `extract_svg_text` + `image_caption_put` (budget-aware, content_hash =
      blake2b(svg_text)); raster via `captioner_from_settings` — agent: count
      `images-queued`; llm/ocr: catch `NotImplementedError` once → clear message +
      non-zero exit; manifest `index_mode='vision'`; new report rows; UNCHANGED
      without `--vision` (design §10).
- [x] 6.2 `image-jobs` command (`--all/--needed`, `--bytes/--no-bytes`,
      `--limit`, `--json`; rich table else) (design §11b).
- [x] 6.3 `image-caption-put` command (file_id_or_path arg; text arg → `--file` →
      stdin; strip + reject empty; `KeyError` → `typer.BadParameter`) (design
      §11b).
- [x] 6.4 Update the module docstring command list (top of `main.py`).

## 7. Transport: HTTP API — owns `packages/api/src/mintmory/api/{schemas.py,app.py}`
      + `docs/openapi/mintmory.yaml`
- [x] 7.1 `ImageCaptionPut` request schema (`description`, required, minLength 1)
      in `schemas.py` (design §11c).
- [x] 7.2 `GET /images/jobs` (→ `list[ImageJob]`, `include_all`/`include_bytes`/
      `limit` query) and `PUT /images/{file_id}` (→ `ImageDescription`, body
      `ImageCaptionPut`, `KeyError`→404) under a new "Images" tag; add
      `ImageJob`/`ImageDescription`/`ImageCaptionPut` imports (design §11c).
- [x] 7.3 OpenAPI YAML: add the two paths + `ImageJob`, `ImageDescription`,
      `ImageCaptionPut` component schemas (mirror the `SummaryJob`/`SummaryPut`
      style; `ImageDescription.record` → `$ref MemoryRecord`) (design §11c).

## 8. Packaging — owns `packages/core/pyproject.toml`
- [x] 8.1 Add `[image] = ["Pillow>=10.0"]` and `[ocr] = ["pytesseract>=0.3.10"]`
      optional extras (mirror `[docs]`/`[otel]`). Confirm neither is added to the
      required `dependencies` list (design §12).

## 9. Tests — owns the `tests/` trees (per package; disjoint from impl groups)
- [x] 9.1 core (`packages/core/tests/`): types round-trip; `VisionSettings`
      defaults + env parse; `extract_svg_text` (namespaced/plain/malformed/empty);
      `captioner_from_settings` (agent→None, llm/ocr→raise); `image_jobs`
      (needs-redescribe, include_all, SVG/proprietary excluded, limit, hybrid
      bytes, size cap/oversized, Pillow-absent); `image_caption_put` (ANNOTATES +
      INFERENCE + is_note=0 + kind metadata; resolve by id/path; KeyError;
      idempotent archive + replaced_description_id; no-drift round-trip);
      `get_annotating_descriptions` (no overlap with notes); `find_image_file_record`;
      `index_mode='vision'` CHECK migration (old-CHECK DB + fresh DB both accept
      it; idempotent) (design §14).
- [x] 9.2 cli (`packages/cli/tests/`): `index-tree --vision` (svg-described/
      images-queued/vision-skipped counts; manifest index_mode='vision';
      incremental re-run; unchanged without `--vision`; llm-provider exits
      non-zero); `image-jobs` (table/`--json`/`--all`/`--bytes`/`--limit`);
      `image-caption-put` (text/`--file`/stdin/empty/unknown-path) (design §14).
- [x] 9.3 mcp (`packages/mcp/tests/`): `image_jobs` (include_all/limit);
      `image_caption_put` round-trip (image drops from default jobs); empty →
      bad_request; unknown → not_found; provider=agent (design §14).
- [x] 9.4 api (`packages/api/tests/`): `GET /images/jobs` 200 + query params;
      `PUT /images/{file_id}` 200 → ImageDescription; unknown id → 404; put
      removes the image from default jobs (design §14).

## 10. Docs — owns `README*`, agent/onboarding docs, `openspec/README.md`
- [x] 10.1 README / agent doc: "image understanding (agent-supplied vision)"
      section — the `image_jobs → agent describes → image_caption_put` loop;
      SVG is free (pure-Python); raster needs the agent; proprietary is
      metadata-only; `--vision` flag; no vision backend required; `[image]`/`[ocr]`
      extras + the llm/ocr seam (future).
- [x] 10.2 `openspec/README.md`: add the `add-image-understanding` bullet.

## 11. Review & integration (orchestrator, Opus)
- [x] 11.1 Verify gates per package (pytest cov ≥ 80 / ruff / ruff format /
      mypy --strict, line-length 100).
- [x] 11.2 Independent Opus reviewer: confirm (a) no-drift — `image_caption_put`
      then default `image_jobs()` omits the image; (b) defaults reproduce today —
      existing index-tree/ingest/search tests unedited + green, `--vision` off is
      a no-op, `get_annotating_notes`/`search()` untouched; (c) `agent` is the
      only implemented provider (`captioner_from_settings` returns None / raises);
      (d) no new REQUIRED dependency (Pillow/pytesseract optional + lazy); (e) the
      `index_mode` CHECK migration is idempotent and old DBs keep working;
      (f) descriptions are `is_note=0` and never enter `notes_on_results`.
- [x] 11.3 Orchestrator applies fixes, re-runs gates, commits.
